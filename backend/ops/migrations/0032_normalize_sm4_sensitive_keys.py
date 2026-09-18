from django.db import migrations


def normalize_encrypted_configs(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    ChatChannel = apps.get_model('ops', 'ChatChannel')
    NotificationChannel = apps.get_model('ops', 'NotificationChannel')

    for model in (SystemSetting, ChatChannel, NotificationChannel):
        field_name = 'value' if model is SystemSetting else 'config'
        for instance in model.objects.all().iterator():
            instance.save(update_fields=[field_name])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0031_sm4_sensitive_data'),
    ]

    operations = [
        migrations.RunPython(normalize_encrypted_configs, migrations.RunPython.noop),
    ]
