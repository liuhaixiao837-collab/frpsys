from django.db import migrations


OLD_MENU_CODE = 'menu.infrastructure'
CONSOLE_MENU_CODE = 'menu.console'

GROUPS = [
    {
        'code': 'menu.audit_management',
        'name': '审计管理',
        'icon': 'Search',
        'path': '',
        'pages': [
            ('page.bastion.command_audit.view', '命令审计'),
            ('page.bastion.session_history.view', '会话历史'),
            ('page.bastion.recordings.view', '录像列表'),
            ('page.bastion.audit_reports.view', '审计报表'),
            ('page.bastion.online_sessions.view', '在线会话'),
            ('page.bastion.command_rules.view', '命令规则'),
        ],
    },
    {
        'code': 'menu.file_transfer',
        'name': '文件传输',
        'icon': 'Send',
        'path': '',
        'pages': [
            ('page.bastion.transfer_mine.view', '我的传输'),
            ('page.bastion.transfer_approvals.view', '传输审批'),
            ('page.bastion.report_center.view', '传输报表'),
            ('page.bastion.transfer_approval_history.view', '审批历史'),
            ('page.bastion.export_tasks.view', '导出管理'),
        ],
    },
    {
        'code': 'menu.asset_management',
        'name': '资产管理',
        'icon': 'Server',
        'path': '',
        'pages': [
            ('page.bastion.accounts.view', '目标账号'),
            ('page.bastion.assets.view', '资产列表'),
        ],
    },
    {
        'code': CONSOLE_MENU_CODE,
        'name': '控制台',
        'icon': 'LayoutDashboard',
        'path': '/bastion/assets',
        'pages': [
            ('page.bastion.settings.view', '堡垒机设置'),
            ('page.bastion.authz.view', '资产授权'),
        ],
    },
    {
        'code': 'menu.work_order_management',
        'name': '工单管理',
        'icon': 'Workflow',
        'path': '',
        'pages': [
            ('page.bastion.approval_flows.view', '审批流管理'),
        ],
    },
]

TRAILING_GROUP_ORDERS = {
    'menu.user_management': 6,
    'menu.platform': 7,
    'menu.logs': 8,
}

ORIGINAL_PAGE_ORDER = [
    'page.bastion.assets.view',
    'page.bastion.accounts.view',
    'page.bastion.authz.view',
    'page.bastion.approval_flows.view',
    'page.bastion.command_rules.view',
    'page.bastion.online_sessions.view',
    'page.bastion.session_history.view',
    'page.bastion.command_audit.view',
    'page.bastion.recordings.view',
    'page.bastion.audit_reports.view',
    'page.bastion.transfer_mine.view',
    'page.bastion.transfer_approvals.view',
    'page.bastion.transfer_approval_history.view',
    'page.bastion.report_center.view',
    'page.bastion.export_tasks.view',
    'page.bastion.settings.view',
]


def reorganize_bastion_menus(apps, schema_editor):
    """拆分堡垒机菜单，并为现有策略补齐新的父级菜单权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    console = MenuNode.objects.get(code=OLD_MENU_CODE)
    console.code = CONSOLE_MENU_CODE
    console.name = '控制台'
    console.icon = 'LayoutDashboard'
    console.path = '/bastion/assets'
    console.sort_order = 4
    console.save(update_fields=['code', 'name', 'icon', 'path', 'sort_order', 'updated_at'])

    groups = {CONSOLE_MENU_CODE: console}
    for group_order, group_data in enumerate(GROUPS, start=1):
        if group_data['code'] == CONSOLE_MENU_CODE:
            group = console
        else:
            group, _created = MenuNode.objects.update_or_create(
                code=group_data['code'],
                defaults={
                    'parent': None,
                    'node_type': 'group',
                    'name': group_data['name'],
                    'path': group_data['path'],
                    'icon': group_data['icon'],
                    'sidebar': True,
                    'aliases': [],
                    'sort_order': group_order,
                    'is_active': True,
                },
            )
        groups[group_data['code']] = group
        for page_order, (page_code, page_name) in enumerate(group_data['pages'], start=1):
            MenuNode.objects.filter(code=page_code).update(
                parent=group,
                name=page_name,
                sort_order=page_order,
            )

    for code, sort_order in TRAILING_GROUP_ORDERS.items():
        MenuNode.objects.filter(code=code).update(sort_order=sort_order)

    page_codes_by_group = {
        group_data['code']: [page_code for page_code, _page_name in group_data['pages']]
        for group_data in GROUPS
    }
    relevant_codes = [
        OLD_MENU_CODE,
        *[page_code for page_codes in page_codes_by_group.values() for page_code in page_codes],
    ]
    for policy in PermissionPolicy.objects.all().iterator():
        effects = dict(
            PermissionRule.objects.filter(
                policy=policy,
                permission_code__in=relevant_codes,
            ).values_list('permission_code', 'effect')
        )
        old_parent_allowed = effects.get(OLD_MENU_CODE) == 'allow'
        for group_code, page_codes in page_codes_by_group.items():
            group_allowed = old_parent_allowed and any(effects.get(code) == 'allow' for code in page_codes)
            PermissionRule.objects.update_or_create(
                policy=policy,
                permission_code=group_code,
                defaults={'effect': 'allow' if group_allowed else 'deny'},
            )
        PermissionRule.objects.filter(policy=policy, permission_code=OLD_MENU_CODE).delete()


def restore_bastion_menu(apps, schema_editor):
    """回退时恢复原堡垒机菜单、页面名称和父级权限。"""
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    console = MenuNode.objects.get(code=CONSOLE_MENU_CODE)
    for page_order, page_code in enumerate(ORIGINAL_PAGE_ORDER, start=1):
        MenuNode.objects.filter(code=page_code).update(parent=console, sort_order=page_order)
    MenuNode.objects.filter(code='page.bastion.report_center.view').update(name='报表中心')

    new_group_codes = [group_data['code'] for group_data in GROUPS]
    for policy in PermissionPolicy.objects.all().iterator():
        effects = dict(
            PermissionRule.objects.filter(
                policy=policy,
                permission_code__in=new_group_codes,
            ).values_list('permission_code', 'effect')
        )
        PermissionRule.objects.update_or_create(
            policy=policy,
            permission_code=OLD_MENU_CODE,
            defaults={'effect': 'allow' if any(effect == 'allow' for effect in effects.values()) else 'deny'},
        )
        PermissionRule.objects.filter(
            policy=policy,
            permission_code__in=new_group_codes,
        ).delete()

    MenuNode.objects.filter(
        code__in=[code for code in new_group_codes if code != CONSOLE_MENU_CODE],
    ).delete()
    console.code = OLD_MENU_CODE
    console.name = '堡垒机'
    console.icon = 'Vault'
    console.path = ''
    console.sort_order = 1
    console.save(update_fields=['code', 'name', 'icon', 'path', 'sort_order', 'updated_at'])
    for code, sort_order in {'menu.user_management': 2, 'menu.platform': 3, 'menu.logs': 4}.items():
        MenuNode.objects.filter(code=code).update(sort_order=sort_order)


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0036_split_user_and_system_logs'),
    ]

    operations = [
        migrations.RunPython(reorganize_bastion_menus, restore_bastion_menu),
    ]
