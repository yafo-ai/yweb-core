"""IP 访问控制模块

提供两种粒度的 IP 访问控制：

1. **中间件级别** — 全局路径规则，适合批量控制（如"管理后台仅内网"）::

    from yweb.middleware.ip_access import IPAccessMiddleware, IPAccessRule

    app.add_middleware(
        IPAccessMiddleware,
        rules=[
            IPAccessRule(
                paths=["/api/v1/admin/*"],
                allow_ips=["192.168.0.0/16", "10.0.0.0/8"],
            ),
        ],
        trusted_proxies=["127.0.0.1"],
    )

2. **路由级别** — 依赖注入，适合单个端点控制::

    from fastapi import Depends
    from yweb.middleware.ip_access import IPAllow, IPDeny

    @app.post("/auth/login", dependencies=[Depends(IPAllow(["192.168.0.0/16"]))])
    async def login():
        ...

    @app.get("/debug", dependencies=[Depends(IPDeny(["0.0.0.0/0"], allow_ips=["127.0.0.1"]))])
    async def debug():
        ...
"""

import json
import inspect
import asyncio
import fnmatch
from dataclasses import dataclass, field
from functools import wraps
from typing import List, Optional, Dict, Any, Callable

from fastapi import Request, HTTPException

from yweb.log import get_logger
from yweb.utils.ip import get_client_ip, get_client_ip_from_scope, ip_in_list

logger = get_logger()


@dataclass
class IPAccessRule:
    """IP 访问控制规则

    Attributes:
        paths: 路径模式列表，支持通配符（如 "/api/v1/admin/*"）
        allow_ips: 允许的 IP/CIDR 列表（白名单模式）
        deny_ips: 拒绝的 IP/CIDR 列表（黑名单模式）
        description: 规则描述（仅用于日志和文档）

    匹配逻辑：
    - 同时配置 deny_ips 和 allow_ips 时：先检查黑名单，再检查白名单
    - 仅配置 allow_ips 时：不在白名单中的 IP 被拒绝
    - 仅配置 deny_ips 时：在黑名单中的 IP 被拒绝
    """
    paths: List[str]
    allow_ips: List[str] = field(default_factory=list)
    deny_ips: List[str] = field(default_factory=list)
    description: str = ""


