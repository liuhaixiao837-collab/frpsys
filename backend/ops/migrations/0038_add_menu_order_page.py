from django.db import migrations


PLATFORM_MENU_CODE = 'menu.platform'
MENU_ORDER_PAGE_CODE = 'page.menu_order.view'
MENU_ORDER_ACTION_CODE = 'page.menu_order.update'


def add_menu_order_page(apps, schema_editor):
    """在平台管理中新增菜单排序页面和保存排序权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    platform_menu = MenuNode.objects.get(code=PLATFORM_MENU_CODE)
    page, _created = MenuNode.objects.update_or_create(
        code=MENU_ORDER_PAGE_CODE,
        defaults={
            'parent': platform_menu,
            'node_type': 'page',
            'name': '菜单排序',
            'path': '/settings/menu-order',
            'icon': 'ListOrdered',
            'sidebar': True,
            'aliases': [],
            'sort_order': 2,
            'is_active': True,
        },
    )
    MenuAction.objects.update_or_create(
        page=page,
        code='update',
        defaults={
            'name': '保存排序',
            'sort_order': 1,
            'is_active': True,
        },
    )

    for policy in PermissionPolicy.objects.all().iterator():
        for permission_code in [MENU_ORDER_PAGE_CODE, MENU_ORDER_ACTION_CODE]:
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=permission_code,
                defaults={'effect': 'deny'},
            )


def remove_menu_order_page(apps, schema_editor):
    """回退时删除菜单排序页面及其策略规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(
        permission_code__in=[MENU_ORDER_PAGE_CODE, MENU_ORDER_ACTION_CODE],
    ).delete()
    MenuNode.objects.filter(code=MENU_ORDER_PAGE_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0037_reorganize_bastion_menus'),
    ]

    operations = [
        migrations.RunPython(add_menu_order_page, remove_menu_order_page),
    ]
