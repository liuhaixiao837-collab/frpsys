from django.db import migrations


DEFAULT_STRATEGY = {
    'retry_count': 2,
    'timeout_seconds': 10,
    'failover_enabled': True,
}


def migrate_model_routes_to_strategy(apps, schema_editor):
    ModelRoutePolicy = apps.get_model('ops', 'ModelRoutePolicy')
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    ModelRoutePolicy.objects.all().delete()
    SystemSetting.objects.get_or_create(
        key='config.llm_strategy.global',
        defaults={'value': dict(DEFAULT_STRATEGY), 'description': 'LLM 模型策略'},
    )


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0021_llm_provider_priority'),
    ]

    operations = [
        migrations.RunPython(migrate_model_routes_to_strategy, migrations.RunPython.noop),
    ]
