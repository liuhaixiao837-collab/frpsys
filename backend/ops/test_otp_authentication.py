import time
from datetime import timedelta
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ops.models import (
    AuditLog, Organization, PermissionPolicy, PermissionRule, SystemSetting, UserProfile,
)
from ops.permission_catalog import required_codes_for_page
from ops.permission_service import clear_permission_cache
from ops.serializers import UserSerializer
from ops.services.otp import totp_code
from ops.test_license_support import verified_license_metadata


class OtpAuthenticationTests(TestCase):
    """验证 OTP 两阶段登录、密文落库和防重放规则。"""

    def setUp(self):
        """创建启用 OTP 的最小平台、组织和人工用户。"""
        self.client = APIClient()
        self.organization = Organization.objects.create(
            name='OTP 测试部门',
            slug='otp-test-department',
            org_type='department',
        )
        self.user = User.objects.create_user(
            username='otp-user',
            email='otp@example.com',
            password='StrongPassword123!',
        )
        UserProfile.objects.create(
            user=self.user,
            organization=self.organization,
            role='member',
            otp_policy='inherit',
        )
        setting = SystemSetting.objects.get(key='security.login')
        setting.value = {
            **setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': True,
        }
        setting.save(update_fields=['value', 'updated_at'])
        license_setting = SystemSetting.objects.get(key='license.management')
        license_setting.value = verified_license_metadata()
        license_setting.save(update_fields=['value', 'updated_at'])
        self.client_nonce = 'otp-browser-session-nonce-0001'

    def begin_login(self):
        """提交正确密码并返回未签发 JWT 的 OTP 预认证响应。"""
        return self.client.post('/api/v1/auth/login', {
            'username': self.user.username,
            'password': 'StrongPassword123!',
            'client_nonce': self.client_nonce,
        }, format='json')

    def bind_otp(self):
        """通过标准 otpauth 内容完成绑定并返回首次响应。"""
        begin = self.begin_login()
        self.assertEqual(begin.status_code, 200, begin.json())
        self.assertEqual(begin.json()['next_step'], 'otp_bind')
        self.assertNotIn('access', begin.json())
        token = begin.json()['preauth_token']
        setup = self.client.post('/api/v1/auth/otp/setup', {
            'preauth_token': token,
            'client_nonce': self.client_nonce,
        }, format='json')
        self.assertEqual(setup.status_code, 200, setup.json())
        uri = setup.json()['otpauth_uri']
        self.assertTrue(uri.startswith('otpauth://totp/'))
        secret = parse_qs(urlsplit(uri).query)['secret'][0]
        timestep = int(time.time() // 30)
        confirm = self.client.post('/api/v1/auth/otp/confirm', {
            'preauth_token': token,
            'client_nonce': self.client_nonce,
            'code': totp_code(secret, timestep),
        }, format='json')
        self.assertEqual(confirm.status_code, 200, confirm.json())
        return confirm, secret, timestep

    def test_binding_encrypts_seed_and_never_serializes_sensitive_values(self):
        """OTP 种子必须以 SM4 密文落库，并且用户接口不返回敏感绑定数据。"""
        confirm, secret, _timestep = self.bind_otp()

        self.assertEqual(
            set(confirm.json()),
            {'access', 'refresh', 'token_type', 'expires_in', 'next_step', 'user'},
        )
        self.assertNotIn(secret, str(UserSerializer(self.user).data))
        self.assertNotIn('otp_secret', UserSerializer(self.user).data)
        with connection.cursor() as cursor:
            cursor.execute('SELECT otp_secret FROM ops_userprofile WHERE user_id = %s', [self.user.id])
            raw_secret = cursor.fetchone()[0]
        self.assertTrue(raw_secret.startswith('sm4:v1:'))
        self.assertNotEqual(raw_secret, secret)
        self.assertTrue(AuditLog.objects.filter(action='User.otp_bind', resource=self.user.username).exists())

    def test_totp_login_rejects_same_successful_timestep_replay(self):
        """同一时间步口令首次登录成功后，新事务中重放必须被拒绝。"""
        _confirm, secret, bound_timestep = self.bind_otp()
        verification_time = (bound_timestep + 1) * 30 + 1
        credential = totp_code(secret, bound_timestep + 1)

        with patch('ops.services.otp.time.time', return_value=verification_time):
            begin = self.begin_login().json()
            verified = self.client.post('/api/v1/auth/otp/verify', {
                'preauth_token': begin['preauth_token'],
                'client_nonce': self.client_nonce,
                'credential': credential,
            }, format='json')
            replay_begin = self.begin_login().json()
            replayed = self.client.post('/api/v1/auth/otp/verify', {
                'preauth_token': replay_begin['preauth_token'],
                'client_nonce': self.client_nonce,
                'credential': credential,
            }, format='json')

        self.assertEqual(verified.status_code, 200, verified.json())
        self.assertIn('access', verified.json())
        self.assertEqual(replayed.status_code, 400, replayed.json())
        self.assertEqual(replayed.json()['detail'], '动态口令错误或已过期')

    def test_totp_login_token_can_restore_current_user(self):
        """普通用户完成 OTP 后必须能用正式令牌读取自身身份并恢复前端登录状态。"""
        _confirm, secret, bound_timestep = self.bind_otp()
        verification_time = (bound_timestep + 1) * 30 + 1
        with patch('ops.services.otp.time.time', return_value=verification_time):
            begin = self.begin_login().json()
            verified = self.client.post('/api/v1/auth/otp/verify', {
                'preauth_token': begin['preauth_token'],
                'client_nonce': self.client_nonce,
                'credential': totp_code(secret, bound_timestep + 1),
            }, format='json')

        self.assertEqual(verified.status_code, 200, verified.json())
        authenticated_client = APIClient()
        authenticated_client.credentials(HTTP_AUTHORIZATION=f"Bearer {verified.json()['access']}")
        current_user = authenticated_client.get('/api/v1/me')

        self.assertEqual(current_user.status_code, 200, current_user.json())
        self.assertEqual(current_user.json()['username'], self.user.username)

    def test_non_six_digit_credential_is_rejected(self):
        """已绑定用户只能提交六位数字动态口令。"""
        self.bind_otp()
        begin = self.begin_login().json()
        rejected = self.client.post('/api/v1/auth/otp/verify', {
            'preauth_token': begin['preauth_token'],
            'client_nonce': self.client_nonce,
            'credential': 'ABCD-EFGH-JKLM',
        }, format='json')

        self.assertEqual(rejected.status_code, 400, rejected.json())
        self.assertEqual(rejected.json()['detail'], '动态口令错误或已过期')

    def test_otp_failure_lock_uses_database_policy(self):
        """OTP 连续错误达到平台阈值时必须持久化配置时长的用户锁定。"""
        _confirm, secret, _timestep = self.bind_otp()
        setting = SystemSetting.objects.get(key='security.login')
        setting.value = {
            **setting.value,
            'otp_failure_limit': 3,
            'otp_lock_minutes': 20,
        }
        setting.save(update_fields=['value', 'updated_at'])
        current_timestep = int(time.time() // 30)
        valid_codes = {
            totp_code(secret, current_timestep + offset)
            for offset in (-1, 0, 1)
        }
        invalid_code = next(code for code in ('000000', '111111', '222222', '333333') if code not in valid_codes)
        begin = self.begin_login().json()

        responses = [
            self.client.post('/api/v1/auth/otp/verify', {
                'preauth_token': begin['preauth_token'],
                'client_nonce': self.client_nonce,
                'credential': invalid_code,
            }, format='json')
            for _index in range(3)
        ]
        blocked_login = self.begin_login()

        self.user.profile.refresh_from_db()
        self.assertEqual([response.status_code for response in responses], [400, 400, 429])
        self.assertIn('20 分钟', responses[-1].json()['detail'])
        self.assertGreater(self.user.profile.otp_locked_until, timezone.now() + timedelta(minutes=19))
        self.assertEqual(blocked_login.status_code, 429)

    def test_user_policy_overrides_platform_default(self):
        """强制启用和免于认证两种用户策略必须分别覆盖平台关闭和开启状态。"""
        setting = SystemSetting.objects.get(key='security.login')
        setting.value = {**setting.value, 'otp_enabled': False}
        setting.save(update_fields=['value', 'updated_at'])
        self.user.profile.otp_policy = 'required'
        self.user.profile.save(update_fields=['otp_policy', 'updated_at'])

        required = self.begin_login()

        setting.value = {**setting.value, 'otp_enabled': True}
        setting.save(update_fields=['value', 'updated_at'])
        self.user.profile.otp_policy = 'exempt'
        self.user.profile.save(update_fields=['otp_policy', 'updated_at'])
        exempt = self.begin_login()

        self.assertEqual(required.json()['next_step'], 'otp_bind')
        self.assertEqual(exempt.json()['next_step'], 'complete')
        self.assertIn('access', exempt.json())

    def test_admin_reset_clears_binding_revokes_tokens_and_writes_system_log(self):
        """管理员重置 OTP 必须清空绑定、记录系统日志并使旧令牌失效。"""
        confirm, _secret, _timestep = self.bind_otp()
        old_access = confirm.json()['access']
        admin = User.objects.create_superuser(
            username='admin',
            email='otp-admin@example.com',
            password='StrongPassword123!',
        )
        UserProfile.objects.create(user=admin, organization=self.organization, role='admin')
        admin_client = APIClient()
        admin_client.force_authenticate(admin)

        reset = admin_client.post(f'/api/v1/users/{self.user.id}/reset-otp/', {}, format='json')

        self.assertEqual(reset.status_code, 200, reset.json())
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.otp_secret, '')
        self.assertEqual(self.user.profile.auth_version, 1)
        self.assertTrue(AuditLog.objects.filter(action='User.otp_reset', resource=self.user.username).exists())
        old_session = APIClient()
        old_session.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertEqual(old_session.get('/api/v1/me').status_code, 401)

    def test_public_settings_only_expose_otp_switch(self):
        """公开设置只允许返回 OTP 布尔开关，不返回任何用户绑定数据。"""
        response = self.client.get('/api/v1/public/platform')

        self.assertEqual(response.status_code, 200)
        self.assertIs(response.json()['otp_enabled'], True)
        self.assertNotIn('otp_secret', str(response.json()))

    def test_reset_otp_requires_independent_database_action_permission(self):
        """普通管理用户只有页面查看权限时不得重置 OTP，补充独立操作权限后才允许。"""
        operator = User.objects.create_user(username='otp-operator', password='StrongPassword123!')
        UserProfile.objects.create(user=operator, organization=self.organization, role='member')
        policy = PermissionPolicy.objects.create(
            name='OTP 重置权限测试',
            subject_type='user',
            user=operator,
            organization=self.organization,
        )
        PermissionRule.objects.bulk_create([
            PermissionRule(policy=policy, permission_code=code, effect='allow')
            for code in required_codes_for_page('page.admin_users.view')
        ])
        operator_client = APIClient()
        operator_client.force_authenticate(operator)
        clear_permission_cache()

        denied = operator_client.post(f'/api/v1/users/{self.user.id}/reset-otp/', {}, format='json')
        PermissionRule.objects.create(
            policy=policy,
            permission_code='page.admin_users.reset_otp',
            effect='allow',
        )
        clear_permission_cache()
        allowed = operator_client.post(f'/api/v1/users/{self.user.id}/reset-otp/', {}, format='json')

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200, allowed.json())
