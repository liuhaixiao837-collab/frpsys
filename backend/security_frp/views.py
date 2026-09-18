from datetime import timedelta

from django.db.models import Count, Q, Sum
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.decorators import action, api_view, authentication_classes, permission_classes
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from data_security.sm4 import decrypt
from ops.models import AuditLog
from ops.permissions import user_organization
from ops.tenancy import assign_organization, scoped_queryset

from . import models, serializers, services


class FrpPagination(PageNumberPagination):
    """FRP module pagination; UI tables are designed around 10 rows per page."""

    page_size = 10
    page_size_query_param = 'page_size'
    max_page_size = 100


class FrpBaseViewSet(viewsets.ModelViewSet):
    """Common organization scoping, search, status filtering and write audit."""

    pagination_class = FrpPagination
    search_fields = ()

    def get_queryset(self):
        """处理 FRP 模块的 get_queryset 业务步骤。"""
        queryset = scoped_queryset(super().get_queryset(), self.request.user)
        keyword = self.request.query_params.get('q', '').strip()
        if keyword and self.search_fields:
            query = Q()
            for field in self.search_fields:
                query |= Q(**{f'{field}__icontains': keyword})
            queryset = queryset.filter(query)
        status_value = self.request.query_params.get('status', '').strip()
        if status_value and any(field.name == 'status' for field in queryset.model._meta.fields):
            queryset = queryset.filter(status=status_value)
        approval_status = self.request.query_params.get('approval_status', '').strip()
        if approval_status and any(field.name == 'approval_status' for field in queryset.model._meta.fields):
            queryset = queryset.filter(approval_status=approval_status)
        return queryset

    def _write_audit(self, action_name, instance, detail=None):
        """处理 FRP 模块的 _write_audit 业务步骤。"""
        services.write_frp_audit(self.request, f'{instance.__class__.__name__}.{action_name}', instance, detail or {'id': getattr(instance, 'pk', None)})

    def perform_create(self, serializer):
        """处理 FRP 模块的 perform_create 业务步骤。"""
        instance = serializer.save()
        assign_organization(instance, self.request.user)
        instance.save()
        self._write_audit('create', instance)

    def perform_update(self, serializer):
        """处理 FRP 模块的 perform_update 业务步骤。"""
        instance = serializer.save()
        assign_organization(instance, self.request.user)
        instance.save()
        self._write_audit('update', instance)

    def perform_destroy(self, instance):
        """处理 FRP 模块的 perform_destroy 业务步骤。"""
        self._write_audit('delete', instance)
        instance.delete()


