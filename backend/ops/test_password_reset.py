import time
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ops.models import AuditLog, Organization, SystemSetting, UserProfile
from ops.services.otp import generate_totp_secret, totp_code
from ops.services.security import login_blocked, record_login_failure
from ops.services.tokens import issue_pair


class PasswordResetTests(TestCase):
    """验证基于 TOTP 的公开找回密码流程及关键安全边界。"""

    def setUp(self):
        """创建关闭交互验证码、已绑定 TOTP 的最小测试用户。"""
        cache.clear()
        self.client = APIClient()
        self.organization = Organization.objects.create(
            name='密码找回测试部门',
            slug='password-reset-department',
            org_type='department',
        )
        self.user = User.objects.create_user(
            username='reset-user',
            email='reset@example.com',
            password='OldPassword123!',
        )
        self.secret = generate_totp_secret()
        self.profile = UserProfile.objects.create(
            user=self.user,
            organization=self.organization,
            role='member',
            otp_secret=self.secret,
            otp_bound_at=timezone.now(),
        )
        setting = SystemSetting.objects.get(key='security.login')
        setting.value = {
            **setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_failure_limit': 5,
            'otp_lock_minutes': 20,
        }
        setting.save(update_fields=['value', 'updated_at'])
        self.client_nonce = 'password-reset-browser-nonce-0001'

    def start_reset(self, username=None, nonce=None, client=None, ip_address='127.0.0.1'):
        """开始一条找回事务并返回接口响应。

        参数：可覆盖用户名、浏览器随机值、测试客户端和来源地址。
        返回：找回开始接口的 DRF 测试响应。
        副作用：向测试缓存写入短期找回事务。
        """
        return (client or self.client).post('/api/v1/auth/password-reset/start', {
            'username': self.user.username if username is None else username,
            'client_nonce': self.client_nonce if nonce is None else nonce,
        }, format='json', REMOTE_ADDR=ip_address)

    def verify_reset_otp(self, reset_token, timestep, credential=None, nonce=None, ip_address='127.0.0.1'):
        """在固定时间步提交找回流程的 TOTP。

        参数：`reset_token` 为第一步令牌；`timestep` 为固定时间步；其余参数可覆盖输入条件。
        返回：OTP 验证接口的测试响应。
        副作用：成功时消费 TOTP 时间步并签发改密事务。
        """
        code = credential if credential is not None else totp_code(self.secret, timestep)
        with patch('ops.services.otp.time.time', return_value=timestep * 30 + 1):
            return self.client.post('/api/v1/auth/password-reset/verify-otp', {
                'reset_token': reset_token,
                'client_nonce': self.client_nonce if nonce is None else nonce,
                'credential': code,
            }, format='json', REMOTE_ADDR=ip_address)

    def complete_reset(self, password_token, password='NewPassword456!', nonce=None, ip_address='127.0.0.1'):
        """提交两次一致的新密码并返回完成接口响应。

        参数：`password_token` 为 OTP 步骤签发的改密资格；其余参数可覆盖密码和绑定条件。
        返回：密码重置完成接口的测试响应。
        副作用：成功时保存新密码并撤销旧认证版本。
        """
        return self.client.post('/api/v1/auth/password-reset/complete', {
            'password_token': password_token,
            'client_nonce': self.client_nonce if nonce is None else nonce,
            'new_password': password,
            'confirm_password': password,
        }, format='json', REMOTE_ADDR=ip_address)

    def verified_password_token(self, timestep=None):
        """完成前两步并返回可用于测试的改密资格。

        参数：`timestep` 为可选固定时间步。
        返回：OTP 验证成功响应中的一次性改密令牌。
        副作用：创建并消费一条测试找回事务及 TOTP 时间步。
        """
        current_timestep = timestep or int(time.time() // 30)
        started = self.start_reset()
        self.assertEqual(started.status_code, 200, started.json())
        verified = self.verify_reset_otp(started.json()['reset_token'], current_timestep)
        self.assertEqual(verified.status_code, 200, verified.json())
        return verified.json()['password_token']

    def test_success_resets_password_revokes_sessions_and_writes_safe_audit(self):
        """正常找回应更新密码、认证版本和周期，且审计不得含敏感输入。"""
        old_access = issue_pair(self.user)['access']
        timestep = int(time.time() // 30)
        started = self.start_reset()
        reset_token = started.json()['reset_token']
        otp_code = totp_code(self.secret, timestep)
        verified = self.verify_reset_otp(reset_token, timestep, credential=otp_code)
        password_token = verified.json()['password_token']
        completed = self.complete_reset(password_token)

        self.assertEqual(completed.status_code, 200, completed.json())
        self.assertNotIn('access', completed.json())
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.user.check_password('NewPassword456!'))
        self.assertEqual(self.profile.auth_version, 1)
        self.assertFalse(self.profile.password_expired_locked)

        authenticated = APIClient()
        authenticated.credentials(HTTP_AUTHORIZATION=f'Bearer {old_access}')
        self.assertNotEqual(authenticated.get('/api/v1/me').status_code, 200)
        audit_dump = str(list(AuditLog.objects.filter(action__startswith='User.password_reset').values()))
        for sensitive_value in ('NewPassword456!', otp_code, reset_token, password_token):
            self.assertNotIn(sensitive_value, audit_dump)

    def test_start_response_does_not_reveal_account_or_otp_binding(self):
        """存在、未绑定与不存在账号必须得到一致的开始响应结构和说明。"""
        unbound = User.objects.create_user(username='unbound-user', password='OldPassword123!')
        UserProfile.objects.create(user=unbound, organization=self.organization, role='member')

        existing = self.start_reset()
        missing = self.start_reset(username='missing-user')
        unbound_response = self.start_reset(username=unbound.username)

        self.assertEqual(existing.status_code, missing.status_code, unbound_response.status_code)
        self.assertEqual(set(existing.json()), set(missing.json()))
        self.assertEqual(existing.json()['detail'], missing.json()['detail'])
        self.assertEqual(existing.json()['detail'], unbound_response.json()['detail'])

    def test_non_six_digit_credential_is_rejected_and_totp_replay_is_blocked(self):
        """找回流程只接受六位动态口令，同一 TOTP 时间步不得再次使用。"""
        invalid_token = self.start_reset().json()['reset_token']
        rejected = self.verify_reset_otp(
            invalid_token,
            int(time.time() // 30),
            credential='ABCD-EFGH-JKLM',
        )
        self.assertEqual(rejected.status_code, 400, rejected.json())

        timestep = int(time.time() // 30) + 1
        first_token = self.start_reset().json()['reset_token']
        first = self.verify_reset_otp(first_token, timestep)
        self.assertEqual(first.status_code, 200, first.json())
        replay_token = self.start_reset().json()['reset_token']
        replay = self.verify_reset_otp(replay_token, timestep)
        self.assertEqual(replay.status_code, 400, replay.json())

    def test_transactions_are_bound_to_browser_ip_and_are_one_time(self):
        """事务跨浏览器随机值、跨 IP 或重复提交时必须失效。"""
        timestep = int(time.time() // 30)
        reset_token = self.start_reset().json()['reset_token']
        wrong_nonce = self.verify_reset_otp(reset_token, timestep, nonce='another-browser-nonce-0002')
        wrong_ip = self.verify_reset_otp(reset_token, timestep, ip_address='10.20.30.40')
        self.assertEqual(wrong_nonce.status_code, 401, wrong_nonce.json())
        self.assertEqual(wrong_ip.status_code, 401, wrong_ip.json())

        password_token = self.verified_password_token(timestep + 1)
        completed = self.complete_reset(password_token)
        repeated = self.complete_reset(password_token, password='AnotherPassword789!')
        self.assertEqual(completed.status_code, 200, completed.json())
        self.assertEqual(repeated.status_code, 401, repeated.json())

    def test_manual_disable_cannot_reset_but_expiry_disable_can_recover(self):
        """管理员禁用账号不得自助恢复，密码过期自动禁用账号可以恢复。"""
        self.user.is_active = False
        self.user.save(update_fields=['is_active'])
        manual_token = self.start_reset().json()['reset_token']
        manual = self.verify_reset_otp(manual_token, int(time.time() // 30))
        self.assertEqual(manual.status_code, 400, manual.json())

        self.profile.password_expired_locked = True
        self.profile.password_changed_at = timezone.now() - timedelta(days=90)
        self.profile.save(update_fields=['password_expired_locked', 'password_changed_at', 'updated_at'])
        timestep = int(time.time() // 30) + 1
        password_token = self.verified_password_token(timestep)
        completed = self.complete_reset(password_token)
        self.assertEqual(completed.status_code, 200, completed.json())
        self.user.refresh_from_db()
        self.profile.refresh_from_db()
        self.assertTrue(self.user.is_active)
        self.assertFalse(self.profile.password_expired_locked)

    def test_password_policy_failure_keeps_qualification_for_retry(self):
        """密码策略失败不得消费改密资格，用户可在同一事务修正后重试。"""
        password_token = self.verified_password_token()
        rejected = self.complete_reset(password_token, password='weak')
        accepted = self.complete_reset(password_token)
        self.assertEqual(rejected.status_code, 400, rejected.json())
        self.assertEqual(accepted.status_code, 200, accepted.json())

    def test_success_clears_user_password_lock_without_clearing_ip_lock(self):
        """找回成功只解除账号密码锁定，必须保留来源 IP 防暴力锁定。"""
        password_token = self.verified_password_token()
        for _index in range(20):
            record_login_failure('127.0.0.1', self.user.username)
        self.assertEqual(login_blocked('127.0.0.1', self.user.username), 'ip')
        self.assertEqual(login_blocked('10.0.0.9', self.user.username), 'user')

        completed = self.complete_reset(password_token)
        self.assertEqual(completed.status_code, 200, completed.json())
        self.assertEqual(login_blocked('127.0.0.1', self.user.username), 'ip')
        self.assertEqual(login_blocked('10.0.0.9', self.user.username), '')

    def test_expired_transaction_and_unknown_account_share_safe_failures(self):
        """事务过期必须拒绝，未知账号的 OTP 失败不得泄露账号状态。"""
        token = self.start_reset().json()['reset_token']
        cache.clear()
        expired = self.verify_reset_otp(token, int(time.time() // 30))
        self.assertEqual(expired.status_code, 401, expired.json())

        unknown_token = self.start_reset(username='unknown-user').json()['reset_token']
        unknown = self.verify_reset_otp(unknown_token, int(time.time() // 30), credential='000000')
        real_token = self.start_reset().json()['reset_token']
        real = self.verify_reset_otp(real_token, int(time.time() // 30), credential='000000')
        self.assertEqual(unknown.status_code, real.status_code)
        self.assertEqual(unknown.json()['detail'], real.json()['detail'])
