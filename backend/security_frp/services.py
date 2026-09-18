import base64
import hashlib
import json
import socket
import urllib.parse
import urllib.error
import urllib.request

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from data_security.sm4 import decrypt
from ops.models import AuditLog
from ops.permissions import user_organization

from . import models


FRP_PROXY_TYPES = ('tcp', 'udp', 'http', 'https', 'stcp', 'xtcp')


class FrpHttpError(Exception):
    """Normalized FRP API error with HTTP status for caller-side branching."""

    def __init__(self, message, status_code=None):
        """处理 FRP 模块的 __init__ 业务步骤。"""
        super().__init__(message)
        self.status_code = status_code


def request_ip(request):
    """处理 FRP 模块的 request_ip 业务步骤。"""
    forwarded = request.META.get('HTTP_X_FORWARDED_FOR', '')
    return (forwarded.split(',', 1)[0].strip() if forwarded else request.META.get('REMOTE_ADDR')) or '127.0.0.1'


def write_frp_audit(request, action, resource, detail=None, organization=None):
    """处理 FRP 模块的 write_frp_audit 业务步骤。"""
    user = getattr(request, 'user', None)
    AuditLog.objects.create(
        organization=organization or getattr(resource, 'organization', None) or (user_organization(user) if user and user.is_authenticated else None),
        actor=getattr(user, 'username', '') or 'frp-agent',
        action=f'frp.{action}',
        resource=str(resource),
        ip_address=request_ip(request),
        detail=detail or {},
    )


def test_tcp_endpoint(host, port, timeout=3):
    """处理 FRP 模块的 test_tcp_endpoint 业务步骤。"""
    started = timezone.now()
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True, '端口可连通', started
    except (OSError, ValueError) as exc:
        return False, f'端口不可连通：{exc}', started


def update_server_test_result(server, ok, message, checked_at):
    """处理 FRP 模块的 update_server_test_result 业务步骤。"""
    server.last_test_status = 'success' if ok else 'failed'
    server.last_test_message = message[:240]
    server.last_test_at = checked_at
    if server.status != 'disabled':
        server.status = 'available' if ok else 'unavailable'
    server.save(update_fields=['last_test_status', 'last_test_message', 'last_test_at', 'status', 'updated_at'])
    return {
        'status': server.status,
        'detail': server.last_test_message,
        'checked_at': timezone.localtime(checked_at).strftime('%Y-%m-%d %H:%M:%S'),
    }


def _base_url(host, port):
    """处理 FRP 模块的 _base_url 业务步骤。"""
    host = str(host or '').strip()
    if not host:
        raise ValidationError({'detail': 'FRP API 地址未配置。'})
    if host.startswith('http://') or host.startswith('https://'):
        return host.rstrip('/')
    return f'http://{host}:{int(port)}'


def _basic_auth_header(username='', password=''):
    """处理 FRP 模块的 _basic_auth_header 业务步骤。"""
    if not username and not password:
        return ''
    raw = f'{username}:{password}'.encode('utf-8')
    return 'Basic ' + base64.b64encode(raw).decode('ascii')


def _json_request(method, url, username='', password='', payload=None, timeout=6):
    """处理 FRP 模块的 _json_request 业务步骤。"""
    data = None
    headers = {'Accept': 'application/json'}
    if payload is not None:
        data = json.dumps(payload).encode('utf-8')
        headers['Content-Type'] = 'application/json'
    auth = _basic_auth_header(username, password)
    if auth:
        headers['Authorization'] = auth
    request = urllib.request.Request(url, data=data, headers=headers, method=method.upper())
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read().decode('utf-8', errors='replace').strip()
            if not body:
                return {}
            return json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace').strip()
        raise FrpHttpError(f'FRP API 调用失败：HTTP {exc.code} {body or exc.reason}', exc.code) from exc
    except urllib.error.URLError as exc:
        raise FrpHttpError(f'FRP API 连接失败：{exc.reason}') from exc
    except (TimeoutError, socket.timeout) as exc:
        raise FrpHttpError('FRP API 连接超时。') from exc
    except ValueError as exc:
        raise FrpHttpError(f'FRP API 返回不是合法 JSON：{exc}') from exc


def _dashboard_credentials(server):
    """处理 FRP 模块的 _dashboard_credentials 业务步骤。"""
    return server.dashboard_username or '', decrypt(server.encrypted_dashboard_password)


def _client_admin_credentials(agent):
    """处理 FRP 模块的 _client_admin_credentials 业务步骤。"""
    username = agent.admin_username or ''
    password = decrypt(agent.encrypted_admin_password)
    if not username or not password:
        raise ValidationError({'detail': 'frpc Admin API 用户名或密码未配置，请先在 frpc 客户端里维护。'})
    return username, password


def frps_dashboard_get(server, path):
    """处理 FRP 模块的 frps_dashboard_get 业务步骤。"""
    username, password = _dashboard_credentials(server)
    host = server.dashboard_host or server.public_host
    return _json_request('GET', f'{_base_url(host, server.dashboard_port)}{path}', username, password)


