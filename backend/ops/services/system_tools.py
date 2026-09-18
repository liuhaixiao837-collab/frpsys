import ipaddress
import locale
import platform
import queue
import socket
import subprocess
import threading
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from icmplib import traceroute as icmp_traceroute
from icmplib.exceptions import ICMPLibError, SocketPermissionError

from django.core.exceptions import ValidationError
from django.core.validators import validate_ipv46_address


MAX_OUTPUT_LENGTH = 16000
CURL_PREVIEW_BYTES = 64 * 1024


def normalize_target(value):
    """校验并规范化 IP 地址或 DNS 主机名，禁止向系统命令传入选项。

    参数：`value` 为用户提交的 IP 地址或主机名。
    返回：规范化后的 IP 地址或 ASCII DNS 主机名。
    副作用：不访问网络，不修改文件或数据库。
    """
    target = str(value or '').strip().rstrip('.')
    if not target or len(target) > 253:
        raise ValueError('请输入有效的 IP 地址或主机名')
    try:
        validate_ipv46_address(target)
        return target
    except ValidationError:
        pass
    try:
        ascii_target = target.encode('idna').decode('ascii').lower()
    except UnicodeError as exc:
        raise ValueError('主机名格式不正确') from exc
    labels = ascii_target.split('.')
    if any(
        not label
        or len(label) > 63
        or label.startswith('-')
        or label.endswith('-')
        or not all(character.isalnum() or character == '-' for character in label)
        for label in labels
    ):
        raise ValueError('主机名格式不正确')
    return ascii_target


def resolve_target(target, port=0, socket_type=socket.SOCK_STREAM):
    """解析目标地址并过滤不可路由的未指定地址和组播地址。

    参数：`target` 为已规范化目标；`port` 为可选端口；`socket_type` 为套接字类型。
    返回：去重后的地址解析记录列表。
    副作用：调用系统 DNS 解析服务，不修改持久化数据。
    """
    try:
        records = socket.getaddrinfo(target, port, type=socket_type)
    except socket.gaierror as exc:
        raise ValueError('目标地址无法解析，请检查 IP 或主机名') from exc
    resolved = []
    seen = set()
    for family, kind, protocol, canonical_name, sockaddr in records:
        address = sockaddr[0]
        parsed = ipaddress.ip_address(address)
        if parsed.is_unspecified or parsed.is_multicast:
            continue
        key = (family, address)
        if key not in seen:
            seen.add(key)
            resolved.append((family, kind, protocol, sockaddr, address))
    if not resolved:
        raise ValueError('目标地址不可用于网络诊断')
    return resolved


def _decode_output(value):
    """按系统首选编码解码诊断输出，并限制返回的字符数量。

    参数：`value` 为系统命令输出的字节串。
    返回：解码、截断并去除首尾空白后的文字。
    副作用：不修改文件或数据库。
    """
    encoding = locale.getpreferredencoding(False) or 'utf-8'
    return (value or b'').decode(encoding, errors='replace')[-MAX_OUTPUT_LENGTH:].strip()


def run_ping(target, count=4, timeout_seconds=2):
    """以参数数组执行系统 Ping，不经过 shell，并返回结构化结果。

    参数：`target` 为目标地址；`count` 为探测次数；`timeout_seconds` 为单次超时秒数。
    返回：包含目标、解析地址、耗时、结果和受限输出的字典。
    副作用：解析目标并启动本机 Ping 子进程，不写入文件或数据库。
    """
    target = normalize_target(target)
    resolved = resolve_target(target, socket_type=socket.SOCK_DGRAM)
    address = resolved[0][4]
    count = max(1, min(int(count), 5))
    timeout_seconds = max(1, min(int(timeout_seconds), 5))
    if platform.system().lower() == 'windows':
        command = ['ping', '-n', str(count), '-w', str(timeout_seconds * 1000), address]
    else:
        command = ['ping', '-c', str(count), '-W', str(timeout_seconds), address]
    started = time.perf_counter()
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=count * timeout_seconds + 5,
            check=False,
            shell=False,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
        )
        output = _decode_output(completed.stdout or completed.stderr)
        success = completed.returncode == 0
        detail = '目标主机响应正常' if success else '未收到目标主机的有效响应'
    except FileNotFoundError:
        success = False
        output = ''
        detail = '当前服务器未安装 Ping 工具'
    except subprocess.TimeoutExpired as exc:
        success = False
        output = _decode_output(exc.stdout or exc.stderr)
        detail = 'Ping 检测超时'
    return {
        'tool': 'ping',
        'target': target,
        'resolved_address': address,
        'success': success,
        'duration_ms': round((time.perf_counter() - started) * 1000),
        'detail': detail,
        'output': output,
    }


