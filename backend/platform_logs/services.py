from django.contrib.auth.models import User

from ops.permissions import user_organization

from .models import AuditLog


def write_login_log(username, ip_address, result, reason='', user=None, auth_method='password'):
    """记录不含认证凭据的用户登录结果和认证方式。

    参数：`username` 为登录账号；`ip_address` 为来源地址；`result` 为成功或失败；
    `reason` 为用户友好的结果说明；`user` 为已识别的平台用户；`auth_method` 为认证方式。
    返回：新建的用户登录日志记录。
    副作用：向数据库写入一条用户日志。
    """
    identified_user = user
    if identified_user is None and username:
        identified_user = User.objects.select_related('profile', 'profile__organization').filter(username=username).first()
    return AuditLog.objects.create(
        organization=user_organization(identified_user),
        actor=username or '未知用户',
        action='auth.login.success' if result == 'success' else 'auth.login.failed',
        resource=username or '未知用户',
        ip_address=ip_address,
        detail={
            'status': result,
            'auth_method': auth_method,
            'reason': reason,
        },
    )
