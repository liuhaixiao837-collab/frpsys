from django.contrib.auth.models import User
from django.db import models
from django.utils import timezone

from data_security.fields import EncryptedCharField, EncryptedJSONField
from ops.model_docs import apply_model_field_help


class TimeStampedModel(models.Model):
    """为业务模型统一提供创建时间和最后更新时间。"""

    created_at = models.DateTimeField(default=timezone.now, help_text='记录创建时间。')
    updated_at = models.DateTimeField(auto_now=True, help_text='记录最后更新时间。')

    class Meta:
        abstract = True


class Organization(TimeStampedModel):
    """组织和部门树节点，用于用户归属、数据隔离和部门权限策略。"""

    TYPE_CHOICES = [
        ('company', '公司'),
        ('department', '部门'),
    ]

    name = models.CharField(max_length=120, unique=True, help_text='组织或部门的显示名称。')
    slug = models.SlugField(max_length=80, unique=True, help_text='组织的唯一英文标识，用于接口和令牌。')
    description = models.TextField(blank=True, help_text='组织或部门的用途说明。')
    region = models.CharField(max_length=80, blank=True, help_text='组织所在区域。')
    parent = models.ForeignKey(
        'self',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='children',
        help_text='上级组织；为空表示公司根节点。',
    )
    org_type = models.CharField(
        max_length=32,
        choices=TYPE_CHOICES,
        default='department',
        help_text='节点类型：公司或部门。',
    )
    is_default = models.BooleanField(default=False, help_text='是否为系统默认公司根节点。')
    is_active = models.BooleanField(default=True, help_text='组织是否可用。')

    class Meta:
        ordering = ['parent_id', 'name']
        indexes = [models.Index(fields=['parent', 'org_type'], name='ops_org_parent_type_idx')]

    def __str__(self):
        """返回组织名称，供后台和审计记录展示。"""
        return self.name


class Role(TimeStampedModel):
    """用户身份标签；功能授权统一由权限策略管理。"""

    code = models.SlugField(max_length=40, unique=True, help_text='角色唯一代码，写入用户档案和令牌。')
    name = models.CharField(max_length=80, help_text='角色显示名称。')
    description = models.TextField(blank=True, help_text='角色职责说明，不承载功能权限。')
    rank = models.PositiveIntegerField(default=10, help_text='角色展示排序权重，数值越大越靠前。')
    is_system = models.BooleanField(default=False, help_text='是否为不可删除的系统预置角色。')
    is_active = models.BooleanField(default=True, help_text='角色是否可分配给用户。')

    class Meta:
        ordering = ['-rank', 'name']
        indexes = [
            models.Index(fields=['code'], name='ops_role_code_idx'),
            models.Index(fields=['is_active', 'rank'], name='ops_role_active_rank_idx'),
        ]

    def __str__(self):
        """返回便于识别的角色名称和代码。"""
        return f'{self.name}({self.code})'


