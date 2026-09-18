import base64
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

from django.contrib.auth.models import User
from gmssl import func, sm2, sm3

from ops.trusted_license_keys import TRUSTED_LICENSE_SM2_KEYS

from .instance_identity import get_instance_id
from .license_time_guard import trusted_license_time


MAX_LICENSE_BYTES = 64 * 1024
LICENSE_SCHEMA_VERSION = 3
LICENSE_ALGORITHM = 'SM2SM3'
LICENSE_TYPE = '堡垒机'
SIGNATURE_BYTES = 64
CHINA_TZ = timezone(timedelta(hours=8), name='Asia/Shanghai')
DISPLAY_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'
EXPECTED_CLAIMS = {
    'schema_version',
    'jti',
    'sub',
    'license_type',
    'instance_id',
    'max_users',
    'max_concurrency',
    'key_id',
    'effective_time',
    'expire_time',
}


def _b64url_encode(value):
    """将字节串编码为无填充 Base64URL 文本。

    参数：`value` 为待编码字节串。
    返回：ASCII Base64URL 字符串。
    副作用：不读写数据库或文件。
    """
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _b64url_decode(value, field_name):
    """严格解码 Licence 的无填充 Base64URL 字段。

    参数：`value` 为编码文本；`field_name` 为中文错误定位字段。
    返回：解码后的字节串。
    副作用：编码不规范时抛出 `ValueError`，不写数据库。
    """
    if not value or '=' in value or not re.fullmatch(r'[A-Za-z0-9_-]+', value):
        raise ValueError(f'Licence {field_name} 编码无效')
    try:
        decoded = base64.urlsafe_b64decode(value + '=' * (-len(value) % 4))
    except (ValueError, base64.binascii.Error) as exc:
        raise ValueError(f'Licence {field_name} 编码无效') from exc
    if _b64url_encode(decoded) != value:
        raise ValueError(f'Licence {field_name} 编码不是规范格式')
    return decoded


def _decode_json_segment(segment, field_name):
    """解码并解析签名信封中的 UTF-8 JSON 对象。

    参数：`segment` 为 Base64URL 段；`field_name` 为 header 或 payload。
    返回：解析后的字典。
    副作用：文本、JSON 或顶层结构无效时抛出 `ValueError`。
    """
    try:
        value = json.loads(_b64url_decode(segment, field_name).decode('utf-8'))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f'Licence {field_name} 不是有效 UTF-8 JSON') from exc
    if not isinstance(value, dict):
        raise ValueError(f'Licence {field_name} 顶层必须是 JSON 对象')
    return value


def _sm3_hex(value):
    """使用 gmssl 计算字节串的 SM3 十六进制摘要。

    参数：`value` 为待摘要字节串。
    返回：64 位小写十六进制摘要。
    副作用：不读写持久化数据。
    """
    return sm3.sm3_hash(func.bytes_to_list(value))


def _trusted_public_key(key_id):
    """按 key_id 从后端内置信任表读取并验证 SM2 公钥。

    参数：`key_id` 为 Licence header 声明的公钥编号。
    返回：128 位十六进制 SM2 公钥。
    副作用：未知编号或信任表配置错误时抛出 `ValueError`；绝不读取 Licence 自带公钥。
    """
    public_key = str(TRUSTED_LICENSE_SM2_KEYS.get(key_id) or '').lower()
    if not public_key:
        raise ValueError('Licence 使用了未知的签发公钥')
    if not re.fullmatch(r'[0-9a-f]{128}', public_key):
        raise ValueError('Licence 可信公钥配置无效')
    expected_key_id = f'key-{_sm3_hex(bytes.fromhex(public_key))[:16]}'
    if key_id != expected_key_id:
        raise ValueError('Licence 可信公钥与 key_id 不匹配')
    return public_key


