"""HybridQuery 终端方法单元测试（Phase 3）

验收范围：
    1. 10 个终端方法，每个同步 + async 路径各一个 case
       (all / first / one / one_or_none / scalar / count /
        get / delete / update / paginate)
    2. _HybridTerminal 一次性消费：二次 await 或 _run_sync 抛 RuntimeError
    3. _HybridTerminal.__await__ 真的跳到另一个线程（线程池执行）
    4. paginate 专项：参数 / 总数 / 列表长度 / Page 类型
    5. allow_sync / YWEB_ASYNC_SAFETY=off 下 async 也走同步分支

Phase 3 不测 CoreModel.query 接入（Phase 4）。
"""

from __future__ import annotations

import asyncio
import threading

import pytest
from sqlalchemy import Column, Integer, String, func
from sqlalchemy.orm import Query, sessionmaker
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound

from yweb.orm import BaseModel, allow_sync
from yweb.orm import async_safety
from yweb.orm.async_safety import SynchronousOnlyOperation
from yweb.orm.hybrid_query import HybridQuery, _HybridTerminal


# ==================== 测试模型 ====================

class HQTUser(BaseModel):
    __tablename__ = "hq_terminal_test_users"
    __table_args__ = {"extend_existing": True}

    email = Column(String(200))
    age = Column(Integer)


# ==================== Fixtures ====================

