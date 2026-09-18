from django.db import migrations


USER_PAGE_CODE = 'page.admin_users.view'
USER_IMPORT_CODE = 'page.admin_users.import'


def add_user_import_permission(apps, schema_editor):
    """新增用户导入操作，并为现有策略补齐默认拒绝。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    user_page = MenuNode.objects.get(code=USER_PAGE_CODE)
    MenuAction.objects.update_or_create(
        page=user_page,
        code='import',
        defaults={'name': '导入', 'sort_order': 6, 'is_active': True},
    )
    PermissionRule.objects.bulk_create([
        PermissionRule(policy=policy, permission_code=USER_IMPORT_CODE, effect='deny')
        for policy in PermissionPolicy.objects.all().iterator()
        if not PermissionRule.objects.filter(policy=policy, permission_code=USER_IMPORT_CODE).exists()
    ])


def remove_user_import_permission(apps, schema_editor):
    """回滚用户导入操作和相关策略规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=USER_IMPORT_CODE).delete()
    user_page = MenuNode.objects.filter(code=USER_PAGE_CODE).first()
    if user_page:
        MenuAction.objects.filter(page=user_page, code='import').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0057_user_report_export_permission'),
    ]

    operations = [
        migrations.RunPython(add_user_import_permission, remove_user_import_permission),
    ]
