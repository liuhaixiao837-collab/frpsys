from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from data_security.sm4 import decrypt, encrypt
from ops.models import Organization, PermissionPolicy, PermissionRule, UserProfile
from ops.permission_service import clear_permission_cache

from .models import FrpAgent, FrpProxy, FrpServer
from .serializers import FrpServerSerializer
from .services import update_proxy_traffic


class FrpMigrationTests(TestCase):
    """验证 FRP 模块在目标平台中的核心接口、加密和解耦结果。"""

    def setUp(self):
        """创建拥有全部权限的管理员及默认组织测试数据。"""
        self.organization = Organization.objects.get(slug='default-org')
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'Password123!')
        UserProfile.objects.create(user=self.user, organization=self.organization, role='admin')
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def create_server(self):
        """创建供接口测试复用的 FRP 服务端。"""
        return FrpServer.objects.create(
            organization=self.organization,
            name='测试服务端',
            server_code='test-frp',
            public_host='127.0.0.1',
        )

    def test_server_secret_uses_sm4(self):
        """确认新写入的 FRP 密码使用目标平台 SM4 保存且不回传明文。"""
        serializer = FrpServerSerializer(data={
            'name': '测试服务端',
            'server_code': 'test-frp',
            'public_host': '127.0.0.1',
            'dashboard_password': 'dashboard-secret',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        server = serializer.save(organization=self.organization)
        self.assertTrue(server.encrypted_dashboard_password.startswith('sm4:v1:'))
        self.assertEqual(decrypt(server.encrypted_dashboard_password), 'dashboard-secret')
        self.assertNotIn('dashboard_password', serializer.data)

    def test_frp_secrets_are_revealed_only_by_dedicated_actions(self):
        """确认服务端与客户端密码只能通过受控解密接口读取。"""
        serializer = FrpServerSerializer(data={
            'name': '敏感配置服务端',
            'server_code': 'secret-frp',
            'public_host': '127.0.0.1',
            'auth_token': 'register-secret',
            'dashboard_password': 'dashboard-secret',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        server = serializer.save(organization=self.organization)
        agent = FrpAgent.objects.create(
            organization=self.organization,
            server=server,
            agent_id='secret-agent',
            fingerprint='secret-agent-fingerprint',
            hostname='frpc-secret',
            encrypted_admin_password=encrypt('agent-secret'),
        )

        server_response = self.client.get(f'/api/v1/security/frp/servers/{server.pk}/reveal/')
        self.assertEqual(server_response.status_code, 200)
        self.assertEqual(server_response.data['secrets']['auth_token'], 'register-secret')
        self.assertEqual(server_response.data['secrets']['dashboard_password'], 'dashboard-secret')

        agent_response = self.client.get(f'/api/v1/security/frp/agents/{agent.pk}/reveal/')
        self.assertEqual(agent_response.status_code, 200)
        self.assertEqual(agent_response.data['secrets']['admin_password'], 'agent-secret')

    def test_agent_model_has_no_bastion_fields(self):
        """确认 FRP 客户端模型不再包含任何堡垒机关联和转入字段。"""
        field_names = {field.name for field in FrpAgent._meta.fields}
        self.assertFalse({'bastion_asset', 'transferred_at', 'transferred_by'} & field_names)
        self.assertFalse({'management_ip', 'os', 'arch', 'version', 'username'} & field_names)

    def test_report_has_no_bastion_metric(self):
        """确认 FRP 报表保留业务指标且不再输出堡垒机绑定数量。"""
        self.create_server()
        response = self.client.get('/api/v1/security/frp/reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['server_count'], 1)
        self.assertNotIn('bound_assets', response.data['summary'])

    def test_traffic_report_tracks_today_and_total(self):
        server = self.create_server()
        agent = FrpAgent.objects.create(
            organization=self.organization,
            server=server,
            agent_id='traffic-agent',
            fingerprint='traffic-agent-fingerprint',
            hostname='frpc-traffic',
            approval_status='approved',
        )
        proxy = FrpProxy.objects.create(
            organization=self.organization,
            server=server,
            agent=agent,
            name='ssh-22',
        )
        update_proxy_traffic(proxy, {'todayTrafficIn': 20 * 1024 * 1024, 'todayTrafficOut': 5 * 1024 * 1024})
        update_proxy_traffic(proxy, {'todayTrafficIn': 25 * 1024 * 1024, 'todayTrafficOut': 7 * 1024 * 1024})
        response = self.client.get('/api/v1/security/frp/traffic-reports/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['summary']['today_traffic_total_bytes'], 32 * 1024 * 1024)
        self.assertEqual(response.data['summary']['traffic_total_bytes'], 32 * 1024 * 1024)
        self.assertEqual(response.data['tunnels'][0]['today_traffic_total_bytes'], 32 * 1024 * 1024)

    def test_agent_registration_keeps_source_behavior(self):
        """确认携带正确注册令牌的 Agent 仍可匿名注册并进入待审核状态。"""
        serializer = FrpServerSerializer(data={
            'name': '注册服务端',
            'server_code': 'register-frp',
            'public_host': '127.0.0.1',
            'auth_token': 'register-token',
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        serializer.save(organization=self.organization)
        anonymous = APIClient()
        response = anonymous.post('/api/v1/security/frp/agent-register/', {
            'server_code': 'register-frp',
            'token': 'register-token',
            'hostname': 'frpc-01',
        }, format='json')
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data['approval_status'], 'pending')
        self.assertEqual(FrpAgent.objects.get().organization, self.organization)

    def test_permission_policy_controls_frp_page_and_actions(self):
        """确认用户管理权限策略可分别控制 FRP 页面查看和新增操作。"""
        operator = User.objects.create_user('frp-operator', password='Password123!')
        UserProfile.objects.create(user=operator, organization=self.organization, role='sre')
        policy = PermissionPolicy.objects.create(
            organization=self.organization,
            name='FRP 只读策略',
            subject_type='user',
            user=operator,
            status='available',
        )
        PermissionRule.objects.create(policy=policy, permission_code='menu.security.frp', effect='allow')
        PermissionRule.objects.create(policy=policy, permission_code='page.security.frp_servers.view', effect='allow')
        clear_permission_cache()
        client = APIClient()
        client.force_authenticate(operator)
        self.assertEqual(client.get('/api/v1/security/frp/servers/').status_code, 200)
        response = client.post('/api/v1/security/frp/servers/', {
            'name': '无权新增',
            'server_code': 'forbidden-create',
            'public_host': '127.0.0.1',
        }, format='json')
        self.assertEqual(response.status_code, 403)
