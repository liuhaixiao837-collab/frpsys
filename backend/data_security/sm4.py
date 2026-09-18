import base64
import hashlib
import hmac
import os
import secrets


PREFIX = 'sm4:v1:'
BLOCK_SIZE = 16

_SBOX = (
    0xD6, 0x90, 0xE9, 0xFE, 0xCC, 0xE1, 0x3D, 0xB7, 0x16, 0xB6, 0x14, 0xC2, 0x28, 0xFB, 0x2C, 0x05,
    0x2B, 0x67, 0x9A, 0x76, 0x2A, 0xBE, 0x04, 0xC3, 0xAA, 0x44, 0x13, 0x26, 0x49, 0x86, 0x06, 0x99,
    0x9C, 0x42, 0x50, 0xF4, 0x91, 0xEF, 0x98, 0x7A, 0x33, 0x54, 0x0B, 0x43, 0xED, 0xCF, 0xAC, 0x62,
    0xE4, 0xB3, 0x1C, 0xA9, 0xC9, 0x08, 0xE8, 0x95, 0x80, 0xDF, 0x94, 0xFA, 0x75, 0x8F, 0x3F, 0xA6,
    0x47, 0x07, 0xA7, 0xFC, 0xF3, 0x73, 0x17, 0xBA, 0x83, 0x59, 0x3C, 0x19, 0xE6, 0x85, 0x4F, 0xA8,
    0x68, 0x6B, 0x81, 0xB2, 0x71, 0x64, 0xDA, 0x8B, 0xF8, 0xEB, 0x0F, 0x4B, 0x70, 0x56, 0x9D, 0x35,
    0x1E, 0x24, 0x0E, 0x5E, 0x63, 0x58, 0xD1, 0xA2, 0x25, 0x22, 0x7C, 0x3B, 0x01, 0x21, 0x78, 0x87,
    0xD4, 0x00, 0x46, 0x57, 0x9F, 0xD3, 0x27, 0x52, 0x4C, 0x36, 0x02, 0xE7, 0xA0, 0xC4, 0xC8, 0x9E,
    0xEA, 0xBF, 0x8A, 0xD2, 0x40, 0xC7, 0x38, 0xB5, 0xA3, 0xF7, 0xF2, 0xCE, 0xF9, 0x61, 0x15, 0xA1,
    0xE0, 0xAE, 0x5D, 0xA4, 0x9B, 0x34, 0x1A, 0x55, 0xAD, 0x93, 0x32, 0x30, 0xF5, 0x8C, 0xB1, 0xE3,
    0x1D, 0xF6, 0xE2, 0x2E, 0x82, 0x66, 0xCA, 0x60, 0xC0, 0x29, 0x23, 0xAB, 0x0D, 0x53, 0x4E, 0x6F,
    0xD5, 0xDB, 0x37, 0x45, 0xDE, 0xFD, 0x8E, 0x2F, 0x03, 0xFF, 0x6A, 0x72, 0x6D, 0x6C, 0x5B, 0x51,
    0x8D, 0x1B, 0xAF, 0x92, 0xBB, 0xDD, 0xBC, 0x7F, 0x11, 0xD9, 0x5C, 0x41, 0x1F, 0x10, 0x5A, 0xD8,
    0x0A, 0xC1, 0x31, 0x88, 0xA5, 0xCD, 0x7B, 0xBD, 0x2D, 0x74, 0xD0, 0x12, 0xB8, 0xE5, 0xB4, 0xB0,
    0x89, 0x69, 0x97, 0x4A, 0x0C, 0x96, 0x77, 0x7E, 0x65, 0xB9, 0xF1, 0x09, 0xC5, 0x6E, 0xC6, 0x84,
    0x18, 0xF0, 0x7D, 0xEC, 0x3A, 0xDC, 0x4D, 0x20, 0x79, 0xEE, 0x5F, 0x3E, 0xD7, 0xCB, 0x39, 0x48,
)
_FK = (0xA3B1BAC6, 0x56AA3350, 0x677D9197, 0xB27022DC)
_CK = (
    0x00070E15, 0x1C232A31, 0x383F464D, 0x545B6269, 0x70777E85, 0x8C939AA1, 0xA8AFB6BD, 0xC4CBD2D9,
    0xE0E7EEF5, 0xFC030A11, 0x181F262D, 0x343B4249, 0x50575E65, 0x6C737A81, 0x888F969D, 0xA4ABB2B9,
    0xC0C7CED5, 0xDCE3EAF1, 0xF8FF060D, 0x141B2229, 0x30373E45, 0x4C535A61, 0x686F767D, 0x848B9299,
    0xA0A7AEB5, 0xBCC3CAD1, 0xD8DFE6ED, 0xF4FB0209, 0x10171E25, 0x2C333A41, 0x484F565D, 0x646B7279,
)


