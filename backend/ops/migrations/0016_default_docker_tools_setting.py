from django.db import migrations


def create_docker_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    Organization = apps.get_model('ops', 'Organization')
    organization = Organization.objects.order_by('id').first()
    SystemSetting.objects.get_or_create(
        key='ci.docker_tools',
        defaults={
            'organization': organization,
            'value': {'name': 'docker', 'path': r'C:\Program Files\Docker\Docker\resources\docker.exe'},
            'description': 'Docker 命令配置',
        },
    )


def remove_docker_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='ci.docker_tools').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0015_default_git_tools_setting'),
    ]

    operations = [
        migrations.RunPython(create_docker_tools_setting, remove_docker_tools_setting),
    ]
