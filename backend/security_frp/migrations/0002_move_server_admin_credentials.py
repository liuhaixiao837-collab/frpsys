from django.db import migrations


def move_server_admin_credentials(apps, schema_editor):
    """将历史服务端 frpc 凭据转存到对应客户端后删除服务端字段。"""
    FrpServer = apps.get_model('security_frp', 'FrpServer')
    FrpAgent = apps.get_model('security_frp', 'FrpAgent')
    for server in FrpServer.objects.exclude(encrypted_client_admin_password='').iterator():
        agents = FrpAgent.objects.filter(server_id=server.pk)
        for agent in agents:
            if not agent.admin_username:
                agent.admin_username = 'cmdb'
            if not agent.encrypted_admin_password:
                agent.encrypted_admin_password = server.encrypted_client_admin_password
            agent.save(update_fields=['admin_username', 'encrypted_admin_password', 'updated_at'])


class Migration(migrations.Migration):

    dependencies = [
        ('security_frp', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(move_server_admin_credentials, migrations.RunPython.noop),
        migrations.RemoveField(model_name='frpserver', name='client_admin_username'),
        migrations.RemoveField(model_name='frpserver', name='encrypted_client_admin_password'),
    ]