class FrpServerViewSet(FrpBaseViewSet):
    queryset = models.FrpServer.objects.select_related('organization').all()
    serializer_class = serializers.FrpServerSerializer
    search_fields = ('name', 'server_code', 'public_host', 'dashboard_host', 'remark')

    def get_queryset(self):
        """处理 FRP 模块的 get_queryset 业务步骤。"""
        return super().get_queryset().annotate(
            agent_count=Count('agents', distinct=True),
            proxy_count=Count('proxies', distinct=True),
        )

    @action(detail=True, methods=['get'], url_path='reveal')
    def reveal(self, request, pk=None):
        """按敏感信息权限解密并返回当前 FRP 服务端密码。"""
        server = self.get_object()
        secrets = {
            'auth_token': decrypt(server.encrypted_auth_token),
            'dashboard_password': decrypt(server.encrypted_dashboard_password),
        }
        self._write_audit('reveal', server, {'id': server.pk, 'fields': [key for key, value in secrets.items() if value]})
        return Response({'secrets': secrets})

    def destroy(self, request, *args, **kwargs):
        """处理 FRP 模块的 destroy 业务步骤。"""
        instance = self.get_object()
        child_count = instance.agents.count() + instance.proxies.count()
        if child_count:
            self._write_audit('delete_blocked', instance, {'id': instance.pk, 'child_count': child_count})
            return Response({'detail': f'该服务端下面还有 {child_count} 条 Agent 或隧道数据，请先处理后再删除。'}, status=400)
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'], url_path='test')
    def test(self, request, pk=None):
        """处理 FRP 模块的 test 业务步骤。"""
        server = self.get_object()
        if server.status == 'disabled':
            result = {'status': 'disabled', 'detail': '服务端已禁用，不能执行测试。'}
        else:
            ok, message, checked_at = services.test_tcp_endpoint(server.public_host, server.bind_port)
            result = services.update_server_test_result(server, ok, message, checked_at)
        self._write_audit('test', server, {'id': server.pk, **result})
        return Response({'server': self.get_serializer(server).data, **result})

    @action(detail=True, methods=['post'], url_path='sync-runtime')
    def sync_runtime(self, request, pk=None):
        """处理 FRP 模块的 sync_runtime 业务步骤。"""
        server = self.get_object()
        result = services.sync_server_runtime(server, request=request)
        self._write_audit('sync_runtime', server, {'id': server.pk, **result})
        server.refresh_from_db()
        return Response({'server': self.get_serializer(server).data, **result})

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, request, pk=None):
        """处理 FRP 模块的 disable 业务步骤。"""
        server = self.get_object()
        server.status = 'disabled'
        server.save(update_fields=['status', 'updated_at'])
        self._write_audit('disable', server)
        return Response(self.get_serializer(server).data)

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, request, pk=None):
        """处理 FRP 模块的 enable 业务步骤。"""
        server = self.get_object()
        server.status = 'configured'
        server.save(update_fields=['status', 'updated_at'])
        self._write_audit('enable', server)
        return Response(self.get_serializer(server).data)


