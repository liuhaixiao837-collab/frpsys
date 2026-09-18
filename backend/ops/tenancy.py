from django.db.models import Q

from .permissions import user_organization
from .services.system_admin import is_system_admin


def organization_scope_ids(user):
    """返回当前组织数据隔离范围内允许访问的组织主键。

    参数：`user` 表示当前或目标用户。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：可能读写数据库。
    """
    if not user or not getattr(user, 'is_authenticated', False):
        return []
    if is_system_admin(user):
        return None
    organization = user_organization(user)
    if not organization:
        return []

    ids = {organization.id}
    pending = [organization.id]
    while pending:
        child_ids = list(organization.__class__.objects.filter(parent_id__in=pending).values_list('id', flat=True))
        pending = [item for item in child_ids if item not in ids]
        ids.update(pending)
    return list(ids)


def scoped_queryset(queryset, user):
    """按当前用户组织范围过滤业务查询集。

    参数：`queryset` 表示待过滤或处理的查询集；`user` 表示当前或目标用户。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    scope_ids = organization_scope_ids(user)
    organization = user_organization(user)
    model = queryset.model
    fields = {field.name for field in model._meta.fields}

    if 'organization' in fields:
        if scope_ids is None:
            return queryset
        if scope_ids:
            return queryset.filter(Q(organization_id__in=scope_ids) | Q(organization__isnull=True))
        return queryset.filter(organization__isnull=True)

    if 'device' in fields and organization:
        if scope_ids is None:
            return queryset
        return queryset.filter(Q(device__organization_id__in=scope_ids) | Q(device__organization__isnull=True))

    if 'incident' in fields and organization:
        if scope_ids is None:
            return queryset
        return queryset.filter(Q(incident__organization_id__in=scope_ids) | Q(incident__organization__isnull=True))

    if 'session' in fields and organization:
        if scope_ids is None:
            return queryset
        return queryset.filter(Q(session__organization_id__in=scope_ids) | Q(session__organization__isnull=True))

    return queryset


def assign_organization(instance, user):
    """为新建或更新记录分配当前用户所属组织。

    参数：`instance` 表示待更新的模型实例；`user` 表示当前或目标用户。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    organization = user_organization(user)
    if organization and hasattr(instance, 'organization_id') and not instance.organization_id:
        instance.organization = organization
    return instance
