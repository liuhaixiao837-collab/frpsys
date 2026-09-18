from django.db import migrations


def backfill_llm_priority(apps, schema_editor):
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    for setting in SystemSetting.objects.filter(key__startswith='config.llm.'):
        value = dict(setting.value or {})
        if value.get('deleted'):
            continue
        try:
            priority = max(1, int(value.get('priority', 50)))
        except (TypeError, ValueError):
            priority = 50
        if value.get('priority') != priority:
            value['priority'] = priority
            setting.value = value
            setting.save(update_fields=['value', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0020_llm_responses_protocol'),
    ]

    operations = [
        migrations.RunPython(backfill_llm_priority, migrations.RunPython.noop),
    ]