class FrpAgentViewSet(FrpBaseViewSet):
    queryset = models.FrpAgent.objects.select_related('organization', 'server').all()
    serializer_class = serializers.FrpAgentSerializer
    search_fields = ('hostname', 'agent_id', 'fingerprint', 'server__name', 'last_error', 'remark')

    def get_queryset(self):
        """处理 FRP 模块的 get_queryset 业务步骤。"""
        queryset = super().get_queryset().annotate(proxy_count=Count('proxies', distinct=True))
        server_id = self.request.query_params.get('server')
        if server_id:
            queryset = queryset.filter(server_id=server_id)
        return queryset

    @action(detail=True, methods=['get'], url_path='reveal')
    def reveal(self, request, pk=None):
        """按敏感信息权限解密并返回当前 frpc 管理密码。"""
        agent = self.get_object()
        own_password = decrypt(agent.encrypted_admin_password)
        secrets = {'admin_password': own_password}
        self._write_audit('reveal', agent, {'id': agent.pk, 'fields': ['admin_password'] if secrets['admin_password'] else []})
        return Response({'secrets': secrets})

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        """处理 FRP 模块的 approve 业务步骤。"""
        agent = self.get_object()
        if agent.status == 'disabled':
            return Response({'detail': 'Agent 已禁用，不能审核通过。'}, status=400)
        agent.approval_status = 'approved'
        agent.approved_by = getattr(request.user, 'username', '') or ''
        agent.approved_at = timezone.now()
        agent.rejected_by = ''
        agent.rejected_at = None
        agent.reject_reason = ''
        agent.save(update_fields=['approval_status', 'approved_by', 'approved_at', 'rejected_by', 'rejected_at', 'reject_reason', 'updated_at'])
        self._write_audit('approve', agent, {'id': agent.pk, 'approval_status': agent.approval_status})
        return Response(self.get_serializer(agent).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        """处理 FRP 模块的 reject 业务步骤。"""
        reason = str(request.data.get('reason') or '').strip()
        if not reason:
            return Response({'detail': '请填写拒绝原因。'}, status=400)
        agent = self.get_object()
        agent.approval_status = 'rejected'
        agent.rejected_by = getattr(request.user, 'username', '') or ''
        agent.rejected_at = timezone.now()
        agent.reject_reason = reason[:240]
        agent.save(update_fields=['approval_status', 'rejected_by', 'rejected_at', 'reject_reason', 'updated_at'])
        self._write_audit('reject', agent, {'id': agent.pk, 'reason': agent.reject_reason})
        return Response(self.get_serializer(agent).data)

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, request, pk=None):
        """处理 FRP 模块的 disable 业务步骤。"""
        agent = self.get_object()
        agent.status = 'disabled'
        agent.save(update_fields=['status', 'updated_at'])
        self._write_audit('disable', agent, {'id': agent.pk})
        return Response(self.get_serializer(agent).data)

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, request, pk=None):
        """处理 FRP 模块的 enable 业务步骤。"""
        agent = self.get_object()
        agent.status = 'offline'
        agent.save(update_fields=['status', 'updated_at'])
        self._write_audit('enable', agent, {'id': agent.pk})
        return Response(self.get_serializer(agent).data)

    @action(detail=True, methods=['post'], url_path='test')
    def test(self, request, pk=None):
        """处理 FRP 模块的 test 业务步骤。"""
        agent = self.get_object()
        result = services.test_agent_admin_api(agent)
        self._write_audit('test', agent, {'id': agent.pk, **result})
        agent.refresh_from_db()
        return Response({'agent': self.get_serializer(agent).data, **result})

    @action(detail=True, methods=['post'], url_path='sync-proxies')
    def sync_proxies(self, request, pk=None):
        """处理 FRP 模块的 sync_proxies 业务步骤。"""
        agent = self.get_object()
        result = services.sync_agent_proxies(agent)
        self._write_audit('sync_proxies', agent, {'id': agent.pk, **result})
        agent.refresh_from_db()
        return Response({'agent': self.get_serializer(agent).data, **result})

    @action(detail=True, methods=['post'], url_path='add-proxy')
    def add_proxy(self, request, pk=None):
        """处理 FRP 模块的 add_proxy 业务步骤。"""
        agent = self.get_object()
        proxy, result = services.add_proxy_to_agent(agent, request.data)
        self._write_audit('add_proxy', agent, {
            'id': agent.pk,
            'proxy_id': proxy.pk,
            'proxy_name': proxy.name,
            'remote_port': proxy.remote_port,
        })
        return Response({
            'detail': f'端口 {proxy.remote_port} 已下发到 {agent.hostname or agent.agent_id}',
            'proxy': serializers.FrpProxySerializer(proxy).data,
            'frpc_result': result,
        })


