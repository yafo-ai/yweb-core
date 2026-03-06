"""ORM 对象缓存测试

测试 @cached(orm_model=...) 的 Session merge 机制、
expire_on_commit 保护（pickle 快照）、
cache_invalidator 的 watch_relationships（M2M 集合变更失效）。
"""

import pytest
from unittest.mock import MagicMock, patch, PropertyMock
from types import SimpleNamespace

from yweb.cache import cached, CacheInvalidator
from yweb.cache.backends import MemoryBackend


class TestCachedOrmModel:
    """测试 @cached 的 orm_model 参数"""

    def test_cache_hit_calls_ensure_session(self):
        """缓存命中时应调用 _ensure_session 处理 detached 对象"""
        fake_db = {1: SimpleNamespace(id=1, name="Alice")}

        cf = cached(ttl=60, orm_model=object)(
            lambda uid: fake_db.get(uid)
        )

        with patch.object(cf, '_ensure_session', wraps=cf._ensure_session) as spy:
            cf(1)  # cache miss
            assert spy.call_count == 0

            cf(1)  # cache hit
            assert spy.call_count == 1

    def test_ensure_session_merges_detached_object(self):
        """_ensure_session 应对 detached 对象执行 merge"""
        mock_model = MagicMock()
        mock_session = MagicMock()
        mock_model.query.session = mock_session

        merged_user = SimpleNamespace(id=1, name="merged")
        mock_session.merge.return_value = merged_user

        cf = cached(ttl=60, orm_model=mock_model)(lambda uid: SimpleNamespace(id=uid))

        with patch('sqlalchemy.orm.session.object_session', return_value=None):
            cf(1)  # cache miss
            result = cf(1)  # cache hit → _ensure_session → merge

        mock_session.merge.assert_called_once()
        assert mock_session.merge.call_args[1] == {'load': False}
        assert result is merged_user

    def test_ensure_session_skips_when_already_attached(self):
        """对象已在 Session 中时不应 merge"""
        mock_model = MagicMock()
        user = SimpleNamespace(id=1)

        cf = cached(ttl=60, orm_model=mock_model)(lambda uid: user)

        with patch('sqlalchemy.orm.session.object_session', return_value=MagicMock()):
            cf(1)
            result = cf(1)

        mock_model.query.session.merge.assert_not_called()
        assert result.id == user.id

    def test_no_orm_model_returns_raw_value(self):
        """不指定 orm_model 时直接返回缓存值"""
        cf = cached(ttl=60)(lambda uid: SimpleNamespace(id=uid))

        cf(1)
        result = cf(1)
        assert result.id == 1


class TestExpireOnCommitProtection:
    """测试 Memory 后端 + orm_model 的 pickle 快照保护"""

    def test_cached_copy_independent_of_original(self):
        """缓存的副本应是独立对象，修改原始不影响缓存"""
        call_count = 0

        @cached(ttl=60, orm_model=object)
        def get_item(item_id: int):
            nonlocal call_count
            call_count += 1
            obj = SimpleNamespace(id=item_id, name="original")
            return obj

        result1 = get_item(1)
        assert result1.name == "original"

        cached_obj = get_item._backend.get(get_item._build_key((1,), {}))
        assert cached_obj is not result1, "缓存应存储独立副本，而非原始引用"
        assert cached_obj.name == "original"

    def test_expire_on_commit_simulation(self):
        """模拟 expire_on_commit 清空原始 __dict__ 后缓存仍可用"""
        call_count = 0
        original_ref = None

        @cached(ttl=60, orm_model=object)
        def get_item(item_id: int):
            nonlocal call_count, original_ref
            call_count += 1
            obj = SimpleNamespace(id=item_id, name="alice", score=100)
            original_ref = obj
            return obj

        get_item(1)
        assert call_count == 1

        # 模拟 expire_on_commit: SQLAlchemy 会 pop 掉 __dict__ 中的属性值
        original_ref.__dict__.pop("name", None)
        original_ref.__dict__.pop("score", None)

        # 缓存命中 — 应返回 pickle 快照（属性完整）
        result = get_item(1)
        assert call_count == 1, "应命中缓存，不重新查询"
        assert result.name == "alice"
        assert result.score == 100

    def test_no_orm_model_stores_reference(self):
        """不指定 orm_model 时应存储引用（原始行为）"""
        @cached(ttl=60)
        def get_item(item_id: int):
            return SimpleNamespace(id=item_id, name="ref")

        result = get_item(1)
        cached_obj = get_item._backend.get(get_item._build_key((1,), {}))
        assert cached_obj is result, "无 orm_model 时应存储原始引用"

    def test_snapshot_preserves_nested_collections(self):
        """pickle 快照应保留嵌套集合（模拟 eager-loaded relationships）"""
        @cached(ttl=60, orm_model=object)
        def get_user(uid: int):
            roles = [SimpleNamespace(id=1, name="admin"), SimpleNamespace(id=2, name="editor")]
            return SimpleNamespace(id=uid, username="alice", roles=roles)

        get_user(1)

        cached_obj = get_user._backend.get(get_user._build_key((1,), {}))
        assert len(cached_obj.roles) == 2
        assert cached_obj.roles[0].name == "admin"
        assert cached_obj.roles[1].name == "editor"


