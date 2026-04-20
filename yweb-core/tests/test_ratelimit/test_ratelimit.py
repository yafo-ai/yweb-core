"""
限流模块测试

测试 yweb.ratelimit 模块，包括：
1. setup_ratelimit 初始化和 middleware 注册
2. key_func 行为（JWT user_id / IP fallback）
3. 429 响应格式（yweb 统一格式）
4. RateLimitSettings 配置集成
5. 事件总线订阅/通知机制
"""

import pytest
from datetime import datetime
from unittest.mock import MagicMock

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.requests import Request
from starlette.responses import Response

from yweb.ratelimit import (
    setup_ratelimit,
    get_user_or_ip,
    get_remote_address,
    RateLimitedEvent,
    RateLimitEventBus,
    rate_limit_event_bus,
)
from yweb.config import RateLimitSettings


# ==================== 辅助函数 ====================


def _create_app_with_ratelimit(**kwargs) -> tuple:
    """创建带限流的测试应用，返回 (app, limiter)"""
    app = FastAPI()
    limiter = setup_ratelimit(app, **kwargs)

    @app.get("/test")
    @limiter.limit("2/minute")
    async def test_endpoint(request: Request, response: Response):
        return {"message": "ok"}

    @app.get("/unlimited")
    async def unlimited_endpoint(request: Request, response: Response):
        return {"message": "no limit"}

    return app, limiter


class _HeadersDict(dict):
    """可作为 Starlette Headers 替代品的 dict 子类"""
    pass


def _make_mock_request(
    path: str = "/test",
    method: str = "GET",
    client_host: str = "127.0.0.1",
    headers: dict = None,
) -> MagicMock:
    """构造 Mock Request 对象"""
    request = MagicMock(spec=Request)
    request.url.path = path
    request.method = method
    request.client.host = client_host
    request.headers = _HeadersDict(headers or {})
    return request


# ==================== 测试类 ====================


class TestSetupRatelimit:
    """setup_ratelimit 初始化测试"""

    def test_setup_returns_limiter(self):
        """测试 setup_ratelimit 返回 Limiter 实例"""
        from slowapi import Limiter

        app = FastAPI()
        limiter = setup_ratelimit(app, default_limits=["10/minute"])

        assert isinstance(limiter, Limiter)

    def test_setup_registers_limiter_on_app_state(self):
        """测试 Limiter 被注册到 app.state"""
        app = FastAPI()
        limiter = setup_ratelimit(app, default_limits=["10/minute"])

        assert app.state.limiter is limiter

    def test_setup_with_settings_object(self):
        """测试使用 RateLimitSettings 对象初始化"""
        settings = RateLimitSettings(
            enabled=True,
            default_limits=["50/minute"],
            headers_enabled=False,
            key_prefix="test_rl",
        )
        app = FastAPI()
        limiter = setup_ratelimit(app, settings=settings)

        assert app.state.limiter is limiter

    def test_setup_explicit_params_override_settings(self):
        """测试显式参数优先于 settings 对象"""
        settings = RateLimitSettings(default_limits=["50/minute"])
        app = FastAPI()
        limiter = setup_ratelimit(
            app, settings=settings, default_limits=["10/minute"]
        )

        assert app.state.limiter is limiter

    def test_setup_disabled_limiter(self):
        """测试 enabled=False 时限流不生效"""
        app, limiter = _create_app_with_ratelimit(
            default_limits=["1/minute"], enabled=False
        )
        client = TestClient(app)

        for _ in range(5):
            response = client.get("/test")
            assert response.status_code == 200

    def test_setup_with_on_limited_single_callback(self):
        """测试 on_limited 传入单个回调"""
        events = []

        def capture(event):
            events.append(event)

        rate_limit_event_bus.clear()
        app = FastAPI()
        setup_ratelimit(app, default_limits=["10/minute"], on_limited=capture)

        assert rate_limit_event_bus.subscriber_count >= 1
        rate_limit_event_bus.clear()

    def test_setup_with_on_limited_multiple_callbacks(self):
        """测试 on_limited 传入多个回调"""
        events_a = []
        events_b = []

        rate_limit_event_bus.clear()
        app = FastAPI()
        setup_ratelimit(
            app,
            default_limits=["10/minute"],
            on_limited=[events_a.append, events_b.append],
        )

        assert rate_limit_event_bus.subscriber_count >= 2
        rate_limit_event_bus.clear()