class FrpProxyViewSet(FrpBaseViewSet):
    queryset = models.FrpProxy.objects.select_related('organization', 'server', 'agent').all()
    serializer_class = serializers.FrpProxySerializer
    search_fields = ('name', 'agent__hostname', 'server__name', 'local_ip', 'subdomain', 'remark')

    def get_queryset(self):
        """处理 FRP 模块的 get_queryset 业务步骤。"""
        queryset = super().get_queryset()
        server_id = self.request.query_params.get('server')
        agent_id = self.request.query_params.get('agent')
        if server_id:
            queryset = queryset.filter(server_id=server_id)
        if agent_id:
            queryset = queryset.filter(agent_id=agent_id)
        return queryset

    def create(self, request, *args, **kwargs):
        """处理 FRP 模块的 create 业务步骤。"""
        agent_id = request.data.get('agent')
        agent = scoped_queryset(models.FrpAgent.objects.select_related('server', 'organization'), request.user).filter(pk=agent_id).first()
        if not agent:
            return Response({'agent': '请选择有效的 frpc 客户端。'}, status=status.HTTP_400_BAD_REQUEST)
        proxy, result = services.add_proxy_to_agent(agent, request.data)
        self._write_audit('create', proxy, {
            'id': proxy.pk,
            'name': proxy.name,
            'remote_port': proxy.remote_port,
            **result,
        })
        return Response(self.get_serializer(proxy).data, status=status.HTTP_201_CREATED)

    def destroy(self, request, *args, **kwargs):
        """处理 FRP 模块的 destroy 业务步骤。"""
        proxy = self.get_object()
        result = services.delete_proxy_from_agent(proxy)
        self._write_audit('delete', proxy, {
            'id': proxy.pk,
            'name': proxy.name,
            'remote_port': proxy.remote_port,
            **result,
        })
        proxy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    @action(detail=True, methods=['post'], url_path='test')
    def test(self, request, pk=None):
        """处理 FRP 模块的 test 业务步骤。"""
        proxy = self.get_object()
        if proxy.status == 'disabled':
            result = {'status': 'disabled', 'detail': '隧道已禁用，不能执行测试。'}
        elif proxy.proxy_type in {'tcp', 'udp'} and proxy.remote_port:
            ok, message, checked_at = services.test_tcp_endpoint(proxy.server.public_host, proxy.remote_port)
            proxy.last_test_status = 'success' if ok else 'failed'
            proxy.last_test_message = message[:240]
            proxy.last_test_at = checked_at
            proxy.status = 'available' if ok else 'unavailable'
            proxy.save(update_fields=['last_test_status', 'last_test_message', 'last_test_at', 'status', 'updated_at'])
            result = {'status': proxy.status, 'detail': proxy.last_test_message}
        else:
            proxy.last_test_status = 'failed'
            proxy.last_test_message = '当前隧道类型缺少可测试的远端端口。'
            proxy.last_test_at = timezone.now()
            proxy.status = 'unavailable'
            proxy.save(update_fields=['last_test_status', 'last_test_message', 'last_test_at', 'status', 'updated_at'])
            result = {'status': proxy.status, 'detail': proxy.last_test_message}
        self._write_audit('test', proxy, {'id': proxy.pk, **result})
        return Response({'proxy': self.get_serializer(proxy).data, **result})

    @action(detail=True, methods=['post'], url_path='disable')
    def disable(self, request, pk=None):
        """处理 FRP 模块的 disable 业务步骤。"""
        proxy = self.get_object()
        proxy, result = services.toggle_proxy_enabled(proxy, False)
        self._write_audit('disable', proxy, {'id': proxy.pk, 'name': proxy.name, 'remote_port': proxy.remote_port, **result})
        return Response({'detail': '\u7aef\u53e3\u5df2\u4e0b\u53d1\u7981\u7528', 'proxy': self.get_serializer(proxy).data, **result})

    @action(detail=True, methods=['post'], url_path='enable')
    def enable(self, request, pk=None):
        """处理 FRP 模块的 enable 业务步骤。"""
        proxy = self.get_object()
        proxy, result = services.toggle_proxy_enabled(proxy, True)
        self._write_audit('enable', proxy, {'id': proxy.pk, 'name': proxy.name, 'remote_port': proxy.remote_port, **result})
        return Response({'detail': '\u7aef\u53e3\u5df2\u4e0b\u53d1\u542f\u7528', 'proxy': self.get_serializer(proxy).data, **result})


class FrpHeartbeatViewSet(FrpBaseViewSet):
    queryset = models.FrpAgentHeartbeat.objects.select_related('organization', 'server', 'agent').all()
    serializer_class = serializers.FrpAgentHeartbeatSerializer
    http_method_names = ['get', 'head', 'options']
    search_fields = ('agent__hostname', 'server__name', 'ip_address', 'message', 'status')


class FrpAuditViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = serializers.FrpAuditSerializer
    pagination_class = FrpPagination

    def get_queryset(self):
        """处理 FRP 模块的 get_queryset 业务步骤。"""
        queryset = scoped_queryset(AuditLog.objects.filter(action__startswith='frp.').order_by('-created_at'), self.request.user)
        keyword = self.request.query_params.get('q', '').strip()
        if keyword:
            queryset = queryset.filter(Q(actor__icontains=keyword) | Q(action__icontains=keyword) | Q(resource__icontains=keyword) | Q(ip_address__icontains=keyword))
        return queryset