def _parse_signed_time(value, field_name):
    """严格解析签名载荷中的北京时间并转换为 UTC。

    参数：`value` 为时间文本；`field_name` 为中文字段名。
    返回：带 UTC 时区的 datetime。
    副作用：格式不符时抛出 `ValueError`，不写数据库。
    """
    if not isinstance(value, str):
        raise ValueError(f'Licence {field_name} 无效')
    try:
        parsed = datetime.strptime(value, DISPLAY_TIME_FORMAT).replace(tzinfo=CHINA_TZ)
    except ValueError as exc:
        raise ValueError(f'Licence {field_name} 必须使用 YYYY-MM-DD HH:MM:SS') from exc
    return parsed.astimezone(timezone.utc)


def _iso_time(value):
    """将 datetime 转换为秒级 UTC ISO 8601 字符串。

    参数：`value` 为带时区时间。
    返回：以 Z 结尾的 UTC 时间字符串。
    副作用：不读写数据库。
    """
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def _metadata_time(value):
    """读取已验签元数据中的 UTC ISO 8601 时间。

    参数：`value` 为数据库保存的时间文本。
    返回：带 UTC 时区 datetime，格式错误时返回 None。
    副作用：不写数据库。
    """
    try:
        parsed = datetime.fromisoformat(str(value or '').replace('Z', '+00:00'))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _safe_text(payload, field, label, max_length):
    """清理并限制 Licence 必填文本字段。

    参数：`payload` 为已验签载荷；`field` 为字段名；`label` 为错误名称；`max_length` 为最大长度。
    返回：去除首尾空白的文本。
    副作用：空值、控制字符或过长时抛出 `ValueError`。
    """
    value = payload.get(field)
    if not isinstance(value, str):
        raise ValueError(f'Licence {label} 无效')
    text = value.strip()
    if not text or len(text) > max_length or any(ord(character) < 32 for character in text):
        raise ValueError(f'Licence {label} 无效')
    return text


def _positive_limit(payload, field):
    """读取并校验 Licence 中的正整数额度。

    参数：`payload` 为已验签载荷；`field` 为额度字段名。
    返回：1 到 1000000 之间的整数。
    副作用：类型或范围无效时抛出 `ValueError`。
    """
    value = payload.get(field)
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= 1_000_000:
        raise ValueError(f'Licence {field} 必须是 1 到 1000000 之间的整数')
    return value


def _verify_envelope(text):
    """解析紧凑信封并使用内置 SM2 公钥执行 SM3 验签。

    参数：`text` 为 Licence 原文。
    返回：签名可信的 payload 字典。
    副作用：格式、算法、key_id 或签名无效时抛出 `ValueError`；不读取文件或写数据库。
    """
    segments = text.split('.')
    if len(segments) != 3:
        raise ValueError('Licence 必须是 SM2 三段式签名格式，旧版 Licence 不再支持')
    header = _decode_json_segment(segments[0], 'header')
    payload = _decode_json_segment(segments[1], 'payload')
    if set(header) != {'alg', 'kid', 'typ'}:
        raise ValueError('Licence header 字段无效')
    key_id = header.get('kid')
    if header.get('alg') != LICENSE_ALGORITHM or header.get('typ') != 'LIC' or not isinstance(key_id, str):
        raise ValueError('Licence 只允许使用 SM2SM3 签名算法')
    public_key = _trusted_public_key(key_id)
    signature = _b64url_decode(segments[2], 'signature')
    if len(signature) != SIGNATURE_BYTES:
        raise ValueError('Licence SM2 签名长度无效')
    verifier = sm2.CryptSM2(private_key='', public_key=public_key, asn1=False)
    signing_input = f'{segments[0]}.{segments[1]}'.encode('ascii')
    try:
        verified = verifier.verify_with_sm3(signature.hex(), signing_input)
    except (TypeError, ValueError, IndexError):
        verified = False
    if not verified:
        raise ValueError('Licence SM2/SM3 签名验证失败，文件可能已被修改')
    if set(payload) != EXPECTED_CLAIMS:
        raise ValueError('Licence payload 字段不完整或包含未知字段')
    if payload.get('schema_version') != LICENSE_SCHEMA_VERSION:
        raise ValueError('Licence schema_version 不受支持')
    if payload.get('key_id') != key_id:
        raise ValueError('Licence payload key_id 与 header 不一致')
    return payload


