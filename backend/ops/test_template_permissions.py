from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import Organization, PermissionMenuNode, PermissionPolicy, PermissionRule, UserProfile
from ops.permission_catalog import catalog_payload, required_codes_for_page
from ops.permission_service import clear_permission_cache


EXPECTED_PAGE_ACTIONS = {
    'page.admin_users.view': {'create', 'update', 'delete', 'disable', 'reset_otp', 'import'},
    'page.admin_departments.view': {'create', 'update', 'delete'},
    'page.admin_user_report.view': {'export'},
    'page.permission_policies.view': {'create', 'update', 'delete'},
    'page.settings.view': {'create', 'update', 'delete', 'reveal', 'test_email', 'test_sms'},
    'page.menu_order.view': {'update'},
    'page.system_status.view': set(),
    'page.logs.users.view': {'export'},
    'page.logs.system.view': {'export'},
}


class TemplatePermissionCatalogTests(TestCase):
    """验证模板仅保留登录、用户、权限、平台和日志相关权限目录。"""

    def test_catalog_contains_only_template_groups(self):
        """权限目录必须只包含用户管理、平台管理和日志管理三个一级菜单。"""
        payload = catalog_payload()['items']
        self.assertEqual(
            [group['code'] for group in payload],
            ['menu.user_management', 'menu.platform', 'menu.logs'],
        )
        self.assertFalse(PermissionMenuNode.objects.filter(code__startswith='page.bastion.').exists())

    def test_page_actions_match_template_contract(self):
        """每个模板页面的数据库操作项必须与前端真实按钮契约一致。"""
        actual = {
            node.code: set(node.actions.values_list('code', flat=True))
            for node in PermissionMenuNode.objects.filter(code__in=EXPECTED_PAGE_ACTIONS).prefetch_related('actions')
        }
        self.assertEqual(actual, EXPECTED_PAGE_ACTIONS)

    def test_required_codes_include_database_parent(self):
        """页面权限链必须包含数据库配置的一级菜单权限。"""
        self.assertEqual(
            required_codes_for_page('page.admin_users.view'),
            ['menu.user_management', 'page.admin_users.view'],
        )
        self.assertEqual(
            required_codes_for_page('page.settings.view'),
            ['menu.platform', 'page.settings.view'],
        )
        self.assertEqual(
            required_codes_for_page('page.logs.system.view'),
            ['menu.logs', 'page.logs.system.view'],
        )


class TemplatePermissionApiTests(TestCase):
    """验证模板普通用户只能访问数据库策略明确允许的页面。"""

    def setUp(self):
        """创建普通用户及默认拒绝的用户权限策略。"""
        organization = Organization.objects.first()
        self.user = User.objects.create_user(username='template-user', password='StrongPassword123!')
        UserProfile.objects.create(user=self.user, organization=organization, role='member')
        self.policy = PermissionPolicy.objects.create(
            name='模板用户权限',
            subject_type='user',
            user=self.user,
            status='available',
        )
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def grant(self, code):
        """向当前测试用户策略写入单项允许规则。"""
        PermissionRule.objects.update_or_create(
            policy=self.policy,
            permission_code=code,
            defaults={'effect': 'allow'},
        )
        clear_permission_cache()

    def test_user_log_requires_group_and_page_permissions(self):
        """普通用户必须同时具备日志菜单和用户日志页面权限。"""
        denied = self.client.get('/api/v1/user-logs/')
        self.grant('menu.logs')
        still_denied = self.client.get('/api/v1/user-logs/')
        self.grant('page.logs.users.view')
        allowed = self.client.get('/api/v1/user-logs/')

        self.assertEqual(denied.status_code, 403)
        self.assertEqual(still_denied.status_code, 403)
        self.assertEqual(allowed.status_code, 200)
