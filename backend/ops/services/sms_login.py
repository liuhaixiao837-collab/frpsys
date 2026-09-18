"""短信登录挑战签发、国密摘要校验和错误锁定服务。"""

import hmac
import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.db import transaction
from django.utils import timezone

from ops.models import SmsLoginChallenge, UserProfile

from .notifications import send_login_sms
from .phone_identity import normalize_mobile_phone, phone_lookup_hash, sm3_hmac_hex
from .platform_security import login_lock_policy


SMS_CODE_DIGITS = 6
SMS_CODE_TTL_SECONDS = 30


def _challenge_token_hash(token):
    """计算短信挑战随机令牌的 SM3-HMAC 摘要。

    参数：`token` 为仅返回浏览器的高强度随机令牌。
    返回：可安全查询数据库的十六进制摘要。
    副作用：不读写数据库。
    """
    return sm3_hmac_hex('sms-challenge-token', token)


def _sms_code_hash(token, code):
    """计算绑定挑战令牌的短信验证码 SM3-HMAC 摘要。

    参数：`token` 为挑战令牌；`code` 为六位短信验证码。
    返回：不可逆摘要。
    副作用：不读写数据库或日志。
    """
    return sm3_hmac_hex('sms-code', f'{token}:{code}')


def _client_nonce_hash(client_nonce):
    """计算浏览器会话随机值的 SM3-HMAC 摘要。

    参数：`client_nonce` 为登录页生命周期内的浏览器随机值。
    返回：不可逆摘要。
    副作用：不读写数据库。
    """
    return sm3_hmac_hex('sms-client-nonce', client_nonce)


def _sms_login_user(phone_hash):
    """按唯一手机号国密索引读取可使用短信登录的用户。

    参数：`phone_hash` 为手机号的 SM3-HMAC 查询索引。
    返回：启用且已绑定 OTP 的用户，不满足条件时返回空值。
    副作用：只读取用户与档案数据。
    """
    user = User.objects.select_related('profile', 'profile__organization').filter(
        profile__phone_lookup_hash=phone_hash,
        is_active=True,
    ).first()
    profile = getattr(user, 'profile', None) if user else None
    if not profile or not profile.otp_secret or not profile.otp_bound_at:
        return None
    if profile.sms_locked_until and profile.sms_locked_until > timezone.now():
        return None
    return user


@transaction.atomic
def _store_challenge(token, phone_hash, code, ip_address, client_nonce, user):
    """使同手机号旧挑战失效并保存新的三十秒一次性挑战。

    参数：包含挑战令牌、手机号索引、验证码、来源、浏览器随机值和可选用户。
    返回：新建的短信挑战记录。
    副作用：更新旧挑战消费时间并新增数据库记录。
    """
    now = timezone.now()
    SmsLoginChallenge.objects.filter(
        phone_lookup_hash=phone_hash,
        consumed_at__isnull=True,
    ).update(consumed_at=now, updated_at=now)
    return SmsLoginChallenge.objects.create(
        token_hash=_challenge_token_hash(token),
        user=user,
        phone_lookup_hash=phone_hash,
        code_hash=_sms_code_hash(token, code),
        ip_address=str(ip_address or ''),
        client_nonce_hash=_client_nonce_hash(client_nonce),
        expires_at=now + timedelta(seconds=SMS_CODE_TTL_SECONDS),
    )


def issue_sms_login_challenge(phone, ip_address, client_nonce):
    """发送验证码并签发绑定手机号、来源与浏览器的一次性挑战。

    参数：`phone` 为手机号；`ip_address` 为真实来源；`client_nonce` 为浏览器随机值。
    返回：随机挑战令牌和固定三十秒有效期。
    副作用：有效用户会调用短信网关；所有请求都会保存匿名一致结构的短期挑战。
    """
    normalized_phone = normalize_mobile_phone(phone)
    phone_hash = phone_lookup_hash(normalized_phone)
    user = _sms_login_user(phone_hash)
    code = str(secrets.randbelow(10 ** SMS_CODE_DIGITS)).zfill(SMS_CODE_DIGITS)
    if user:
        send_login_sms(normalized_phone, code)
    token = secrets.token_urlsafe(32)
    _store_challenge(token, phone_hash, code, ip_address, client_nonce, user)
    return {
        'challenge_token': token,
        'expires_in': SMS_CODE_TTL_SECONDS,
        'detail': '若该手机号已绑定可用账号，短信验证码已发送',
    }


