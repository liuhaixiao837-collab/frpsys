from django.db import migrations


def clear_role_permissions(apps, schema_editor):
    Role = apps.get_model('ops', 'Role')
    Role.objects.exclude(permissions=[]).update(permissions=[])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0011_permission_policy'),
    ]

    operations = [
        migrations.RunPython(clear_role_permissions, noop_reverse),
    ]