def _count_pairs(queryset, key, label_key='name', value_key='value', limit=None):
    """处理 FRP 模块的 _count_pairs 业务步骤。"""
    rows = queryset.values(key).annotate(count=Count('id')).order_by('-count', key)
    if limit:
        rows = rows[:limit]
    return [
        {label_key: row[key] or '未设置', value_key: row['count']}
        for row in rows
    ]


@api_view(['GET'])
def frp_report_center(request):
    """处理 FRP 模块的 frp_report_center 业务步骤。"""
    today = timezone.localdate()
    start_date = today - timedelta(days=6)
    server_qs = scoped_queryset(models.FrpServer.objects.all(), request.user)
    agent_qs = scoped_queryset(models.FrpAgent.objects.all(), request.user)
    proxy_qs = scoped_queryset(models.FrpProxy.objects.select_related('agent'), request.user)
    audit_qs = scoped_queryset(AuditLog.objects.filter(action__startswith='frp.'), request.user)

    audit_trend = []
    for offset in range(7):
        day = start_date + timedelta(days=offset)
        day_audits = audit_qs.filter(created_at__date=day)
        audit_trend.append({
            'date': day.strftime('%m-%d'),
            'audit': day_audits.count(),
            'sync': day_audits.filter(action__icontains='sync').count(),
            'proxy': day_audits.filter(action__icontains='proxy').count(),
        })

    top_agents = [
        {'name': row['hostname'] or row['agent_id'] or '未命名客户端', 'value': row['proxy_count']}
        for row in agent_qs.annotate(proxy_count=Count('proxies')).values('hostname', 'agent_id', 'proxy_count').order_by('-proxy_count', 'hostname')[:8]
    ]
    recent_audits = [
        {
            'id': item.id,
            'time': timezone.localtime(item.created_at).strftime('%Y-%m-%d %H:%M:%S'),
            'actor': item.actor or '-',
            'action': item.action,
            'resource': item.resource or '-',
            'ip_address': item.ip_address or '-',
        }
        for item in audit_qs.order_by('-created_at')[:8]
    ]

    payload = {
        'summary': {
            'server_count': server_qs.count(),
            'available_servers': server_qs.filter(status='available').count(),
            'agent_count': agent_qs.count(),
            'online_agents': agent_qs.filter(status='online').count(),
            'proxy_count': proxy_qs.count(),
            'available_proxies': proxy_qs.filter(status='available').count(),
            'store_enabled_agents': agent_qs.filter(store_enabled=True).count(),
            'audit_count': audit_qs.count(),
        },
        'audit_trend': audit_trend,
        'server_statuses': _count_pairs(server_qs, 'status'),
        'agent_statuses': _count_pairs(agent_qs, 'status'),
        'proxy_statuses': _count_pairs(proxy_qs, 'status'),
        'proxy_types': _count_pairs(proxy_qs, 'proxy_type'),
        'agent_sources': _count_pairs(agent_qs, 'source'),
        'top_agents': top_agents,
        'recent_audits': recent_audits,
    }
    return Response(payload)


