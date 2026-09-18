import ipaddress
import secrets
import string
from datetime import timedelta

from django.utils import timezone

from ops.services.system_admin import SYSTEM_ADMIN_USERNAME


DEFAULT_LOGIN_WHITELIST = {
    'enabled': False,
    'entries': [],
    'descriptions': {},
}
DEFAULT_LOGIN_BLACKLIST = {
    'enabled': False,
    'entries': [],
    'descriptions': {},
}
DEFAULT_PASSWORD_POLICY = {
    'min_length': 8,
    'require_uppercase': True,
    'require_lowercase': True,
    'require_number': True,
    'require_special': True,
    'exclude_username': True,
    'max_age_days': 30,
}
DEFAULT_LOGIN_SETTINGS = {
    'captcha_enabled': True,
    'slider_captcha_enabled': True,
    'otp_enabled': False,
    'sms_login_enabled': False,
    'login_failure_limit': 5,
    'login_lock_minutes': 30,
    'ip_failure_limit': 20,
    'ip_lock_minutes': 30,
    'otp_failure_limit': 5,
    'otp_lock_minutes': 20,
    'sms_failure_limit': 5,
    'sms_lock_minutes': 20,
}
DEFAULT_TIMEZONE_SETTINGS = {
    'timezone': 'Asia/Shanghai',
}
DEFAULT_WATERMARK_SETTINGS = {
    'enabled': False,
    'content_type': 'username_ip',
    'custom_text': '',
    'layout': 'tiled',
    'show_time': True,
    'font_size': 14,
    'font_weight': 500,
    'color': '#64748b',
    'opacity': 0.14,
    'rotate': -24,
    'horizontal_gap': 220,
    'vertical_gap': 140,
}


def setting_value(key, defaults):
    """读取平台级设置并与默认值合并。

    参数：`key` 为设置唯一键；`defaults` 为数据库未配置时使用的默认字典。
    返回：包含完整默认字段的设置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    from ops.models import SystemSetting

    setting = SystemSetting.objects.filter(key=key).order_by('organization_id', 'id').first()
    value = setting.value if setting and isinstance(setting.value, dict) else {}
    return {**defaults, **value}


def login_whitelist_settings():
    """返回登录来源白名单配置。

    参数：无。
    返回：包含启用状态和 IP/CIDR 条目的配置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('security.login_whitelist', DEFAULT_LOGIN_WHITELIST)


def login_blacklist_settings():
    """返回登录来源黑名单配置。

    参数：无。
    返回：包含启用状态和 IP/CIDR 条目的配置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('security.login_blacklist', DEFAULT_LOGIN_BLACKLIST)


def password_policy_settings():
    """返回当前用户密码复杂度策略。

    参数：无。
    返回：包含长度及字符类别要求的配置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('security.password_policy', DEFAULT_PASSWORD_POLICY)


def password_max_age_days():
    """读取密码最大使用天数并限制在安全范围内。
    参数：无。
    返回：密码有效天数；小于等于 0 表示不启用过期锁定。
    副作用：只读取数据库配置，不修改持久化数据。
    """
    policy = password_policy_settings()
    try:
        value = int(policy.get('max_age_days') or 0)
    except (TypeError, ValueError):
        value = DEFAULT_PASSWORD_POLICY['max_age_days']
    return max(0, min(3650, value))


def password_expiry_exempt(user):
    """判断用户是否豁免平台密码修改周期策略。
    参数：`user` 为待判断的 Django 用户或匿名用户。
    返回：系统唯一超级管理员 admin 始终返回真；其余用户返回假。
    副作用：不读取或修改数据库；只按保留用户名判断，账号被误锁定时仍可豁免。
    """
    return str(getattr(user, 'username', '') or '') == SYSTEM_ADMIN_USERNAME


def password_is_expired(user, now=None):
    """判断用户密码是否已经超过平台密码策略有效期。
    参数：`user` 为待检查的 Django 用户；`now` 为可选的当前时间。
    返回：超过有效期返回 True，否则返回 False；admin 豁免修改周期策略时始终返回 False。
    副作用：只读取用户档案和平台配置，不修改数据库。
    """
    if password_expiry_exempt(user):
        return False
    max_age_days = password_max_age_days()
    if max_age_days <= 0:
        return False
    profile = getattr(user, 'profile', None)
    changed_at = getattr(profile, 'password_changed_at', None) if profile else None
    if not changed_at:
        return False
    current_time = now or timezone.now()
    return changed_at + timedelta(days=max_age_days) <= current_time


def reset_password_expiry_cycle(profile):
    """重置用户密码有效期周期并清除密码过期锁定标记。
    参数：`profile` 为用户扩展档案。
    返回：更新后的用户扩展档案。
    副作用：写入 password_changed_at、password_expired_locked 和 updated_at。
    """
    profile.password_changed_at = timezone.now()
    profile.password_expired_locked = False
    profile.save(update_fields=['password_changed_at', 'password_expired_locked', 'updated_at'])
    return profile


