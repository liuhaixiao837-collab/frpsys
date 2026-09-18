from django.db.models import Q
from django.http import HttpResponse
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.decorators import action

from ops.permissions import user_organization
from ops.services.client_ip import request_client_ip
from ops.tenancy import scoped_queryset

from .export import (
    apply_log_time_range,
    build_log_workbook,
    filter_export_logs,
    parse_log_time_range,
)
from .models import AuditLog
from .serializers import AuditLogSerializer


class BaseLogViewSet(viewsets.ReadOnlyModelViewSet):
    """为用户日志和系统日志提供统一的只读查询能力。"""

    queryset = AuditLog.objects.all()
    serializer_class = AuditLogSerializer
    export_kind = ''

    def base_queryset(self):
        """返回由具体日志页面限定类型和组织范围的基础查询集。"""
        return scoped_queryset(self.queryset, self.request.user)

    def filtered_queryset(self, queryset):
        """按关键词和时间范围筛选日志列表。"""
        query = self.request.query_params.get('q', '').strip()
        start_time, end_time = parse_log_time_range(self.request.query_params)
        queryset = apply_log_time_range(queryset, start_time, end_time)
        if query:
            queryset = queryset.filter(
                Q(actor__icontains=query)
                | Q(action__icontains=query)
                | Q(resource__icontains=query)
                | Q(ip_address__icontains=query)
            )
        return queryset.order_by('-created_at')

    @action(detail=False, methods=['get'], url_path='export')
    def export(self, request):
        """按页面当前筛选条件导出最多一百八十天的全部匹配日志。"""
        start_time, end_time = parse_log_time_range(
            request.query_params,
            require_complete=True,
            enforce_limit=True,
        )
        queryset = apply_log_time_range(self.base_queryset(), start_time, end_time).order_by('-created_at')
        rows = filter_export_logs(list(queryset), self.export_kind, request.query_params)
        content = build_log_workbook(rows, self.export_kind, start_time, end_time, request.query_params)
        AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='AuditLog.export',
            resource='用户日志' if self.export_kind == 'user' else '系统日志',
            ip_address=request_client_ip(request),
            detail={
                'rows': len(rows),
                'start_time': start_time.isoformat(),
                'end_time': end_time.isoformat(),
            },
        )
        timestamp = timezone.localtime().strftime('%Y%m%d-%H%M%S')
        filename = f'{self.export_kind}-logs-{timestamp}.xlsx'
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        response['Cache-Control'] = 'no-store'
        return response


class UserLogViewSet(BaseLogViewSet):
    """只读查询登录时间、结果和认证方式等用户登录日志。"""

    permission_code = 'page.logs.users.view'
    export_kind = 'user'

    def base_queryset(self):
        """只返回当前数据范围内的登录日志。"""
        return super().base_queryset().filter(action__startswith='auth.login')

    def get_queryset(self):
        """只返回登录尝试记录并应用通用查询条件。"""
        return self.filtered_queryset(self.base_queryset())


class SystemLogViewSet(BaseLogViewSet):
    """只读查询登录以外的用户业务行为和系统操作日志。"""

    permission_code = 'page.logs.system.view'
    export_kind = 'system'

    def base_queryset(self):
        """只返回当前数据范围内的非登录系统日志。"""
        return super().base_queryset().exclude(action__startswith='auth.login')

    def get_queryset(self):
        """返回全部非登录行为，包含中间件补记的写操作。"""
        return self.filtered_queryset(self.base_queryset())