class TestKeyFuncs:
    """限流 Key 提取函数测试"""

    def test_get_remote_address_from_client(self):
        """测试从 request.client.host 提取 IP"""
        request = _make_mock_request(client_host="192.168.1.100")
        result = get_remote_address(request)
        assert result == "192.168.1.100"

    def test_get_remote_address_from_x_forwarded_for(self):
        """测试从 X-Forwarded-For 提取 IP（反向代理场景）"""
        request = _make_mock_request(
            headers={"x-forwarded-for": "10.0.0.1, 192.168.1.1"}
        )
        result = get_remote_address(request)
        assert result == "10.0.0.1"

    def test_get_remote_address_from_x_real_ip(self):
        """测试从 X-Real-IP 提取 IP"""
        request = _make_mock_request(headers={"x-real-ip": "172.16.0.1"})
        result = get_remote_address(request)
        assert result == "172.16.0.1"

    def test_get_user_or_ip_anonymous_returns_ip(self):
        """测试匿名请求返回 IP 标识"""
        request = _make_mock_request(client_host="10.0.0.5")
        result = get_user_or_ip(request)
        assert result == "ip:10.0.0.5"

    def test_get_user_or_ip_with_jwt_returns_user(self):
        """测试携带 JWT 时返回用户标识"""
        from jose import jwt as jose_jwt

        token = jose_jwt.encode({"sub": "admin"}, "secret", algorithm="HS256")
        request = _make_mock_request(
            headers={"authorization": f"Bearer {token}"}
        )
        result = get_user_or_ip(request)
        assert result == "user:admin"

    def test_get_user_or_ip_with_invalid_token_falls_back_to_ip(self):
        """测试无效 token 时 fallback 到 IP"""
        request = _make_mock_request(
            client_host="10.0.0.99",
            headers={"authorization": "Bearer not-a-valid-jwt"},
        )
        result = get_user_or_ip(request)
        assert result == "ip:10.0.0.99"

    def test_get_user_or_ip_with_empty_bearer(self):
        """测试空 Bearer 值时 fallback 到 IP"""
        request = _make_mock_request(
            client_host="10.0.0.50",
            headers={"authorization": "Bearer "},
        )
        result = get_user_or_ip(request)
        assert result == "ip:10.0.0.50"

    def test_get_user_or_ip_with_non_bearer_auth(self):
        """测试非 Bearer 认证头时 fallback 到 IP"""
        request = _make_mock_request(
            client_host="10.0.0.60",
            headers={"authorization": "Basic dXNlcjpwYXNz"},
        )
        result = get_user_or_ip(request)
        assert result == "ip:10.0.0.60"


class TestRateLimitResponse:
    """429 响应格式测试"""

    @pytest.fixture(autouse=True)
    def cleanup_event_bus(self):
        """每个测试前清空事件总线"""
        rate_limit_event_bus.clear()
        yield
        rate_limit_event_bus.clear()

    def test_429_returns_yweb_format(self):
        """测试超限时返回 yweb 统一 JSON 格式"""
        app, limiter = _create_app_with_ratelimit(default_limits=["2/minute"])
        client = TestClient(app)

        client.get("/test")
        client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429

        data = response.json()
        assert data["status"] == "error"
        assert "请求过于频繁" in data["message"]

    def test_429_includes_rate_limit_headers(self):
        """测试超限时响应包含 X-RateLimit-* headers"""
        app, limiter = _create_app_with_ratelimit(
            default_limits=["2/minute"], headers_enabled=True
        )
        client = TestClient(app)

        client.get("/test")
        client.get("/test")

        response = client.get("/test")
        assert response.status_code == 429
        assert "x-ratelimit-limit" in response.headers or "X-RateLimit-Limit" in response.headers

    def test_unlimited_endpoint_not_affected(self):
        """测试未限流端点不受 per-route 限流影响"""
        app, limiter = _create_app_with_ratelimit(default_limits=["100/minute"])
        client = TestClient(app)

        client.get("/test")
        client.get("/test")
        third = client.get("/test")
        assert third.status_code == 429

        response = client.get("/unlimited")
        assert response.status_code == 200


class TestRateLimitEventBus:
    """限流事件总线测试"""

    @pytest.fixture(autouse=True)
    def fresh_bus(self):
        """每个测试使用干净的事件总线"""
        self.bus = RateLimitEventBus()
        yield

    def test_subscribe_and_emit(self):
        """测试订阅后触发事件能收到通知"""
        received = []
        self.bus.subscribe(received.append)

        event = RateLimitedEvent(
            client_id="user:1",
            path="/test",
            method="GET",
            limit="5 per 1 minute",
            timestamp=datetime.utcnow(),
            headers={},
        )
        self.bus.emit(event)

        assert len(received) == 1
        assert received[0].client_id == "user:1"
        assert received[0].path == "/test"

    def test_unsubscribe(self):
        """测试取消订阅后不再收到通知"""
        received = []
        self.bus.subscribe(received.append)
        self.bus.unsubscribe(received.append)

        event = RateLimitedEvent(
            client_id="user:1",
            path="/test",
            method="GET",
            limit="5 per 1 minute",
            timestamp=datetime.utcnow(),
            headers={},
        )
        self.bus.emit(event)

        assert len(received) == 0

    def test_unsubscribe_nonexistent_returns_false(self):
        """测试取消不存在的订阅返回 False"""
        result = self.bus.unsubscribe(lambda e: None)
        assert result is False

    def test_duplicate_subscribe_ignored(self):
        """测试重复订阅同一回调被忽略"""
        received = []
        self.bus.subscribe(received.append)
        self.bus.subscribe(received.append)

        assert self.bus.subscriber_count == 1

    def test_subscriber_exception_does_not_block_others(self):
        """测试单个订阅者异常不影响其他订阅者"""
        results = []

        def bad_subscriber(event):
            raise RuntimeError("intentional error")

        def good_subscriber(event):
            results.append(event)

        self.bus.subscribe(bad_subscriber)
        self.bus.subscribe(good_subscriber)

        event = RateLimitedEvent(
            client_id="ip:10.0.0.1",
            path="/api",
            method="POST",
            limit="10 per 1 minute",
            timestamp=datetime.utcnow(),
            headers={},
        )
        self.bus.emit(event)

        assert len(results) == 1
        assert results[0].client_id == "ip:10.0.0.1"

    def test_clear_removes_all_subscribers(self):
        """测试 clear 清空所有订阅者"""
        self.bus.subscribe(lambda e: None)
        self.bus.subscribe(lambda e: None)
        assert self.bus.subscriber_count == 2

        self.bus.clear()
        assert self.bus.subscriber_count == 0

    def test_subscriber_count_property(self):
        """测试 subscriber_count 属性"""
        assert self.bus.subscriber_count == 0

        cb = lambda e: None  # noqa: E731
        self.bus.subscribe(cb)
        assert self.bus.subscriber_count == 1

        self.bus.unsubscribe(cb)
        assert self.bus.subscriber_count == 0


