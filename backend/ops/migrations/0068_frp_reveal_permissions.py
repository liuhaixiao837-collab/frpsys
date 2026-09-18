from django.db import migrations


FRP_SECRET_PAGES = (
    'page.security.frp_servers.view',
    'page.security.frp_agents.view',
)


def add_frp_reveal_permissions(apps, schema_editor):
    """为 FRP 密码查看增加独立权限，并为现有策略默认继承页面权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for page_code in FRP_SECRET_PAGES:
        page = MenuNode.objects.filter(code=page_code).first()
        if not page:
            continue
        MenuAction.objects.update_or_create(
            page=page,
            code='reveal',
            defaults={'name': '查看敏感信息', 'sort_order': 20, 'is_active': True},
        )
        permission_code = page_code.removesuffix('.view') + '.reveal'
        for policy in PermissionPolicy.objects.all().iterator():
            page_rule = PermissionRule.objects.filter(policy=policy, permission_code=page_code).first()
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=permission_code,
                defaults={'effect': page_rule.effect if page_rule else 'deny'},
            )


def remove_frp_reveal_permissions(apps, schema_editor):
    """回滚 FRP 密码查看权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    for page_code in FRP_SECRET_PAGES:
        permission_code = page_code.removesuffix('.view') + '.reveal'
        PermissionRule.objects.filter(permission_code=permission_code).delete()
        page = MenuNode.objects.filter(code=page_code).first()
        if page:
            MenuAction.objects.filter(page=page, code='reveal').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0067_frp_permissions'),
    ]

    operations = [
        migrations.RunPython(add_frp_reveal_permissions, remove_frp_reveal_permissions),
    ]
