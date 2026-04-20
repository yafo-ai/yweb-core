"""限流模块 - 一站式初始化

基于 slowapi 的轻度封装，提供配置桥接、身份识别、统一 429 响应。

使用示例:
    from yweb.ratelimit import setup_ratelimit

    app = FastAPI()

    # 快速初始化
    limiter = setup_ratelimit(app, default_limits=["100/minute"])

    # 从配置初始化
    limiter = setup_ratelimit(app, settings=settings.ratelimit)

    # 带事件订阅
    limiter = setup_ratelimit(
        app,
        default_limits=["100/minute"],
        on_limited=my_callback,
    )

    # 路由中使用 slowapi 原生装饰器
    @app.get("/api/v1/login")
    @limiter.limit("5/minute")
    async def login(request: Request):
        ...
"""

from typing import Any, Callable, List, Optional, Union

from starlette.requests import Request
from starlette.responses import JSONResponse

from yweb.log import get_logger
from yweb.response import Resp

from .events import RateLimitedEvent, rate_limit_event_bus
from .key_funcs import get_user_or_ip

logger = get_logger("yweb.ratelimit")


def _make_handler() -> Callable:
    """创建限流超限异常处理器"""

    def rate_limit_exceeded_handler(request: Request, exc: Any) -> JSONResponse:
        detail = str(exc.detail) if hasattr(exc, "detail") else str(exc)

        response = Resp.TooManyRequests(
            message=f"请求过于频繁，请稍后再试（限制: {detail}）"
        )

        limiter = getattr(request.app.state, "limiter", None)
        if limiter and hasattr(request.state, "view_rate_limit"):
            try:
                response = limiter._inject_headers(
                    response, request.state.view_rate_limit
                )
            except Exception:
                pass

        logger.warning(
            f"Rate limited: {request.method} {request.url.path} | {detail}"
        )

        event = RateLimitedEvent.from_request(request, detail)
        rate_limit_event_bus.emit(event)

        return response

    return rate_limit_exceeded_handler


def setup_ratelimit(
    app: Any,
    *,
    default_limits: Optional[List[str]] = None,
    storage_uri: Optional[str] = None,
    key_func: Optional[Callable] = None,
    headers_enabled: bool = True,
    key_prefix: str = "yweb_rl",
    enabled: bool = True,
    settings: Optional[Any] = None,
    on_limited: Optional[Union[Callable, List[Callable]]] = None,
) -> Any:
    """一站式初始化限流

    基于 slowapi 创建 Limiter，注册 middleware 和异常处理器，
    集成 yweb 统一 429 响应格式和限流事件总线。

    Args:
        app: FastAPI 应用实例
        default_limits: 全局默认限流规则，如 ["100/minute", "5/second"]
        storage_uri: 存储后端 URI，空/"memory:" 用内存，"redis://..." 用 Redis
        key_func: 限流 key 提取函数，默认 get_user_or_ip（JWT user_id / IP）
        headers_enabled: 是否在响应中包含 X-RateLimit-* headers
        key_prefix: 限流计数器 key 前缀
        enabled: 是否启用限流（False 时所有限流规则不生效）
        settings: RateLimitSettings 实例，提供时作为参数默认值
        on_limited: 限流触发时的回调，单个 Callable 或 Callable 列表

    Returns:
        slowapi.Limiter 实例，可用于 @limiter.limit() 装饰器

    Raises:
        ImportError: slowapi 未安装时
    """
    try:
        from slowapi import Limiter
        from slowapi.errors import RateLimitExceeded
        from slowapi.middleware import SlowAPIMiddleware
    except ImportError:
        raise ImportError(
            "限流模块需要 slowapi 库，请安装: pip install yweb[ratelimit]"
        )

    if settings is not None:
        if default_limits is None:
            default_limits = settings.default_limits
        if storage_uri is None:
            storage_uri = settings.storage_uri
        if not hasattr(setup_ratelimit, "_explicit_headers"):
            headers_enabled = settings.headers_enabled
        if key_prefix == "yweb_rl":
            key_prefix = settings.key_prefix
        enabled = settings.enabled

    if default_limits is None:
        default_limits = ["60/minute"]

    if key_func is None:
        key_func = get_user_or_ip

    resolved_storage = storage_uri or "memory://"

    if on_limited is not None:
        if callable(on_limited):
            rate_limit_event_bus.subscribe(on_limited)
        else:
            for cb in on_limited:
                rate_limit_event_bus.subscribe(cb)

    limiter = Limiter(
        key_func=key_func,
        default_limits=default_limits,
        storage_uri=resolved_storage,
        headers_enabled=headers_enabled,
        key_prefix=key_prefix,
        enabled=enabled,
    )

    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _make_handler())
    app.add_middleware(SlowAPIMiddleware)

    storage_desc = "Redis" if "redis" in resolved_storage.lower() else "memory"
    logger.info(
        f"限流已初始化: default_limits={default_limits}, "
        f"storage={storage_desc}, headers={headers_enabled}, "
        f"key_prefix={key_prefix}, enabled={enabled}"
    )

    return limiter


__all__ = ["setup_ratelimit"]
