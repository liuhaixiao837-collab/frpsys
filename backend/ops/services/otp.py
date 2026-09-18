import base64
import hashlib
import hmac
import secrets
import struct
import time
from datetime import timedelta
from urllib.parse import quote, urlencode

from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from ops.models import Organization, SystemSetting, UserProfile


OTP_DIGITS = 6
OTP_PERIOD = 30
OTP_WINDOW = 1
OTP_SECRET_BYTES = 20
OTP_TRANSACTION_SECONDS = 300
OTP_SETUP_SECONDS = 600


def generate_totp_secret():
    """生成兼容通用令牌应用的 Base32 TOTP 种子。

    参数：无。
    返回：不含填充符的 Base32 安全随机种子。
    副作用：使用操作系统密码学安全随机源，不写入持久化数据。
    """
    return base64.b32encode(secrets.token_bytes(OTP_SECRET_BYTES)).decode('ascii').rstrip('=')


def totp_code(secret, timestep):
    """按 RFC 6238 计算指定时间步的六位动态口令。

    参数：`secret` 为 Base32 种子；`timestep` 为 30 秒时间步编号。
    返回：六位数字字符串。
    副作用：不读写数据库、文件或网络。
    """
    normalized = str(secret or '').strip().upper()
    padding = '=' * ((8 - len(normalized) % 8) % 8)
    key = base64.b32decode(f'{normalized}{padding}', casefold=True)
    digest = hmac.new(key, struct.pack('>Q', int(timestep)), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack('>I', digest[offset:offset + 4])[0] & 0x7FFFFFFF
    return str(value % (10 ** OTP_DIGITS)).zfill(OTP_DIGITS)


def matching_timestep(secret, code, timestamp=None):
    """在当前时间步前后各一个窗口内匹配动态口令。

    参数：`secret` 为 Base32 种子；`code` 为用户输入；`timestamp` 为可选 Unix 时间。
    返回：匹配的时间步编号；不匹配时返回 None。
    副作用：不读写持久化数据。
    """
    normalized = str(code or '').strip()
    if len(normalized) != OTP_DIGITS or not normalized.isdigit():
        return None
    current = int((time.time() if timestamp is None else timestamp) // OTP_PERIOD)
    for offset in (0, -1, 1):
        candidate = current + offset
        if hmac.compare_digest(totp_code(secret, candidate), normalized):
            return candidate
    return None


def effective_otp_enabled(user, platform_enabled=None):
    """按用户独立策略优先于平台默认的规则计算 OTP 是否必需。

    参数：`user` 为 Django 用户；`platform_enabled` 为可选的已读取平台默认状态。
    返回：当前用户是否必须绑定并验证 OTP。
    副作用：读取用户档案和平台登录设置，不修改数据。
    """
    profile = getattr(user, 'profile', None)
    policy = getattr(profile, 'otp_policy', 'inherit') if profile else 'inherit'
    if policy == 'required':
        return True
    if policy == 'exempt':
        return False
    if platform_enabled is None:
        from ops.services.platform_security import login_security_settings
        platform_enabled = login_security_settings().get('otp_enabled')
    return bool(platform_enabled)


def ensure_user_profile(user):
    """确保登录用户具有可保存 OTP 状态的扩展档案。

    参数：`user` 为已通过密码认证的 Django 用户。
    返回：用户现有或新建的 UserProfile。
    副作用：缺少组织或用户档案时会创建最小必需数据库记录。
    """
    profile = getattr(user, 'profile', None)
    if profile:
        return profile
    organization = Organization.objects.filter(is_default=True).order_by('id').first()
    organization = organization or Organization.objects.order_by('id').first()
    if not organization:
        organization = Organization.objects.create(
            name='默认组织',
            slug='default-org',
            description='系统自动创建的公司根组织。',
            region='中国',
            org_type='company',
            is_default=True,
            is_active=True,
        )
    profile, _created = UserProfile.objects.get_or_create(
        user=user,
        defaults={'organization': organization, 'role': 'member'},
    )
    return profile


def otp_status_payload(user, platform_enabled=None):
    """生成不含种子或口令的 OTP 状态摘要。

    参数：`user` 为待展示的 Django 用户；`platform_enabled` 为可复用的平台默认状态。
    返回：策略、有效启用状态、绑定状态和中文状态。
    副作用：只读取用户档案和平台设置。
    """
    profile = getattr(user, 'profile', None)
    policy = getattr(profile, 'otp_policy', 'inherit') if profile else 'inherit'
    bound = bool(profile and profile.otp_secret and profile.otp_bound_at)
    effective = effective_otp_enabled(user, platform_enabled=platform_enabled)
    locked = bool(profile and profile.otp_locked_until and profile.otp_locked_until > timezone.now())
    if locked:
        state, label = 'locked', '已锁定'
    elif effective and not bound:
        state, label = 'pending', '待绑定'
    elif bound and not effective:
        state, label = 'exempt', '已绑定（免验证）'
    elif bound:
        state, label = 'bound', '已绑定'
    else:
        state, label = 'disabled', '未启用'
    return {
        'otp_policy': policy,
        'otp_effective_enabled': effective,
        'otp_bound': bound,
        'otp_status': state,
        'otp_status_label': label,
    }


def _transaction_key(token):
    """将敏感预认证令牌转换为不可逆的缓存键。

    参数：`token` 为随机预认证令牌。
    返回：仅包含 SHA-256 摘要的缓存键。
    副作用：不读写持久化数据。
    """
    digest = hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()
    return f'otp-preauth:{digest}'


def issue_login_transaction(user, ip_address, client_nonce, step, auth_method='password'):
    """签发绑定来源、浏览器会话和用户的一次性 OTP 预认证事务。

    参数：`user` 为已通过第一阶段的用户；`ip_address` 为来源地址；
    `client_nonce` 为登录页会话随机值；`step` 为 bind 或 verify；
    `auth_method` 为已经通过的密码或短信第一阶段方式。
    返回：随机预认证令牌。
    副作用：向缓存写入一条五分钟有效的认证事务。
    """
    token = secrets.token_urlsafe(32)
    cache.set(_transaction_key(token), {
        'user_id': user.id,
        'ip_address': str(ip_address or ''),
        'client_nonce': str(client_nonce or ''),
        'step': step,
        'setup_secret': '',
        'setup_failures': 0,
        'auth_method': 'sms' if auth_method == 'sms' else 'password',
    }, timeout=OTP_TRANSACTION_SECONDS)
    return token


def load_login_transaction(token, ip_address, client_nonce, expected_step):
    """读取并校验 OTP 预认证事务的绑定条件。

    参数：`token` 为预认证令牌；`ip_address` 和 `client_nonce` 为当前请求条件；
    `expected_step` 为期望的 bind 或 verify 步骤。
    返回：校验成功的事务字典；失败时返回 None。
    副作用：只读取缓存。
    """
    payload = cache.get(_transaction_key(token))
    if not isinstance(payload, dict):
        return None
    if payload.get('ip_address') != str(ip_address or ''):
        return None
    if not client_nonce or payload.get('client_nonce') != str(client_nonce):
        return None
    if payload.get('step') != expected_step:
        return None
    return payload


def save_login_transaction(token, payload, timeout=OTP_TRANSACTION_SECONDS):
    """更新未完成 OTP 事务的临时状态。

    参数：`token` 为预认证令牌；`payload` 为事务数据；`timeout` 为剩余有效秒数。
    返回：无显式返回值。
    副作用：覆盖写入对应的缓存事务。
    """
    cache.set(_transaction_key(token), payload, timeout=timeout)


def consume_login_transaction(token):
    """销毁已完成或已失效的 OTP 预认证事务。

    参数：`token` 为要消费的预认证令牌。
    返回：缓存删除结果。
    副作用：删除一条缓存认证事务。
    """
    return cache.delete(_transaction_key(token))


def setup_payload(token, transaction_payload, username):
    """为未绑定用户生成或复用临时种子和标准 otpauth 内容。

    参数：`token` 为预认证令牌；`transaction_payload` 为事务数据；`username` 为账号名。
    返回：不含其他凭据的 otpauth URI 和有效期。
    副作用：首次调用时向缓存写入临时种子。
    """
    secret = transaction_payload.get('setup_secret') or generate_totp_secret()
    transaction_payload['setup_secret'] = secret
    save_login_transaction(token, transaction_payload, timeout=OTP_SETUP_SECONDS)
    setting = SystemSetting.objects.filter(key='platform').order_by('organization_id', 'id').first()
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    issuer = str(value.get('name') or 'Ongrid').strip()[:80]
    label = quote(f'{issuer}:{username}', safe='')
    query = urlencode({
        'secret': secret,
        'issuer': issuer,
        'algorithm': 'SHA1',
        'digits': OTP_DIGITS,
        'period': OTP_PERIOD,
    })
    return {'otpauth_uri': f'otpauth://totp/{label}?{query}', 'expires_in': OTP_SETUP_SECONDS}


@transaction.atomic
def register_setup_failure(token, transaction_payload, user=None):
    """累计绑定确认阶段的口令失败并在达到限制时销毁事务。

    参数：`token` 为预认证令牌；`transaction_payload` 为当前事务。
    返回：是否已达到平台配置的失败上限。
    副作用：更新或删除缓存事务；达到上限时持久化用户 OTP 锁定时间。
    """
    from ops.services.platform_security import login_lock_policy

    policy = login_lock_policy()
    failures = int(transaction_payload.get('setup_failures') or 0) + 1
    transaction_payload['setup_failures'] = failures
    if failures >= policy['otp_failure_limit']:
        consume_login_transaction(token)
        if user:
            ensure_user_profile(user)
            profile = UserProfile.objects.select_for_update().get(user=user)
            profile.otp_failed_attempts = 0
            profile.otp_locked_until = timezone.now() + timedelta(minutes=policy['otp_lock_minutes'])
            profile.save(update_fields=['otp_failed_attempts', 'otp_locked_until', 'updated_at'])
        return True
    save_login_transaction(token, transaction_payload, timeout=OTP_SETUP_SECONDS)
    return False


@transaction.atomic
def bind_user_otp(user, secret, timestep):
    """事务绑定用户 TOTP 种子并记录首次验证时间步。

    参数：`user` 为已通过预认证的用户；`secret` 为临时种子；`timestep` 为确认口令的时间步。
    返回：更新后的用户档案。
    副作用：使用 SM4 加密种子并更新绑定状态。
    """
    ensure_user_profile(user)
    profile = UserProfile.objects.select_for_update().get(user=user)
    profile.otp_secret = secret
    profile.otp_bound_at = timezone.now()
    profile.otp_last_timestep = int(timestep)
    profile.otp_failed_attempts = 0
    profile.otp_locked_until = None
    profile.save(update_fields=[
        'otp_secret', 'otp_bound_at', 'otp_last_timestep', 'otp_failed_attempts',
        'otp_locked_until', 'updated_at',
    ])
    return profile


def _otp_failure(profile, now, policy):
    """在行锁内累计 OTP 失败并根据阈值设置锁定时间。

    参数：`profile` 为已锁定的用户档案；`now` 为当前时间。
    返回：是否因达到失败阈值而进入锁定。
    副作用：更新档案的失败次数和锁定截止时间。
    """
    profile.otp_failed_attempts = int(profile.otp_failed_attempts or 0) + 1
    locked = profile.otp_failed_attempts >= policy['otp_failure_limit']
    if locked:
        profile.otp_locked_until = now + timedelta(minutes=policy['otp_lock_minutes'])
        profile.otp_failed_attempts = 0
    profile.save(update_fields=['otp_failed_attempts', 'otp_locked_until', 'updated_at'])
    return locked


@transaction.atomic
def verify_user_otp(user, credential):
    """事务校验六位 TOTP 并防止并发重放。

    参数：`user` 为预认证用户；`credential` 为六位动态口令。
    返回：包含成功状态、验证方式、错误说明和锁定状态的字典。
    副作用：行锁定更新时间步、失败次数或锁定时间。
    """
    ensure_user_profile(user)
    from ops.services.platform_security import login_lock_policy

    policy = login_lock_policy()
    profile = UserProfile.objects.select_for_update().get(user=user)
    now = timezone.now()
    if profile.otp_locked_until and profile.otp_locked_until > now:
        return {'success': False, 'method': '', 'detail': 'OTP 验证已锁定，请稍后重试', 'locked': True}
    if profile.otp_locked_until:
        profile.otp_locked_until = None
        profile.otp_failed_attempts = 0
        profile.save(update_fields=['otp_locked_until', 'otp_failed_attempts', 'updated_at'])
    if not profile.otp_secret or not profile.otp_bound_at:
        return {'success': False, 'method': '', 'detail': 'OTP 尚未绑定', 'locked': False}

    value = str(credential or '').strip()
    timestep = matching_timestep(profile.otp_secret, value)
    if timestep is not None:
        if profile.otp_last_timestep is not None and timestep <= profile.otp_last_timestep:
            locked = _otp_failure(profile, now, policy)
            detail = (
                f'OTP 输入错误次数过多，已锁定 {policy["otp_lock_minutes"]} 分钟'
                if locked else '动态口令错误或已过期'
            )
            return {'success': False, 'method': '', 'detail': detail, 'locked': locked}
        profile.otp_last_timestep = timestep
        profile.otp_failed_attempts = 0
        profile.otp_locked_until = None
        profile.save(update_fields=['otp_last_timestep', 'otp_failed_attempts', 'otp_locked_until', 'updated_at'])
        return {'success': True, 'method': 'otp', 'detail': '', 'locked': False}

    locked = _otp_failure(profile, now, policy)
    detail = (
        f'OTP 输入错误次数过多，已锁定 {policy["otp_lock_minutes"]} 分钟'
        if locked else '动态口令错误或已过期'
    )
    return {'success': False, 'method': '', 'detail': detail, 'locked': locked}


@transaction.atomic
def reset_user_otp(user):
    """销毁用户现有 OTP 绑定并使已签发的会话令牌失效。

    参数：`user` 为管理员选择的目标用户。
    返回：重置后的用户档案。
    副作用：清空种子、重放和锁定状态，并递增认证版本。
    """
    ensure_user_profile(user)
    profile = UserProfile.objects.select_for_update().get(user=user)
    profile.otp_secret = ''
    profile.otp_bound_at = None
    profile.otp_last_timestep = None
    profile.otp_failed_attempts = 0
    profile.otp_locked_until = None
    profile.auth_version = int(profile.auth_version or 0) + 1
    profile.save(update_fields=[
        'otp_secret', 'otp_bound_at', 'otp_last_timestep', 'otp_failed_attempts',
        'otp_locked_until', 'auth_version', 'updated_at',
    ])
    from ops.services.login_sessions import revoke_user_login_sessions
    revoke_user_login_sessions(user)
    return profile
