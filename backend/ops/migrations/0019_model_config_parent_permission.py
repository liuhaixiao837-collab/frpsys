from django.db import migrations


MODEL_CONFIG_PARENT = 'menu.model_config'
MODEL_CONFIG_CHILDREN = ['page.llm.view', 'page.model_routes.view']


def grant_model_config_parent(apps, schema_editor):
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    policy_ids = PermissionRule.objects.filter(
        permission_code__in=MODEL_CONFIG_CHILDREN,
        effect='allow',
    ).values_list('policy_id', flat=True).distinct()
    existing_policy_ids = set(
        PermissionRule.objects.filter(
            policy_id__in=policy_ids,
            permission_code=MODEL_CONFIG_PARENT,
        ).values_list('policy_id', flat=True)
    )
    rules = [
        PermissionRule(policy_id=policy_id, permission_code=MODEL_CONFIG_PARENT, effect='allow')
        for policy_id in policy_ids
        if policy_id not in existing_policy_ids
    ]
    if rules:
        PermissionRule.objects.bulk_create(rules, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0018_remove_platform_management_modules'),
    ]

    operations = [
        migrations.RunPython(grant_model_config_parent, migrations.RunPython.noop),
    ]