def lock_user_for_password_expiry(user):
    """因密码超过有效期禁用用户并标记为密码过期锁定。
    参数：`user` 为需要禁用的 Django 用户。
    返回：完成锁定时返回 True；缺少档案或用户豁免修改周期时返回 False。
    副作用：将用户 is_active 置为 False，并写入用户档案锁定标记。
    """
    profile = getattr(user, 'profile', None)
    if not profile or password_expiry_exempt(user):
        return False
    user.is_active = False
    user.save(update_fields=['is_active'])
    profile.password_expired_locked = True
    profile.save(update_fields=['password_expired_locked', 'updated_at'])
    return True


def restore_system_admin_expiry_lock(user):
    """恢复被密码修改周期策略误锁定的系统超级管理员 admin。

    参数：`user` 为登录请求命中的候选账号。
    返回：完成恢复返回 True；非 admin、未带密码过期锁定标记或缺少档案时返回 False。
    副作用：仅在档案标记为密码过期锁定时启用账号并重置密码有效期周期。
    """
    profile = getattr(user, 'profile', None)
    if not profile or not profile.password_expired_locked or not password_expiry_exempt(user):
        return False
    if not user.is_active:
        user.is_active = True
        user.save(update_fields=['is_active'])
    reset_password_expiry_cycle(profile)
    return True


def login_security_settings():
    """返回登录认证开关和密码、OTP 错误锁定策略。

    参数：无。
    返回：包含认证开关、失败次数和锁定分钟数的配置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('security.login', DEFAULT_LOGIN_SETTINGS)


def login_lock_policy(settings=None):
    """读取并约束 IP、密码、OTP 与短信验证码的失败锁定策略。

    参数：`settings` 为可选的已读取登录配置，省略时读取数据库。
    返回：八项均为安全范围内整数的登录锁定策略。
    副作用：未传入配置时只读数据库，不修改持久化数据。
    """
    source = settings if isinstance(settings, dict) else login_security_settings()

    def bounded_integer(key, minimum, maximum):
        """将单个策略字段转换为整数并限制在安全范围内。"""
        try:
            value = int(source.get(key, DEFAULT_LOGIN_SETTINGS[key]))
        except (TypeError, ValueError):
            value = DEFAULT_LOGIN_SETTINGS[key]
        return max(minimum, min(maximum, value))

    return {
        'login_failure_limit': bounded_integer('login_failure_limit', 3, 20),
        'login_lock_minutes': bounded_integer('login_lock_minutes', 1, 1440),
        'ip_failure_limit': bounded_integer('ip_failure_limit', 5, 200),
        'ip_lock_minutes': bounded_integer('ip_lock_minutes', 1, 1440),
        'otp_failure_limit': bounded_integer('otp_failure_limit', 3, 20),
        'otp_lock_minutes': bounded_integer('otp_lock_minutes', 1, 1440),
        'sms_failure_limit': bounded_integer('sms_failure_limit', 3, 20),
        'sms_lock_minutes': bounded_integer('sms_lock_minutes', 1, 1440),
    }


def timezone_settings():
    """返回平台统一时区配置。

    参数：无。
    返回：包含 IANA 时区名称的配置字典。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('locale.timezone', DEFAULT_TIMEZONE_SETTINGS)


def watermark_settings():
    """返回工作台全局水印配置。

    参数：无。
    返回：包含内容类型、布局和视觉样式的完整水印配置。
    副作用：只读取数据库，不修改持久化数据。
    """
    return setting_value('security.watermark', DEFAULT_WATERMARK_SETTINGS)


def normalize_access_entries(entries, list_name='访问限制'):
    """规范化并校验访问限制中的 IP 或 CIDR 条目。

    参数：`entries` 为用户提交的地址列表；`list_name` 为错误提示中的名单名称。
    返回：去重后的标准地址字符串列表。
    副作用：输入无效时抛出 `ValueError`，不修改持久化数据。
    """
    if not isinstance(entries, list):
        raise ValueError(f'{list_name}必须是地址列表')
    normalized = []
    for entry in entries:
        text = str(entry or '').strip()
        if not text:
            continue
        try:
            network = ipaddress.ip_network(text, strict=True)
        except ValueError as exc:
            suggestion = ''
            if '/' in text:
                try:
                    expected = ipaddress.ip_network(text, strict=False)
                    suggestion = f'；CIDR 必须使用网段起始地址，例如 {expected}'
                except ValueError:
                    pass
            raise ValueError(f'{list_name}地址无效：{text}{suggestion}') from exc
        canonical = str(network.network_address) if network.prefixlen == network.max_prefixlen else str(network)
        if canonical not in normalized:
            normalized.append(canonical)
    return normalized


def normalize_whitelist_entries(entries):
    """兼容既有调用并规范化登录白名单地址。

    参数：`entries` 为用户提交的地址列表。
    返回：去重后的标准 IP/CIDR 字符串列表。
    副作用：输入无效时抛出 `ValueError`，不修改持久化数据。
    """
    return normalize_access_entries(entries, '白名单')