@api_view(['GET'])
def frp_traffic_report(request):
    """Return current FRP tunnel traffic counters collected from frps Dashboard."""
    proxy_qs = scoped_queryset(models.FrpProxy.objects.select_related('agent', 'server'), request.user)
    summary = proxy_qs.aggregate(
        traffic_in_bytes=Sum('traffic_in_bytes'),
        traffic_out_bytes=Sum('traffic_out_bytes'),
    )
    today = timezone.localdate()
    today_summary = proxy_qs.filter(traffic_date=today).aggregate(
        traffic_in_bytes=Sum('today_traffic_in_bytes'),
        traffic_out_bytes=Sum('today_traffic_out_bytes'),
    )
    rows = []
    for proxy in proxy_qs.order_by('-traffic_in_bytes', '-traffic_out_bytes', 'name')[:50]:
        rows.append({
            'id': proxy.id,
            'name': proxy.name,
            'agent_name': proxy.agent.hostname or proxy.agent.agent_id,
            'server_name': proxy.server.name,
            'proxy_type': proxy.proxy_type,
            'status': proxy.status,
            'traffic_in_bytes': proxy.traffic_in_bytes,
            'traffic_out_bytes': proxy.traffic_out_bytes,
            'today_traffic_in_bytes': proxy.today_traffic_in_bytes if proxy.traffic_date == today else 0,
            'today_traffic_out_bytes': proxy.today_traffic_out_bytes if proxy.traffic_date == today else 0,
            'today_traffic_total_bytes': (proxy.today_traffic_in_bytes + proxy.today_traffic_out_bytes) if proxy.traffic_date == today else 0,
            'traffic_total_bytes': proxy.traffic_in_bytes + proxy.traffic_out_bytes,
            'traffic_updated_at': timezone.localtime(proxy.traffic_updated_at).strftime('%Y-%m-%d %H:%M:%S') if proxy.traffic_updated_at else '',
        })
    return Response({
        'summary': {
            'traffic_in_bytes': summary['traffic_in_bytes'] or 0,
            'traffic_out_bytes': summary['traffic_out_bytes'] or 0,
            'traffic_total_bytes': (summary['traffic_in_bytes'] or 0) + (summary['traffic_out_bytes'] or 0),
            'today_traffic_in_bytes': today_summary['traffic_in_bytes'] or 0,
            'today_traffic_out_bytes': today_summary['traffic_out_bytes'] or 0,
            'today_traffic_total_bytes': (today_summary['traffic_in_bytes'] or 0) + (today_summary['traffic_out_bytes'] or 0),
            'proxy_count': proxy_qs.count(),
        },
        'tunnels': rows,
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def agent_register(request):
    """处理 FRP 模块的 agent_register 业务步骤。"""
    try:
        agent, created = services.register_agent(request)
    except Exception as exc:
        detail = getattr(exc, 'detail', None) or str(exc)
        return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
    services.write_frp_audit(request, 'agent.register', agent, {
        'agent_id': agent.agent_id,
        'server_code': agent.server.server_code,
        'created': created,
        'approval_status': agent.approval_status,
    }, organization=agent.organization)
    return Response({
        'detail': 'Agent 已注册，等待管理员审核。' if created else 'Agent 信息已刷新。',
        'approval_status': agent.approval_status,
        'status': agent.status,
        'agent_id': agent.agent_id,
    }, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def agent_heartbeat(request):
    """处理 FRP 模块的 agent_heartbeat 业务步骤。"""
    try:
        agent, heartbeat = services.heartbeat_agent(request)
    except Exception as exc:
        detail = getattr(exc, 'detail', None) or str(exc)
        return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
    services.write_frp_audit(request, 'agent.heartbeat', agent, {
        'agent_id': agent.agent_id,
        'server_code': agent.server.server_code,
        'status': heartbeat.status,
        'message': heartbeat.message,
    }, organization=agent.organization)
    return Response({
        'detail': '心跳已接收。',
        'approval_status': agent.approval_status,
        'status': agent.status,
        'reported_at': timezone.localtime(heartbeat.reported_at).strftime('%Y-%m-%d %H:%M:%S'),
    })


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
def agent_config(request):
    """处理 FRP 模块的 agent_config 业务步骤。"""
    try:
        agent, proxies = services.agent_config(request)
    except Exception as exc:
        detail = getattr(exc, 'detail', None) or str(exc)
        return Response({'detail': detail}, status=status.HTTP_400_BAD_REQUEST)
    services.write_frp_audit(request, 'agent.config', agent, {
        'agent_id': agent.agent_id,
        'server_code': agent.server.server_code,
        'proxy_count': len(proxies),
    }, organization=agent.organization)
    return Response({
        'agent_id': agent.agent_id,
        'server_code': agent.server.server_code,
        'proxies': serializers.FrpProxySerializer(proxies, many=True).data,
    })
