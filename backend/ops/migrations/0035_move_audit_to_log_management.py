from django.db import migrations


LOG_MENU_CODE = 'menu.logs'
PLATFORM_MENU_CODE = 'menu.platform'
AUDIT_PAGE_CODE = 'page.audit.view'


def move_audit_to_log_management(apps, schema_editor):
    """创建日志管理菜单，将审计日志及已有授权迁移到新权限链。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    log_menu, _created = MenuNode.objects.update_or_create(
        code=LOG_MENU_CODE,
        defaults={
            'parent': None,
            'node_type': 'group',
            'name': '日志管理',
            'path': '',
            'icon': 'FileText',
            'sidebar': True,
            'aliases': [],
            'sort_order': 4,
            'is_active': True,
        },
    )
    MenuNode.objects.filter(code=AUDIT_PAGE_CODE).update(parent=log_menu, sort_order=1)

    for policy in PermissionPolicy.objects.all().iterator():
        effects = dict(
            PermissionRule.objects.filter(
                policy=policy,
                permission_code__in=[PLATFORM_MENU_CODE, AUDIT_PAGE_CODE],
            ).values_list('permission_code', 'effect')
        )
        effect = (
            'allow'
            if effects.get(PLATFORM_MENU_CODE) == 'allow' and effects.get(AUDIT_PAGE_CODE) == 'allow'
            else 'deny'
        )
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=LOG_MENU_CODE,
            defaults={'effect': effect},
        )


def move_audit_back_to_platform(apps, schema_editor):
    """回退时把审计日志放回平台管理并移除日志管理权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    platform_menu = MenuNode.objects.filter(code=PLATFORM_MENU_CODE).first()
    if platform_menu:
        MenuNode.objects.filter(code=AUDIT_PAGE_CODE).update(parent=platform_menu, sort_order=2)
    PermissionRule.objects.filter(permission_code=LOG_MENU_CODE).delete()
    MenuNode.objects.filter(code=LOG_MENU_CODE).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0034_delete_agent_remove_aiassistantattachment_message_and_more'),
    ]

    operations = [
        migrations.RunPython(move_audit_to_log_management, move_audit_back_to_platform),
    ]