def normalize_access_descriptions(entries, descriptions, list_name='访问限制'):
    """规范化访问限制地址对应的用途说明。

    参数：`entries` 为已校验的标准地址列表；`descriptions` 为地址到说明的映射；
    `list_name` 为错误提示中的名单名称。
    返回：只包含有效名单地址且去除首尾空白的说明映射。
    副作用：格式错误或说明超过 200 字时抛出 `ValueError`，不修改持久化数据。
    """
    if descriptions in (None, ''):
        return {}
    if not isinstance(descriptions, dict):
        raise ValueError(f'{list_name}说明必须是地址与说明的对应关系')
    valid_entries = set(entries)
    normalized = {}
    for address, description in descriptions.items():
        raw_address = str(address or '').strip()
        text = str(description or '').strip()
        if not raw_address or not text:
            continue
        try:
            network = ipaddress.ip_network(raw_address, strict=True)
        except ValueError as exc:
            raise ValueError(f'{list_name}说明对应的地址无效：{raw_address}') from exc
        canonical = str(network.network_address) if network.prefixlen == network.max_prefixlen else str(network)
        if canonical not in valid_entries:
            continue
        if len(text) > 200:
            raise ValueError(f'{list_name}单条说明不能超过 200 个字符')
        normalized[canonical] = text
    return normalized


def _matches_access_list(ip_address, config):
    """判断来源 IP 是否命中指定的访问限制配置。

    参数：`ip_address` 为来源地址；`config` 为包含 entries 的名单配置。
    返回：来源地址命中任一 IP/CIDR 时返回真。
    副作用：不修改持久化数据；无效地址按未命中处理。
    """
    try:
        address = ipaddress.ip_address(str(ip_address or '').strip())
        networks = [ipaddress.ip_network(entry, strict=False) for entry in config.get('entries', [])]
    except ValueError:
        return False
    return any(address in network for network in networks)


def login_ip_access_result(ip_address):
    """按黑名单优先、白名单随后规则判断登录来源。

    参数：`ip_address` 为服务端读取的来源地址。
    返回：二元组，依次为是否允许和用户友好的拒绝原因。
    副作用：读取数据库中的访问限制配置，不修改持久化数据。
    """
    blacklist = login_blacklist_settings()
    if blacklist.get('enabled') and _matches_access_list(ip_address, blacklist):
        return False, '来源地址在登录黑名单中'
    whitelist = login_whitelist_settings()
    if whitelist.get('enabled') and not _matches_access_list(ip_address, whitelist):
        return False, '来源地址不在登录白名单'
    return True, ''


def login_ip_allowed(ip_address):
    """判断登录来源地址是否符合当前访问限制策略。

    参数：`ip_address` 为服务端从连接信息读取的来源地址。
    返回：未命中黑名单且符合白名单时返回真，否则返回假。
    副作用：读取数据库中的黑白名单配置，不修改持久化数据。
    """
    allowed, _reason = login_ip_access_result(ip_address)
    return allowed


def validate_password(password, username=''):
    """按数据库密码策略校验一个待保存的用户密码。

    参数：`password` 为待校验明文；`username` 为需要排除的登录名。
    返回：全部规则通过时返回原密码。
    副作用：规则不满足时抛出 `ValueError`，不记录或保存明文。
    """
    policy = password_policy_settings()
    value = str(password or '')
    min_length = max(6, min(64, int(policy.get('min_length') or 8)))
    failures = []
    if len(value) < min_length:
        failures.append(f'密码长度不能少于 {min_length} 位')
    if policy.get('require_uppercase') and not any(char.isupper() for char in value):
        failures.append('密码必须包含大写字母')
    if policy.get('require_lowercase') and not any(char.islower() for char in value):
        failures.append('密码必须包含小写字母')
    if policy.get('require_number') and not any(char.isdigit() for char in value):
        failures.append('密码必须包含数字')
    if policy.get('require_special') and not any(not char.isalnum() for char in value):
        failures.append('密码必须包含特殊字符')
    normalized_username = str(username or '').strip().lower()
    if policy.get('exclude_username') and normalized_username and normalized_username in value.lower():
        failures.append('密码不能包含用户名')
    if failures:
        raise ValueError('；'.join(failures))
    return value


def generate_compliant_password(username='', length=16):
    """生成符合当前复杂度策略的随机用户密码。

    参数：`username` 为需避开的登录名；`length` 为期望密码长度。
    返回：通过当前策略校验的随机密码。
    副作用：只读取数据库并使用安全随机源，不保存或输出密码。
    """
    policy = password_policy_settings()
    target_length = max(int(policy.get('min_length') or 8), length, 6)
    required_sets = []
    if policy.get('require_uppercase'):
        required_sets.append(string.ascii_uppercase)
    if policy.get('require_lowercase'):
        required_sets.append(string.ascii_lowercase)
    if policy.get('require_number'):
        required_sets.append(string.digits)
    if policy.get('require_special'):
        required_sets.append('!@#$%^&*_-+=')
    alphabet = string.ascii_letters + string.digits + '!@#$%^&*_-+='
    while True:
        characters = [secrets.choice(values) for values in required_sets]
        characters.extend(secrets.choice(alphabet) for _ in range(target_length - len(characters)))
        secrets.SystemRandom().shuffle(characters)
        candidate = ''.join(characters)
        try:
            return validate_password(candidate, username)
        except ValueError:
            continue
