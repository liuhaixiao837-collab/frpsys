from django.db import models

from .sm4 import decrypt_if_encrypted, encrypt


SENSITIVE_KEY_PARTS = (
    'secret', 'password', 'passphrase', 'credential', 'private_key',
    'api_key', 'encrypt_key', 'encryption_key',
)


def is_sensitive_key(key):
    """判断配置键是否代表必须加密保护的敏感数据。

    参数：`key` 表示该步骤所需的key 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    normalized = str(key or '').lower()
    is_token = normalized == 'token' or normalized.endswith('_token')
    return is_token or any(part in normalized for part in SENSITIVE_KEY_PARTS)


def encrypt_sensitive_values(value, sensitive=False):
    """递归加密结构化配置中的敏感字段值。

    参数：`value` 表示待处理的输入值；`sensitive` 表示该步骤所需的sensitive 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if isinstance(value, dict):
        return {
            key: encrypt_sensitive_values(item, sensitive=is_sensitive_key(key))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [encrypt_sensitive_values(item, sensitive=sensitive) for item in value]
    if sensitive and value not in (None, ''):
        return encrypt(value)
    return value


def decrypt_sensitive_values(value):
    """递归解密结构化配置中的敏感字段值。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if isinstance(value, dict):
        return {key: decrypt_sensitive_values(item) for key, item in value.items()}
    if isinstance(value, list):
        return [decrypt_sensitive_values(item) for item in value]
    return decrypt_if_encrypted(value) if isinstance(value, str) else value


class EncryptedCharField(models.CharField):
    description = 'SM4 encrypted character data'

    def from_db_value(self, value, expression, connection):
        """封装 `from_db_value` 对应的业务处理步骤，供所属模块统一调用。

        参数：`value` 表示待处理的输入值；`expression` 表示该步骤所需的expression 参数；`connection` 表示该步骤所需的connection 参数。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        return decrypt_if_encrypted(value) if value else value

    def to_python(self, value):
        """封装 `to_python` 对应的业务处理步骤，供所属模块统一调用。

        参数：`value` 表示待处理的输入值。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        value = super().to_python(value)
        return decrypt_if_encrypted(value) if value else value

    def get_prep_value(self, value):
        """计算并返回 `prep_value` 对应的用户友好业务值。

        参数：`value` 表示待处理的输入值。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        value = super().get_prep_value(value)
        return encrypt(value) if value else value


class EncryptedJSONField(models.JSONField):
    description = 'JSON data with SM4 encrypted sensitive values'

    def from_db_value(self, value, expression, connection):
        """封装 `from_db_value` 对应的业务处理步骤，供所属模块统一调用。

        参数：`value` 表示待处理的输入值；`expression` 表示该步骤所需的expression 参数；`connection` 表示该步骤所需的connection 参数。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        value = super().from_db_value(value, expression, connection)
        return decrypt_sensitive_values(value)

    def to_python(self, value):
        """封装 `to_python` 对应的业务处理步骤，供所属模块统一调用。

        参数：`value` 表示待处理的输入值。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        value = super().to_python(value)
        return decrypt_sensitive_values(value)

    def get_prep_value(self, value):
        """计算并返回 `prep_value` 对应的用户友好业务值。

        参数：`value` 表示待处理的输入值。
        返回：返回该业务步骤生成、查询或校验后的结果。
        副作用：不直接修改持久化数据。
        """
        return super().get_prep_value(encrypt_sensitive_values(value))
