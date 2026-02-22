"""IP 地址工具测试

测试 IP 提取和 IP/CIDR 匹配功能
"""

import pytest

from yweb.utils.ip import get_client_ip, get_client_ip_from_scope, ip_in_list


class TestIpInList:
    """ip_in_list 函数测试"""

    def test_single_ip_match(self):
        """测试单 IP 精确匹配"""
        assert ip_in_list("192.168.1.100", ["192.168.1.100"]) is True

    def test_single_ip_no_match(self):
        """测试单 IP 不匹配"""
        assert ip_in_list("192.168.1.101", ["192.168.1.100"]) is False

    def test_cidr_match(self):
        """测试 CIDR 网段匹配"""
        assert ip_in_list("192.168.1.50", ["192.168.0.0/16"]) is True
        assert ip_in_list("192.168.255.255", ["192.168.0.0/16"]) is True

    def test_cidr_no_match(self):
        """测试 CIDR 网段不匹配"""
        assert ip_in_list("10.0.0.1", ["192.168.0.0/16"]) is False

    def test_cidr_24_subnet(self):
        """测试 /24 子网匹配"""
        assert ip_in_list("10.0.1.100", ["10.0.1.0/24"]) is True
        assert ip_in_list("10.0.2.1", ["10.0.1.0/24"]) is False

    def test_wildcard_match_all(self):
        """测试通配符 * 匹配所有 IP"""
        assert ip_in_list("1.2.3.4", ["*"]) is True
        assert ip_in_list("192.168.0.1", ["*"]) is True

    def test_multiple_rules(self):
        """测试多条规则，任意一条匹配即可"""
        rules = ["10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16"]
        assert ip_in_list("10.1.2.3", rules) is True
        assert ip_in_list("172.20.0.1", rules) is True
        assert ip_in_list("192.168.100.1", rules) is True
        assert ip_in_list("8.8.8.8", rules) is False

    def test_empty_list(self):
        """测试空列表返回 False"""
        assert ip_in_list("192.168.1.1", []) is False

    def test_invalid_ip_returns_false(self):
        """测试无效 IP 返回 False"""
        assert ip_in_list("not-an-ip", ["192.168.0.0/16"]) is False
        assert ip_in_list("", ["192.168.0.0/16"]) is False

    def test_invalid_ip_can_match_wildcard(self):
        """测试无效 IP 在通配符规则下也可匹配"""
        assert ip_in_list("not-an-ip", ["*"]) is True

    def test_invalid_rule_skipped(self):
        """测试无效规则被跳过，不影响其他规则"""
        assert ip_in_list("10.0.0.1", ["invalid-rule", "10.0.0.0/8"]) is True

    def test_ipv6_single(self):
        """测试 IPv6 单地址匹配"""
        assert ip_in_list("::1", ["::1"]) is True
        assert ip_in_list("::1", ["::2"]) is False

    def test_ipv6_cidr(self):
        """测试 IPv6 CIDR 匹配"""
        assert ip_in_list("fe80::1", ["fe80::/10"]) is True
        assert ip_in_list("2001:db8::1", ["fe80::/10"]) is False

    def test_loopback(self):
        """测试环回地址"""
        assert ip_in_list("127.0.0.1", ["127.0.0.0/8"]) is True
        assert ip_in_list("127.0.0.1", ["127.0.0.1"]) is True

    def test_mixed_ipv4_ipv6_rules(self):
        """测试混合 IPv4 和 IPv6 规则"""
        rules = ["192.168.0.0/16", "::1"]
        assert ip_in_list("192.168.1.1", rules) is True
        assert ip_in_list("::1", rules) is True
        assert ip_in_list("10.0.0.1", rules) is False

    def test_whitespace_in_rule(self):
        """测试规则中的空白被正确处理"""
        assert ip_in_list("10.0.0.1", ["  10.0.0.1  "]) is True
        assert ip_in_list("10.0.0.1", [" 10.0.0.0/8 "]) is True


