from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    """将既有审计表的模型状态迁入独立日志应用，不改动数据库表和数据。"""

    initial = True

    dependencies = [
        ('ops', '0062_watermark_setting'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.CreateModel(
                    name='AuditLog',
                    fields=[
                        ('id', models.BigAutoField(help_text='日志记录主键。', primary_key=True, serialize=False)),
                        (
                            'created_at',
                            models.DateTimeField(default=django.utils.timezone.now, help_text='日志记录创建时间。'),
                        ),
                        ('updated_at', models.DateTimeField(auto_now=True, help_text='日志记录最后更新时间。')),
                        ('actor', models.CharField(help_text='执行操作或尝试登录的用户名。', max_length=80)),
                        ('action', models.CharField(help_text='具体业务操作代码。', max_length=120)),
                        ('resource', models.CharField(help_text='被操作对象的用户友好标识。', max_length=160)),
                        (
                            'ip_address',
                            models.GenericIPAddressField(default='127.0.0.1', help_text='发起操作的客户端 IP 地址。'),
                        ),
                        (
                            'detail',
                            models.JSONField(
                                blank=True,
                                default=dict,
                                help_text='用于生成友好详情的结构化操作上下文。',
                            ),
                        ),
                        (
                            'organization',
                            models.ForeignKey(
                                blank=True,
                                help_text='操作发生时用户所属的组织。',
                                null=True,
                                on_delete=django.db.models.deletion.CASCADE,
                                related_name='audit_logs',
                                to='ops.organization',
                            ),
                        ),
                    ],
                    options={
                        'db_table': 'ops_auditlog',
                        'ordering': ['-created_at'],
                    },
                ),
            ],
            database_operations=[],
        ),
    ]
