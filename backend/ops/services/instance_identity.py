import hashlib
import json
import platform
import shutil
import subprocess
import uuid
from functools import lru_cache
from pathlib import Path


INSTANCE_ID_SCHEMA_VERSION = 1
INSTANCE_ID_DOMAIN = 'taichu-bastion-instance'
INVALID_IDENTIFIERS = {
    '',
    '0',
    '00000000-0000-0000-0000-000000000000',
    'ffffffff-ffff-ffff-ffff-ffffffffffff',
    'default string',
    'none',
    'not specified',
    'to be filled by o.e.m.',
    'unknown',
}


def _normalize_identifier(value):
    """规范化机器标识，消除大小写、首尾括号和多余空白造成的差异。

    参数：`value` 为操作系统、固件或系统磁盘返回的原始标识。
    返回：可参与实例 ID 计算的稳定小写文本，无效占位值返回空字符串。
    副作用：不读取或修改系统与数据库。
    """
    normalized = ' '.join(str(value or '').replace('\x00', '').strip().strip('{}').split()).casefold()
    if normalized in INVALID_IDENTIFIERS or set(normalized.replace('-', '')) in ({'0'}, {'f'}):
        return ''
    return normalized


def _read_identifier(path):
    """读取只包含机器标识的系统文件并进行规范化。

    参数：`path` 为 Linux 系统标识文件路径。
    返回：规范化后的标识；文件不存在、无权限或内容无效时返回空字符串。
    副作用：只读访问指定系统文件，不修改文件。
    """
    try:
        return _normalize_identifier(Path(path).read_text(encoding='utf-8', errors='ignore'))
    except OSError:
        return ''


def _run_identifier_command(arguments):
    """安全执行固定参数的本机标识查询命令。

    参数：`arguments` 为不经过 Shell 拼接的命令与参数列表。
    返回：命令首个非空输出行的规范化标识，执行失败或超时返回空字符串。
    副作用：启动一个最长等待五秒的只读本机查询进程，不写数据库和文件。
    """
    try:
        completed = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='ignore',
            timeout=5,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
    except (OSError, subprocess.SubprocessError):
        return ''
    if completed.returncode != 0:
        return ''
    for line in completed.stdout.splitlines():
        value = _normalize_identifier(line.lstrip('\ufeff'))
        if value:
            return value
    return ''


def _windows_powershell_identifier(script):
    """通过 Windows PowerShell 执行固定的 CIM 或磁盘标识查询。

    参数：`script` 为代码内置、无用户输入的 PowerShell 只读脚本。
    返回：规范化后的首行查询结果，PowerShell 不可用时返回空字符串。
    副作用：启动隐藏的 PowerShell 查询进程，不修改系统配置。
    """
    executable = shutil.which('powershell.exe') or shutil.which('powershell')
    if not executable:
        return ''
    return _run_identifier_command([
        executable,
        '-NoLogo',
        '-NoProfile',
        '-NonInteractive',
        '-Command',
        script,
    ])


def _windows_os_install_id():
    """读取 Windows 注册表 MachineGuid 作为操作系统安装编号。

    参数：无。
    返回：规范化后的 MachineGuid，注册表不可访问时返回空字符串。
    副作用：只读访问本机注册表，不修改注册表。
    """
    try:
        import winreg

        access = winreg.KEY_READ | getattr(winreg, 'KEY_WOW64_64KEY', 0)
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r'SOFTWARE\Microsoft\Cryptography',
            0,
            access,
        ) as key:
            value, _ = winreg.QueryValueEx(key, 'MachineGuid')
    except (ImportError, OSError):
        return ''
    return _normalize_identifier(value)


def _collect_windows_identifiers():
    """采集 Windows 的安装编号、SMBIOS 固件 UUID 和系统磁盘唯一编号。

    参数：无。
    返回：按固定字段命名的三个规范化标识；无法读取的字段为空字符串。
    副作用：只读访问注册表，并启动 PowerShell 查询 CIM 与磁盘信息。
    """
    firmware_uuid = _windows_powershell_identifier(
        "$ErrorActionPreference='Stop'; "
        "[string](Get-CimInstance -ClassName Win32_ComputerSystemProduct).UUID"
    )
    system_disk_uuid = _windows_powershell_identifier(
        "$ErrorActionPreference='Stop'; "
        "$drive=$env:SystemDrive.TrimEnd(':'); "
        "$disk=Get-Partition -DriveLetter $drive | Get-Disk | Select-Object -First 1; "
        "if ($disk.UniqueId) {[string]$disk.UniqueId} "
        "else {[string](Get-Volume -DriveLetter $drive).UniqueId}"
    )
    return {
        'os_install_id': _windows_os_install_id(),
        'firmware_uuid': firmware_uuid,
        'system_disk_uuid': system_disk_uuid,
    }


