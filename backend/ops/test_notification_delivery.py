import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import AuditLog, SmsDispatchRecord, SystemSetting
from ops.services.notifications import NotificationRateLimitError, NotificationSendError, send_test_email, send_test_sms


class NotificationDeliveryTests(TestCase):
    """验证通知测试接口、渠道调用和敏感信息边界。"""

    def setUp(self):
        """创建系统管理员并写入不会真实外发的测试配置。"""
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='admin@example.com',
            password='StrongPassword123!',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        setting = SystemSetting.objects.get(key='notification.delivery')
        setting.value = {
            'email': {
                'enabled': True,
                'smtp_host': 'smtp.example.com',
                'smtp_port': 465,
                'security': 'ssl',
                'sender_email': 'notice@example.com',
                'username': 'notice@example.com',
                'password': 'smtp-secret',
            },
            'sms': {
                'enabled': True,
                'provider': 'aliyun',
                'access_key_id': 'test-access-key-id',
                'access_key_secret': 'test-access-key-secret',
                'sign_name': '测试签名',
                'template_code': 'SMS_123456789',
                'recipient_limit_per_minute': 1,
                'recipient_limit_per_hour': 10,
                'recipient_limit_per_day': 50,
            },
        }
        setting.save(update_fields=['value', 'updated_at'])
        platform = SystemSetting.objects.get(key='platform')
        platform.value = {**platform.value, 'name': '清风堡垒机'}
        platform.save(update_fields=['value', 'updated_at'])

    @patch('ops.views.send_test_email')
    def test_email_endpoint_validates_sends_audits_and_throttles(self, mocked_send):
        """邮件接口应只传收件邮箱、写安全审计并限制连续点击。"""
        response = self.client.post(
            '/api/v1/system-settings/notification/test/email/',
            {'recipient': 'receiver@example.com'},
            format='json',
        )
        repeated = self.client.post(
            '/api/v1/system-settings/notification/test/email/',
            {'recipient': 'receiver@example.com'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(repeated.status_code, 429)
        mocked_send.assert_called_once_with('receiver@example.com')
        audit = AuditLog.objects.get(action='SystemSetting.test_email')
        self.assertEqual(audit.resource, 'notification.delivery')
        self.assertEqual(audit.detail, {
            'key': 'notification.delivery',
            'channel': 'email',
            'result': 'success',
        })
        self.assertNotIn('receiver@example.com', str(audit.detail))

    def test_setting_api_persists_recipient_rate_limits(self):
        """平台设置接口应分别保存邮箱和手机号的三个频率窗口。"""
        setting = SystemSetting.objects.get(key='notification.delivery')
        value = setting.value
        value['email'].update({
            'recipient_limit_per_minute': 8,
            'recipient_limit_per_hour': 120,
            'recipient_limit_per_day': 800,
        })
        value['sms'].update({
            'recipient_limit_per_minute': 2,
            'recipient_limit_per_hour': 20,
            'recipient_limit_per_day': 80,
        })

        response = self.client.put(
            '/api/v1/system-settings/notification/delivery/',
            {'value': value, 'description': setting.description},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.json())
        saved = SystemSetting.objects.get(key='notification.delivery').value
        self.assertEqual(saved['email']['recipient_limit_per_minute'], 8)
        self.assertEqual(saved['email']['recipient_limit_per_hour'], 120)
        self.assertEqual(saved['email']['recipient_limit_per_day'], 800)
        self.assertEqual(saved['sms']['recipient_limit_per_minute'], 2)
        self.assertEqual(saved['sms']['recipient_limit_per_hour'], 20)
        self.assertEqual(saved['sms']['recipient_limit_per_day'], 80)

    def test_setting_api_rejects_inconsistent_recipient_rate_limits(self):
        """分钟上限大于小时上限时必须拒绝保存整个通知配置。"""
        setting = SystemSetting.objects.get(key='notification.delivery')
        value = setting.value
        value['email'].update({
            'recipient_limit_per_minute': 20,
            'recipient_limit_per_hour': 10,
            'recipient_limit_per_day': 100,
        })

        response = self.client.put(
            '/api/v1/system-settings/notification/delivery/',
            {'value': value, 'description': setting.description},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('每分钟不大于每小时', str(response.json()))

    @patch('ops.views.send_test_sms')
    def test_sms_endpoint_normalizes_china_country_code(self, mocked_send):
        """短信接口应接受中国国家码并只向发送服务传十一位手机号。"""
        response = self.client.post(
            '/api/v1/system-settings/notification/test/sms/',
            {'phone': '+86 13800138000'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.json())
        mocked_send.assert_called_once_with('13800138000')
        audit = AuditLog.objects.get(action='SystemSetting.test_sms')
        self.assertEqual(audit.detail['result'], 'success')
        self.assertNotIn('13800138000', str(audit.detail))

    def test_sms_endpoint_rejects_invalid_phone_before_sending(self):
        """无效手机号必须在调用第三方渠道前返回友好校验提示。"""
        response = self.client.post(
            '/api/v1/system-settings/notification/test/sms/',
            {'phone': '12345'},
            format='json',
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn('有效的中国大陆手机号', str(response.json()))

    @patch('ops.services.notifications.EmailMultiAlternatives')
    @patch('ops.services.notifications.EmailBackend')
    def test_email_service_builds_html_and_text_without_external_assets(self, backend_class, message_class):
        """邮件服务应使用保存配置并生成带平台名称的纯文本和 HTML 正文。"""
        message = message_class.return_value
        message.send.return_value = 1

        self.assertTrue(send_test_email('receiver@example.com'))

        backend_class.assert_called_once_with(
            host='smtp.example.com', port=465,
            username='notice@example.com', password='smtp-secret',
            use_tls=False, use_ssl=True, timeout=10, fail_silently=False,
        )
        call = message_class.call_args.kwargs
        self.assertIn('清风堡垒机', call['subject'])
        self.assertIn('清风堡垒机', call['body'])
        self.assertEqual(call['to'], ['receiver@example.com'])
        html_body, content_type = message.attach_alternative.call_args.args
        self.assertEqual(content_type, 'text/html')
        self.assertIn('配置验证成功', html_body)
        self.assertNotIn('http://', html_body)
        self.assertNotIn('https://', html_body)

    @patch('ops.services.notifications.requests.post')
    def test_sms_service_uses_saved_template_with_code_parameter(self, mocked_post):
        """短信服务必须签名已保存模板并只提交六位验证码变量。"""
        mocked_post.return_value = Mock(ok=True)
        mocked_post.return_value.json.return_value = {'Code': 'OK', 'RequestId': 'request-id'}

        self.assertTrue(send_test_sms('13800138000'))

        kwargs = mocked_post.call_args.kwargs
        self.assertEqual(kwargs['timeout'], 10)
        self.assertEqual(kwargs['data']['TemplateCode'], 'SMS_123456789')
        self.assertEqual(kwargs['data']['SignName'], '测试签名')
        self.assertEqual(kwargs['data']['PhoneNumbers'], '13800138000')
        self.assertIn('Signature', kwargs['data'])
        self.assertEqual(kwargs['data']['TemplateParam'], '{"code":"123456"}')
        self.assertNotIn('test-access-key-secret', str(kwargs['data']))
        self.assertEqual(SmsDispatchRecord.objects.get().status, 'sent')

    @patch('ops.services.notifications.requests.post')
    def test_sms_service_supports_six_additional_template_providers(self, mocked_post):
        """其余六家短信服务商都必须只提交 code 验证码变量。"""
        provider_cases = {
            'tencent': ({
                'secret_id': 'tencent-secret-id',
                'secret_key': 'tencent-secret-key',
                'sdk_app_id': '1400000000',
                'sign_name': '测试签名',
                'template_code': '100001',
            }, {'Response': {'SendStatusSet': [{'Code': 'Ok'}]}}),
            'baidu': ({
                'access_key_id': 'baidu-access-key-id',
                'access_key_secret': 'baidu-access-key-secret',
                'signature_id': 'sms-signature-id',
                'template_code': 'sms-template-id',
            }, {'code': 1000}),
            'upyun': ({
                'authorization_token': 'Bearer upyun-token',
                'template_code': 'upyun-template-id',
            }, {'code': 0}),
            'qiniu': ({
                'access_key_id': 'qiniu-access-key-id',
                'access_key_secret': 'qiniu-access-key-secret',
                'template_code': 'qiniu-template-id',
            }, {'job_id': 'job-id'}),
            'yunpian': ({
                'api_key': 'yunpian-api-key',
                'template_code': '1234567',
            }, {'code': 0}),
            'netease': ({
                'app_key': 'netease-app-key',
                'app_secret': 'netease-app-secret',
                'template_code': '9876543',
            }, {'code': 200}),
        }

        for index, (provider, (provider_config, response_payload)) in enumerate(provider_cases.items()):
            with self.subTest(provider=provider):
                setting = SystemSetting.objects.get(key='notification.delivery')
                setting.value = {
                    **setting.value,
                    'sms': {
                        'enabled': True,
                        'provider': provider,
                        **provider_config,
                        'recipient_limit_per_minute': 1,
                        'recipient_limit_per_hour': 10,
                        'recipient_limit_per_day': 50,
                    },
                }
                setting.save(update_fields=['value', 'updated_at'])
                mocked_post.reset_mock()
                mocked_post.return_value = Mock(ok=True, status_code=200, content=b'{}')
                mocked_post.return_value.json.return_value = response_payload

                self.assertTrue(send_test_sms(f'1380013800{index}'))

                kwargs = mocked_post.call_args.kwargs
                if provider in {'tencent', 'baidu', 'qiniu'}:
                    body = json.loads(kwargs['data'].decode('utf-8'))
                else:
                    body = kwargs['data']
                if provider == 'tencent':
                    self.assertTrue(kwargs['headers']['Authorization'].startswith('TC3-HMAC-SHA256 '))
                    self.assertEqual(kwargs['headers']['X-TC-Action'], 'SendSms')
                    self.assertEqual(body['TemplateParamSet'], ['123456'])
                elif provider == 'baidu':
                    self.assertTrue(kwargs['headers']['Authorization'].startswith('bce-auth-v1/'))
                    self.assertEqual(body['contentVar'], {'code': '123456'})
                elif provider == 'upyun':
                    self.assertEqual(kwargs['headers']['Authorization'], 'Bearer upyun-token')
                    self.assertEqual(body['vars'], '123456')
                elif provider == 'qiniu':
                    self.assertTrue(kwargs['headers']['Authorization'].startswith('Qiniu '))
                    self.assertEqual(body['mobile'], f'1380013800{index}')
                    self.assertEqual(body['parameters'], {'code': '123456'})
                elif provider == 'yunpian':
                    self.assertEqual(body['tpl_value'], '#code#=123456')
                else:
                    self.assertEqual(body['params'], '["123456"]')
                    self.assertEqual(len(kwargs['headers']['CheckSum']), 40)
                self.assertEqual(SmsDispatchRecord.objects.latest('id').status, 'sent')

    @patch('ops.services.notifications.requests.post')
    def test_sms_service_applies_dynamic_recipient_limit(self, mocked_post):
        """同一手机号必须实时应用短信网关保存的分钟发送上限。"""
        mocked_post.return_value = Mock(ok=True)
        mocked_post.return_value.json.return_value = {'Code': 'OK'}

        self.assertTrue(send_test_sms('13800138000'))
        with self.assertRaises(NotificationRateLimitError):
            send_test_sms('13800138000')

        self.assertEqual(mocked_post.call_count, 1)

    @patch('ops.services.notifications.requests.post')
    def test_sms_service_returns_safe_provider_error(self, mocked_post):
        """阿里云失败提示只保留错误码，不泄露第三方原始消息。"""
        mocked_post.return_value = Mock(ok=True)
        mocked_post.return_value.json.return_value = {
            'Code': 'isv.BUSINESS_LIMIT_CONTROL',
            'Message': 'sensitive provider context with phone 13800138000',
        }

        with self.assertRaises(NotificationSendError) as caught:
            send_test_sms('13800138000')

        self.assertIn('isv.BUSINESS_LIMIT_CONTROL', str(caught.exception))
        self.assertNotIn('13800138000', str(caught.exception))
