"""堡垒机内置的 Licence SM2 公钥信任表。"""


# 这里只允许放置厂商离线签发公钥，键为 key_id，值为 128 位十六进制
# SM2 公钥（X、Y 坐标顺序拼接）。私钥不得进入本仓库或部署系统。
TRUSTED_LICENSE_SM2_KEYS = {
    'key-951f9d0de2724b16': (
        '760bb8021c3144d8b1a66545f020023278bcd40445342ce15729fbc68e5b5df0'
        'b420eae2b9e215be9726542bfcdb247eed83cb56e3641ae3f9ab185330c489d1'
    ),
}
