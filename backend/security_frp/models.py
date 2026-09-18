import hashlib

from django.db import models
from django.utils import timezone

from ops.model_docs import apply_model_field_help
from ops.models import Organization, TimeStampedModel


class FrpServer(TimeStampedModel):
    """保存平台管理员维护的 FRP 服务端接入配置。"""

    STATUSES = [
        ('available', '可用'),
        ('configured', '已配置'),
        ('unconfigured', '未配置'),
        ('unavailable', '不可用'),
        ('disabled', '已禁用'),
    ]
    TEST_STATUSES = [
        ('not_tested', '未测试'),
        ('success', '测试成功'),
        ('failed', '测试失败'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='frp_servers', verbose_name='组织')
    name = models.CharField(max_length=120, verbose_name='服务端名称')
    server_code = models.SlugField(max_length=120, verbose_name='服务端编码')
    public_host = models.CharField(max_length=180, verbose_name='公网地址')
    bind_port = models.PositiveIntegerField(default=7000, verbose_name='FRP 服务端端口')
    allow_ports = models.CharField(max_length=240, blank=True, verbose_name='允许映射端口范围')
    dashboard_host = models.CharField(max_length=180, blank=True, verbose_name='Dashboard 地址')
    dashboard_port = models.PositiveIntegerField(default=7500, verbose_name='Dashboard 端口')
    dashboard_username = models.CharField(max_length=120, blank=True, verbose_name='Dashboard 用户名')
    encrypted_dashboard_password = models.TextField(blank=True, verbose_name='Dashboard 密码密文')
    encrypted_auth_token = models.TextField(blank=True, verbose_name='FRP 认证 Token 密文')
    allow_register = models.BooleanField(default=True, verbose_name='允许 Agent 注册')
    max_agents = models.PositiveIntegerField(default=200, verbose_name='最大接入数量')
    status = models.CharField(max_length=32, choices=STATUSES, default='configured', verbose_name='状态')
    last_test_status = models.CharField(max_length=32, choices=TEST_STATUSES, default='not_tested', verbose_name='最近测试状态')
    last_test_message = models.CharField(max_length=240, blank=True, verbose_name='最近测试结果')
    last_test_at = models.DateTimeField(null=True, blank=True, verbose_name='最近测试时间')
    remark = models.TextField(blank=True, verbose_name='备注')

    class Meta:
        ordering = ['name']
        unique_together = [('organization', 'server_code')]
        indexes = [
            models.Index(fields=['organization', 'status'], name='frp_server_org_status_idx'),
            models.Index(fields=['server_code'], name='frp_server_code_idx'),
        ]

    def __str__(self):
        """处理 FRP 模块的 __str__ 业务步骤。"""
        return self.name

    @property
    def has_auth_token(self):
        """处理 FRP 模块的 has_auth_token 业务步骤。"""
        return bool(self.encrypted_auth_token)

    @property
    def has_dashboard_password(self):
        """处理 FRP 模块的 has_dashboard_password 业务步骤。"""
        return bool(self.encrypted_dashboard_password)

class FrpAgent(TimeStampedModel):
    """保存注册到服务端并等待平台审核的 FRP 客户端。"""

    SOURCES = [
        ('manual', '手动维护'),
        ('frps_dashboard', 'frps Dashboard'),
        ('agent_report', 'Agent 上报'),
    ]
    APPROVAL_STATUSES = [
        ('pending', '待审核'),
        ('approved', '已通过'),
        ('rejected', '已拒绝'),
    ]
    STATUSES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('unavailable', '异常'),
        ('disabled', '已禁用'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='frp_agents', verbose_name='组织')
    server = models.ForeignKey(FrpServer, on_delete=models.CASCADE, related_name='agents', verbose_name='所属服务端')
    agent_id = models.CharField(max_length=160, verbose_name='Agent ID')
    fingerprint = models.CharField(max_length=128, verbose_name='机器指纹')
    hostname = models.CharField(max_length=160, blank=True, verbose_name='主机名')
    client_ip = models.GenericIPAddressField(null=True, blank=True, verbose_name='注册来源 IP')
    source = models.CharField(max_length=32, choices=SOURCES, default='manual', verbose_name='来源')
    admin_host = models.CharField(max_length=180, blank=True, verbose_name='frpc Admin API 地址')
    admin_port = models.PositiveIntegerField(null=True, blank=True, verbose_name='frpc Admin API 端口')
    admin_username = models.CharField(max_length=120, blank=True, verbose_name='frpc Admin API 用户名')
    encrypted_admin_password = models.TextField(blank=True, verbose_name='frpc Admin API 密码密文')
    admin_proxy_name = models.CharField(max_length=160, blank=True, verbose_name='frpc 管理隧道名称')
    admin_proxy_remote_addr = models.CharField(max_length=240, blank=True, verbose_name='frpc 管理隧道远端地址')
    store_enabled = models.BooleanField(default=False, verbose_name='frpc Store API 已启用')
    runtime_proxy_count = models.PositiveIntegerField(default=0, verbose_name='运行隧道数量')
    tags = models.JSONField(default=list, blank=True, verbose_name='标签')
    metadata = models.JSONField(default=dict, blank=True, verbose_name='上报元数据')
    approval_status = models.CharField(max_length=32, choices=APPROVAL_STATUSES, default='pending', verbose_name='审核状态')
    status = models.CharField(max_length=32, choices=STATUSES, default='offline', verbose_name='在线状态')
    last_heartbeat_at = models.DateTimeField(null=True, blank=True, verbose_name='最近心跳时间')
    last_seen_at = models.DateTimeField(null=True, blank=True, verbose_name='最近上报时间')
    last_error = models.CharField(max_length=240, blank=True, verbose_name='最近错误')
    approved_by = models.CharField(max_length=120, blank=True, verbose_name='审核人')
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name='审核时间')
    rejected_by = models.CharField(max_length=120, blank=True, verbose_name='拒绝人')
    rejected_at = models.DateTimeField(null=True, blank=True, verbose_name='拒绝时间')
    reject_reason = models.CharField(max_length=240, blank=True, verbose_name='拒绝原因')
    remark = models.TextField(blank=True, verbose_name='备注')

    class Meta:
        ordering = ['-last_seen_at', 'hostname']
        unique_together = [('organization', 'server', 'fingerprint')]
        indexes = [
            models.Index(fields=['organization', 'approval_status'], name='frp_agent_org_approval_idx'),
            models.Index(fields=['organization', 'status'], name='frp_agent_org_status_idx'),
            models.Index(fields=['fingerprint'], name='frp_agent_fingerprint_idx'),
        ]

    def __str__(self):
        """处理 FRP 模块的 __str__ 业务步骤。"""
        return self.hostname or self.agent_id

    @staticmethod
    def build_fingerprint(hostname=''):
        """处理 FRP 模块的 build_fingerprint 业务步骤。"""
        return hashlib.sha256((hostname or '').encode('utf-8')).hexdigest()

    @property
    def has_admin_password(self):
        """处理 FRP 模块的 has_admin_password 业务步骤。"""
        return bool(self.encrypted_admin_password)