def normalize_license_content(content, now=None):
    """验签并校验导入 Licence，生成可加密保存的原文和安全元数据。

    参数：`content` 为上传或输入的 Licence 原文；`now` 为测试可传入的当前时间。
    返回：包含 SM4 敏感键、已验签授权元数据和验证方式的配置字典。
    副作用：读取启用用户数量和实例 ID，并推进时间保护高水位；任何校验失败时不保存 Licence。
    """
    text = str(content or '').strip()
    if not text:
        raise ValueError('Licence 内容不能为空')
    try:
        encoded_size = len(text.encode('ascii'))
    except UnicodeEncodeError as exc:
        raise ValueError('Licence 必须是 ASCII 紧凑签名文本') from exc
    if encoded_size > MAX_LICENSE_BYTES:
        raise ValueError('Licence 文件不能超过 64 KB')
    payload = _verify_envelope(text)
    license_id = _safe_text(payload, 'jti', '编号', 120)
    customer = _safe_text(payload, 'sub', '授权客户', 160)
    license_type = _safe_text(payload, 'license_type', '授权类型', 64)
    if license_type != LICENSE_TYPE:
        raise ValueError(f'当前系统只接受授权类型“{LICENSE_TYPE}”')
    try:
        instance_id = str(uuid.UUID(_safe_text(payload, 'instance_id', '实例 ID', 36)))
    except ValueError as exc:
        raise ValueError('Licence 实例 ID 必须是有效 UUID') from exc
    current_instance_id = get_instance_id()
    if not current_instance_id:
        raise ValueError('当前服务器实例 ID 暂不可用，不能导入 Licence')
    if instance_id != current_instance_id:
        raise ValueError('Licence 实例 ID 与当前服务器不一致')
    if not license_id.startswith(f'{instance_id}-'):
        raise ValueError('Licence 编号前缀必须与实例 ID 一致')
    max_users = _positive_limit(payload, 'max_users')
    max_concurrency = _positive_limit(payload, 'max_concurrency')
    active_users = User.objects.filter(is_active=True).count()
    if active_users > max_users:
        raise ValueError(f'当前启用用户数为 {active_users}，超过 Licence 授权用户数 {max_users}')
    effective_time = _parse_signed_time(payload.get('effective_time'), '生效时间')
    expire_time = _parse_signed_time(payload.get('expire_time'), '到期时间')
    if expire_time <= effective_time:
        raise ValueError('Licence 到期时间必须晚于生效时间')
    trusted_time, unavailable_reason = trusted_license_time(now=now)
    if unavailable_reason:
        raise ValueError(f'Licence 时间保护不可用：{unavailable_reason}')
    if trusted_time < effective_time:
        raise ValueError('Licence 尚未到生效时间')
    if trusted_time >= expire_time:
        raise ValueError('Licence 已过期')
    return {
        'configured': True,
        'license_secret': text,
        'schema_version': LICENSE_SCHEMA_VERSION,
        'license_id': license_id,
        'customer': customer,
        'license_type': license_type,
        'instance_id': instance_id,
        'effective_time': _iso_time(effective_time),
        'expire_time': _iso_time(expire_time),
        'max_users': max_users,
        'max_concurrency': max_concurrency,
        'verification': 'sm2-sm3',
    }