def frpc_admin_get(agent, path):
    """处理 FRP 模块的 frpc_admin_get 业务步骤。"""
    username, password = _client_admin_credentials(agent)
    return _json_request('GET', f'{_base_url(agent.admin_host, agent.admin_port)}{path}', username, password)


def frpc_admin_post(agent, path, payload):
    """处理 FRP 模块的 frpc_admin_post 业务步骤。"""
    username, password = _client_admin_credentials(agent)
    return _json_request('POST', f'{_base_url(agent.admin_host, agent.admin_port)}{path}', username, password, payload=payload)


def frpc_admin_put(agent, path, payload):
    """处理 FRP 模块的 frpc_admin_put 业务步骤。"""
    username, password = _client_admin_credentials(agent)
    return _json_request('PUT', f'{_base_url(agent.admin_host, agent.admin_port)}{path}', username, password, payload=payload)


def frpc_admin_delete(agent, path):
    """处理 FRP 模块的 frpc_admin_delete 业务步骤。"""
    username, password = _client_admin_credentials(agent)
    return _json_request('DELETE', f'{_base_url(agent.admin_host, agent.admin_port)}{path}', username, password)


def _proxy_name(item):
    """处理 FRP 模块的 _proxy_name 业务步骤。"""
    return str(item.get('name') or item.get('proxyName') or '').strip()


