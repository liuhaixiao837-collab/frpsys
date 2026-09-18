from datetime import datetime, timedelta, timezone as datetime_timezone

from django.utils import timezone

from ops.models import PlatformLoginSession


PLATFORM_SESSION_ACTIVITY_SECONDS = 300


def _payload_expiry(payload):
    """把 JWT 过期时间转换为可比较的时区时间。

    参数：`payload` 为已验签的访问或刷新令牌载荷。
    返回：令牌声明的过期时间；无效时返回当前时间。
    副作用：不修改持久化数据。
    """
    try:
        return datetime.fromtimestamp(int(payload.get('exp') or 0), tz=datetime_timezone.utc)
    except (OverflowError, TypeError, ValueError):
        return timezone.now()


def register_login_session(user, session_id, expires_at, auth_version=0):
    """登记新签发的平台登录会话。

    参数：用户、随机会话标识、最晚有效时间和认证版本。
    返回：新建或更新的平台会话记录。
    副作用：写入平台登录会话台账。
    """
    now = timezone.now()
    session, _created = PlatformLoginSession.objects.update_or_create(
        session_id=str(session_id),
        defaults={
            'user': user,
            'auth_version': int(auth_version or 0),
            'last_seen_at': now,
            'expires_at': expires_at,
            'revoked_at': None,
        },
    )
    return session


def touch_login_session(user, payload):
    """在访问令牌通过鉴权时续活对应平台会话。

    参数：`user` 为认证用户；`payload` 为已验签访问令牌载荷。
    返回：已续活的平台会话记录；缺少标识时返回 None。
    副作用：更新最近活动时间，旧版令牌首次访问时补建会话。
    """
    session_id = str(payload.get('sid') or payload.get('jti') or '').strip()
    if not session_id:
        return None
    now = timezone.now()
    expires_at = _payload_expiry(payload)
    auth_version = int(payload.get('auth_version') or 0)
    session = PlatformLoginSession.objects.filter(session_id=session_id, user=user).first()
    if not session:
        return register_login_session(user, session_id, expires_at, auth_version)
    session.last_seen_at = now
    session.auth_version = auth_version
    session.revoked_at = None
    if expires_at > session.expires_at:
        session.expires_at = expires_at
    session.save(update_fields=['last_seen_at', 'auth_version', 'revoked_at', 'expires_at', 'updated_at'])
    return session


def revoke_login_session(payload):
    """撤销当前令牌关联的平台登录会话。

    参数：`payload` 为当前访问令牌载荷。
    返回：被更新的会话数量。
    副作用：写入会话撤销时间。
    """
    session_id = str(payload.get('sid') or payload.get('jti') or '').strip()
    if not session_id:
        return 0
    return PlatformLoginSession.objects.filter(session_id=session_id, revoked_at=None).update(
        revoked_at=timezone.now(),
        updated_at=timezone.now(),
    )


def revoke_user_login_sessions(user):
    """撤销用户因安全状态变更而失效的全部平台会话。

    参数：`user` 为被重置密码或认证因素的用户。
    返回：被更新的会话数量。
    副作用：批量写入会话撤销时间。
    """
    now = timezone.now()
    return PlatformLoginSession.objects.filter(user=user, revoked_at=None).update(
        revoked_at=now,
        updated_at=now,
    )


def active_platform_sessions(now=None):
    """返回仍有效且近期有平台活动的登录会话查询集。

    参数：`now` 为可选统计时刻。
    返回：可继续聚合的平台会话 QuerySet。
    副作用：只读取数据库。
    """
    current_time = now or timezone.now()
    activity_start = current_time - timedelta(seconds=PLATFORM_SESSION_ACTIVITY_SECONDS)
    return PlatformLoginSession.objects.filter(
        user__is_active=True,
        revoked_at=None,
        expires_at__gt=current_time,
        last_seen_at__gte=activity_start,
    )
