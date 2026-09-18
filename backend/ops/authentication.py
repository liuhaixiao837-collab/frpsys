from django.contrib.auth.models import User
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

from .services.tokens import decode_token, token_matches_auth_version
from .services.login_sessions import touch_login_session
from .services.license_access import license_access_denial
from .services.client_ip import request_client_ip
from .services.platform_security import login_ip_access_result


class JWTAuthentication(BaseAuthentication):
    def authenticate_header(self, request):
        """返回令牌认证失败时使用的认证方案响应头。

        参数：`request` 表示当前请求对象。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        return 'Bearer'

    def authenticate(self, request):
        """解析访问令牌并返回通过认证的平台用户和令牌载荷。

        参数：`request` 表示当前请求对象。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        auth = request.headers.get('Authorization', '')
        if not auth:
            return None
        if not auth.startswith('Bearer '):
            return None

        payload = decode_token(auth.removeprefix('Bearer ').strip(), expected_type='access')
        user = User.objects.select_related('profile').filter(id=payload.get('sub'), is_active=True).first()
        if not user:
            raise AuthenticationFailed('Token 用户不存在或已停用')
        if not token_matches_auth_version(user, payload):
            raise AuthenticationFailed('认证状态已变更，请重新登录')
        ip_allowed, denial_reason = login_ip_access_result(request_client_ip(request))
        if not ip_allowed:
            raise AuthenticationFailed(f'当前来源地址不允许访问：{denial_reason}')
        denial = license_access_denial(user)
        if denial:
            raise AuthenticationFailed(denial['detail'])

        request.auth_payload = payload
        touch_login_session(user, payload)
        return user, payload
