from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import PlatformLoginSession
from ops.services.tokens import issue_pair
from ops.views import SystemStatusView


class SystemStatusApiTests(TestCase):
    """验证系统状态接口的权限声明和响应契约。"""

    def setUp(self):
        """创建管理员客户端供系统状态接口测试使用。"""
        self.admin = User.objects.create_superuser(
            username='admin',
            email='system-status@example.com',
            password='StrongPassword123!',
        )
        self.client = APIClient()

    def test_system_status_declares_database_page_permission(self):
        """系统状态接口必须显式绑定数据库中的页面权限代码。"""
        self.assertEqual(SystemStatusView.permission_code, 'page.system_status.view')

    def test_system_status_requires_authentication_and_returns_all_metrics(self):
        """未登录请求必须拒绝，管理员可获得完整指标结构。"""
        anonymous = self.client.get('/api/v1/system-status/')
        self.client.force_authenticate(self.admin)
        payload = {
            'collected_at': '2026-07-24T00:00:00Z',
            'cpu': {'percent': 12.5, 'physical_cores': 4, 'logical_cores': 8},
            'memory': {'percent': 45.2, 'used_bytes': 1, 'total_bytes': 2},
            'disk': {'percent': 50.0, 'used_bytes': 3, 'total_bytes': 6},
            'network': {'bytes_sent': 10, 'bytes_received': 20},
            'concurrency': {'users': 2, 'sessions': 3},
            'runtime': {'hostname': 'test-host'},
        }
        with patch('ops.views.collect_system_status', return_value=payload):
            response = self.client.get('/api/v1/system-status/')

        self.assertIn(anonymous.status_code, [401, 403])
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), payload)

    def test_platform_login_is_counted_and_logout_revokes_session(self):
        """平台 JWT 登录必须计入在线用户指标，主动退出后立即撤销会话。"""
        tokens = issue_pair(self.admin)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {tokens['access']}")

        response = self.client.get('/api/v1/system-status/')

        self.assertEqual(response.status_code, 200, response.json())
        self.assertEqual(response.json()['concurrency'], {'users': 1, 'sessions': 1})
        logout = self.client.post('/api/v1/auth/logout', {}, format='json')
        self.assertEqual(logout.status_code, 204)
        self.assertFalse(PlatformLoginSession.objects.filter(revoked_at=None).exists())

    def test_runtime_lists_only_used_national_cryptography(self):
        """运行环境必须按功能列出实际使用的 SM2、SM3 和 SM4 算法及说明。"""
        self.client.force_authenticate(self.admin)

        response = self.client.get('/api/v1/system-status/')

        self.assertEqual(response.status_code, 200, response.json())
        cryptography = response.json()['runtime']['national_cryptography']
        self.assertEqual(cryptography, [
            {
                'feature': 'Licence 数字签名与验签',
                'algorithm': 'SM2',
                'description': '验证 Licence 来源并防止授权内容被篡改',
            },
            {
                'feature': '数据摘要与完整性校验',
                'algorithm': 'SM3',
                'description': '用于 Licence 签名摘要、实例 ID，以及用户手机号等加密数据的完整性校验',
            },
            {
                'feature': '短信验证码安全校验',
                'algorithm': 'SM3',
                'description': '使用带密钥 SM3-HMAC 保护手机号查询索引、短信验证码和登录挑战摘要',
            },
            {
                'feature': '用户隐私信息加密',
                'algorithm': 'SM4',
                'description': '保护用户手机号和 OTP 等可回读隐私信息',
            },
            {
                'feature': '平台敏感配置加密',
                'algorithm': 'SM4',
                'description': '保护邮箱密码、短信密钥和其他平台凭据',
            },
            {
                'feature': '短信登录敏感数据保护',
                'algorithm': 'SM4',
                'description': '加密保存用户手机号和阿里云短信网关 AccessKey Secret',
            },
            {
                'feature': 'Licence 数据安全存储',
                'algorithm': 'SM4',
                'description': '加密保存导入的 Licence 原文',
            },
            {
                'feature': 'Licence 时间保护数据',
                'algorithm': 'SM4',
                'description': '加密保存可信时间和回拨锁定状态',
            },
        ])
        self.assertEqual({item['algorithm'] for item in cryptography}, {'SM2', 'SM3', 'SM4'})