def _traffic_bytes(value):
    """Normalize FRP traffic counters to bytes."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, dict):
        for key in ('bytes', 'value', 'total', 'amount'):
            if key in value:
                return _traffic_bytes(value[key])
        return None
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = str(value).strip().replace(',', '')
    if not text:
        return None
    suffixes = (('tib', 1024 ** 4), ('tb', 1024 ** 4), ('gib', 1024 ** 3), ('gb', 1024 ** 3),
                ('mib', 1024 ** 2), ('mb', 1024 ** 2), ('kib', 1024), ('kb', 1024), ('b', 1))
    lowered = text.lower()
    for suffix, multiplier in suffixes:
        if lowered.endswith(suffix):
            try:
                return max(0, int(float(lowered[:-len(suffix)].strip()) * multiplier))
            except ValueError:
                return None
    try:
        return max(0, int(float(text)))
    except ValueError:
        return None


def _proxy_traffic(item, direction):
    """Read traffic counters from the FRPS proxy payload across API versions."""
    keys = {
        'in': ('traffic_in_bytes', 'trafficInBytes', 'traffic_in', 'trafficIn', 'bytes_in', 'in_bytes'),
        'out': ('traffic_out_bytes', 'trafficOutBytes', 'traffic_out', 'trafficOut', 'bytes_out', 'out_bytes'),
        'today_in': ('today_traffic_in_bytes', 'todayTrafficIn', 'today_traffic_in'),
        'today_out': ('today_traffic_out_bytes', 'todayTrafficOut', 'today_traffic_out'),
    }[direction]
    for key in keys:
        if key in item:
            parsed = _traffic_bytes(item.get(key))
            if parsed is not None:
                return parsed
    traffic = item.get('traffic')
    if isinstance(traffic, dict):
        for key in keys:
            if key in traffic:
                parsed = _traffic_bytes(traffic.get(key))
                if parsed is not None:
                    return parsed
    return None


def update_proxy_traffic(proxy, item, updated_at=None):
    """Persist traffic counters when the FRPS Dashboard exposes them."""
    traffic_in = _proxy_traffic(item, 'in')
    traffic_out = _proxy_traffic(item, 'out')
    today_in = _proxy_traffic(item, 'today_in')
    today_out = _proxy_traffic(item, 'today_out')
    if traffic_in is None and traffic_out is None and today_in is None and today_out is None:
        return False
    checked_at = updated_at or timezone.now()
    checked_date = timezone.localtime(checked_at).date()
    same_day = proxy.traffic_date == checked_date

    for direction, source_value, today_value in (
        ('in', traffic_in, today_in),
        ('out', traffic_out, today_out),
    ):
        if source_value is None:
            source_value = today_value
        if source_value is None:
            continue
        source_key = f'traffic_source_{direction}_bytes'
        total_key = f'traffic_{direction}_bytes'
        today_key = f'today_traffic_{direction}_bytes'
        previous_source = int(getattr(proxy, source_key) or 0)
        delta = source_value if not proxy.traffic_updated_at or not same_day else max(0, source_value - previous_source)
        if same_day and source_value < previous_source:
            delta = source_value
        setattr(proxy, total_key, int(getattr(proxy, total_key) or 0) + delta)
        setattr(proxy, today_key, today_value if today_value is not None else (int(getattr(proxy, today_key) or 0) + delta if same_day else delta))
        setattr(proxy, source_key, source_value)
    proxy.traffic_date = checked_date
    proxy.traffic_updated_at = checked_at
    proxy.save(update_fields=['traffic_in_bytes', 'traffic_out_bytes', 'today_traffic_in_bytes', 'today_traffic_out_bytes', 'traffic_source_in_bytes', 'traffic_source_out_bytes', 'traffic_date', 'traffic_updated_at', 'updated_at'])
    return True


def _proxy_type(item, fallback='tcp'):
    """处理 FRP 模块的 _proxy_type 业务步骤。"""
    return str(item.get('type') or item.get('proxyType') or fallback or 'tcp').strip().lower()


def _proxy_conf(item, proxy_type=None):
    """处理 FRP 模块的 _proxy_conf 业务步骤。"""
    proxy_type = proxy_type or _proxy_type(item)
    conf = item.get(proxy_type)
    if isinstance(conf, dict):
        return conf
    conf = item.get('conf')
    return conf if isinstance(conf, dict) else {}


def _extract_proxy_items(payload, proxy_type=None):
    """处理 FRP 模块的 _extract_proxy_items 业务步骤。"""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if isinstance(payload.get('proxies'), list):
        return [item for item in payload['proxies'] if isinstance(item, dict)]
    keys = [proxy_type] if proxy_type else FRP_PROXY_TYPES
    rows = []
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            rows.extend(item for item in value if isinstance(item, dict))
    return rows


def _proxy_enabled(item):
    """处理 FRP 模块的 _proxy_enabled 业务步骤。"""
    conf = _proxy_conf(item)
    value = item.get('enabled')
    if value is None:
        value = conf.get('enabled')
    if value is None:
        return True
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() not in {'false', '0', 'no', 'off', 'disabled'}


def _parse_host_port(value, fallback_host=''):
    """处理 FRP 模块的 _parse_host_port 业务步骤。"""
    text = str(value or '').strip()
    if not text:
        return fallback_host, None
    if text.startswith('[') and ']:' in text:
        host, port = text.rsplit(':', 1)
        return host.strip('[]'), _int_or_none(port)
    if ':' in text:
        host, port = text.rsplit(':', 1)
        return host or fallback_host, _int_or_none(port)
    return fallback_host, _int_or_none(text)


def _int_or_none(value):
    """处理 FRP 模块的 _int_or_none 业务步骤。"""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _local_endpoint(item, proxy_type):
    """处理 FRP 模块的 _local_endpoint 业务步骤。"""
    conf = _proxy_conf(item, proxy_type)
    local_ip = item.get('local_ip') or item.get('localIP') or conf.get('localIP') or conf.get('local_ip') or ''
    local_port = item.get('local_port') or item.get('localPort') or conf.get('localPort') or conf.get('local_port')
    if (not local_ip or not local_port) and (item.get('local_addr') or item.get('localAddr')):
        local_ip, local_port = _parse_host_port(item.get('local_addr') or item.get('localAddr'), fallback_host=local_ip)
    return local_ip or '127.0.0.1', _int_or_none(local_port) or 0


def _remote_endpoint(item, proxy_type, server):
    """处理 FRP 模块的 _remote_endpoint 业务步骤。"""
    conf = _proxy_conf(item, proxy_type)
    remote_port = item.get('remote_port') or item.get('remotePort') or conf.get('remotePort') or conf.get('remote_port')
    remote_host = server.public_host
    if item.get('remote_addr') or item.get('remoteAddr'):
        remote_host, parsed_port = _parse_host_port(item.get('remote_addr') or item.get('remoteAddr'), fallback_host=server.public_host)
        remote_port = remote_port or parsed_port
    return remote_host or server.public_host, _int_or_none(remote_port)


def _is_running(status):
    """处理 FRP 模块的 _is_running 业务步骤。"""
    return str(status or '').lower() in {'running', 'online', 'available', 'success'}


def _is_admin_proxy(item):
    """处理 FRP 模块的 _is_admin_proxy 业务步骤。"""
    name = _proxy_name(item).lower()
    local_addr = str(item.get('local_addr') or item.get('localAddr') or '').lower()
    return name == 'frpc-admin-api' or name.endswith('-admin-api') or local_addr.endswith(':7400')


def _proxy_store_definition(name, proxy_type, local_ip, local_port, remote_port=None, custom_domains=None, subdomain='', use_encryption=True, use_compression=True, enabled=None):
    """处理 FRP 模块的 _proxy_store_definition 业务步骤。"""
    block = {
        'localIP': local_ip,
        'localPort': local_port,
        'transport': {
            'useEncryption': bool(use_encryption),
            'useCompression': bool(use_compression),
        },
    }
    if enabled is not None:
        block['enabled'] = bool(enabled)
    if proxy_type in {'tcp', 'udp'} and remote_port:
        block['remotePort'] = remote_port
    custom_domains = [str(item).strip() for item in (custom_domains or []) if str(item).strip()]
    if proxy_type in {'http', 'https'}:
        if custom_domains:
            block['customDomains'] = custom_domains
        if subdomain:
            block['subdomain'] = subdomain
    definition = {
        'name': name,
        'type': proxy_type,
        proxy_type: block,
    }
    return definition


def _proxy_store_definition_from_model(proxy, enabled=None):
    """处理 FRP 模块的 _proxy_store_definition_from_model 业务步骤。"""
    return _proxy_store_definition(
        proxy.name,
        proxy.proxy_type,
        proxy.local_ip,
        proxy.local_port,
        remote_port=proxy.remote_port,
        custom_domains=proxy.custom_domains,
        subdomain=proxy.subdomain,
        enabled=enabled,
    )


def _agent_fingerprint(server, admin_host, admin_port, admin_proxy_name):
    """处理 FRP 模块的 _agent_fingerprint 业务步骤。"""
    source = f'{server.pk}|{admin_host}|{admin_port}|{admin_proxy_name}'
    return hashlib.sha256(source.encode('utf-8')).hexdigest()


def _update_proxy_from_runtime(agent, item, proxy_type=None):
    """处理 FRP 模块的 _update_proxy_from_runtime 业务步骤。"""
    proxy_type = _proxy_type(item, proxy_type)
    name = _proxy_name(item)
    if not name or _is_admin_proxy(item):
        return None
    local_ip, local_port = _local_endpoint(item, proxy_type)
    _remote_host, remote_port = _remote_endpoint(item, proxy_type, agent.server)
    enabled = _proxy_enabled(item)
    if not enabled:
        status = 'disabled'
    elif _is_running(item.get('status')):
        status = 'available'
    elif item.get('status') is not None:
        status = 'unavailable'
    else:
        status = 'configured'
    last_test_status = 'success' if status == 'available' else ('not_tested' if status == 'configured' else 'failed')
    last_test_message = str(item.get('err') or item.get('error') or '')
    if status == 'disabled' and not last_test_message:
        last_test_message = '宸茬鐢?'
    proxy, _created = models.FrpProxy.objects.update_or_create(
        organization=agent.organization,
        server=agent.server,
        name=name,
        defaults={
            'agent': agent,
            'proxy_type': proxy_type,
            'local_ip': local_ip,
            'local_port': local_port or 0,
            'remote_port': remote_port,
            'status': status,
            'last_test_status': last_test_status,
            'last_test_message': last_test_message[:240],
            'last_test_at': timezone.now(),
        },
    )
    update_proxy_traffic(proxy, item)
    return proxy


def _port_allowed(server, port):
    """处理 FRP 模块的 _port_allowed 业务步骤。"""
    text = str(getattr(server, 'allow_ports', '') or '').strip()
    if not text:
        return True
    for part in text.replace(' ', '').split(','):
        if not part:
            continue
        if '-' in part:
            start, end = part.split('-', 1)
            start_port, end_port = _int_or_none(start), _int_or_none(end)
            if start_port is not None and end_port is not None and start_port <= port <= end_port:
                return True
        elif _int_or_none(part) == port:
            return True
    return False


def _store_proxy_for_model(proxy, rows):
    """处理 FRP 模块的 _store_proxy_for_model 业务步骤。"""
    exact = None
    same_port = []
    for item in rows:
        if _proxy_name(item) == proxy.name:
            exact = item
        _remote_host, remote_port = _remote_endpoint(item, _proxy_type(item, proxy.proxy_type), proxy.server)
        if remote_port and proxy.remote_port and int(remote_port) == int(proxy.remote_port) and _proxy_name(item) != proxy.name:
            same_port.append(item)
    return exact, same_port


def _store_items(agent):
    """处理 FRP 模块的 _store_items 业务步骤。"""
    try:
        payload = frpc_admin_get(agent, '/api/store/proxies')
        return True, _extract_proxy_items(payload)
    except FrpHttpError as exc:
        if exc.status_code == 404:
            return False, []
        raise


def sync_agent_proxies(agent):
    """处理 FRP 模块的 sync_agent_proxies 业务步骤。"""
    if not agent.admin_host or not agent.admin_port:
        raise ValidationError({'detail': '该 frpc 没有管理 API 地址，无法同步端口。'})
    try:
        status_payload = frpc_admin_get(agent, '/api/status')
        store_enabled, store_rows = _store_items(agent)
    except FrpHttpError as exc:
        agent.status = 'unavailable'
        agent.last_error = str(exc)[:240]
        agent.save(update_fields=['status', 'last_error', 'updated_at'])
        raise ValidationError({'detail': str(exc)}) from exc

    rows = _extract_proxy_items(status_payload)
    if store_rows:
        store_by_name = {_proxy_name(item): item for item in store_rows if _proxy_name(item)}
        merged = []
        seen = set()
        for item in rows:
            name = _proxy_name(item)
            merged_item = {**store_by_name.get(name, {}), **item}
            merged.append(merged_item)
            seen.add(name)
        merged.extend(item for name, item in store_by_name.items() if name not in seen)
        rows = merged

    saved = []
    for item in rows:
        proxy = _update_proxy_from_runtime(agent, item)
        if proxy:
            saved.append(proxy)

    now = timezone.now()
    agent.store_enabled = store_enabled
    agent.runtime_proxy_count = len(saved)
    if agent.status != 'disabled':
        agent.status = 'online'
    agent.last_seen_at = now
    agent.last_heartbeat_at = now
    agent.last_error = ''
    agent.save(update_fields=['store_enabled', 'runtime_proxy_count', 'status', 'last_seen_at', 'last_heartbeat_at', 'last_error', 'updated_at'])
    return {'store_enabled': store_enabled, 'proxy_count': len(saved)}


def test_agent_admin_api(agent):
    """处理 FRP 模块的 test_agent_admin_api 业务步骤。"""
    checked_at = timezone.now()
    checked_text = timezone.localtime(checked_at).strftime('%Y-%m-%d %H:%M:%S')
    if agent.status == 'disabled':
        return {'status': 'disabled', 'detail': 'frpc 已禁用，不能执行测试。', 'checked_at': checked_text}
    if not agent.admin_host or not agent.admin_port:
        agent.status = 'unavailable'
        agent.last_error = 'frpc Admin API 地址或端口未配置。'
        agent.save(update_fields=['status', 'last_error', 'updated_at'])
        return {'status': agent.status, 'detail': agent.last_error, 'checked_at': checked_text}
    try:
        status_payload = frpc_admin_get(agent, '/api/status')
        store_enabled, _store_rows = _store_items(agent)
    except (FrpHttpError, ValidationError) as exc:
        agent.status = 'unavailable'
        agent.last_error = str(exc)[:240]
        agent.save(update_fields=['status', 'last_error', 'updated_at'])
        return {'status': agent.status, 'detail': agent.last_error, 'checked_at': checked_text}

    runtime_rows = [item for item in _extract_proxy_items(status_payload) if not _is_admin_proxy(item)]
    agent.store_enabled = store_enabled
    agent.runtime_proxy_count = len(runtime_rows)
    agent.status = 'online'
    agent.last_seen_at = checked_at
    agent.last_heartbeat_at = checked_at
    agent.last_error = ''
    agent.save(update_fields=['store_enabled', 'runtime_proxy_count', 'status', 'last_seen_at', 'last_heartbeat_at', 'last_error', 'updated_at'])
    store_text = '已启用' if store_enabled else '未启用'
    return {
        'status': agent.status,
        'detail': f'frpc Admin API 可访问，当前运行端口 {len(runtime_rows)} 个，Store API {store_text}。',
        'checked_at': checked_text,
        'store_enabled': store_enabled,
        'proxy_count': len(runtime_rows),
    }


def sync_server_runtime(server, request=None):
    """处理 FRP 模块的 sync_server_runtime 业务步骤。"""
    try:
        server_info = frps_dashboard_get(server, '/api/serverinfo')
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc

    allow_ports = str(server_info.get('allowPortsStr') or server_info.get('allow_ports') or '').strip()
    update_fields = ['updated_at']
    if allow_ports and allow_ports != server.allow_ports:
        server.allow_ports = allow_ports
        update_fields.append('allow_ports')
    if server.status != 'disabled':
        server.status = 'available'
        update_fields.append('status')
    server.save(update_fields=update_fields)

    runtime_rows = []
    errors = []
    for proxy_type in FRP_PROXY_TYPES:
        try:
            payload = frps_dashboard_get(server, f'/api/proxy/{proxy_type}')
            for item in _extract_proxy_items(payload, proxy_type):
                item.setdefault('type', proxy_type)
                runtime_rows.append(item)
        except FrpHttpError as exc:
            errors.append(f'{proxy_type}: {exc}')

    now = timezone.now()
    for item in runtime_rows:
        if _is_admin_proxy(item):
            continue
        name = _proxy_name(item)
        if not name:
            continue
        proxy = models.FrpProxy.objects.filter(server=server, name=name).first()
        if proxy:
            update_proxy_traffic(proxy, item, now)

    admin_rows = [item for item in runtime_rows if _is_admin_proxy(item)]
    agents = []
    for item in admin_rows:
        admin_host, admin_port = _remote_endpoint(item, 'tcp', server)
        if not admin_port:
            continue
        name = _proxy_name(item) or f'frpc-admin-{admin_port}'
        fingerprint = _agent_fingerprint(server, admin_host, admin_port, name)
        defaults = {
            'agent_id': fingerprint[:16],
            'hostname': f'frpc-{admin_port}',
            'source': 'frps_dashboard',
            'admin_host': admin_host,
            'admin_port': admin_port,
            'admin_proxy_name': name,
            'admin_proxy_remote_addr': item.get('remote_addr') or item.get('remoteAddr') or f'{admin_host}:{admin_port}',
            'approval_status': 'approved',
            'status': 'online' if _is_running(item.get('status')) else 'unavailable',
            'last_seen_at': now,
            'last_heartbeat_at': now,
            'last_error': '',
            'metadata': {'dashboard_proxy': item, 'server_info': server_info},
        }
        agent, _created = models.FrpAgent.objects.update_or_create(
            organization=server.organization,
            server=server,
            fingerprint=fingerprint,
            defaults=defaults,
        )
        try:
            sync_agent_proxies(agent)
        except ValidationError as exc:
            detail = getattr(exc, 'detail', None) or str(exc)
            errors.append(f'{agent.hostname}: {detail}')
        agents.append(agent)

    return {
        'server_version': server_info.get('version') or server_info.get('serverVersion') or '',
        'allow_ports': server.allow_ports,
        'discovered_agents': len(agents),
        'dashboard_proxy_count': len(runtime_rows),
        'errors': errors[:8],
    }


def add_proxy_to_agent(agent, payload):
    """处理 FRP 模块的 add_proxy_to_agent 业务步骤。"""
    if agent.approval_status != 'approved':
        raise ValidationError({'detail': '该 frpc 未通过准入，不能新增端口。'})
    if agent.status == 'disabled':
        raise ValidationError({'detail': '该 frpc 已禁用，不能新增端口。'})
    if not agent.admin_host or not agent.admin_port:
        raise ValidationError({'detail': '该 frpc 没有管理 API 地址，无法下发端口。'})

    try:
        store_enabled, _rows = _store_items(agent)
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc
    if not store_enabled:
        raise ValidationError({'detail': '该 frpc 未启用 Store API，请在 frpc.toml 配置 [store].path 后重启。'})

    name = str(payload.get('name') or '').strip()
    proxy_type = str(payload.get('proxy_type') or payload.get('type') or 'tcp').strip().lower()
    local_ip = str(payload.get('local_ip') or '127.0.0.1').strip()
    local_port = _int_or_none(payload.get('local_port'))
    remote_port = _int_or_none(payload.get('remote_port'))
    if not name:
        raise ValidationError({'name': '请填写端口名称。'})
    if proxy_type not in {'tcp', 'udp'}:
        raise ValidationError({'proxy_type': '当前新增端口先支持 TCP/UDP。'})
    if not local_port or not 1 <= local_port <= 65535:
        raise ValidationError({'local_port': '本地端口必须在 1-65535 之间。'})
    if not remote_port or not 1 <= remote_port <= 65535:
        raise ValidationError({'remote_port': '远端端口必须在 1-65535 之间。'})
    if not _port_allowed(agent.server, remote_port):
        raise ValidationError({'remote_port': f'远端端口 {remote_port} 不在服务端允许范围 {agent.server.allow_ports} 内。'})
    if models.FrpProxy.objects.filter(organization=agent.organization, server=agent.server, name=name).exclude(agent=agent).exists():
        raise ValidationError({'name': '该端口名称已被其他 frpc 使用。'})
    if models.FrpProxy.objects.filter(organization=agent.organization, server=agent.server, remote_port=remote_port).exclude(name=name).exists():
        raise ValidationError({'remote_port': '该远端端口已被占用。'})

    definition = _proxy_store_definition(
        name,
        proxy_type,
        local_ip,
        local_port,
        remote_port=remote_port,
        use_encryption=payload.get('use_encryption', True),
        use_compression=payload.get('use_compression', True),
        enabled=True,
    )
    try:
        result = frpc_admin_post(agent, '/api/store/proxies', definition)
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc

    try:
        _verified_store_enabled, verified_rows = _store_items(agent)
    except FrpHttpError as exc:
        raise ValidationError({'detail': f'frpc 已返回新增结果，但二次读取 Store 失败：{exc}'}) from exc
    if not any(_proxy_name(item) == name for item in verified_rows):
        raise ValidationError({'detail': f'frpc API 已返回新增结果，但 Store 里没有代理 {name}，平台不会写入本地记录。请检查 frpc store 配置和版本。'})

    proxy, _created = models.FrpProxy.objects.update_or_create(
        organization=agent.organization,
        server=agent.server,
        name=name,
        defaults={
            'agent': agent,
            'proxy_type': proxy_type,
            'local_ip': local_ip,
            'local_port': local_port,
            'remote_port': remote_port,
            'status': 'configured',
            'remark': str(payload.get('remark') or '').strip(),
        },
    )
    try:
        sync_agent_proxies(agent)
    except ValidationError:
        pass
    return proxy, result


def toggle_proxy_enabled(proxy, enabled):
    """处理 FRP 模块的 toggle_proxy_enabled 业务步骤。"""
    agent = proxy.agent
    if agent.approval_status != 'approved':
        raise ValidationError({'detail': '\u8be5 frpc \u672a\u901a\u8fc7\u5ba1\u6838\uff0c\u4e0d\u80fd\u64cd\u4f5c\u7aef\u53e3\u3002'})
    if not agent.admin_host or not agent.admin_port:
        raise ValidationError({'detail': '\u8be5 frpc \u6ca1\u6709\u7ba1\u7406 API \u5730\u5740\uff0c\u65e0\u6cd5\u64cd\u4f5c\u7aef\u53e3\u3002'})

    try:
        store_enabled, store_rows = _store_items(agent)
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc
    if not store_enabled:
        raise ValidationError({'detail': '\u8be5 frpc \u672a\u542f\u7528 Store API\uff0c\u8bf7\u5728 frpc.toml \u914d\u7f6e [store].path \u540e\u91cd\u8bd5\u3002'})
    exact_store_proxy, same_port_rows = _store_proxy_for_model(proxy, store_rows)
    if exact_store_proxy is None:
        if same_port_rows:
            names = ', '.join(_proxy_name(item) for item in same_port_rows if _proxy_name(item))
            raise ValidationError({'detail': f'frpc Store \u91cc\u4e0d\u5b58\u5728\u4ee3\u7406 {proxy.name}\uff0c\u8fdc\u7aef\u7aef\u53e3 {proxy.remote_port} \u5b9e\u9645\u7531 {names} \u5360\u7528\u3002\u8bf7\u5148\u540c\u6b65\u7aef\u53e3\uff0c\u518d\u7981\u7528\u771f\u6b63\u8fd0\u884c\u7684\u90a3\u6761\u8bb0\u5f55\u3002'})
        action_text = '\u542f\u7528' if enabled else '\u7981\u7528'
        raise ValidationError({'detail': f'frpc Store \u91cc\u4e0d\u5b58\u5728\u4ee3\u7406 {proxy.name}\uff0c\u65e0\u6cd5\u4e0b\u53d1{action_text}\u3002\u8bf7\u5148\u540c\u6b65\u7aef\u53e3\u540e\u518d\u64cd\u4f5c\u3002'})

    definition = _proxy_store_definition_from_model(proxy, enabled=enabled)
    try:
        proxy_name = urllib.parse.quote(proxy.name, safe='')
        result = frpc_admin_put(agent, f'/api/store/proxies/{proxy_name}', definition)
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc

    try:
        sync_result = sync_agent_proxies(agent)
        proxy.refresh_from_db()
    except ValidationError:
        proxy.status = 'disabled' if not enabled else 'configured'
        proxy.save(update_fields=['status', 'updated_at'])
        sync_result = {'store_enabled': store_enabled, 'proxy_count': None}

    return proxy, {'frpc_result': result, 'sync_result': sync_result}


def delete_proxy_from_agent(proxy):
    """处理 FRP 模块的 delete_proxy_from_agent 业务步骤。"""
    agent = proxy.agent
    if agent.approval_status != 'approved':
        raise ValidationError({'detail': '\u8be5 frpc \u672a\u901a\u8fc7\u5ba1\u6838\uff0c\u4e0d\u80fd\u5220\u9664\u7aef\u53e3\u3002'})
    if not agent.admin_host or not agent.admin_port:
        raise ValidationError({'detail': '\u8be5 frpc \u6ca1\u6709\u7ba1\u7406 API \u5730\u5740\uff0c\u65e0\u6cd5\u5220\u9664\u7aef\u53e3\u3002'})

    try:
        store_enabled, store_rows = _store_items(agent)
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc
    if not store_enabled:
        raise ValidationError({'detail': '\u8be5 frpc \u672a\u542f\u7528 Store API\uff0c\u8bf7\u5728 frpc.toml \u914d\u7f6e [store].path \u540e\u91cd\u8bd5\u3002'})

    exact_store_proxy, same_port_rows = _store_proxy_for_model(proxy, store_rows)
    if exact_store_proxy is None:
        if same_port_rows:
            names = ', '.join(_proxy_name(item) for item in same_port_rows if _proxy_name(item))
            raise ValidationError({'detail': f'frpc Store \u91cc\u4e0d\u5b58\u5728\u4ee3\u7406 {proxy.name}\uff0c\u8fdc\u7aef\u7aef\u53e3 {proxy.remote_port} \u5b9e\u9645\u7531 {names} \u5360\u7528\u3002\u8bf7\u5148\u540c\u6b65\u7aef\u53e3\uff0c\u518d\u5220\u9664\u771f\u6b63\u8fd0\u884c\u7684\u90a3\u6761\u8bb0\u5f55\u3002'})
        return {
            'frpc_result': {'detail': 'remote proxy already missing'},
            'sync_result': {'store_enabled': store_enabled, 'proxy_count': None},
            'remote_deleted': False,
        }

    try:
        proxy_name = urllib.parse.quote(proxy.name, safe='')
        result = frpc_admin_delete(agent, f'/api/store/proxies/{proxy_name}')
    except FrpHttpError as exc:
        raise ValidationError({'detail': str(exc)}) from exc

    try:
        sync_result = sync_agent_proxies(agent)
    except ValidationError:
        sync_result = {'store_enabled': store_enabled, 'proxy_count': None}

    return {'frpc_result': result, 'sync_result': sync_result, 'remote_deleted': True}


def authenticate_server_token(server, request):
    """处理 FRP 模块的 authenticate_server_token 业务步骤。"""
    provided = (
        request.headers.get('X-FRP-Token') or
        request.headers.get('X-Frp-Token') or
        request.data.get('token') or
        ''
    )
    auth = request.headers.get('Authorization', '')
    if auth.lower().startswith('bearer '):
        provided = auth.split(' ', 1)[1].strip()
    expected = decrypt(server.encrypted_auth_token)
    if not expected:
        raise ValidationError({'detail': 'FRP 服务端未配置注册 Token，拒绝 Agent 注册。'})
    if provided != expected:
        raise ValidationError({'detail': 'FRP 注册 Token 校验失败。'})


def find_server_for_machine(payload):
    """处理 FRP 模块的 find_server_for_machine 业务步骤。"""
    code = str(payload.get('server_code') or '').strip()
    if not code:
        raise ValidationError({'server_code': '请提供 FRP 服务端编码。'})
    server = models.FrpServer.objects.select_related('organization').filter(server_code=code).first()
    if not server:
        raise ValidationError({'server_code': 'FRP 服务端不存在。'})
    if server.status == 'disabled':
        raise ValidationError({'detail': 'FRP 服务端已禁用，拒绝 Agent 接入。'})
    return server


def normalize_tags(value):
    """处理 FRP 模块的 normalize_tags 业务步骤。"""
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(',') if item.strip()]
    return []


def register_agent(request):
    """处理 FRP 模块的 register_agent 业务步骤。"""
    server = find_server_for_machine(request.data)
    authenticate_server_token(server, request)
    if not server.allow_register:
        raise ValidationError({'detail': '该 FRP 服务端暂未开放 Agent 注册。'})

    payload = request.data
    hostname = str(payload.get('hostname') or '').strip()
    fingerprint = str(payload.get('fingerprint') or '').strip() or models.FrpAgent.build_fingerprint(hostname)
    agent_id = str(payload.get('agent_id') or fingerprint[:16]).strip()
    if not hostname and not str(payload.get('fingerprint') or '').strip():
        raise ValidationError({'detail': 'Agent 至少需要上报主机名或指纹。'})

    agent_count = models.FrpAgent.objects.filter(server=server).count()
    existing = models.FrpAgent.objects.filter(organization=server.organization, server=server, fingerprint=fingerprint).first()
    if not existing and agent_count >= server.max_agents:
        raise ValidationError({'detail': f'该 FRP 服务端最多接入 {server.max_agents} 台 Agent。'})

    now = timezone.now()
    defaults = {
        'agent_id': agent_id,
        'hostname': hostname,
        'client_ip': request_ip(request),
        'tags': normalize_tags(payload.get('tags')),
        'metadata': payload.get('metadata') if isinstance(payload.get('metadata'), dict) else {},
        'last_seen_at': now,
        'last_heartbeat_at': now,
        'last_error': '',
    }
    if existing:
        for key, value in defaults.items():
            setattr(existing, key, value)
        if existing.status != 'disabled':
            existing.status = 'online'
        existing.save()
        created = False
        agent = existing
    else:
        agent = models.FrpAgent.objects.create(
            organization=server.organization,
            server=server,
            fingerprint=fingerprint,
            approval_status='pending',
            status='online',
            **defaults,
        )
        created = True

    models.FrpAgentHeartbeat.objects.create(
        organization=server.organization,
        server=server,
        agent=agent,
        status='online',
        ip_address=request_ip(request),
        message='Agent 注册上报' if created else 'Agent 信息刷新',
        metrics=payload.get('metrics') if isinstance(payload.get('metrics'), dict) else {},
        reported_at=now,
    )
    return agent, created


def heartbeat_agent(request):
    """处理 FRP 模块的 heartbeat_agent 业务步骤。"""
    server = find_server_for_machine(request.data)
    authenticate_server_token(server, request)
    fingerprint = str(request.data.get('fingerprint') or '').strip()
    agent_id = str(request.data.get('agent_id') or '').strip()
    queryset = models.FrpAgent.objects.filter(organization=server.organization, server=server)
    agent = queryset.filter(fingerprint=fingerprint).first() if fingerprint else None
    if not agent and agent_id:
        agent = queryset.filter(agent_id=agent_id).first()
    if not agent:
        raise ValidationError({'detail': 'Agent 未注册，请先完成注册。'})

    status = str(request.data.get('status') or 'online').strip()
    normalized = 'error' if status in {'error', 'unavailable'} else ('offline' if status == 'offline' else 'online')
    now = timezone.now()
    if agent.status != 'disabled':
        agent.status = 'unavailable' if normalized == 'error' else normalized
    agent.last_heartbeat_at = now
    agent.last_seen_at = now
    agent.client_ip = request_ip(request)
    agent.last_error = str(request.data.get('message') or request.data.get('error') or '')[:240]
    agent.save(update_fields=['status', 'last_heartbeat_at', 'last_seen_at', 'client_ip', 'last_error', 'updated_at'])
    heartbeat = models.FrpAgentHeartbeat.objects.create(
        organization=server.organization,
        server=server,
        agent=agent,
        status=normalized,
        ip_address=request_ip(request),
        message=agent.last_error,
        metrics=request.data.get('metrics') if isinstance(request.data.get('metrics'), dict) else {},
        reported_at=now,
    )
    return agent, heartbeat


def agent_config(request):
    """处理 FRP 模块的 agent_config 业务步骤。"""
    server = find_server_for_machine(request.data)
    authenticate_server_token(server, request)
    fingerprint = str(request.data.get('fingerprint') or '').strip()
    agent_id = str(request.data.get('agent_id') or '').strip()
    queryset = models.FrpAgent.objects.filter(organization=server.organization, server=server)
    agent = queryset.filter(fingerprint=fingerprint).first() if fingerprint else None
    if not agent and agent_id:
        agent = queryset.filter(agent_id=agent_id).first()
    if not agent:
        raise ValidationError({'detail': 'Agent 未注册，请先完成注册。'})
    if agent.approval_status != 'approved':
        raise ValidationError({'detail': 'Agent 尚未审核通过，暂不下发 FRP 配置。'})
    if agent.status == 'disabled':
        raise ValidationError({'detail': 'Agent 已禁用，暂不下发 FRP 配置。'})
    proxies = agent.proxies.exclude(status='disabled').select_related('server')
    return agent, proxies
