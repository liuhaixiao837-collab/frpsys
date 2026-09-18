from django.db import migrations, models
import django.utils.timezone


DEFAULT_ROLES = [
    ('owner', '所有者', '平台最高权限，拥有全部管理能力', ['*'], 40),
    ('admin', '管理员', '用户、部门、角色、配置和运维资源管理', ['users.manage', 'departments.manage', 'roles.manage', 'settings.manage', 'ops.write', 'ops.read'], 30),
    ('sre', 'SRE', '日常运维、告警响应、诊断和 AI RCA', ['ops.write', 'alerts.manage', 'incidents.manage', 'aiops.use', 'ops.read'], 20),
    ('member', '成员', '普通运维成员，可查看和执行常规操作', ['ops.write', 'aiops.use', 'ops.read'], 20),
    ('viewer', '观察者', '只读查看运行状态、告警、日志和报告', ['ops.read'], 10),
    ('readonly', '只读', '最小只读权限', ['ops.read'], 10),
]


def seed_roles(apps, schema_editor):
    Role = apps.get_model('ops', 'Role')
    for code, name, description, permissions, rank in DEFAULT_ROLES:
        Role.objects.update_or_create(
            code=code,
            defaults={
                'name': name,
                'description': description,
                'permissions': permissions,
                'rank': rank,
                'is_system': True,
                'is_active': True,
            },
        )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0008_organization_hierarchy'),
    ]

    operations = [
        migrations.CreateModel(
            name='Role',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('code', models.SlugField(max_length=40, unique=True)),
                ('name', models.CharField(max_length=80)),
                ('description', models.TextField(blank=True)),
                ('permissions', models.JSONField(blank=True, default=list)),
                ('rank', models.PositiveIntegerField(default=10)),
                ('is_system', models.BooleanField(default=False)),
                ('is_active', models.BooleanField(default=True)),
            ],
            options={
                'ordering': ['-rank', 'name'],
            },
        ),
        migrations.AlterField(
            model_name='userprofile',
            name='role',
            field=models.CharField(default='sre', max_length=32),
        ),
        migrations.AddIndex(
            model_name='role',
            index=models.Index(fields=['code'], name='ops_role_code_idx'),
        ),
        migrations.AddIndex(
            model_name='role',
            index=models.Index(fields=['is_active', 'rank'], name='ops_role_active_rank_idx'),
        ),
        migrations.RunPython(seed_roles, noop_reverse),
    ]
