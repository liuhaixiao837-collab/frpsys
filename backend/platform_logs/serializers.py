from rest_framework import serializers

from .models import AuditLog


class AuditLogSerializer(serializers.ModelSerializer):
    """输出审计日志业务字段，不暴露模型内部关联信息。"""

    class Meta:
        model = AuditLog
        fields = ['id', 'actor', 'action', 'resource', 'ip_address', 'detail', 'created_at']
        read_only_fields = fields
