from django.db import migrations


def configure_openai_responses(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    setting = SystemSetting.objects.filter(key='config.llm.openai').first()
    if not setting:
        return
    value = dict(setting.value or {})
    if 'api.codexzh.com' in str(value.get('base_url') or '') or value.get('default_model') == 'gpt-5.5':
        value['base_url'] = 'https://api.codexzh.com/v1'
        value['api_protocol'] = 'responses'
        for field in ('last_test_status', 'last_test_detail', 'last_test_at'):
            value.pop(field, None)
        setting.value = value
        setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0019_model_config_parent_permission'),
    ]

    operations = [
        migrations.RunPython(configure_openai_responses, migrations.RunPython.noop),
    ]
