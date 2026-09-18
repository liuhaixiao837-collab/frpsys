from django.core.exceptions import ValidationError


SYSTEM_ADMIN_USERNAME = 'admin'


def is_system_admin(user):
    """判断用户是否为系统唯一的超级管理员 admin。

    参数：`user` 为待判断的 Django 用户或匿名用户。
    返回：仅精确用户名为 admin 且启用、具备 staff 和 superuser 标记时返回真。
    副作用：不读取或修改数据库。
    """
    return bool(
        user
        and getattr(user, 'is_authenticated', False)
        and getattr(user, 'username', '') == SYSTEM_ADMIN_USERNAME
        and getattr(user, 'is_active', False)
        and getattr(user, 'is_staff', False)
        and getattr(user, 'is_superuser', False)
    )


def enforce_system_admin_invariant(instance):
    """在用户保存前强制执行唯一 admin 超级管理员约束。

    参数：`instance` 为即将保存的 Django 用户实例。
    返回：无显式返回值。
    副作用：读取原用户名称；为 admin 固定管理员标记，并拒绝保留名、改名和其他超级管理员。
    """
    username = str(getattr(instance, 'username', '') or '').strip()
    if username.casefold() == SYSTEM_ADMIN_USERNAME and username != SYSTEM_ADMIN_USERNAME:
        raise ValidationError('用户名 admin 为系统保留名称，不区分大小写')

    if instance.pk:
        original_username = (
            instance.__class__.objects.filter(pk=instance.pk).values_list('username', flat=True).first()
        )
        if original_username == SYSTEM_ADMIN_USERNAME and username != SYSTEM_ADMIN_USERNAME:
            raise ValidationError('系统超级管理员 admin 不允许修改用户名')

    if username == SYSTEM_ADMIN_USERNAME:
        instance.is_superuser = True
        instance.is_staff = True
        instance.is_active = True
        return
    if getattr(instance, 'is_superuser', False):
        raise ValidationError('系统只允许 admin 作为超级管理员')