class IPAccessMiddleware:
    """IP 访问控制中间件（纯 ASGI 实现）

    对匹配路径的请求进行 IP 检查，不匹配任何规则的请求按 default_policy 处理。

    Args:
        app: ASGI 应用
        rules: IP 访问控制规则列表
        default_policy: 默认策略，"allow"（放行）或 "deny"（拒绝），默认 "allow"
        trusted_proxies: 受信任的代理 IP 列表，用于正确提取客户端 IP
        deny_status_code: 拒绝时的 HTTP 状态码，默认 403
        deny_message: 拒绝时的响应消息
    """

    def __init__(
        self,
        app,
        rules: Optional[List[IPAccessRule]] = None,
        default_policy: str = "allow",
        trusted_proxies: Optional[List[str]] = None,
        deny_status_code: int = 403,
        deny_message: str = "IP 访问被拒绝",
    ):
        self.app = app
        self.rules = rules or []
        self.default_policy = default_policy
        self.trusted_proxies = trusted_proxies
        self.deny_status_code = deny_status_code
        self.deny_message = deny_message

        # 启动时打印规则摘要
        if self.rules:
            logger.info(
                f"IP 访问控制已启用：{len(self.rules)} 条规则，"
                f"默认策略={self.default_policy}"
            )
            for i, rule in enumerate(self.rules):
                logger.info(
                    f"  规则[{i}]: paths={rule.paths}, "
                    f"allow={rule.allow_ips or '无'}, "
                    f"deny={rule.deny_ips or '无'}"
                    f"{f', {rule.description}' if rule.description else ''}"
                )

    async def __call__(self, scope, receive, send):
        """ASGI 入口"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        client_ip = get_client_ip_from_scope(scope, self.trusted_proxies)

        # 检查访问权限
        allowed, reason = self._check_access(client_ip, path)

        if not allowed:
            logger.warning(
                f"IP 访问被拒绝: ip={client_ip}, path={path}, reason={reason}"
            )
            await self._send_deny_response(send, client_ip, reason)
            return

        await self.app(scope, receive, send)

    def _check_access(self, ip: str, path: str) -> tuple:
        """检查 IP 对指定路径的访问权限

        Returns:
            (allowed: bool, reason: str)
        """
        # 遍历规则，找到第一个路径匹配的规则
        for rule in self.rules:
            if not self._path_matches(path, rule.paths):
                continue

            # 匹配到规则，执行 IP 检查

            # 1. 先检查黑名单
            if rule.deny_ips and ip_in_list(ip, rule.deny_ips):
                return False, f"命中黑名单规则: {rule.description or rule.paths}"

            # 2. 再检查白名单
            if rule.allow_ips:
                if ip_in_list(ip, rule.allow_ips):
                    return True, "白名单放行"
                else:
                    return False, f"不在白名单中: {rule.description or rule.paths}"

            # 3. 仅配了黑名单且未命中 → 放行
            if rule.deny_ips:
                return True, "未命中黑名单"

        # 没有匹配到任何规则，使用默认策略
        if self.default_policy == "deny":
            return False, "默认策略拒绝"
        return True, "默认策略放行"

    @staticmethod
    def _path_matches(path: str, patterns: List[str]) -> bool:
        """检查路径是否匹配任意一个模式

        支持通配符：
        - "/api/v1/admin/*" 匹配 /api/v1/admin/ 下所有路径
        - "/api/v1/admin/**" 同上（** 和 * 效果一致，因为 fnmatch 不区分）
        - "/api/v1/users" 精确匹配
        """
        for pattern in patterns:
            if fnmatch.fnmatch(path, pattern):
                return True
        return False

    async def _send_deny_response(self, send, client_ip: str, reason: str):
        """发送拒绝响应"""
        body = json.dumps(
            {
                "code": self.deny_status_code,
                "message": self.deny_message,
                "detail": reason,
            },
            ensure_ascii=False,
        ).encode("utf-8")

        await send({
            "type": "http.response.start",
            "status": self.deny_status_code,
            "headers": [
                (b"content-type", b"application/json; charset=utf-8"),
                (b"content-length", str(len(body)).encode()),
            ],
        })
        await send({
            "type": "http.response.body",
            "body": body,
        })

    @staticmethod
    def from_settings(config: Any) -> Dict[str, Any]:
        """从配置对象/字典中解析中间件参数

        支持两种格式：
        1. Pydantic model / 带属性的对象
        2. 字典（直接来自 YAML）

        配置示例（settings.yaml）::

            ip_access:
              enabled: true
              default_policy: allow
              trusted_proxies: ["127.0.0.1"]
              deny_status_code: 403
              deny_message: "IP 访问被拒绝"
              rules:
                - paths: ["/api/v1/admin/*"]
                  allow_ips: ["192.168.0.0/16"]
                  description: "管理后台仅允许内网"

        Returns:
            可直接解包传给 __init__ 的参数字典（不含 app）。
            如果 enabled=false，返回空 rules 列表。

        使用::

            if hasattr(settings, 'ip_access') and settings.ip_access:
                app.add_middleware(
                    IPAccessMiddleware,
                    **IPAccessMiddleware.from_settings(settings.ip_access),
                )
        """
        # 统一转为字典
        if hasattr(config, "model_dump"):
            data = config.model_dump()
        elif hasattr(config, "__dict__"):
            data = vars(config)
        elif isinstance(config, dict):
            data = config
        else:
            return {"rules": []}

        # 检查是否启用
        if not data.get("enabled", True):
            return {"rules": []}

        # 解析规则
        rules = []
        for rule_data in data.get("rules", []):
            rules.append(IPAccessRule(
                paths=rule_data.get("paths", []),
                allow_ips=rule_data.get("allow_ips", []),
                deny_ips=rule_data.get("deny_ips", []),
                description=rule_data.get("description", ""),
            ))

        return {
            "rules": rules,
            "default_policy": data.get("default_policy", "allow"),
            "trusted_proxies": data.get("trusted_proxies"),
            "deny_status_code": data.get("deny_status_code", 403),
            "deny_message": data.get("deny_message", "IP 访问被拒绝"),
        }


# ==================== 路由级别 IP 控制 ====================
#
# 提供两种风格：
# 1. 装饰器风格（推荐）:  @ip_allow(["10.0.0.0/8"])
# 2. 依赖注入风格:        dependencies=[Depends(IPAllow(["10.0.0.0/8"]))]
#


# --------------- 通用路由守卫工厂 ---------------

def _create_route_guard(check_fn: Callable) -> Callable:
    """创建 FastAPI 兼容的路由装饰器（通用工厂）

    将一个 ``async check_fn(request: Request) -> None`` 转换为可以
    直接标注在 FastAPI 路由函数上的装饰器，自动处理签名合成，
    不破坏 FastAPI 的参数注入（Path / Query / Body / Depends 等）。

    原理：在 wrapper 签名中注入 ``request: Request`` 参数（如果原函数
    没有的话），FastAPI 会自动识别 ``Request`` 类型并注入，且不会
    出现在 OpenAPI 文档中。

    Args:
        check_fn: 异步守卫函数，检查失败抛出 HTTPException

    Returns:
        可用于装饰 FastAPI 路由函数的装饰器
    """

    def decorator(func: Callable) -> Callable:
        sig = inspect.signature(func)
        has_request = "request" in sig.parameters
        is_async = asyncio.iscoroutinefunction(func)

        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = kwargs.get("request")

            # 执行守卫检查
            if request is not None:
                await check_fn(request)

            # 如果原函数没有 request 参数，从 kwargs 中移除
            if not has_request and "request" in kwargs:
                kwargs.pop("request")

            if is_async:
                return await func(*args, **kwargs)
            return func(*args, **kwargs)

        # 合成签名：确保 request 参数存在，供 FastAPI 自动注入
        if not has_request:
            params = list(sig.parameters.values())
            # 在 **kwargs 之前插入（如果有的话），否则追加
            insert_idx = len(params)
            for i, p in enumerate(params):
                if p.kind == inspect.Parameter.VAR_KEYWORD:
                    insert_idx = i
                    break
            params.insert(
                insert_idx,
                inspect.Parameter(
                    "request",
                    inspect.Parameter.KEYWORD_ONLY,
                    annotation=Request,
                ),
            )
            wrapper.__signature__ = sig.replace(parameters=params)

        return wrapper

    return decorator


# --------------- 装饰器风格 ---------------

def ip_allow(
    allow_ips: List[str],
    trusted_proxies: Optional[List[str]] = None,
    status_code: int = 403,
    message: str = "IP 访问被拒绝",
):
    """IP 白名单路由装饰器

    仅允许指定 IP/CIDR 的请求访问该端点，其余拒绝。

    使用示例::

        @app.post("/admin/sync")
        @ip_allow(["10.0.0.0/8", "192.168.0.0/16"])
        async def sync_data():
            ...

        # 原函数已有 request 参数也兼容
        @app.get("/info")
        @ip_allow(["*"])
        async def info(request: Request):
            return {"ip": request.client.host}

    Args:
        allow_ips: 允许的 IP/CIDR 列表（支持 "*" 通配符）
        trusted_proxies: 受信任代理列表
        status_code: 拒绝时的 HTTP 状态码
        message: 拒绝时的错误消息
    """

    async def _check(request: Request):
        client_ip = get_client_ip(request, trusted_proxies)
        if not ip_in_list(client_ip, allow_ips):
            logger.warning(
                f"IP 访问被拒绝（路由白名单）: ip={client_ip}, "
                f"path={request.url.path}, allow={allow_ips}"
            )
            raise HTTPException(status_code=status_code, detail=message)

    return _create_route_guard(_check)


def ip_deny(
    deny_ips: List[str],
    allow: Optional[List[str]] = None,
    trusted_proxies: Optional[List[str]] = None,
    status_code: int = 403,
    message: str = "IP 访问被拒绝",
):
    """IP 黑名单路由装饰器

    拒绝指定 IP/CIDR 的请求。可选配合白名单豁免。

    使用示例::

        @app.get("/api/data")
        @ip_deny(["1.2.3.4", "5.6.7.0/24"])
        async def get_data():
            ...

        # 黑名单 + 白名单豁免：拒绝所有，仅允许本机
        @app.get("/debug")
        @ip_deny(["0.0.0.0/0"], allow=["127.0.0.1", "::1"])
        async def debug_info():
            ...

    Args:
        deny_ips: 拒绝的 IP/CIDR 列表
        allow: 可选白名单豁免列表（优先于黑名单）
        trusted_proxies: 受信任代理列表
        status_code: 拒绝时的 HTTP 状态码
        message: 拒绝时的错误消息
    """
    allow_ips = allow or []

    async def _check(request: Request):
        client_ip = get_client_ip(request, trusted_proxies)
        # 白名单豁免
        if allow_ips and ip_in_list(client_ip, allow_ips):
            return
        if ip_in_list(client_ip, deny_ips):
            logger.warning(
                f"IP 访问被拒绝（路由黑名单）: ip={client_ip}, "
                f"path={request.url.path}, deny={deny_ips}"
            )
            raise HTTPException(status_code=status_code, detail=message)

    return _create_route_guard(_check)


# --------------- 依赖注入风格（用于 Router 级别） ---------------

class IPAllow:
    """IP 白名单依赖 — 用于 Router/路由的 dependencies 参数

    使用示例::

        from fastapi import Depends
        from yweb.middleware.ip_access import IPAllow

        # Router 级别
        admin_router = APIRouter(
            dependencies=[Depends(IPAllow(["192.168.0.0/16"]))],
        )

        # 单个路由
        @app.post("/webhook", dependencies=[Depends(IPAllow(["203.0.113.0/24"]))])
        async def webhook():
            ...
    """

    def __init__(
        self,
        allow_ips: List[str],
        trusted_proxies: Optional[List[str]] = None,
        deny_status_code: int = 403,
        deny_message: str = "IP 访问被拒绝",
    ):
        self.allow_ips = allow_ips
        self.trusted_proxies = trusted_proxies
        self.deny_status_code = deny_status_code
        self.deny_message = deny_message

    async def __call__(self, request: Request):
        client_ip = get_client_ip(request, self.trusted_proxies)
        if not ip_in_list(client_ip, self.allow_ips):
            logger.warning(
                f"IP 访问被拒绝（路由白名单）: ip={client_ip}, "
                f"path={request.url.path}, allow={self.allow_ips}"
            )
            raise HTTPException(
                status_code=self.deny_status_code,
                detail=self.deny_message,
            )


class IPDeny:
    """IP 黑名单依赖 — 用于 Router/路由的 dependencies 参数

    使用示例::

        from fastapi import Depends
        from yweb.middleware.ip_access import IPDeny

        @app.get("/api/data", dependencies=[Depends(IPDeny(["1.2.3.4"]))])
        async def get_data():
            ...
    """

    def __init__(
        self,
        deny_ips: List[str],
        allow_ips: Optional[List[str]] = None,
        trusted_proxies: Optional[List[str]] = None,
        deny_status_code: int = 403,
        deny_message: str = "IP 访问被拒绝",
    ):
        self.deny_ips = deny_ips
        self.allow_ips = allow_ips or []
        self.trusted_proxies = trusted_proxies
        self.deny_status_code = deny_status_code
        self.deny_message = deny_message

    async def __call__(self, request: Request):
        client_ip = get_client_ip(request, self.trusted_proxies)
        if self.allow_ips and ip_in_list(client_ip, self.allow_ips):
            return
        if ip_in_list(client_ip, self.deny_ips):
            logger.warning(
                f"IP 访问被拒绝（路由黑名单）: ip={client_ip}, "
                f"path={request.url.path}, deny={self.deny_ips}"
            )
            raise HTTPException(
                status_code=self.deny_status_code,
                detail=self.deny_message,
            )
