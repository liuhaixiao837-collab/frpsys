from django.db import migrations


def create_helm_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    Organization = apps.get_model('ops', 'Organization')
    organization = Organization.objects.order_by('id').first()
    SystemSetting.objects.get_or_create(
        key='ci.helm_tools',
        defaults={
            'organization': organization,
            'value': {'name': 'helm', 'path': 'helm'},
            'description': 'Helm command config',
        },
    )


def remove_helm_tools_setting(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    SystemSetting.objects.filter(key='ci.helm_tools').delete()


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0016_default_docker_tools_setting'),
    ]

    operations = [
        migrations.RunPython(create_helm_tools_setting, remove_helm_tools_setting),
    ]
