"""
控制器装饰器 —— 标记方法的 HTTP 方法与路由元数据。

ResourceController 中所有 public 方法默认注册为 POST。可用以下装饰器调整：

- ``@get`` / ``@post``：标记 HTTP 方法，可裸用，也可带参数传递路由元数据
- ``@route(method=..., ...)``：通用形式，显式指定方法与元数据

支持的元数据（与 FastAPI ``APIRouter.get/post`` 参数一致）::

    response_model, status_code, dependencies, summary, description,
    response_description, responses, name, deprecated, ...

使用示例::

    from yweb.controller import ResourceController, get, post

    class ItemController(ResourceController):
        prefix = "/item"

        @get
        async def list(self): ...                         # GET，无额外元数据

        @get(response_model=ItemListResponse)
        async def page(self): ...                         # GET + response_model

        @post(response_model=ItemResponse, status_code=201)
        async def create(self, body: CreateItem): ...     # POST + 元数据

        @post(dependencies=[require_role("admin")])
        async def delete(self, body: DeleteItem): ...     # POST + 方法级依赖

依赖项既可传入可调用对象（自动包装为 ``Depends``），也可直接传入 ``Depends(...)``。
"""

from typing import Any, Callable, Optional


def _set_route_meta(
    func: Callable,
    http_method: Optional[str] = None,
    *,
    path: Optional[str] = None,
    **kwargs,
) -> Callable:
    """把 HTTP 方法与路由元数据写到函数对象上，供 ResourceController 注册时读取。

    ``path`` 用于覆盖默认的 ``/方法名`` 路径（例如方法名无法表达连字符路径
    ``/reset-password`` 时）。它不是 FastAPI 路由元数据，单独存放。
    """
    if http_method is not None:
        func._http_method = http_method  # type: ignore[attr-defined]

    if path is not None:
        func._route_path = path  # type: ignore[attr-defined]

    meta = getattr(func, "_route_kwargs", None)
    if meta is None:
        meta = {}
        func._route_kwargs = meta  # type: ignore[attr-defined]
    # 过滤掉值为 None 的项，避免覆盖 FastAPI 的默认行为
    meta.update({k: v for k, v in kwargs.items() if v is not None})
    return func


def get(func: Optional[Callable] = None, **kwargs: Any):
    """标记该方法为 GET 端点。

    支持两种写法::

        @get
        async def list(self): ...

        @get(response_model=Foo, status_code=200, dependencies=[...])
        async def list(self): ...
    """
    if func is not None and callable(func) and not kwargs:
        return _set_route_meta(func, http_method="GET")

    def decorator(f: Callable) -> Callable:
        return _set_route_meta(f, http_method="GET", **kwargs)

    return decorator


def post(func: Optional[Callable] = None, **kwargs: Any):
    """标记该方法为 POST 端点（默认即 POST，通常用于附带元数据）。

    支持两种写法::

        @post
        async def create(self, body): ...

        @post(response_model=Foo, status_code=201, dependencies=[...])
        async def create(self, body): ...
    """
    if func is not None and callable(func) and not kwargs:
        return _set_route_meta(func, http_method="POST")

    def decorator(f: Callable) -> Callable:
        return _set_route_meta(f, http_method="POST", **kwargs)

    return decorator


_ALLOWED_METHODS = {"GET", "POST"}


def route(method: str = "POST", **kwargs: Any):
    """通用路由装饰器，显式指定 HTTP 方法与元数据。

    ResourceController 只允许 GET 和 POST，传入其他方法会抛出 ValueError。
    如需 PUT/DELETE/PATCH 等方法，请使用函数式路由。

    使用示例::

        @route("GET", response_model=Foo)
        async def list(self): ...
    """
    method = method.upper()
    if method not in _ALLOWED_METHODS:
        raise ValueError(
            f"ResourceController 只允许 GET/POST，收到 '{method}'。"
            f"如需 {method} 请使用函数式路由。"
        )

    def decorator(f: Callable) -> Callable:
        return _set_route_meta(f, http_method=method, **kwargs)

    return decorator
