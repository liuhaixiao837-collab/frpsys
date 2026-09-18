from unittest.mock import patch
from uuid import UUID

from django.test import SimpleTestCase

from ops.services.instance_identity import (
    collect_machine_identifiers,
    derive_instance_id,
    get_instance_id,
)
from ops.services.license_management import license_public_metadata


class InstanceIdentityTests(SimpleTestCase):
    """验证跨平台机器标识采集和实例 ID 的稳定生成规则。"""

    identifiers = {
        'os_install_id': 'A1B2C3D4',
        'firmware_uuid': '11111111-2222-3333-4444-555555555555',
        'system_disk_uuid': '66666666-7777-8888-9999-AAAAAAAAAAAA',
    }

    def setUp(self):
        """测试开始前清除 Django 启动阶段预生成的实例 ID 缓存。"""
        get_instance_id.cache_clear()

    def tearDown(self):
        """清除进程缓存，防止不同测试使用同一个实例 ID。"""
        get_instance_id.cache_clear()

    def test_same_identifiers_generate_stable_uuidv8(self):
        """相同标识在大小写和外层空白变化后仍应生成相同 UUIDv8。"""
        first = derive_instance_id(**self.identifiers)
        second = derive_instance_id(**{
            key: f'  {value.lower()}  '
            for key, value in self.identifiers.items()
        })

        self.assertEqual(first, second)
        self.assertEqual(UUID(first).version, 8)

    def test_each_identifier_changes_instance_id(self):
        """操作系统、固件或磁盘任一标识变化都必须改变实例 ID。"""
        baseline = derive_instance_id(**self.identifiers)

        for key in self.identifiers:
            changed = {**self.identifiers, key: f'{self.identifiers[key]}-changed'}
            self.assertNotEqual(derive_instance_id(**changed), baseline)

    def test_missing_or_placeholder_identifier_is_rejected(self):
        """缺失值和厂商默认占位 UUID 不得生成看似有效的实例 ID。"""
        with self.assertRaises(ValueError):
            derive_instance_id('', self.identifiers['firmware_uuid'], self.identifiers['system_disk_uuid'])
        with self.assertRaises(ValueError):
            derive_instance_id(
                self.identifiers['os_install_id'],
                '00000000-0000-0000-0000-000000000000',
                self.identifiers['system_disk_uuid'],
            )

    @patch('ops.services.instance_identity._collect_windows_identifiers')
    @patch('ops.services.instance_identity.platform.system', return_value='Windows')
    def test_windows_uses_windows_collector(self, system_mock, collector_mock):
        """Windows 环境必须使用注册表、CIM 和系统盘采集器。"""
        collector_mock.return_value = self.identifiers

        self.assertEqual(collect_machine_identifiers(), self.identifiers)
        collector_mock.assert_called_once_with()
        system_mock.assert_called_once_with()

    @patch('ops.services.instance_identity._collect_linux_identifiers')
    @patch('ops.services.instance_identity.platform.system', return_value='Linux')
    def test_linux_uses_linux_collector(self, system_mock, collector_mock):
        """Linux 环境必须使用 machine-id、DMI 和根文件系统采集器。"""
        collector_mock.return_value = self.identifiers

        self.assertEqual(collect_machine_identifiers(), self.identifiers)
        collector_mock.assert_called_once_with()
        system_mock.assert_called_once_with()

    @patch('ops.services.instance_identity.collect_machine_identifiers')
    def test_public_license_metadata_contains_only_derived_instance_id(self, collector_mock):
        """Licence 公开数据应包含实例 ID，但不得包含三个原始机器标识。"""
        collector_mock.return_value = self.identifiers
        expected = derive_instance_id(**self.identifiers)

        metadata = license_public_metadata({})
        invalid_metadata = license_public_metadata({'configured': True, 'expires_at': 'invalid'})

        self.assertEqual(metadata['instance_id'], expected)
        self.assertEqual(invalid_metadata['instance_id'], expected)
        self.assertFalse(any(key in metadata for key in self.identifiers))
