from datetime import datetime, timedelta, timezone

from django.contrib.auth.models import User
from django.db import connection
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from ops.models import AuditLog, SystemSetting
from ops.services.instance_identity import get_instance_id
from ops.services.license_management import license_public_metadata, normalize_license_content
from ops.services.license_time_guard import trusted_license_time
from ops.test_license_support import signed_test_license, trusted_test_key, verified_license_metadata


@override_settings(SM4_MASTER_KEYS=['unit-test-sm4-master-key'])
class LicenseImportTests(TestCase):
    """验证 SM2 Licence 导入、额度、实例和失败保护规则。"""

    def setUp(self):
        """安装测试公钥并创建固定的唯一 admin。"""
        self.trusted_key = trusted_test_key()
        self.trusted_key.start()
        self.admin = User.objects.create_superuser(
            username='admin',
            email='license-admin@example.com',
            password='StrongPassword123!',
        )

    def tearDown(self):
        """恢复生产可信公钥表。"""
        self.trusted_key.stop()

    def test_valid_sm2_license_is_normalized_with_concurrency_and_type(self):
        """正确签名且用户额度足够的 Licence 应保存全部展示字段。"""
        content = signed_test_license(max_users=1, max_concurrency=2)

        normalized = normalize_license_content(content)

        self.assertEqual(normalized['verification'], 'sm2-sm3')
        self.assertEqual(normalized['license_type'], '堡垒机')
        self.assertEqual(normalized['max_users'], 1)
        self.assertEqual(normalized['max_concurrency'], 2)
        self.assertEqual(normalized['instance_id'], get_instance_id())

    def test_tampered_signature_and_unknown_key_are_rejected(self):
        """签名字符被修改或 key_id 不在内置信任表时必须拒绝导入。"""
        content = signed_test_license()
        header, payload, signature = content.split('.')
        replacement = 'A' if signature[0] != 'A' else 'B'
        tampered = f'{header}.{payload}.{replacement}{signature[1:]}'

        with self.assertRaisesRegex(ValueError, '签名验证失败'):
            normalize_license_content(tampered)
        self.trusted_key.stop()
        try:
            with self.assertRaisesRegex(ValueError, '未知的签发公钥'):
                normalize_license_content(content)
        finally:
            self.trusted_key.start()

    def test_instance_type_and_active_user_limit_are_enforced(self):
        """实例、堡垒机类型和包含 admin 的启用用户数必须同时满足。"""
        User.objects.create_user(username='enabled-user', password='StrongPassword123!')
        User.objects.create_user(username='disabled-user', password='StrongPassword123!', is_active=False)

        with self.assertRaisesRegex(ValueError, '实例 ID 与当前服务器不一致'):
            normalize_license_content(signed_test_license(instance_id='11111111-2222-8333-8444-555555555555'))
        with self.assertRaisesRegex(ValueError, '只接受授权类型“堡垒机”'):
            normalize_license_content(signed_test_license(license_type='数据库'))
        with self.assertRaisesRegex(ValueError, '当前启用用户数为 2'):
            normalize_license_content(signed_test_license(max_users=1))

    def test_failed_api_import_preserves_existing_license_and_writes_failure_audit(self):
        """导入错误 Licence 时不得覆盖旧配置，并记录不含原文的失败系统日志。"""
        setting = SystemSetting.objects.get(key='license.management')
        previous = verified_license_metadata()
        setting.value = previous
        setting.save(update_fields=['value', 'updated_at'])
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.put('/api/v1/system-settings/license/management/', {
            'value': {'license_secret': 'invalid-license'},
        }, format='json')

        self.assertEqual(response.status_code, 400, response.json())
        setting.refresh_from_db()
        self.assertEqual(setting.value, previous)
        log = AuditLog.objects.filter(action='SystemSetting.license_import').latest('id')
        self.assertEqual(log.detail['result'], 'failed')
        self.assertNotIn('invalid-license', str(log.detail))


@override_settings(SM4_MASTER_KEYS=['unit-test-sm4-master-key'])
class LicenseTimeGuardTests(TestCase):
    """验证一小时容忍窗口、可信时间高水位和不可用锁存。"""

    def test_rollback_within_one_hour_is_tolerated_without_extending_time(self):
        """一小时以内回拨应继续使用历史高水位且不进入不可用状态。"""
        high_water = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        trusted_license_time(now=high_water)

        trusted, reason = trusted_license_time(now=high_water - timedelta(minutes=59))

        self.assertEqual(reason, '')
        self.assertEqual(trusted, high_water)

    def test_rollback_over_one_hour_is_persistently_unavailable(self):
        """超过一小时回拨必须永久锁存，墙上时间恢复后也不能自动解锁。"""
        high_water = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)
        trusted_license_time(now=high_water)

        _trusted, first_reason = trusted_license_time(now=high_water - timedelta(hours=1, seconds=1))
        _trusted, later_reason = trusted_license_time(now=high_water + timedelta(days=1))

        self.assertIn('回拨超过 1 小时', first_reason)
        self.assertEqual(later_reason, first_reason)
        metadata = license_public_metadata(verified_license_metadata(), now=high_water + timedelta(days=2))
        self.assertEqual(metadata['status'], 'unavailable')
        with connection.cursor() as cursor:
            cursor.execute("SELECT value FROM ops_systemsetting WHERE key = 'license.time_guard'")
            stored = cursor.fetchone()[0]
        self.assertIn('sm4:v1:', stored)
        self.assertNotIn('回拨超过 1 小时', stored)
