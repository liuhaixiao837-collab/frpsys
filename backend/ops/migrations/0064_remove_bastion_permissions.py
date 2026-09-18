from django.db import migrations


BASTION_MENU_CODES = [
    'menu.audit_management',
    'menu.file_transfer',
    'menu.asset_management',
    'menu.console',
    'menu.work_order_management',
]


def remove_bastion_permissions(apps, schema_editor):
    """从模板数据库目录和既有策略中移除全部堡垒机权限。"""
    PermissionMenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    UserMenuOrderPreference = apps.get_model('ops', 'UserMenuOrderPreference')

    PermissionMenuNode.objects.filter(code__startswith='page.bastion.').delete()
    PermissionMenuNode.objects.filter(code__in=BASTION_MENU_CODES).delete()
    PermissionRule.objects.filter(permission_code__startswith='page.bastion.').delete()
    PermissionRule.objects.filter(permission_code__in=BASTION_MENU_CODES).delete()

    for preference in UserMenuOrderPreference.objects.all().iterator():
        cleaned = []
        for group in preference.order_data or []:
            parent_code = str(group.get('parent_code') or '')
            if parent_code in BASTION_MENU_CODES:
                continue
            codes = [
                code for code in group.get('codes', [])
                if code not in BASTION_MENU_CODES and not str(code).startswith('page.bastion.')
            ]
            cleaned.append({'parent_code': parent_code, 'codes': codes})
        if cleaned != preference.order_data:
            preference.order_data = cleaned
            preference.save(update_fields=['order_data', 'updated_at'])


class Migration(migrations.Migration):
    """清理模板不需要的堡垒机菜单、操作权限和个人排序数据。"""

    dependencies = [
        ('ops', '0063_move_audit_log_to_platform_logs'),
    ]

    operations = [
        migrations.RunPython(remove_bastion_permissions, migrations.RunPython.noop),
    ]