class FrpProxy(TimeStampedModel):
    """保存下发到已审核 FRP 客户端的代理隧道配置。"""

    PROXY_TYPES = [
        ('tcp', 'TCP'),
        ('udp', 'UDP'),
        ('http', 'HTTP'),
        ('https', 'HTTPS'),
        ('stcp', 'STCP'),
        ('xtcp', 'XTCP'),
    ]
    STATUSES = [
        ('available', '可用'),
        ('configured', '已配置'),
        ('unavailable', '不可用'),
        ('disabled', '已禁用'),
    ]
    TEST_STATUSES = [
        ('not_tested', '未测试'),
        ('success', '测试成功'),
        ('failed', '测试失败'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='frp_proxies', verbose_name='组织')
    server = models.ForeignKey(FrpServer, on_delete=models.CASCADE, related_name='proxies', verbose_name='所属服务端')
    agent = models.ForeignKey(FrpAgent, on_delete=models.CASCADE, related_name='proxies', verbose_name='所属 Agent')
    name = models.CharField(max_length=120, verbose_name='代理名称')
    proxy_type = models.CharField(max_length=16, choices=PROXY_TYPES, default='tcp', verbose_name='代理类型')
    local_ip = models.CharField(max_length=120, default='127.0.0.1', verbose_name='本地地址')
    local_port = models.PositiveIntegerField(default=22, verbose_name='本地端口')
    remote_port = models.PositiveIntegerField(null=True, blank=True, verbose_name='远端端口')
    custom_domains = models.JSONField(default=list, blank=True, verbose_name='自定义域名')
    subdomain = models.CharField(max_length=120, blank=True, verbose_name='子域名')
    status = models.CharField(max_length=32, choices=STATUSES, default='configured', verbose_name='状态')
    last_test_status = models.CharField(max_length=32, choices=TEST_STATUSES, default='not_tested', verbose_name='最近测试状态')
    last_test_message = models.CharField(max_length=240, blank=True, verbose_name='最近测试结果')
    last_test_at = models.DateTimeField(null=True, blank=True, verbose_name='最近测试时间')
    traffic_in_bytes = models.PositiveBigIntegerField(default=0, verbose_name='入站流量字节数')
    traffic_out_bytes = models.PositiveBigIntegerField(default=0, verbose_name='出站流量字节数')
    today_traffic_in_bytes = models.PositiveBigIntegerField(default=0, verbose_name='今日入站流量字节数')
    today_traffic_out_bytes = models.PositiveBigIntegerField(default=0, verbose_name='今日出站流量字节数')
    traffic_source_in_bytes = models.PositiveBigIntegerField(default=0, verbose_name='最近源入站流量字节数')
    traffic_source_out_bytes = models.PositiveBigIntegerField(default=0, verbose_name='最近源出站流量字节数')
    traffic_date = models.DateField(null=True, blank=True, verbose_name='流量统计日期')
    traffic_updated_at = models.DateTimeField(null=True, blank=True, verbose_name='流量更新时间')
    remark = models.TextField(blank=True, verbose_name='备注')

    class Meta:
        ordering = ['server__name', 'name']
        unique_together = [('organization', 'server', 'name')]
        indexes = [
            models.Index(fields=['organization', 'status'], name='frp_proxy_org_status_idx'),
            models.Index(fields=['server', 'agent'], name='frp_proxy_server_agent_idx'),
        ]

    def __str__(self):
        """处理 FRP 模块的 __str__ 业务步骤。"""
        return self.name


class FrpAgentHeartbeat(TimeStampedModel):
    """保存 FRP 客户端心跳历史，供在线状态排查。"""

    STATUSES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('error', '异常'),
    ]

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, null=True, blank=True, related_name='frp_heartbeats', verbose_name='组织')
    server = models.ForeignKey(FrpServer, on_delete=models.CASCADE, related_name='heartbeats', verbose_name='所属服务端')
    agent = models.ForeignKey(FrpAgent, on_delete=models.CASCADE, related_name='heartbeats', verbose_name='所属 Agent')
    status = models.CharField(max_length=32, choices=STATUSES, default='online', verbose_name='状态')
    ip_address = models.GenericIPAddressField(null=True, blank=True, verbose_name='来源 IP')
    message = models.CharField(max_length=240, blank=True, verbose_name='消息')
    metrics = models.JSONField(default=dict, blank=True, verbose_name='指标')
    reported_at = models.DateTimeField(default=timezone.now, verbose_name='上报时间')

    class Meta:
        ordering = ['-reported_at']
        indexes = [
            models.Index(fields=['organization', 'reported_at'], name='frp_heartbeat_org_time_idx'),
            models.Index(fields=['agent', 'reported_at'], name='frp_heartbeat_agent_time_idx'),
        ]

    def __str__(self):
        """处理 FRP 模块的 __str__ 业务步骤。"""
        return f'{self.agent} {self.status}'


apply_model_field_help(globals())
