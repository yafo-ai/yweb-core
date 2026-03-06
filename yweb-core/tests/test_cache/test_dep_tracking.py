"""依赖追踪缓存失效测试

测试 cache_invalidator 的反向索引机制：
缓存写入时自动扫描结果中的实体，实体变更时精确失效包含该实体的缓存条目。
"""

from dataclasses import dataclass, field
from typing import List
from types import SimpleNamespace

from yweb.cache import cached, CacheInvalidator
from yweb.cache.invalidation import _extract_entities


@dataclass
class OrderEntity:
    id: int
    user_id: int
    amount: float


@dataclass
class PageResult:
    """模拟分页对象"""
    items: list
    total: int = 0


class TestExtractEntities:
    """测试 _extract_entities 扫描函数"""

    def test_single_entity(self):
        o = OrderEntity(id=1, user_id=1, amount=10.0)
        result = _extract_entities(o, {OrderEntity})
        assert result == [(OrderEntity, 1)]

    def test_list_of_entities(self):
        orders = [OrderEntity(id=i, user_id=1, amount=i * 10.0) for i in range(1, 4)]
        result = _extract_entities(orders, {OrderEntity})
        assert len(result) == 3
        assert (OrderEntity, 2) in result

    def test_page_result(self):
        items = [OrderEntity(id=1, user_id=1, amount=10.0)]
        page = PageResult(items=items, total=1)
        result = _extract_entities(page, {OrderEntity})
        assert result == [(OrderEntity, 1)]

    def test_unregistered_model_ignored(self):
        o = OrderEntity(id=1, user_id=1, amount=10.0)
        result = _extract_entities(o, set())
        assert result == []

    def test_none_returns_empty(self):
        assert _extract_entities(None, {OrderEntity}) == []


class TestDependencyTracking:
    """测试列表查询的依赖追踪失效"""

    def setup_method(self):
        self.invalidator = CacheInvalidator()

    def test_list_cache_invalidated_on_entity_change(self):
        """列表缓存中某一项变更时，该缓存条目应被失效"""
        call_count = 0
        orders_db = [
            OrderEntity(id=1, user_id=1, amount=100),
            OrderEntity(id=2, user_id=1, amount=200),
            OrderEntity(id=3, user_id=2, amount=300),
        ]

        @cached(ttl=60)
        def get_orders(user_id: int):
            nonlocal call_count
            call_count += 1
            return [o for o in orders_db if o.user_id == user_id]

        self.invalidator.register(OrderEntity, get_orders)

        # 首次调用：cache miss
        result = get_orders(1)
        assert call_count == 1
        assert len(result) == 2

        # 手动注册依赖（模拟 invalidate_on 自动触发的 track_dependencies）
        cache_key = get_orders._build_key((1,), {})
        self.invalidator.track_dependencies(get_orders, cache_key, result)

        # 再次调用：cache hit
        get_orders(1)
        assert call_count == 1

        # 模拟 Order(id=2) 被更新 → 触发反向索引失效
        self.invalidator._invalidate_for_target(
            OrderEntity, orders_db[1], "after_update"
        )

        # 再次调用：cache miss（被失效了）
        get_orders(1)
        assert call_count == 2

    def test_unrelated_entity_change_does_not_invalidate(self):
        """不在缓存结果中的实体变更，不应影响该缓存"""
        call_count = 0
        orders_db = [
            OrderEntity(id=1, user_id=1, amount=100),
            OrderEntity(id=99, user_id=99, amount=999),
        ]

        @cached(ttl=60)
        def get_user1_orders():
            nonlocal call_count
            call_count += 1
            return [orders_db[0]]

        self.invalidator.register(OrderEntity, get_user1_orders)

        get_user1_orders()
        assert call_count == 1

        cache_key = get_user1_orders._build_key((), {})
        self.invalidator.track_dependencies(
            get_user1_orders, cache_key, [orders_db[0]]
        )

        # Order(id=99) 变更 → 不应影响 user1 的缓存
        self.invalidator._invalidate_for_target(
            OrderEntity, orders_db[1], "after_update"
        )

        get_user1_orders()
        assert call_count == 1, "不相关实体变更不应导致缓存失效"

    def test_single_entity_still_works_via_key_extractor(self):
        """单实体查询仍通过 key_extractor 精确失效（路径 1）"""
        call_count = 0

        @cached(ttl=60)
        def get_order(order_id: int):
            nonlocal call_count
            call_count += 1
            return OrderEntity(id=order_id, user_id=1, amount=100)

        self.invalidator.register(OrderEntity, get_order)

        get_order(1)
        assert call_count == 1
        get_order(1)
        assert call_count == 1

        # key_extractor 路径：Order(id=1) 变更 → invalidate(1)
        self.invalidator._invalidate_for_target(
            OrderEntity, OrderEntity(id=1, user_id=1, amount=100), "after_update"
        )

        get_order(1)
        assert call_count == 2

    def test_entity_in_multiple_caches(self):
        """同一实体出现在多个缓存条目中，变更时应全部失效"""
        calls_a = 0
        calls_b = 0
        shared_order = OrderEntity(id=5, user_id=1, amount=500)

        @cached(ttl=60)
        def list_a():
            nonlocal calls_a
            calls_a += 1
            return [shared_order]

        @cached(ttl=60)
        def list_b():
            nonlocal calls_b
            calls_b += 1
            return [shared_order, OrderEntity(id=6, user_id=2, amount=600)]

        self.invalidator.register(OrderEntity, list_a)
        self.invalidator.register(OrderEntity, list_b)

        list_a()
        list_b()
        assert calls_a == 1
        assert calls_b == 1

        # 注册依赖
        self.invalidator.track_dependencies(
            list_a, list_a._build_key((), {}), [shared_order]
        )
        self.invalidator.track_dependencies(
            list_b, list_b._build_key((), {}),
            [shared_order, OrderEntity(id=6, user_id=2, amount=600)]
        )

        # Order(id=5) 变更 → 两个缓存都应失效
        self.invalidator._invalidate_for_target(
            OrderEntity, shared_order, "after_update"
        )

        list_a()
        list_b()
        assert calls_a == 2
        assert calls_b == 2
