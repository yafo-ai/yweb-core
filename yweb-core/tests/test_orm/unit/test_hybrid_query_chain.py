"""HybridQuery 链式代理单元测试（Phase 2）

验收范围：
    1. 代理链（``.filter().order_by().limit()`` 每步返回 HybridQuery）
    2. ``session`` 属性透传真实 Session（不是 HybridQuery）
    3. 非 Query 返回值原样透传（例如 ``statement`` 返回 SQL AST）
    4. ``__repr__`` 包含内部 Query 信息
    5. 同步隐式终端（``for/bool/index``）透传 —— 真实 SA Query + SQLite in-memory
    6. async 隐式终端抛 ``SynchronousOnlyOperation``，错误消息含引导
    7. ``allow_sync()`` 兜底：async 内临时放行
    8. ``YWEB_ASYNC_SAFETY=off``：async 内直接迭代不抛错
    9. 边界：访问不存在的属性/方法抛 AttributeError

Phase 2 不测终端方法（``.all()`` / ``.count()`` 等），留给 Phase 3。
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest
from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import Query, Session, sessionmaker

from yweb.orm import BaseModel, allow_sync
from yweb.orm import async_safety
from yweb.orm.async_safety import SynchronousOnlyOperation
from yweb.orm.hybrid_query import HybridQuery, _HybridTerminal


# ==================== 测试模型 ====================

class HQUser(BaseModel):
    __tablename__ = "hq_test_users"
    __table_args__ = {"extend_existing": True}

    email = Column(String(200))
    age = Column(Integer)


# ==================== Fixtures ====================

@pytest.fixture
def sa_query(memory_engine) -> Query:
    """提供一个真实 SA Query（接入了内存 SQLite，可真正执行 SQL）"""
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session: Session = SessionLocal()
    try:
        session.add_all([
            HQUser(name="Alice", email="a@t", age=30),
            HQUser(name="Bob", email="b@t", age=25),
            HQUser(name="Carol", email="c@t", age=35),
        ])
        session.commit()
        yield session.query(HQUser)
    finally:
        session.close()


@pytest.fixture(autouse=True)
def reset_async_safety_mode():
    """每个 case 结束恢复 _mode，避免污染其他测试"""
    original = async_safety._mode
    yield
    async_safety._mode = original


# ==================== 代理链测试（Mock 版：不发 SQL） ====================

class TestProxyChain:
    """验证链式方法代理的核心逻辑 —— 用 Mock 隔离 SA"""

    def test_chain_returns_hybrid_query(self):
        """每一步 Query 方法调用都应重新包装成 HybridQuery"""
        inner = MagicMock(spec=Query)
        filtered = MagicMock(spec=Query)
        inner.filter_by.return_value = filtered

        hq = HybridQuery(inner)
        result = hq.filter_by(name="Alice")

        assert isinstance(result, HybridQuery)
        assert result._query is filtered

    def test_chain_preserves_final_query(self):
        """多层链式调用后，最末层 ``_query`` 是链尾的真 Query"""
        q0 = MagicMock(spec=Query)
        q1 = MagicMock(spec=Query)
        q2 = MagicMock(spec=Query)
        q3 = MagicMock(spec=Query)
        q0.filter.return_value = q1
        q1.order_by.return_value = q2
        q2.limit.return_value = q3

        result = HybridQuery(q0).filter("x").order_by("y").limit(10)

        assert isinstance(result, HybridQuery)
        assert result._query is q3

    def test_non_query_return_value_is_not_wrapped(self):
        """方法返回值非 Query 时应原样透传（不套 HybridQuery）"""
        inner = MagicMock(spec=Query)
        inner.count.return_value = 42

        hq = HybridQuery(inner)
        assert hq.count() == 42

    def test_non_callable_attribute_is_passed_through(self):
        """非 callable 属性（如 ``statement``）直接返回原值"""
        inner = MagicMock(spec=Query)
        fake_stmt = object()
        inner.statement = fake_stmt

        hq = HybridQuery(inner)
        assert hq.statement is fake_stmt

    def test_missing_attribute_raises_attribute_error(self):
        """访问不存在的属性应正确抛 AttributeError（而非递归）"""
        inner = MagicMock(spec=Query)

        hq = HybridQuery(inner)
        with pytest.raises(AttributeError):
            hq.this_method_does_not_exist_on_sa_query_ever

    def test_repr_contains_inner_query(self):
        """``__repr__`` 应包含内部 Query 的 repr"""
        inner = MagicMock(spec=Query)
        inner.__repr__ = lambda self: "<FakeQuery>"

        hq = HybridQuery(inner)
        assert "HybridQuery(" in repr(hq)
        assert "<FakeQuery>" in repr(hq)


# ==================== session 属性透传 ====================

class TestSessionPassthrough:
    """验证 session 属性返回真实 Session（CoreModel 依赖此契约）"""

    def test_session_returns_real_session(self, memory_engine):
        SessionLocal = sessionmaker(bind=memory_engine)
        real_session: Session = SessionLocal()
        try:
            q = real_session.query(HQUser)
            hq = HybridQuery(q)

            assert hq.session is real_session
            assert not isinstance(hq.session, HybridQuery)
        finally:
            real_session.close()


# ==================== 同步上下文隐式终端透传（真实 Query） ====================

class TestSyncImplicitTerminalPassthrough:
    """同步上下文下，HybridQuery 的 __iter__ / __getitem__ / __bool__
    应 100% 复刻 SA Query 的原生行为"""

    def test_iter_works_in_sync(self, sa_query):
        """``for u in hq`` 同步正常迭代"""
        hq = HybridQuery(sa_query)
        users = list(hq)
        assert len(users) == 3
        assert {u.name for u in users} == {"Alice", "Bob", "Carol"}

    def test_bool_matches_sa_query(self, sa_query):
        """``bool(hq)`` 应与 ``bool(sa_query)`` 行为一致（同步透传契约）

        说明：SA 的 ``Query`` 对象本身不定义 ``__bool__``，故 ``bool(query)``
        一律为 True（是对象 truthy，不反映结果集是否为空）。
        HybridQuery 采取 Q 方案——同步上下文完全复刻 SA 行为，不做额外语义。
        """
        hq = HybridQuery(sa_query)
        assert bool(hq) is bool(sa_query)

        empty = sa_query.filter(HQUser.name == "NoBody")
        hq_empty = HybridQuery(empty)
        assert bool(hq_empty) is bool(empty)

    def test_getitem_index_works_in_sync(self, sa_query):
        """``hq[0]`` 同步取第一条"""
        ordered = sa_query.order_by(HQUser.age.asc())
        hq = HybridQuery(ordered)
        first = hq[0]
        assert first.name == "Bob"

    def test_getitem_slice_works_in_sync(self, sa_query):
        """``hq[0:2]`` 同步切片"""
        ordered = sa_query.order_by(HQUser.age.asc())
        hq = HybridQuery(ordered)
        top2 = hq[0:2]
        assert len(top2) == 2
        assert [u.name for u in top2] == ["Bob", "Alice"]


# ==================== async 上下文隐式终端拦截 ====================

class TestAsyncImplicitTerminalBlocked:
    """async 上下文下，__iter__ / __getitem__ / __bool__
    应抛 SynchronousOnlyOperation 并给出显式引导"""

    def test_iter_raises_in_async(self, sa_query):
        hq = HybridQuery(sa_query)

        async def _run():
            return list(hq)

        with pytest.raises(SynchronousOnlyOperation) as exc_info:
            asyncio.run(_run())

        assert "await query.all()" in str(exc_info.value)

    def test_bool_raises_in_async(self, sa_query):
        hq = HybridQuery(sa_query)

        async def _run():
            return bool(hq)

        with pytest.raises(SynchronousOnlyOperation) as exc_info:
            asyncio.run(_run())

        assert "await query.count() > 0" in str(exc_info.value)

    def test_getitem_raises_in_async(self, sa_query):
        hq = HybridQuery(sa_query)

        async def _run():
            return hq[0]

        with pytest.raises(SynchronousOnlyOperation) as exc_info:
            asyncio.run(_run())

        assert "await query.limit" in str(exc_info.value)


# ==================== allow_sync 与 YWEB_ASYNC_SAFETY=off 兜底 ====================

class TestAsyncBypass:
    """验证两个逃生口：allow_sync() 上下文管理器 & 全局关闭开关"""

    def test_allow_sync_bypasses_async_check(self, sa_query):
        """async 内 ``with allow_sync():`` 后，隐式终端不再抛错"""
        hq = HybridQuery(sa_query)

        async def _run():
            with allow_sync():
                return bool(hq)

        result = asyncio.run(_run())
        assert result is True

    def test_mode_off_bypasses_async_check(self, sa_query):
        """``YWEB_ASYNC_SAFETY=off`` 下，async 内直接迭代不抛错"""
        async_safety._mode = "off"
        hq = HybridQuery(sa_query)

        async def _run():
            return list(hq)

        users = asyncio.run(_run())
        assert len(users) == 3


# ==================== _HybridTerminal 占位 ====================

class TestHybridTerminalStub:
    """Phase 2 仅验证 _HybridTerminal 可构造；__await__/_run_sync 在 Phase 3"""

    def test_terminal_stores_thunk(self):
        thunk = lambda: [1, 2, 3]
        terminal = _HybridTerminal(thunk)
        assert terminal._thunk is thunk
