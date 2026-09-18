import json
import os
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import User
from django.core import signing
from django.core.cache import cache
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, StreamingHttpResponse
from django.utils import timezone
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from . import models, serializers
from .permission_catalog import (
    ROOT_MENU_ORDER_KEY,
    catalog_payload,
    menu_order_items_for_user,
    navigation_payload_for_user,
)
from .permission_service import clear_permission_cache
from .permissions import AdminOnlyPermission, user_organization
from .services.platform_security import (
    login_ip_access_result,
    login_lock_policy,
    login_security_settings,
    lock_user_for_password_expiry,
    password_is_expired,
    password_max_age_days,
    password_policy_settings,
    restore_system_admin_expiry_lock,
    timezone_settings,
    watermark_settings,
    validate_password,
)
from .services.license_access import license_access_denial, license_concurrency_denial
from platform_logs.models import AuditLog
from platform_logs.services import write_login_log
from .services.password_reset import (
    PASSWORD_RESET_SECONDS,
    consume_reset_transaction,
    eligible_reset_user,
    issue_reset_transaction,
    load_reset_transaction,
    register_anonymous_otp_failure,
    reset_transaction_user,
    set_recovered_password,
    simulate_anonymous_totp_check,
)
from .services.otp import (
    OTP_TRANSACTION_SECONDS,
    bind_user_otp,
    consume_login_transaction,
    effective_otp_enabled,
    ensure_user_profile,
    issue_login_transaction,
    load_login_transaction,
    matching_timestep,
    otp_status_payload,
    register_setup_failure,
    reset_user_otp,
    setup_payload,
    verify_user_otp,
)
from .services.security import (
    clear_login_failures,
    clear_user_login_failures,
    ip_login_blocked,
    login_blocked,
    record_login_failure,
)
from .services.system_status import collect_system_status
from .services.system_tools import (
    normalize_curl_url,
    run_curl,
    run_mtr,
    run_ping,
    run_telnet,
    stream_traceroute,
)
from .services.client_ip import request_client_ip
from .services.notifications import (
    NotificationConfigurationError,
    NotificationRateLimitError,
    NotificationSendError,
    send_test_email,
    send_test_sms,
)
from .services.llm_providers import (
    LlmConfigurationError,
    LlmConnectionError,
    provider_for_code,
    test_llm_provider,
    update_provider_status,
)
from .services.sms_login import (
    SMS_CODE_TTL_SECONDS,
    issue_sms_login_challenge,
    verify_sms_login_challenge,
)
from .services.slider_captcha import (
    SLIDER_MAX_AGE,
    consume_slider_verification,
    issue_slider_challenge,
    verify_slider_challenge,
)
from .services.tokens import decode_token, issue_access_from_refresh, issue_pair, token_matches_auth_version
from .services.user_import import (
    UserImportError,
    build_user_import_template,
    import_users,
    public_validation_result,
    validate_user_import,
)
from .services.system_admin import is_system_admin
from .tenancy import assign_organization, organization_scope_ids, scoped_queryset


CAPTCHA_SALT = 'ongrid-login-captcha'
CAPTCHA_MAX_AGE = 300
CAPTCHA_CHARS = 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'
LOGO_MAX_SIZE = 2 * 1024 * 1024
LOGO_ALLOWED_TYPES = {
    '.png': {'image/png'},
    '.jpg': {'image/jpeg'},
    '.jpeg': {'image/jpeg'},
    '.webp': {'image/webp'},
    '.gif': {'image/gif'},
}
DEFAULT_PLATFORM_LOGO_URL = '/assets/brand/logo.svg'


def issue_login_captcha():
    """生成四位登录验证码及带有效期校验能力的签名令牌。"""
    code = ''.join(secrets.choice(CAPTCHA_CHARS) for _ in range(4))
    return code, signing.dumps({'code': code}, salt=CAPTCHA_SALT)


def captcha_valid(token, answer):
    """校验验证码签名、有效期和用户提交的答案。"""
    try:
        payload = signing.loads(token, salt=CAPTCHA_SALT, max_age=CAPTCHA_MAX_AGE)
    except (signing.BadSignature, signing.SignatureExpired):
        return False
    return str(payload.get('code', '')).upper() == str(answer or '').strip().upper()


def default_organization_root():
    """返回并修正默认公司根节点；数据库为空时创建一个。"""
    root = models.Organization.objects.filter(is_default=True).order_by('id').first()
    if not root:
        root = models.Organization.objects.filter(parent__isnull=True).order_by('id').first()
    if not root:
        root = models.Organization.objects.create(
            name='默认组织',
            slug='default-org',
            description='公司根组织，部门默认挂载到此节点。',
            region='中国',
            org_type='company',
            is_default=True,
            is_active=True,
        )
    elif not root.is_default or root.org_type != 'company' or root.parent_id or not root.is_active:
        root.is_default = True
        root.org_type = 'company'
        root.parent = None
        root.is_active = True
        root.save(update_fields=['is_default', 'org_type', 'parent', 'is_active', 'updated_at'])
    return root


def serialize_org_tree(orgs, serializer_context=None):
    """把组织查询集转换为前端部门树结构。"""
    rows = serializers.OrganizationSerializer(orgs, many=True, context=serializer_context or {}).data
    by_id = {row['id']: {**row, 'children': []} for row in rows}
    roots = []
    for row in by_id.values():
        parent_id = row.get('parent_id')
        if parent_id and parent_id in by_id:
            by_id[parent_id]['children'].append(row)
        else:
            roots.append(row)
    return roots


def organization_member_count_map():
    """统计每个部门自身及全部下级部门的用户总数，默认组织覆盖全系统用户。"""
    organizations = list(models.Organization.objects.values('id', 'parent_id', 'is_default'))
    parent_by_id = {row['id']: row['parent_id'] for row in organizations}
    counts = {row['id']: 0 for row in organizations}
    direct_counts = models.UserProfile.objects.values('organization_id').annotate(value=Count('id'))
    for row in direct_counts:
        organization_id = row['organization_id']
        value = row['value']
        if organization_id not in counts:
            continue
        counts[organization_id] += value
        parent_id = parent_by_id.get(organization_id)
        visited = {organization_id}
        while parent_id and parent_id not in visited:
            visited.add(parent_id)
            if parent_id in counts:
                counts[parent_id] += value
            parent_id = parent_by_id.get(parent_id)
    total_users = User.objects.count()
    for row in organizations:
        if row['is_default']:
            counts[row['id']] = total_users
    return counts


def organization_usage(organization):
    """统计部门的直接关联数据，防止删除部门时级联丢失业务记录。"""
    usage = {}
    ignored_accessors = {'permission_policies', 'department_permission_policies', 'settings'}
    for relation in models.Organization._meta.related_objects:
        accessor = relation.get_accessor_name()
        if accessor in ignored_accessors:
            continue
        manager = getattr(organization, accessor, None)
        if manager is None or not hasattr(manager, 'count'):
            continue
        count = manager.count()
        if count:
            usage[accessor] = count
    return usage


class BaseViewSet(viewsets.ModelViewSet):
    """为核心可写接口统一提供组织隔离和业务审计。"""

    def get_queryset(self):
        """按当前用户的组织范围过滤查询集。"""
        return scoped_queryset(super().get_queryset(), self.request.user)

    def perform_create(self, serializer):
        """创建记录、补充所属组织并写入审计日志。"""
        instance = serializer.save()
        assign_organization(instance, self.request.user)
        instance.save()
        self.write_audit('create', instance)

    def perform_update(self, serializer):
        """更新记录、校正所属组织并写入审计日志。"""
        instance = serializer.save()
        assign_organization(instance, self.request.user)
        instance.save()
        self.write_audit('update', instance)

    def perform_destroy(self, instance):
        """删除记录前写入可追溯的业务审计日志。"""
        self.write_audit('delete', instance)
        instance.delete()

    def write_audit(self, action, instance, detail=None):
        """记录当前请求对指定业务对象执行的操作。"""
        if isinstance(instance, models.AuditLog):
            return
        models.AuditLog.objects.create(
            organization=user_organization(self.request.user),
            actor=getattr(self.request.user, 'username', 'system') or 'system',
            action=f'{instance.__class__.__name__}.{action}',
            resource=str(instance),
            ip_address=request_client_ip(self.request),
            detail=detail or {'id': getattr(instance, 'id', None)},
        )


