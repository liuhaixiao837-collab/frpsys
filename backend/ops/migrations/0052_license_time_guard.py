from django.db import migrations


def create_license_time_guard(apps, schema_editor):
    """创建不含初始时间的 Licence 防回拨状态配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.get_or_create(
        key='license.time_guard',
        defaults={
            'organization': None,
            'value': {},
            'description': 'Licence 防时间回拨保护状态',
        },
    )


def remove_license_time_guard(apps, schema_editor):
    """回退迁移时删除 Licence 防回拨状态配置。"""
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='license.time_guard').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0051_unique_system_admin'),
    ]

    operations = [
        migrations.RunPython(create_license_time_guard, remove_license_time_guard),
    ]
