from django.db import migrations


TEST_ACTIONS = [
    ('test_email', '测试邮件'),
    ('test_sms', '测试短信'),
]


def create_notification_test_permissions(apps, schema_editor):
    """为平台设置增加邮件和短信测试操作，并为现有策略补齐默认拒绝规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    page = MenuNode.objects.filter(code='page.settings.view').first()
    if not page:
        return
    for offset, (code, name) in enumerate(TEST_ACTIONS, start=5):
        MenuAction.objects.update_or_create(
            page=page,
            code=code,
            defaults={'name': name, 'sort_order': offset, 'is_active': True},
        )
        permission_code = f'page.settings.{code}'
        PermissionRule.objects.bulk_create([
            PermissionRule(policy=policy, permission_code=permission_code, effect='deny')
            for policy in PermissionPolicy.objects.all().iterator()
            if not PermissionRule.objects.filter(policy=policy, permission_code=permission_code).exists()
        ])


def remove_notification_test_permissions(apps, schema_editor):
    """回滚时删除新增操作及其对应策略规则。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    codes = [f'page.settings.{code}' for code, _name in TEST_ACTIONS]
    PermissionRule.objects.filter(permission_code__in=codes).delete()
    page = MenuNode.objects.filter(code='page.settings.view').first()
    if page:
        MenuAction.objects.filter(page=page, code__in=[code for code, _name in TEST_ACTIONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0053_notification_delivery_setting'),
    ]

    operations = [
        migrations.RunPython(create_notification_test_permissions, remove_notification_test_permissions),
    ]
