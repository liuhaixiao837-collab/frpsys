from django.db import migrations


REMOVED_PERMISSION_PREFIXES = [
    'page.integrations.',
    'page.health.',
    'page.webshell.',
    'page.backups.',
    'page.slo.',
    'page.usage.',
]

REMOVED_PERMISSION_CODES = [
    'page.integrations.view',
    'page.health.view',
    'page.webshell.view',
    'page.backups.view',
    'page.slo.view',
    'page.usage.view',
]


def cleanup_removed_platform_modules(apps, schema_editor):
    PermissionRule = apps.get_model('ops', 'PermissionRule')
    SystemSetting = apps.get_model('ops', 'SystemSetting')
    query = PermissionRule.objects.filter(permission_code__in=REMOVED_PERMISSION_CODES)
    for prefix in REMOVED_PERMISSION_PREFIXES:
        query = query | PermissionRule.objects.filter(permission_code__startswith=prefix)
    query.delete()
    SystemSetting.objects.filter(key__startswith='config.integrations.').delete()


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0017_default_helm_tools_setting'),
    ]

    operations = [
        migrations.RunPython(cleanup_removed_platform_modules, migrations.RunPython.noop),
        migrations.DeleteModel(name='BackupSnapshot'),
        migrations.DeleteModel(name='Integration'),
        migrations.DeleteModel(name='SLOTarget'),
        migrations.DeleteModel(name='UsageBudget'),
        migrations.DeleteModel(name='WebShellSession'),
    ]
