from django.db import migrations


PLATFORM_MENU_CODE = 'menu.platform'
SYSTEM_STATUS_PAGE_CODE = 'page.system_status.view'
DEFAULT_SETTINGS = {
    'security.login_blacklist': (
        {'enabled': False, 'entries': []},
        '登录来源 IP 黑名单',
    ),
    'license.management': (
        {'configured': False},
        '平台 Licence 授权配置',
    ),
}


def add_access_license_and_system_status(apps, schema_editor):
    """新增访问黑名单、Licence 默认设置和系统状态页面权限。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for key, (value, description) in DEFAULT_SETTINGS.items():
        SystemSetting.objects.get_or_create(
            key=key,
            defaults={
                'organization': None,
                'value': value,
                'description': description,
            },
        )

    platform_menu = MenuNode.objects.get(code=PLATFORM_MENU_CODE)
    MenuNode.objects.update_or_create(
        code=SYSTEM_STATUS_PAGE_CODE,
        defaults={
            'parent': platform_menu,
            'node_type': 'page',
            'name': '系统状态',
            'path': '/settings/system-status',
            'icon': 'Activity',
            'sidebar': True,
            'aliases': [],
            'sort_order': 3,
            'is_active': True,
        },
    )
    for policy in PermissionPolicy.objects.all().iterator():
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=SYSTEM_STATUS_PAGE_CODE,
            defaults={'effect': 'deny'},
        )


def remove_access_license_and_system_status(apps, schema_editor):
    """回退时删除本次新增设置、系统状态页面及其权限规则。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=SYSTEM_STATUS_PAGE_CODE).delete()
    MenuNode.objects.filter(code=SYSTEM_STATUS_PAGE_CODE).delete()
    SystemSetting.objects.filter(key__in=DEFAULT_SETTINGS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0040_user_menu_order_preference'),
    ]

    operations = [
        migrations.RunPython(add_access_license_and_system_status, remove_access_license_and_system_status),
    ]