class UserProfile(TimeStampedModel):
    """扩展 Django 用户，保存部门、身份标签、密码周期和 OTP 安全状态。"""

    OTP_POLICY_CHOICES = [
        ('inherit', '跟随平台'),
        ('required', '强制启用'),
        ('exempt', '免于认证'),
    ]

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        help_text='关联的登录用户。',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='profiles',
        help_text='用户当前所属部门。',
    )
    role = models.CharField(max_length=32, default='sre', help_text='用户身份标签代码，不直接授予功能权限。')
    title = models.CharField(max_length=80, blank=True, help_text='用户岗位或职务。')
    phone = EncryptedCharField(max_length=512, blank=True, help_text='使用 SM4 加密保存的手机号码。')
    phone_lookup_hash = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        unique=True,
        help_text='使用带密钥 SM3-HMAC 生成的手机号查询索引，不保存手机号明文。',
    )
    password_changed_at = models.DateTimeField(default=timezone.now, help_text='用户最近一次修改密码或管理员解锁重置周期的时间。')
    password_expired_locked = models.BooleanField(default=False, help_text='是否因密码超过有效期被系统自动禁用。')
    otp_policy = models.CharField(
        max_length=16,
        choices=OTP_POLICY_CHOICES,
        default='inherit',
        help_text='用户 OTP 策略：跟随平台、强制启用或免于认证。',
    )
    otp_secret = EncryptedCharField(
        max_length=512,
        blank=True,
        help_text='使用 SM4 加密保存的 TOTP Base32 种子，接口和日志禁止返回。',
    )
    otp_bound_at = models.DateTimeField(null=True, blank=True, help_text='用户最近一次完成 OTP 绑定的时间。')
    otp_last_timestep = models.BigIntegerField(null=True, blank=True, help_text='最后一次成功使用的 TOTP 时间步，用于防止口令重放。')
    otp_failed_attempts = models.PositiveSmallIntegerField(default=0, help_text='当前连续 OTP 验证失败次数。')
    otp_locked_until = models.DateTimeField(null=True, blank=True, help_text='OTP 验证锁定截止时间；为空表示未锁定。')
    sms_failed_attempts = models.PositiveSmallIntegerField(default=0, help_text='短信验证码当前连续输入错误次数。')
    sms_locked_until = models.DateTimeField(null=True, blank=True, help_text='短信验证码验证锁定截止时间；为空表示未锁定。')
    auth_version = models.PositiveIntegerField(default=0, help_text='认证版本号，重置 OTP 时递增以使已签发令牌失效。')

    def __str__(self):
        """返回用户名和身份标签。"""
        return f'{self.user.username} / {self.role}'


class PlatformLoginSession(TimeStampedModel):
    """记录仍在活动窗口内的平台网页登录会话。"""

    session_id = models.CharField(max_length=64, unique=True, help_text='登录会话的随机唯一标识。')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='platform_login_sessions',
        help_text='当前登录会话关联的平台用户。',
    )
    auth_version = models.PositiveIntegerField(default=0, help_text='签发会话时的用户认证版本。')
    last_seen_at = models.DateTimeField(default=timezone.now, help_text='会话最近一次通过平台鉴权的时间。')
    expires_at = models.DateTimeField(help_text='会话最晚有效时间。')
    revoked_at = models.DateTimeField(null=True, blank=True, help_text='用户退出或认证状态变更时的撤销时间。')

    class Meta:
        ordering = ['-last_seen_at']
        indexes = [
            models.Index(fields=['revoked_at', 'expires_at'], name='ops_login_active_idx'),
            models.Index(fields=['user', 'last_seen_at'], name='ops_login_user_seen_idx'),
        ]

    def __str__(self):
        """返回用户名和会话标识摘要。"""
        return f'{self.user.username}:{self.session_id[:8]}'


class SmsLoginChallenge(TimeStampedModel):
    """保存短期短信登录挑战的国密摘要、绑定条件和一次性消费状态。"""

    token_hash = models.CharField(max_length=64, unique=True, help_text='短信挑战随机令牌的 SM3-HMAC 摘要。')
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='sms_login_challenges',
        help_text='手机号对应的用户；匿名一致性挑战为空。',
    )
    phone_lookup_hash = models.CharField(max_length=64, db_index=True, help_text='接收手机号的 SM3-HMAC 查询索引。')
    code_hash = models.CharField(max_length=64, help_text='六位短信验证码与挑战令牌组合后的 SM3-HMAC 摘要。')
    ip_address = models.GenericIPAddressField(help_text='挑战绑定的真实客户端 IP 地址。')
    client_nonce_hash = models.CharField(max_length=64, help_text='浏览器会话随机值的 SM3-HMAC 摘要。')
    expires_at = models.DateTimeField(help_text='短信验证码严格失效时间。')
    consumed_at = models.DateTimeField(null=True, blank=True, help_text='挑战成功使用或主动失效的时间。')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['phone_lookup_hash', 'expires_at'], name='ops_sms_challenge_phone_idx'),
            models.Index(fields=['user', 'consumed_at'], name='ops_sms_challenge_user_idx'),
        ]

    def __str__(self):
        """返回不含手机号和验证码的短信挑战摘要。"""
        return f'sms:{self.id}:{"used" if self.consumed_at else "active"}'


