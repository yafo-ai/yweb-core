"""测试 CacheInvalidator 增量事件注册

验证 CacheInvalidator.register() 支持对同一 Model 多次注册不同事件，
每次注册的新事件都能正确设置 SQLAlchemy 监听器。

修复前 bug:
    _setup_listeners 只在 Model 首次注册时执行，后续注册的新事件被忽略。

修复方案:
    将 _listened_models: Set[Type] 改为 _listened_events: Dict[Type, Set[str]]，
    按事件粒度跟踪，支持增量注册。
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


# ==================== 单元测试：验证增量注册机制 ====================


class TestIncrementalEventRegistration:
    """验证 _listened_events 按事件粒度跟踪"""

    def test_new_events_trigger_listener_setup(self):
        """第二次注册带新事件时，_setup_listeners_for_events 应被调用"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        @cached(ttl=10)
        def func_b(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events") as mock_setup:
            # 第一次注册：默认事件
            invalidator.register(DummyModel, func_a)
            assert mock_setup.call_count == 1
            # 第一次调用参数应包含 after_update 和 after_delete
            first_call_events = mock_setup.call_args_list[0][0][1]
            assert first_call_events == {"after_update", "after_delete"}

            # 第二次注册：带新事件 after_insert
            invalidator.register(
                DummyModel, func_b, events=("after_insert",)
            )
            # 应为新事件再次调用
            assert mock_setup.call_count == 2
            second_call_events = mock_setup.call_args_list[1][0][1]
            assert second_call_events == {"after_insert"}

    def test_duplicate_events_do_not_trigger_setup(self):
        """重复注册相同事件时，不会重复设置监听器"""
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

            # 第二次注册：相同事件 → 不应再调用
            invalidator.register(DummyModel, func_b)
            assert mock_setup.call_count == 1

    def test_listened_events_tracks_per_event(self):
        """_listened_events 以事件为粒度跟踪"""
        invalidator = CacheInvalidator()

        @cached(ttl=10)
        def func_a(uid: int):
            return uid

        @cached(ttl=10)
        def func_b(uid: int):
            return uid

        DummyModel = type("DummyModel", (), {})

        with patch.object(invalidator, "_setup_listeners_for_events"):
            invalidator.register(DummyModel, func_a)

        # 首次注册后，记录了两个事件
        assert invalidator._listened_events[DummyModel] == {"after_update", "after_delete"}

        with patch.object(invalidator, "_setup_listeners_for_events"):
            invalidator.register(
                DummyModel, func_b, events=("after_insert",)
            )

        # 增量注册后，三个事件都被记录
        assert invalidator._listened_events[DummyModel] == {
            "after_update", "after_delete", "after_insert"
        }


# ==================== 集成测试：真实 SQLAlchemy 事件 ====================


class TestIncrementalRegistrationIntegration:
    """使用真实 SQLAlchemy 模型验证增量注册的实际行为"""

    def test_after_insert_triggered_when_registered_second(self, db_env):
        """after_insert 在第二次注册时也能正常触发"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def get_user(uid: int):
            return {"id": uid}

        @cached(ttl=60)
        def get_detail(uid: int):
            return {"id": uid}

        # 第一次注册：默认事件 (after_update, after_delete)
        invalidator.register(UserModel, get_user)

        # 第二次注册：包含 after_insert
        invalidator.register(
            UserModel, get_detail, events=("after_insert",)
        )

        triggered = _spy_invalidate(invalidator)

        # 插入新用户
        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        assert "after_insert" in triggered

    def test_after_update_still_works(self, db_env):
        """after_update 在首次注册中设置，不受增量注册影响"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def get_user(uid: int):
            return {"id": uid}

        invalidator.register(UserModel, get_user)

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        user.name = "Alice Updated"
        session.flush()

        assert "after_update" in triggered

    def test_after_insert_works_when_in_first_register(self, db_env):
        """after_insert 在首次注册中仍然正常工作"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def get_user(uid: int):
            return {"id": uid}

        invalidator.register(
            UserModel, get_user,
            events=("after_update", "after_delete", "after_insert"),
        )

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        assert "after_insert" in triggered

    def test_all_events_from_separate_registers(self, db_env):
        """不同注册的事件最终都能正常触发"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def func_a(uid: int):
            return uid

        @cached(ttl=60)
        def func_b(uid: int):
            return uid

        # 首次注册：只 after_update
        invalidator.register(
            UserModel, func_a, events=("after_update",)
        )

        # 第二次注册：只 after_delete
        invalidator.register(
            UserModel, func_b, events=("after_delete",)
        )

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        user.name = "Updated"
        session.flush()

        session.delete(user)
        session.flush()

        assert "after_update" in triggered
        assert "after_delete" in triggered

    def test_cache_invalidated_on_insert_via_second_register(self, db_env):
        """第二次注册的 after_insert 能正确失效缓存"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        call_count = 0

        @cached(ttl=60)
        def get_user(uid: int):
            return {"id": uid}

        @cached(ttl=60)
        def get_detail(uid: int):
            nonlocal call_count
            call_count += 1
            return {"id": uid, "name": "cached"}

        # 第一次注册：默认事件
        invalidator.register(UserModel, get_user)

        # 第二次注册：after_insert
        invalidator.register(
            UserModel, get_detail, events=("after_insert",)
        )

        # 预缓存 uid=1
        get_detail(1)
        assert call_count == 1
        get_detail(1)
        assert call_count == 1  # 缓存命中

        # 插入 uid=1 的用户 → after_insert 触发 → get_detail(1) 缓存失效
        user = UserModel(id=1, name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()

        get_detail(1)
        assert call_count == 2  # 缓存已失效，重新调用

    def test_all_three_events_via_single_register(self, db_env):
        """单次注册三种事件，全部正常触发"""
        UserModel, session = db_env
        invalidator = CacheInvalidator()

        @cached(ttl=60)
        def get_user(uid: int):
            return {"id": uid}

        invalidator.register(
            UserModel, get_user,
            events=("after_update", "after_delete", "after_insert"),
        )

        triggered = _spy_invalidate(invalidator)

        user = UserModel(name="Alice", email="alice@test.com")
        session.add(user)
        session.flush()
        assert "after_insert" in triggered

        user.name = "Updated"
        session.flush()
        assert "after_update" in triggered

        session.delete(user)
        session.flush()
        assert "after_delete" in triggered
