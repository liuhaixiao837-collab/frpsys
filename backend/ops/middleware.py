from platform_logs.models import AuditLog
from .permissions import user_organization
from .services.client_ip import request_client_ip


class ApiAuditMiddleware:
    """为成功的写入类接口统一补记平台审计日志。"""

    MUTATING_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}
    EXCLUDED_SUFFIXES = (
        '/auth/login', '/auth/refresh', '/auth/otp/setup', '/auth/otp/confirm', '/auth/otp/verify',
        '/reset-otp',
    )

    def __init__(self, get_response):
        """初始化实例并保存后续处理所需的依赖和配置。

        参数：`get_response` 表示该步骤所需的get_response 参数。
        返回：无显式返回值。
        副作用：不直接修改持久化数据。
        """
        self.get_response = get_response

    def __call__(self, request):
        """处理当前中间件调用，并将请求继续传递给下游处理器。

        参数：`request` 表示当前请求对象。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：可能读写数据库。
        """
        response = self.get_response(request)
        if (
            request.path.startswith('/api/')
            and request.method in self.MUTATING_METHODS
            and response.status_code < 400
            and not request.path.rstrip('/').endswith(self.EXCLUDED_SUFFIXES)
        ):
            user = getattr(request, 'user', None)
            actor = getattr(user, 'username', '') or 'anonymous'
            AuditLog.objects.create(
                organization=user_organization(user) if getattr(user, 'is_authenticated', False) else None,
                actor=actor,
                action=f'http.{request.method.lower()}',
                resource=request.path,
                ip_address=request_client_ip(request),
                detail={'status': response.status_code},
            )
        return response