class SM4Error(ValueError):
    pass


def _rotl(value, bits):
    """执行 SM4 字运算所需的三十二位循环左移。

    参数：`value` 表示待处理的输入值；`bits` 表示该步骤所需的bits 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return ((value << bits) | (value >> (32 - bits))) & 0xFFFFFFFF


def _tau(value):
    """对 SM4 状态字的四个字节执行非线性 S 盒变换。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return (
        (_SBOX[(value >> 24) & 0xFF] << 24)
        | (_SBOX[(value >> 16) & 0xFF] << 16)
        | (_SBOX[(value >> 8) & 0xFF] << 8)
        | _SBOX[value & 0xFF]
    )


def _round_transform(value):
    """执行 SM4 数据加解密轮函数的线性变换。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    value = _tau(value)
    return value ^ _rotl(value, 2) ^ _rotl(value, 10) ^ _rotl(value, 18) ^ _rotl(value, 24)


def _key_transform(value):
    """执行 SM4 密钥扩展轮函数的线性变换。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    value = _tau(value)
    return value ^ _rotl(value, 13) ^ _rotl(value, 23)


def _round_keys(key):
    """根据主密钥生成 SM4 三十二轮轮密钥。

    参数：`key` 表示该步骤所需的key 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if len(key) != BLOCK_SIZE:
        raise SM4Error('SM4 key must be exactly 16 bytes')
    words = [int.from_bytes(key[index:index + 4], 'big') ^ _FK[index // 4] for index in range(0, 16, 4)]
    keys = []
    for index in range(32):
        next_word = words[index] ^ _key_transform(words[index + 1] ^ words[index + 2] ^ words[index + 3] ^ _CK[index])
        next_word &= 0xFFFFFFFF
        words.append(next_word)
        keys.append(next_word)
    return keys


def crypt_block(block, key, decrypt=False):
    """使用 SM4 轮密钥加密或解密单个十六字节数据块。

    参数：`block` 表示该步骤所需的block 参数；`key` 表示该步骤所需的key 参数；`decrypt` 表示该步骤所需的decrypt 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if len(block) != BLOCK_SIZE:
        raise SM4Error('SM4 block must be exactly 16 bytes')
    keys = _round_keys(key)
    if decrypt:
        keys.reverse()
    words = [int.from_bytes(block[index:index + 4], 'big') for index in range(0, 16, 4)]
    for round_key in keys:
        words.append((words[-4] ^ _round_transform(words[-3] ^ words[-2] ^ words[-1] ^ round_key)) & 0xFFFFFFFF)
    return b''.join(word.to_bytes(4, 'big') for word in reversed(words[-4:]))


def _xor(left, right):
    """对两个等长字节串执行逐字节异或。

    参数：`left` 表示该步骤所需的left 参数；`right` 表示该步骤所需的right 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return bytes(a ^ b for a, b in zip(left, right))


def _pad(value):
    """使用 PKCS#7 规则将明文填充到十六字节边界。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    length = BLOCK_SIZE - (len(value) % BLOCK_SIZE)
    return value + bytes([length]) * length


def _unpad(value):
    """校验并移除 PKCS#7 填充，拒绝格式不合法的密文。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if not value or len(value) % BLOCK_SIZE:
        raise SM4Error('Invalid SM4 padded payload')
    length = value[-1]
    if length < 1 or length > BLOCK_SIZE or value[-length:] != bytes([length]) * length:
        raise SM4Error('Invalid SM4 padding')
    return value[:-length]


def _cbc_encrypt(value, key, iv):
    """使用随机初始化向量按 SM4-CBC 模式加密数据。

    参数：`value` 表示待处理的输入值；`key` 表示该步骤所需的key 参数；`iv` 表示该步骤所需的iv 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    output = []
    previous = iv
    for index in range(0, len(value), BLOCK_SIZE):
        previous = crypt_block(_xor(value[index:index + BLOCK_SIZE], previous), key)
        output.append(previous)
    return b''.join(output)


