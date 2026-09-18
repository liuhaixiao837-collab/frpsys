from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ('security_frp', '0002_move_server_admin_credentials'),
    ]

    operations = [
        migrations.RemoveField(model_name='frpagent', name='management_ip'),
        migrations.RemoveField(model_name='frpagent', name='os'),
        migrations.RemoveField(model_name='frpagent', name='arch'),
        migrations.RemoveField(model_name='frpagent', name='version'),
        migrations.RemoveField(model_name='frpagent', name='username'),
    ]
