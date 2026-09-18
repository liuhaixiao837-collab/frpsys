"""安全解析 HTTP 与 WebSocket 请求的真实客户端 IP。"""

import ipaddress

from django.conf import settings


def normalize_ip_address(value):
    """把 IPv4、IPv6 和 IPv4 映射 IPv6 转换为标准地址。

    参数：`value` 为连接地址或转发头中的单个地址值。
    返回：有效地址的标准字符串；无效或空值返回空字符串。
    副作用：不读取数据库或修改请求。
    """
    text = str(value or '').strip()
    if not text:
        return ''
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return ''
    if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped:
        return str(address.ipv4_mapped)
    return str(address)


def _trusted_proxy_networks():
    """读取并解析允许提供转发地址的可信代理网段。

    返回：由后端配置生成的 IPv4 或 IPv6 网络列表。
    副作用：只读取 Django 配置，不修改运行状态。
    """
    networks = []
    for entry in getattr(settings, 'TRUSTED_PROXY_IPS', []):
        try:
            networks.append(ipaddress.ip_network(str(entry).strip(), strict=False))
        except ValueError:
            continue
    return networks


def _is_trusted_proxy(address):
    """判断单个连接地址是否属于可信代理范围。

    参数：`address` 为已经标准化的 IP 地址。
    返回：命中任一可信代理网段时返回真。
    副作用：只读取配置。
    """
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return any(parsed.version == network.version and parsed in network for network in _trusted_proxy_networks())


def client_ip_from_forwarding(remote_address, forwarded_for=''):
    """按可信代理链计算不可由普通客户端伪造的真实来源 IP。

    参数：`remote_address` 为直接 TCP 对端，`forwarded_for` 为代理转发链。
    返回：从右向左跳过可信代理后的第一个来源地址；无法解析时返回回环地址。
    副作用：不修改请求头或持久化数据。
    """
    remote_ip = normalize_ip_address(remote_address)
    if not remote_ip:
        return '127.0.0.1'
    if not _is_trusted_proxy(remote_ip):
        return remote_ip

    forwarded_chain = [
        normalized
        for item in str(forwarded_for or '').split(',')
        if (normalized := normalize_ip_address(item))
    ]
    for address in reversed([*forwarded_chain, remote_ip]):
        if not _is_trusted_proxy(address):
            return address
    return remote_ip


def request_client_ip(request):
    """从 Django 请求中返回经过可信代理校验的真实客户端 IP。

    参数：`request` 为当前 HTTP 请求。
    返回：可用于名单匹配、锁定和审计的标准 IP 字符串。
    副作用：不修改请求或数据库。
    """
    return client_ip_from_forwarding(
        request.META.get('REMOTE_ADDR'),
        request.META.get('HTTP_X_FORWARDED_FOR', ''),
    )


def scope_client_ip(scope):
    """从 Channels WebSocket scope 中解析真实客户端 IP。

    参数：`scope` 为当前 WebSocket 连接范围。
    返回：可用于名单匹配、会话记录和审计的标准 IP 字符串。
    副作用：不修改连接范围或数据库。
    """
    headers = dict(scope.get('headers') or [])
    forwarded = headers.get(b'x-forwarded-for', b'').decode('utf-8', errors='ignore')
    client = scope.get('client') or ('127.0.0.1', 0)
    return client_ip_from_forwarding(client[0], forwarded)
