from django.core.cache import cache

from .platform_security import login_lock_policy


def _key(kind, value, state):
    """生成登录失败限制在缓存中使用的稳定键。

    参数：`kind` 表示该步骤所需的kind 参数；`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return f'ongrid:login:password:{state}:{kind}:{str(value or "unknown").lower()}'


def login_blocked(ip_address, username, settings=None):
    """判断指定登录标识和来源地址是否已触发临时锁定。

    参数：`ip_address` 表示该步骤所需的ip_address 参数；`username` 表示该步骤所需的username 参数。
    返回：锁定来源为 `ip` 或 `user`，未锁定时返回空字符串。
    副作用：不直接修改持久化数据。
    """
    if cache.get(_key('ip', ip_address, 'lock'), 0):
        return 'ip'
    if cache.get(_key('user', username, 'lock'), 0):
        return 'user'
    return ''


def record_login_failure(ip_address, username, settings=None):
    """累计登录失败次数并在达到阈值时设置临时锁定。

    参数：`ip_address` 表示该步骤所需的ip_address 参数；`username` 表示该步骤所需的username 参数。
    返回：本次失败触发的锁定来源，未触发时返回空字符串。
    副作用：不直接修改持久化数据。
    """
    policy = login_lock_policy(settings)
    limits = {
        'user': policy['login_failure_limit'],
        'ip': policy['ip_failure_limit'],
    }
    lock_seconds = {
        'user': policy['login_lock_minutes'] * 60,
        'ip': policy['ip_lock_minutes'] * 60,
    }
    locked_kinds = set()
    for kind, value in [('ip', ip_address), ('user', username)]:
        count_key = _key(kind, value, 'count')
        if cache.add(count_key, 1, timeout=lock_seconds[kind]):
            failures = 1
        else:
            try:
                failures = cache.incr(count_key)
            except ValueError:
                cache.set(count_key, 1, timeout=lock_seconds[kind])
                failures = 1
        if failures >= limits[kind]:
            cache.set(_key(kind, value, 'lock'), 1, timeout=lock_seconds[kind])
            cache.delete(count_key)
            locked_kinds.add(kind)
    if 'ip' in locked_kinds:
        return 'ip'
    if 'user' in locked_kinds:
        return 'user'
    return ''


def clear_login_failures(ip_address, username):
    """登录成功后清除对应的失败次数和锁定状态。

    参数：`ip_address` 表示该步骤所需的ip_address 参数；`username` 表示该步骤所需的username 参数。
    返回：无显式返回值。
    副作用：不直接修改持久化数据。
    """
    cache.delete_many([
        _key(kind, value, state)
        for kind, value in [('ip', ip_address), ('user', username)]
        for state in ('count', 'lock')
    ])


def clear_user_login_failures(username):
    """只清除指定账号的密码失败计数和锁定状态。

    参数：`username` 为完成自助改密的登录账号。
    返回：缓存后端删除的键数量。
    副作用：删除账号维度缓存，不影响来源 IP 的防暴力计数和锁定。
    """
    return cache.delete_many([
        _key('user', username, state)
        for state in ('count', 'lock')
    ])


def ip_login_blocked(ip_address):
    """判断来源 IP 是否处于登录防暴力锁定状态。

    参数：`ip_address` 为服务端连接信息中的来源地址。
    返回：IP 锁定时返回 True，否则返回 False。
    副作用：只读取缓存，不修改锁定剩余时间。
    """
    return bool(cache.get(_key('ip', ip_address, 'lock'), 0))

