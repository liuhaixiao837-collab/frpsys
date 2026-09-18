from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('ops', '0010_organization_is_active'),
    ]

    operations = [
        migrations.CreateModel(
            name='PermissionPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('name', models.CharField(max_length=120)),
                ('subject_type', models.CharField(choices=[('department', 'Department'), ('user', 'User')], max_length=32)),
                ('priority', models.PositiveIntegerField(default=50)),
                ('status', models.CharField(choices=[('available', 'Available'), ('disabled', 'Disabled')], default='available', max_length=32)),
                ('remark', models.TextField(blank=True)),
                ('department', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='department_permission_policies', to='ops.organization')),
                ('organization', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='permission_policies', to='ops.organization')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='permission_policies', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['priority', '-updated_at'],
            },
        ),
        migrations.CreateModel(
            name='PermissionRule',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('permission_code', models.CharField(max_length=160)),
                ('effect', models.CharField(choices=[('allow', 'Allow'), ('deny', 'Deny')], default='allow', max_length=16)),
                ('policy', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='rules', to='ops.permissionpolicy')),
            ],
            options={
                'ordering': ['permission_code'],
                'unique_together': {('policy', 'permission_code')},
            },
        ),
        migrations.AddIndex(
            model_name='permissionpolicy',
            index=models.Index(fields=['subject_type', 'status', 'priority'], name='ops_perm_policy_subject_idx'),
        ),
        migrations.AddIndex(
            model_name='permissionpolicy',
            index=models.Index(fields=['department', 'status'], name='ops_perm_policy_dept_idx'),
        ),
        migrations.AddIndex(
            model_name='permissionpolicy',
            index=models.Index(fields=['user', 'status'], name='ops_perm_policy_user_idx'),
        ),
        migrations.AddIndex(
            model_name='permissionrule',
            index=models.Index(fields=['permission_code', 'effect'], name='ops_perm_rule_code_idx'),
        ),
    ]
