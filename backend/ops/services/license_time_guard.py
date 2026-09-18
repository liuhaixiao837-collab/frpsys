import json
import time
from datetime import timedelta, timezone as datetime_timezone

from django.db import transaction
from django.utils import timezone


TIME_GUARD_SETTING_KEY = 'license.time_guard'
ROLLBACK_TOLERANCE = timedelta(hours=1)
PERSIST_INTERVAL = timedelta(minutes=1)
_PROCESS_WALL_ANCHOR = timezone.now()
_PROCESS_MONOTONIC_ANCHOR = time.monotonic()


def _as_utc(value):
    """将测试或系统传入时间规范化为带时区 UTC 时间。

    参数：`value` 为 datetime 时间。
    返回：带 UTC 时区的 datetime。
    副作用：时间格式无效时抛出 `ValueError`，不写数据库。
    """
    if not hasattr(value, 'tzinfo'):
        raise ValueError('时间保护输入必须是 datetime')
    if value.tzinfo is None:
        value = value.replace(tzinfo=datetime_timezone.utc)
    return value.astimezone(datetime_timezone.utc)


def _parse_time(value):
    """解析时间保护配置中的 UTC ISO 8601 时间。

    参数：`value` 为已解密时间文本。
    返回：带 UTC 时区的 datetime，空值或格式错误返回 None。
    副作用：不写数据库。
    """
    try:
        parsed = timezone.datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
    except ValueError:
        return None
    return _as_utc(parsed)


def _format_time(value):
    """将时间保护高水位格式化为秒级 UTC ISO 8601 文本。

    参数：`value` 为带时区 datetime。
    返回：以 Z 结尾的秒级 UTC 时间字符串。
    副作用：不写数据库。
    """
    return _as_utc(value).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _decode_guard(value):
    """读取 SM4 保护的时间高水位和不可用锁存状态。

    参数：`value` 为 `license.time_guard` 的 ORM 解密配置。
    返回：结构合法时返回保护状态字典，否则返回 None。
    副作用：不写数据库；JSON 格式错误被转换为 None。
    """
    if not isinstance(value, dict):
        return None
    secret = value.get('guard_secret')
    if not secret:
        return {}
    try:
        guard = json.loads(secret)
    except (TypeError, json.JSONDecodeError):
        return None
    return guard if isinstance(guard, dict) else None


def _encode_guard(guard):
    """将完整时间保护状态编码到触发 SM4 加密的敏感键中。

    参数：`guard` 为高水位、锁存状态和原因组成的字典。
    返回：可交给 `EncryptedJSONField` 保存的配置字典。
    副作用：不直接写数据库。
    """
    return {'guard_secret': json.dumps(guard, ensure_ascii=False, sort_keys=True, separators=(',', ':'))}


def _process_expected_time():
    """根据进程启动墙上时间和单调时钟计算不可倒退的运行期时间。

    参数：无。
    返回：当前进程理论上至少已经到达的 UTC 时间。
    副作用：读取进程单调时钟，不写数据库。
    """
    elapsed = max(0.0, time.monotonic() - _PROCESS_MONOTONIC_ANCHOR)
    return _PROCESS_WALL_ANCHOR + timedelta(seconds=elapsed)


def trusted_license_time(now=None):
    """计算 Licence 使用的可信时间并锁存严重时间回拨。

    参数：`now` 为测试可传入的墙上时间；传入时不比较进程单调时钟。
    返回：二元组 `(可信 UTC 时间, 不可用原因)`，正常时原因为空字符串。
    副作用：事务读取并按分钟推进 `license.time_guard`；回拨超过一小时后永久写入不可用状态。
    """
    from ops.models import SystemSetting

    wall_time = _as_utc(now or timezone.now())
    process_time = wall_time if now is not None else _process_expected_time()
    with transaction.atomic():
        setting, created = SystemSetting.objects.select_for_update().get_or_create(
            key=TIME_GUARD_SETTING_KEY,
            defaults={
                'organization': None,
                'value': {},
                'description': 'Licence 防时间回拨保护状态',
            },
        )
        guard = _decode_guard(setting.value)
        if guard is None:
            guard = {
                'max_trusted_time': _format_time(max(wall_time, process_time)),
                'unavailable': True,
                'reason': '时间保护数据完整性校验失败',
                'detected_at': _format_time(wall_time),
            }
            setting.value = _encode_guard(guard)
            setting.save(update_fields=['value', 'updated_at'])
            return max(wall_time, process_time), guard['reason']

        high_water = _parse_time(guard.get('max_trusted_time'))
        if not high_water:
            high_water = max(wall_time, process_time)
            guard = {
                'max_trusted_time': _format_time(high_water),
                'unavailable': False,
                'reason': '',
                'detected_at': '',
            }

        if guard.get('unavailable'):
            return max(wall_time, process_time, high_water), str(guard.get('reason') or '检测到机器时间异常')

        rollback_reference = max(high_water, process_time)
        if wall_time < rollback_reference - ROLLBACK_TOLERANCE:
            guard.update({
                'unavailable': True,
                'reason': '检测到机器时间回拨超过 1 小时',
                'detected_at': _format_time(wall_time),
                'max_trusted_time': _format_time(rollback_reference),
            })
            setting.value = _encode_guard(guard)
            setting.save(update_fields=['value', 'updated_at'])
            return rollback_reference, guard['reason']

        trusted_time = max(wall_time, process_time, high_water)
        should_persist = created or trusted_time - high_water >= PERSIST_INTERVAL or not setting.value.get('guard_secret')
        if should_persist:
            guard['max_trusted_time'] = _format_time(trusted_time)
            setting.value = _encode_guard(guard)
            setting.save(update_fields=['value', 'updated_at'])
        return trusted_time, ''
