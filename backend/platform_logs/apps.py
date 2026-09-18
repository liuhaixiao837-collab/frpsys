from django.apps import AppConfig


class PlatformLogsConfig(AppConfig):
    """注册通用平台日志模型与接口能力。"""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'platform_logs'
    verbose_name = '平台日志'
