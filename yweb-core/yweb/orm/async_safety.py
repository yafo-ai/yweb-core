"""异步安全检测模块

检测并阻止在 async 上下文（事件循环线程）中直接调用同步数据库操作，
防止阻塞事件循环导致并发性能下降和连接池耗尽。

原理：
    asyncio.get_running_loop() 能准确判断当前代码是否运行在事件循环线程上：
    - 能拿到 loop → 在事件循环线程 → 同步 DB 操作会阻塞
    - RuntimeError  → 在普通线程/线程池 → 安全

    各场景的检测结果：
    - def 路由（FastAPI 自动放线程池）  → 放行
    - async def + async_db_call()（线程池）→ 放行
    - async def 直接调 ORM              → 拦截
    - async def + allow_sync()          → 放行（如 lifespan 启动初始化）
    - 脚本 / 测试 / 定时任务            → 放行

公开 API:
    - SynchronousOnlyOperation: 异常类
    - check_async_safety(): 检测函数
    - allow_sync(): 上下文管理器，临时允许在 async 中执行同步操作
    - AsyncSafeQueryProperty: query 属性的安全包装描述符

配置：
    通过环境变量 YWEB_ASYNC_SAFETY 控制行为：
    - "error"（默认）: 抛出异常
    - "warn": 发出警告，继续执行
    - "off": 禁用检测
"""

import asyncio
import os
import warnings
from contextlib import contextmanager
from contextvars import ContextVar

__all__ = [
    'SynchronousOnlyOperation',
    'check_async_safety',
    'is_in_async_context',
    'allow_sync',
    'AsyncSafeQueryProperty',
]


class SynchronousOnlyOperation(RuntimeError):
    """在 async 上下文中执行了同步数据库操作

    当 async def 路由/函数中直接调用同步 ORM 方法时抛出此异常。
    同步操作会阻塞事件循环，导致所有并发请求被串行化，
    最终引发 QueuePool TimeoutError。
    """
    pass


_FIX_GUIDANCE = """
在 async def 中直接调用同步 ORM 会阻塞事件循环，导致并发性能严重下降。

修复方式（任选其一）：

  方式1（推荐）—— 将路由改为 def，FastAPI 自动放入线程池:

      @router.get("/users")
      def get_users():                    # ← 去掉 async
          return User.query.all()

  方式2 —— 保持 async def，用 async_db_call() 包装同步调用:

      from yweb.orm import async_db_call

      @router.get("/users")
      async def get_users():
          users = await async_db_call(User.get_all)  # ← 包装同步调用
          return users

      # 也支持 lambda 包裹复杂查询
      users = await async_db_call(
          lambda: User.query.filter_by(is_active=True).all()
      )

如需临时禁用此检测（不推荐），设置环境变量:
  YWEB_ASYNC_SAFETY=off
""".strip()

_mode = os.environ.get("YWEB_ASYNC_SAFETY", "error").lower()

_bypass = ContextVar('_async_safety_bypass', default=False)


@contextmanager
def allow_sync():
    """临时允许在 async 上下文中执行同步数据库操作

    用于 FastAPI lifespan、startup 事件等**必须**声明为 async def
    但需要执行同步 ORM 操作的场景。这些场景下没有并发请求，
    阻塞事件循环不会造成性能问题。

    使用示例::

        from yweb.orm import allow_sync

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            with allow_sync():
                init_database("sqlite:///app.db")
                auto_sync_permissions(app)
            yield

    .. warning::
        不要在请求处理路由中使用此上下文管理器，
        那里应该使用 ``def`` 路由或 ``async_db_call()``。
    """
    token = _bypass.set(True)
    try:
        yield
    finally:
        _bypass.reset(token)


def check_async_safety():
    """检测当前是否在事件循环线程中

    如果检测到在事件循环线程中调用（即 async 上下文），
    根据配置模式抛出异常或发出警告。

    此函数被嵌入到 ORM 的关键入口点（get_session、query 属性），
    用户通常不需要直接调用。
    """
    if _mode == "off":
        return

    if _bypass.get():
        return

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return

    if _mode == "warn":
        warnings.warn(
            "检测到在 async 上下文中直接调用同步数据库操作，"
            "这会阻塞事件循环。请使用 def 路由或 async_db_call() 包装。",
            RuntimeWarning,
            stacklevel=3,
        )
    else:
        raise SynchronousOnlyOperation(
            "检测到在 async 上下文中直接调用同步数据库操作！\n\n"
            + _FIX_GUIDANCE
        )


def is_in_async_context() -> bool:
    """判断当前是否在事件循环线程中（不抛错、不发警告）。

    与 :func:`check_async_safety` 不同，此函数仅返回布尔值，
    供需要自定义错误消息的调用方（如 HybridQuery 隐式终端）使用。

    同样尊重 ``YWEB_ASYNC_SAFETY=off`` 与 :func:`allow_sync` 的 bypass。
    """
    if _mode == "off":
        return False

    if _bypass.get():
        return False

    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


class AsyncSafeQueryProperty:
    """包装 SQLAlchemy 的 query_property，在 async 上下文中拦截访问

    当用户在 async def 中访问 Model.query 时，会先执行 async 安全检测，
    阻止同步查询阻塞事件循环。

    使用方式（框架内部）::

        raw_qp = session_scope.query_property()
        CoreModel.query = AsyncSafeQueryProperty(raw_qp)
    """

    def __init__(self, query_property):
        self._query_property = query_property

    def __get__(self, obj, cls):
        check_async_safety()
        return self._query_property.__get__(obj, cls)
