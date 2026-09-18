from django.db import migrations


LOG_MENU_CODE = 'menu.logs'
OLD_AUDIT_CODE = 'page.audit.view'
USER_LOG_CODE = 'page.logs.users.view'
SYSTEM_LOG_CODE = 'page.logs.system.view'


def split_log_pages(apps, schema_editor):
    """把旧审计日志页面拆分为用户日志和系统日志页面。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    log_menu = MenuNode.objects.get(code=LOG_MENU_CODE)
    system_log = MenuNode.objects.get(code=OLD_AUDIT_CODE)
    system_log.code = SYSTEM_LOG_CODE
    system_log.name = '系统日志'
    system_log.path = '/logs/system'
    system_log.icon = 'Activity'
    system_log.sort_order = 2
    system_log.save(update_fields=['code', 'name', 'path', 'icon', 'sort_order', 'updated_at'])

    MenuNode.objects.update_or_create(
        code=USER_LOG_CODE,
        defaults={
            'parent': log_menu,
            'node_type': 'page',
            'name': '用户日志',
            'path': '/logs/users',
            'icon': 'Users',
            'sidebar': True,
            'aliases': [],
            'sort_order': 1,
            'is_active': True,
        },
    )

    for policy in PermissionPolicy.objects.all().iterator():
        old_rule = PermissionRule.objects.filter(policy=policy, permission_code=OLD_AUDIT_CODE).first()
        effect = old_rule.effect if old_rule else 'deny'
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=SYSTEM_LOG_CODE,
            defaults={'effect': effect},
        )
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=USER_LOG_CODE,
            defaults={'effect': effect},
        )
        PermissionRule.objects.filter(policy=policy, permission_code=OLD_AUDIT_CODE).delete()


def merge_log_pages(apps, schema_editor):
    """回退时恢复旧审计日志页面和对应权限规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for policy in PermissionPolicy.objects.all().iterator():
        system_rule = PermissionRule.objects.filter(policy=policy, permission_code=SYSTEM_LOG_CODE).first()
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=OLD_AUDIT_CODE,
            defaults={'effect': system_rule.effect if system_rule else 'deny'},
        )
        PermissionRule.objects.filter(
            policy=policy,
            permission_code__in=[USER_LOG_CODE, SYSTEM_LOG_CODE],
        ).delete()

    MenuNode.objects.filter(code=USER_LOG_CODE).delete()
    system_log = MenuNode.objects.filter(code=SYSTEM_LOG_CODE).first()
    if system_log:
        system_log.code = OLD_AUDIT_CODE
        system_log.name = '审计日志'
        system_log.path = '/audit'
        system_log.icon = 'Search'
        system_log.sort_order = 1
        system_log.save(update_fields=['code', 'name', 'path', 'icon', 'sort_order', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0035_move_audit_to_log_management'),
    ]

    operations = [
        migrations.RunPython(split_log_pages, merge_log_pages),
    ]
