from django.contrib import admin

from . import models


@admin.register(models.FrpServer)
class FrpServerAdmin(admin.ModelAdmin):
    list_display = ('name', 'server_code', 'public_host', 'bind_port', 'status', 'last_test_at')
    search_fields = ('name', 'server_code', 'public_host')
    list_filter = ('status', 'allow_register')


@admin.register(models.FrpAgent)
class FrpAgentAdmin(admin.ModelAdmin):
    list_display = ('hostname', 'server', 'approval_status', 'status', 'last_heartbeat_at')
    search_fields = ('hostname', 'agent_id', 'fingerprint')
    list_filter = ('approval_status', 'status')


@admin.register(models.FrpProxy)
class FrpProxyAdmin(admin.ModelAdmin):
    list_display = ('name', 'agent', 'proxy_type', 'local_port', 'remote_port', 'status')
    search_fields = ('name', 'agent__hostname', 'local_ip')
    list_filter = ('proxy_type', 'status')


@admin.register(models.FrpAgentHeartbeat)
class FrpAgentHeartbeatAdmin(admin.ModelAdmin):
    list_display = ('agent', 'status', 'ip_address', 'reported_at')
    search_fields = ('agent__hostname', 'ip_address', 'message')
    list_filter = ('status',)
