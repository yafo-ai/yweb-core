"""HybridQuery —— 同步/异步双模查询代理

设计范围（Phase 2 + Phase 3）
=================================================

Phase 2（已交付）：链式代理骨架
    - ``HybridQuery[T]`` 透明代理 SA ``Query``，链式方法返回 HybridQuery
    - ``session`` 透传真实 ``Session``
    - 隐式终端 ``__iter__`` / ``__getitem__`` / ``__bool__`` —— 同步透传、async 抛错

Phase 3（本次交付）：终端方法与 await 支持
    - ``_HybridTerminal[U]`` 实装 ``__await__``（走 ``starlette.concurrency.run_in_threadpool``）
      + ``_run_sync()`` 内部同步入口 + 一次性消费保护（``_consumed``）
    - ``HybridQuery`` 上 10 个终端方法：``all`` / ``first`` / ``one`` / ``one_or_none`` /
      ``scalar`` / ``count`` / ``get`` / ``delete`` / ``update`` / ``paginate``
    - 所有终端统一走 ``_terminal()`` helper，遵循 Phase 3.3 决策 A + A2：
      * 同步上下文 → 立即求值返回原生结果
      * async 上下文 → 返回 ``_HybridTerminal``；未 ``await`` 则下一行操作触发 ``TypeError``

Phase 4（未开始）：接入 ``CoreModel.query`` —— 当前仍是 ``AsyncSafeQueryProperty``。

相关文档:
    - docs/orm_docs/22_hybrid_query_sync_async_refactor.md §5.1 / §7.3
    - docs/orm_docs/23_hybrid_query_execution_checklist.md Phase 2 / Phase 3
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any, Callable, Generator, Generic, TypeVar, Union

from .async_safety import AsyncSafeQueryProperty, SynchronousOnlyOperation, is_in_async_context

if TYPE_CHECKING:
    from sqlalchemy.orm import Query, Session

__all__ = [
    "HybridQuery",
    "HybridQueryProperty",
    "_HybridTerminal",
]

T = TypeVar("T")
U = TypeVar("U")


class _HybridTerminal(Generic[T]):
    """终端结果对象 —— 一次性 awaitable

    承载一个"待执行的同步调用"（``thunk``），对外提供两种消费方式：

    1. ``await terminal`` —— 在 async 上下文下通过
       :func:`starlette.concurrency.run_in_threadpool` 移交到 AnyIO 线程池
       执行，不阻塞事件循环；
    2. ``terminal._run_sync()`` —— 下划线内部 escape hatch，直接同步调用，
       **不是公开 API**，仅供框架内部少量兼容点使用（Phase 3.3 决策：不对
       外暴露 ``.value()`` / ``.result()`` 避免与"同步直接调用"造成双写法）。

    **一次性语义**（doc 22 §7.3.9）：同一对象只能消费一次，第二次 await
    或 ``_run_sync()`` 均抛 :class:`RuntimeError`；避免复用 terminal 导致
    重复执行 SQL 的隐式副作用。
    """

    __slots__ = ("_thunk", "_consumed")

    def __init__(self, thunk: Callable[[], T]) -> None:
        self._thunk = thunk
        self._consumed = False

    def __await__(self) -> Generator[Any, None, T]:
        self._mark_consumed()
        from starlette.concurrency import run_in_threadpool

        return run_in_threadpool(self._thunk).__await__()

    def _run_sync(self) -> T:
        """同步执行 thunk（内部 escape hatch，不是公开 API）"""
        self._mark_consumed()
        return self._thunk()

    def _mark_consumed(self) -> None:
        if self._consumed:
            raise RuntimeError(
                "HybridQuery terminal already consumed. "
                "终端对象只能消费一次；如需再次查询请重新构建 query。"
            )
        self._consumed = True


class HybridQuery(Generic[T]):
    """同步/异步双模查询代理

    包装 SQLAlchemy 的 ``Query``，同步上下文下行为 100% 贴近原生；
    async 上下文下将终端求值移交线程池，避免阻塞事件循环。

    用法（Phase 4 接入 ``CoreModel.query`` 后）::

        # 同步上下文（def 路由、脚本、测试）
        users = User.query.filter_by(is_active=True).all()

        # async 上下文（async def 路由）
        users = await User.query.filter_by(is_active=True).all()
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

    def _terminal(self, thunk: Callable[[], U]) -> "Union[U, _HybridTerminal[U]]":
        """终端方法统一入口（Phase 3.3 决策 A）

        - 同步上下文：立即调用 thunk 返回原生结果；
        - async 上下文：返回 :class:`_HybridTerminal`，供 ``await`` 消费。

        尊重 ``allow_sync()`` 与 ``YWEB_ASYNC_SAFETY=off``（通过
        :func:`is_in_async_context` 内部判断）。
        """
        if is_in_async_context():
            return _HybridTerminal(thunk)
        return thunk()

    def all(self) -> "Union[list[T], _HybridTerminal[list[T]]]":
        return self._terminal(lambda: self._query.all())

    def first(self) -> "Union[T | None, _HybridTerminal[T | None]]":
        return self._terminal(lambda: self._query.first())

    def one(self) -> "Union[T, _HybridTerminal[T]]":
        return self._terminal(lambda: self._query.one())

    def one_or_none(self) -> "Union[T | None, _HybridTerminal[T | None]]":
        return self._terminal(lambda: self._query.one_or_none())

    def scalar(self) -> "Union[Any, _HybridTerminal[Any]]":
        return self._terminal(lambda: self._query.scalar())

    def count(self) -> "Union[int, _HybridTerminal[int]]":
        return self._terminal(lambda: self._query.count())

    def get(self, ident: Any) -> "Union[T | None, _HybridTerminal[T | None]]":
        """按主键取（SA 2.0 已 deprecate，仅为向后兼容保留）"""
        return self._terminal(lambda: self._query.get(ident))

    def delete(self, synchronize_session: Any = "auto") -> "Union[int, _HybridTerminal[int]]":
        """批量删除，返回影响行数（写终端）"""
        return self._terminal(
            lambda: self._query.delete(synchronize_session=synchronize_session)
        )

    def update(
        self,
        values: dict,
        synchronize_session: Any = "auto",
    ) -> "Union[int, _HybridTerminal[int]]":
        """批量更新，返回影响行数（写终端）"""
        return self._terminal(
            lambda: self._query.update(values, synchronize_session=synchronize_session)
        )

    def paginate(
        self,
        page: int = 1,
        page_size: int = 10,
        max_page_size: int = 100,
        schema: Any = None,
    ) -> Any:
        """分页查询（走 ``CoreModel._add_paginate_to_query`` 注入的方法）

        内部一次 thunk 内完成 count + offset/limit.all()，**同一线程池回合**
        执行完毕，避免两次跳线程（doc 22 §7.3.1）。

        返回 :class:`Page` 同步，或 ``_HybridTerminal[Page]`` 异步。
        """
        return self._terminal(
            lambda: self._query.paginate(
                page=page,
                page_size=page_size,
                max_page_size=max_page_size,
                schema=schema,
            )
        )


