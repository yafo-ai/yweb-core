"""中间件模块

提供 FastAPI/Starlette 中间件：
- RequestIDMiddleware: 请求ID生成
- RequestLoggingMiddleware: 请求日志记录
- PerformanceMonitoringMiddleware: 性能监控
- CurrentUserMiddleware: 当前用户追踪（审计功能）
- IPAccessMiddleware: IP 访问控制
"""

from .request_id import RequestIDMiddleware, get_request_id
from .request_logging import RequestLoggingMiddleware
from .performance import PerformanceMonitoringMiddleware
from .current_user import (
    CurrentUserMiddleware,
    SimpleCurrentUserMiddleware,
    set_current_user_id,
    get_current_user_id,
    clear_current_user_id,
)
from .ip_access import (
    IPAccessMiddleware,
    IPAccessRule,
    # 装饰器风格
    ip_allow,
    ip_deny,
    # 依赖注入风格
    IPAllow,
    IPDeny,
    # 通用路由守卫工厂（高级用法）
    _create_route_guard,
)

__all__ = [
    "RequestIDMiddleware",
    "RequestLoggingMiddleware",
    "PerformanceMonitoringMiddleware",
    "CurrentUserMiddleware",
    "SimpleCurrentUserMiddleware",
    "get_request_id",
    # ContextVar 方式的用户ID管理
    "set_current_user_id",
    "get_current_user_id",
    "clear_current_user_id",
    # IP 访问控制 — 中间件
    "IPAccessMiddleware",
    "IPAccessRule",
    # IP 访问控制 — 装饰器
    "ip_allow",
    "ip_deny",
    # IP 访问控制 — 依赖注入
    "IPAllow",
    "IPDeny",
]
