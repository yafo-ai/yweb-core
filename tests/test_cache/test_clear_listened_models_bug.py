"""测试 CacheInvalidator.clear() 后重新注册的行为

验证 clear() 后重新注册同一 Model 时，新事件类型能正确注册监听器。

修复方案（方案 A）:
    _listened_events 在 clear() 时故意不清空。
    旧 SQLAlchemy 监听器保留（_registrations 为空时是无害 no-op），
    新事件通过 set 差集检测后增量注册。
"""

import pytest
from unittest.mock import patch

from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from sqlalchemy.pool import StaticPool

from yweb.cache import cached, CacheInvalidator


# ==================== Fixtures ====================


@pytest.fixture
def db_env():
    """每个测试创建完全隔离的 DB 环境（独立 Base + Model + Session）"""
    base = declarative_base()

    class UserModel(base):
        __tablename__ = "users"
        id = Column(Integer, primary_key=True, autoincrement=True)
        name = Column(String(50))
        email = Column(String(100))

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False)()

    yield UserModel, session

    session.close()
    engine.dispose()


# ==================== 辅助函数 ====================


def _spy_invalidate(invalidator):
    """为 invalidator 安装 spy，返回事件记录列表"""
    triggered_events = []
    original = invalidator._invalidate_for_target

    def spy(model, target, event_name):
        triggered_events.append(event_name)
        original(model, target, event_name)

    invalidator._invalidate_for_target = spy
    return triggered_events


# ==================== 单元测试：clear() 内部状态 ====================


class TestClearInternalState:
    """验证 clear() 对内部状态的影响"""

    def test_registrations_cleared_after_clear(self):
        """clear() 正确清空 _registrations"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events"):
            invalidator.register(DummyModel, func_a)

        assert len(invalidator.get_registrations()) > 0

        invalidator.clear()

        assert len(invalidator.get_registrations()) == 0

    def test_listened_events_retained_after_clear(self):
        """clear() 后 _listened_events 保留（方案 A 设计：旧监听器做 no-op）"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events"):
            invalidator.register(DummyModel, func_a)

        assert DummyModel in invalidator._listened_events

        invalidator.clear()

        # _listened_events 保留 → 重新注册相同事件不会创建重复监听器
        assert DummyModel in invalidator._listened_events

    def test_new_event_after_clear_can_be_registered(self):
        """clear() 后注册新事件类型，增量注册机制仍正常工作"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        @cached(ttl=10)
        def func_b(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events") as mock_setup:
            # 首次注册：after_update, after_delete
            invalidator.register(DummyModel, func_a)
            assert mock_setup.call_count == 1

            # 清空
            invalidator.clear()

            # 重新注册：包含新事件 after_insert
            invalidator.register(
                DummyModel, func_b,
                events=("after_update", "after_delete", "after_insert"),
            )
            # after_insert 是新事件 → _setup_listeners_for_events 被调用
            assert mock_setup.call_count == 2
            new_events = mock_setup.call_args_list[1][0][1]
            assert new_events == {"after_insert"}

    def test_same_event_after_clear_no_duplicate_listener(self):
        """clear() 后注册相同事件，不会创建重复监听器"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        @cached(ttl=10)
        def func_b(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events") as mock_setup:
            invalidator.register(DummyModel, func_a)
            assert mock_setup.call_count == 1

            invalidator.clear()

            # 注册完全相同的事件 → 不创建重复监听器
            invalidator.register(DummyModel, func_b)
            assert mock_setup.call_count == 1  # 未增加


# ==================== 集成测试：clear() + 重新注册 ====================


class TestClearAndReregisterIntegration:
    """集成测试：clear() 后重新注册的实际行为"""

    def test_new_event_works_after_clear(self, db_env):
        """clear() 后注册新事件类型，新事件正常触发"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def func_v1(uid: int):
            return {"id": uid, "version": 1}

        # V1：默认事件
        invalidator.register(UserModel, func_v1)

        # 清空
        invalidator.clear()

        @cached(ttl=60)
        def func_v2(uid: int):
            return {"id": uid, "version": 2}

        # V2：需要 after_insert
        invalidator.register(
            UserModel, func_v2, events=("after_insert",)
        )

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        assert "after_insert" in triggered

    def test_same_event_after_clear_still_works(self, db_env):
        """clear() 后用相同事件重新注册，旧监听器仍有效"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def func_v1(uid: int):
            return {"id": uid, "version": 1}

        invalidator.register(UserModel, func_v1)

        invalidator.clear()

        call_count = 0

        @cached(ttl=60)
        def func_v2(uid: int):
            nonlocal call_count
            call_count += 1
            return {"id": uid, "version": 2}

        invalidator.register(UserModel, func_v2)

        # 创建用户并缓存
        user = UserModel(id=1, name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        func_v2(1)
        assert call_count == 1
        func_v2(1)
        assert call_count == 1  # 缓存命中

        triggered = _spy_invalidate(invalidator)

        # UPDATE → 旧监听器触发，新注册被处理
        user.name = "Alice Updated"
        session.flush()

        assert "after_update" in triggered
        func_v2(1)
        assert call_count == 2  # 缓存已失效

    def test_full_reconfigure_with_new_events(self, db_env):
        """V1 → clear → V2（增加 after_insert）→ 所有事件都正常工作"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def func_v1(uid: int):
            return uid

        invalidator.register(UserModel, func_v1)

        invalidator.clear()

        @cached(ttl=60)
        def func_v2(uid: int):
            return uid

        invalidator.register(
            UserModel, func_v2,
            events=("after_update", "after_delete", "after_insert"),
        )

        triggered = _spy_invalidate(invalidator)

        # INSERT
        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()
        assert "after_insert" in triggered

        # UPDATE
        user.name = "Bob"
        session.flush()
        assert "after_update" in triggered

        # DELETE
        session.delete(user)
        session.flush()
        assert "after_delete" in triggered


# ==================== 边界场景 ====================


class TestClearEdgeCases:
    """clear() 相关的边界场景"""

    def test_multiple_clear_and_reregister(self, db_env):
        """多次 clear + 重新注册后，新事件类型能正常工作"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        # 第一轮：只有 after_update
        @cached(ttl=60)
        def func_round1(uid: int):
            return uid

        invalidator.register(
            UserModel, func_round1, events=("after_update",)
        )

        # 第二轮
        invalidator.clear()

        @cached(ttl=60)
        def func_round2(uid: int):
            return uid

        invalidator.register(
            UserModel, func_round2,
            events=("after_update", "after_insert"),
        )

        # 第三轮
        invalidator.clear()

        @cached(ttl=60)
        def func_round3(uid: int):
            return uid

        invalidator.register(
            UserModel, func_round3,
            events=("after_update", "after_insert"),
        )

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Test", email="test@test.com")
        session.add(user)
        session.flush()

        # 多次 clear 后 after_insert 仍然正常
        assert "after_insert" in triggered

        user.name = "Updated"
        session.flush()
        assert "after_update" in triggered

    def test_clear_is_safe_no_crash(self, db_env):
        """clear() 后旧 handler 不会因 _registrations 为空而崩溃"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def func_a(uid: int):
            return uid

        invalidator.register(UserModel, func_a)

        invalidator.clear()

        # INSERT + UPDATE → 旧 handler 触发但不应崩溃
        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        user.name = "Updated"
        session.flush()

        # 无异常 → 旧 handler 安全地成为 no-op