def run_telnet(target, port, timeout_seconds=5):
    """使用 TCP 握手检测目标端口，不读取目标服务返回的数据。

    参数：`target` 为目标地址；`port` 为 TCP 端口；`timeout_seconds` 为连接超时秒数。
    返回：包含目标、端口、耗时和连通结果的字典。
    副作用：解析目标并建立短时 TCP 连接，不写入文件或数据库。
    """
    target = normalize_target(target)
    port = int(port)
    if port < 1 or port > 65535:
        raise ValueError('端口必须在 1-65535 之间')
    timeout_seconds = max(1, min(int(timeout_seconds), 10))
    records = resolve_target(target, port=port)
    started = time.perf_counter()
    last_error = None
    for family, kind, protocol, sockaddr, address in records:
        connection = socket.socket(family, kind, protocol)
        connection.settimeout(timeout_seconds)
        try:
            connection.connect(sockaddr)
            return {
                'tool': 'telnet',
                'target': target,
                'resolved_address': address,
                'port': port,
                'success': True,
                'duration_ms': round((time.perf_counter() - started) * 1000),
                'detail': '目标 TCP 端口已开放',
            }
        except OSError as exc:
            last_error = exc
        finally:
            connection.close()
    return {
        'tool': 'telnet',
        'target': target,
        'resolved_address': records[0][4],
        'port': port,
        'success': False,
        'duration_ms': round((time.perf_counter() - started) * 1000),
        'detail': '目标 TCP 端口未开放或被网络策略拦截',
        'error_code': getattr(last_error, 'errno', None),
    }


def _traceroute_command(target, max_hops=20, timeout_seconds=2):
    """校验路由追踪参数并生成不经过 shell 的系统命令。

    参数：`target` 为目标；`max_hops` 为最大跳数；`timeout_seconds` 为单跳超时秒数。
    返回：规范化目标、解析地址、参数数组和整体截止秒数。
    副作用：解析目标地址，不启动命令或修改持久化数据。
    """
    target = normalize_target(target)
    resolved = resolve_target(target, socket_type=socket.SOCK_DGRAM)
    address = resolved[0][4]
    max_hops = max(1, min(int(max_hops), 30))
    timeout_seconds = max(1, min(int(timeout_seconds), 5))
    is_windows = platform.system().lower() == 'windows'
    command = (
        ['tracert', '-d', '-h', str(max_hops), '-w', str(timeout_seconds * 1000), address]
        if is_windows
        else ['traceroute', '-n', '-m', str(max_hops), '-w', str(timeout_seconds), address]
    )
    return target, address, command, max_hops * timeout_seconds + 10


def stream_traceroute(target, max_hops=20, timeout_seconds=2):
    """逐行执行系统路由追踪并返回开始、输出和完成事件。

    参数：`target` 为目标；`max_hops` 为最大跳数；`timeout_seconds` 为单跳超时秒数。
    返回：按顺序产生 SSE 事件名和载荷的生成器。
    副作用：启动并在超时、完成或调用方关闭时终止本机路由追踪子进程。
    """
    target, address, command, deadline_seconds = _traceroute_command(target, max_hops, timeout_seconds)

    def event_iterator():
        """消费子进程输出队列，并在超时或断开时可靠结束进程。

        参数：无。
        返回：按执行阶段产生诊断事件。
        副作用：启动后台读线程和路由追踪子进程，并负责回收进程。
        """
        started = time.perf_counter()
        process = None
        output_queue = queue.Queue()
        chunks = []
        output_length = 0
        timed_out = False
        success = False
        detail = '路由追踪未完整到达目标'
        yield 'start', {
            'tool': 'traceroute', 'target': target, 'resolved_address': address,
            'success': False, 'duration_ms': 0, 'detail': '正在追踪路由', 'output': '',
        }
        try:
            process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=0,
                shell=False,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0),
            )

            def read_output():
                """在后台读取管道，避免无输出时阻塞超时判断。

                参数：无。
                返回：无显式返回值。
                副作用：持续读取子进程标准输出，并向线程安全队列写入事件。
                """
                try:
                    for raw_line in iter(process.stdout.readline, b''):
                        output_queue.put(('line', raw_line))
                finally:
                    output_queue.put(('eof', b''))

            reader = threading.Thread(target=read_output, daemon=True)
            reader.start()
            deadline = time.monotonic() + deadline_seconds
            reached_eof = False
            while not reached_eof:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    timed_out = True
                    break
                try:
                    item_type, raw_line = output_queue.get(timeout=min(0.25, remaining))
                except queue.Empty:
                    continue
                if item_type == 'eof':
                    reached_eof = True
                    continue
                line = _decode_output(raw_line)
                if not line:
                    continue
                line = f'{line}\n'
                chunks.append(line)
                output_length += len(line)
                while output_length > MAX_OUTPUT_LENGTH and chunks:
                    output_length -= len(chunks.pop(0))
                yield 'output', {'text': line}

            if timed_out and process.poll() is None:
                process.terminate()
            try:
                return_code = process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()
                return_code = process.wait(timeout=2)
            success = not timed_out and return_code == 0
            detail = (
                '路由追踪超时，已返回当前可用结果'
                if timed_out
                else ('路由追踪已完成' if success else '路由追踪未完整到达目标')
            )
        except FileNotFoundError:
            detail = '当前服务器未安装 Traceroute 工具'
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
        yield 'done', {
            'tool': 'traceroute', 'target': target, 'resolved_address': address,
            'success': success,
            'duration_ms': round((time.perf_counter() - started) * 1000),
            'detail': detail,
            'output': ''.join(chunks)[-MAX_OUTPUT_LENGTH:].strip(),
        }

    return event_iterator()