def _cbc_decrypt(value, key, iv):
    """按 SM4-CBC 模式解密数据并移除填充。

    参数：`value` 表示待处理的输入值；`key` 表示该步骤所需的key 参数；`iv` 表示该步骤所需的iv 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if not value or len(value) % BLOCK_SIZE:
        raise SM4Error('Invalid SM4 ciphertext length')
    output = []
    previous = iv
    for index in range(0, len(value), BLOCK_SIZE):
        block = value[index:index + BLOCK_SIZE]
        output.append(_xor(crypt_block(block, key, decrypt=True), previous))
        previous = block
    return b''.join(output)


def _digest(data):
    """使用 SM3-HMAC 计算密文完整性校验值。

    参数：`data` 表示待处理的数据。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return hashlib.new('sm3', data).digest()


def _master_keys():
    """读取并校验当前及历史 SM4 主密钥配置。

    参数：无。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    try:
        from django.conf import settings
        configured = getattr(settings, 'SM4_MASTER_KEYS', None)
    except Exception:
        configured = None
    if not configured:
        configured = [os.getenv('SM4_MASTER_KEY', 'local-sm4-development-key-change-me')]
    if isinstance(configured, str):
        configured = [item.strip() for item in configured.split(',') if item.strip()]
    if not configured:
        raise SM4Error('SM4_MASTER_KEY is not configured')
    return [str(item).encode('utf-8') for item in configured]


def _derive_keys(master_key):
    """从主密钥派生相互独立的加密密钥和校验密钥。

    参数：`master_key` 表示该步骤所需的master_key 参数。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    root = _digest(master_key)
    encryption_key = hmac.new(root, b'cmdb-sm4-encryption-v1', 'sm3').digest()[:16]
    authentication_key = hmac.new(root, b'cmdb-sm4-authentication-v1', 'sm3').digest()
    return encryption_key, authentication_key


def is_encrypted(value):
    """判断给定值是否采用当前 SM4 版本密文格式。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return isinstance(value, str) and value.startswith(PREFIX)


def encrypt(value):
    """使用 SM4-CBC、随机初始化向量和 SM3-HMAC 加密明文。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if value is None or value == '':
        return ''
    value = str(value)
    if is_encrypted(value):
        return value
    encryption_key, authentication_key = _derive_keys(_master_keys()[0])
    iv = secrets.token_bytes(BLOCK_SIZE)
    ciphertext = _cbc_encrypt(_pad(value.encode('utf-8')), encryption_key, iv)
    authenticated = PREFIX.encode('ascii') + iv + ciphertext
    tag = hmac.new(authentication_key, authenticated, 'sm3').digest()
    payload = base64.urlsafe_b64encode(iv + ciphertext + tag).decode('ascii')
    return PREFIX + payload


def decrypt(value):
    """校验完整性后使用当前或历史主密钥解密 SM4 密文。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    if value is None or value == '':
        return ''
    value = str(value)
    if not is_encrypted(value):
        raise SM4Error('Value is not an SM4 ciphertext')
    try:
        encoded = value[len(PREFIX):]
        payload = base64.b64decode(encoded, altchars=b'-_', validate=True)
    except (ValueError, base64.binascii.Error) as exc:
        raise SM4Error('Invalid SM4 ciphertext encoding') from exc
    if len(payload) < BLOCK_SIZE + BLOCK_SIZE + 32:
        raise SM4Error('Invalid SM4 ciphertext payload')
    iv, encrypted, supplied_tag = payload[:BLOCK_SIZE], payload[BLOCK_SIZE:-32], payload[-32:]
    authenticated = PREFIX.encode('ascii') + iv + encrypted
    for master_key in _master_keys():
        encryption_key, authentication_key = _derive_keys(master_key)
        expected_tag = hmac.new(authentication_key, authenticated, 'sm3').digest()
        if not hmac.compare_digest(supplied_tag, expected_tag):
            continue
        return _unpad(_cbc_decrypt(encrypted, encryption_key, iv)).decode('utf-8')
    raise SM4Error('SM4 ciphertext authentication failed')


def decrypt_if_encrypted(value):
    """仅在值为 SM4 密文时解密，否则原样返回以兼容历史数据。

    参数：`value` 表示待处理的输入值。
    返回：返回该业务步骤生成、查询或校验后的结果。
    副作用：不直接修改持久化数据。
    """
    return decrypt(value) if is_encrypted(value) else value

