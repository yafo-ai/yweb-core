"""限流事件模块

提供限流触发时的事件数据类和事件总线，支持订阅/通知模式。

使用示例:
    from yweb.ratelimit import rate_limit_event_bus, RateLimitedEvent

    # 订阅限流事件
    def on_rate_limited(event: RateLimitedEvent):
        print(f"限流触发: {event.client_id} -> {event.path}")

    rate_limit_event_bus.subscribe(on_rate_limited)

    # 取消订阅
    rate_limit_event_bus.unsubscribe(on_rate_limited)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Dict, List

from starlette.requests import Request

from yweb.log import get_logger

logger = get_logger("yweb.ratelimit")

_SAFE_HEADERS = ("user-agent", "referer", "origin", "x-forwarded-for", "x-real-ip")


@dataclass(frozen=True)
class RateLimitedEvent:
    """限流触发事件（不可变值对象）

    Attributes:
        client_id: 限流标识（如 "user:123" 或 "ip:10.0.0.1"）
        path: 请求路径
        method: HTTP method
        limit: 触发的限流规则描述，如 "5 per 1 minute"
        timestamp: 触发时间（UTC）
        headers: 请求头摘要（仅保留安全字段，不含 Authorization 等敏感头）
    """
    client_id: str
    path: str
    method: str
    limit: str
    timestamp: datetime
    headers: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_request(cls, request: Request, detail: str, client_id: str = "") -> "RateLimitedEvent":
        """从 Request 对象构造事件快照

        Args:
            request: Starlette Request 对象
            detail: 限流规则描述（来自 RateLimitExceeded.detail）
            client_id: 限流标识，为空时从请求中推断
        """
        if not client_id:
            from .key_funcs import get_user_or_ip
            client_id = get_user_or_ip(request)

        safe_headers = {
            k: v for k, v in request.headers.items()
            if k.lower() in _SAFE_HEADERS
        }

        return cls(
            client_id=client_id,
            path=str(request.url.path),
            method=request.method,
            limit=str(detail),
            timestamp=datetime.utcnow(),
            headers=safe_headers,
        )


class RateLimitEventBus:
    """限流事件订阅/通知总线

    使用示例:
        bus = RateLimitEventBus()

        def my_handler(event: RateLimitedEvent):
            save_to_db(event)

        bus.subscribe(my_handler)

        # 触发时（由框架内部调用）
        bus.emit(event)

        # 取消订阅
        bus.unsubscribe(my_handler)
    """

    def __init__(self):
        self._subscribers: List[Callable[[RateLimitedEvent], None]] = []

    def subscribe(self, callback: Callable[[RateLimitedEvent], None]) -> None:
        """订阅限流事件

        Args:
            callback: 事件回调函数，接收 RateLimitedEvent 参数
        """
        if callback not in self._subscribers:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[RateLimitedEvent], None]) -> bool:
        """取消订阅

        Args:
            callback: 要取消的回调函数

        Returns:
            是否成功取消（回调不存在时返回 False）
        """
        try:
            self._subscribers.remove(callback)
            return True
        except ValueError:
            return False

    def emit(self, event: RateLimitedEvent) -> None:
        """广播事件给所有订阅者

        同步逐个调用订阅者。单个订阅者抛异常只 log warning，
        不影响其他订阅者和 429 响应返回。
        """
        for callback in self._subscribers:
            try:
                callback(event)
            except Exception as e:
                logger.warning(
                    f"Rate limit event subscriber error: "
                    f"{callback.__name__ if hasattr(callback, '__name__') else callback} "
                    f"raised {type(e).__name__}: {e}"
                )

    def clear(self) -> None:
        """清空所有订阅者"""
        self._subscribers.clear()

    @property
    def subscriber_count(self) -> int:
        """当前订阅者数量"""
        return len(self._subscribers)


rate_limit_event_bus = RateLimitEventBus()
"""全局限流事件总线实例"""


__all__ = [
    "RateLimitedEvent",
    "RateLimitEventBus",
    "rate_limit_event_bus",
]
