from django.db import models
from django.utils import timezone


class AuditLog(models.Model):
    """记录平台登录尝试和用户业务操作，供日志管理独立查询。"""

    id = models.BigAutoField(primary_key=True, help_text='日志记录主键。')
    created_at = models.DateTimeField(default=timezone.now, help_text='日志记录创建时间。')
    updated_at = models.DateTimeField(auto_now=True, help_text='日志记录最后更新时间。')
    organization = models.ForeignKey(
        'ops.Organization',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='audit_logs',
        help_text='操作发生时用户所属的组织。',
    )
    actor = models.CharField(max_length=80, help_text='执行操作或尝试登录的用户名。')
    action = models.CharField(max_length=120, help_text='具体业务操作代码。')
    resource = models.CharField(max_length=160, help_text='被操作对象的用户友好标识。')
    ip_address = models.GenericIPAddressField(default='127.0.0.1', help_text='发起操作的客户端 IP 地址。')
    detail = models.JSONField(default=dict, blank=True, help_text='用于生成友好详情的结构化操作上下文。')

    class Meta:
        db_table = 'ops_auditlog'
        ordering = ['-created_at']

    def __str__(self):
        """返回执行人、操作和资源组成的审计摘要。"""
        return f'{self.actor}:{self.action}:{self.resource}'
