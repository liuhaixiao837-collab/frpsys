import time
from urllib.parse import parse_qs, urlsplit

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import SystemSetting
from ops.services.license_access import current_license_status
from ops.services.otp import totp_code
from ops.services.tokens import issue_pair
from ops.test_license_support import verified_license_metadata


class LicenseLoginAccessTests(TestCase):
    """验证 Licence 三状态对普通用户、admin 和已签发令牌的访问限制。"""

    def setUp(self):
        """创建唯一 admin、普通用户，并关闭与 Licence 无关的登录校验。"""
        self.client = APIClient()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='StrongPassword123!',
        )
        self.user = User.objects.create_user(
            username='license-user',
            email='license-user@example.com',
            password='StrongPassword123!',
        )
        login_setting = SystemSetting.objects.get(key='security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': False,
            'slider_captcha_enabled': False,
            'otp_enabled': False,
        }
        login_setting.save(update_fields=['value', 'updated_at'])

    def set_license(self, state):
        """写入测试所需的 Licence 状态并返回保存后的平台配置。"""
        values = {
            'valid': verified_license_metadata(),
            'expired': verified_license_metadata(expired=True),
            'unconfigured': {'configured': False},
            'damaged': {'configured': True, 'verification': 'structure'},
        }
        setting = SystemSetting.objects.get(key='license.management')
        setting.value = values[state]
        setting.save(update_fields=['value', 'updated_at'])
        return setting

    def login(self, username='license-user', password='StrongPassword123!', **extra):
        """提交不含验证码的登录请求，并允许测试补充 OTP 会话参数。"""
        return self.client.post('/api/v1/auth/login', {
            'username': username,
            'password': password,
            **extra,
        }, format='json')

    def test_unconfigured_and_expired_license_reject_normal_user(self):
        """普通用户在未配置或已过期状态下不得进入系统。"""
        self.set_license('unconfigured')
        unconfigured = self.login()
        self.set_license('expired')
        expired = self.login()

        self.assertEqual(unconfigured.status_code, 403, unconfigured.json())
        self.assertEqual(unconfigured.json()['code'], 'LICENSE_UNCONFIGURED')
        self.assertEqual(expired.status_code, 403, expired.json())
        self.assertEqual(expired.json()['code'], 'LICENSE_EXPIRED')

    def test_valid_license_allows_normal_user_and_admin_always_bypasses(self):
        """有效 Licence 允许普通用户登录，唯一 admin 在未配置状态下仍可维护系统。"""
        self.set_license('valid')
        normal = self.login()
        self.set_license('unconfigured')
        admin = self.login(username='admin')

        self.assertEqual(normal.status_code, 200, normal.json())
        self.assertIn('access', normal.json())
        self.assertEqual(admin.status_code, 200, admin.json())
        self.assertIn('access', admin.json())

    def test_damaged_license_is_exposed_and_enforced_as_unavailable(self):
        """损坏或旧版 Licence 必须进入不可用状态并拒绝普通用户。"""
        self.set_license('damaged')

        response = self.login()

        self.assertEqual(current_license_status(), 'unavailable')
        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(response.json()['code'], 'LICENSE_UNAVAILABLE')

    def test_expiry_revokes_existing_access_and_refresh_tokens(self):
        """Licence 到期后普通用户的旧访问令牌和刷新令牌必须立即失效。"""
        self.set_license('valid')
        logged_in = self.login()
        self.assertEqual(logged_in.status_code, 200, logged_in.json())
        tokens = logged_in.json()
        self.set_license('expired')

        access_client = APIClient()
        access_client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")
        current_user = access_client.get('/api/v1/me')
        refreshed = self.client.post('/api/v1/auth/refresh', {
            'refresh': tokens['refresh'],
        }, format='json')

        self.assertEqual(current_user.status_code, 401, current_user.json())
        self.assertEqual(refreshed.status_code, 403, refreshed.json())
        self.assertEqual(refreshed.json()['code'], 'LICENSE_EXPIRED')

    def test_invalid_license_stops_login_before_otp_transaction(self):
        """Licence 无效时必须在 OTP 预认证事务签发前拒绝普通用户。"""
        login_setting = SystemSetting.objects.get(key='security.login')
        login_setting.value = {**login_setting.value, 'otp_enabled': True}
        login_setting.save(update_fields=['value', 'updated_at'])
        self.set_license('expired')

        response = self.login(client_nonce='license-otp-client-nonce-0001')

        self.assertEqual(response.status_code, 403, response.json())
        self.assertEqual(response.json()['code'], 'LICENSE_EXPIRED')
        self.assertNotIn('preauth_token', response.json())

    def test_license_expiring_during_otp_does_not_issue_token(self):
        """OTP 事务期间 Licence 到期时，最终验证成功也不得签发正式令牌。"""
        login_setting = SystemSetting.objects.get(key='security.login')
        login_setting.value = {**login_setting.value, 'otp_enabled': True}
        login_setting.save(update_fields=['value', 'updated_at'])
        self.set_license('valid')
        nonce = 'license-otp-client-nonce-0002'
        begin = self.login(client_nonce=nonce)
        self.assertEqual(begin.status_code, 200, begin.json())
        token = begin.json()['preauth_token']
        setup = self.client.post('/api/v1/auth/otp/setup', {
            'preauth_token': token,
            'client_nonce': nonce,
        }, format='json')
        self.assertEqual(setup.status_code, 200, setup.json())
        secret = parse_qs(urlsplit(setup.json()['otpauth_uri']).query)['secret'][0]
        self.set_license('expired')

        confirm = self.client.post('/api/v1/auth/otp/confirm', {
            'preauth_token': token,
            'client_nonce': nonce,
            'code': totp_code(secret, int(time.time() // 30)),
        }, format='json')

        self.assertEqual(confirm.status_code, 401, confirm.json())
        self.assertNotIn('access', confirm.json())
        self.assertIn('Licence 已过期', confirm.json()['detail'])

    def test_user_creation_and_reactivation_respect_license_user_limit(self):
        """新增启用用户和重新启用用户都不得使启用人数超过授权额度。"""
        setting = self.set_license('valid')
        setting.value = verified_license_metadata(max_users=3)
        setting.save(update_fields=['value', 'updated_at'])
        admin_client = APIClient()
        admin_client.force_authenticate(self.admin)

        allowed = admin_client.post('/api/v1/users/', {
            'username': 'quota-allowed',
            'password': 'StrongPassword123!',
            'is_active': True,
        }, format='json')
        denied = admin_client.post('/api/v1/users/', {
            'username': 'quota-denied',
            'password': 'StrongPassword123!',
            'is_active': True,
        }, format='json')
        inactive = admin_client.post('/api/v1/users/', {
            'username': 'quota-inactive',
            'password': 'StrongPassword123!',
            'is_active': False,
        }, format='json')
        reactivated = admin_client.patch(
            f"/api/v1/users/{inactive.json()['id']}/",
            {'is_active': True},
            format='json',
        )

        self.assertEqual(allowed.status_code, 201, allowed.json())
        self.assertEqual(denied.status_code, 400, denied.json())
        self.assertIn('Licence 授权用户数不足', str(denied.json()))
        self.assertEqual(inactive.status_code, 201, inactive.json())
        self.assertEqual(reactivated.status_code, 400, reactivated.json())
        self.assertIn('当前最多允许 3 个启用用户', str(reactivated.json()))

    def test_concurrency_limit_rejects_new_normal_user_before_token_issue(self):
        """并发额度占满后，新普通用户登录必须留在登录流程且不得获得令牌。"""
        setting = self.set_license('valid')
        setting.value = verified_license_metadata(max_concurrency=1)
        setting.save(update_fields=['value', 'updated_at'])
        occupied = User.objects.create_user(
            username='occupied-user',
            password='StrongPassword123!',
        )
        issue_pair(occupied)

        response = self.login()

        self.assertEqual(response.status_code, 401, response.json())
        self.assertNotIn('access', response.json())
        self.assertIn('Licence 并发上限（1 人）', response.json()['detail'])

    def test_admin_does_not_consume_concurrency_and_existing_user_can_login_again(self):
        """admin 不占并发额度，同一普通用户重复登录也不重复占用用户数。"""
        setting = self.set_license('valid')
        setting.value = verified_license_metadata(max_concurrency=1)
        setting.save(update_fields=['value', 'updated_at'])
        issue_pair(self.admin)

        first = self.login()
        second = self.login()

        self.assertEqual(first.status_code, 200, first.json())
        self.assertEqual(second.status_code, 200, second.json())
        self.assertIn('access', second.json())


class SystemAdminInvariantTests(TestCase):
    """验证系统中只有固定用户名 admin 可以成为超级管理员。"""

    def setUp(self):
        """创建系统唯一 admin，并用其访问用户管理接口。"""
        self.admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='StrongPassword123!',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_reserved_name_and_second_superuser_are_rejected(self):
        """大小写变体保留名和任何非 admin 超级管理员都不得保存。"""
        with self.assertRaises(ValidationError):
            User.objects.create_user(username='Admin', password='StrongPassword123!')
        with self.assertRaises(ValidationError):
            User.objects.create_superuser(username='root', password='StrongPassword123!')

    def test_admin_cannot_be_renamed_disabled_or_deleted_by_api(self):
        """用户管理接口必须拒绝修改 admin 用户名、停用或删除该账号。"""
        renamed = self.client.patch(
            f'/api/v1/users/{self.admin.id}/',
            {'username': 'root'},
            format='json',
        )
        disabled = self.client.patch(
            f'/api/v1/users/{self.admin.id}/',
            {'is_active': False},
            format='json',
        )
        deleted = self.client.delete(f'/api/v1/users/{self.admin.id}/')

        self.assertEqual(renamed.status_code, 400, renamed.json())
        self.assertEqual(disabled.status_code, 400, disabled.json())
        self.assertEqual(deleted.status_code, 400, deleted.json())
        self.admin.refresh_from_db()
        self.assertEqual(self.admin.username, 'admin')
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_superuser)

    def test_saving_admin_restores_required_administrator_flags(self):
        """绕过接口修改 admin 标记时，模型保存钩子必须恢复其启用和管理员身份。"""
        self.admin.is_active = False
        self.admin.is_staff = False
        self.admin.is_superuser = False

        self.admin.save()

        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertTrue(self.admin.is_staff)
        self.assertTrue(self.admin.is_superuser)
