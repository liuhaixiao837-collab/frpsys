import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path

import psutil

from .login_sessions import active_platform_sessions


def _bytes(value):
    """把系统指标值规范为非负整数字节数。

    参数：`value` 为 psutil 返回的数值。
    返回：非负整数。
    副作用：不读取或修改持久化数据。
    """
    return max(0, int(value or 0))


def collect_system_status():
    """采集当前服务主机资源、运行环境和平台在线用户指标。

    参数：无。
    返回：包含 CPU、内存、磁盘、网络累计流量、在线用户和运行环境的字典。
    副作用：读取操作系统指标和平台登录会话数据库，不修改持久化数据。
    """
    memory = psutil.virtual_memory()
    disk_root = Path.cwd().anchor or '/'
    disk = psutil.disk_usage(disk_root)
    network = psutil.net_io_counters()
    platform_sessions = active_platform_sessions()
    active_user_count = platform_sessions.exclude(user_id=None).values('user_id').distinct().count()
    boot_time = datetime.fromtimestamp(psutil.boot_time(), tz=timezone.utc)
    current_time = datetime.now(timezone.utc)
    return {
        'collected_at': current_time.isoformat().replace('+00:00', 'Z'),
        'cpu': {
            'percent': round(float(psutil.cpu_percent(interval=0.1)), 1),
            'physical_cores': psutil.cpu_count(logical=False) or 0,
            'logical_cores': psutil.cpu_count(logical=True) or 0,
        },
        'memory': {
            'percent': round(float(memory.percent), 1),
            'used_bytes': _bytes(memory.used),
            'total_bytes': _bytes(memory.total),
        },
        'disk': {
            'percent': round(float(disk.percent), 1),
            'used_bytes': _bytes(disk.used),
            'total_bytes': _bytes(disk.total),
        },
        'network': {
            'bytes_sent': _bytes(network.bytes_sent),
            'bytes_received': _bytes(network.bytes_recv),
        },
        'concurrency': {
            'users': active_user_count,
            'sessions': platform_sessions.count(),
        },
        'runtime': {
            'hostname': socket.gethostname(),
            'operating_system': platform.platform(),
            'python_version': platform.python_version(),
            'process_id': psutil.Process().pid,
            'boot_time': boot_time.isoformat().replace('+00:00', 'Z'),
            'uptime_seconds': max(0, int((current_time - boot_time).total_seconds())),
            'architecture': platform.machine() or sys.platform,
            'national_cryptography': [
                {
                    'feature': 'Licence 数字签名与验签',
                    'algorithm': 'SM2',
                    'description': '验证 Licence 来源并防止授权内容被篡改',
                },
                {
                    'feature': '数据摘要与完整性校验',
                    'algorithm': 'SM3',
                    'description': '用于 Licence 签名摘要、实例 ID，以及用户手机号等加密数据的完整性校验',
                },
                {
                    'feature': '短信验证码安全校验',
                    'algorithm': 'SM3',
                    'description': '使用带密钥 SM3-HMAC 保护手机号查询索引、短信验证码和登录挑战摘要',
                },
                {
                    'feature': '用户隐私信息加密',
                    'algorithm': 'SM4',
                    'description': '保护用户手机号和 OTP 等可回读隐私信息',
                },
                {
                    'feature': '平台敏感配置加密',
                    'algorithm': 'SM4',
                    'description': '保护邮箱密码、短信密钥和其他平台凭据',
                },
                {
                    'feature': '短信登录敏感数据保护',
                    'algorithm': 'SM4',
                    'description': '加密保存用户手机号和阿里云短信网关 AccessKey Secret',
                },
                {
                    'feature': 'Licence 数据安全存储',
                    'algorithm': 'SM4',
                    'description': '加密保存导入的 Licence 原文',
                },
                {
                    'feature': 'Licence 时间保护数据',
                    'algorithm': 'SM4',
                    'description': '加密保存可信时间和回拨锁定状态',
                },
            ],
        },
    }
