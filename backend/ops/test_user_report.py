from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from ops.models import Organization, PermissionPolicy, PermissionRule, UserProfile
from ops.permission_catalog import required_codes_for_page
from ops.permission_service import clear_permission_cache


class UserReportTests(TestCase):
    """验证用户报表的全局统计口径和独立页面权限。"""

    def setUp(self):
        """创建公司、父子部门和具备不同状态的用户测试数据。"""
        clear_permission_cache()
        self.company = Organization.objects.create(
            name='测试公司', slug='report-company', org_type='company', is_default=True,
        )
        self.department = Organization.objects.create(
            name='研发部', slug='report-development', org_type='department', parent=self.company,
        )
        self.child_department = Organization.objects.create(
            name='平台组', slug='report-platform', org_type='department', parent=self.department,
        )
        self.outside_company = Organization.objects.create(
            name='外部公司', slug='report-outside-company', org_type='company',
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='StrongPassword123!',
        )
        UserProfile.objects.create(user=self.admin, organization=self.company, role='admin')
        self.manager = User.objects.create_user(
            username='manager', password='StrongPassword123!', date_joined=timezone.now() - timedelta(days=1),
        )
        UserProfile.objects.create(
            user=self.manager,
            organization=self.department,
            role='sre',
            otp_bound_at=timezone.now(),
        )
        self.operator = User.objects.create_user(
            username='operator',
            password='StrongPassword123!',
            is_active=False,
            date_joined=timezone.now() - timedelta(days=2),
        )
        UserProfile.objects.create(user=self.operator, organization=self.child_department, role='member')
        self.local_policy = PermissionPolicy.objects.create(
            name='研发策略', subject_type='department', department=self.department,
            organization=self.department, status='available',
        )
        PermissionRule.objects.bulk_create([
            PermissionRule(policy=self.local_policy, permission_code='page.admin_users.view', effect='allow'),
            PermissionRule(policy=self.local_policy, permission_code='page.admin_users.delete', effect='allow'),
            PermissionRule(policy=self.local_policy, permission_code='page.admin_users.update', effect='deny'),
        ])
        self.outside_policy = PermissionPolicy.objects.create(
            name='外部策略', subject_type='department', department=self.outside_company,
            organization=self.outside_company, status='disabled',
        )

    def tearDown(self):
        """清理跨测试进程复用的权限计算缓存。"""
        clear_permission_cache()

    def grant_report_permission(self, user):
        """为普通测试用户授予用户管理菜单和用户报表查看权限。"""
        policy = PermissionPolicy.objects.create(
            name=f'{user.username}-user-report',
            subject_type='user',
            user=user,
            organization=user.profile.organization,
        )
        PermissionRule.objects.bulk_create([
            PermissionRule(policy=policy, permission_code=code, effect='allow')
            for code in required_codes_for_page('page.admin_user_report.view')
        ])
        clear_permission_cache()

    def test_super_admin_receives_complete_user_report(self):
        """超级管理员应看到全部用户及全部业务部门统计。"""
        client = APIClient()
        client.force_authenticate(self.admin)

        response = client.get('/api/v1/user-report/')

        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()
        self.assertEqual(payload['summary']['total_users'], 3)
        self.assertEqual(payload['summary']['active_users'], 2)
        self.assertEqual(payload['summary']['disabled_users'], 1)
        self.assertEqual(payload['summary']['department_count'], 2)
        self.assertEqual(payload['summary']['otp_bound'], 1)
        self.assertEqual(sum(item['value'] for item in payload['registration_trend']), 3)
        permission_statistics = payload['permission_statistics']
        self.assertEqual(permission_statistics['summary']['total_policies'], 2)
        self.assertEqual(permission_statistics['summary']['available_policies'], 1)
        self.assertEqual(permission_statistics['summary']['disabled_policies'], 1)
        self.assertEqual(permission_statistics['summary']['allowed_rules'], 2)
        self.assertEqual(
            permission_statistics['department_authorization_distribution'],
            [
                {'name': '已授权部门', 'value': 1},
                {'name': '未授权部门', 'value': 1},
            ],
        )
        self.assertEqual(
            permission_statistics['authorization_mode_distribution'],
            [
                {'name': '直接授权', 'value': 1},
                {'name': '继承授权', 'value': 1},
            ],
        )
        self.assertEqual(
            next(item['value'] for item in permission_statistics['risk_distribution'] if item['name'] == '删除'),
            1,
        )

    def test_regular_user_with_report_permission_receives_complete_report(self):
        """普通用户获报表页面权限后也应看到系统全部统计数据。"""
        self.grant_report_permission(self.manager)
        client = APIClient()
        client.force_authenticate(self.manager)

        response = client.get('/api/v1/user-report/')

        self.assertEqual(response.status_code, 200, response.json())
        payload = response.json()
        self.assertEqual(payload['summary']['total_users'], 3)
        self.assertEqual(payload['summary']['department_count'], 2)
        self.assertEqual(
            {item['name'] for item in payload['department_distribution']},
            {'测试公司', '研发部', '平台组'},
        )
        permission_departments = {
            item['name'] for item in payload['permission_statistics']['department_distribution']
        }
        self.assertIn('研发部', permission_departments)
        self.assertIn('外部公司', permission_departments)

    def test_user_report_requires_its_page_permission(self):
        """没有用户报表页面权限的普通用户必须被拒绝访问。"""
        client = APIClient()
        client.force_authenticate(self.manager)

        response = client.get('/api/v1/user-report/')

        self.assertEqual(response.status_code, 403)
