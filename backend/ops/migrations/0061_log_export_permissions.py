from django.db import migrations


LOG_PAGE_CODES = ('page.logs.users.view', 'page.logs.system.view')


def add_log_export_permissions(apps, schema_editor):
    """为用户日志和系统日志新增独立导出操作权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for page_code in LOG_PAGE_CODES:
        page = MenuNode.objects.get(code=page_code)
        MenuAction.objects.update_or_create(
            page=page,
            code='export',
            defaults={'name': '导出', 'sort_order': 1, 'is_active': True},
        )
        export_code = page_code.removesuffix('.view') + '.export'
        for policy in PermissionPolicy.objects.all().iterator():
            page_rule = PermissionRule.objects.filter(policy=policy, permission_code=page_code).first()
            effect = page_rule.effect if page_rule else 'deny'
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=export_code,
                defaults={'effect': effect},
            )


def remove_log_export_permissions(apps, schema_editor):
    """回滚用户日志和系统日志导出操作权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for page_code in LOG_PAGE_CODES:
        export_code = page_code.removesuffix('.view') + '.export'
        PermissionRule.objects.filter(permission_code=export_code).delete()
        page = MenuNode.objects.filter(code=page_code).first()
        if page:
            MenuAction.objects.filter(page=page, code='export').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0060_sms_login'),
    ]

    operations = [
        migrations.RunPython(add_log_export_permissions, remove_log_export_permissions),
    ]
