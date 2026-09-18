from django.db import migrations


PLATFORM_MENU_CODE = 'menu.platform'
PAGE_CODE = 'page.system_tools.view'
ACTION_DEFINITIONS = (
    ('ping', '执行 Ping', 1),
    ('telnet', '执行 Telnet', 2),
    ('curl', '执行 Curl', 3),
    ('traceroute', '执行 Traceroute', 4),
    ('mtr', '执行 MTR', 5),
)


def add_platform_tools_page(apps, schema_editor):
    """新增平台工具页面、五项操作权限，并为现有策略默认拒绝。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    platform_menu = MenuNode.objects.get(code=PLATFORM_MENU_CODE)
    page, _created = MenuNode.objects.update_or_create(
        code=PAGE_CODE,
        defaults={
            'parent': platform_menu,
            'node_type': 'page',
            'name': '平台工具',
            'path': '/settings/system-tools',
            'icon': 'Wrench',
            'sidebar': True,
            'aliases': [],
            'sort_order': 4,
            'is_active': True,
        },
    )
    MenuAction.objects.filter(page=page).delete()
    MenuAction.objects.bulk_create([
        MenuAction(page=page, code=code, name=name, sort_order=sort_order, is_active=True)
        for code, name, sort_order in ACTION_DEFINITIONS
    ])

    permission_codes = [PAGE_CODE, *[f'page.system_tools.{code}' for code, _name, _order in ACTION_DEFINITIONS]]
    for policy in PermissionPolicy.objects.all().iterator():
        for permission_code in permission_codes:
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=permission_code,
                defaults={'effect': 'deny'},
            )

    valid_codes = list(
        MenuNode.objects.filter(parent=platform_menu, is_active=True, sidebar=True)
        .order_by('sort_order', 'id')
        .values_list('code', flat=True)
    )
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        current = source.get(PLATFORM_MENU_CODE, [])
        if not isinstance(current, list):
            current = []
        source[PLATFORM_MENU_CODE] = list(dict.fromkeys([
            *[code for code in current if code in valid_codes],
            *valid_codes,
        ]))
        preference.order_data = source
        preference.save(update_fields=['order_data', 'updated_at'])


def remove_platform_tools_page(apps, schema_editor):
    """回滚时移除平台工具目录、规则和个人排序引用。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code__startswith='page.system_tools.').delete()
    MenuNode.objects.filter(code=PAGE_CODE).delete()
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        current = source.get(PLATFORM_MENU_CODE, [])
        if PAGE_CODE not in current:
            continue
        source[PLATFORM_MENU_CODE] = [code for code in current if code != PAGE_CODE]
        preference.order_data = source
        preference.save(update_fields=['order_data', 'updated_at'])


class Migration(migrations.Migration):
    """把平台工具及五项独立执行权限接入数据库权限目录。"""

    dependencies = [('ops', '0064_remove_bastion_permissions')]

    operations = [
        migrations.RunPython(add_platform_tools_page, remove_platform_tools_page),
    ]
