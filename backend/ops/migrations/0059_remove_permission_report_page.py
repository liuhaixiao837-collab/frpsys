from django.db import migrations


PERMISSION_REPORT_PAGE_CODE = 'page.permission_report.view'
PERMISSION_POLICY_PAGE_CODE = 'page.permission_policies.view'


def remove_permission_report_page(apps, schema_editor):
    """清理曾短暂创建的独立权限报表页面及其策略规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=PERMISSION_REPORT_PAGE_CODE).delete()
    MenuNode.objects.filter(code=PERMISSION_REPORT_PAGE_CODE).delete()
    MenuNode.objects.filter(code=PERMISSION_POLICY_PAGE_CODE).update(sort_order=4)


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0058_permission_report_and_user_import'),
    ]

    operations = [
        migrations.RunPython(remove_permission_report_page, migrations.RunPython.noop),
    ]
