from rest_framework import serializers
from django.utils import timezone

from data_security.sm4 import encrypt

from . import models


DT_FORMAT = '%Y-%m-%d %H:%M:%S'
MASK = '********'


class FrpServerSerializer(serializers.ModelSerializer):
    auth_token = serializers.CharField(write_only=True, required=False, allow_blank=True)
    dashboard_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_auth_token = serializers.SerializerMethodField()
    has_dashboard_password = serializers.SerializerMethodField()
    agent_count = serializers.IntegerField(read_only=True, default=0)
    proxy_count = serializers.IntegerField(read_only=True, default=0)
    created_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    updated_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    last_test_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)

    class Meta:
        model = models.FrpServer
        fields = [
            'id', 'organization', 'name', 'server_code', 'public_host', 'bind_port',
            'allow_ports', 'dashboard_host', 'dashboard_port', 'dashboard_username',
            'dashboard_password', 'auth_token', 'has_auth_token', 'has_dashboard_password',
            'allow_register',
            'max_agents', 'agent_count', 'proxy_count', 'status', 'last_test_status',
            'last_test_message', 'last_test_at', 'remark', 'created_at', 'updated_at',
        ]
        read_only_fields = ['organization', 'last_test_status', 'last_test_message', 'last_test_at', 'created_at', 'updated_at']

    def get_has_auth_token(self, obj):
        """处理 FRP 模块的 get_has_auth_token 业务步骤。"""
        return obj.has_auth_token

    def get_has_dashboard_password(self, obj):
        """处理 FRP 模块的 get_has_dashboard_password 业务步骤。"""
        return obj.has_dashboard_password

    def _apply_secrets(self, instance, validated_data):
        """处理 FRP 模块的 _apply_secrets 业务步骤。"""
        token = validated_data.pop('auth_token', None)
        password = validated_data.pop('dashboard_password', None)
        if token and token != MASK:
            instance.encrypted_auth_token = encrypt(token)
        if password and password != MASK:
            instance.encrypted_dashboard_password = encrypt(password)
        return instance

    def create(self, validated_data):
        """处理 FRP 模块的 create 业务步骤。"""
        token = validated_data.pop('auth_token', None)
        password = validated_data.pop('dashboard_password', None)
        instance = models.FrpServer.objects.create(**validated_data)
        if token and token != MASK:
            instance.encrypted_auth_token = encrypt(token)
        if password and password != MASK:
            instance.encrypted_dashboard_password = encrypt(password)
        instance.save()
        return instance

    def update(self, instance, validated_data):
        """处理 FRP 模块的 update 业务步骤。"""
        for key, value in list(validated_data.items()):
            if key not in {'auth_token', 'dashboard_password'}:
                setattr(instance, key, value)
        self._apply_secrets(instance, validated_data)
        instance.save()
        return instance


class FrpAgentSerializer(serializers.ModelSerializer):
    admin_password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    has_admin_password = serializers.SerializerMethodField()
    server_name = serializers.CharField(source='server.name', read_only=True, default='')
    proxy_count = serializers.IntegerField(read_only=True, default=0)
    created_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    updated_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    last_heartbeat_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    last_seen_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    approved_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    rejected_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)

    class Meta:
        model = models.FrpAgent
        fields = [
            'id', 'organization', 'server', 'server_name', 'agent_id', 'fingerprint',
            'hostname', 'client_ip', 'source', 'admin_host', 'admin_port', 'admin_username',
            'admin_password', 'has_admin_password', 'admin_proxy_name',
            'admin_proxy_remote_addr', 'store_enabled', 'runtime_proxy_count',
            'tags', 'metadata', 'approval_status', 'status', 'last_heartbeat_at',
            'last_seen_at', 'last_error', 'approved_by', 'approved_at', 'rejected_by',
            'rejected_at', 'reject_reason', 'proxy_count', 'remark',
            'created_at', 'updated_at',
        ]
        read_only_fields = [
            'organization', 'agent_id', 'fingerprint', 'client_ip', 'last_heartbeat_at',
            'last_seen_at', 'approved_by', 'approved_at', 'rejected_by', 'rejected_at',
            'server_name', 'proxy_count', 'has_admin_password', 'created_at', 'updated_at',
        ]

    def get_has_admin_password(self, obj):
        """处理 FRP 模块的 get_has_admin_password 业务步骤。"""
        return obj.has_admin_password

    def _apply_admin_password(self, instance, validated_data):
        """处理 FRP 模块的 _apply_admin_password 业务步骤。"""
        password = validated_data.pop('admin_password', None)
        if password and password != MASK:
            instance.encrypted_admin_password = encrypt(password)
        return instance

    def create(self, validated_data):
        """处理 FRP 模块的 create 业务步骤。"""
        password = validated_data.pop('admin_password', None)
        hostname = str(validated_data.get('hostname') or '').strip()
        fingerprint = models.FrpAgent.build_fingerprint(hostname)
        validated_data.setdefault('fingerprint', fingerprint)
        validated_data.setdefault('agent_id', fingerprint[:16])
        instance = super().create(validated_data)
        if password and password != MASK:
            instance.encrypted_admin_password = encrypt(password)
            instance.save(update_fields=['encrypted_admin_password', 'updated_at'])
        return instance

    def update(self, instance, validated_data):
        """处理 FRP 模块的 update 业务步骤。"""
        for key, value in list(validated_data.items()):
            if key != 'admin_password':
                setattr(instance, key, value)
        self._apply_admin_password(instance, validated_data)
        instance.save()
        return instance


