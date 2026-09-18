from functools import lru_cache

from django.contrib.auth.models import AnonymousUser
from django.db.models import Q

from .permission_catalog import all_permission_codes, catalog_payload, catalog_signature, page_code_for_path
from .services.system_admin import is_system_admin


def _department_ids_for_user(user):
    """返回用户当前部门及全部上级部门 ID，用于继承部门策略。"""
    profile = getattr(user, 'profile', None)
    organization = getattr(profile, 'organization', None) if profile else None
    if not organization:
        return []
    ids = [organization.id]
    cursor = organization.parent
    while cursor:
        ids.append(cursor.id)
        cursor = cursor.parent
    return ids


def is_permission_admin(user):
    """判断用户是否为拥有全部目录权限的平台管理员。"""
    if not user or isinstance(user, AnonymousUser) or not user.is_authenticated:
        return False
    return is_system_admin(user)


@lru_cache(maxsize=512)
def _effective_permission_codes_cached(user_id, department_id, is_admin, catalog_signature):
    """计算并缓存用户在当前部门和目录版本下的有效权限。"""
    from django.contrib.auth.models import User
    from .models import PermissionPolicy

    if is_admin:
        return tuple(all_permission_codes())

    user = User.objects.select_related('profile', 'profile__organization').filter(pk=user_id).first()
    if not user:
        return tuple()

    allowed = set()
    denied = set()

    department_ids = _department_ids_for_user(user)
    policies = PermissionPolicy.objects.prefetch_related('rules').filter(status='available').filter(
        Q(subject_type='department', department_id__in=department_ids) |
        Q(subject_type='user', user_id=user.id)
    ).order_by('priority', 'subject_type', 'id')

    for policy in policies:
        policy_allow = {rule.permission_code for rule in policy.rules.all() if rule.effect == 'allow'}
        policy_deny = {rule.permission_code for rule in policy.rules.all() if rule.effect == 'deny'}

        if policy.subject_type == 'user':
            allowed.difference_update(policy_deny)
            denied.update(policy_deny)
            allowed.update(policy_allow)
            denied.difference_update(policy_allow)
        else:
            allowed.update(policy_allow)
            denied.update(policy_deny)

    allowed.difference_update(denied)
    return tuple(sorted(allowed))


def clear_permission_cache():
    """在策略或权限目录变化后清空有效权限缓存。"""
    _effective_permission_codes_cached.cache_clear()


def effective_permission_codes(user):
    """返回指定用户当前生效的权限代码列表。"""
    if not user or not user.is_authenticated:
        return []
    profile = getattr(user, 'profile', None)
    department_id = getattr(getattr(profile, 'organization', None), 'id', None) if profile else None
    return list(_effective_permission_codes_cached(
        user.id,
        department_id,
        is_permission_admin(user),
        catalog_signature(),
    ))


def has_permission(user, code):
    """判断用户是否拥有指定功能权限。"""
    if not code:
        return True
    if is_permission_admin(user):
        return True
    permissions = set(effective_permission_codes(user))
    return code in permissions


def permission_payload_for_user(user):
    """返回用户有效权限及当前数据库权限目录。"""
    return {
        'permissions': effective_permission_codes(user),
        'catalog': catalog_payload(),
    }


def page_permission_for_request_path(path):
    """将 API 请求路径转换为数据库中的页面权限代码。"""
    path = (path or '').split('/api/v1', 1)[-1]
    if path.startswith('/'):
        return page_code_for_path(path)
    return ''
