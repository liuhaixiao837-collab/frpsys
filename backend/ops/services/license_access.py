from .license_management import license_public_metadata
from .login_sessions import active_platform_sessions
from .system_admin import SYSTEM_ADMIN_USERNAME, is_system_admin


LICENSE_VALID = 'valid'
LICENSE_EXPIRED = 'expired'
LICENSE_UNCONFIGURED = 'unconfigured'
LICENSE_UNAVAILABLE = 'unavailable'


def current_license_metadata(now=None):
    """读取 Licence 配置并返回动态公开元数据。

    参数：`now` 为测试场景可传入的当前时间。
    返回：包含状态、授权用户数和并发数等字段的安全公开元数据。
    副作用：读取 `license.management`，并可能推进防时间回拨高水位。
    """
    from ops.models import SystemSetting

    setting = SystemSetting.objects.filter(key='license.management').order_by('id').first()
    return license_public_metadata(setting.value if setting else {}, now=now)


def current_license_status(now=None):
    """读取 Licence 配置并归一为四种对外状态。

    参数：`now` 为测试场景可传入的当前时间。
    返回：`valid`、`expired`、`unconfigured` 或 `unavailable`。
    副作用：读取 `license.management`，并可能推进防时间回拨高水位。
    """
    metadata = current_license_metadata(now=now)
    status = metadata.get('status')
    if status == LICENSE_VALID:
        return LICENSE_VALID
    if status == LICENSE_EXPIRED:
        return LICENSE_EXPIRED
    if status == LICENSE_UNAVAILABLE:
        return LICENSE_UNAVAILABLE
    return LICENSE_UNCONFIGURED


def license_user_limit_denial(activating_users=1, now=None):
    """检查新增或重新启用用户是否会超过 Licence 授权用户数。

    参数：`activating_users` 为本次操作新增的启用用户数；`now` 为测试时刻。
    返回：额度足够或 Licence 非有效状态时返回空值，超限时返回错误信息。
    副作用：读取 Licence 配置和启用用户总数，不修改数据库。
    """
    from django.contrib.auth.models import User

    metadata = current_license_metadata(now=now)
    if metadata.get('status') != LICENSE_VALID:
        return None
    try:
        limit = int(metadata.get('max_users') or 0)
        requested = max(0, int(activating_users or 0))
    except (TypeError, ValueError):
        limit = 0
        requested = 0
    active_users = User.objects.filter(is_active=True).count()
    if active_users + requested <= limit:
        return None
    return {
        'status': LICENSE_VALID,
        'code': 'LICENSE_USER_LIMIT_EXCEEDED',
        'detail': f'Licence 授权用户数不足，当前最多允许 {limit} 个启用用户',
    }


def license_concurrency_denial(user, now=None):
    """检查新登录用户是否超过 Licence 并发用户数。

    参数：`user` 为已完成全部认证因素的用户；`now` 为测试时刻。
    返回：admin、已有活动会话或额度充足时返回空值，超限时返回错误信息。
    副作用：读取 Licence 配置及最近五分钟内的活动平台会话，不修改数据库。
    """
    if is_system_admin(user):
        return None
    metadata = current_license_metadata(now=now)
    if metadata.get('status') != LICENSE_VALID:
        return None
    try:
        limit = int(metadata.get('max_concurrency') or 0)
    except (TypeError, ValueError):
        limit = 0
    active_user_ids = active_platform_sessions(now=now).exclude(
        user__username=SYSTEM_ADMIN_USERNAME,
    ).values_list('user_id', flat=True).distinct()
    if active_user_ids.filter(user_id=user.id).exists():
        return None
    if active_user_ids.count() < limit:
        return None
    return {
        'status': LICENSE_VALID,
        'code': 'LICENSE_CONCURRENCY_EXCEEDED',
        'detail': f'当前在线用户数已达到 Licence 并发上限（{limit} 人），请稍后重试或联系管理员扩容',
    }


def license_access_denial(user, now=None):
    """返回当前用户因 Licence 状态无法使用系统时的错误信息。

    参数：`user` 为已通过身份认证的用户；`now` 为测试可传入的当前时间。
    返回：admin 或有效 Licence 返回空值，其他情况返回状态、错误码和中文说明。
    副作用：读取 Licence 配置，不写数据库或日志。
    """
    if is_system_admin(user):
        return None
    status = current_license_status(now=now)
    if status == LICENSE_VALID:
        return None
    if status == LICENSE_EXPIRED:
        return {
            'status': status,
            'code': 'LICENSE_EXPIRED',
            'detail': '系统 Licence 已过期，请联系超级管理员更新授权',
        }
    if status == LICENSE_UNAVAILABLE:
        return {
            'status': status,
            'code': 'LICENSE_UNAVAILABLE',
            'detail': '系统 Licence 当前不可用，请联系超级管理员处理授权或时间异常',
        }
    return {
        'status': LICENSE_UNCONFIGURED,
        'code': 'LICENSE_UNCONFIGURED',
        'detail': '系统 Licence 未配置，请联系超级管理员完成授权',
    }


def license_allows_user(user, now=None):
    """判断用户在当前 Licence 状态下是否可以使用系统。

    参数：`user` 为待检查用户；`now` 为测试可传入的当前时间。
    返回：admin 或 Licence 有效时返回真，否则返回假。
    副作用：读取 Licence 配置，不修改数据库。
    """
    return license_access_denial(user, now=now) is None
