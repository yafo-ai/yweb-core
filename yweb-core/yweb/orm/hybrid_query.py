"""HybridQuery —— 同步/异步双模查询代理

Phase 2（本次交付）：仅链式代理骨架，不发 SQL
=================================================

- ``HybridQuery[T]``：包装 SQLAlchemy 的 ``Query``，将其所有链式方法
  （``filter`` / ``order_by`` / ``limit`` 等）透明代理，返回值若仍是
  ``Query``，再包一层 ``HybridQuery`` 以支持链式语法。
- ``session`` 属性直接透传真实 :class:`sqlalchemy.orm.Session`，保障
  ``CoreModel`` 内 ``cls.query.session.execute(...)`` 等调用不受影响。
- 隐式终端 ``__iter__`` / ``__getitem__`` / ``__bool__`` 采用
  **上下文感知** 策略（与 23 号清单 Phase 3.3 决策 A 一致）：

  * 同步上下文：透传给 SA ``Query``，行为保持 100% 等价；
  * async 上下文：抛出 :class:`SynchronousOnlyOperation`，错误消息中
    提示改用 ``await q.all()`` / ``await q.count() > 0`` 等显式终端。

- ``_HybridTerminal[T]`` 仅放最小壳子，``__await__`` 与 ``_run_sync()``
  将在 Phase 3（终端方法）实装。

- **本 Phase 不接入** ``CoreModel.query`` —— 等 Phase 4 才替换 ``query_property``。

相关文档:
    - docs/orm_docs/22_hybrid_query_sync_async_refactor.md
    - docs/orm_docs/23_hybrid_query_execution_checklist.md
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable, Generic, TypeVar

from .async_safety import SynchronousOnlyOperation, is_in_async_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

__all__ = [
    "HybridQuery",
    "_HybridTerminal",
]

T = TypeVar("T")


class _HybridTerminal(Generic[T]):
    """终端结果占位对象（Phase 3 实装 ``__await__`` 与 ``_run_sync()``）

    Phase 2 只提供最小壳子，方便 ``hybrid_query.py`` 与测试用例
    import 时符号可用；Phase 3 将补上实际的同步求值与可 await 语义。
    """

    __slots__ = ("_thunk",)

    def __init__(self, thunk: Callable[[], T]) -> None:
        self._thunk = thunk


class HybridQuery(Generic[T]):
    """同步/异步双模查询代理

    包装 SQLAlchemy 的 ``Query``，Phase 2 仅透传链式方法与隐式终端。
    终端方法（``all`` / ``first`` / ``count`` / ``delete`` / ``update`` 等）
    在 Phase 3 单独实现。

    用法（Phase 4 接入 ``CoreModel.query`` 后）::

        # 同步上下文（def 路由、脚本、测试）
        users = User.query.filter_by(is_active=True).all()   # 原样工作

        # async 上下文（async def 路由）
        users = await User.query.filter_by(is_active=True).all()  # 返回 awaitable
    """

    __slots__ = ("_query",)

    def __init__(self, query: "Query[T]") -> None:
        self._query = query

    @property
    def session(self) -> "Session":
        """透传真实 :class:`Session`（不包成 HybridQuery）。

        ``CoreModel`` 内部大量使用 ``cls.query.session.execute(...)``
        这类"借 query 拿 session"的写法，必须保持行为一致。
        """
        return self._query.session

    def __getattr__(self, name: str) -> Any:
        if name == "_query":
            raise AttributeError(name)

        attr = getattr(self._query, name)
        if not callable(attr):
            return attr

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            result = attr(*args, **kwargs)
            from sqlalchemy.orm import Query as _SAQuery

            if isinstance(result, _SAQuery):
                return HybridQuery(result)
            return result

        return _wrapped

    def __repr__(self) -> str:
        return f"HybridQuery({self._query!r})"

    __str__ = __repr__

    def __iter__(self):
        if is_in_async_context():
            raise SynchronousOnlyOperation(
                "HybridQuery 不支持在 async 上下文中直接迭代（会阻塞事件循环）。\n"
                "请改用:  users = await query.all()"
            )
        return iter(self._query)

    def __getitem__(self, item: Any) -> Any:
        if is_in_async_context():
            raise SynchronousOnlyOperation(
                "HybridQuery 不支持在 async 上下文中切片/索引（会阻塞事件循环）。\n"
                "请改用:  items = await query.limit(n).offset(m).all()"
            )
        return self._query[item]

    def __bool__(self) -> bool:
        if is_in_async_context():
            raise SynchronousOnlyOperation(
                "HybridQuery 不支持在 async 上下文中做布尔判断（会阻塞事件循环）。\n"
                "请改用:  exists = await query.count() > 0"
            )
        return bool(self._query)
