"""手机号标准化与带密钥 SM3 查询索引服务。"""

import hmac

from django.conf import settings


def normalize_mobile_phone(value):
    """标准化并校验中国大陆手机号。

    参数：`value` 为用户输入的手机号，可包含空格、短横线或中国国家码。
    返回：十一位中国大陆手机号；格式无效时抛出 `ValueError`。
    副作用：不读取或修改数据库，不记录手机号。
    """
    normalized = ''.join(character for character in str(value or '').strip() if character not in {' ', '-'})
    if normalized.startswith('+86'):
        normalized = normalized[3:]
    elif normalized.startswith('0086'):
        normalized = normalized[4:]
    if len(normalized) != 11 or not normalized.isdigit() or normalized[0] != '1' or normalized[1] not in '3456789':
        raise ValueError('请输入有效的中国大陆手机号')
    return normalized


def sm3_hmac_hex(domain, value):
    """使用独立域和服务端密钥计算 SM3-HMAC 十六进制摘要。

    参数：`domain` 为摘要用途隔离名称；`value` 为不应明文落库的输入值。
    返回：六十四位小写十六进制摘要。
    副作用：只读取服务端 SMS_SECURITY_KEY，不修改持久化数据。
    """
    key = str(settings.SMS_SECURITY_KEY).encode('utf-8')
    message = f'taichu-bastion:{domain}:v1:{value}'.encode('utf-8')
    return hmac.new(key, message, 'sm3').hexdigest()


def phone_lookup_hash(value):
    """为标准手机号生成不可逆的带密钥 SM3 查询索引。

    参数：`value` 为已标准化或待标准化手机号。
    返回：非空手机号的六十四位摘要，空值返回 `None`。
    副作用：不保存或记录手机号。
    """
    if not str(value or '').strip():
        return None
    return sm3_hmac_hex('phone-lookup', normalize_mobile_phone(value))