def run_traceroute(target, max_hops=20, timeout_seconds=2):
    """兼容非流式调用，消费路由追踪事件并返回最终结果。

    参数：`target` 为目标；`max_hops` 为最大跳数；`timeout_seconds` 为单跳超时秒数。
    返回：路由追踪完成事件的结构化载荷。
    副作用：启动并回收本机路由追踪子进程。
    """
    final_result = None
    for event, payload in stream_traceroute(target, max_hops=max_hops, timeout_seconds=timeout_seconds):
        if event == 'done':
            final_result = payload
    return final_result


def run_mtr(target, count=3, max_hops=20, timeout_seconds=2):
    """使用 Python ICMP 探测实现 MTR 风格的逐跳质量统计。

    参数：`target` 为目标；`count` 为每跳探测次数；`max_hops` 为最大跳数；
    `timeout_seconds` 为单次探测超时秒数。
    返回：包含逐跳丢包率和延迟的结构化诊断结果。
    副作用：解析目标并通过 ICMP 原始套接字发送网络探测，不修改文件或数据库。
    """
    target = normalize_target(target)
    resolved = resolve_target(target, socket_type=socket.SOCK_DGRAM)
    address = resolved[0][4]
    count = max(1, min(int(count), 10))
    max_hops = max(1, min(int(max_hops), 30))
    timeout_seconds = max(1, min(int(timeout_seconds), 5))
    started = time.perf_counter()
    try:
        hops = icmp_traceroute(
            address, count=count, timeout=timeout_seconds, max_hops=max_hops, fast=False,
        )
    except (SocketPermissionError, PermissionError) as exc:
        raise ValueError('当前服务账号没有 ICMP 原始套接字权限，请以管理员权限运行平台服务') from exc
    except ICMPLibError as exc:
        raise ValueError(f'MTR 探测失败：{exc}') from exc

    rows = ['跳数  地址                                      丢包率   已发/已收   最小/平均/最大延迟(ms)']
    hop_items = []
    hop_by_distance = {hop.distance: hop for hop in hops}
    reached_target = bool(hops) and hops[-1].address == address
    final_distance = hops[-1].distance if reached_target else max_hops
    for distance in range(1, final_distance + 1):
        hop = hop_by_distance.get(distance)
        item = ({
            'hop': distance, 'address': '*', 'packet_loss': 100.0,
            'packets_sent': count, 'packets_received': 0,
            'min_rtt': 0.0, 'avg_rtt': 0.0, 'max_rtt': 0.0,
        } if hop is None else {
            'hop': hop.distance, 'address': hop.address,
            'packet_loss': round(hop.packet_loss * 100, 1),
            'packets_sent': hop.packets_sent, 'packets_received': hop.packets_received,
            'min_rtt': round(hop.min_rtt, 2), 'avg_rtt': round(hop.avg_rtt, 2),
            'max_rtt': round(hop.max_rtt, 2),
        })
        hop_items.append(item)
        rows.append(
            f"{item['hop']:>4}  {item['address']:<39} {item['packet_loss']:>6.1f}%   "
            f"{item['packets_sent']:>2}/{item['packets_received']:<2}       "
            f"{item['min_rtt']:>7.2f}/{item['avg_rtt']:>7.2f}/{item['max_rtt']:>7.2f}"
        )
    success = reached_target
    return {
        'tool': 'mtr', 'target': target, 'resolved_address': address, 'success': success,
        'duration_ms': round((time.perf_counter() - started) * 1000),
        'detail': 'MTR 链路质量探测已完成' if success else 'MTR 已返回当前可达链路结果',
        'output': '\n'.join(rows), 'hops': hop_items,
    }