class TestGetClientIpFromScope:
    """get_client_ip_from_scope 函数测试"""

    @staticmethod
    def _make_scope(client_ip="192.168.1.100", headers=None):
        """构造 ASGI scope"""
        scope = {
            "type": "http",
            "client": (client_ip, 12345),
            "headers": [],
        }
        if headers:
            scope["headers"] = [
                (k.lower().encode(), v.encode()) for k, v in headers.items()
            ]
        return scope

    def test_direct_ip_no_proxy(self):
        """测试直连 IP（无代理）"""
        scope = self._make_scope("1.2.3.4")
        assert get_client_ip_from_scope(scope) == "1.2.3.4"

    def test_direct_ip_no_trusted_proxies(self):
        """测试没有配置受信代理时，忽略代理头"""
        scope = self._make_scope("127.0.0.1", {"x-forwarded-for": "1.2.3.4"})
        assert get_client_ip_from_scope(scope) == "127.0.0.1"

    def test_xff_with_trusted_proxy(self):
        """测试通过 X-Forwarded-For 提取 IP（受信代理）"""
        scope = self._make_scope("127.0.0.1", {"x-forwarded-for": "203.0.113.50"})
        result = get_client_ip_from_scope(scope, trusted_proxies=["127.0.0.1"])
        assert result == "203.0.113.50"

    def test_xff_multiple_ips(self):
        """测试 X-Forwarded-For 有多个 IP 时取第一个"""
        scope = self._make_scope(
            "127.0.0.1",
            {"x-forwarded-for": "203.0.113.50, 10.0.0.1, 127.0.0.1"},
        )
        result = get_client_ip_from_scope(scope, trusted_proxies=["127.0.0.1"])
        assert result == "203.0.113.50"

    def test_xri_with_trusted_proxy(self):
        """测试通过 X-Real-IP 提取 IP（受信代理）"""
        scope = self._make_scope("10.0.0.1", {"x-real-ip": "203.0.113.99"})
        result = get_client_ip_from_scope(scope, trusted_proxies=["10.0.0.0/8"])
        assert result == "203.0.113.99"

    def test_xff_priority_over_xri(self):
        """测试 X-Forwarded-For 优先于 X-Real-IP"""
        scope = self._make_scope(
            "127.0.0.1",
            {"x-forwarded-for": "1.1.1.1", "x-real-ip": "2.2.2.2"},
        )
        result = get_client_ip_from_scope(scope, trusted_proxies=["127.0.0.1"])
        assert result == "1.1.1.1"

    def test_empty_xff_falls_back_to_xri(self):
        """测试空 X-Forwarded-For 时回退到 X-Real-IP"""
        scope = self._make_scope(
            "127.0.0.1",
            {"x-forwarded-for": "   ", "x-real-ip": "2.2.2.2"},
        )
        result = get_client_ip_from_scope(scope, trusted_proxies=["127.0.0.1"])
        assert result == "2.2.2.2"

    def test_untrusted_proxy_ignores_headers(self):
        """测试非受信代理时忽略代理头（防 IP 伪造）"""
        scope = self._make_scope(
            "8.8.8.8",
            {"x-forwarded-for": "spoofed.ip"},
        )
        result = get_client_ip_from_scope(scope, trusted_proxies=["127.0.0.1"])
        assert result == "8.8.8.8"

    def test_no_client_returns_unknown(self):
        """测试没有 client 信息时返回 unknown"""
        scope = {"type": "http", "headers": []}
        assert get_client_ip_from_scope(scope) == "unknown"

    def test_trusted_proxy_cidr(self):
        """测试受信代理支持 CIDR"""
        scope = self._make_scope("10.0.5.1", {"x-forwarded-for": "203.0.113.10"})
        result = get_client_ip_from_scope(scope, trusted_proxies=["10.0.0.0/8"])
        assert result == "203.0.113.10"


class TestGetClientIp:
    """get_client_ip 函数测试（Request 对象版本）"""

    @staticmethod
    def _make_request(client_ip="192.168.1.1", headers=None):
        """构造模拟 Request 对象"""
        from starlette.testclient import TestClient
        from starlette.applications import Starlette

        # 构造 ASGI scope 并创建 Request
        from starlette.requests import Request

        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "query_string": b"",
            "root_path": "",
            "headers": [],
            "client": (client_ip, 12345),
        }
        if headers:
            scope["headers"] = [
                (k.lower().encode(), v.encode()) for k, v in headers.items()
            ]
        return Request(scope)

    def test_direct_ip(self):
        """测试直连 IP"""
        request = self._make_request("203.0.113.1")
        assert get_client_ip(request) == "203.0.113.1"

    def test_xff_with_trusted_proxy(self):
        """测试代理环境下提取真实 IP"""
        request = self._make_request(
            "127.0.0.1", {"x-forwarded-for": "203.0.113.50"}
        )
        result = get_client_ip(request, trusted_proxies=["127.0.0.1"])
        assert result == "203.0.113.50"

    def test_untrusted_proxy(self):
        """测试非受信代理不信任代理头"""
        request = self._make_request(
            "8.8.8.8", {"x-forwarded-for": "spoofed"}
        )
        result = get_client_ip(request, trusted_proxies=["127.0.0.1"])
        assert result == "8.8.8.8"