class OrganizationViewSet(BaseViewSet):
    """提供部门列表、树、成员调整和安全删除接口。"""

    queryset = models.Organization.objects.all()
    serializer_class = serializers.OrganizationSerializer
    permission_classes = [AdminOnlyPermission]

    def get_serializer_context(self):
        """为部门序列化补充包含全部下级部门的成员统计。"""
        context = super().get_serializer_context()
        context['organization_member_counts'] = organization_member_count_map()
        return context

    def get_queryset(self):
        """返回带成员和子部门数量的组织列表，并支持关键词搜索。"""
        queryset = super().get_queryset().select_related('parent').annotate(
            member_count=Count('profiles', distinct=True),
            children_count=Count('children', distinct=True),
        ).order_by('parent_id', 'name')
        query = self.request.query_params.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query) | Q(slug__icontains=query) | Q(description__icontains=query)
            )
        return queryset

    def perform_create(self, serializer):
        """创建组织并保证系统只有一个公司根节点。"""
        root = default_organization_root()
        requested_parent = serializer.validated_data.get('parent')
        is_default = bool(serializer.validated_data.get('is_default'))
        if is_default:
            instance = serializer.save(parent=None, org_type='company', is_default=True)
            models.Organization.objects.exclude(pk=instance.pk).update(is_default=False)
        else:
            instance = serializer.save(
                parent=requested_parent or root,
                org_type=serializer.validated_data.get('org_type') or 'department',
            )
        self.write_audit('create', instance, {'parent_id': instance.parent_id, 'is_default': instance.is_default})

    def perform_update(self, serializer):
        """更新组织并维护根节点层级约束。"""
        root = default_organization_root()
        requested_parent = serializer.validated_data.get('parent')
        is_default = serializer.validated_data.get('is_default')
        instance = serializer.save()
        if is_default:
            instance.parent = None
            instance.org_type = 'company'
            models.Organization.objects.exclude(pk=instance.pk).update(is_default=False)
        elif instance.pk != root.pk and instance.parent_id is None:
            instance.parent = requested_parent or root
            instance.org_type = instance.org_type or 'department'
        instance.save()
        self.write_audit('update', instance, {'parent_id': instance.parent_id, 'is_default': instance.is_default})

    def destroy(self, request, *args, **kwargs):
        """仅允许删除没有成员、子部门或业务数据的普通部门。"""
        organization = self.get_object()
        if organization.is_default or organization.parent_id is None:
            return Response({'detail': '默认组织是公司根节点，不能删除'}, status=status.HTTP_400_BAD_REQUEST)
        usage = organization_usage(organization)
        if usage:
            return Response(
                {'detail': '部门下仍有关联数据，不能直接删除', 'usage': usage},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=False, methods=['get'], permission_classes=[AdminOnlyPermission])
    def tree(self, request):
        """返回组织平铺数据和树形数据。"""
        queryset = self.get_queryset()
        serializer_context = self.get_serializer_context()
        return Response({
            'items': serializers.OrganizationSerializer(queryset, many=True, context=serializer_context).data,
            'tree': serialize_org_tree(queryset, serializer_context),
        })

    @action(detail=True, methods=['get', 'post'], permission_classes=[AdminOnlyPermission])
    def members(self, request, pk=None):
        """查询部门成员，或把已有/新建用户加入当前部门。"""
        organization = self.get_object()
        if request.method == 'GET':
            users = User.objects.filter(profile__organization=organization).select_related(
                'profile', 'profile__organization'
            )
            return Response(serializers.UserSerializer(users, many=True).data)
        if organization.is_default or organization.parent_id is None:
            return Response({'detail': '默认组织不能添加用户，请选择具体部门'}, status=status.HTTP_400_BAD_REQUEST)
        user_id = request.data.get('user_id')
        if user_id:
            user = User.objects.select_related('profile', 'profile__organization').get(pk=user_id)
            profile, _ = models.UserProfile.objects.get_or_create(
                user=user,
                defaults={'organization': organization, 'role': serializers.default_role_code()},
            )
            profile.organization = organization
            profile.save()
            self.write_audit('add_member', organization, {'user_id': user.id, 'username': user.username})
            user = User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)
            return Response(serializers.UserSerializer(user).data)
        payload = request.data.copy()
        payload['organization_id'] = organization.id
        serializer = serializers.UserSerializer(data=payload, context={'request': request})
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        self.write_audit('invite_member', organization, {'user_id': user.id, 'username': user.username})
        return Response(serializers.UserSerializer(user).data, status=status.HTTP_201_CREATED)

    @action(
        detail=True,
        methods=['delete'],
        url_path='members/(?P<user_id>[^/.]+)',
        permission_classes=[AdminOnlyPermission],
    )
    def remove_member(self, request, pk=None, user_id=None):
        """从普通部门移出用户，并将其转移到默认公司根节点。"""
        organization = self.get_object()
        if organization.is_default or organization.parent_id is None:
            return Response({'detail': '默认组织成员不能从公司根节点移出'}, status=status.HTTP_400_BAD_REQUEST)
        user = User.objects.select_related('profile', 'profile__organization').get(pk=user_id)
        root = default_organization_root()
        profile, _ = models.UserProfile.objects.get_or_create(
            user=user,
            defaults={'organization': root, 'role': serializers.default_role_code()},
        )
        if profile.organization_id != organization.id:
            return Response({'detail': '用户不属于该部门'}, status=status.HTTP_400_BAD_REQUEST)
        profile.organization = root
        profile.save(update_fields=['organization', 'updated_at'])
        self.write_audit(
            'remove_member',
            organization,
            {'user_id': user.id, 'username': user.username, 'moved_to': root.id},
        )
        user = User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)
        return Response(serializers.UserSerializer(user).data)


class RoleViewSet(viewsets.ReadOnlyModelViewSet):
    """只读提供可分配的身份标签；系统不再提供旧角色权限编辑入口。"""

    queryset = models.Role.objects.all()
    serializer_class = serializers.RoleSerializer
    permission_classes = [AdminOnlyPermission]

    def get_queryset(self):
        """返回身份标签列表，并支持关键词和启用状态筛选。"""
        queryset = self.queryset.order_by('-rank', 'name')
        query = self.request.query_params.get('q', '').strip()
        if query:
            queryset = queryset.filter(
                Q(code__icontains=query) | Q(name__icontains=query) | Q(description__icontains=query)
            )
        if self.request.query_params.get('active') in ['1', 'true', 'True']:
            queryset = queryset.filter(is_active=True)
        return queryset


class UserViewSet(BaseViewSet):
    """提供用户查询、新增、编辑、停用和安全删除接口。"""

    queryset = User.objects.select_related('profile', 'profile__organization').all().order_by('username')
    serializer_class = serializers.UserSerializer
    permission_classes = [AdminOnlyPermission]

    def get_queryset(self):
        """按组织范围返回用户，并支持姓名、角色和部门关键词搜索。"""
        queryset = self.queryset
        scope_ids = organization_scope_ids(self.request.user)
        if scope_ids is not None and scope_ids:
            queryset = queryset.filter(profile__organization_id__in=scope_ids)
        elif scope_ids == []:
            queryset = queryset.none()
        query = self.request.query_params.get('q', '').strip()
        if query:
            role_codes = list(models.Role.objects.filter(
                Q(code__icontains=query) | Q(name__icontains=query)
            ).values_list('code', flat=True))
            queryset = queryset.filter(
                Q(username__icontains=query)
                | Q(email__icontains=query)
                | Q(first_name__icontains=query)
                | Q(last_name__icontains=query)
                | Q(profile__role__icontains=query)
                | Q(profile__role__in=role_codes)
                | Q(profile__organization__name__icontains=query)
            )
        return queryset.order_by('username')

    def perform_create(self, serializer):
        """创建用户并记录身份标签等审计信息。"""
        user = serializer.save()
        models.AuditLog.objects.create(
            organization=user_organization(self.request.user),
            actor=getattr(self.request.user, 'username', 'system') or 'system',
            action='User.create',
            resource=user.username,
            ip_address=request_client_ip(self.request),
            detail={'user_id': user.id, 'role': getattr(user.profile, 'role', '')},
        )

    def perform_update(self, serializer):
        """更新用户并记录身份标签和启用状态。"""
        user = serializer.save()
        models.AuditLog.objects.create(
            organization=user_organization(self.request.user),
            actor=getattr(self.request.user, 'username', 'system') or 'system',
            action='User.update',
            resource=user.username,
            ip_address=request_client_ip(self.request),
            detail={
                'user_id': user.id,
                'role': getattr(user.profile, 'role', ''),
                'is_active': user.is_active,
                'otp_policy': getattr(user.profile, 'otp_policy', 'inherit'),
            },
        )

    @action(detail=True, methods=['post'], url_path='reset-otp')
    def reset_otp(self, request, pk=None):
        """重置目标用户 OTP 并使其现有平台令牌失效。

        参数：`request` 为已通过用户管理重置权限校验的请求；`pk` 为目标用户编号。
        返回：不含 OTP 种子和动态口令的最新用户数据。
        副作用：销毁目标用户 OTP 配置、使令牌失效并写入系统日志。
        """
        user = self.get_object()
        reset_user_otp(user)
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='User.otp_reset',
            resource=user.username,
            ip_address=request_client_ip(request),
            detail={'user_id': user.id, 'result': 'success'},
        )
        refreshed = User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)
        return Response(serializers.UserSerializer(refreshed).data)

    def destroy(self, request, *args, **kwargs):
        """阻止删除当前用户或系统唯一的超级管理员 admin。"""
        user = self.get_object()
        if is_system_admin(user):
            return Response({'detail': '系统超级管理员 admin 不允许删除'}, status=status.HTTP_400_BAD_REQUEST)
        if user.id == request.user.id:
            return Response({'detail': '不能删除当前登录用户'}, status=status.HTTP_400_BAD_REQUEST)
        username = user.username
        user_id = user.id
        user.delete()
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='User.delete',
            resource=username,
            ip_address=request_client_ip(request),
            detail={'user_id': user_id},
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


def permission_statistics_payload():
    """汇总系统全部权限策略的状态、授权覆盖、继承关系、效果和高风险授权。"""
    policies = models.PermissionPolicy.objects.select_related(
        'department', 'user', 'user__profile', 'user__profile__organization',
    ).prefetch_related('rules').all()
    organization_rows = list(
        models.Organization.objects.filter(is_active=True).values('id', 'parent_id', 'org_type')
    )
    department_rows = [row for row in organization_rows if row['org_type'] == 'department']
    parent_by_id = {row['id']: row['parent_id'] for row in organization_rows}

    policy_rows = list(policies)
    available_policies = sum(policy.status == 'available' for policy in policy_rows)
    department_policies = sum(policy.subject_type == 'department' for policy in policy_rows)
    available_policy_rows = [policy for policy in policy_rows if policy.status == 'available']
    active_department_ids = {row['id'] for row in department_rows}
    authorized_department_ids = {
        policy.department_id
        for policy in available_policy_rows
        if policy.subject_type == 'department' and policy.department_id in active_department_ids
    }
    inherited_authorizations = 0
    allowed_rules = 0
    denied_rules = 0
    department_counts = {}
    risk_labels = {
        'delete': '删除',
        'export': '导出',
        'download': '下载',
        'connect': '连接',
        'approve': '审批',
        'disconnect': '断开会话',
        'reveal': '查看敏感配置',
        'replay': '回放录像',
    }
    risk_counts = {label: 0 for label in risk_labels.values()}

    for policy in available_policy_rows:
        if policy.subject_type != 'department' or not policy.department_id:
            continue
        for department in department_rows:
            ancestor_id = department['parent_id']
            visited_ids = set()
            while ancestor_id and ancestor_id not in visited_ids:
                if ancestor_id == policy.department_id:
                    inherited_authorizations += 1
                    break
                visited_ids.add(ancestor_id)
                ancestor_id = parent_by_id.get(ancestor_id)

    for policy in policy_rows:
        subject_department = (
            policy.department
            if policy.subject_type == 'department'
            else getattr(getattr(policy.user, 'profile', None), 'organization', None)
        )
        department_name = getattr(subject_department, 'name', '') or '未分配部门'
        department_counts[department_name] = department_counts.get(department_name, 0) + 1
        for rule in policy.rules.all():
            if rule.effect == 'allow':
                allowed_rules += 1
                action_name = str(rule.permission_code or '').rsplit('.', 1)[-1]
                if policy.status == 'available' and action_name in risk_labels:
                    risk_counts[risk_labels[action_name]] += 1
            else:
                denied_rules += 1

    return {
        'summary': {
            'total_policies': len(policy_rows),
            'available_policies': available_policies,
            'disabled_policies': len(policy_rows) - available_policies,
            'department_policies': department_policies,
            'user_policies': len(policy_rows) - department_policies,
            'allowed_rules': allowed_rules,
            'denied_rules': denied_rules,
        },
        'status_distribution': [
            {'name': '已启用', 'value': available_policies},
            {'name': '已停用', 'value': len(policy_rows) - available_policies},
        ],
        'authorization_mode_distribution': [
            {'name': '直接授权', 'value': len(available_policy_rows)},
            {'name': '继承授权', 'value': inherited_authorizations},
        ],
        'subject_distribution': [
            {'name': '部门策略', 'value': department_policies},
            {'name': '用户策略', 'value': len(policy_rows) - department_policies},
        ],
        'department_authorization_distribution': [
            {'name': '已授权部门', 'value': len(authorized_department_ids)},
            {'name': '未授权部门', 'value': len(active_department_ids - authorized_department_ids)},
        ],
        'effect_distribution': [
            {'name': '允许', 'value': allowed_rules},
            {'name': '拒绝', 'value': denied_rules},
        ],
        'department_distribution': [
            {'name': name, 'value': value}
            for name, value in sorted(department_counts.items(), key=lambda item: (-item[1], item[0]))
        ],
        'risk_distribution': [
            {'name': name, 'value': value}
            for name, value in risk_counts.items()
        ],
    }