def _register_sms_failure(profile, challenge, now):
    """累计短信验证码错误并按平台策略锁定用户。

    参数：`profile` 为行锁定用户档案；`challenge` 为当前挑战；`now` 为服务端时间。
    返回：达到阈值并锁定时返回真。
    副作用：更新用户短信失败状态，锁定时同时消费当前挑战。
    """
    policy = login_lock_policy()
    profile.sms_failed_attempts = int(profile.sms_failed_attempts or 0) + 1
    locked = profile.sms_failed_attempts >= policy['sms_failure_limit']
    if locked:
        profile.sms_failed_attempts = 0
        profile.sms_locked_until = now + timedelta(minutes=policy['sms_lock_minutes'])
        challenge.consumed_at = now
        challenge.save(update_fields=['consumed_at', 'updated_at'])
    profile.save(update_fields=['sms_failed_attempts', 'sms_locked_until', 'updated_at'])
    return locked


@transaction.atomic
def verify_sms_login_challenge(token, code, ip_address, client_nonce):
    """校验并消费短信验证码，成功时返回已绑定 OTP 的启用用户。

    参数：`token` 为挑战令牌；`code` 为六位验证码；其余参数为当前绑定条件。
    返回：包含成功、用户、错误说明和锁定状态的字典。
    副作用：行锁挑战与用户档案，更新一次性消费、错误次数或锁定时间。
    """
    challenge = SmsLoginChallenge.objects.select_for_update().select_related(
        'user',
        'user__profile',
        'user__profile__organization',
    ).filter(token_hash=_challenge_token_hash(token)).first()
    now = timezone.now()
    if (
        not challenge
        or challenge.consumed_at
        or challenge.expires_at <= now
        or challenge.ip_address != str(ip_address or '')
        or challenge.client_nonce_hash != _client_nonce_hash(client_nonce)
    ):
        return {'success': False, 'user': None, 'detail': '短信验证码错误或已过期', 'locked': False}
    user = challenge.user
    if not user or not user.is_active:
        challenge.consumed_at = now
        challenge.save(update_fields=['consumed_at', 'updated_at'])
        return {'success': False, 'user': None, 'detail': '短信验证码错误或已过期', 'locked': False}
    profile = UserProfile.objects.select_for_update().get(user=user)
    if profile.sms_locked_until and profile.sms_locked_until > now:
        return {'success': False, 'user': user, 'detail': '短信验证码验证已锁定，请稍后重试', 'locked': True}
    if profile.sms_locked_until:
        profile.sms_locked_until = None
        profile.sms_failed_attempts = 0
        profile.save(update_fields=['sms_locked_until', 'sms_failed_attempts', 'updated_at'])
    normalized_code = str(code or '').strip()
    matched = len(normalized_code) == SMS_CODE_DIGITS and normalized_code.isdigit() and hmac.compare_digest(
        challenge.code_hash,
        _sms_code_hash(token, normalized_code),
    )
    if not matched:
        locked = _register_sms_failure(profile, challenge, now)
        policy = login_lock_policy()
        detail = (
            f'短信验证码错误次数过多，已锁定 {policy["sms_lock_minutes"]} 分钟'
            if locked else '短信验证码错误或已过期'
        )
        return {'success': False, 'user': user, 'detail': detail, 'locked': locked}
    if not profile.otp_secret or not profile.otp_bound_at:
        challenge.consumed_at = now
        challenge.save(update_fields=['consumed_at', 'updated_at'])
        return {'success': False, 'user': user, 'detail': '该账号尚未绑定 OTP，请使用密码登录完成绑定', 'locked': False}
    challenge.consumed_at = now
    challenge.save(update_fields=['consumed_at', 'updated_at'])
    profile.sms_failed_attempts = 0
    profile.sms_locked_until = None
    profile.save(update_fields=['sms_failed_attempts', 'sms_locked_until', 'updated_at'])
    return {'success': True, 'user': user, 'detail': '', 'locked': False}


def invalidate_user_sms_challenges(user):
    """使指定用户尚未使用的短信登录挑战立即失效。

    参数：`user` 为手机号变更、停用或其他认证状态变化的用户。
    返回：被更新的挑战数量。
    副作用：批量写入当前服务端时间作为消费时间。
    """
    now = timezone.now()
    return SmsLoginChallenge.objects.filter(user=user, consumed_at__isnull=True).update(
        consumed_at=now,
        updated_at=now,
    )
