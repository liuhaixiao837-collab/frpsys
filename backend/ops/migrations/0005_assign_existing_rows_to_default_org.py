from django.db import migrations


ORG_SCOPED_MODELS = [
    'AlertRule',
    'AuditLog',
    'BackupSnapshot',
    'ChangeEvent',
    'ChatChannel',
    'ChatSession',
    'CloudAsset',
    'Device',
    'Incident',
    'Integration',
    'InvestigationRun',
    'KnowledgeDocument',
    'KnowledgeRepo',
    'MaintenanceWindow',
    'ModelRoutePolicy',
    'MonitorPanel',
    'MutatingProposal',
    'NotificationChannel',
    'OnCallSchedule',
    'Playbook',
    'Report',
    'ReportSchedule',
    'SLOTarget',
    'SSHIdentity',
    'SystemSetting',
    'TopologyNode',
    'WatchTask',
]


def assign_org(apps, schema_editor):
    Organization = apps.get_model('ops', 'Organization')
    org = Organization.objects.order_by('id').first()
    if not org:
        return
    for model_name in ORG_SCOPED_MODELS:
        model = apps.get_model('ops', model_name)
        model.objects.filter(organization__isnull=True).update(organization=org)


def unassign_org(apps, schema_editor):
    for model_name in ORG_SCOPED_MODELS:
        model = apps.get_model('ops', model_name)
        model.objects.update(organization=None)


class Migration(migrations.Migration):
    dependencies = [
        ('ops', '0004_alertrule_organization_auditlog_organization_and_more'),
    ]

    operations = [
        migrations.RunPython(assign_org, unassign_org),
    ]
