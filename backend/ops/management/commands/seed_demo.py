from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from ops.models import Organization, Role, UserProfile


ROLE_SPECS = [
    ('owner', '所有者', '平台最高身份标签。功能权限仍由权限策略授予。', 40),
    ('admin', '管理员', '平台管理身份标签。功能权限仍由权限策略授予。', 30),
    ('sre', 'SRE', '日常运维身份标签。功能权限仍由权限策略授予。', 20),
    ('member', '成员', '普通成员身份标签。功能权限仍由权限策略授予。', 20),
    ('viewer', '观察者', '观察者身份标签。功能权限仍由权限策略授予。', 10),
    ('readonly', '只读', '只读身份标签。功能权限仍由权限策略授予。', 10),
]


class Command(BaseCommand):
    """创建本地启动和平台接口测试所需的最小基础数据。"""

    help = '创建最小组织、身份标签和本地管理员数据'

    def handle(self, *args, **options):
        """幂等创建默认组织、预置身份标签和 admin 用户。"""
        root, _ = Organization.objects.update_or_create(
            slug='default-org',
            defaults={
                'name': '默认组织',
                'description': '公司根组织，所有部门默认挂载到此节点。',
                'region': '中国',
                'parent': None,
                'org_type': 'company',
                'is_default': True,
                'is_active': True,
            },
        )
        Organization.objects.exclude(pk=root.pk).filter(parent__isnull=True).update(
            parent=root,
            org_type='department',
            is_default=False,
        )
        for code, name, description, rank in ROLE_SPECS:
            Role.objects.update_or_create(
                code=code,
                defaults={
                    'name': name,
                    'description': description,
                    'rank': rank,
                    'is_system': True,
                    'is_active': True,
                },
            )

        admin, created = User.objects.get_or_create(
            username='admin',
            defaults={'is_staff': True, 'is_superuser': True, 'is_active': True},
        )
        admin.is_staff = True
        admin.is_superuser = True
        admin.is_active = True
        if created or not admin.has_usable_password():
            admin.set_password('admin123')
        admin.save()
        UserProfile.objects.update_or_create(
            user=admin,
            defaults={'organization': root, 'role': 'admin', 'title': '平台管理员'},
        )
        self.stdout.write(self.style.SUCCESS('最小基础数据创建完成'))
