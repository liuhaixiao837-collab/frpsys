from django.db import migrations
from django.utils import timezone


def release_system_admin_password_lock(apps, schema_editor):
    """解除 admin 因密码修改周期策略产生的过期锁定。

    参数：`apps` 为历史模型注册表；`schema_editor` 为当前迁移使用的数据库编辑器。
    返回：无显式返回值。
    副作用：仅在存在锁定标记时启用 admin 并重置密码有效期周期，其余情况不写入数据库。
    """
    User = apps.get_model('auth', 'User')
    UserProfile = apps.get_model('ops', 'UserProfile')
    admin = User.objects.filter(username='admin').order_by('id').first()
    if not admin:
        return
    locked = UserProfile.objects.filter(user=admin, password_expired_locked=True)
    if not locked.exists():
        return
    locked.update(password_expired_locked=False, password_changed_at=timezone.now())
    User.objects.filter(pk=admin.pk).update(is_active=True)


def keep_system_admin_password_lock(apps, schema_editor):
    """admin 豁免密码修改周期属于可用性约束，回滚迁移时不恢复过期锁定。"""


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0069_frp_traffic_report_menu'),
    ]

    operations = [
        migrations.RunPython(release_system_admin_password_lock, keep_system_admin_password_lock),
    ]
