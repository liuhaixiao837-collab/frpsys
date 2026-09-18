from datetime import timedelta
from uuid import uuid4

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed


DEFAULT_SESSION_TIMEOUT_SECONDS = int(getattr(settings, 'ONGRID_ACCESS_TOKEN_MINUTES', 30)) * 60
ALGORITHM = 'HS256'


def session_timeout_seconds():
    """读取并限制平台会话空闲超时秒数。

    参数：无。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    try:
        from ops.models import SystemSetting
        setting = SystemSetting.objects.filter(key='security').order_by('organization_id', 'id').first()
        value = setting.value if setting and isinstance(setting.value, dict) else {}
        seconds = int(value.get('session_timeout') or DEFAULT_SESSION_TIMEOUT_SECONDS)
    except Exception:
        seconds = DEFAULT_SESSION_TIMEOUT_SECONDS
    return max(60, seconds)


def access_token_seconds():
    """根据平台设置计算访问令牌有效期秒数。

    参数：无。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    timeout = session_timeout_seconds()
    return max(60, min(1800, timeout // 2))


def _profile_claims(user):
    """生成令牌中使用的用户组织和身份摘要声明。

    参数：`user` 表示当前或目标用户。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    profile = getattr(user, 'profile', None)
    organization = getattr(profile, 'organization', None) if profile else None
    role_code = getattr(profile, 'role', 'viewer') if profile else 'viewer'
    role_name = role_code
    try:
        from ops.models import Role
        role = Role.objects.filter(code=role_code).first()
        if role:
            role_name = role.name
    except Exception:
        pass
    return {
        'role': role_code,
        'role_name': role_name,
        'org_id': organization.id if organization else None,
        'org_slug': organization.slug if organization else '',
        'auth_version': int(getattr(profile, 'auth_version', 0) or 0) if profile else 0,
    }


def token_matches_auth_version(user, payload):
    """校验 JWT 中的认证版本是否仍与用户档案一致。

    参数：`user` 为令牌关联用户；`payload` 为已验签的 JWT 载荷。
    返回：版本一致时返回真，重置认证因素后返回假。
    副作用：只读取用户档案，不修改数据库。
    """
    profile = getattr(user, 'profile', None)
    current = int(getattr(profile, 'auth_version', 0) or 0) if profile else 0
    try:
        issued = int(payload.get('auth_version', 0) or 0)
    except (TypeError, ValueError):
        return False
    return current == issued


def issue_token(user, token_type='access', ttl=None, session_id=None):
    """签发包含用户身份、类型和有效期的 JWT。

    参数：`user` 表示当前或目标用户；`token_type` 表示该步骤所需的token_type 参数；`ttl` 表示该步骤所需的ttl 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    now = timezone.now()
    ttl = ttl or timedelta(seconds=access_token_seconds() if token_type == 'access' else session_timeout_seconds())
    payload = {
        'iss': 'ongrid-local',
        'jti': str(uuid4()),
        'type': token_type,
        'sub': str(user.id),
        'username': user.username,
        'iat': int(now.timestamp()),
        'exp': int((now + ttl).timestamp()),
        'sid': str(session_id or uuid4()),
        **_profile_claims(user),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=ALGORITHM)


def issue_pair(user, session_id=None):
    """为已认证用户签发访问令牌和刷新令牌。

    参数：`user` 表示当前或目标用户。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    access_seconds = access_token_seconds()
    refresh_seconds = session_timeout_seconds()
    session_id = str(session_id or uuid4())
    refresh_expires_at = timezone.now() + timedelta(seconds=refresh_seconds)
    result = {
        'access': issue_token(user, 'access', ttl=timedelta(seconds=access_seconds), session_id=session_id),
        'refresh': issue_token(user, 'refresh', ttl=timedelta(seconds=refresh_seconds), session_id=session_id),
        'token_type': 'Bearer',
        'expires_in': access_seconds,
    }
    from ops.services.login_sessions import register_login_session
    profile = getattr(user, 'profile', None)
    register_login_session(
        user,
        session_id,
        refresh_expires_at,
        int(getattr(profile, 'auth_version', 0) or 0) if profile else 0,
    )
    return result


def issue_access_from_refresh(user, refresh_payload):
    """校验刷新令牌后签发新的访问令牌。

    参数：`user` 表示当前或目标用户；`refresh_payload` 表示该步骤所需的refresh_payload 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    now_ts = int(timezone.now().timestamp())
    refresh_expires_at = int(refresh_payload.get('exp') or 0)
    remaining_seconds = refresh_expires_at - now_ts
    if remaining_seconds <= 0:
        raise AuthenticationFailed('Token 已过期')
    return issue_pair(user, session_id=refresh_payload.get('sid'))


def decode_token(token, expected_type='access'):
    """校验 JWT 签名、类型和有效期并返回载荷。

    参数：`token` 表示该步骤所需的token 参数；`expected_type` 表示该步骤所需的expected_type 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[ALGORITHM], issuer='ongrid-local')
    except jwt.ExpiredSignatureError as exc:
        raise AuthenticationFailed('Token 已过期') from exc
    except jwt.InvalidTokenError as exc:
        raise AuthenticationFailed('Token 无效') from exc

    if payload.get('type') != expected_type:
        raise AuthenticationFailed('Token 类型不匹配')
    return payload