class UserReportView(APIView):
    """返回系统全部用户、部门、OTP、账号和权限策略统计。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.admin_user_report.view'

    def get(self, request):
        """按全局数据范围汇总用户报表，不受当前用户所属部门限制。"""
        users = User.objects.select_related('profile', 'profile__organization').all()
        organizations = models.Organization.objects.filter(is_active=True)

        total_users = users.count()
        active_users = users.filter(is_active=True).count()
        otp_bound = users.filter(profile__otp_bound_at__isnull=False).count()
        department_rows = list(
            users.values('profile__organization_id', 'profile__organization__name')
            .annotate(value=Count('id'))
            .order_by('-value', 'profile__organization__name')
        )
        department_distribution = [
            {
                'name': row['profile__organization__name'] or '未分配部门',
                'value': row['value'],
            }
            for row in department_rows
        ]

        today = timezone.localdate()
        trend_start = today - timedelta(days=6)
        trend_counts = {trend_start + timedelta(days=offset): 0 for offset in range(7)}
        for joined_at in users.filter(date_joined__date__gte=trend_start).values_list('date_joined', flat=True):
            joined_date = timezone.localtime(joined_at).date() if timezone.is_aware(joined_at) else joined_at.date()
            if joined_date in trend_counts:
                trend_counts[joined_date] += 1

        return Response({
            'summary': {
                'total_users': total_users,
                'active_users': active_users,
                'disabled_users': total_users - active_users,
                'department_count': organizations.filter(org_type='department').count(),
                'otp_bound': otp_bound,
                'otp_unbound': total_users - otp_bound,
            },
            'department_distribution': department_distribution,
            'otp_distribution': [
                {'name': '已绑定', 'value': otp_bound},
                {'name': '未绑定', 'value': total_users - otp_bound},
            ],
            'status_distribution': [
                {'name': '已启用', 'value': active_users},
                {'name': '已禁用', 'value': total_users - active_users},
            ],
            'registration_trend': [
                {'date': day.strftime('%m-%d'), 'value': value}
                for day, value in trend_counts.items()
            ],
            'permission_statistics': permission_statistics_payload(),
        })


class UserImportTemplateView(APIView):
    """动态生成包含当前部门和身份字典的用户导入模板。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.admin_users.view'

    def get(self, request):
        """在内存中生成 XLSX 模板并作为附件直接下载。"""
        content = build_user_import_template(request.user)
        response = HttpResponse(
            content,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        )
        response['Content-Disposition'] = 'attachment; filename="user-import-template.xlsx"'
        response['X-Content-Type-Options'] = 'nosniff'
        response['Cache-Control'] = 'no-store'
        return response


class UserImportPrecheckView(APIView):
    """接收用户 Excel 并执行无落库、无临时文件的逐行预检查。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.admin_users.view'
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """返回有效和异常行数及错误详情，不创建用户或记录敏感字段。"""
        try:
            result = validate_user_import(request.FILES.get('file'), request.user)
        except UserImportError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(public_validation_result(result))


class UserImportConfirmView(APIView):
    """重新校验上传 Excel，并以整批成功或整批回滚方式导入用户。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.admin_users.view'
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """事务创建全部用户并记录不含个人敏感数据的导入审计。"""
        try:
            result = import_users(request.FILES.get('file'), request.user)
        except UserImportError as exc:
            models.AuditLog.objects.create(
                organization=user_organization(request.user),
                actor=getattr(request.user, 'username', 'system') or 'system',
                action='User.import',
                resource='用户批量导入',
                ip_address=request_client_ip(request),
                detail={'result': 'failed'},
            )
            payload = {'detail': str(exc)}
            if exc.result:
                payload['validation'] = exc.result
            return Response(payload, status=status.HTTP_400_BAD_REQUEST)
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='User.import',
            resource='用户批量导入',
            ip_address=request_client_ip(request),
            detail={
                'result': 'success',
                'created_count': result['created_count'],
                'department_count': result['department_count'],
            },
        )
        return Response(result, status=status.HTTP_201_CREATED)


class PermissionCatalogView(APIView):
    """返回数据库权限目录，供权限策略编辑器使用。"""

    permission_classes = [AdminOnlyPermission]

    def get(self, request):
        """读取包含页面和真实操作项的完整权限目录。"""
        return Response(catalog_payload())


class PublicNavigationView(APIView):
    """公开返回数据库菜单结构，登录页和前端路由初始化均使用此接口。"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """返回数据库菜单树，并为已登录用户应用个人菜单顺序。"""
        return Response(navigation_payload_for_user(request.user))


class MenuOrderView(APIView):
    """查询和保存当前用户的分层菜单展示顺序。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.menu_order.view'

    def get(self, request):
        """返回当前用户可调整的主菜单和各级子菜单顺序。"""
        return Response({'items': menu_order_items_for_user(request.user)})
    def put(self, request):
        """事务保存当前用户的完整分层菜单顺序并记录系统日志。"""
        serializer = serializers.MenuOrderUpdateSerializer(data=request.data, context={'request': request})
        serializer.is_valid(raise_exception=True)
        orders = serializer.validated_data['orders']
        before_items = menu_order_items_for_user(request.user)
        order_data = {item['parent_code']: item['codes'] for item in orders}
        with transaction.atomic():
            models.UserMenuOrderPreference.objects.update_or_create(
                user=request.user,
                defaults={'order_data': order_data},
            )
            models.AuditLog.objects.create(
                organization=user_organization(request.user),
                actor=getattr(request.user, 'username', 'system') or 'system',
                action='MenuOrder.update',
                resource='个人菜单顺序',
                ip_address=request_client_ip(request),
                detail={
                    'result': 'success',
                    'scope': 'current_user',
                    'groups_updated': len(order_data),
                    'root_before': [item['name'] for item in before_items],
                    'root_after': [item['name'] for item in menu_order_items_for_user(request.user)],
                },
            )
        return Response({'items': menu_order_items_for_user(request.user)})


