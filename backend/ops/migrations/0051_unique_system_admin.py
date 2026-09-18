from django.db import migrations


def normalize_system_admin(apps, schema_editor):
    """将现有 admin 固定为唯一超级管理员，并降级其他超级管理员。"""
    User = apps.get_model('auth', 'User')
    admin = User.objects.filter(username='admin').order_by('id').first()
    if not admin:
        return
    User.objects.filter(is_superuser=True).exclude(pk=admin.pk).update(is_superuser=False)
    User.objects.filter(pk=admin.pk).update(is_superuser=True, is_staff=True, is_active=True)


def keep_normalized_system_admin(apps, schema_editor):
    """唯一超级管理员属于安全约束，回滚迁移时不恢复不安全的历史标记。"""


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0050_platformloginsession'),
    ]

    operations = [
        migrations.RunPython(normalize_system_admin, keep_normalized_system_admin),
    ]
