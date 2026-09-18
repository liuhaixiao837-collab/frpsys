from django.contrib.auth.models import User
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from platform_logs.serializers import AuditLogSerializer  # noqa: F401
from urllib.parse import urlsplit
import re

from data_security.fields import is_sensitive_key

from . import models
from .local_assets import normalize_local_asset_path
from .permission_catalog import (
    ROOT_MENU_ORDER_KEY,
    catalog_payload,
    menu_order_items_for_user,
    required_codes_for_permission,
)
from .permission_service import clear_permission_cache, effective_permission_codes
from .services.license_management import license_public_metadata, normalize_license_content
from .services.license_access import license_user_limit_denial
from .services.system_admin import SYSTEM_ADMIN_USERNAME, is_system_admin
from .services.platform_security import (
    DEFAULT_LOGIN_BLACKLIST,
    DEFAULT_LOGIN_SETTINGS,
    DEFAULT_LOGIN_WHITELIST,
    DEFAULT_PASSWORD_POLICY,
    DEFAULT_TIMEZONE_SETTINGS,
    DEFAULT_WATERMARK_SETTINGS,
    generate_compliant_password,
    login_lock_policy,
    login_security_settings,
    normalize_access_entries,
    normalize_access_descriptions,
    normalize_whitelist_entries,
    validate_password,
)
from .services.otp import otp_status_payload
from .services.phone_identity import normalize_mobile_phone, phone_lookup_hash
from .services.sms_login import invalidate_user_sms_challenges
from .services.notifications import SMS_PROVIDER_NAMES, SMS_PROVIDER_REQUIRED_FIELDS
from .services.llm_providers import (
    LLM_PROVIDER_DEFINITIONS,
    default_llm_settings,
    normalize_provider_base_url,
)


class SystemToolPingSerializer(serializers.Serializer):
    """Validate Ping target, packet count, and per-packet timeout."""

    target = serializers.CharField(max_length=253, trim_whitespace=True)
    count = serializers.IntegerField(min_value=1, max_value=5, default=4)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=5, default=2)


class SystemToolTelnetSerializer(serializers.Serializer):
    """Validate TCP connectivity target, port, and timeout."""

    target = serializers.CharField(max_length=253, trim_whitespace=True)
    port = serializers.IntegerField(min_value=1, max_value=65535)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=10, default=5)


class SystemToolCurlSerializer(serializers.Serializer):
    """Validate an in-memory Curl request."""

    target = serializers.CharField(max_length=2048, trim_whitespace=True)
    method = serializers.ChoiceField(choices=('GET', 'HEAD'), default='GET')
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=30, default=10)


class SystemToolTracerouteSerializer(serializers.Serializer):
    """Validate Traceroute target, hop limit, and timeout."""

    target = serializers.CharField(max_length=253, trim_whitespace=True)
    max_hops = serializers.IntegerField(min_value=1, max_value=30, default=20)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=5, default=2)


class SystemToolMtrSerializer(serializers.Serializer):
    """Validate Python MTR target and probe limits."""

    target = serializers.CharField(max_length=253, trim_whitespace=True)
    count = serializers.IntegerField(min_value=1, max_value=10, default=3)
    max_hops = serializers.IntegerField(min_value=1, max_value=30, default=20)
    timeout_seconds = serializers.IntegerField(min_value=1, max_value=5, default=2)


MASK = '********'


def normalize_filing_settings(value):
    """校验并标准化登录页备案配置，不允许非 HTTP(S) 链接进入公开页面。"""
    if not isinstance(value, dict):
        raise ValueError('备案配置格式无效')

    def clean_text(field, label):
        """清理备案文本并限制长度，避免异常内容进入登录页。"""
        text = str(value.get(field) or '').strip()
        if len(text) > 100:
            raise ValueError(f'{label}不能超过 100 个字符')
        return text

    def clean_url(field, label, record):
        """只接受与备案号配套的 HTTP(S) 绝对链接。"""
        url = str(value.get(field) or '').strip()
        if not record:
            return ''
        if not url:
            return ''
        if len(url) > 500:
            raise ValueError(f'{label}不能超过 500 个字符')
        parsed = urlsplit(url)
        if parsed.scheme not in {'http', 'https'} or not parsed.netloc:
            raise ValueError(f'{label}必须是 http 或 https 开头的完整地址')
        return url

    icp_record = clean_text('icp_record', '工信部备案号')
    public_security_record = clean_text('public_security_record', '公安部备案号')
    return {
        'icp_record': icp_record,
        'icp_url': clean_url('icp_url', '工信部备案链接', icp_record),
        'public_security_record': public_security_record,
        'public_security_url': clean_url(
            'public_security_url',
            '公安部备案链接',
            public_security_record,
        ),
    }


def default_role_code():
    """返回新用户默认使用的身份标签代码。"""
    return 'member'


def role_for_code(code):
    """按角色代码查询身份标签；不存在时返回空值。"""
    if not code:
        return None
    return models.Role.objects.filter(code=code).first()