@pytest.fixture
def seeded_session(memory_engine):
    """准备 3 条数据，返回 (session, query_factory)"""
    BaseModel.metadata.create_all(bind=memory_engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session = SessionLocal()
    try:
        session.add_all([
            HQTUser(name="Alice", email="a@t", age=30),
            HQTUser(name="Bob", email="b@t", age=25),
            HQTUser(name="Carol", email="c@t", age=35),
        ])
        session.commit()
        yield session
    finally:
        session.close()


@pytest.fixture
def hq(seeded_session):
    return HybridQuery(seeded_session.query(HQTUser))


@pytest.fixture(autouse=True)
def reset_async_safety_mode():
    original = async_safety._mode
    yield
    async_safety._mode = original


# ==================== 同步路径 —— 10 个终端方法 ====================

class TestSyncTerminals:
    """同步上下文下，每个终端方法立即求值返回原生结果（不返回 _HybridTerminal）"""

    def test_all_returns_list(self, hq):
        result = hq.all()
        assert isinstance(result, list)
        assert len(result) == 3

    def test_first_returns_model_or_none(self, hq):
        result = hq.filter(HQTUser.name == "Alice").first()
        assert isinstance(result, HQTUser)
        assert result.name == "Alice"

        none_result = hq.filter(HQTUser.name == "NoBody").first()
        assert none_result is None

    def test_one_returns_single(self, hq):
        result = hq.filter(HQTUser.name == "Alice").one()
        assert result.name == "Alice"

    def test_one_raises_when_not_exactly_one(self, hq):
        with pytest.raises(NoResultFound):
            hq.filter(HQTUser.name == "NoBody").one()
        with pytest.raises(MultipleResultsFound):
            hq.one()

    def test_one_or_none_returns_single_or_none(self, hq):
        assert hq.filter(HQTUser.name == "Alice").one_or_none().name == "Alice"
        assert hq.filter(HQTUser.name == "NoBody").one_or_none() is None

    def test_scalar_returns_primitive(self, seeded_session):
        count_q = seeded_session.query(func.count(HQTUser.id))
        result = HybridQuery(count_q).scalar()
        assert result == 3

    def test_count_returns_int(self, hq):
        assert hq.count() == 3
        assert hq.filter(HQTUser.age > 28).count() == 2

    def test_get_returns_by_pk(self, hq, seeded_session):
        first_row = seeded_session.query(HQTUser).order_by(HQTUser.id.asc()).first()
        import warnings
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            result = hq.get(first_row.id)
        assert result.id == first_row.id

    def test_delete_returns_affected_rows(self, hq, seeded_session):
        affected = hq.filter(HQTUser.age < 28).delete(synchronize_session=False)
        seeded_session.commit()
        assert affected == 1
        assert seeded_session.query(HQTUser).count() == 2

    def test_update_returns_affected_rows(self, hq, seeded_session):
        affected = hq.filter(HQTUser.age >= 30).update(
            {"email": "senior@t"}, synchronize_session=False
        )
        seeded_session.commit()
        assert affected == 2
        emails = {u.email for u in seeded_session.query(HQTUser).filter(HQTUser.age >= 30).all()}
        assert emails == {"senior@t"}

    def test_paginate_returns_page(self, hq):
        page = hq.paginate(page=1, page_size=2)

        assert page.total_records == 3
        assert page.page == 1
        assert page.page_size == 2
        assert page.total_pages == 2
        assert len(page.rows) == 2

    def test_paginate_second_page(self, hq):
        page = hq.paginate(page=2, page_size=2)

        assert page.page == 2
        assert len(page.rows) == 1


# ==================== async 路径 —— 10 个终端方法 ====================

class TestAsyncTerminals:
    """async 上下文下，每个终端方法返回可 await 的 _HybridTerminal"""

    def test_all_async(self, hq):
        async def _run():
            result = hq.all()
            assert isinstance(result, _HybridTerminal)
            return await result

        users = asyncio.run(_run())
        assert len(users) == 3

    def test_first_async(self, hq):
        async def _run():
            t = hq.filter(HQTUser.name == "Alice").first()
            assert isinstance(t, _HybridTerminal)
            return await t

        user = asyncio.run(_run())
        assert user.name == "Alice"

    def test_one_async(self, hq):
        async def _run():
            return await hq.filter(HQTUser.name == "Bob").one()

        user = asyncio.run(_run())
        assert user.name == "Bob"

    def test_one_or_none_async(self, hq):
        async def _run():
            return await hq.filter(HQTUser.name == "NoBody").one_or_none()

        result = asyncio.run(_run())
        assert result is None

    def test_scalar_async(self, seeded_session):
        async def _run():
            count_q = seeded_session.query(func.count(HQTUser.id))
            return await HybridQuery(count_q).scalar()

        assert asyncio.run(_run()) == 3

    def test_count_async(self, hq):
        async def _run():
            return await hq.count()

        assert asyncio.run(_run()) == 3

    def test_get_async(self, hq, seeded_session):
        first_row = seeded_session.query(HQTUser).first()

        async def _run():
            import warnings
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                return await hq.get(first_row.id)

        result = asyncio.run(_run())
        assert result.id == first_row.id

    def test_delete_async(self, hq, seeded_session):
        async def _run():
            return await hq.filter(HQTUser.age < 28).delete(synchronize_session=False)

        affected = asyncio.run(_run())
        seeded_session.commit()
        assert affected == 1

    def test_update_async(self, hq, seeded_session):
        async def _run():
            return await hq.filter(HQTUser.age >= 30).update(
                {"email": "senior@t"}, synchronize_session=False
            )

        affected = asyncio.run(_run())
        seeded_session.commit()
        assert affected == 2

    def test_paginate_async(self, hq):
        async def _run():
            t = hq.paginate(page=1, page_size=2)
            assert isinstance(t, _HybridTerminal)
            return await t

        page = asyncio.run(_run())
        assert page.total_records == 3
        assert len(page.rows) == 2


# ==================== _HybridTerminal 一次性消费 ====================

class TestTerminalOneShot:
    """终端对象只能消费一次（doc 22 §7.3.9）"""

    def test_second_await_raises(self):
        calls = []
        terminal = _HybridTerminal(lambda: calls.append(1) or "ok")

        async def _run():
            first = await terminal
            with pytest.raises(RuntimeError, match="already consumed"):
                await terminal
            return first

        result = asyncio.run(_run())
        assert result == "ok"
        assert len(calls) == 1

    def test_second_run_sync_raises(self):
        calls = []
        terminal = _HybridTerminal(lambda: calls.append(1) or "ok")

        assert terminal._run_sync() == "ok"
        with pytest.raises(RuntimeError, match="already consumed"):
            terminal._run_sync()
        assert len(calls) == 1

    def test_mixed_await_then_run_sync_raises(self):
        """先 await 后 _run_sync 也算重复消费"""
        terminal = _HybridTerminal(lambda: "ok")

        async def _run():
            await terminal

        asyncio.run(_run())
        with pytest.raises(RuntimeError, match="already consumed"):
            terminal._run_sync()


# ==================== __await__ 跑在线程池（不阻塞事件循环） ====================

class TestTerminalThreadpool:
    """验证 await 真的把 thunk 调度到其他线程"""

    def test_await_executes_in_different_thread(self):
        main_thread_id = threading.get_ident()
        captured = {}

        def thunk():
            captured["thread_id"] = threading.get_ident()
            return 42

        terminal = _HybridTerminal(thunk)

        async def _run():
            return await terminal

        result = asyncio.run(_run())

        assert result == 42
        assert "thread_id" in captured
        assert captured["thread_id"] != main_thread_id


# ==================== bypass：allow_sync / YWEB_ASYNC_SAFETY=off ====================

class TestAsyncBypassInTerminals:
    """bypass 下 async 也走同步分支：终端直接返回原生结果，不再是 _HybridTerminal"""

    def test_allow_sync_makes_terminal_return_native(self, hq):
        async def _run():
            with allow_sync():
                result = hq.all()
            assert not isinstance(result, _HybridTerminal)
            assert isinstance(result, list)
            return result

        users = asyncio.run(_run())
        assert len(users) == 3

    def test_mode_off_makes_terminal_return_native(self, hq):
        async_safety._mode = "off"

        async def _run():
            result = hq.count()
            assert not isinstance(result, _HybridTerminal)
            return result

        assert asyncio.run(_run()) == 3


# ==================== Phase 3.3 A2：async 忘 await 让错误显形 ====================

class TestA2MissingAwait:
    """async 中忘记 await，拿到的是 _HybridTerminal 对象；
    下一步操作（迭代 / 属性 / 算术）会因为类型不符自然抛 TypeError。"""

    def test_forgetting_await_and_iterating_raises(self, hq):
        async def _run():
            result = hq.all()
            with pytest.raises(TypeError):
                for _ in result:
                    pass

        asyncio.run(_run())

    def test_forgetting_await_on_count_and_compare_raises(self, hq):
        async def _run():
            result = hq.count()
            with pytest.raises(TypeError):
                _ = result + 1

        asyncio.run(_run())
