"""
yweb.controller —— 类视图路由控制器

提供以「一个类 = 一个资源」方式组织 API 的能力：
- 方法名即路由动作
- 默认 POST，@get 标记 GET
- 下划线开头的方法不注册
- 类定义完成时自动生成 APIRouter

快速开始::

    from yweb.controller import ResourceController, get

    class ConnectorController(ResourceController):
        prefix = "/connector"
        tags = ["连接器"]

        @get
        async def list(self, page: int = 1):
            return Resp.OK(...)

        async def create(self, body: CreateRequest):
            return Resp.OK(...)

    # 挂载到 app
    app.include_router(ConnectorController.router, prefix="/api/v1")

    # 或自动扫描
    from yweb.controller import scan_controllers
    scan_controllers(app, package="app.api.v1", prefix="/api/v1")
"""

from .base import ResourceController
from .decorators import get, post, route
from .scanner import scan_controllers

__all__ = [
    "ResourceController",
    "get",
    "post",
    "route",
    "scan_controllers",
]
