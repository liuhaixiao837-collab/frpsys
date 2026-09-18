from django.db import migrations

import data_security.fields


def encrypt_existing_values(apps, schema_editor):
    UserProfile = apps.get_model('ops', 'UserProfile')
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    ChatChannel = apps.get_model('ops', 'ChatChannel')
    NotificationChannel = apps.get_model('ops', 'NotificationChannel')

    for profile in UserProfile.objects.exclude(phone='').iterator():
        profile.save(update_fields=['phone'])
    for model in (SystemSetting, ChatChannel, NotificationChannel):
        field_name = 'value' if model is SystemSetting else 'config'
        for instance in model.objects.all().iterator():
            instance.save(update_fields=[field_name])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0030_aiassistantmessage_summary_aiusermemory'),
    ]

    operations = [
        migrations.AlterField(
            model_name='userprofile',
            name='phone',
            field=data_security.fields.EncryptedCharField(blank=True, max_length=512),
        ),
        migrations.AlterField(
            model_name='systemsetting',
            name='value',
            field=data_security.fields.EncryptedJSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='chatchannel',
            name='config',
            field=data_security.fields.EncryptedJSONField(blank=True, default=dict),
        ),
        migrations.AlterField(
            model_name='notificationchannel',
            name='config',
            field=data_security.fields.EncryptedJSONField(blank=True, default=dict),
        ),
        migrations.RunPython(encrypt_existing_values, migrations.RunPython.noop),
    ]

