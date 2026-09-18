from django.db import migrations


GROUP_CODE = 'menu.security.frp'
PAGES = (
    ('page.security.frp_servers.view', 'FRP 服务端', '/security/frp/servers', 'Server', 1, (
        ('create', '新增', 1), ('update', '编辑', 2), ('delete', '删除', 3),
        ('test', '连通测试', 4), ('sync_runtime', '同步客户端', 5), ('disable', '禁用或启用', 6),
    )),
    ('page.security.frp_agents.view', 'frpc 客户端', '/security/frp/agents', 'MonitorCog', 2, (
        ('create', '新增', 1), ('update', '编辑', 2), ('delete', '删除', 3),
        ('approve', '审核通过', 4), ('reject', '审核拒绝', 5), ('test', '管理接口测试', 6),
        ('sync_proxies', '同步隧道', 7), ('add_proxy', '新增隧道', 8),
        ('view_proxies', '查看隧道', 9), ('disable', '禁用或启用', 10),
    )),
    ('page.security.frp_proxies.view', 'FRP 隧道', '/security/frp/proxies', 'Cable', 3, (
        ('create', '新增', 1), ('update', '编辑', 2), ('delete', '删除', 3),
        ('test', '连通测试', 4), ('disable', '禁用或启用', 5),
    )),
    ('page.security.frp_audits.view', 'FRP 审计', '/security/frp/audits', 'FileClock', 4, ()),
    ('page.security.frp_reports.view', 'FRP 报表', '/security/frp/reports', 'ChartSpline', 5, ()),
)


def add_frp_permissions(apps, schema_editor):
    """新增 FRP 菜单、页面及操作权限，并为现有策略默认拒绝。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    group, _created = MenuNode.objects.update_or_create(
        code=GROUP_CODE,
        defaults={
            'parent': None,
            'node_type': 'group',
            'name': 'FRP 管理',
            'path': '',
            'icon': 'Cable',
            'sidebar': True,
            'aliases': [],
            'sort_order': 9,
            'is_active': True,
        },
    )
    permission_codes = [GROUP_CODE]
    for code, name, path, icon, sort_order, actions in PAGES:
        page, _created = MenuNode.objects.update_or_create(
            code=code,
            defaults={
                'parent': group,
                'node_type': 'page',
                'name': name,
                'path': path,
                'icon': icon,
                'sidebar': True,
                'aliases': [],
                'sort_order': sort_order,
                'is_active': True,
            },
        )
        MenuAction.objects.filter(page=page).delete()
        MenuAction.objects.bulk_create([
            MenuAction(page=page, code=action_code, name=action_name, sort_order=action_order, is_active=True)
            for action_code, action_name, action_order in actions
        ])
        permission_codes.append(code)
        permission_codes.extend(f'{code.removesuffix(".view")}.{action_code}' for action_code, _name, _order in actions)

    for policy in PermissionPolicy.objects.all().iterator():
        for permission_code in permission_codes:
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=permission_code,
                defaults={'effect': 'deny'},
            )

    page_codes = [page[0] for page in PAGES]
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        root_order = source.get('__root__', [])
        if not isinstance(root_order, list):
            root_order = []
        source['__root__'] = list(dict.fromkeys([*root_order, GROUP_CODE]))
        source[GROUP_CODE] = page_codes
        preference.order_data = source
        preference.save(update_fields=['order_data', 'updated_at'])


def remove_frp_permissions(apps, schema_editor):
    """回滚时移除 FRP 权限目录、策略规则和个人排序引用。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuPreference = apps.get_model('ops', 'UserMenuOrderPreference')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    PermissionRule.objects.filter(permission_code=GROUP_CODE).delete()
    PermissionRule.objects.filter(permission_code__startswith='page.security.frp_').delete()
    MenuNode.objects.filter(code=GROUP_CODE).delete()
    for preference in MenuPreference.objects.all().iterator():
        source = dict(preference.order_data) if isinstance(preference.order_data, dict) else {}
        source['__root__'] = [code for code in source.get('__root__', []) if code != GROUP_CODE]
        source.pop(GROUP_CODE, None)
        preference.order_data = source
        preference.save(update_fields=['order_data', 'updated_at'])


class Migration(migrations.Migration):
    """把 FRP 管理接入数据库菜单和权限策略目录。"""

    dependencies = [('ops', '0066_llm_provider_setting')]

    operations = [migrations.RunPython(add_frp_permissions, remove_frp_permissions)]
