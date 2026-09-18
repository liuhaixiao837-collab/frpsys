import os
import shutil
import tempfile

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from ops.models import AuditLog, Organization, SystemSetting, UserProfile
from ops.services.platform_security import login_ip_access_result, validate_password
from ops.test_license_support import verified_license_metadata


class PlatformSecuritySettingsTests(TestCase):
    """验证平台安全配置的持久化、登录约束和密码策略行为。"""

    def setUp(self):
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='platform-security@example.com',
            password='StrongPassword123!',
        )
        self.user = User.objects.create_user(
            username='security-login-user',
            password='StrongPassword123!',
        )
        license_setting = SystemSetting.objects.get(key='license.management')
        license_setting.value = verified_license_metadata()
        license_setting.save(update_fields=['value', 'updated_at'])
        self.client = APIClient()

    def setting(self, key):
        """返回测试数据库中指定键的平台配置。"""
        return SystemSetting.objects.get(key=key)

    def test_migration_creates_all_security_tab_defaults(self):
        """平台设置 Tab 依赖的安全、Licence 与时区配置必须由迁移统一入库。"""
        self.assertTrue(SystemSetting.objects.filter(key='security').exists())
        self.assertTrue(SystemSetting.objects.filter(key='security.login_whitelist').exists())
        self.assertTrue(SystemSetting.objects.filter(key='security.login_blacklist').exists())
        self.assertTrue(SystemSetting.objects.filter(key='security.password_policy').exists())
        self.assertTrue(SystemSetting.objects.filter(key='security.login').exists())
        self.assertTrue(SystemSetting.objects.filter(key='notification.delivery').exists())
        notification_setting = self.setting('notification.delivery')
        self.assertEqual(notification_setting.value['email']['recipient_limit_per_minute'], 5)
        self.assertEqual(notification_setting.value['email']['recipient_limit_per_hour'], 100)
        self.assertEqual(notification_setting.value['email']['recipient_limit_per_day'], 500)
        self.assertEqual(notification_setting.value['sms']['recipient_limit_per_minute'], 1)
        self.assertEqual(notification_setting.value['sms']['recipient_limit_per_hour'], 10)
        self.assertEqual(notification_setting.value['sms']['recipient_limit_per_day'], 50)
        self.assertTrue(SystemSetting.objects.filter(key='license.management').exists())
        filing_setting = self.setting('platform.filing')
        self.assertEqual(filing_setting.value['icp_record'], '冀ICP备2026010543号-3')
        self.assertEqual(filing_setting.value['public_security_record'], '冀公网安备13310102000221号')
        timezone_setting = self.setting('locale.timezone')
        self.assertEqual(timezone_setting.value['timezone'], 'Asia/Shanghai')
        watermark_setting = self.setting('security.watermark')
        self.assertFalse(watermark_setting.value['enabled'])
        self.assertEqual(watermark_setting.value['content_type'], 'username_ip')
        self.assertEqual(watermark_setting.value['layout'], 'tiled')
        login_setting = self.setting('security.login')
        self.assertEqual(login_setting.value['login_failure_limit'], 5)
        self.assertEqual(login_setting.value['login_lock_minutes'], 30)
        self.assertEqual(login_setting.value['ip_failure_limit'], 20)
        self.assertEqual(login_setting.value['ip_lock_minutes'], 30)
        self.assertEqual(login_setting.value['otp_failure_limit'], 5)
        self.assertEqual(login_setting.value['otp_lock_minutes'], 20)

    def test_login_can_skip_captcha_only_when_database_switch_is_disabled(self):
        """验证码关闭后登录不要求验证码，重新启用后必须提交验证码。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

        without_captcha = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json')
        self.assertEqual(without_captcha.status_code, 200, without_captcha.json())

        login_setting.value = {**login_setting.value, 'captcha_enabled': True}
        login_setting.save(update_fields=['value', 'updated_at'])
        captcha_required = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json')
        self.assertEqual(captcha_required.status_code, 400)
        self.assertEqual(captcha_required.json()['detail'], '请输入验证码')

    def test_password_failure_lock_uses_database_policy(self):
        """密码连续错误达到配置阈值时必须立即按配置时长锁定用户。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
            'login_failure_limit': 3,
            'login_lock_minutes': 7,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

        responses = [
            self.client.post('/api/v1/auth/login', {
                'username': self.user.username,
                'password': 'WrongPassword123!',
            }, format='json', REMOTE_ADDR='10.20.30.40')
            for _index in range(3)
        ]
        blocked_correct_password = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='10.20.30.40')

        self.assertEqual([response.status_code for response in responses], [401, 401, 429])
        self.assertIn('7 分钟', responses[-1].json()['detail'])
        self.assertEqual(blocked_correct_password.status_code, 429)

    def test_ip_failure_lock_uses_independent_database_policy(self):
        """同一来源 IP 跨账号失败达到独立阈值时必须按独立时长锁定。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
            'login_failure_limit': 10,
            'ip_failure_limit': 5,
            'ip_lock_minutes': 11,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

        responses = [
            self.client.post('/api/v1/auth/login', {
                'username': f'unknown-user-{index}',
                'password': 'WrongPassword123!',
            }, format='json', REMOTE_ADDR='10.30.40.50')
            for index in range(5)
        ]
        blocked_valid_user = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='10.30.40.50')

        self.assertEqual([response.status_code for response in responses], [401, 401, 401, 401, 429])
        self.assertIn('来源 IP', responses[-1].json()['detail'])
        self.assertIn('11 分钟', responses[-1].json()['detail'])
        self.assertEqual(blocked_valid_user.status_code, 429)

    def test_slider_captcha_is_required_and_verification_is_single_use(self):
        """拖拽验证启用后必须服务端校验，成功凭证只能由同一来源登录一次。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            'captcha_enabled': False,
            'slider_captcha_enabled': True,
            'otp_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

        missing = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='10.10.8.9')
        challenge = self.client.get('/api/v1/auth/slider-captcha', REMOTE_ADDR='10.10.8.9').json()
        too_fast = self.client.post('/api/v1/auth/slider-captcha', {
            'challenge_token': challenge['challenge_token'],
            'offset_x': challenge['target_x'],
            'elapsed_ms': 100,
        }, format='json', REMOTE_ADDR='10.10.8.9')
        challenge = self.client.get('/api/v1/auth/slider-captcha', REMOTE_ADDR='10.10.8.9').json()
        verified = self.client.post('/api/v1/auth/slider-captcha', {
            'challenge_token': challenge['challenge_token'],
            'offset_x': challenge['target_x'] + 3,
            'elapsed_ms': 850,
        }, format='json', REMOTE_ADDR='10.10.8.9')

        self.assertEqual(missing.status_code, 400)
        self.assertEqual(missing.json()['detail'], '请完成图形拖拽验证')
        self.assertEqual(too_fast.status_code, 400)
        self.assertEqual(verified.status_code, 200, verified.json())
        verification_token = verified.json()['verification_token']
        succeeded = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
            'slider_verification': verification_token,
        }, format='json', REMOTE_ADDR='10.10.8.9')
        replayed = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
            'slider_verification': verification_token,
        }, format='json', REMOTE_ADDR='10.10.8.9')

        self.assertEqual(succeeded.status_code, 200, succeeded.json())
        self.assertEqual(replayed.status_code, 400)
        self.assertEqual(replayed.json()['detail'], '图形拖拽验证失败或已过期')

    def test_login_whitelist_accepts_cidr_and_rejects_other_sources(self):
        """启用白名单时只允许命中 IP 或 CIDR 的来源调用登录接口。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        whitelist = self.setting('security.login_whitelist')
        whitelist.value = {'enabled': True, 'entries': ['10.20.0.0/16']}
        whitelist.save(update_fields=['value', 'updated_at'])

        denied = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='192.168.1.8')
        allowed = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='10.20.3.9')

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200, allowed.json())
        denied_log = AuditLog.objects.filter(actor=self.user.username, action='auth.login.failed').latest('id')
        self.assertEqual(denied_log.detail['reason'], '来源地址不在登录白名单')

    def test_password_policy_is_applied_to_user_api(self):
        """用户新增接口必须拒绝不符合当前数据库密码策略的密码。"""
        self.client.force_authenticate(self.admin)
        weak = self.client.post('/api/v1/users/', {
            'username': 'policy-user',
            'password': 'simplepass',
        }, format='json')
        strong = self.client.post('/api/v1/users/', {
            'username': 'policy-user',
            'password': 'ValidPassword123!',
        }, format='json')

        self.assertEqual(weak.status_code, 400)
        self.assertIn('密码必须包含大写字母', str(weak.json()))
        self.assertEqual(strong.status_code, 201, strong.json())

    def test_user_password_policy_endpoint_returns_database_rules(self):
        """用户管理页面读取的密码提示必须与数据库策略保持一致。"""
        policy = self.setting('security.password_policy')
        policy.value = {
            'min_length': 12,
            'require_uppercase': False,
            'require_lowercase': True,
            'require_number': True,
            'require_special': False,
            'exclude_username': True,
            'max_age_days': 45,
        }
        policy.save(update_fields=['value', 'updated_at'])
        self.client.force_authenticate(self.admin)

        response = self.client.get('/api/v1/users/password-policy/')

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json(), policy.value)

    def test_password_expired_login_disables_user_until_admin_unlock(self):
        """密码超过平台有效期时登录必须禁用用户，管理员启用后重新计算周期。"""
        organization = Organization.objects.create(
            name='密码过期测试组织',
            slug='password-expiry-org',
            org_type='company',
            is_default=True,
        )
        expired_at = timezone.now() - timedelta(days=31)
        UserProfile.objects.create(
            user=self.user,
            organization=organization,
            role='member',
            password_changed_at=expired_at,
        )
        login_setting = self.setting('security.login')
        login_setting.value = {
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        policy = self.setting('security.password_policy')
        policy.value = {**policy.value, 'max_age_days': 30}
        policy.save(update_fields=['value', 'updated_at'])

        denied = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json')
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(denied.status_code, 403, denied.json())
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.profile.password_expired_locked)
        self.assertTrue(AuditLog.objects.filter(action='User.password_expired_disable', resource=self.user.username).exists())

        self.client.force_authenticate(self.admin)
        unlocked = self.client.patch(f'/api/v1/users/{self.user.id}/', {
            'username': self.user.username,
            'is_active': True,
        }, format='json')
        self.user.refresh_from_db()
        self.user.profile.refresh_from_db()

        self.assertEqual(unlocked.status_code, 200, unlocked.json())
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.user.profile.password_expired_locked)
        self.assertGreater(self.user.profile.password_changed_at, expired_at)

    def relax_login_challenges(self):
        """关闭测试用例中的验证码约束，便于直接校验密码登录结果。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

    def set_password_max_age_days(self, days):
        """写入平台密码修改周期配置，返回生效后的设置对象。"""
        policy = self.setting('security.password_policy')
        policy.value = {**policy.value, 'max_age_days': days}
        policy.save(update_fields=['value', 'updated_at'])
        return policy

    def create_profile(self, user, slug, password_changed_at, role='member', password_expired_locked=False):
        """为测试用户建立所属部门并写入密码周期起点。"""
        organization = Organization.objects.create(
            name=f'{slug}组织',
            slug=slug,
            org_type='company',
            is_default=True,
        )
        return UserProfile.objects.create(
            user=user,
            organization=organization,
            role=role,
            password_changed_at=password_changed_at,
            password_expired_locked=password_expired_locked,
        )

    def test_system_admin_is_exempt_from_password_expiry_policy(self):
        """密码修改周期策略只约束普通用户，admin 长期未修改密码仍可登录。"""
        self.create_profile(
            self.admin,
            'system-admin-exempt-org',
            timezone.now() - timedelta(days=365),
            role='admin',
        )
        self.relax_login_challenges()
        self.set_password_max_age_days(30)

        allowed = self.client.post('/api/v1/auth/login', {
            'username': self.admin.username,
            'password': 'StrongPassword123!',
        }, format='json')
        self.admin.refresh_from_db()
        self.admin.profile.refresh_from_db()

        self.assertEqual(allowed.status_code, 200, allowed.json())
        self.assertTrue(self.admin.is_active)
        self.assertFalse(self.admin.profile.password_expired_locked)
        self.assertFalse(AuditLog.objects.filter(action='User.password_expired_disable').exists())

    def test_stuck_system_admin_expiry_lock_is_repaired_on_login(self):
        """历史版本误锁 admin 时，登录必须自动解除锁定并记录审计日志。"""
        self.create_profile(
            self.admin,
            'system-admin-repair-org',
            timezone.now() - timedelta(days=365),
            role='admin',
            password_expired_locked=True,
        )
        User.objects.filter(pk=self.admin.pk).update(is_active=False)
        self.relax_login_challenges()
        self.set_password_max_age_days(30)

        allowed = self.client.post('/api/v1/auth/login', {
            'username': self.admin.username,
            'password': 'StrongPassword123!',
        }, format='json')
        self.admin.refresh_from_db()
        self.admin.profile.refresh_from_db()

        self.assertEqual(allowed.status_code, 200, allowed.json())
        self.assertTrue(self.admin.is_active)
        self.assertFalse(self.admin.profile.password_expired_locked)
        self.assertTrue(
            AuditLog.objects.filter(
                action='User.password_expired_lock_restored',
                resource=self.admin.username,
            ).exists()
        )

    def test_stuck_system_admin_expiry_lock_keeps_rejecting_wrong_password(self):
        """自动解除 admin 过期锁定时不得放过错误口令，并必须记录登录失败。"""
        self.create_profile(
            self.admin,
            'system-admin-wrong-password-org',
            timezone.now() - timedelta(days=365),
            role='admin',
            password_expired_locked=True,
        )
        self.relax_login_challenges()
        self.set_password_max_age_days(30)

        denied = self.client.post('/api/v1/auth/login', {
            'username': self.admin.username,
            'password': 'WrongPassword123!',
        }, format='json')
        self.admin.profile.refresh_from_db()

        self.assertEqual(denied.status_code, 401, denied.json())
        self.assertFalse(self.admin.profile.password_expired_locked)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin.username,
                action='auth.login.failed',
            ).exists()
        )

    def test_login_blacklist_takes_precedence_over_whitelist(self):
        """来源同时命中黑白名单时必须由黑名单优先拒绝并记录用户日志。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        whitelist = self.setting('security.login_whitelist')
        whitelist.value = {'enabled': True, 'entries': ['10.20.0.0/16']}
        whitelist.save(update_fields=['value', 'updated_at'])
        blacklist = self.setting('security.login_blacklist')
        blacklist.value = {'enabled': True, 'entries': ['10.20.3.9']}
        blacklist.save(update_fields=['value', 'updated_at'])

        denied = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='10.20.3.9')
        allowed, reason = login_ip_access_result('10.20.8.7')

        self.assertEqual(denied.status_code, 403)
        self.assertTrue(allowed)
        self.assertEqual(reason, '')
        denied_log = AuditLog.objects.filter(actor=self.user.username, action='auth.login.failed').latest('id')
        self.assertEqual(denied_log.detail['reason'], '来源地址在登录黑名单中')

    def test_vite_proxy_real_ip_is_used_by_login_blacklist_and_audit(self):
        """经本机 Vite 代理登录时必须按真实浏览器 IP 拒绝并记录审计。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        blacklist = self.setting('security.login_blacklist')
        blacklist.value = {'enabled': True, 'entries': ['192.168.3.167']}
        blacklist.save(update_fields=['value', 'updated_at'])

        denied = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='::ffff:192.168.3.167')

        self.assertEqual(denied.status_code, 403)
        denied_log = AuditLog.objects.filter(actor=self.user.username, action='auth.login.failed').latest('id')
        self.assertEqual(denied_log.ip_address, '192.168.3.167')
        self.assertEqual(denied_log.detail['reason'], '来源地址在登录黑名单中')

    def test_direct_backend_request_cannot_spoof_blacklisted_forwarded_ip(self):
        """非可信来源直接请求后端时必须忽略其伪造的转发地址。"""
        login_setting = self.setting('security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        blacklist = self.setting('security.login_blacklist')
        blacklist.value = {'enabled': True, 'entries': ['10.10.10.10']}
        blacklist.save(update_fields=['value', 'updated_at'])

        allowed = self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
        }, format='json', REMOTE_ADDR='192.168.3.167', HTTP_X_FORWARDED_FOR='10.10.10.10')

        self.assertEqual(allowed.status_code, 200, allowed.json())
        login_log = AuditLog.objects.filter(actor=self.user.username, action='auth.login.success').latest('id')
        self.assertEqual(login_log.ip_address, '192.168.3.167')

    def test_blacklist_rejects_existing_access_and_refresh_tokens(self):
        """名单更新后命中来源的现有访问令牌和刷新令牌必须立即失效。"""
        from ops.services.tokens import issue_pair

        tokens = issue_pair(self.user)
        blacklist = self.setting('security.login_blacklist')
        blacklist.value = {'enabled': True, 'entries': ['192.168.3.167']}
        blacklist.save(update_fields=['value', 'updated_at'])
        access_client = APIClient()
        access_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        access_response = access_client.get(
            '/api/v1/me',
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='192.168.3.167',
        )
        refresh_response = self.client.post('/api/v1/auth/refresh', {
            'refresh': tokens['refresh'],
        }, format='json', REMOTE_ADDR='127.0.0.1', HTTP_X_FORWARDED_FOR='192.168.3.167')

        self.assertEqual(access_response.status_code, 401)
        self.assertIn('来源地址在登录黑名单中', access_response.json()['detail'])
        self.assertEqual(refresh_response.status_code, 403)
        self.assertIn('来源地址在登录黑名单中', refresh_response.json()['detail'])

    def test_login_blacklist_cidr_rejects_member_address(self):
        """黑名单 CIDR 必须拒绝网段内地址，同时不得误伤网段外地址。"""
        blacklist = self.setting('security.login_blacklist')
        blacklist.value = {'enabled': True, 'entries': ['192.168.2.0/24']}
        blacklist.save(update_fields=['value', 'updated_at'])

        denied, denied_reason = login_ip_access_result('192.168.2.4')
        allowed, allowed_reason = login_ip_access_result('192.168.3.4')

        self.assertFalse(denied)
        self.assertEqual(denied_reason, '来源地址在登录黑名单中')
        self.assertTrue(allowed)
        self.assertEqual(allowed_reason, '')

    def test_access_list_descriptions_and_strict_cidr_validation(self):
        """访问名单应拒绝带主机位的 CIDR，并保存合法地址的用途说明。"""
        self.client.force_authenticate(self.admin)
        blacklist = self.setting('security.login_blacklist')

        invalid = self.client.patch(f'/api/v1/settings/{blacklist.id}/', {
            'value': {
                'enabled': True,
                'entries': ['192.168.10.8/24'],
                'descriptions': {'192.168.10.8/24': '错误网段写法'},
            },
        }, format='json')
        response = self.client.patch(f'/api/v1/settings/{blacklist.id}/', {
            'value': {
                'enabled': True,
                'entries': ['192.168.10.0/24', '192.168.0.0/16', '192.168.20.8/32', '203.0.113.9'],
                'descriptions': {
                    '192.168.10.0/24': ' 办公网出口 ',
                    '192.168.0.0/16': '总部内网',
                    '192.168.20.8/32': '单台运维机',
                    '203.0.113.9': '异常来源地址',
                    '198.51.100.1': '不在名单中的孤立说明',
                },
            },
        }, format='json')

        self.assertEqual(invalid.status_code, 400, invalid.json())
        self.assertIn('CIDR 必须使用网段起始地址', str(invalid.json()))
        self.assertEqual(response.status_code, 200, response.json())
        blacklist.refresh_from_db()
        self.assertEqual(blacklist.value['entries'], [
            '192.168.10.0/24',
            '192.168.0.0/16',
            '192.168.20.8',
            '203.0.113.9',
        ])
        self.assertEqual(blacklist.value['descriptions'], {
            '192.168.10.0/24': '办公网出口',
            '192.168.0.0/16': '总部内网',
            '192.168.20.8': '单台运维机',
            '203.0.113.9': '异常来源地址',
        })

    def test_setting_validation_rejects_empty_enabled_access_lists_and_accepts_otp(self):
        """设置接口允许启用拖拽验证和 OTP，但不得保存空访问名单。"""
        self.client.force_authenticate(self.admin)
        whitelist = self.setting('security.login_whitelist')
        blacklist = self.setting('security.login_blacklist')
        login_setting = self.setting('security.login')

        invalid_whitelist = self.client.patch(f'/api/v1/settings/{whitelist.id}/', {
            'value': {'enabled': True, 'entries': []},
        }, format='json')
        valid_otp = self.client.patch(f'/api/v1/settings/{login_setting.id}/', {
            'value': {'captcha_enabled': True, 'slider_captcha_enabled': True, 'otp_enabled': True},
        }, format='json')
        valid_slider = self.client.patch(f'/api/v1/settings/{login_setting.id}/', {
            'value': {
                'captcha_enabled': False,
                'slider_captcha_enabled': True,
                'otp_enabled': False,
                'login_failure_limit': 6,
                'login_lock_minutes': 45,
                'ip_failure_limit': 25,
                'ip_lock_minutes': 35,
                'otp_failure_limit': 4,
                'otp_lock_minutes': 25,
            },
        }, format='json')
        invalid_lock_policy = self.client.patch(f'/api/v1/settings/{login_setting.id}/', {
            'value': {
                'captcha_enabled': False,
                'slider_captcha_enabled': True,
                'otp_enabled': False,
                'login_failure_limit': 2,
            },
        }, format='json')
        invalid_blacklist = self.client.patch(f'/api/v1/settings/{blacklist.id}/', {
            'value': {'enabled': True, 'entries': []},
        }, format='json')
        invalid_legacy_whitelist = self.client.put('/api/v1/system-settings/security/login_whitelist/', {
            'value': {'enabled': True, 'entries': []},
        }, format='json')

        self.assertEqual(invalid_whitelist.status_code, 400)
        self.assertEqual(invalid_blacklist.status_code, 400)
        self.assertEqual(valid_otp.status_code, 200, valid_otp.json())
        self.assertEqual(valid_slider.status_code, 200, valid_slider.json())
        self.assertEqual(invalid_lock_policy.status_code, 400)
        login_setting.refresh_from_db()
        self.assertTrue(login_setting.value['slider_captcha_enabled'])
        self.assertFalse(login_setting.value['otp_enabled'])
        self.assertEqual(login_setting.value['login_failure_limit'], 6)
        self.assertEqual(login_setting.value['login_lock_minutes'], 45)
        self.assertEqual(login_setting.value['ip_failure_limit'], 25)
        self.assertEqual(login_setting.value['ip_lock_minutes'], 35)
        self.assertEqual(login_setting.value['otp_failure_limit'], 4)
        self.assertEqual(login_setting.value['otp_lock_minutes'], 25)
        self.assertEqual(invalid_legacy_whitelist.status_code, 400)

    def test_platform_public_settings_only_expose_non_sensitive_login_options(self):
        """公开设置返回登录页品牌、备案和验证开关，但不泄露访问名单。"""
        response = self.client.get('/api/v1/public/platform')

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()['captcha_enabled'])
        self.assertTrue(response.json()['slider_captcha_enabled'])
        self.assertFalse(response.json()['otp_enabled'])
        self.assertEqual(response.json()['timezone'], 'Asia/Shanghai')
        self.assertFalse(response.json()['watermark']['enabled'])
        self.assertEqual(response.json()['watermark']['content_type'], 'username_ip')
        self.assertEqual(response.json()['client_ip'], '127.0.0.1')
        self.assertEqual(response.json()['icp_record'], '冀ICP备2026010543号-3')
        self.assertEqual(response.json()['public_security_record'], '冀公网安备13310102000221号')
        self.assertNotIn('entries', response.json())

    def test_watermark_setting_validates_style_and_is_publicly_effective(self):
        """水印设置应校验视觉边界，并通过公开平台接口提供给工作台。"""
        self.client.force_authenticate(self.admin)
        setting = self.setting('security.watermark')
        valid_value = {
            'enabled': True,
            'content_type': 'custom',
            'custom_text': '内部资料 · 严禁外传',
            'layout': 'tiled',
            'show_time': True,
            'font_size': 16,
            'font_weight': 600,
            'color': '#2563eb',
            'opacity': 0.18,
            'rotate': -20,
            'horizontal_gap': 240,
            'vertical_gap': 150,
        }
        valid = self.client.patch(
            f'/api/v1/settings/{setting.id}/',
            {'value': valid_value},
            format='json',
        )
        invalid = self.client.patch(
            f'/api/v1/settings/{setting.id}/',
            {'value': {**valid_value, 'opacity': 0.9}},
            format='json',
        )

        self.assertEqual(valid.status_code, 200, valid.json())
        self.assertEqual(invalid.status_code, 400)
        public = self.client.get('/api/v1/public/platform')
        self.assertTrue(public.json()['watermark']['enabled'])
        self.assertEqual(public.json()['watermark']['custom_text'], '内部资料 · 严禁外传')
        self.assertEqual(public.json()['watermark']['opacity'], 0.18)

    def test_platform_logo_upload_returns_local_path_and_writes_audit(self):
        """平台 Logo 上传接口只保存本地图片路径，并记录不含文件内容的系统日志。"""
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.client.force_authenticate(self.admin)
        logo = SimpleUploadedFile(
            'logo.png',
            b'\x89PNG\r\n\x1a\n' + b'0' * 32,
            content_type='image/png',
        )

        with self.settings(MEDIA_ROOT=temp_dir):
            response = self.client.post(
                '/api/v1/system-settings/platform/logo-upload/',
                {'file': logo},
                format='multipart',
            )

        self.assertEqual(response.status_code, 200, response.json())
        logo_url = response.json()['logo_url']
        self.assertTrue(logo_url.startswith('/uploads/platform/logo/'))
        self.assertTrue(os.path.exists(os.path.join(temp_dir, logo_url.removeprefix('/uploads/'))))
        log = AuditLog.objects.filter(action='SystemSetting.logo_upload').latest('id')
        self.assertEqual(log.resource, '平台 Logo')
        self.assertEqual(log.detail['logo_url'], logo_url)
        self.assertNotIn('PNG', str(log.detail))

    def test_platform_logo_upload_rejects_non_image_file(self):
        """平台 Logo 上传接口必须拒绝非图片文件。"""
        temp_dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, temp_dir, ignore_errors=True)
        self.client.force_authenticate(self.admin)
        text_file = SimpleUploadedFile('logo.txt', b'not image', content_type='text/plain')

        with self.settings(MEDIA_ROOT=temp_dir):
            response = self.client.post(
                '/api/v1/system-settings/platform/logo-upload/',
                {'file': text_file},
                format='multipart',
            )

        self.assertEqual(response.status_code, 400)
        self.assertIn('只支持', response.json()['detail'])

    def test_password_validator_uses_updated_database_policy(self):
        """密码校验服务必须立即使用管理员保存的新长度规则。"""
        policy = self.setting('security.password_policy')
        policy.value = {**policy.value, 'min_length': 20}
        policy.save(update_fields=['value', 'updated_at'])

        with self.assertRaisesMessage(ValueError, '密码长度不能少于 20 位'):
            validate_password('ValidPassword123!', 'another-user')