class FrpProxySerializer(serializers.ModelSerializer):
    server = serializers.PrimaryKeyRelatedField(read_only=True)
    server_name = serializers.CharField(source='server.name', read_only=True, default='')
    agent_name = serializers.CharField(source='agent.hostname', read_only=True, default='')
    created_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    updated_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    last_test_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    traffic = serializers.SerializerMethodField()
    today_traffic = serializers.SerializerMethodField()

    class Meta:
        model = models.FrpProxy
        fields = '__all__'
        read_only_fields = ['organization', 'server_name', 'agent_name', 'traffic', 'today_traffic', 'last_test_status', 'last_test_message', 'last_test_at', 'traffic_in_bytes', 'traffic_out_bytes', 'today_traffic_in_bytes', 'today_traffic_out_bytes', 'traffic_source_in_bytes', 'traffic_source_out_bytes', 'traffic_date', 'traffic_updated_at', 'created_at', 'updated_at']

    def get_traffic(self, obj):
        total = int(obj.traffic_in_bytes or 0) + int(obj.traffic_out_bytes or 0)
        return f'{total / (1024 * 1024):.2f}M' if total else '-'

    def get_today_traffic(self, obj):
        if obj.traffic_date != timezone.localdate():
            return '-'
        total = int(obj.today_traffic_in_bytes or 0) + int(obj.today_traffic_out_bytes or 0)
        return f'{total / (1024 * 1024):.2f}M' if total else '-'

    def validate(self, attrs):
        """处理 FRP 模块的 validate 业务步骤。"""
        attrs = super().validate(attrs)
        agent = attrs.get('agent') or getattr(self.instance, 'agent', None)
        if agent:
            if agent.approval_status != 'approved':
                raise serializers.ValidationError({'agent': 'Agent 尚未审核通过，不能下发隧道配置。'})
            if agent.status == 'disabled':
                raise serializers.ValidationError({'agent': 'Agent 已禁用，不能下发隧道配置。'})
            attrs['server'] = agent.server
        return attrs

    def create(self, validated_data):
        """处理 FRP 模块的 create 业务步骤。"""
        agent = validated_data.get('agent')
        if agent:
            validated_data['server'] = agent.server
        return super().create(validated_data)

    def update(self, instance, validated_data):
        """处理 FRP 模块的 update 业务步骤。"""
        agent = validated_data.get('agent') or instance.agent
        if agent:
            validated_data['server'] = agent.server
        return super().update(instance, validated_data)


class FrpAgentHeartbeatSerializer(serializers.ModelSerializer):
    server_name = serializers.CharField(source='server.name', read_only=True, default='')
    agent_name = serializers.CharField(source='agent.hostname', read_only=True, default='')
    created_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)
    reported_at = serializers.DateTimeField(format=DT_FORMAT, read_only=True)

    class Meta:
        model = models.FrpAgentHeartbeat
        fields = '__all__'
        read_only_fields = ['organization', 'server_name', 'agent_name', 'created_at', 'updated_at']


class FrpAuditSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    actor = serializers.CharField()
    action = serializers.CharField()
    resource = serializers.CharField()
    ip_address = serializers.CharField()
    detail = serializers.JSONField()
    created_at = serializers.DateTimeField(format=DT_FORMAT)
