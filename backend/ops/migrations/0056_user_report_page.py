from django.db import migrations


USER_MANAGEMENT_MENU_CODE = 'menu.user_management'
USER_REPORT_PAGE_CODE = 'page.admin_user_report.view'
PERMISSION_POLICY_PAGE_CODE = 'page.permission_policies.view'


def add_user_report_page(apps, schema_editor):
    """新增用户报表菜单，并为已有权限策略补齐默认拒绝规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    parent = MenuNode.objects.get(code=USER_MANAGEMENT_MENU_CODE)
    MenuNode.objects.update_or_create(
        code=USER_REPORT_PAGE_CODE,
        defaults={
            'parent': parent,
            'node_type': 'page',
            'name': '用户报表',
            'path': '/admin/user-report',
            'icon': 'ChartSpline',
            'sidebar': True,
            'aliases': [],
            'sort_order': 3,
            'is_active': True,
        },
    )
    MenuNode.objects.filter(code=PERMISSION_POLICY_PAGE_CODE).update(sort_order=4)
    PermissionRule.objects.bulk_create([
        PermissionRule(policy=policy, permission_code=USER_REPORT_PAGE_CODE, effect='deny')
        for policy in PermissionPolicy.objects.all().iterator()
        if not PermissionRule.objects.filter(
            policy=policy,
            permission_code=USER_REPORT_PAGE_CODE,
        ).exists()
    ])


def remove_user_report_page(apps, schema_editor):
    """回滚用户报表菜单、策略规则和原权限策略排序。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=USER_REPORT_PAGE_CODE).delete()
    MenuNode.objects.filter(code=USER_REPORT_PAGE_CODE).delete()
    MenuNode.objects.filter(code=PERMISSION_POLICY_PAGE_CODE).update(sort_order=3)


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0055_notification_recipient_rate_limits'),
    ]

    operations = [
        migrations.RunPython(add_user_report_page, remove_user_report_page),
    ]
