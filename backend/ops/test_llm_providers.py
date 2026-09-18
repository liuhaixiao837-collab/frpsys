import json
from unittest.mock import Mock, patch

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ops.models import AuditLog, SystemSetting
from ops.serializers import SystemSettingSerializer
from ops.services.llm_providers import (
    LLM_PROVIDER_DEFINITIONS,
    LlmConnectionError,
    default_llm_settings,
    test_llm_provider,
)


@override_settings(SM4_MASTER_KEYS=['unit-test-sm4-master-key'])
class LlmProviderTests(TestCase):
    """验证六家 LLM 配置、连通性检测和敏感信息边界。"""

    def setUp(self):
        """创建管理员客户端和一份可检测的六厂商配置。"""
        cache.clear()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='llm-admin@example.com',
            password='StrongPassword123!',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)
        value = default_llm_settings()
        for provider in value['providers']:
            provider['api_key'] = f"secret-{provider['code']}"
            provider['enabled'] = True
        self.setting, _created = SystemSetting.objects.update_or_create(
            key='llm.providers',
            defaults={
                'value': value,
                'description': '平台大语言模型厂商配置',
            },
        )

    def test_serializer_encrypts_masks_and_preserves_api_keys(self):
        """API Key 必须 SM4 加密落库，掩码编辑不能覆盖原值。"""
        represented = SystemSettingSerializer(self.setting).data['value']
        self.assertTrue(all(item['api_key'] == '********' for item in represented['providers']))
        with connection.cursor() as cursor:
            cursor.execute('SELECT value FROM ops_systemsetting WHERE id = %s', [self.setting.id])
            stored = json.loads(cursor.fetchone()[0])
        self.assertTrue(all(item['api_key'].startswith('sm4:v1:') for item in stored['providers']))
        self.assertNotIn('secret-deepseek', json.dumps(stored))

        represented['providers'][0]['model'] = 'deepseek-v4-updated'
        serializer = SystemSettingSerializer(self.setting, data={'value': represented}, partial=True)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        updated = serializer.save()
        self.assertEqual(updated.value['providers'][0]['api_key'], 'secret-deepseek')
        self.assertEqual(updated.value['providers'][0]['status'], 'unchecked')

    def test_serializer_requires_all_providers_and_priority_range(self):
        """配置必须完整包含六家厂商且优先级只能为 1 到 100。"""
        value = default_llm_settings()
        value['providers'][0]['priority'] = 0
        invalid_priority = SystemSettingSerializer(self.setting, data={'value': value}, partial=True)
        self.assertFalse(invalid_priority.is_valid())
        self.assertIn('1 到 100', str(invalid_priority.errors))

        value = default_llm_settings()
        value['providers'].pop()
        incomplete = SystemSettingSerializer(self.setting, data={'value': value}, partial=True)
        self.assertFalse(incomplete.is_valid())
        self.assertIn('六家内置厂商', str(incomplete.errors))

    def test_serializer_rejects_non_official_provider_host(self):
        """厂商接口地址不能被改成任意主机或内网探测地址。"""
        value = default_llm_settings()
        value['providers'][0]['base_url'] = 'https://127.0.0.1/v1'
        serializer = SystemSettingSerializer(self.setting, data={'value': value}, partial=True)
        self.assertFalse(serializer.is_valid())
        self.assertIn('官方接口地址', str(serializer.errors))

    @patch('ops.services.llm_providers.requests.post')
    def test_six_providers_use_their_saved_endpoint_and_model(self, mocked_post):
        """六家厂商均按保存的官方地址、模型和 Bearer 密钥发起检测。"""
        mocked_post.return_value = Mock(status_code=200)
        providers = default_llm_settings()['providers']
        for provider in providers:
            provider['api_key'] = f"key-{provider['code']}"
            self.assertTrue(test_llm_provider(provider))
            call = mocked_post.call_args
            definition = LLM_PROVIDER_DEFINITIONS[provider['code']]
            self.assertEqual(call.args[0], f"{definition['base_url']}/chat/completions")
            self.assertEqual(call.kwargs['json']['model'], definition['model'])
            self.assertEqual(call.kwargs['headers']['Authorization'], f"Bearer key-{provider['code']}")
        self.assertEqual(mocked_post.call_count, 6)

    @patch('ops.views.test_llm_provider')
    def test_detection_success_updates_status_and_writes_safe_audit(self, mocked_test):
        """检测成功应回写可用状态，审计仅包含厂商和结果。"""
        response = self.client.post(
            '/api/v1/system-settings/llm/test/',
            {'provider': 'deepseek'},
            format='json',
        )

        self.assertEqual(response.status_code, 200, response.json())
        mocked_test.assert_called_once()
        self.setting.refresh_from_db()
        provider = self.setting.value['providers'][0]
        self.assertEqual(provider['status'], 'available')
        self.assertTrue(provider['last_checked_at'])
        audit = AuditLog.objects.get(action='SystemSetting.test_llm')
        self.assertEqual(audit.detail, {
            'key': 'llm.providers',
            'provider': 'deepseek',
            'result': 'available',
        })
        self.assertNotIn('secret-deepseek', str(audit.detail))

    @patch('ops.views.test_llm_provider', side_effect=LlmConnectionError('模型服务鉴权失败，请检查 API Key'))
    def test_detection_failure_updates_unavailable_without_leaking_secret(self, mocked_test):
        """检测失败应回写不可用状态并返回经过收敛的中文错误。"""
        response = self.client.post(
            '/api/v1/system-settings/llm/test/',
            {'provider': 'qwen'},
            format='json',
        )

        self.assertEqual(response.status_code, 502, response.json())
        self.assertIn('鉴权失败', response.json()['detail'])
        self.assertNotIn('secret-qwen', str(response.json()))
        self.setting.refresh_from_db()
        provider = next(item for item in self.setting.value['providers'] if item['code'] == 'qwen')
        self.assertEqual(provider['status'], 'unavailable')
        self.assertEqual(mocked_test.call_count, 1)

    @patch('ops.views.test_llm_provider')
    def test_detection_throttles_repeated_provider_clicks(self, mocked_test):
        """同一用户连续检测同一厂商时应执行五秒限流。"""
        first = self.client.post('/api/v1/system-settings/llm/test/', {'provider': 'glm'}, format='json')
        repeated = self.client.post('/api/v1/system-settings/llm/test/', {'provider': 'glm'}, format='json')

        self.assertEqual(first.status_code, 200, first.json())
        self.assertEqual(repeated.status_code, 429, repeated.json())
        mocked_test.assert_called_once()