def _linux_firmware_uuid():
    """读取 Linux DMI 固件 UUID，并在 sysfs 不可用时尝试 dmidecode。

    参数：无。
    返回：规范化后的固件 UUID，当前设备没有 DMI 信息或权限不足时返回空字符串。
    副作用：只读访问 sysfs；必要时执行一次只读 dmidecode 查询。
    """
    for path in (
        '/sys/class/dmi/id/product_uuid',
        '/sys/devices/virtual/dmi/id/product_uuid',
    ):
        value = _read_identifier(path)
        if value:
            return value
    executable = shutil.which('dmidecode')
    if executable:
        return _run_identifier_command([executable, '-s', 'system-uuid'])
    return ''


def _linux_system_disk_uuid():
    """读取 Linux 根文件系统 UUID 作为系统磁盘唯一编号。

    参数：无。
    返回：规范化后的根文件系统 UUID；容器覆盖层或工具不可用时返回空字符串。
    副作用：执行只读 findmnt 查询；回退路径只读遍历 `/dev/disk/by-uuid`。
    """
    findmnt = shutil.which('findmnt')
    if findmnt:
        value = _run_identifier_command([findmnt, '--noheadings', '--output', 'UUID', '--target', '/'])
        if value:
            return value
        source = _run_identifier_command([findmnt, '--noheadings', '--output', 'SOURCE', '--target', '/'])
    else:
        source = ''

    if not source.startswith('/'):
        return ''
    try:
        source_path = Path(source).resolve(strict=True)
        for link in Path('/dev/disk/by-uuid').iterdir():
            if link.resolve(strict=True) == source_path:
                return _normalize_identifier(link.name)
    except OSError:
        return ''
    return ''


def _collect_linux_identifiers():
    """采集 Linux 的安装编号、DMI 固件 UUID 和根文件系统 UUID。

    参数：无。
    返回：按固定字段命名的三个规范化标识；无法读取的字段为空字符串。
    副作用：只读访问 `/etc`、sysfs 和磁盘挂载信息，不修改系统。
    """
    os_install_id = _read_identifier('/etc/machine-id') or _read_identifier('/var/lib/dbus/machine-id')
    return {
        'os_install_id': os_install_id,
        'firmware_uuid': _linux_firmware_uuid(),
        'system_disk_uuid': _linux_system_disk_uuid(),
    }


def collect_machine_identifiers():
    """根据当前操作系统采集生成实例 ID 所需的三个机器标识。

    参数：无。
    返回：Windows 或 Linux 的操作系统安装编号、固件 UUID 和系统磁盘 UUID。
    副作用：执行对应操作系统的只读标识采集，不保存或输出原始标识。
    """
    system_name = platform.system().casefold()
    if system_name == 'windows':
        return _collect_windows_identifiers()
    if system_name == 'linux':
        return _collect_linux_identifiers()
    return {'os_install_id': '', 'firmware_uuid': '', 'system_disk_uuid': ''}


def derive_instance_id(os_install_id, firmware_uuid, system_disk_uuid):
    """使用三个机器标识和 SM3 生成确定性的 UUIDv8 实例 ID。

    参数：依次为操作系统安装编号、固件 UUID 和系统磁盘 UUID。
    返回：符合 RFC 9562 UUIDv8 外形的实例 ID；任一标识无效时抛出 `ValueError`。
    副作用：不保存、输出或传输原始机器标识。
    """
    identifiers = {
        'firmware_uuid': _normalize_identifier(firmware_uuid),
        'os_install_id': _normalize_identifier(os_install_id),
        'system_disk_uuid': _normalize_identifier(system_disk_uuid),
    }
    if not all(identifiers.values()):
        raise ValueError('生成实例 ID 需要三个有效的机器标识')
    canonical = json.dumps(
        {
            'domain': INSTANCE_ID_DOMAIN,
            'schema_version': INSTANCE_ID_SCHEMA_VERSION,
            **identifiers,
        },
        ensure_ascii=True,
        sort_keys=True,
        separators=(',', ':'),
    ).encode('utf-8')
    digest = bytearray(hashlib.new('sm3', canonical).digest()[:16])
    digest[6] = (digest[6] & 0x0F) | 0x80
    digest[8] = (digest[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(digest)))


@lru_cache(maxsize=1)
def get_instance_id():
    """采集当前机器标识并返回本次服务进程使用的稳定实例 ID。

    参数：无。
    返回：成功时返回实例 UUID；标识不足或当前系统不支持时返回空字符串。
    副作用：首次调用执行只读系统采集，结果仅缓存在当前进程内，不写数据库。
    """
    identifiers = collect_machine_identifiers()
    try:
        return derive_instance_id(**identifiers)
    except ValueError:
        return ''


def initialize_instance_identity():
    """在 Django 服务启动时预先计算并缓存当前实例 ID。

    参数：无。
    返回：成功时返回实例 UUID，采集条件不足时返回空字符串。
    副作用：触发一次只读机器标识采集并将计算结果缓存在当前进程内。
    """
    return get_instance_id()
