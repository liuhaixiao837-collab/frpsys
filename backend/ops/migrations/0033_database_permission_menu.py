from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


MENU_GROUPS = [
    {
        'code': 'menu.infrastructure', 'name': '堡垒机', 'icon': 'Vault',
        'pages': [
            ('page.bastion.assets.view', '资产列表', '/bastion/assets', 'Server', [
                ('/bastion/assets/:id', '资产详情'),
                ('/bastion/web-terminal/:sessionId', 'Web SSH'),
                ('/bastion/web-rdp/:sessionId', 'Web RDP'),
            ], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用'), ('connect', '连接'), ('check', '检测'), ('upload', '上传'), ('download', '下载')]),
            ('page.bastion.accounts.view', '目标账号', '/bastion/accounts', 'Vault', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用')]),
            ('page.bastion.authz.view', '资产授权', '/bastion/authz/rules', 'ShieldCheck', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用')]),
            ('page.bastion.approval_flows.view', '审批流管理', '/bastion/approval/flows', 'Workflow', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用')]),
            ('page.bastion.command_rules.view', '命令规则', '/bastion/command/rules', 'TerminalSquare', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用')]),
            ('page.bastion.online_sessions.view', '在线会话', '/bastion/sessions/online', 'Activity', [], [('disconnect', '断开连接')]),
            ('page.bastion.session_history.view', '会话历史', '/bastion/sessions/history', 'List', [], []),
            ('page.bastion.command_audit.view', '命令审计', '/bastion/audit/commands', 'FileCode2', [], []),
            ('page.bastion.recordings.view', '录像列表', '/bastion/audit/replays', 'Images', [('/bastion/audit/replay/:id', '录像详情')], [('replay', '回放'), ('sync_oss', '同步 OSS')]),
            ('page.bastion.audit_reports.view', '审计报表', '/bastion/audit/reports', 'FileText', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用'), ('download', '下载'), ('generate', '生成报告')]),
            ('page.bastion.transfer_mine.view', '我的传输', '/bastion/transfer/my-tasks', 'Send', [], [('create', '服务器间拷贝'), ('upload', '上传'), ('download', '下载'), ('resubmit', '重新提交'), ('cancel', '取消'), ('delete', '删除')]),
            ('page.bastion.transfer_approvals.view', '传输审批', '/bastion/transfer/approvals', 'ShieldAlert', [], [('approve', '通过'), ('reject', '驳回')]),
            ('page.bastion.transfer_approval_history.view', '审批历史', '/bastion/transfer/approval-history', 'FileClock', [], []),
            ('page.bastion.report_center.view', '报表中心', '/bastion/reports/center', 'ChartSpline', [], [('export', '导出')]),
            ('page.bastion.export_tasks.view', '导出管理', '/bastion/export/tasks', 'DatabaseBackup', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('export', '下载'), ('generate', '重新生成'), ('cancel', '取消')]),
            ('page.bastion.settings.view', '堡垒机设置', '/bastion/settings', 'Settings', [], [('update', '编辑'), ('delete', '删除'), ('cleanup', '清理过期中转')]),
        ],
    },
    {
        'code': 'menu.user_management', 'name': '用户管理', 'icon': 'Users',
        'pages': [
            ('page.admin_users.view', '用户管理', '/admin/users', 'Users', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('disable', '禁用/启用')]),
            ('page.admin_departments.view', '部门管理', '/admin/departments', 'Network', [('/admin/orgs', '组织管理')], [('create', '新增'), ('update', '编辑/成员'), ('delete', '删除')]),
            ('page.permission_policies.view', '权限策略', '/admin/permissions', 'ShieldCheck', [], [('create', '新增/克隆'), ('update', '编辑'), ('delete', '删除')]),
        ],
    },
    {
        'code': 'menu.platform', 'name': '平台管理', 'icon': 'Settings',
        'pages': [
            ('page.settings.view', '平台设置', '/settings', 'Settings', [], [('create', '新增'), ('update', '编辑'), ('delete', '删除'), ('reveal', '查看敏感信息')]),
            ('page.audit.view', '审计日志', '/audit', 'Search', [], []),
        ],
    },
]


def seed_permission_menu(apps, schema_editor):
    MenuNode = apps.get_model('ops', 'PermissionMenuNode')
    MenuAction = apps.get_model('ops', 'PermissionMenuAction')
    PermissionPolicy = apps.get_model('ops', 'PermissionPolicy')
    PermissionRule = apps.get_model('ops', 'PermissionRule')

    all_codes = []
    for group_order, group_data in enumerate(MENU_GROUPS, start=1):
        group = MenuNode.objects.create(
            node_type='group', code=group_data['code'], name=group_data['name'],
            icon=group_data['icon'], sidebar=True, sort_order=group_order,
        )
        all_codes.append(group.code)
        for page_order, page_data in enumerate(group_data['pages'], start=1):
            code, name, path, icon, aliases, actions = page_data
            page = MenuNode.objects.create(
                parent=group, node_type='page', code=code, name=name, path=path,
                icon=icon, sidebar=True, aliases=[{'path': item[0], 'name': item[1]} for item in aliases],
                sort_order=page_order,
            )
            all_codes.append(code)
            prefix = code.removesuffix('.view')
            for action_order, (action_code, action_name) in enumerate(actions, start=1):
                MenuAction.objects.create(
                    page=page, code=action_code, name=action_name, sort_order=action_order,
                )
                all_codes.append(f'{prefix}.{action_code}')

    for policy in PermissionPolicy.objects.all().iterator():
        existing_rules = list(PermissionRule.objects.filter(policy=policy))
        existing = {rule.permission_code: rule.effect for rule in existing_rules if rule.permission_code != '*'}
        wildcard = next((rule.effect for rule in existing_rules if rule.permission_code == '*'), '')
        PermissionRule.objects.bulk_create([
            PermissionRule(policy=policy, permission_code=code, effect=existing.get(code, wildcard or 'deny'))
            for code in all_codes if code not in existing
        ])
        PermissionRule.objects.filter(policy=policy).exclude(permission_code__in=all_codes).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0032_normalize_sm4_sensitive_keys'),
    ]

    operations = [
        migrations.AlterField(
            model_name='permissionrule',
            name='effect',
            field=models.CharField(choices=[('allow', 'Allow'), ('deny', 'Deny')], default='deny', max_length=16),
        ),
        migrations.CreateModel(
            name='PermissionMenuNode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('node_type', models.CharField(choices=[('group', 'Menu group'), ('page', 'Page')], default='page', max_length=16)),
                ('code', models.CharField(max_length=160, unique=True)),
                ('name', models.CharField(max_length=120)),
                ('path', models.CharField(blank=True, max_length=240)),
                ('icon', models.CharField(blank=True, max_length=80)),
                ('sidebar', models.BooleanField(default=True)),
                ('aliases', models.JSONField(blank=True, default=list)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='ops.permissionmenunode')),
            ],
            options={'ordering': ['sort_order', 'id']},
        ),
        migrations.CreateModel(
            name='PermissionMenuAction',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.CharField(max_length=80)),
                ('name', models.CharField(max_length=80)),
                ('description', models.CharField(blank=True, max_length=240)),
                ('sort_order', models.PositiveIntegerField(default=0)),
                ('is_active', models.BooleanField(default=True)),
                ('page', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='actions', to='ops.permissionmenunode')),
            ],
            options={'ordering': ['sort_order', 'id'], 'unique_together': {('page', 'code')}},
        ),
        migrations.AddIndex(model_name='permissionmenunode', index=models.Index(fields=['parent', 'is_active', 'sort_order'], name='ops_perm_menu_parent_idx')),
        migrations.AddIndex(model_name='permissionmenunode', index=models.Index(fields=['node_type', 'is_active'], name='ops_perm_menu_type_idx')),
        migrations.AddIndex(model_name='permissionmenuaction', index=models.Index(fields=['page', 'is_active', 'sort_order'], name='ops_perm_action_page_idx')),
        migrations.RunPython(seed_permission_menu, migrations.RunPython.noop),
    ]
