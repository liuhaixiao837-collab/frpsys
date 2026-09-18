from django.test import RequestFactory, SimpleTestCase, override_settings

from ops.services.client_ip import request_client_ip, scope_client_ip


@override_settings(TRUSTED_PROXY_IPS=['127.0.0.1/32', '::1/128'])
class ClientIpTests(SimpleTestCase):
    """验证真实客户端 IP 解析和代理头防伪造边界。"""

    def setUp(self):
        """创建用于构造 HTTP 请求的测试工厂。"""
        self.factory = RequestFactory()

    def test_trusted_vite_proxy_returns_forwarded_lan_client(self):
        """本机 Vite 代理转发时应取得局域网浏览器真实地址。"""
        request = self.factory.get(
            '/api/v1/me',
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='192.168.3.167',
        )

        self.assertEqual(request_client_ip(request), '192.168.3.167')

    def test_ipv4_mapped_ipv6_is_normalized_before_matching(self):
        """Windows 和 Node 常见的 IPv4 映射 IPv6 必须还原为 IPv4。"""
        request = self.factory.get(
            '/api/v1/me',
            REMOTE_ADDR='::ffff:127.0.0.1',
            HTTP_X_FORWARDED_FOR='::ffff:192.168.3.167',
        )

        self.assertEqual(request_client_ip(request), '192.168.3.167')

    def test_untrusted_direct_client_cannot_spoof_forwarded_header(self):
        """直接连接后端的普通客户端不能使用转发头冒充其他 IP。"""
        request = self.factory.get(
            '/api/v1/me',
            REMOTE_ADDR='192.168.3.167',
            HTTP_X_FORWARDED_FOR='10.10.10.10',
        )

        self.assertEqual(request_client_ip(request), '192.168.3.167')

    @override_settings(TRUSTED_PROXY_IPS=['127.0.0.1/32', '10.0.0.0/8'])
    def test_proxy_chain_uses_nearest_untrusted_client(self):
        """多级可信代理链应跳过右侧代理并返回真实客户端。"""
        request = self.factory.get(
            '/api/v1/me',
            REMOTE_ADDR='127.0.0.1',
            HTTP_X_FORWARDED_FOR='198.51.100.8, 10.0.0.9',
        )

        self.assertEqual(request_client_ip(request), '198.51.100.8')

    def test_websocket_scope_uses_same_trusted_proxy_rules(self):
        """WebSocket 连接必须与 HTTP 请求使用相同真实 IP 结果。"""
        scope = {
            'client': ('127.0.0.1', 51000),
            'headers': [(b'x-forwarded-for', b'192.168.3.167')],
        }

        self.assertEqual(scope_client_ip(scope), '192.168.3.167')