def _unconfigured_metadata(instance_id):
    """生成 Licence 未配置时的统一公开元数据。

    参数：`instance_id` 为当前服务器计算的实例 ID。
    返回：不含 Licence 原文的未配置状态字典。
    副作用：不读写数据库。
    """
    return {
        'configured': False,
        'status': 'unconfigured',
        'status_label': '未配置',
        'instance_id': instance_id,
        'license_id': '',
        'customer': '',
        'license_type': '',
        'effective_time': '',
        'expire_time': '',
        'max_users': 0,
        'max_concurrency': 0,
        'days_remaining': 0,
        'verification': '',
        'unavailable_reason': '',
    }


def _unavailable_metadata(data, instance_id, reason):
    """生成已配置但不可用时的安全公开元数据。

    参数：`data` 为已保存元数据；`instance_id` 为当前实例；`reason` 为中文业务原因。
    返回：保留安全展示字段且不含 Licence 原文、签名或 key_id 的字典。
    副作用：不读写数据库。
    """
    return {
        'configured': True,
        'status': 'unavailable',
        'status_label': '不可用',
        'instance_id': instance_id,
        'license_id': data.get('license_id', ''),
        'customer': data.get('customer', ''),
        'license_type': data.get('license_type', ''),
        'effective_time': data.get('effective_time', ''),
        'expire_time': data.get('expire_time', ''),
        'max_users': data.get('max_users', 0),
        'max_concurrency': data.get('max_concurrency', 0),
        'days_remaining': 0,
        'verification': data.get('verification', ''),
        'unavailable_reason': reason,
    }


def license_public_metadata(value, now=None):
    """动态计算 Licence 的有效、过期、未配置或不可用公开状态。

    参数：`value` 为已保存配置；`now` 为测试可传入的当前时间。
    返回：不含 Licence 原文、签名和公钥细节的状态及授权元数据。
    副作用：读取当前实例 ID并推进时间保护高水位；不修改 Licence 配置。
    """
    data = value if isinstance(value, dict) else {}
    instance_id = get_instance_id()
    if not data.get('configured'):
        return _unconfigured_metadata(instance_id)
    if data.get('verification') != 'sm2-sm3' or data.get('schema_version') != LICENSE_SCHEMA_VERSION:
        return _unavailable_metadata(data, instance_id, 'Licence 未通过当前 SM2/SM3 验签')
    if not instance_id:
        return _unavailable_metadata(data, instance_id, '当前服务器实例 ID 暂不可用')
    if data.get('instance_id') != instance_id:
        return _unavailable_metadata(data, instance_id, '运行环境实例 ID 与 Licence 不一致')
    if data.get('license_type') != LICENSE_TYPE:
        return _unavailable_metadata(data, instance_id, 'Licence 授权类型与当前系统不一致')
    effective_time = _metadata_time(data.get('effective_time'))
    expire_time = _metadata_time(data.get('expire_time'))
    if not effective_time or not expire_time or expire_time <= effective_time:
        return _unavailable_metadata(data, instance_id, 'Licence 时间字段无效')
    trusted_time, unavailable_reason = trusted_license_time(now=now)
    if unavailable_reason:
        return _unavailable_metadata(data, instance_id, unavailable_reason)
    if trusted_time < effective_time:
        return _unavailable_metadata(data, instance_id, 'Licence 尚未到生效时间')
    remaining_seconds = (expire_time - trusted_time).total_seconds()
    status = 'valid' if remaining_seconds > 0 else 'expired'
    return {
        'configured': True,
        'status': status,
        'status_label': '有效' if status == 'valid' else '已过期',
        'instance_id': instance_id,
        'days_remaining': max(0, int(remaining_seconds // 86400)),
        'license_id': data.get('license_id', ''),
        'customer': data.get('customer', ''),
        'license_type': data.get('license_type', ''),
        'effective_time': data.get('effective_time', ''),
        'expire_time': data.get('expire_time', ''),
        'max_users': data.get('max_users', 0),
        'max_concurrency': data.get('max_concurrency', 0),
        'verification': data.get('verification', ''),
        'unavailable_reason': '',
    }
