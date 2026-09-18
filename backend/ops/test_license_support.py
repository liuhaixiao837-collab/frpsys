import base64
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from gmssl import func, sm2, sm3

from ops.services.instance_identity import get_instance_id
from ops.trusted_license_keys import TRUSTED_LICENSE_SM2_KEYS


TEST_PRIVATE_KEY = '0' * 63 + '1'
_KEY_BUILDER = sm2.CryptSM2(private_key=TEST_PRIVATE_KEY, public_key='', asn1=False)
TEST_PUBLIC_KEY = _KEY_BUILDER._kg(int(TEST_PRIVATE_KEY, 16), sm2.default_ecc_table['g']).lower()
TEST_KEY_ID = f"key-{sm3.sm3_hash(func.bytes_to_list(bytes.fromhex(TEST_PUBLIC_KEY)))[:16]}"


def trusted_test_key():
    """返回把后端信任表临时替换为测试 SM2 公钥的补丁。

    参数：无。
    返回：可调用 start/stop 或作为上下文使用的 `patch.dict` 对象。
    副作用：补丁生效期间临时修改进程内可信公钥字典，结束后自动恢复。
    """
    return patch.dict(TRUSTED_LICENSE_SM2_KEYS, {TEST_KEY_ID: TEST_PUBLIC_KEY}, clear=True)


def _b64url(value):
    """生成测试紧凑信封使用的无填充 Base64URL 文本。

    参数：`value` 为待编码字节串。
    返回：ASCII 编码文本。
    副作用：不修改持久化数据。
    """
    return base64.urlsafe_b64encode(value).rstrip(b'=').decode('ascii')


def _canonical_json(value):
    """使用与生产 Licence 相同的规范 JSON 编码测试字段。

    参数：`value` 为待编码字典。
    返回：键排序、无多余空白的 UTF-8 JSON 字节串。
    副作用：不修改持久化数据。
    """
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')


def signed_test_license(**overrides):
    """生成可由生产验签逻辑接受的测试 SM2 Licence。

    参数：`overrides` 可覆盖任一签名载荷字段。
    返回：三段式 ASCII Licence 文本。
    副作用：使用安全随机数生成 SM2 签名随机量，不写数据库或文件。
    """
    instance_id = overrides.get('instance_id') or get_instance_id()
    claims = {
        'schema_version': 3,
        'jti': f'{instance_id}-20260725-TEST0001',
        'sub': '测试客户',
        'license_type': '堡垒机',
        'instance_id': instance_id,
        'max_users': 120,
        'max_concurrency': 10,
        'key_id': TEST_KEY_ID,
        'effective_time': '2020-01-01 00:00:00',
        'expire_time': '2099-12-31 23:59:59',
        **overrides,
    }
    header = {'alg': 'SM2SM3', 'kid': TEST_KEY_ID, 'typ': 'LIC'}
    header_segment = _b64url(_canonical_json(header))
    payload_segment = _b64url(_canonical_json(claims))
    signing_input = f'{header_segment}.{payload_segment}'.encode('ascii')
    signer = sm2.CryptSM2(private_key=TEST_PRIVATE_KEY, public_key=TEST_PUBLIC_KEY, asn1=False)
    signature = bytes.fromhex(signer.sign_with_sm3(signing_input, func.random_hex(64)))
    return f'{header_segment}.{payload_segment}.{_b64url(signature)}'


def verified_license_metadata(*, expired=False, **overrides):
    """生成绕过导入接口时用于其他业务测试的已验签 Licence 元数据。

    参数：`expired` 表示是否生成已经到期的状态；`overrides` 可覆盖授权额度等字段。
    返回：与生产导入后数据库结构一致且不含真实签名原文的字典。
    副作用：读取当前测试进程缓存的实例 ID，不写数据库。
    """
    instance_id = get_instance_id()
    effective_time = datetime(1999, 1, 1, tzinfo=timezone.utc) if expired else datetime.now(timezone.utc) - timedelta(days=1)
    expire_time = datetime(2000, 1, 1, tzinfo=timezone.utc) if expired else datetime(2099, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return {
        'configured': True,
        'schema_version': 3,
        'license_id': f'{instance_id}-20260725-TESTMETA',
        'customer': '测试客户',
        'license_type': '堡垒机',
        'instance_id': instance_id,
        'effective_time': effective_time.isoformat().replace('+00:00', 'Z'),
        'expire_time': expire_time.isoformat().replace('+00:00', 'Z'),
        'max_users': 100,
        'max_concurrency': 10,
        'verification': 'sm2-sm3',
        **overrides,
    }
