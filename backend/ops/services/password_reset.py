import hashlib
import secrets

from django.contrib.auth.models import User
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from ops.models import UserProfile
from ops.services.otp import ensure_user_profile, matching_timestep
from ops.services.platform_security import login_lock_policy, validate_password


PASSWORD_RESET_SECONDS = 300
DUMMY_TOTP_SECRET = 'JBSWY3DPEHPK3PXPJBSWY3DPEHPK3PXP'


def _reset_transaction_key(token):
    """把找回密码事务令牌转换为不可逆缓存键。

    参数：`token` 为浏览器持有的随机事务令牌。
    返回：仅包含 SHA-256 摘要的缓存键。
    副作用：不读写数据库、缓存或文件。
    """
    digest = hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()
    return f'password-reset:{digest}'


def issue_reset_transaction(user, ip_address, client_nonce, step='otp'):
    """签发绑定用户、来源地址和浏览器会话的短期找回事务。

    参数：`user` 为可选的真实用户；`ip_address` 为请求来源；
    `client_nonce` 为页面会话随机值；`step` 为 otp 或 password。
    返回：仅返回给当前浏览器的一次性随机令牌。
    副作用：向缓存写入一条五分钟有效的找回事务。
    """
    token = secrets.token_urlsafe(32)
    cache.set(_reset_transaction_key(token), {
        'user_id': user.id if user else None,
        'ip_address': str(ip_address or ''),
        'client_nonce': str(client_nonce or ''),
        'step': step,
        'otp_failures': 0,
    }, timeout=PASSWORD_RESET_SECONDS)
    return token


def load_reset_transaction(token, ip_address, client_nonce, expected_step):
    """读取并校验找回事务的来源、浏览器会话和当前步骤。

    参数：`token` 为事务令牌；`ip_address` 与 `client_nonce` 为当前请求条件；
    `expected_step` 为调用方允许的事务步骤。
    返回：全部绑定条件一致时返回事务字典，否则返回 None。
    副作用：只读取缓存，不延长事务有效期。
    """
    payload = cache.get(_reset_transaction_key(token))
    if not isinstance(payload, dict):
        return None
    if payload.get('ip_address') != str(ip_address or ''):
        return None
    if not client_nonce or payload.get('client_nonce') != str(client_nonce):
        return None
    if payload.get('step') != expected_step:
        return None
    return payload


def save_reset_transaction(token, payload):
    """保存尚未完成的找回事务状态。

    参数：`token` 为事务令牌；`payload` 为更新后的事务字典。
    返回：无显式返回值。
    副作用：覆盖写入对应缓存并把剩余有效期设为五分钟。
    """
    cache.set(_reset_transaction_key(token), payload, timeout=PASSWORD_RESET_SECONDS)


def consume_reset_transaction(token):
    """销毁已经完成、锁定或主动失效的找回事务。

    参数：`token` 为待销毁的一次性事务令牌。
    返回：缓存后端的删除结果。
    副作用：删除对应缓存记录。
    """
    return cache.delete(_reset_transaction_key(token))


def eligible_reset_user(username):
    """查找允许通过已绑定 TOTP 自助找回密码的用户。

    参数：`username` 为用户输入的登录账号。
    返回：启用用户或因密码过期自动禁用的用户；其他情况返回 None。
    副作用：只读取用户和档案，不泄露查询结果给调用端。
    """
    user = User.objects.select_related('profile', 'profile__organization').filter(
        username=str(username or '').strip(),
    ).first()
    profile = getattr(user, 'profile', None) if user else None
    if not user or not profile or not profile.otp_secret or not profile.otp_bound_at:
        return None
    if user.is_active or profile.password_expired_locked:
        return user
    return None


def reset_transaction_user(payload):
    """从已校验的找回事务重新读取当前仍可自助改密的用户。

    参数：`payload` 为通过来源和步骤校验的缓存事务。
    返回：仍满足启用状态与 OTP 绑定条件的用户，否则返回 None。
    副作用：只读取数据库，防止管理员在事务期间禁用用户后仍可改密。
    """
    user = User.objects.select_related('profile', 'profile__organization').filter(
        pk=payload.get('user_id'),
    ).first()
    if not user:
        return None
    return eligible_reset_user(user.username)


def register_anonymous_otp_failure(token, payload):
    """为不存在或不符合条件的账号模拟一致的 OTP 失败与锁定节奏。

    参数：`token` 为找回事务令牌；`payload` 为当前匿名事务。
    返回：达到平台 OTP 失败上限时返回 True。
    副作用：更新缓存失败次数，达到上限时销毁事务。
    """
    policy = login_lock_policy()
    failures = int(payload.get('otp_failures') or 0) + 1
    payload['otp_failures'] = failures
    if failures >= policy['otp_failure_limit']:
        consume_reset_transaction(token)
        return True
    save_reset_transaction(token, payload)
    return False


def simulate_anonymous_totp_check(credential):
    """为匿名占位事务执行一次与真实 TOTP 接近的恒定计算。

    参数：`credential` 为找回页面提交的候选六位口令。
    返回：始终返回 None，固定种子的匹配结果不会被用于认证。
    副作用：只执行内存中的 HMAC 计算，不读取或修改用户数据。
    """
    matching_timestep(DUMMY_TOTP_SECRET, credential)
    return None


@transaction.atomic
def set_recovered_password(user, new_password):
    """按平台策略保存新密码并撤销该用户全部旧会话。

    参数：`user` 为已完成 TOTP 验证的用户；`new_password` 为待保存明文。
    返回：更新后的用户对象以及是否恢复了密码过期账号。
    副作用：加密保存密码、更新时间与认证版本，并仅恢复密码过期自动禁用状态。
    """
    locked_user = User.objects.select_for_update().get(pk=user.pk)
    ensure_user_profile(locked_user)
    profile = UserProfile.objects.select_for_update().get(user=locked_user)
    if not locked_user.is_active and not profile.password_expired_locked:
        raise PermissionError('当前账号不允许自助找回密码')

    password = validate_password(new_password, locked_user.username)
    restored_from_expiry = bool(profile.password_expired_locked)
    locked_user.set_password(password)
    if restored_from_expiry:
        locked_user.is_active = True
    locked_user.save(update_fields=['password', 'is_active'])

    profile.password_changed_at = timezone.now()
    profile.password_expired_locked = False
    profile.auth_version = int(profile.auth_version or 0) + 1
    profile.save(update_fields=[
        'password_changed_at', 'password_expired_locked', 'auth_version', 'updated_at',
    ])
    from ops.services.login_sessions import revoke_user_login_sessions
    revoke_user_login_sessions(locked_user)
    return locked_user, restored_from_expiry
