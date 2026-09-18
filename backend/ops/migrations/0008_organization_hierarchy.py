from django.db import migrations, models
import django.db.models.deletion


def seed_default_root(apps, schema_editor):
    Organization = apps.get_model('ops', 'Organization')
    root = Organization.objects.filter(is_default=True).order_by('id').first()
    if not root:
        root = Organization.objects.filter(slug='default-org').first()
    if not root:
        root = Organization.objects.filter(name='默认组织').first()
    if not root:
        root = Organization.objects.create(
            name='默认组织',
            slug='default-org',
            description='公司根组织，部门默认挂载到这里',
            region='中国',
            org_type='company',
            is_default=True,
        )

    root.parent = None
    root.org_type = 'company'
    root.is_default = True
    root.save(update_fields=['parent', 'org_type', 'is_default', 'updated_at'])

    Organization.objects.exclude(pk=root.pk).filter(parent__isnull=True).update(
        parent=root,
        org_type='department',
        is_default=False,
    )


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0007_topologynodetype_topologyrelationtype_and_more'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='organization',
            options={'ordering': ['parent_id', 'name']},
        ),
        migrations.AddField(
            model_name='organization',
            name='is_default',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='organization',
            name='org_type',
            field=models.CharField(
                choices=[('company', 'Company'), ('department', 'Department')],
                default='department',
                max_length=32,
            ),
        ),
        migrations.AddField(
            model_name='organization',
            name='parent',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='children',
                to='ops.organization',
            ),
        ),
        migrations.AddIndex(
            model_name='organization',
            index=models.Index(fields=['parent', 'org_type'], name='ops_org_parent_type_idx'),
        ),
        migrations.RunPython(seed_default_root, noop_reverse),
    ]
