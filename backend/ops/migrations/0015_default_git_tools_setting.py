from django.db import migrations


def create_git_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    Organization = apps.get_model('ops', 'Organization')
    organization = Organization.objects.order_by('id').first()
    SystemSetting.objects.get_or_create(
        key='ci.git_tools',
        defaults={
            'organization': organization,
            'value': {'name': 'git', 'path': '/mingw64/bin/git'},
            'description': 'Git 命令配置',
        },
    )


def remove_git_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='ci.git_tools').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0014_default_backup_tools_setting'),
    ]

    operations = [
        migrations.RunPython(create_git_tools_setting, remove_git_tools_setting),
    ]