class TestWatchRelationships:
    """测试 cache_invalidator 的 watch_relationships 功能"""

    def _make_m2m_model(self):
        """构造带 ManyToMany 关系的模拟模型"""
        mock_rel = MagicMock()
        mock_rel.secondary = MagicMock()  # 非 None → ManyToMany
        mock_rel.key = "roles"

        mock_mapper = MagicMock()
        mock_mapper.relationships = [mock_rel]

        mock_model = MagicMock()
        mock_model.__name__ = "FakeUser"
        mock_model.roles = MagicMock()

        return mock_model, mock_mapper

    def test_m2m_append_triggers_invalidation(self):
        """M2M 集合 append 应触发缓存失效"""
        invalidator = CacheInvalidator()
        mock_model, mock_mapper = self._make_m2m_model()
        call_count = 0

        @cached(ttl=60)
        def get_obj(obj_id: int):
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(id=obj_id)

        from sqlalchemy import event
        with patch('sqlalchemy.inspect', return_value=mock_mapper):
            with patch.object(event, 'listen') as mock_listen:
                invalidator.register(mock_model, get_obj, watch_relationships=True)

                append_calls = [
                    c for c in mock_listen.call_args_list
                    if c[0][1] == "append"
                ]
                remove_calls = [
                    c for c in mock_listen.call_args_list
                    if c[0][1] == "remove"
                ]
                assert len(append_calls) == 1, "应注册 append 监听器"
                assert len(remove_calls) == 1, "应注册 remove 监听器"

    def test_collection_change_bypasses_event_filter(self):
        """collection_change 事件应绕过注册时的 events 过滤"""
        invalidator = CacheInvalidator()
        call_count = 0

        @cached(ttl=60)
        def get_obj(obj_id: int):
            nonlocal call_count
            call_count += 1
            return SimpleNamespace(id=obj_id)

        # 只注册 after_update 事件
        invalidator._registrations[object] = [{
            "func": get_obj,
            "key_extractor": lambda o: o.id,
            "events": ("after_update",),
        }]

        get_obj(1)
        assert call_count == 1

        # collection_change 不在 events 里，但仍应触发失效
        invalidator._invalidate_for_target(
            object, SimpleNamespace(id=1), "collection_change"
        )
        get_obj(1)
        assert call_count == 2, "collection_change 应绕过事件过滤，触发失效"

    def test_no_m2m_relations_no_listeners(self):
        """无 ManyToMany 关系时不应注册集合监听器"""
        invalidator = CacheInvalidator()

        mock_rel = MagicMock()
        mock_rel.secondary = None  # OneToMany，不是 M2M

        mock_mapper = MagicMock()
        mock_mapper.relationships = [mock_rel]

        mock_model = MagicMock()
        mock_model.__name__ = "Article"

        @cached(ttl=60)
        def get_article(aid: int):
            return SimpleNamespace(id=aid)

        from sqlalchemy import event
        with patch('sqlalchemy.inspect', return_value=mock_mapper):
            with patch.object(event, 'listen') as mock_listen:
                invalidator.register(mock_model, get_article, watch_relationships=True)

                collection_calls = [
                    c for c in mock_listen.call_args_list
                    if c[0][1] in ("append", "remove")
                ]
                assert len(collection_calls) == 0, "OneToMany 不应注册集合监听器"

    def test_watch_relationships_default_true(self):
        """watch_relationships 默认值应为 True"""
        invalidator = CacheInvalidator()
        mock_model, mock_mapper = self._make_m2m_model()

        @cached(ttl=60)
        def get_obj(obj_id: int):
            return SimpleNamespace(id=obj_id)

        from sqlalchemy import event
        with patch('sqlalchemy.inspect', return_value=mock_mapper):
            with patch.object(event, 'listen') as mock_listen:
                # 不显式传 watch_relationships，默认应为 True
                invalidator.register(mock_model, get_obj)

                append_calls = [
                    c for c in mock_listen.call_args_list
                    if c[0][1] == "append"
                ]
                assert len(append_calls) == 1, "默认应注册 M2M 集合监听器"

    def test_watch_relationships_false_skips(self):
        """显式 watch_relationships=False 时不应注册集合监听器"""
        invalidator = CacheInvalidator()
        mock_model, mock_mapper = self._make_m2m_model()

        @cached(ttl=60)
        def get_obj(obj_id: int):
            return SimpleNamespace(id=obj_id)

        from sqlalchemy import event
        with patch('sqlalchemy.inspect', return_value=mock_mapper):
            with patch.object(event, 'listen') as mock_listen:
                invalidator.register(
                    mock_model, get_obj, watch_relationships=False
                )

                collection_calls = [
                    c for c in mock_listen.call_args_list
                    if c[0][1] in ("append", "remove")
                ]
                assert len(collection_calls) == 0