class HybridQueryProperty:
    """``CoreModel.query`` 的描述符 —— 默认走 HybridQuery，支持环境变量回退

    **默认行为（``YWEB_HYBRID_QUERY=on`` 或未设置）**：
        ``Model.query`` 返回 :class:`HybridQuery` 包装，其终端方法在同步上下文
        立即求值、在 async 上下文返回 :class:`_HybridTerminal` 供 await。
        不在 ``__get__`` 时调用 :func:`check_async_safety` —— async 检测交由
        HybridQuery 的终端方法 / 隐式终端禁用处理（避免 async 路由刚访问
        ``Model.query.filter_by(...)`` 就炸）。

    **回退行为（``YWEB_HYBRID_QUERY=off``）**：
        退回到 Phase 4 之前的 :class:`AsyncSafeQueryProperty`：返回原生
        SA ``Query``，访问瞬间若处于 async 上下文直接抛
        :class:`SynchronousOnlyOperation`（与重构前行为完全一致，
        供紧急回滚使用，doc 22 §7.4）。

    使用方式（框架内部，``db_session.py`` 挂载）::

        raw_qp = self._session_scope.query_property()
        CoreModel.query = HybridQueryProperty(raw_qp)
    """

    __slots__ = ("_raw_qp", "_async_safe_qp")

    def __init__(self, raw_query_property: Any) -> None:
        self._raw_qp = raw_query_property
        self._async_safe_qp = AsyncSafeQueryProperty(raw_query_property)

    def __get__(self, obj: Any, cls: Any) -> Any:
        if self._is_rollback_mode():
            return self._async_safe_qp.__get__(obj, cls)

        raw_query = self._raw_qp.__get__(obj, cls)
        return HybridQuery(raw_query)

    @staticmethod
    def _is_rollback_mode() -> bool:
        return os.environ.get("YWEB_HYBRID_QUERY", "on").lower() == "off"