class SystemStatusView(APIView):
    """返回平台管理页面所需的当前系统运行状态。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.system_status.view'

    def get(self, request):
        """采集并返回 CPU、内存、磁盘、网络、并发用户和运行环境指标。"""
        return Response(collect_system_status())


class SystemToolView(APIView):
    """提供受数据库权限控制和频率限制的平台网络诊断工具。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.system_tools.view'
    tool = ''
    serializer_class = None

    def _write_audit(self, request, result, target, duration_ms=0, port=None):
        """记录诊断类型、目标和结果，不保存命令文本或服务响应内容。

        参数：`request` 为请求；`result` 为业务结果；`target` 为安全目标；
        `duration_ms` 为耗时；`port` 为可选 TCP 端口。
        返回：无显式返回值。
        副作用：向 platform_logs 的系统日志表写入一条诊断审计记录。
        """
        detail = {
            'tool': self.tool,
            'target': target,
            'result': result,
            'duration_ms': duration_ms,
        }
        if port is not None:
            detail['port'] = port
        AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action=f'SystemTool.{self.tool}',
            resource='平台工具',
            ip_address=request_client_ip(request),
            detail=detail,
        )

    def execute(self, validated_data):
        """声明由具体工具视图实现的安全诊断调用。

        参数：`validated_data` 为序列化器校验后的参数。
        返回：具体诊断服务的结构化结果。
        副作用：由子类决定网络或子进程调用，本方法本身只抛出未实现异常。
        """
        raise NotImplementedError

    def audit_target(self, target):
        """返回允许写入系统日志的脱敏目标地址。

        参数：`target` 为用户提交的目标。
        返回：默认原样返回目标，Curl 子类会移除查询参数。
        副作用：不修改持久化数据。
        """
        return target

    def post(self, request):
        """校验参数、限制高频调用、执行诊断并记录系统日志。

        参数：`request` 为当前用户的 POST 请求。
        返回：结构化诊断结果或用户友好的错误响应。
        副作用：可能调用网络或子进程，并写入一条系统日志。
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        throttle_key = f'system-tool:{request.user.pk}'
        if not cache.add(throttle_key, True, timeout=2):
            return Response(
                {'detail': '网络诊断操作过于频繁，请稍后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        target = self.audit_target(serializer.validated_data['target'])
        port = serializer.validated_data.get('port')
        try:
            result = self.execute(serializer.validated_data)
        except (TypeError, ValueError) as exc:
            self._write_audit(request, 'rejected', target, port=port)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            self._write_audit(request, 'failed', target, port=port)
            return Response(
                {'detail': '网络诊断执行失败，请稍后重试'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        self._write_audit(
            request,
            'success' if result['success'] else 'unreachable',
            result['target'],
            result['duration_ms'],
            result.get('port'),
        )
        return Response(result)


class SystemToolPingView(SystemToolView):
    """执行受控的 ICMP Ping 网络诊断。"""

    tool = 'ping'
    serializer_class = serializers.SystemToolPingSerializer

    def execute(self, validated_data):
        """调用不经过 shell 的 Ping 服务并返回结果。"""
        return run_ping(**validated_data)


class SystemToolTelnetView(SystemToolView):
    """执行指定目标和端口的 TCP 握手诊断。"""

    tool = 'telnet'
    serializer_class = serializers.SystemToolTelnetSerializer

    def execute(self, validated_data):
        """调用不读取远端数据的 TCP 端口检测服务并返回结果。"""
        return run_telnet(**validated_data)


class SystemToolCurlView(SystemToolView):
    """执行不落盘、不跟随重定向的 HTTP 响应诊断。"""

    tool = 'curl'
    serializer_class = serializers.SystemToolCurlSerializer

    def audit_target(self, target):
        """移除 URL 查询参数，避免令牌等敏感信息进入系统日志。"""
        try:
            return normalize_curl_url(target)[1]
        except ValueError:
            return '已拒绝的 Curl 地址'

    def execute(self, validated_data):
        """调用仅在内存读取有限响应内容的 HTTP 诊断服务。"""
        payload = dict(validated_data)
        payload['url'] = payload.pop('target')
        return run_curl(**payload)


class SystemToolTracerouteView(SystemToolView):
    """执行指定目标的受控路由追踪，并通过 SSE 实时返回输出。"""

    tool = 'traceroute'
    serializer_class = serializers.SystemToolTracerouteSerializer

    def post(self, request):
        """逐行返回路由追踪内容，并在流完成、中断或失败后写入系统日志。

        参数：`request` 为当前用户的 POST 请求。
        返回：SSE 流响应，参数错误或限流时返回普通 JSON 响应。
        副作用：启动路由追踪子进程，并在流结束时写入一条系统日志。
        """
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        throttle_key = f'system-tool:{request.user.pk}'
        if not cache.add(throttle_key, True, timeout=2):
            return Response(
                {'detail': '网络诊断操作过于频繁，请稍后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        target = serializer.validated_data['target']
        try:
            events = stream_traceroute(**serializer.validated_data)
        except (TypeError, ValueError) as exc:
            self._write_audit(request, 'rejected', target)
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        def streaming_content():
            """编码 SSE 事件并保证成功、失败或中断均留下审计结果。

            参数：无。
            返回：逐段产生符合 SSE 格式的 UTF-8 文字。
            副作用：消费诊断生成器、回收其子进程并写入系统日志。
            """
            final_result = None
            try:
                for event, payload in events:
                    if event == 'done':
                        final_result = payload
                    data = json.dumps(payload, ensure_ascii=False, separators=(',', ':'))
                    yield f'event: {event}\ndata: {data}\n\n'
            except Exception:
                final_result = {
                    'target': target, 'success': False, 'duration_ms': 0,
                    'detail': '路由追踪执行失败',
                }
                data = json.dumps(final_result, ensure_ascii=False, separators=(',', ':'))
                yield f'event: done\ndata: {data}\n\n'
            finally:
                close_events = getattr(events, 'close', None)
                if callable(close_events):
                    close_events()
                result = final_result or {'target': target, 'success': False, 'duration_ms': 0}
                self._write_audit(
                    request,
                    'success' if result.get('success') else ('unreachable' if final_result else 'cancelled'),
                    result.get('target', target),
                    result.get('duration_ms', 0),
                )

        response = StreamingHttpResponse(streaming_content(), content_type='text/event-stream; charset=utf-8')
        response['Cache-Control'] = 'no-cache, no-transform'
        response['X-Accel-Buffering'] = 'no'
        return response


class SystemToolMtrView(SystemToolView):
    """执行不依赖系统 mtr 命令的 Python ICMP 链路质量探测。"""

    tool = 'mtr'
    serializer_class = serializers.SystemToolMtrSerializer

    def execute(self, validated_data):
        """调用 Python ICMP 路由质量统计服务并返回逐跳结果。"""
        return run_mtr(**validated_data)


class NotificationTestView(APIView):
    """使用数据库中已保存的通知配置执行单次渠道测试。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.settings.view'
    serializer_class = None
    channel = ''
    success_detail = ''

    def _write_audit(self, request, result):
        """记录测试渠道和结果，不保存收件地址或任何渠道凭据。"""
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action=f'SystemSetting.test_{self.channel}',
            resource='notification.delivery',
            ip_address=request_client_ip(request),
            detail={
                'key': 'notification.delivery',
                'channel': self.channel,
                'result': result,
            },
        )

    def send(self, validated_data):
        """由具体邮件或短信测试视图实现实际发送。"""
        raise NotImplementedError

    def post(self, request):
        """校验接收方、限制重复点击并调用对应通知发送服务。"""
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        throttle_key = f'notification-test:{request.user.pk}:{self.channel}'
        if not cache.add(throttle_key, True, timeout=30):
            return Response(
                {'detail': '测试发送过于频繁，请 30 秒后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        try:
            self.send(serializer.validated_data)
        except NotificationConfigurationError as exc:
            self._write_audit(request, 'failed')
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except NotificationSendError as exc:
            self._write_audit(request, 'failed')
            return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
        except Exception:
            self._write_audit(request, 'failed')
            return Response(
                {'detail': '测试发送失败，请检查通知配置和网络连接'},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        self._write_audit(request, 'success')
        return Response({'detail': self.success_detail})


class NotificationEmailTestView(NotificationTestView):
    """发送一封带平台名称和 HTML 格式的 SMTP 测试邮件。"""

    serializer_class = serializers.NotificationEmailTestSerializer
    channel = 'email'
    success_detail = '测试邮件已发送，请检查收件箱。'

    def send(self, validated_data):
        """把已校验收件邮箱交给邮件发送服务。"""
        return send_test_email(validated_data['recipient'])


class NotificationSmsTestView(NotificationTestView):
    """使用已保存阿里云签名和模板发送测试短信。"""

    serializer_class = serializers.NotificationSmsTestSerializer
    channel = 'sms'
    success_detail = '测试短信已提交至阿里云，请注意查收。'

    def send(self, validated_data):
        """把已标准化手机号交给当前短信服务商发送。"""
        return send_test_sms(validated_data['phone'])


class LlmProviderTestView(APIView):
    """使用已保存凭据检测单个 LLM 厂商的 OpenAI 兼容接口。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.settings.view'

    def _write_audit(self, request, provider, result):
        """只记录厂商和检测结论，不保存凭据或第三方响应。"""
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='SystemSetting.test_llm',
            resource='llm.providers',
            ip_address=request_client_ip(request),
            detail={
                'key': 'llm.providers',
                'provider': provider,
                'result': result,
            },
        )

    def _save_status(self, setting_id, provider, provider_status):
        """在短事务中回写指定厂商的最新状态，避免覆盖其他检测结果。"""
        checked_at = timezone.now().isoformat()
        with transaction.atomic():
            setting = models.SystemSetting.objects.select_for_update().get(pk=setting_id)
            setting.value = update_provider_status(
                setting.value,
                provider,
                provider_status,
                checked_at,
            )
            setting.save(update_fields=['value', 'updated_at'])
        return checked_at

    def post(self, request):
        """限制重复点击、执行真实连通性检测并返回安全状态。"""
        serializer = serializers.LlmProviderTestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        provider_code = serializer.validated_data['provider']
        throttle_key = f'llm-provider-test:{request.user.pk}:{provider_code}'
        if not cache.add(throttle_key, True, timeout=5):
            return Response(
                {'detail': '检测过于频繁，请 5 秒后再试'},
                status=status.HTTP_429_TOO_MANY_REQUESTS,
            )
        setting = models.SystemSetting.objects.filter(key='llm.providers').first()
        provider = provider_for_code(setting.value, provider_code) if setting else None
        if not setting or not provider:
            return Response(
                {'detail': '请先保存 LLM 厂商配置'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            test_llm_provider(provider)
        except LlmConfigurationError as exc:
            checked_at = self._save_status(setting.pk, provider_code, 'unavailable')
            self._write_audit(request, provider_code, 'unavailable')
            return Response(
                {'detail': str(exc), 'provider': provider_code, 'status': 'unavailable', 'last_checked_at': checked_at},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except LlmConnectionError as exc:
            checked_at = self._save_status(setting.pk, provider_code, 'unavailable')
            self._write_audit(request, provider_code, 'unavailable')
            return Response(
                {'detail': str(exc), 'provider': provider_code, 'status': 'unavailable', 'last_checked_at': checked_at},
                status=status.HTTP_502_BAD_GATEWAY,
            )
        except Exception:
            checked_at = self._save_status(setting.pk, provider_code, 'unavailable')
            self._write_audit(request, provider_code, 'unavailable')
            return Response(
                {
                    'detail': '模型服务检测失败，请检查配置和网络连接',
                    'provider': provider_code,
                    'status': 'unavailable',
                    'last_checked_at': checked_at,
                },
                status=status.HTTP_502_BAD_GATEWAY,
            )
        checked_at = self._save_status(setting.pk, provider_code, 'available')
        self._write_audit(request, provider_code, 'available')
        return Response({
            'detail': '模型服务连接正常',
            'provider': provider_code,
            'status': 'available',
            'last_checked_at': checked_at,
        })


class PlatformLogoUploadView(APIView):
    """上传平台 Logo 到本地上传目录，并返回可保存到平台设置的本地路径。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.settings.view'
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        """校验图片文件、保存到 /uploads/ 平台目录并写入系统日志。"""
        upload = request.FILES.get('file')
        if not upload:
            return Response({'detail': '请选择要上传的 Logo 文件'}, status=status.HTTP_400_BAD_REQUEST)
        error = self._validate_upload(upload)
        if error:
            return Response({'detail': error}, status=status.HTTP_400_BAD_REQUEST)
        extension = os.path.splitext(upload.name or '')[1].lower()
        target_name = f'platform/logo/{uuid.uuid4().hex}{extension}'
        saved_name = default_storage.save(target_name, upload).replace('\\', '/')
        logo_url = f'{settings.MEDIA_URL.rstrip("/")}/{saved_name}'
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action='SystemSetting.logo_upload',
            resource='平台 Logo',
            ip_address=request_client_ip(request),
            detail={
                'result': 'success',
                'file_size': upload.size,
                'logo_url': logo_url,
            },
        )
        return Response({'logo_url': logo_url})

    def _validate_upload(self, upload):
        """校验 Logo 文件大小、扩展名、MIME 类型和基础文件头。"""
        extension = os.path.splitext(upload.name or '')[1].lower()
        if extension not in LOGO_ALLOWED_TYPES:
            return 'Logo 只支持 PNG、JPG、JPEG、WEBP 或 GIF 图片'
        if upload.size > LOGO_MAX_SIZE:
            return 'Logo 文件不能超过 2 MB'
        content_type = str(getattr(upload, 'content_type', '') or '').lower()
        if content_type and content_type not in LOGO_ALLOWED_TYPES[extension]:
            return 'Logo 文件类型与扩展名不一致'
        head = upload.read(16)
        upload.seek(0)
        if extension == '.png' and not head.startswith(b'\x89PNG\r\n\x1a\n'):
            return 'PNG 图片格式无效'
        if extension in {'.jpg', '.jpeg'} and not head.startswith(b'\xff\xd8\xff'):
            return 'JPEG 图片格式无效'
        if extension == '.webp' and not (head.startswith(b'RIFF') and head[8:12] == b'WEBP'):
            return 'WEBP 图片格式无效'
        if extension == '.gif' and not (head.startswith(b'GIF87a') or head.startswith(b'GIF89a')):
            return 'GIF 图片格式无效'
        return ''


class PermissionPolicyViewSet(BaseViewSet):
    """提供权限策略查询、增删改和克隆接口。"""

    queryset = models.PermissionPolicy.objects.select_related(
        'department', 'user', 'organization'
    ).prefetch_related('rules').all()
    serializer_class = serializers.PermissionPolicySerializer
    permission_classes = [AdminOnlyPermission]

    def get_queryset(self):
        """按授权对象和关键词筛选当前组织可见的权限策略。"""
        queryset = super().get_queryset()
        subject_type = self.request.query_params.get('subject_type')
        subject_id = self.request.query_params.get('subject_id')
        query = self.request.query_params.get('q', '').strip()
        if subject_type in ['department', 'user']:
            queryset = queryset.filter(subject_type=subject_type)
            if subject_type == 'department' and subject_id:
                queryset = queryset.filter(department_id=subject_id)
            if subject_type == 'user' and subject_id:
                queryset = queryset.filter(user_id=subject_id)
        if query:
            queryset = queryset.filter(
                Q(name__icontains=query)
                | Q(remark__icontains=query)
                | Q(department__name__icontains=query)
                | Q(user__username__icontains=query)
            )
        return queryset.order_by('priority', '-updated_at')

    def perform_create(self, serializer):
        """创建策略、记录审计并清除有效权限缓存。"""
        policy = serializer.save(organization=user_organization(self.request.user))
        self.write_audit('create', policy, {'id': policy.id, 'subject_type': policy.subject_type})
        clear_permission_cache()

    def perform_update(self, serializer):
        """更新策略、记录审计并清除有效权限缓存。"""
        policy = serializer.save()
        self.write_audit('update', policy, {'id': policy.id, 'subject_type': policy.subject_type})
        clear_permission_cache()

    def perform_destroy(self, instance):
        """删除策略、记录审计并清除有效权限缓存。"""
        self.write_audit('delete', instance, {'id': instance.id, 'subject_type': instance.subject_type})
        instance.delete()
        clear_permission_cache()

    @action(detail=True, methods=['post'])
    def clone(self, request, pk=None):
        """复制策略及其全部允许/拒绝规则。"""
        source = self.get_object()
        clone_name = request.data.get('name') or f'{source.name} 副本'
        policy = models.PermissionPolicy.objects.create(
            organization=user_organization(request.user),
            name=clone_name[:120],
            subject_type=source.subject_type,
            department=source.department,
            user=source.user,
            priority=source.priority,
            status=source.status,
            remark=source.remark,
        )
        models.PermissionRule.objects.bulk_create([
            models.PermissionRule(
                policy=policy,
                permission_code=rule.permission_code,
                effect=rule.effect,
            )
            for rule in source.rules.all()
        ])
        self.write_audit('clone', policy, {'id': policy.id, 'source_id': source.id})
        clear_permission_cache()
        return Response(self.get_serializer(policy).data, status=status.HTTP_201_CREATED)


def authenticated_login_payload(user, ip_address, auth_method):
    """在所有必需认证因素通过后组装正式登录响应。

    参数：`user` 为完成认证的用户；`ip_address` 为来源地址；`auth_method` 为实际认证方式。
    返回：包含正式令牌和脱敏用户数据的字典。
    副作用：写入一条登录成功用户日志。
    """
    denial = license_access_denial(user)
    if denial:
        write_login_log(
            user.username,
            ip_address,
            'failed',
            denial['detail'],
            user=user,
            auth_method=auth_method,
        )
        raise AuthenticationFailed(denial['detail'])
    concurrency_denial = None
    tokens = None
    with transaction.atomic():
        models.SystemSetting.objects.select_for_update().filter(key='license.management').first()
        concurrency_denial = license_concurrency_denial(user)
        if not concurrency_denial:
            tokens = issue_pair(user)
    if concurrency_denial:
        write_login_log(
            user.username,
            ip_address,
            'failed',
            concurrency_denial['detail'],
            user=user,
            auth_method=auth_method,
        )
        raise AuthenticationFailed(concurrency_denial['detail'])
    write_login_log(user.username, ip_address, 'success', '登录成功', user=user, auth_method=auth_method)
    return {**tokens, 'next_step': 'complete', 'user': serializers.UserSerializer(user).data}


def no_store_response(data, response_status=None):
    """返回禁止浏览器和中间代理缓存的认证响应。

    参数：`data` 为认证响应数据；`response_status` 为可选 HTTP 状态码。
    返回：带 `Cache-Control: no-store` 的 DRF Response。
    副作用：不修改数据库，仅设置响应头。
    """
    response = Response(data, status=response_status)
    response['Cache-Control'] = 'no-store'
    return response


def otp_transaction_user(payload):
    """从预认证事务读取仍处于启用状态的用户。

    参数：`payload` 为已校验来源和浏览器会话的 OTP 事务。
    返回：带用户档案的启用用户；不存在时返回 None。
    副作用：只读取数据库。
    """
    return User.objects.select_related('profile', 'profile__organization').filter(
        pk=payload.get('user_id'),
        is_active=True,
    ).first()


def otp_transaction_auth_method(payload):
    """返回 OTP 事务对应的完整登录认证方式。

    参数：`payload` 为已验证来源的 OTP 预认证事务。
    返回：password+otp 或 sms+otp。
    副作用：不读写数据库、缓存或日志。
    """
    return 'sms+otp' if payload.get('auth_method') == 'sms' else 'password+otp'


class SystemSettingViewSet(BaseViewSet):
    """提供平台设置列表及标准增删改接口。"""

    queryset = models.SystemSetting.objects.all()
    serializer_class = serializers.SystemSettingSerializer
    permission_classes = [AdminOnlyPermission]

    def get_queryset(self):
        """返回当前平台正在使用的设置项。"""
        return super().get_queryset().order_by('id')

    def write_audit(self, action, instance, detail=None):
        """记录平台设置键和成功结果，不写入配置值或敏感字段。"""
        super().write_audit(action, instance, detail={
            'id': instance.id,
            'key': instance.key,
            'result': 'success',
        })


class UserPasswordPolicyView(APIView):
    """为用户管理页面提供当前数据库密码策略的只读快照。"""

    permission_classes = [AdminOnlyPermission]
    permission_code = 'page.admin_users.view'

    def get(self, request):
        """返回新增和编辑用户时需要展示及预校验的密码规则。

        参数：`request` 为当前已认证的用户管理页面请求。
        返回：包含最小长度和五项复杂度开关的响应。
        副作用：只读取平台密码策略，不修改数据库或记录密码内容。
        """
        policy = password_policy_settings()
        return Response({
            'min_length': max(6, min(64, int(policy.get('min_length') or 8))),
            'require_uppercase': bool(policy.get('require_uppercase')),
            'require_lowercase': bool(policy.get('require_lowercase')),
            'require_number': bool(policy.get('require_number')),
            'require_special': bool(policy.get('require_special')),
            'exclude_username': bool(policy.get('exclude_username')),
            'max_age_days': password_max_age_days(),
        })


class LoginView(APIView):
    """校验登录第一阶段，并按用户策略签发 OTP 预认证事务或正式 JWT。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验登录凭据，记录登录审计并返回令牌和用户信息。"""
        username = str(request.data.get('username', '')).strip()
        password = str(request.data.get('password', ''))
        captcha_token = str(request.data.get('captcha_token', '')).strip()
        captcha_code = str(request.data.get('captcha_code', '')).strip()
        slider_verification = str(request.data.get('slider_verification', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        ip_address = request_client_ip(request)
        ip_allowed, denial_reason = login_ip_access_result(ip_address)
        if not ip_allowed:
            write_login_log(username, ip_address, 'failed', denial_reason)
            return Response({'detail': '当前来源地址不允许登录'}, status=status.HTTP_403_FORBIDDEN)
        if not username or not password:
            write_login_log(username, ip_address, 'failed', '用户名和密码不能为空')
            return Response({'detail': '用户名和密码不能为空'}, status=status.HTTP_400_BAD_REQUEST)
        login_config = login_security_settings()
        if login_config.get('captcha_enabled'):
            if not captcha_token or not captcha_code:
                write_login_log(username, ip_address, 'failed', '未提交验证码')
                return Response({'detail': '请输入验证码'}, status=status.HTTP_400_BAD_REQUEST)
            if not captcha_valid(captcha_token, captcha_code):
                write_login_log(username, ip_address, 'failed', '验证码错误或已过期')
                return Response({'detail': '验证码错误或已过期'}, status=status.HTTP_400_BAD_REQUEST)
        if login_config.get('slider_captcha_enabled'):
            if not slider_verification:
                write_login_log(username, ip_address, 'failed', '未完成图形拖拽验证')
                return Response({'detail': '请完成图形拖拽验证'}, status=status.HTTP_400_BAD_REQUEST)
            if not consume_slider_verification(slider_verification, ip_address):
                write_login_log(username, ip_address, 'failed', '图形拖拽验证失败或已过期')
                return Response({'detail': '图形拖拽验证失败或已过期'}, status=status.HTTP_400_BAD_REQUEST)
        lock_policy = login_lock_policy(login_config)
        blocked_scope = login_blocked(ip_address, username, login_config)
        if blocked_scope:
            ip_blocked = blocked_scope == 'ip'
            lock_minutes = lock_policy['ip_lock_minutes'] if ip_blocked else lock_policy['login_lock_minutes']
            subject = '来源 IP' if ip_blocked else '账号'
            write_login_log(username, ip_address, 'failed', f'{subject}登录失败次数过多，暂时锁定')
            return Response({
                'detail': f'{subject}登录失败次数过多，已锁定，请 {lock_minutes} 分钟后重试',
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        user = authenticate(username=username, password=password)
        candidate = None
        if not user:
            candidate = User.objects.select_related('profile', 'profile__organization').filter(username=username).first()
            if candidate and restore_system_admin_expiry_lock(candidate):
                # admin 豁免密码修改周期，历史误锁记录在登录时自动修复后重新校验一次口令。
                models.AuditLog.objects.create(
                    organization=user_organization(candidate),
                    actor='system',
                    action='User.password_expired_lock_restored',
                    resource=candidate.username,
                    ip_address=ip_address,
                    detail={'user_id': candidate.id, 'result': 'restored', 'reason': 'password_expiry_exempt'},
                )
                user = authenticate(username=username, password=password)
        if not user:
            if (
                candidate
                and not candidate.is_active
                and getattr(getattr(candidate, 'profile', None), 'password_expired_locked', False)
            ):
                write_login_log(username, ip_address, 'failed', '密码长期未修改，账号已禁用，请联系管理员解锁')
                return Response({'detail': '密码长期未修改，账号已禁用，请联系管理员解锁'}, status=status.HTTP_403_FORBIDDEN)
            locked_scope = record_login_failure(ip_address, username, login_config)
            if locked_scope:
                ip_locked = locked_scope == 'ip'
                lock_minutes = lock_policy['ip_lock_minutes'] if ip_locked else lock_policy['login_lock_minutes']
                subject = '来源 IP' if ip_locked else '账号'
                write_login_log(username, ip_address, 'failed', f'{subject}登录失败次数过多，暂时锁定')
                return Response({
                    'detail': f'{subject}登录失败次数过多，已锁定，请 {lock_minutes} 分钟后重试',
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
            write_login_log(username, ip_address, 'failed', '用户名或密码错误')
            return Response({'detail': '用户名或密码错误'}, status=status.HTTP_401_UNAUTHORIZED)
        if password_is_expired(user):
            locked = lock_user_for_password_expiry(user)
            if locked:
                models.AuditLog.objects.create(
                    organization=user_organization(user),
                    actor='system',
                    action='User.password_expired_disable',
                    resource=user.username,
                    ip_address=ip_address,
                    detail={'user_id': user.id, 'result': 'disabled', 'reason': 'password_expired'},
                )
            write_login_log(user.username, ip_address, 'failed', '密码长期未修改，账号已禁用，请联系管理员解锁', user=user)
            return Response({'detail': '密码长期未修改，账号已禁用，请联系管理员解锁'}, status=status.HTTP_403_FORBIDDEN)
        clear_login_failures(ip_address, username)
        denial = license_access_denial(user)
        if denial:
            write_login_log(user.username, ip_address, 'failed', denial['detail'], user=user)
            return Response(
                {'detail': denial['detail'], 'code': denial['code']},
                status=status.HTTP_403_FORBIDDEN,
            )
        if effective_otp_enabled(user):
            if len(client_nonce) < 16 or len(client_nonce) > 128:
                write_login_log(user.username, ip_address, 'failed', '登录会话已失效，请刷新页面', user=user)
                return Response({'detail': '登录会话已失效，请刷新页面'}, status=status.HTTP_400_BAD_REQUEST)
            ensure_user_profile(user)
            user = User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)
            otp_status = otp_status_payload(user)
            if otp_status['otp_status'] == 'locked':
                write_login_log(user.username, ip_address, 'failed', 'OTP 验证已锁定，请稍后重试', user=user)
                return Response({
                    'detail': f'OTP 输入错误次数过多，已锁定 {lock_policy["otp_lock_minutes"]} 分钟，请稍后重试',
                }, status=status.HTTP_429_TOO_MANY_REQUESTS)
            step = 'verify' if otp_status['otp_bound'] else 'bind'
            preauth_token = issue_login_transaction(user, ip_address, client_nonce, step)
            return no_store_response({
                'next_step': 'otp_verify' if step == 'verify' else 'otp_bind',
                'preauth_token': preauth_token,
                'expires_in': OTP_TRANSACTION_SECONDS,
            })
        return no_store_response(authenticated_login_payload(user, ip_address, 'password'))


class SmsLoginSendView(APIView):
    """校验反自动化凭证并发送三十秒短信登录验证码。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """消费字符和拖拽验证码后签发短信登录挑战。

        参数：`request` 包含手机号、两类验证码和浏览器会话随机值。
        返回：匿名一致的挑战令牌、三十秒有效期和发送说明。
        副作用：可能调用短信服务商、占用动态额度并保存国密摘要挑战。
        """
        ip_address = request_client_ip(request)
        ip_allowed, denial_reason = login_ip_access_result(ip_address)
        if not ip_allowed:
            write_login_log('', ip_address, 'failed', denial_reason, auth_method='sms+otp')
            return Response({'detail': '当前来源地址不允许登录'}, status=status.HTTP_403_FORBIDDEN)
        login_config = login_security_settings()
        if not login_config.get('sms_login_enabled'):
            return Response({'detail': '短信登录尚未启用'}, status=status.HTTP_403_FORBIDDEN)
        if ip_login_blocked(ip_address):
            lock_minutes = login_lock_policy(login_config)['ip_lock_minutes']
            write_login_log('', ip_address, 'failed', '来源 IP 登录失败次数过多，暂时锁定', auth_method='sms+otp')
            return Response({
                'detail': f'来源 IP 登录失败次数过多，已锁定，请 {lock_minutes} 分钟后重试',
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        serializer = serializers.SmsLoginSendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if not captcha_valid(data['captcha_token'], data['captcha_code']):
            write_login_log('', ip_address, 'failed', '验证码错误或已过期', auth_method='sms+otp')
            return Response({'detail': '验证码错误或已过期'}, status=status.HTTP_400_BAD_REQUEST)
        if not consume_slider_verification(data['slider_verification'], ip_address):
            write_login_log('', ip_address, 'failed', '图形拖拽验证失败或已过期', auth_method='sms+otp')
            return Response({'detail': '图形拖拽验证失败或已过期'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = issue_sms_login_challenge(data['phone'], ip_address, data['client_nonce'])
        except NotificationRateLimitError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        except (NotificationConfigurationError, NotificationSendError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_503_SERVICE_UNAVAILABLE)
        return no_store_response(payload)


class SmsLoginVerifyView(APIView):
    """验证一次性短信验证码并签发后续 OTP 预认证事务。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """验证短信挑战、错误锁定、用户状态和 Licence 后进入 OTP。

        参数：`request` 包含短信挑战令牌、六位验证码和浏览器随机值。
        返回：成功时返回 OTP 验证步骤；失败时返回统一中文说明。
        副作用：消费或更新短信挑战与用户锁定状态，并写入失败用户日志。
        """
        ip_address = request_client_ip(request)
        ip_allowed, denial_reason = login_ip_access_result(ip_address)
        if not ip_allowed:
            write_login_log('', ip_address, 'failed', denial_reason, auth_method='sms+otp')
            return Response({'detail': '当前来源地址不允许登录'}, status=status.HTTP_403_FORBIDDEN)
        login_config = login_security_settings()
        if not login_config.get('sms_login_enabled'):
            return Response({'detail': '短信登录尚未启用'}, status=status.HTTP_403_FORBIDDEN)
        serializer = serializers.SmsLoginVerifySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = verify_sms_login_challenge(
            data['challenge_token'],
            data['code'],
            ip_address,
            data['client_nonce'],
        )
        user = result.get('user')
        if not result['success']:
            write_login_log(
                user.username if user else '',
                ip_address,
                'failed',
                result['detail'],
                user=user,
                auth_method='sms+otp',
            )
            response_status = status.HTTP_429_TOO_MANY_REQUESTS if result['locked'] else status.HTTP_400_BAD_REQUEST
            return Response({'detail': result['detail']}, status=response_status)
        denial = license_access_denial(user)
        if denial:
            write_login_log(user.username, ip_address, 'failed', denial['detail'], user=user, auth_method='sms+otp')
            return Response({'detail': denial['detail'], 'code': denial['code']}, status=status.HTTP_403_FORBIDDEN)
        otp_status = otp_status_payload(user, platform_enabled=True)
        if otp_status['otp_status'] == 'locked':
            lock_minutes = login_lock_policy(login_config)['otp_lock_minutes']
            write_login_log(user.username, ip_address, 'failed', 'OTP 验证已锁定，请稍后重试', user=user, auth_method='sms+otp')
            return Response({
                'detail': f'OTP 输入错误次数过多，已锁定 {lock_minutes} 分钟，请稍后重试',
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)
        preauth_token = issue_login_transaction(user, ip_address, data['client_nonce'], 'verify', auth_method='sms')
        return no_store_response({
            'next_step': 'otp_verify',
            'preauth_token': preauth_token,
            'expires_in': OTP_TRANSACTION_SECONDS,
            'sms_code_expires_in': SMS_CODE_TTL_SECONDS,
        })


class OtpSetupView(APIView):
    """为通过第一阶段认证的未绑定用户提供临时 otpauth 内容。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验预认证事务并返回仅本次绑定使用的二维码内容。

        参数：`request` 包含预认证令牌和浏览器会话随机值。
        返回：标准 otpauth URI 和临时有效期。
        副作用：在缓存事务中生成或复用临时 TOTP 种子，不写日志。
        """
        token = str(request.data.get('preauth_token', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        ip_address = request_client_ip(request)
        payload = load_login_transaction(token, ip_address, client_nonce, 'bind')
        user = otp_transaction_user(payload or {})
        if not payload or not user:
            return Response({'detail': 'OTP 绑定会话已失效，请重新登录'}, status=status.HTTP_401_UNAUTHORIZED)
        return no_store_response(setup_payload(token, payload, user.username))


class OtpConfirmView(APIView):
    """确认首个 TOTP 口令，完成绑定并签发正式登录令牌。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """验证临时种子的动态口令并完成一次性绑定。

        参数：`request` 包含预认证令牌、会话随机值和六位动态口令。
        返回：正式令牌和用户数据。
        副作用：加密保存种子、消费事务并分别写入系统和用户日志。
        """
        token = str(request.data.get('preauth_token', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        code = str(request.data.get('code', '')).strip()
        ip_address = request_client_ip(request)
        payload = load_login_transaction(token, ip_address, client_nonce, 'bind')
        user = otp_transaction_user(payload or {})
        if not payload or not user or not payload.get('setup_secret'):
            return Response({'detail': 'OTP 绑定会话已失效，请重新登录'}, status=status.HTTP_401_UNAUTHORIZED)
        timestep = matching_timestep(payload['setup_secret'], code)
        if timestep is None:
            locked = register_setup_failure(token, payload, user)
            reason = '动态口令错误或已过期'
            write_login_log(user.username, ip_address, 'failed', reason, user=user, auth_method=otp_transaction_auth_method(payload))
            response_status = status.HTTP_429_TOO_MANY_REQUESTS if locked else status.HTTP_400_BAD_REQUEST
            detail = (
                f'OTP 绑定验证失败次数过多，已锁定 {login_lock_policy()["otp_lock_minutes"]} 分钟'
                if locked else reason
            )
            return Response({'detail': detail}, status=response_status)
        bind_user_otp(user, payload['setup_secret'], timestep)
        consume_login_transaction(token)
        models.AuditLog.objects.create(
            organization=user_organization(user),
            actor=user.username,
            action='User.otp_bind',
            resource=user.username,
            ip_address=ip_address,
            detail={'user_id': user.id, 'result': 'success'},
        )
        user = User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)
        return no_store_response(authenticated_login_payload(user, ip_address, otp_transaction_auth_method(payload)))


class OtpVerifyView(APIView):
    """验证已绑定用户的 TOTP 并完成登录。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """消费六位动态口令，成功后才签发正式令牌。

        参数：`request` 包含预认证令牌、会话随机值和 OTP 凭据。
        返回：成功时返回正式令牌和用户数据，失败时返回统一中文说明。
        副作用：事务更新防重放时间步或锁定状态，并写入用户日志。
        """
        token = str(request.data.get('preauth_token', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        credential = str(request.data.get('credential', '')).strip()
        ip_address = request_client_ip(request)
        payload = load_login_transaction(token, ip_address, client_nonce, 'verify')
        user = otp_transaction_user(payload or {})
        if not payload or not user:
            return Response({'detail': 'OTP 验证会话已失效，请重新登录'}, status=status.HTTP_401_UNAUTHORIZED)
        result = verify_user_otp(user, credential)
        if not result['success']:
            write_login_log(
                user.username,
                ip_address,
                'failed',
                result['detail'],
                user=user,
                auth_method=otp_transaction_auth_method(payload),
            )
            response_status = status.HTTP_429_TOO_MANY_REQUESTS if result['locked'] else status.HTTP_400_BAD_REQUEST
            return Response({'detail': result['detail']}, status=response_status)
        consume_login_transaction(token)
        return no_store_response(authenticated_login_payload(user, ip_address, otp_transaction_auth_method(payload)))


class PasswordResetStartView(APIView):
    """完成公开找回流程的反自动化校验并签发匿名一致的 OTP 事务。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验账号输入、字符验证码和拖拽凭证后开始找回事务。

        参数：`request` 包含用户名、浏览器随机值以及平台已启用的验证码凭证。
        返回：无论账号是否存在或可找回，均返回相同结构的 OTP 步骤响应。
        副作用：消费验证码凭证并在缓存中写入五分钟有效的一次性事务。
        """
        username = str(request.data.get('username', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        captcha_token = str(request.data.get('captcha_token', '')).strip()
        captcha_code = str(request.data.get('captcha_code', '')).strip()
        slider_verification = str(request.data.get('slider_verification', '')).strip()
        ip_address = request_client_ip(request)
        if not username:
            return Response({'detail': '请输入需要找回的用户名'}, status=status.HTTP_400_BAD_REQUEST)
        if len(client_nonce) < 16 or len(client_nonce) > 128:
            return Response({'detail': '找回会话已失效，请刷新页面'}, status=status.HTTP_400_BAD_REQUEST)

        ip_allowed, _denial_reason = login_ip_access_result(ip_address)
        if not ip_allowed:
            return Response({'detail': '当前来源地址不允许进行账号验证'}, status=status.HTTP_403_FORBIDDEN)
        if ip_login_blocked(ip_address):
            lock_minutes = login_lock_policy()['ip_lock_minutes']
            return Response({
                'detail': f'来源 IP 已被登录保护策略锁定，请 {lock_minutes} 分钟后重试',
            }, status=status.HTTP_429_TOO_MANY_REQUESTS)

        login_config = login_security_settings()
        if login_config.get('captcha_enabled'):
            if not captcha_token or not captcha_code:
                return Response({'detail': '请输入验证码'}, status=status.HTTP_400_BAD_REQUEST)
            if not captcha_valid(captcha_token, captcha_code):
                return Response({'detail': '验证码错误或已过期'}, status=status.HTTP_400_BAD_REQUEST)
        if login_config.get('slider_captcha_enabled'):
            if not slider_verification:
                return Response({'detail': '请完成图形拖拽验证'}, status=status.HTTP_400_BAD_REQUEST)
            if not consume_slider_verification(slider_verification, ip_address):
                return Response({'detail': '图形拖拽验证失败或已过期'}, status=status.HTTP_400_BAD_REQUEST)

        user = eligible_reset_user(username)
        reset_token = issue_reset_transaction(user, ip_address, client_nonce, step='otp')
        return no_store_response({
            'next_step': 'otp',
            'reset_token': reset_token,
            'expires_in': PASSWORD_RESET_SECONDS,
            'detail': '如账号可用于自助找回，请继续验证已绑定的动态令牌',
        })


class PasswordResetOtpView(APIView):
    """验证找回事务中的六位 TOTP 并签发一次性改密资格。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验绑定于账号的六位 TOTP。

        参数：`request` 包含找回事务令牌、浏览器随机值和六位动态口令。
        返回：成功时返回新的改密事务令牌，失败时返回统一令牌错误。
        副作用：更新 OTP 防重放与锁定状态，成功时消费原事务并写系统审计。
        """
        token = str(request.data.get('reset_token', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        credential = str(request.data.get('credential', '')).strip()
        ip_address = request_client_ip(request)
        payload = load_reset_transaction(token, ip_address, client_nonce, 'otp')
        if not payload:
            return Response({'detail': '找回会话已失效，请重新开始'}, status=status.HTTP_401_UNAUTHORIZED)

        user = reset_transaction_user(payload)
        if not user:
            simulate_anonymous_totp_check(credential)
            locked = register_anonymous_otp_failure(token, payload)
            detail = (
                f'动态令牌错误次数过多，已锁定 {login_lock_policy()["otp_lock_minutes"]} 分钟'
                if locked else '动态令牌无效或已过期'
            )
            response_status = status.HTTP_429_TOO_MANY_REQUESTS if locked else status.HTTP_400_BAD_REQUEST
            return Response({'detail': detail}, status=response_status)

        result = verify_user_otp(user, credential)
        if not result['success']:
            models.AuditLog.objects.create(
                organization=user_organization(user),
                actor=user.username,
                action='User.password_reset_otp_failed',
                resource=user.username,
                ip_address=ip_address,
                detail={'user_id': user.id, 'result': 'failed', 'reason': 'invalid_or_expired'},
            )
            if result['locked']:
                consume_reset_transaction(token)
            response_status = status.HTTP_429_TOO_MANY_REQUESTS if result['locked'] else status.HTTP_400_BAD_REQUEST
            detail = (
                f'动态令牌错误次数过多，已锁定 {login_lock_policy()["otp_lock_minutes"]} 分钟'
                if result['locked'] else '动态令牌无效或已过期'
            )
            return Response({'detail': detail}, status=response_status)

        consume_reset_transaction(token)
        password_token = issue_reset_transaction(user, ip_address, client_nonce, step='password')
        models.AuditLog.objects.create(
            organization=user_organization(user),
            actor=user.username,
            action='User.password_reset_otp_verified',
            resource=user.username,
            ip_address=ip_address,
            detail={'user_id': user.id, 'result': 'success', 'method': 'totp'},
        )
        password_policy = password_policy_settings()
        return no_store_response({
            'next_step': 'password',
            'password_token': password_token,
            'expires_in': PASSWORD_RESET_SECONDS,
            'password_policy': {
                'min_length': max(6, min(64, int(password_policy.get('min_length') or 8))),
                'require_uppercase': bool(password_policy.get('require_uppercase')),
                'require_lowercase': bool(password_policy.get('require_lowercase')),
                'require_number': bool(password_policy.get('require_number')),
                'require_special': bool(password_policy.get('require_special')),
                'exclude_username': bool(password_policy.get('exclude_username')),
            },
        })


class PasswordResetCompleteView(APIView):
    """消费一次性改密资格并按平台策略保存用户的新密码。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验改密事务和两次密码输入，撤销旧会话并完成找回。

        参数：`request` 包含改密事务、浏览器随机值、新密码和确认密码。
        返回：完成状态与用于登录页预填的用户名，不返回任何登录令牌。
        副作用：保存密码摘要、更新密码周期和认证版本、清除账号密码锁定并写系统审计。
        """
        token = str(request.data.get('password_token', '')).strip()
        client_nonce = str(request.data.get('client_nonce', '')).strip()
        new_password = str(request.data.get('new_password', ''))
        confirm_password = str(request.data.get('confirm_password', ''))
        ip_address = request_client_ip(request)
        payload = load_reset_transaction(token, ip_address, client_nonce, 'password')
        user = reset_transaction_user(payload or {})
        if not payload or not user:
            return Response({'detail': '改密资格已失效，请重新开始'}, status=status.HTTP_401_UNAUTHORIZED)
        if not new_password:
            return Response({'detail': '请输入新密码'}, status=status.HTTP_400_BAD_REQUEST)
        if new_password != confirm_password:
            return Response({'detail': '两次输入的密码不一致'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            validate_password(new_password, user.username)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if not consume_reset_transaction(token):
            return Response({'detail': '改密资格已使用，请重新开始'}, status=status.HTTP_401_UNAUTHORIZED)
        try:
            updated_user, restored_from_expiry = set_recovered_password(user, new_password)
        except PermissionError:
            return Response({'detail': '当前账号不允许自助找回密码'}, status=status.HTTP_403_FORBIDDEN)
        clear_user_login_failures(updated_user.username)
        models.AuditLog.objects.create(
            organization=user_organization(updated_user),
            actor=updated_user.username,
            action='User.password_reset',
            resource=updated_user.username,
            ip_address=ip_address,
            detail={
                'user_id': updated_user.id,
                'result': 'success',
                'restored_from_password_expiry': restored_from_expiry,
                'sessions_revoked': True,
            },
        )
        return no_store_response({
            'next_step': 'complete',
            'username': updated_user.username,
            'detail': '密码已更新，请使用新密码登录',
        })


class CaptchaView(APIView):
    """提供登录页所需的短期验证码。"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """返回验证码、签名令牌和有效秒数。"""
        if not login_security_settings().get('captcha_enabled'):
            return Response({'enabled': False, 'code': '', 'token': '', 'expires_in': 0})
        code, token = issue_login_captcha()
        return Response({'enabled': True, 'code': code, 'token': token, 'expires_in': CAPTCHA_MAX_AGE})


class SliderCaptchaView(APIView):
    """提供登录页拖拽拼图挑战和服务端位置验证。"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """按数据库开关返回新的短期拖拽挑战。

        参数：`request` 为当前匿名请求。
        返回：关闭状态或前端绘图所需的随机挑战参数。
        副作用：启用时向缓存写入一条短期挑战记录。
        """
        if not login_security_settings().get('slider_captcha_enabled'):
            return Response({'enabled': False, 'expires_in': 0})
        ip_address = request_client_ip(request)
        return Response({'enabled': True, **issue_slider_challenge(ip_address)})

    def post(self, request):
        """校验拖拽释放位置并返回一次性登录凭证。

        参数：`request` 包含挑战令牌、横向位置和拖拽耗时。
        返回：成功状态与短期登录验证凭证。
        副作用：消费挑战缓存；验证成功时写入一次性凭证缓存。
        """
        if not login_security_settings().get('slider_captcha_enabled'):
            return Response({'enabled': False, 'verified': True, 'verification_token': ''})
        ip_address = request_client_ip(request)
        verification_token = verify_slider_challenge(
            str(request.data.get('challenge_token', '')).strip(),
            request.data.get('offset_x'),
            request.data.get('elapsed_ms'),
            ip_address,
        )
        if not verification_token:
            return Response(
                {'detail': '拼图位置不正确，请重试'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response({
            'enabled': True,
            'verified': True,
            'verification_token': verification_token,
            'expires_in': SLIDER_MAX_AGE,
        })


class SwitchOrganizationView(APIView):
    """允许超级管理员切换当前数据隔离组织。"""

    def post(self, request):
        """切换用户部门、重新签发令牌并写入审计日志。"""
        organization_id = request.data.get('organization_id')
        organization = models.Organization.objects.filter(pk=organization_id).first()
        if not organization:
            return Response({'detail': '部门不存在'}, status=status.HTTP_404_NOT_FOUND)
        if not is_system_admin(request.user):
            return Response({'detail': '只有管理员可以切换部门'}, status=status.HTTP_403_FORBIDDEN)
        profile, _ = models.UserProfile.objects.get_or_create(
            user=request.user,
            defaults={'organization': organization, 'role': 'admin'},
        )
        profile.organization = organization
        profile.save(update_fields=['organization', 'updated_at'])
        tokens = issue_pair(request.user)
        models.AuditLog.objects.create(
            organization=organization,
            actor=request.user.username,
            action='auth.switch_org',
            resource=organization.slug,
            detail={'organization_id': organization.id},
        )
        return Response({**tokens, 'user': serializers.UserSerializer(request.user).data})


class RefreshView(APIView):
    """使用仍在有效期内的刷新令牌签发新令牌对。"""

    permission_classes = [permissions.AllowAny]

    def post(self, request):
        """校验刷新令牌及用户状态后返回新令牌。"""
        refresh = str(request.data.get('refresh', '')).strip()
        if not refresh:
            return Response({'detail': 'refresh token is required'}, status=status.HTTP_400_BAD_REQUEST)
        payload = decode_token(refresh, expected_type='refresh')
        user = User.objects.select_related('profile').filter(id=payload.get('sub'), is_active=True).first()
        if not user:
            return Response({'detail': 'Token 用户不存在或已停用'}, status=status.HTTP_401_UNAUTHORIZED)
        if not token_matches_auth_version(user, payload):
            return Response({'detail': '认证状态已变更，请重新登录'}, status=status.HTTP_401_UNAUTHORIZED)
        ip_allowed, denial_reason = login_ip_access_result(request_client_ip(request))
        if not ip_allowed:
            return Response(
                {'detail': f'当前来源地址不允许刷新登录状态：{denial_reason}'},
                status=status.HTTP_403_FORBIDDEN,
            )
        denial = license_access_denial(user)
        if denial:
            return Response(
                {'detail': denial['detail'], 'code': denial['code']},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(issue_access_from_refresh(user, payload))


class LogoutView(APIView):
    """撤销当前平台登录会话。"""

    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """撤销当前访问令牌对应的会话并返回空响应。"""
        from ops.services.login_sessions import revoke_login_session

        revoke_login_session(getattr(request, 'auth_payload', {}) or {})
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """返回当前登录用户及其数据库策略计算后的有效权限。"""

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """序列化当前认证用户。"""
        return Response(serializers.UserSerializer(request.user).data)


class PublicPlatformSettingsView(APIView):
    """公开返回登录页所需品牌、备案、认证开关和平台时区。"""

    permission_classes = [permissions.AllowAny]

    def get(self, request):
        """过滤历史外网 Logo 和非法备案链接，并只公开非敏感登录显示设置。"""
        setting = models.SystemSetting.objects.filter(key='platform').order_by('organization_id', 'id').first()
        value = setting.value if setting and isinstance(setting.value, dict) else {}
        filing_setting = models.SystemSetting.objects.filter(key='platform.filing').order_by('organization_id', 'id').first()
        filing_value = filing_setting.value if filing_setting and isinstance(filing_setting.value, dict) else {}
        try:
            filing = serializers.normalize_filing_settings(filing_value)
        except ValueError:
            filing = serializers.normalize_filing_settings({})
        login_config = login_security_settings()
        raw_logo_url = value.get('logo_url')
        logo_url = serializers.normalize_local_asset_path(raw_logo_url) if raw_logo_url else DEFAULT_PLATFORM_LOGO_URL
        return Response({
            'name': value.get('name') or 'Ongrid',
            'logo_url': logo_url,
            **filing,
            'captcha_enabled': bool(login_config.get('captcha_enabled')),
            'slider_captcha_enabled': bool(login_config.get('slider_captcha_enabled')),
            'otp_enabled': bool(login_config.get('otp_enabled')),
            'sms_login_enabled': bool(login_config.get('sms_login_enabled')),
            'timezone': timezone_settings().get('timezone') or 'Asia/Shanghai',
            'watermark': watermark_settings(),
            'client_ip': request_client_ip(request),
        })


class SystemSettingDetailView(APIView):
    """按分类和键新增、编辑或删除单个平台设置。"""

    permission_classes = [AdminOnlyPermission]

    def _setting(self, category, key):
        """按组合设置键查询记录。"""
        return models.SystemSetting.objects.filter(key=f'{category}.{key}').first()

    def _write_audit(self, request, action_name, setting, result='success'):
        """记录设置新增、编辑或删除操作。"""
        models.AuditLog.objects.create(
            organization=user_organization(request.user),
            actor=getattr(request.user, 'username', 'system') or 'system',
            action=f'SystemSetting.{action_name}',
            resource=setting.key,
            ip_address=request_client_ip(request),
            detail={'id': setting.id, 'key': setting.key, 'result': result},
        )

    def put(self, request, category, key):
        """存在时更新设置，不存在时创建设置，并保留被遮盖的敏感值。"""
        setting_key = f'{category}.{key}'
        setting = models.SystemSetting.objects.filter(key=setting_key).first()
        payload = {
            'key': setting_key,
            'value': request.data.get('value', {}),
            'description': request.data.get('description', setting.description if setting else ''),
        }
        if setting:
            serializer = serializers.SystemSettingSerializer(
                setting,
                data=payload,
                partial=True,
                context={'request': request},
            )
            try:
                serializer.is_valid(raise_exception=True)
            except serializers.serializers.ValidationError:
                if setting_key == 'license.management':
                    self._write_audit(request, 'license_import', setting, result='failed')
                raise
            setting = serializer.save()
            action_name = 'license_import' if setting_key == 'license.management' else 'update'
        else:
            serializer = serializers.SystemSettingSerializer(
                data=payload,
                context={'request': request},
            )
            try:
                serializer.is_valid(raise_exception=True)
            except serializers.serializers.ValidationError:
                if setting_key == 'license.management':
                    audit_target = models.SystemSetting(key=setting_key)
                    audit_target.id = 0
                    self._write_audit(request, 'license_import', audit_target, result='failed')
                raise
            setting = serializer.save(organization=user_organization(request.user))
            action_name = 'license_import' if setting_key == 'license.management' else 'create'
        self._write_audit(request, action_name, setting)
        return Response(serializers.SystemSettingSerializer(setting).data)

    def delete(self, request, category, key):
        """删除指定设置并保留删除审计。"""
        setting = self._setting(category, key)
        if not setting:
            return Response({'detail': '设置不存在'}, status=status.HTTP_404_NOT_FOUND)
        self._write_audit(request, 'delete', setting)
        setting.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class SystemSettingRevealView(SystemSettingDetailView):
    """在具有查看敏感信息权限时返回未遮盖的设置值。"""

    def get(self, request, category, key):
        """返回指定设置的原始解密值。"""
        setting = self._setting(category, key)
        if not setting:
            return Response({'detail': '设置不存在'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'id': setting.id,
            'key': setting.key,
            'value': setting.value,
            'description': setting.description,
            'updated_at': setting.updated_at,
        })
