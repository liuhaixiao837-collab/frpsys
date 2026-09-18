from django.db import migrations


USER_REPORT_PAGE_CODE = 'page.admin_user_report.view'
USER_REPORT_EXPORT_CODE = 'page.admin_user_report.export'


def add_user_report_export_permission(apps, schema_editor):
    """新增用户报表导出操作，并为已有权限策略补齐默认拒绝规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    page = MenuNode.objects.get(code=USER_REPORT_PAGE_CODE)
    MenuAction.objects.update_or_create(
        page=page,
        code='export',
        defaults={
            'name': '导出',
            'sort_order': 1,
            'is_active': True,
        },
    )
    PermissionRule.objects.bulk_create([
        PermissionRule(policy=policy, permission_code=USER_REPORT_EXPORT_CODE, effect='deny')
        for policy in PermissionPolicy.objects.all().iterator()
        if not PermissionRule.objects.filter(
            policy=policy,
            permission_code=USER_REPORT_EXPORT_CODE,
        ).exists()
    ])


def remove_user_report_export_permission(apps, schema_editor):
    """回滚用户报表导出操作及其权限策略规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=USER_REPORT_EXPORT_CODE).delete()
    page = MenuNode.objects.filter(code=USER_REPORT_PAGE_CODE).first()
    if page:
        MenuAction.objects.filter(page=page, code='export').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0056_user_report_page'),
    ]

    operations = [
        migrations.RunPython(add_user_report_export_permission, remove_user_report_export_permission),
    ]
