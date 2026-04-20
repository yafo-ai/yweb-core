"""限流模块

基于 slowapi 的轻度封装，提供一站式初始化、身份识别、统一 429 响应和限流事件订阅。

使用示例:
    from yweb.ratelimit import setup_ratelimit

    app = FastAPI()
    limiter = setup_ratelimit(app, default_limits=["100/minute"])

    @app.get("/api/v1/login")
    @limiter.limit("5/minute")
    async def login(request: Request):
        ...

事件订阅:
    from yweb.ratelimit import rate_limit_event_bus, RateLimitedEvent

    def save_to_db(event: RateLimitedEvent):
        ...

    rate_limit_event_bus.subscribe(save_to_db)
"""

from .setup import setup_ratelimit
from .key_funcs import get_user_or_ip, get_remote_address
from .events import RateLimitedEvent, RateLimitEventBus, rate_limit_event_bus

__all__ = [
    # 初始化（主要 API）
    "setup_ratelimit",
    # Key 函数
    "get_user_or_ip",
    "get_remote_address",
    # 事件
    "RateLimitedEvent",
    "RateLimitEventBus",
    "rate_limit_event_bus",
]
