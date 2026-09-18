from django.db import migrations


class Migration(migrations.Migration):
    """从核心应用移除旧日志模型状态，保留原数据库表供日志应用接管。"""

    dependencies = [
        ('ops', '0062_watermark_setting'),
        ('platform_logs', '0001_move_audit_log'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[migrations.DeleteModel(name='AuditLog')],
            database_operations=[],
        ),
    ]
