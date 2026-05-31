"""
ResourceController —— 类视图路由控制器基类。

让开发者以「一个类 = 一个资源」的方式组织 API：
- 方法名即路由路径
- 默认 POST，用 @get 标记 GET 方法
- _ 开头的方法不注册为路由
- 类定义完成时自动生成 APIRouter

使用示例::

    from yweb.controller import ResourceController, get

    class ConnectorController(ResourceController):
        prefix = "/connector"
        tags = ["连接器"]

        @get
        async def list(self, page: int = 1):
            ...

        async def create(self, body: CreateRequest):
            ...
"""

import inspect
from typing import ClassVar

from fastapi import APIRouter, Depends


class ResourceController:
    """
    类视图路由控制器基类。

    子类声明 prefix（路径前缀），方法自动注册为路由端点。
    最终路由路径通过 FastAPI 的 include_router 分层组合：

        全局前缀 + 模块前缀 + prefix + /action
        /api/v1  + /workflow + /template + /create
    """

    prefix: ClassVar[str]
    tags: ClassVar[list[str]] = []
    dependencies: ClassVar[list] = []

    router: ClassVar[APIRouter]

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

        if "prefix" not in cls.__dict__:
            return

        deps = cls.__dict__.get("dependencies", cls.dependencies)
        cls.router = APIRouter(
            prefix=cls.prefix,
            tags=cls.__dict__.get("tags", cls.tags),
            dependencies=[Depends(d) for d in deps] if deps else [],
        )

        cls._register_actions()

    @classmethod
    def _register_actions(cls):
        """扫描类中的方法，注册为路由端点。"""
        for attr_name in list(vars(cls)):
            if attr_name.startswith("_"):
                continue

            method = vars(cls).get(attr_name)
            if method is None:
                continue

            if not inspect.isfunction(method):
                continue

            endpoint = cls._make_endpoint(method, attr_name)

            http_method = getattr(method, "_http_method", None)
            if http_method == "GET":
                cls.router.get(
                    f"/{attr_name}",
                    summary=cls._get_summary(method),
                )(endpoint)
            else:
                cls.router.post(
                    f"/{attr_name}",
                    summary=cls._get_summary(method),
                )(endpoint)

    @classmethod
    def _make_endpoint(cls, method, name: str):
        """
        将类方法包装为独立函数，剥离 self 参数。

        FastAPI 通过反射函数签名生成 OpenAPI 文档。类方法的第一个参数是 self，
        如果不剥离，FastAPI 会把 self 当成请求参数。处理后 type hints 正常
        工作，Swagger 文档中正确展示输入输出 Schema。
        """
        sig = inspect.signature(method)
        params = [p for p_name, p in sig.parameters.items() if p_name != "self"]
        new_sig = sig.replace(parameters=params)

        if inspect.iscoroutinefunction(method):
            async def endpoint(**kwargs):
                instance = cls()
                return await method(instance, **kwargs)
        else:
            async def endpoint(**kwargs):
                instance = cls()
                return method(instance, **kwargs)

        endpoint.__name__ = method.__name__
        endpoint.__qualname__ = method.__qualname__
        endpoint.__doc__ = method.__doc__
        endpoint.__module__ = getattr(method, "__module__", None)
        endpoint.__signature__ = new_sig
        endpoint.__annotations__ = {
            p_name: p.annotation
            for p_name, p in new_sig.parameters.items()
            if p.annotation is not inspect.Parameter.empty
        }
        if "return" in getattr(method, "__annotations__", {}):
            endpoint.__annotations__["return"] = method.__annotations__["return"]

        return endpoint

    @staticmethod
    def _get_summary(method) -> str | None:
        """从 docstring 第一行提取 summary。"""
        doc = method.__doc__
        if not doc:
            return None
        first_line = doc.strip().split("\n")[0].strip()
        return first_line if first_line else None