class SmsDispatchRecord(TimeStampedModel):
    """记录短信网关发送配额占用状态，不保存手机号、验证码或第三方响应。"""

    STATUS_CHOICES = [
        ('pending', '发送中'),
        ('sent', '已发送'),
        ('failed', '发送失败'),
    ]
    PURPOSE_CHOICES = [
        ('login', '短信登录'),
        ('test', '渠道测试'),
    ]

    recipient_hash = models.CharField(max_length=64, db_index=True, help_text='接收手机号的 SM3-HMAC 查询索引。')
    purpose = models.CharField(max_length=16, choices=PURPOSE_CHOICES, help_text='本次短信发送的业务用途。')
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='pending', help_text='网关发送处理状态。')

    class Meta:
        ordering = ['-created_at']
        indexes = [models.Index(fields=['recipient_hash', 'status', 'created_at'], name='ops_sms_dispatch_limit_idx')]

    def __str__(self):
        """返回不含手机号的短信发送状态摘要。"""
        return f'{self.purpose}:{self.status}:{self.id}'


class PermissionMenuNode(TimeStampedModel):
    """数据库中的菜单组或页面节点，同时定义页面访问权限。"""

    NODE_TYPES = [
        ('group', '菜单组'),
        ('page', '页面'),
    ]

    parent = models.ForeignKey(
        'self',
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='children',
        help_text='上级菜单组；菜单组本身为空。',
    )
    node_type = models.CharField(
        max_length=16,
        choices=NODE_TYPES,
        default='page',
        help_text='节点类型：菜单组或页面。',
    )
    code = models.CharField(max_length=160, unique=True, help_text='菜单或页面的唯一权限代码。')
    name = models.CharField(max_length=120, help_text='菜单中展示的中文名称。')
    path = models.CharField(max_length=240, blank=True, help_text='页面对应的前端路由。')
    icon = models.CharField(max_length=80, blank=True, help_text='前端本地图标库中的图标名称。')
    sidebar = models.BooleanField(default=True, help_text='是否在侧边栏展示。')
    aliases = models.JSONField(default=list, blank=True, help_text='共享此页面权限的前端路由别名。')
    sort_order = models.PositiveIntegerField(default=0, help_text='同级菜单的展示顺序。')
    is_active = models.BooleanField(default=True, help_text='菜单或页面权限是否启用。')

    class Meta:
        ordering = ['sort_order', 'id']
        indexes = [
            models.Index(fields=['parent', 'is_active', 'sort_order'], name='ops_perm_menu_parent_idx'),
            models.Index(fields=['node_type', 'is_active'], name='ops_perm_menu_type_idx'),
        ]

    def __str__(self):
        """返回菜单名称和权限代码。"""
        return f'{self.name}({self.code})'


class PermissionMenuAction(TimeStampedModel):
    """页面上真实存在的可授权操作，例如新增、编辑或删除。"""

    page = models.ForeignKey(
        PermissionMenuNode,
        on_delete=models.CASCADE,
        related_name='actions',
        help_text='操作所属的页面权限节点。',
    )
    code = models.CharField(max_length=80, help_text='页面内唯一的操作代码。')
    name = models.CharField(max_length=80, help_text='权限策略中展示的操作名称。')
    sort_order = models.PositiveIntegerField(default=0, help_text='操作在权限策略中的展示顺序。')
    is_active = models.BooleanField(default=True, help_text='操作权限是否启用。')

    class Meta:
        ordering = ['sort_order', 'id']
        unique_together = [('page', 'code')]
        indexes = [models.Index(fields=['page', 'is_active', 'sort_order'], name='ops_perm_action_page_idx')]

    def __str__(self):
        """返回完整的页面操作权限代码。"""
        return f'{self.page.code}.{self.code}'