def normalize_curl_url(value):
    """校验 Curl URL，并生成不含查询参数和片段的审计展示地址。

    参数：`value` 为用户提交的 HTTP 或 HTTPS 地址。
    返回：实际请求地址和移除查询参数后的安全审计地址。
    副作用：不访问网络，不修改文件或数据库。
    """
    url = str(value or '').strip()
    if not url or len(url) > 2048:
        raise ValueError('请输入有效的 HTTP 或 HTTPS 地址')
    parsed = urlsplit(url)
    if parsed.scheme.lower() not in {'http', 'https'} or not parsed.hostname:
        raise ValueError('Curl 仅支持 HTTP 和 HTTPS 地址')
    if parsed.username is not None or parsed.password is not None:
        raise ValueError('Curl 地址不允许包含用户名或密码')
    try:
        port = parsed.port
    except ValueError as exc:
        raise ValueError('Curl 地址端口格式不正确') from exc
    host = normalize_target(parsed.hostname)
    display_host = f'[{host}]' if ':' in host else host
    netloc = f'{display_host}:{port}' if port is not None else display_host
    path = parsed.path or '/'
    safe_url = urlunsplit((parsed.scheme.lower(), netloc, path, '', ''))
    request_url = urlunsplit((parsed.scheme.lower(), netloc, path, parsed.query, ''))
    return request_url, safe_url


def run_curl(url, method='GET', timeout_seconds=10):
    """在内存读取受限 HTTP 响应预览，禁止重定向且不创建文件。

    参数：`url` 为 HTTP(S) 地址；`method` 仅允许 GET 或 HEAD；`timeout_seconds` 为超时秒数。
    返回：包含状态码、内容类型、耗时和受限正文预览的诊断结果。
    副作用：向目标发起一次不使用环境代理的 HTTPS 校验请求，不写入文件或数据库。
    """
    request_url, safe_url = normalize_curl_url(url)
    method = str(method or 'GET').upper()
    if method not in {'GET', 'HEAD'}:
        raise ValueError('Curl 仅支持 GET 和 HEAD 方法')
    timeout_seconds = max(1, min(int(timeout_seconds), 30))
    started = time.perf_counter()
    session = requests.Session()
    session.trust_env = False
    response = None
    try:
        response = session.request(
            method, request_url, timeout=timeout_seconds, stream=True,
            allow_redirects=False, verify=True,
            headers={'User-Agent': 'Platform-System-Tools/1.0', 'Accept': '*/*'},
        )
        preview = bytearray()
        truncated = False
        if method != 'HEAD':
            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue
                remaining = CURL_PREVIEW_BYTES + 1 - len(preview)
                preview.extend(chunk[:remaining])
                if len(preview) > CURL_PREVIEW_BYTES:
                    truncated = True
                    break
            if truncated:
                del preview[CURL_PREVIEW_BYTES:]
        content_type = (response.headers.get('Content-Type') or '').strip()
        media_type = content_type.split(';', 1)[0].lower()
        is_text = media_type.startswith('text/') or any(
            marker in media_type for marker in ('json', 'xml', 'javascript', 'x-www-form-urlencoded')
        )
        body_preview = (
            bytes(preview).decode(response.encoding or 'utf-8', errors='replace')
            if preview and is_text else ''
        )
        lines = [
            f'HTTP {response.status_code} {response.reason or ""}'.rstrip(),
            f'Content-Type: {content_type or "未提供"}',
            f'已读取响应: {len(preview)} 字节' + ('（预览已截断）' if truncated else ''),
        ]
        if response.headers.get('Location'):
            try:
                location = normalize_curl_url(response.headers['Location'])[1]
            except ValueError:
                location = '目标返回了不可展示的跳转地址'
            lines.append(f'Location: {location}')
        if body_preview:
            lines.extend(['', body_preview])
        elif preview:
            lines.extend(['', '响应为二进制内容，未显示正文预览。'])
        return {
            'tool': 'curl', 'target': safe_url, 'resolved_address': '',
            'success': response.ok,
            'duration_ms': round((time.perf_counter() - started) * 1000),
            'detail': f'HTTP 请求已完成，状态码 {response.status_code}',
            'output': '\n'.join(lines)[-MAX_OUTPUT_LENGTH:],
            'status_code': response.status_code, 'content_type': content_type,
            'bytes_read': len(preview), 'truncated': truncated,
        }
    except requests.RequestException as exc:
        return {
            'tool': 'curl', 'target': safe_url, 'resolved_address': '', 'success': False,
            'duration_ms': round((time.perf_counter() - started) * 1000),
            'detail': f'HTTP 请求失败：{exc}', 'output': '',
        }
    finally:
        if response is not None:
            response.close()
        session.close()

