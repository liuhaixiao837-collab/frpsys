from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from ops.models import Organization, UserProfile


class OrganizationMemberTests(TestCase):
    """验证部门递归人数统计和默认组织成员限制。"""

    def setUp(self):
        """创建默认组织、父子部门和分布在不同层级的用户。"""
        self.root = Organization.objects.filter(is_default=True).first()
        if not self.root:
            self.root = Organization.objects.create(
                name='默认组织', slug='default-org-test', org_type='company', is_default=True,
            )
        self.parent = Organization.objects.create(
            name='测试部门', slug='parent-department-test', parent=self.root,
        )
        self.child = Organization.objects.create(
            name='测试1部门', slug='child-department-test', parent=self.parent,
        )
        self.admin = User.objects.create_superuser(
            username='admin', email='admin@example.com', password='StrongPassword123!',
        )
        UserProfile.objects.create(user=self.admin, organization=self.root, role='admin')
        self.parent_user = User.objects.create_user(username='parent-user', password='StrongPassword123!')
        UserProfile.objects.create(user=self.parent_user, organization=self.parent, role='member')
        self.child_user = User.objects.create_user(username='child-user', password='StrongPassword123!')
        UserProfile.objects.create(user=self.child_user, organization=self.child, role='member')
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def test_tree_member_count_includes_descendant_departments(self):
        """父部门应累计下级部门用户，默认组织应统计系统全部用户。"""
        response = self.client.get('/api/v1/orgs/tree/')

        self.assertEqual(response.status_code, 200, response.json())
        rows = {item['name']: item for item in response.json()['items']}
        self.assertEqual(rows['默认组织']['member_count'], 3)
        self.assertEqual(rows['测试部门']['member_count'], 2)
        self.assertEqual(rows['测试1部门']['member_count'], 1)

    def test_default_organization_rejects_adding_member(self):
        """默认组织成员接口不得接收新增或迁入用户请求。"""
        response = self.client.post(
            f'/api/v1/orgs/{self.root.id}/members/',
            {'user_id': self.child_user.id},
            format='json',
        )

        self.assertEqual(response.status_code, 400, response.json())
        self.child_user.profile.refresh_from_db()
        self.assertEqual(self.child_user.profile.organization_id, self.child.id)

    def test_default_organization_rejects_creating_user(self):
        """用户新增接口不得把普通用户直接创建到默认组织。"""
        response = self.client.post('/api/v1/users/', {
            'username': 'root-user',
            'password': 'StrongPassword123!',
            'department_id': self.root.id,
            'is_active': False,
        }, format='json')

        self.assertEqual(response.status_code, 400, response.json())
        self.assertFalse(User.objects.filter(username='root-user').exists())
