from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ops.models import AuditLog, Organization, SmsLoginChallenge, SystemSetting, UserProfile
from ops.serializers import UserSerializer
from ops.services.otp import totp_code
from ops.services.phone_identity import phone_lookup_hash


class SmsLoginTests(TestCase):
    """验证短信登录、三十秒一次性挑战、OTP 衔接和手机号唯一规则。"""

    def setUp(self):
        """创建具备唯一手机号和已绑定 OTP 的系统管理员。"""
        cache.clear()
        self.client = APIClient()
        self.organization = Organization.objects.create(
            name='短信登录测试部门',
            slug='sms-login-test',
            description='短信登录专项测试部门',
            region='中国',
            org_type='company',
            is_default=True,
            is_active=True,
        )
        self.user = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='StrongPassword123!',
        )
        self.phone = '13800138000'
        self.otp_secret = 'JBSWY3DPEHPK3PXP'
        UserProfile.objects.create(
            user=self.user,
            organization=self.organization,
            role='admin',
            phone=self.phone,
            phone_lookup_hash=phone_lookup_hash(self.phone),
            otp_policy='required',
            otp_secret=self.otp_secret,
            otp_bound_at=timezone.now(),
        )
        login_setting = SystemSetting.objects.get(key='security.login')
        login_setting.value = {
            **login_setting.value,
            'captcha_enabled': True,
            'slider_captcha_enabled': True,
            'otp_enabled': True,
            'sms_login_enabled': True,
            'sms_failure_limit': 3,
            'sms_lock_minutes': 20,
        }
        login_setting.save(update_fields=['value', 'updated_at'])
        notification = SystemSetting.objects.get(key='notification.delivery')
        notification.value = {
            **notification.value,
            'sms': {
                'enabled': True,
                'provider': 'aliyun',
                'access_key_id': 'test-access-key-id',
                'access_key_secret': 'test-access-key-secret',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'recipient_limit_per_minute': 5,
                'recipient_limit_per_hour': 20,
                'recipient_limit_per_day': 50,
            },
        }
        notification.save(update_fields=['value', 'updated_at'])
        self.client_nonce = 'sms-login-browser-nonce-0001'

    def verification_credentials(self):
        """获取当前来源可消费的字符验证码和拖拽验证凭证。"""
        captcha = self.client.get('/api/v1/auth/captcha').json()
        slider = self.client.get('/api/v1/auth/slider-captcha').json()
        verified = self.client.post('/api/v1/auth/slider-captcha', {
            'challenge_token': slider['challenge_token'],
            'offset_x': slider['target_x'],
            'elapsed_ms': 800,
        }, format='json')
        self.assertEqual(verified.status_code, 200, verified.json())
        return captcha, verified.json()['verification_token']

    def send_code(self):
        """使用完整反自动化凭证发送固定测试短信验证码。"""
        captcha, slider_verification = self.verification_credentials()
        with patch('ops.services.sms_login.secrets.randbelow', return_value=123456), patch(
            'ops.services.sms_login.send_login_sms',
            return_value=True,
        ) as mocked_send:
            response = self.client.post('/api/v1/auth/sms-login/send', {
                'phone': self.phone,
                'captcha_token': captcha['token'],
                'captcha_code': captcha['code'],
                'slider_verification': slider_verification,
                'client_nonce': self.client_nonce,
            }, format='json')
        self.assertEqual(response.status_code, 200, response.json())
        mocked_send.assert_called_once_with(self.phone, '123456')
        return response.json()['challenge_token']

    def test_sms_code_is_thirty_seconds_single_use_and_then_requires_otp(self):
        """短信验证码必须三十秒有效、只能使用一次且成功后只进入 OTP。"""
        token = self.send_code()
        challenge = SmsLoginChallenge.objects.get()
        remaining = (challenge.expires_at - challenge.created_at).total_seconds()
        self.assertGreaterEqual(remaining, 29)
        self.assertLessEqual(remaining, 31)

        verified = self.client.post('/api/v1/auth/sms-login/verify', {
            'challenge_token': token,
            'code': '123456',
            'client_nonce': self.client_nonce,
        }, format='json')
        replayed = self.client.post('/api/v1/auth/sms-login/verify', {
            'challenge_token': token,
            'code': '123456',
            'client_nonce': self.client_nonce,
        }, format='json')

        self.assertEqual(verified.status_code, 200, verified.json())
        self.assertEqual(verified.json()['next_step'], 'otp_verify')
        self.assertNotIn('access', verified.json())
        self.assertEqual(replayed.status_code, 400)

        timestep = int(timezone.now().timestamp() // 30)
        with patch('ops.services.otp.time.time', return_value=timestep * 30 + 1):
            completed = self.client.post('/api/v1/auth/otp/verify', {
                'preauth_token': verified.json()['preauth_token'],
                'client_nonce': self.client_nonce,
                'credential': totp_code(self.otp_secret, timestep),
            }, format='json')
        self.assertEqual(completed.status_code, 200, completed.json())
        self.assertIn('access', completed.json())
        self.assertTrue(AuditLog.objects.filter(
            action='auth.login.success',
            detail__auth_method='sms+otp',
        ).exists())

    def test_expired_sms_code_is_rejected_without_incrementing_error_count(self):
        """服务端时间超过三十秒后必须拒绝验证码且不累计输入错误。"""
        token = self.send_code()
        SmsLoginChallenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))

        response = self.client.post('/api/v1/auth/sms-login/verify', {
            'challenge_token': token,
            'code': '123456',
            'client_nonce': self.client_nonce,
        }, format='json')

        self.assertEqual(response.status_code, 400)
        self.user.profile.refresh_from_db()
        self.assertEqual(self.user.profile.sms_failed_attempts, 0)

    def test_wrong_sms_codes_trigger_database_lock_policy(self):
        """连续错误达到平台阈值后必须锁定短信验证并消费挑战。"""
        token = self.send_code()

        responses = [self.client.post('/api/v1/auth/sms-login/verify', {
            'challenge_token': token,
            'code': '000000',
            'client_nonce': self.client_nonce,
        }, format='json') for _index in range(3)]

        self.assertEqual([response.status_code for response in responses], [400, 400, 429])
        self.user.profile.refresh_from_db()
        self.assertGreater(self.user.profile.sms_locked_until, timezone.now() + timedelta(minutes=19))
        self.assertIsNotNone(SmsLoginChallenge.objects.get().consumed_at)

    def test_user_serializer_rejects_duplicate_normalized_phone(self):
        """新增用户必须拒绝与现有加密手机号相同的标准手机号。"""
        serializer = UserSerializer(data={
            'username': 'sms-user',
            'password': 'StrongPassword123!',
            'phone': '+86 138-0013-8000',
            'department_id': self.organization.id,
        })

        self.assertFalse(serializer.is_valid())
        self.assertIn('手机号已绑定其他用户', str(serializer.errors))

    def test_public_settings_expose_only_sms_login_switch(self):
        """公开设置只增加短信登录布尔值，不暴露网关和模板配置。"""
        response = self.client.get('/api/v1/public/platform')

        self.assertEqual(response.status_code, 200, response.json())
        self.assertIs(response.json()['sms_login_enabled'], True)
        self.assertNotIn('template_code', str(response.json()))
        self.assertNotIn('access_key', str(response.json()).lower())
