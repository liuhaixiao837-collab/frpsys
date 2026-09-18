from django.db import migrations


def create_backup_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    Organization = apps.get_model('ops', 'Organization')
    organization = Organization.objects.order_by('id').first()
    SystemSetting.objects.get_or_create(
        key='database.backup_tools',
        defaults={
            'organization': organization,
            'value': {'name': 'mysqldump', 'path': '/usr/local/mysql/mysqldump'},
            'description': '数据库备份命令配置',
        },
    )


def remove_backup_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='database.backup_tools').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0013_integration_code_repository_choice'),
    ]

    operations = [
        migrations.RunPython(create_backup_tools_setting, remove_backup_tools_setting),
    ]