def mask_secrets(value):
    """递归遮盖设置数据中的密码、密钥等敏感字段。"""
    if isinstance(value, dict):
        return {
            key: MASK if is_sensitive_key(key) and item else mask_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [mask_secrets(item) for item in value]
    return value


def preserve_masked(incoming, current):
    """更新设置时将遮盖符还原为原敏感值，避免误覆盖密文。"""
    if isinstance(incoming, dict):
        current = current if isinstance(current, dict) else {}
        merged = dict(current)
        for key, value in incoming.items():
            if value == MASK and is_sensitive_key(key):
                merged[key] = current.get(key, '')
            else:
                merged[key] = preserve_masked(value, current.get(key))
        return merged
    if isinstance(incoming, list):
        current = current if isinstance(current, list) else []
        return [
            preserve_masked(item, current[index] if index < len(current) else None)
            for index, item in enumerate(incoming)
        ]
    return incoming


class RoleSerializer(serializers.ModelSerializer):
    """序列化身份标签及其当前分配人数，不暴露旧权限字段。"""

    assigned_count = serializers.SerializerMethodField()

    class Meta:
        model = models.Role
        fields = [
            'id', 'code', 'name', 'description', 'rank', 'is_system',
            'is_active', 'assigned_count', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'assigned_count', 'created_at', 'updated_at']

    def get_assigned_count(self, obj):
        """返回使用该身份标签的用户数量。"""
        assigned_count = getattr(obj, 'assigned_count', None)
        if assigned_count is not None:
            return assigned_count
        return models.UserProfile.objects.filter(role=obj.code).count()


class UserSerializer(serializers.ModelSerializer):
    """负责用户、部门、身份标签、手机号和密码的读写转换。"""

    role = serializers.CharField(required=False, allow_blank=True, default='')
    role_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    role_name = serializers.SerializerMethodField()
    is_system_admin = serializers.SerializerMethodField()
    permissions = serializers.SerializerMethodField()
    title = serializers.CharField(required=False, allow_blank=True, default='')
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    organization = serializers.SerializerMethodField()
    department = serializers.SerializerMethodField()
    organization_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    department_id = serializers.IntegerField(write_only=True, required=False, allow_null=True)
    password = serializers.CharField(write_only=True, required=False, allow_blank=True, min_length=6)
    password_changed_at = serializers.SerializerMethodField()
    password_expired_locked = serializers.SerializerMethodField()
    otp_policy = serializers.ChoiceField(
        choices=models.UserProfile.OTP_POLICY_CHOICES,
        required=False,
        write_only=True,
    )
    otp_effective_enabled = serializers.SerializerMethodField()
    otp_bound = serializers.SerializerMethodField()
    otp_status = serializers.SerializerMethodField()
    otp_status_label = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = [
            'id', 'username', 'first_name', 'last_name', 'email', 'is_active',
            'role', 'role_id', 'role_name', 'is_system_admin', 'permissions', 'title', 'phone',
            'organization', 'organization_id', 'department', 'department_id', 'password',
            'password_changed_at', 'password_expired_locked', 'date_joined', 'last_login',
            'otp_policy', 'otp_effective_enabled', 'otp_bound', 'otp_status', 'otp_status_label',
        ]
        read_only_fields = ['id', 'is_system_admin', 'date_joined', 'last_login']

    def _profile_organization(self, obj):
        """读取用户档案中的所属部门。"""
        profile = getattr(obj, 'profile', None)
        return getattr(profile, 'organization', None) if profile else None

    def get_organization(self, obj):
        """返回兼容旧客户端的组织名称。"""
        organization = self._profile_organization(obj)
        return organization.name if organization else ''

    def get_department(self, obj):
        """返回用户所属部门名称。"""
        return self.get_organization(obj)

    def get_role_name(self, obj):
        """返回用户身份标签的显示名称。"""
        if is_system_admin(obj):
            return '超级管理员'
        profile = getattr(obj, 'profile', None)
        role_code = getattr(profile, 'role', 'viewer') if profile else 'viewer'
        role = role_for_code(role_code)
        return role.name if role else role_code

    def get_is_system_admin(self, obj):
        """返回当前用户是否为系统唯一的 admin 超级管理员。"""
        return is_system_admin(obj)

    def get_permissions(self, obj):
        """从数据库权限策略计算用户的有效权限代码。"""
        return effective_permission_codes(obj)

    def get_password_changed_at(self, obj):
        """返回用户最近一次密码周期起算时间。"""
        value = getattr(getattr(obj, 'profile', None), 'password_changed_at', None)
        return value.isoformat() if value else None

    def get_password_expired_locked(self, obj):
        """返回用户是否因密码超过有效期被系统禁用。"""
        return bool(getattr(getattr(obj, 'profile', None), 'password_expired_locked', False))

    def _otp_status(self, obj):
        """返回已脱敏的用户 OTP 策略和绑定状态。"""
        cached = getattr(obj, '_serialized_otp_status', None)
        if cached is not None:
            return cached
        if not hasattr(self, '_otp_platform_enabled'):
            self._otp_platform_enabled = bool(login_security_settings().get('otp_enabled'))
        cached = otp_status_payload(obj, platform_enabled=self._otp_platform_enabled)
        obj._serialized_otp_status = cached
        return cached

    def get_otp_effective_enabled(self, obj):
        """返回用户当前是否必须使用 OTP。"""
        return self._otp_status(obj)['otp_effective_enabled']

    def get_otp_bound(self, obj):
        """返回用户是否已完成 OTP 绑定。"""
        return self._otp_status(obj)['otp_bound']

    def get_otp_status(self, obj):
        """返回用户 OTP 状态代码。"""
        return self._otp_status(obj)['otp_status']

    def get_otp_status_label(self, obj):
        """返回用户 OTP 状态的中文文字。"""
        return self._otp_status(obj)['otp_status_label']

    def to_representation(self, instance):
        """将用户档案字段合并为前端需要的友好结构。"""
        data = super().to_representation(instance)
        profile = getattr(instance, 'profile', None)
        role_code = getattr(profile, 'role', 'viewer') if profile else 'viewer'
        role = role_for_code(role_code)
        data['role'] = role_code
        data['role_id'] = role.id if role else None
        data['title'] = getattr(profile, 'title', '') if profile else ''
        data['phone'] = getattr(profile, 'phone', '') if profile else ''
        data['otp_policy'] = getattr(profile, 'otp_policy', 'inherit') if profile else 'inherit'
        department_id = getattr(getattr(profile, 'organization', None), 'id', None) if profile else None
        data['organization_id'] = department_id
        data['department_id'] = department_id
        return data

    def validate_username(self, value):
        """保证用户名在新增和编辑场景下保持唯一。"""
        if str(value).casefold() == SYSTEM_ADMIN_USERNAME:
            if not self.instance or getattr(self.instance, 'username', '') != SYSTEM_ADMIN_USERNAME:
                raise serializers.ValidationError('用户名 admin 为系统保留名称')
            if value != SYSTEM_ADMIN_USERNAME:
                raise serializers.ValidationError('系统超级管理员 admin 不允许修改用户名')
        queryset = User.objects.filter(username=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('用户名已存在')
        return value

    def validate_phone(self, value):
        """标准化手机号并保证加密手机号对应的国密查询索引唯一。

        参数：`value` 为新增、编辑或导入提交的手机号。
        返回：空字符串或标准十一位手机号。
        副作用：只查询手机号索引，不输出或记录已有手机号。
        """
        if not str(value or '').strip():
            return ''
        try:
            normalized = normalize_mobile_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc
        queryset = models.UserProfile.objects.filter(phone_lookup_hash=phone_lookup_hash(normalized))
        if self.instance:
            queryset = queryset.exclude(user=self.instance)
        if queryset.exists():
            raise serializers.ValidationError('手机号已绑定其他用户，请更换手机号')
        return normalized

    def validate(self, attrs):
        """阻止通过用户接口改名或停用系统超级管理员 admin。"""
        attrs = super().validate(attrs)
        if self.instance and getattr(self.instance, 'username', '') == SYSTEM_ADMIN_USERNAME:
            if attrs.get('username', SYSTEM_ADMIN_USERNAME) != SYSTEM_ADMIN_USERNAME:
                raise serializers.ValidationError({'username': '系统超级管理员 admin 不允许修改用户名'})
            if attrs.get('is_active') is False:
                raise serializers.ValidationError({'is_active': '系统超级管理员 admin 不允许停用'})
        return attrs

    def validate_password(self, value):
        """按当前数据库密码策略校验用户提交的新密码。"""
        if not value:
            return value
        username = self.initial_data.get('username') or getattr(self.instance, 'username', '')
        try:
            return validate_password(value, username)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc

    def _organization(self, attrs):
        """解析提交的部门，并在编辑时保留原部门。"""
        request = self.context.get('request')
        current_org = getattr(getattr(getattr(request, 'user', None), 'profile', None), 'organization', None)
        org_id = attrs.pop('department_id', None)
        if org_id is None:
            org_id = attrs.pop('organization_id', None)
        organization = None
        if org_id:
            try:
                organization = models.Organization.objects.get(pk=org_id)
            except models.Organization.DoesNotExist as exc:
                raise serializers.ValidationError({'department_id': '部门不存在'}) from exc
        elif self.instance:
            existing = self._profile_organization(self.instance)
            if existing:
                return existing
        else:
            organization = current_org or models.Organization.objects.order_by('id').first()
        if not self.instance and organization and (organization.is_default or organization.parent_id is None):
            raise serializers.ValidationError({'department_id': '默认组织不能新增用户，请选择具体部门'})
        return organization

    def _role(self, attrs, current=None):
        """校验提交的身份标签并返回可用角色代码。"""
        role_id = attrs.pop('role_id', None)
        role_code = attrs.pop('role', None)
        if role_id is None and (role_code is None or str(role_code).strip() == ''):
            return current if current is not None else default_role_code()
        try:
            role = (
                models.Role.objects.get(pk=role_id)
                if role_id
                else models.Role.objects.get(code=str(role_code or '').strip())
            )
        except models.Role.DoesNotExist as exc:
            raise serializers.ValidationError({'role': '角色不存在或未入库'}) from exc
        if not role.is_active:
            raise serializers.ValidationError({'role': '角色已停用'})
        return role.code

    def create(self, validated_data):
        """创建登录用户及其部门、身份标签和加密手机号档案。"""
        role = self._role(validated_data)
        title = validated_data.pop('title', '')
        phone = validated_data.pop('phone', '')
        otp_policy = validated_data.pop('otp_policy', 'inherit')
        password = validated_data.pop('password', '')
        organization = self._organization(validated_data)
        with transaction.atomic():
            models.SystemSetting.objects.select_for_update().filter(key='license.management').first()
            if validated_data.get('is_active', True):
                denial = license_user_limit_denial()
                if denial:
                    raise serializers.ValidationError({'is_active': denial['detail']})
            user = User(**validated_data)
            user.set_password(password or generate_compliant_password(user.username))
            user.save()
            models.UserProfile.objects.update_or_create(
                user=user,
                defaults={
                    'organization': organization,
                    'role': role,
                    'title': title,
                    'phone': phone,
                    'phone_lookup_hash': phone_lookup_hash(phone),
                    'password_changed_at': timezone.now(),
                    'password_expired_locked': False,
                    'otp_policy': otp_policy,
                },
            )
        return User.objects.select_related('profile', 'profile__organization').get(pk=user.pk)

    def update(self, instance, validated_data):
        """更新用户和档案；空密码不会覆盖现有密码。"""
        current_role = getattr(getattr(instance, 'profile', None), 'role', None)
        role = self._role(validated_data, current=current_role)
        title = validated_data.pop('title', None)
        phone = validated_data.pop('phone', None)
        otp_policy = validated_data.pop('otp_policy', None)
        password = validated_data.pop('password', None)
        organization = self._organization(validated_data)
        was_active = instance.is_active
        with transaction.atomic():
            models.SystemSetting.objects.select_for_update().filter(key='license.management').first()
            if not was_active and validated_data.get('is_active') is True:
                denial = license_user_limit_denial()
                if denial:
                    raise serializers.ValidationError({'is_active': denial['detail']})
            for key, value in validated_data.items():
                setattr(instance, key, value)
            if password:
                instance.set_password(password)
            instance.save()
            profile, _ = models.UserProfile.objects.get_or_create(
                user=instance,
                defaults={'organization': organization, 'role': role or ''},
            )
            if organization:
                profile.organization = organization
            if role is not None:
                profile.role = role
            if title is not None:
                profile.title = title
            if phone is not None:
                profile.phone = phone
                profile.phone_lookup_hash = phone_lookup_hash(phone)
                profile.sms_failed_attempts = 0
                profile.sms_locked_until = None
            if otp_policy is not None:
                profile.otp_policy = otp_policy
            if password:
                profile.password_changed_at = timezone.now()
                profile.password_expired_locked = False
            elif not was_active and instance.is_active and profile.password_expired_locked:
                profile.password_changed_at = timezone.now()
                profile.password_expired_locked = False
            profile.save()
            if phone is not None or (was_active and not instance.is_active):
                invalidate_user_sms_challenges(instance)
        return User.objects.select_related('profile', 'profile__organization').get(pk=instance.pk)


class OrganizationSerializer(serializers.ModelSerializer):
    """序列化部门树关系及成员、子部门统计。"""

    parent_id = serializers.PrimaryKeyRelatedField(
        source='parent',
        queryset=models.Organization.objects.all(),
        required=False,
        allow_null=True,
    )
    parent_name = serializers.CharField(source='parent.name', read_only=True, default='')
    member_count = serializers.SerializerMethodField()
    children_count = serializers.SerializerMethodField()
    is_root = serializers.SerializerMethodField()

    class Meta:
        model = models.Organization
        fields = [
            'id', 'name', 'slug', 'description', 'region', 'parent_id', 'parent_name',
            'org_type', 'is_default', 'is_active', 'is_root', 'member_count', 'children_count',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'is_root', 'member_count', 'children_count', 'created_at', 'updated_at']

    def get_member_count(self, obj):
        """优先返回视图计算的本部门及全部下级部门成员总数。"""
        member_counts = self.context.get('organization_member_counts') or {}
        if obj.pk in member_counts:
            return member_counts[obj.pk]
        value = getattr(obj, 'member_count', None)
        return value if value is not None else obj.profiles.count()

    def get_children_count(self, obj):
        """优先返回查询注解中的直接子部门数。"""
        value = getattr(obj, 'children_count', None)
        return value if value is not None else obj.children.count()

    def get_is_root(self, obj):
        """判断组织是否为公司根节点。"""
        return obj.parent_id is None

    def validate(self, attrs):
        """禁止将组织挂到自身或自己的下级节点。"""
        parent = attrs.get('parent')
        instance = self.instance
        if instance and parent:
            if parent.pk == instance.pk:
                raise serializers.ValidationError({'parent_id': '组织不能选择自己作为上级'})
            cursor = parent
            while cursor:
                if cursor.pk == instance.pk:
                    raise serializers.ValidationError({'parent_id': '不能把组织移动到自己的下级'})
                cursor = cursor.parent
        return attrs


class MaskedConfigSerializer(serializers.ModelSerializer):
    """为包含敏感配置的模型统一提供遮盖和保留逻辑。"""

    config_field = 'value'

    def to_representation(self, instance):
        """输出设置时遮盖敏感字段。"""
        data = super().to_representation(instance)
        data[self.config_field] = mask_secrets(data.get(self.config_field))
        return data

    def update(self, instance, validated_data):
        """更新设置时保留提交为遮盖符的原敏感值。"""
        if self.config_field in validated_data:
            validated_data[self.config_field] = preserve_masked(
                validated_data[self.config_field],
                getattr(instance, self.config_field, {}),
            )
        return super().update(instance, validated_data)


class SystemSettingSerializer(MaskedConfigSerializer):
    """序列化平台设置，并阻止外网资源地址进入平台品牌配置。"""

    class Meta:
        model = models.SystemSetting
        fields = '__all__'

    def to_representation(self, instance):
        """输出平台设置，并为 Licence 动态补充不含原文的有效期状态。"""
        data = super().to_representation(instance)
        if instance.key == 'license.management':
            metadata = license_public_metadata(instance.value)
            data['value'] = {
                **metadata,
                'license_secret': MASK if metadata.get('configured') else '',
            }
        return data

    def validate_key(self, value):
        """保证平台设置键唯一。"""
        queryset = models.SystemSetting.objects.filter(key=value)
        if self.instance:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            raise serializers.ValidationError('配置项已存在，请编辑原配置')
        return value

    def validate(self, attrs):
        """校验平台 Logo、备案、访问策略、登录选项、通知、Licence 和统一时区。"""
        attrs = super().validate(attrs)
        key = attrs.get('key') or getattr(self.instance, 'key', '')
        value = attrs.get('value')
        if key == 'platform' and isinstance(value, dict):
            value = dict(value)
            value['logo_url'] = normalize_local_asset_path(value.get('logo_url'), raise_error=True)
            attrs['value'] = value
        elif key == 'platform.filing':
            try:
                attrs['value'] = normalize_filing_settings(value)
            except ValueError as exc:
                raise serializers.ValidationError({'value': str(exc)}) from exc
        elif key == 'security.login_whitelist':
            attrs['value'] = self._validate_login_whitelist(value)
        elif key == 'security.login_blacklist':
            attrs['value'] = self._validate_login_blacklist(value)
        elif key == 'security.password_policy':
            attrs['value'] = self._validate_password_policy(value)
        elif key == 'security.login':
            attrs['value'] = self._validate_login_settings(value)
        elif key == 'notification.delivery':
            attrs['value'] = self._validate_notification_settings(value)
        elif key == 'llm.providers':
            attrs['value'] = self._validate_llm_settings(value)
        elif key == 'locale.timezone':
            attrs['value'] = self._validate_timezone(value)
        elif key == 'security.watermark':
            attrs['value'] = self._validate_watermark(value)
        elif key == 'license.management':
            attrs['value'] = self._validate_license(value)
        return attrs

    def _validate_login_whitelist(self, value):
        """校验白名单开关、IP/CIDR 条目和用途说明，并返回标准配置。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '白名单配置格式无效'})
        try:
            entries = normalize_whitelist_entries(value.get('entries', []))
        except ValueError as exc:
            raise serializers.ValidationError({'value': str(exc)}) from exc
        enabled = bool(value.get('enabled'))
        if enabled and not entries:
            raise serializers.ValidationError({'value': '启用白名单前至少填写一个 IP 或 CIDR'})
        try:
            descriptions = normalize_access_descriptions(entries, value.get('descriptions', {}), '白名单')
        except ValueError as exc:
            raise serializers.ValidationError({'value': str(exc)}) from exc
        return {
            **DEFAULT_LOGIN_WHITELIST,
            'enabled': enabled,
            'entries': entries,
            'descriptions': descriptions,
        }

    def _validate_login_blacklist(self, value):
        """校验黑名单开关、IP/CIDR 条目和用途说明，并返回标准配置。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '黑名单配置格式无效'})
        try:
            entries = normalize_access_entries(value.get('entries', []), '黑名单')
        except ValueError as exc:
            raise serializers.ValidationError({'value': str(exc)}) from exc
        enabled = bool(value.get('enabled'))
        if enabled and not entries:
            raise serializers.ValidationError({'value': '启用黑名单前至少填写一个 IP 或 CIDR'})
        try:
            descriptions = normalize_access_descriptions(entries, value.get('descriptions', {}), '黑名单')
        except ValueError as exc:
            raise serializers.ValidationError({'value': str(exc)}) from exc
        return {
            **DEFAULT_LOGIN_BLACKLIST,
            'enabled': enabled,
            'entries': entries,
            'descriptions': descriptions,
        }

    def _validate_license(self, value):
        """校验 Licence 原文，并只返回可加密保存的原文与安全元数据。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': 'Licence 配置格式无效'})
        content = value.get('license_secret', '')
        if content == MASK and self.instance:
            return self.instance.value
        try:
            return normalize_license_content(content)
        except ValueError as exc:
            raise serializers.ValidationError({'value': str(exc)}) from exc

    def _validate_password_policy(self, value):
        """校验密码最小长度和复杂度开关，并返回完整策略。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '密码策略格式无效'})
        try:
            min_length = int(value.get('min_length', DEFAULT_PASSWORD_POLICY['min_length']))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({'value': '密码最小长度必须是整数'}) from exc
        try:
            max_age_days = int(value.get('max_age_days', DEFAULT_PASSWORD_POLICY['max_age_days']))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({'value': '密码有效期天数必须是整数'}) from exc
        if min_length < 6 or min_length > 64:
            raise serializers.ValidationError({'value': '密码最小长度必须在 6 到 64 位之间'})
        if max_age_days < 0 or max_age_days > 3650:
            raise serializers.ValidationError({'value': '密码有效期天数必须在 0 到 3650 天之间，0 表示不启用'})
        return {
            'min_length': min_length,
            'require_uppercase': bool(value.get('require_uppercase')),
            'require_lowercase': bool(value.get('require_lowercase')),
            'require_number': bool(value.get('require_number')),
            'require_special': bool(value.get('require_special')),
            'exclude_username': bool(value.get('exclude_username')),
            'max_age_days': max_age_days,
        }

    def _validate_login_settings(self, value):
        """校验登录认证开关以及密码、OTP 错误锁定策略。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '登录设置格式无效'})
        integer_fields = {
            'login_failure_limit': ('密码失败次数', 3, 20),
            'login_lock_minutes': ('密码锁定时长', 1, 1440),
            'ip_failure_limit': ('IP 失败次数', 5, 200),
            'ip_lock_minutes': ('IP 锁定时长', 1, 1440),
            'otp_failure_limit': ('OTP 失败次数', 3, 20),
            'otp_lock_minutes': ('OTP 锁定时长', 1, 1440),
            'sms_failure_limit': ('短信验证码失败次数', 3, 20),
            'sms_lock_minutes': ('短信验证码锁定时长', 1, 1440),
        }
        normalized = {}
        for field, (label, minimum, maximum) in integer_fields.items():
            try:
                normalized[field] = int(value.get(field, DEFAULT_LOGIN_SETTINGS[field]))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({'value': f'{label}必须是整数'}) from exc
            if normalized[field] < minimum or normalized[field] > maximum:
                raise serializers.ValidationError({
                    'value': f'{label}必须在 {minimum} 到 {maximum} 之间',
                })
        sms_login_enabled = bool(value.get('sms_login_enabled'))
        captcha_enabled = bool(value.get('captcha_enabled'))
        slider_captcha_enabled = bool(value.get('slider_captcha_enabled'))
        otp_enabled = bool(value.get('otp_enabled'))
        if sms_login_enabled and not all([captcha_enabled, slider_captcha_enabled, otp_enabled]):
            raise serializers.ValidationError({
                'value': '启用短信登录前必须同时启用登录验证码、图形拖拽验证和平台 OTP 认证',
            })
        notification = models.SystemSetting.objects.filter(key='notification.delivery').first()
        delivery = notification.value if notification and isinstance(notification.value, dict) else {}
        sms = delivery.get('sms', {}) if isinstance(delivery.get('sms', {}), dict) else {}
        sms_provider = str(sms.get('provider') or 'aliyun').strip().lower()
        sms_required_fields = SMS_PROVIDER_REQUIRED_FIELDS.get(sms_provider, ())
        sms_ready = bool(
            sms.get('enabled')
            and sms_required_fields
            and all(str(sms.get(field) or '').strip() for field in sms_required_fields)
        )
        if sms_login_enabled and not sms_ready:
            raise serializers.ValidationError({'value': '启用短信登录前必须先启用并完整配置短信网关'})
        return {
            **DEFAULT_LOGIN_SETTINGS,
            'captcha_enabled': captcha_enabled,
            'slider_captcha_enabled': slider_captcha_enabled,
            'otp_enabled': otp_enabled,
            'sms_login_enabled': sms_login_enabled,
            **login_lock_policy({**value, **normalized}),
        }

    def _validate_timezone(self, value):
        """校验平台时区使用受支持的 IANA 时区名称。"""
        supported = {'Asia/Shanghai', 'Asia/Hong_Kong', 'Asia/Tokyo', 'Asia/Singapore', 'UTC'}
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '时区设置格式无效'})
        timezone_name = str(value.get('timezone') or DEFAULT_TIMEZONE_SETTINGS['timezone']).strip()
        if timezone_name not in supported:
            raise serializers.ValidationError({'value': '请选择系统支持的时区'})
        return {'timezone': timezone_name}

    def _validate_watermark(self, value):
        """校验并标准化全局水印的内容、布局和视觉参数。"""
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '水印设置格式无效'})

        content_type = str(value.get('content_type') or DEFAULT_WATERMARK_SETTINGS['content_type'])
        if content_type not in {'username', 'username_ip', 'platform', 'custom'}:
            raise serializers.ValidationError({'value': '请选择系统支持的水印内容类型'})
        layout = str(value.get('layout') or DEFAULT_WATERMARK_SETTINGS['layout'])
        if layout not in {'tiled', 'center'}:
            raise serializers.ValidationError({'value': '请选择系统支持的水印布局'})
        custom_text = str(value.get('custom_text') or '').strip()
        if len(custom_text) > 40:
            raise serializers.ValidationError({'value': '自定义水印文字不能超过 40 个字符'})
        if bool(value.get('enabled')) and content_type == 'custom' and not custom_text:
            raise serializers.ValidationError({'value': '启用自定义水印前请填写水印文字'})

        color = str(value.get('color') or DEFAULT_WATERMARK_SETTINGS['color']).strip().lower()
        if not re.fullmatch(r'#[0-9a-f]{6}', color):
            raise serializers.ValidationError({'value': '水印颜色必须使用六位十六进制颜色'})

        integer_fields = {
            'font_size': ('字体大小', 11, 28),
            'font_weight': ('字体粗细', 400, 600),
            'rotate': ('旋转角度', -60, 60),
            'horizontal_gap': ('水平间距', 140, 480),
            'vertical_gap': ('垂直间距', 90, 320),
        }
        normalized = {}
        for field, (label, minimum, maximum) in integer_fields.items():
            try:
                normalized[field] = int(value.get(field, DEFAULT_WATERMARK_SETTINGS[field]))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({'value': f'{label}必须是整数'}) from exc
            if normalized[field] < minimum or normalized[field] > maximum:
                raise serializers.ValidationError({'value': f'{label}必须在 {minimum} 到 {maximum} 之间'})
        if normalized['font_weight'] not in {400, 500, 600}:
            raise serializers.ValidationError({'value': '字体粗细只支持常规、中等或半粗体'})

        try:
            opacity = float(value.get('opacity', DEFAULT_WATERMARK_SETTINGS['opacity']))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({'value': '水印透明度必须是数字'}) from exc
        if opacity < 0.05 or opacity > 0.35:
            raise serializers.ValidationError({'value': '水印透明度必须在 0.05 到 0.35 之间'})

        return {
            'enabled': bool(value.get('enabled')),
            'content_type': content_type,
            'custom_text': custom_text,
            'layout': layout,
            'show_time': bool(value.get('show_time')),
            'color': color,
            'opacity': round(opacity, 2),
            **normalized,
        }

    def _validate_llm_settings(self, value):
        """校验六家内置 LLM 厂商、优先级和加密凭据配置。"""
        if not isinstance(value, dict) or not isinstance(value.get('providers'), list):
            raise serializers.ValidationError({'value': 'LLM 配置格式无效'})
        submitted = value['providers']
        expected_codes = set(LLM_PROVIDER_DEFINITIONS)
        submitted_codes = [
            str(item.get('code') or '').strip().lower()
            for item in submitted if isinstance(item, dict)
        ]
        if len(submitted) != len(expected_codes) or set(submitted_codes) != expected_codes:
            raise serializers.ValidationError({'value': 'LLM 配置必须完整包含六家内置厂商'})
        if len(submitted_codes) != len(set(submitted_codes)):
            raise serializers.ValidationError({'value': 'LLM 厂商不能重复'})

        current_value = self.instance.value if self.instance and isinstance(self.instance.value, dict) else {}
        current_providers = {
            str(item.get('code') or ''): item
            for item in current_value.get('providers', []) if isinstance(item, dict)
        }
        submitted_providers = {item['code'].strip().lower(): item for item in submitted}
        defaults = {
            item['code']: item for item in default_llm_settings()['providers']
        }
        normalized = []
        for code, definition in LLM_PROVIDER_DEFINITIONS.items():
            provider = submitted_providers[code]
            previous = current_providers.get(code, {})
            model = str(provider.get('model') or '').strip()
            if not model:
                raise serializers.ValidationError({'value': f"请填写{definition['name']}模型名称"})
            if len(model) > 120:
                raise serializers.ValidationError({'value': '模型名称不能超过 120 个字符'})
            try:
                priority = int(provider.get('priority', definition['priority']))
            except (TypeError, ValueError) as exc:
                raise serializers.ValidationError({'value': 'LLM 优先级必须是整数'}) from exc
            if priority < 1 or priority > 100:
                raise serializers.ValidationError({'value': 'LLM 优先级必须在 1 到 100 之间'})
            try:
                base_url = normalize_provider_base_url(code, provider.get('base_url'))
            except ValueError as exc:
                raise serializers.ValidationError({'value': str(exc)}) from exc
            api_key = str(provider.get('api_key') or '').strip()
            if api_key in {'', MASK} and previous.get('api_key'):
                api_key = MASK
            if len(api_key) > 1024:
                raise serializers.ValidationError({'value': 'API Key 不能超过 1024 个字符'})
            enabled = bool(provider.get('enabled'))
            if enabled and not api_key:
                raise serializers.ValidationError({'value': f"启用{definition['name']}前请填写 API Key"})
            description = str(provider.get('description') or '').strip()
            if len(description) > 500:
                raise serializers.ValidationError({'value': 'LLM 厂商说明不能超过 500 个字符'})

            api_key_changed = bool(api_key and api_key != MASK and api_key != previous.get('api_key'))
            connection_changed = (
                api_key_changed
                or model != previous.get('model')
                or base_url != previous.get('base_url')
            )
            normalized.append({
                'name': definition['name'],
                'code': code,
                'model': model,
                'priority': priority,
                'enabled': enabled,
                'api_key': api_key,
                'base_url': base_url,
                'status': 'unchecked' if connection_changed else previous.get('status', defaults[code]['status']),
                'last_checked_at': '' if connection_changed else previous.get('last_checked_at', ''),
                'description': description,
            })
        return {'providers': normalized}

    def _validate_notification_settings(self, value):
        """校验邮件和验证码短信配置，并保留未重新填写的敏感凭据。

        参数：`value` 为包含 `email` 和 `sms` 的通知渠道配置。
        返回：字段完整、长度受限且可由 SM4 加密保存的标准配置。
        副作用：不发送邮件或短信，不直接写入数据库。
        """
        if not isinstance(value, dict):
            raise serializers.ValidationError({'value': '通知设置格式无效'})
        email = value.get('email', {})
        sms = value.get('sms', {})
        if not isinstance(email, dict) or not isinstance(sms, dict):
            raise serializers.ValidationError({'value': '邮件和短信配置必须是对象'})

        def clean_text(source, field, label, maximum=255):
            """清理单个通知配置文本并限制长度。

            参数：`source` 为渠道字典，`field` 为字段名，`label` 为中文名，`maximum` 为长度上限。
            返回：去除首尾空白后的字符串。
            副作用：不修改输入字典或持久化数据。
            """
            text = str(source.get(field) or '').strip()
            if len(text) > maximum:
                raise serializers.ValidationError({'value': f'{label}不能超过 {maximum} 个字符'})
            return text

        def clean_recipient_limits(source, channel_label, defaults):
            """校验单一收件邮箱或手机号的分钟、小时和每日发送上限。

            参数：`source` 为渠道配置，`channel_label` 为接收方名称，`defaults` 为默认上限。
            返回：三个窗口的正整数上限；窗口关系无效时抛出序列化错误。
            副作用：不修改输入配置。
            """
            fields = (
                ('recipient_limit_per_minute', '每分钟'),
                ('recipient_limit_per_hour', '每小时'),
                ('recipient_limit_per_day', '每天'),
            )
            limits = {}
            for field, period_label in fields:
                try:
                    limits[field] = int(source.get(field, defaults[field]))
                except (TypeError, ValueError) as exc:
                    raise serializers.ValidationError({
                        'value': f'{channel_label}{period_label}发送上限必须是整数',
                    }) from exc
                if limits[field] < 1 or limits[field] > 100000:
                    raise serializers.ValidationError({
                        'value': f'{channel_label}{period_label}发送上限必须在 1 到 100000 之间',
                    })
            if not (
                limits['recipient_limit_per_minute']
                <= limits['recipient_limit_per_hour']
                <= limits['recipient_limit_per_day']
            ):
                raise serializers.ValidationError({
                    'value': f'{channel_label}发送上限必须满足每分钟不大于每小时、每小时不大于每天',
                })
            return limits

        current = self.instance.value if self.instance and isinstance(self.instance.value, dict) else {}
        current_email = current.get('email', {}) if isinstance(current.get('email', {}), dict) else {}
        current_sms = current.get('sms', {}) if isinstance(current.get('sms', {}), dict) else {}

        smtp_host = clean_text(email, 'smtp_host', 'SMTP 主机')
        if smtp_host and any(character.isspace() for character in smtp_host):
            raise serializers.ValidationError({'value': 'SMTP 主机不能包含空格'})
        try:
            smtp_port = int(email.get('smtp_port', 465))
        except (TypeError, ValueError) as exc:
            raise serializers.ValidationError({'value': 'SMTP 端口必须是整数'}) from exc
        if smtp_port < 1 or smtp_port > 65535:
            raise serializers.ValidationError({'value': 'SMTP 端口必须在 1 到 65535 之间'})
        security = clean_text(email, 'security', '邮件连接安全方式', 20).lower() or 'ssl'
        if security not in {'ssl', 'starttls', 'none'}:
            raise serializers.ValidationError({'value': '邮件连接安全方式只支持 SSL、STARTTLS 或不加密'})
        sender_email = clean_text(email, 'sender_email', '发件箱邮箱', 254)
        if sender_email:
            try:
                validate_email(sender_email)
            except DjangoValidationError as exc:
                raise serializers.ValidationError({'value': '发件箱邮箱格式无效'}) from exc
        username = clean_text(email, 'username', 'SMTP 用户名')
        password = clean_text(email, 'password', 'SMTP 密码', 512)
        if password in {'', MASK} and current_email.get('password'):
            password = MASK
        email_enabled = bool(email.get('enabled'))
        email_limits = clean_recipient_limits(email, '同一收件邮箱', {
            'recipient_limit_per_minute': 5,
            'recipient_limit_per_hour': 100,
            'recipient_limit_per_day': 500,
        })
        if email_enabled and not all([smtp_host, sender_email, username, password]):
            raise serializers.ValidationError({
                'value': '启用发件箱邮箱前必须填写 SMTP 主机、发件箱邮箱、用户名和密码',
            })

        provider = clean_text(sms, 'provider', '短信服务商', 30).lower() or 'aliyun'
        if provider not in SMS_PROVIDER_REQUIRED_FIELDS:
            raise serializers.ValidationError({'value': '请选择平台支持的短信服务商'})
        sms_field_specs = {
            'access_key_id': ('AccessKey ID', 128),
            'access_key_secret': ('AccessKey Secret', 256),
            'secret_id': ('SecretId', 128),
            'secret_key': ('SecretKey', 256),
            'sdk_app_id': ('SmsSdkAppId', 64),
            'sign_name': ('短信签名', 100),
            'signature_id': ('签名 ID', 100),
            'authorization_token': ('Authorization Token', 512),
            'api_key': ('API Key', 256),
            'app_key': ('AppKey', 128),
            'app_secret': ('AppSecret', 256),
            'template_code': ('模板 ID/编码', 100),
        }
        sms_fields = {
            field: clean_text(sms, field, label, maximum)
            for field, (label, maximum) in sms_field_specs.items()
        }
        for field in ('access_key_secret', 'secret_id', 'secret_key', 'authorization_token', 'api_key', 'app_secret'):
            if sms_fields[field] in {'', MASK} and current_sms.get(field):
                sms_fields[field] = MASK
        sms_enabled = bool(sms.get('enabled'))
        sms_limits = clean_recipient_limits(sms, '同一手机号', {
            'recipient_limit_per_minute': 1,
            'recipient_limit_per_hour': 10,
            'recipient_limit_per_day': 50,
        })
        missing_fields = [
            field for field in SMS_PROVIDER_REQUIRED_FIELDS[provider]
            if not sms_fields.get(field)
        ]
        if sms_enabled and missing_fields:
            provider_name = SMS_PROVIDER_NAMES[provider]
            missing_labels = '、'.join(sms_field_specs[field][0] for field in missing_fields)
            raise serializers.ValidationError({
                'value': f'启用{provider_name}短信前请填写：{missing_labels}',
            })
        login_setting = models.SystemSetting.objects.filter(key='security.login').first()
        login_value = login_setting.value if login_setting and isinstance(login_setting.value, dict) else {}
        if login_value.get('sms_login_enabled') and not sms_enabled:
            raise serializers.ValidationError({'value': '短信登录启用期间不能禁用短信网关，请先关闭短信登录'})

        return {
            'email': {
                'enabled': email_enabled,
                'smtp_host': smtp_host,
                'smtp_port': smtp_port,
                'security': security,
                'sender_email': sender_email,
                'username': username,
                'password': password,
                **email_limits,
            },
            'sms': {
                'enabled': sms_enabled,
                'provider': provider,
                **sms_fields,
                **sms_limits,
            },
        }


class NotificationEmailTestSerializer(serializers.Serializer):
    """校验测试邮件的收件邮箱。"""

    recipient = serializers.EmailField(
        max_length=254,
        error_messages={
            'required': '请输入收件邮箱',
            'blank': '请输入收件邮箱',
            'invalid': '请输入有效的收件邮箱',
        },
    )


class NotificationSmsTestSerializer(serializers.Serializer):
    """校验并标准化测试短信的中国大陆手机号。"""

    phone = serializers.CharField(max_length=20, trim_whitespace=True)

    def validate_phone(self, value):
        """去除中国国家码并校验十一位大陆手机号。"""
        try:
            return normalize_mobile_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class LlmProviderTestSerializer(serializers.Serializer):
    """校验需要执行连通性检测的内置 LLM 厂商代码。"""

    provider = serializers.ChoiceField(
        choices=tuple(LLM_PROVIDER_DEFINITIONS),
        error_messages={
            'required': '请选择 LLM 厂商',
            'invalid_choice': '请选择平台支持的 LLM 厂商',
        },
    )

class SmsLoginSendSerializer(serializers.Serializer):
    """校验短信登录验证码发送请求。"""

    phone = serializers.CharField(max_length=20, trim_whitespace=True)
    captcha_token = serializers.CharField(max_length=200)
    captcha_code = serializers.CharField(max_length=12)
    slider_verification = serializers.CharField(max_length=200)
    client_nonce = serializers.CharField(min_length=16, max_length=128)

    def validate_phone(self, value):
        """标准化短信登录请求中的中国大陆手机号。"""
        try:
            return normalize_mobile_phone(value)
        except ValueError as exc:
            raise serializers.ValidationError(str(exc)) from exc


class SmsLoginVerifySerializer(serializers.Serializer):
    """校验短信验证码验证请求。"""

    challenge_token = serializers.CharField(min_length=20, max_length=200)
    code = serializers.RegexField(r'^\d{6}$', error_messages={'invalid': '请输入六位短信验证码'})
    client_nonce = serializers.CharField(min_length=16, max_length=128)


class MenuOrderUpdateSerializer(serializers.Serializer):
    """校验用户提交的完整分层菜单排序。"""

    orders = serializers.ListField(
        child=serializers.DictField(),
        allow_empty=False,
    )

    def validate_orders(self, value):
        """要求提交当前用户全部可见菜单，拒绝缺项、重复项和越权菜单代码。"""
        request = self.context.get('request')
        user = getattr(request, 'user', None)
        visible_items = menu_order_items_for_user(user)
        expected = {ROOT_MENU_ORDER_KEY: [item['code'] for item in visible_items]}

        def collect_children(items):
            """递归收集每个可见父节点下的完整同级菜单代码。

            参数：`items` 表示当前用户可见的排序菜单节点。
            返回：无显式返回值。
            副作用：把存在子菜单的父级及其代码顺序写入 `expected`。
            """
            for item in items:
                children = item.get('children', [])
                if children:
                    expected[item['code']] = [child['code'] for child in children]
                    collect_children(children)

        collect_children(visible_items)
        expected = {parent: codes for parent, codes in expected.items() if codes}

        normalized = []
        submitted_parents = []
        for item in value:
            parent_code = str(item.get('parent_code') or '').strip()
            codes = item.get('codes')
            if not parent_code or not isinstance(codes, list) or not codes:
                raise serializers.ValidationError('每组菜单必须包含父级代码和非空顺序')
            normalized_codes = [str(code).strip() for code in codes]
            if any(not code for code in normalized_codes):
                raise serializers.ValidationError('菜单代码不能为空')
            if len(normalized_codes) != len(set(normalized_codes)):
                raise serializers.ValidationError(f'{parent_code} 下存在重复菜单')
            if parent_code not in expected:
                raise serializers.ValidationError('包含无效的父级菜单')
            if set(normalized_codes) != set(expected[parent_code]):
                raise serializers.ValidationError(f'{parent_code} 下的菜单必须完整且全部有效')
            submitted_parents.append(parent_code)
            normalized.append({'parent_code': parent_code, 'codes': normalized_codes})
        if len(submitted_parents) != len(set(submitted_parents)):
            raise serializers.ValidationError('父级菜单排序存在重复项')
        if set(submitted_parents) != set(expected):
            raise serializers.ValidationError('必须提交全部可排序菜单组')
        return normalized


class PermissionRuleSerializer(serializers.ModelSerializer):
    """序列化单项权限的允许或拒绝状态。"""

    effect_label = serializers.SerializerMethodField()

    class Meta:
        model = models.PermissionRule
        fields = ['id', 'permission_code', 'effect', 'effect_label', 'created_at', 'updated_at']
        read_only_fields = ['id', 'effect_label', 'created_at', 'updated_at']

    def get_effect_label(self, obj):
        """返回用户友好的授权状态文本。"""
        return '允许' if obj.effect == 'allow' else '拒绝'


class PermissionPolicySerializer(serializers.ModelSerializer):
    """校验并保存部门或用户的完整权限策略。"""

    rules = PermissionRuleSerializer(many=True, required=False)
    subject_name = serializers.SerializerMethodField()
    subject_label = serializers.SerializerMethodField()

    class Meta:
        model = models.PermissionPolicy
        fields = [
            'id', 'name', 'subject_type', 'subject_name', 'subject_label', 'department', 'user',
            'priority', 'status', 'remark', 'rules', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'subject_name', 'subject_label', 'created_at', 'updated_at']

    def get_subject_name(self, obj):
        """返回授权对象的名称。"""
        if obj.subject_type == 'user' and obj.user:
            return obj.user.username
        if obj.department:
            return obj.department.name
        return ''

    def get_subject_label(self, obj):
        """返回带对象类型的授权对象说明。"""
        if obj.subject_type == 'user':
            return f'用户：{obj.user.username}' if obj.user else '用户：未选择'
        return f'部门：{obj.department.name}' if obj.department else '部门：未选择'

    def validate(self, attrs):
        """保证策略只关联与授权对象类型匹配的部门或用户。"""
        subject_type = attrs.get('subject_type', getattr(self.instance, 'subject_type', 'department'))
        department = attrs.get('department', getattr(self.instance, 'department', None))
        user = attrs.get('user', getattr(self.instance, 'user', None))
        if subject_type == 'department' and not department:
            raise serializers.ValidationError({'department': '请选择要授权的部门'})
        if subject_type == 'user' and not user:
            raise serializers.ValidationError({'user': '请选择要授权的用户'})
        return attrs

    def validate_rules(self, rules):
        """拒绝数据库权限目录中不存在或重复的权限代码。"""
        valid_codes = set(catalog_payload()['all_codes'])
        seen = set()
        for rule in rules:
            code = str(rule.get('permission_code') or '').strip()
            if code not in valid_codes:
                raise serializers.ValidationError(f'权限项不存在：{code or "空权限代码"}')
            if code in seen:
                raise serializers.ValidationError(f'权限项重复：{code}')
            seen.add(code)
        return rules

    def _save_rules(self, policy, rules):
        """按当前权限目录补齐全部规则，未提交的权限统一保存为拒绝。"""
        if rules is None:
            return
        valid_codes = catalog_payload()['all_codes']
        valid_code_set = set(valid_codes)
        submitted = {}
        for rule in rules:
            code = str(rule.get('permission_code') or '').strip()
            if not code:
                continue
            if code not in valid_code_set:
                raise serializers.ValidationError({'rules': f'权限项不存在：{code}'})
            effect = rule.get('effect')
            if effect not in ['allow', 'deny']:
                raise serializers.ValidationError({'rules': f'权限状态无效：{code}'})
            submitted[code] = effect
        for code in [code for code, effect in submitted.items() if effect == 'allow']:
            for required_code in required_codes_for_permission(code):
                submitted[required_code] = 'allow'
        normalized = [
            models.PermissionRule(
                policy=policy,
                permission_code=code,
                effect=submitted.get(code, 'deny'),
            )
            for code in valid_codes
        ]
        policy.rules.all().delete()
        models.PermissionRule.objects.bulk_create(normalized)
        clear_permission_cache()

    def create(self, validated_data):
        """创建策略并用默认拒绝补齐完整权限目录。"""
        rules = validated_data.pop('rules', [])
        policy = models.PermissionPolicy.objects.create(**validated_data)
        self._save_rules(policy, rules)
        return policy

    def update(self, instance, validated_data):
        """更新策略、清理不匹配的授权对象并重建规则。"""
        rules = validated_data.pop('rules', None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if instance.subject_type == 'department':
            instance.user = None
        if instance.subject_type == 'user':
            instance.department = None
        instance.save()
        self._save_rules(instance, rules)
        return instance