class UserMenuOrderPreference(TimeStampedModel):
    """保存单个用户的菜单层级排序偏好，不改变平台默认菜单顺序。"""

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='menu_order_preference',
        help_text='使用这套个人菜单顺序的平台用户。',
    )
    order_data = models.JSONField(
        default=dict,
        blank=True,
        help_text='按父级菜单权限代码保存的完整同级菜单代码顺序。',
    )

    def __str__(self):
        """返回个人菜单排序偏好的用户标识。"""
        return f'{self.user.username} 的菜单顺序'


class PermissionPolicy(TimeStampedModel):
    """分配给部门或用户的功能权限策略。"""

    SUBJECT_CHOICES = [
        ('department', '部门'),
        ('user', '用户'),
    ]
    STATUS_CHOICES = [
        ('available', '可用'),
        ('disabled', '已禁用'),
    ]

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='permission_policies',
        help_text='策略所属的数据隔离组织。',
    )
    name = models.CharField(max_length=120, help_text='权限策略名称。')
    subject_type = models.CharField(max_length=32, choices=SUBJECT_CHOICES, help_text='授权对象类型：部门或用户。')
    department = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='department_permission_policies',
        help_text='授权对象为部门时关联的部门。',
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='permission_policies',
        help_text='授权对象为用户时关联的用户。',
    )
    priority = models.PositiveIntegerField(default=50, help_text='策略计算顺序，数值越小越先处理。')
    status = models.CharField(
        max_length=32,
        choices=STATUS_CHOICES,
        default='available',
        help_text='策略是否参与权限计算。',
    )
    remark = models.TextField(blank=True, help_text='策略用途和变更原因备注。')

    class Meta:
        ordering = ['priority', '-updated_at']
        indexes = [
            models.Index(fields=['subject_type', 'status', 'priority'], name='ops_perm_policy_subject_idx'),
            models.Index(fields=['department', 'status'], name='ops_perm_policy_dept_idx'),
            models.Index(fields=['user', 'status'], name='ops_perm_policy_user_idx'),
        ]

    def __str__(self):
        """返回权限策略名称。"""
        return self.name


class PermissionRule(TimeStampedModel):
    """权限策略中的单个允许或拒绝规则，默认拒绝。"""

    EFFECT_CHOICES = [
        ('allow', '允许'),
        ('deny', '拒绝'),
    ]

    policy = models.ForeignKey(
        PermissionPolicy,
        on_delete=models.CASCADE,
        related_name='rules',
        help_text='规则所属的权限策略。',
    )
    permission_code = models.CharField(max_length=160, help_text='数据库菜单目录中的完整权限代码。')
    effect = models.CharField(
        max_length=16,
        choices=EFFECT_CHOICES,
        default='deny',
        help_text='授权效果；未明确允许时保持拒绝。',
    )

    class Meta:
        ordering = ['permission_code']
        unique_together = [('policy', 'permission_code')]
        indexes = [models.Index(fields=['permission_code', 'effect'], name='ops_perm_rule_code_idx')]

    def __str__(self):
        """返回策略、权限代码和授权效果。"""
        return f'{self.policy_id}:{self.permission_code}:{self.effect}'


class SystemSetting(TimeStampedModel):
    """平台设置项，敏感值由加密字段使用 SM4 加密保存。"""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name='settings',
        help_text='设置所属组织；为空表示平台级设置。',
    )
    key = models.CharField(max_length=120, unique=True, help_text='设置项唯一键。')
    value = EncryptedJSONField(default=dict, blank=True, help_text='设置值；其中敏感字段使用 SM4 加密保存。')
    description = models.TextField(blank=True, help_text='设置项用途说明。')

    def __str__(self):
        """返回设置项唯一键。"""
        return self.key


apply_model_field_help(globals())

# 保留历史导入路径，业务实现和模型注册均由独立日志应用负责。
from platform_logs.models import AuditLog  # noqa: E402,F401