class TestRateLimitedEvent:
    """限流事件数据类测试"""

    def test_event_is_frozen(self):
        """测试事件是不可变的"""
        event = RateLimitedEvent(
            client_id="user:1",
            path="/test",
            method="GET",
            limit="5 per 1 minute",
            timestamp=datetime.utcnow(),
            headers={},
        )
        with pytest.raises(AttributeError):
            event.client_id = "user:2"

    def test_from_request_extracts_safe_headers(self):
        """测试 from_request 只提取安全请求头，不包含 Authorization"""
        request = _make_mock_request(
            path="/api/login",
            method="POST",
            client_host="10.0.0.1",
            headers={
                "user-agent": "Mozilla/5.0",
                "authorization": "Bearer secret-token",
                "referer": "https://example.com",
                "x-custom": "should-be-excluded",
            },
        )

        event = RateLimitedEvent.from_request(request, "5 per 1 minute")

        assert "user-agent" in event.headers
        assert "referer" in event.headers
        assert "authorization" not in event.headers
        assert "x-custom" not in event.headers

    def test_from_request_populates_all_fields(self):
        """测试 from_request 填充所有字段"""
        request = _make_mock_request(
            path="/api/data", method="GET", client_host="192.168.1.1"
        )

        event = RateLimitedEvent.from_request(
            request, "10 per 1 minute", client_id="user:42"
        )

        assert event.client_id == "user:42"
        assert event.path == "/api/data"
        assert event.method == "GET"
        assert event.limit == "10 per 1 minute"
        assert isinstance(event.timestamp, datetime)


class TestRateLimitIntegration:
    """限流集成测试"""

    @pytest.fixture(autouse=True)
    def cleanup_event_bus(self):
        """每个测试前清空全局事件总线"""
        rate_limit_event_bus.clear()
        yield
        rate_limit_event_bus.clear()

    def test_429_triggers_event(self):
        """测试超限时触发限流事件"""
        events = []
        rate_limit_event_bus.subscribe(events.append)

        app, limiter = _create_app_with_ratelimit(default_limits=["2/minute"])
        client = TestClient(app)

        client.get("/test")
        client.get("/test")
        response = client.get("/test")

        assert response.status_code == 429
        assert len(events) == 1
        assert events[0].path == "/test"
        assert events[0].method == "GET"
        assert "2 per 1 minute" in events[0].limit

    def test_non_limited_request_does_not_trigger_event(self):
        """测试未超限请求不触发事件"""
        events = []
        rate_limit_event_bus.subscribe(events.append)

        app, limiter = _create_app_with_ratelimit(default_limits=["100/minute"])
        client = TestClient(app)

        client.get("/test")
        client.get("/test")

        assert len(events) == 0

    def test_setup_from_settings_and_rate_limit_works(self):
        """测试从 RateLimitSettings 初始化后限流正常工作"""
        settings = RateLimitSettings(
            enabled=True,
            default_limits=["1/minute"],
        )
        app = FastAPI()
        limiter = setup_ratelimit(app, settings=settings)

        @app.get("/api")
        @limiter.limit("1/minute")
        async def api_endpoint(request: Request, response: Response):
            return {"ok": True}

        client = TestClient(app)

        first = client.get("/api")
        assert first.status_code == 200

        second = client.get("/api")
        assert second.status_code == 429

        data = second.json()
        assert data["status"] == "error"
        assert "请求过于频繁" in data["message"]

    def test_multiple_events_for_multiple_429s(self):
        """测试多次超限触发多次事件"""
        events = []
        rate_limit_event_bus.subscribe(events.append)

        app, limiter = _create_app_with_ratelimit(default_limits=["100/minute"])
        client = TestClient(app)

        # per-route limit is 2/minute, so 3rd and 4th requests both trigger 429
        client.get("/test")
        client.get("/test")
        client.get("/test")
        client.get("/test")

        assert len(events) == 2
