"""缓存装饰器测试"""

import pytest
import time
from typing import Optional
from dataclasses import dataclass

from yweb.cache import cached, memory_cache, CachedFunction


# 模拟用户类
@dataclass
class User:
    id: int
    name: str
    is_active: bool = True


# 模拟数据库
_fake_db = {
    1: User(id=1, name="Alice"),
    2: User(id=2, name="Bob"),
    3: User(id=3, name="Charlie", is_active=False),
}


class TestCachedDecorator:
    """测试 @cached 装饰器"""
    
    def test_basic_caching(self):
        """测试基本缓存功能"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 第一次调用，应该查询"数据库"
        user1 = get_user(1)
        assert user1.name == "Alice"
        assert call_count == 1
        
        # 第二次调用，应该从缓存返回
        user1_again = get_user(1)
        assert user1_again.name == "Alice"
        assert call_count == 1  # 没有增加
        
        # 不同参数，应该再次查询
        user2 = get_user(2)
        assert user2.name == "Bob"
        assert call_count == 2
    
    def test_invalidate_single(self):
        """测试单个缓存失效"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 先缓存
        get_user(1)
        assert call_count == 1
        
        # 再次调用，使用缓存
        get_user(1)
        assert call_count == 1
        
        # 失效缓存
        get_user.invalidate(1)
        
        # 再次调用，应该重新查询
        get_user(1)
        assert call_count == 2
    
    def test_invalidate_many(self):
        """测试批量缓存失效"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 缓存多个用户
        get_user(1)
        get_user(2)
        assert call_count == 2
        
        # 使用缓存
        get_user(1)
        get_user(2)
        assert call_count == 2
        
        # 批量失效
        count = get_user.invalidate_many([1, 2])
        assert count == 2
        
        # 再次调用，应该重新查询
        get_user(1)
        get_user(2)
        assert call_count == 4
    
    def test_clear_all(self):
        """测试清空所有缓存"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 缓存多个
        get_user(1)
        get_user(2)
        assert call_count == 2
        
        # 清空
        get_user.clear()
        
        # 都需要重新查询
        get_user(1)
        get_user(2)
        assert call_count == 4
    
    def test_refresh(self):
        """测试强制刷新"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 先缓存
        get_user(1)
        assert call_count == 1
        
        # 强制刷新
        user = get_user.refresh(1)
        assert user.name == "Alice"
        assert call_count == 2
    
    def test_stats(self):
        """测试统计信息"""
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            return _fake_db.get(user_id)
        
        # 产生一些命中和未命中
        get_user(1)  # miss
        get_user(1)  # hit
        get_user(2)  # miss
        get_user(2)  # hit
        get_user(2)  # hit
        
        stats = get_user.stats()
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        assert "hit_rate" in stats
    
    def test_none_not_cached(self):
        """测试 None 结果不被缓存"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 查询不存在的用户
        result = get_user(999)
        assert result is None
        assert call_count == 1
        
        # 再次查询，应该重新调用（None 不缓存）
        result = get_user(999)
        assert result is None
        assert call_count == 2
    
    def test_ttl_expiration(self):
        """测试 TTL 过期"""
        call_count = 0
        
        @cached(ttl=1)  # 1 秒过期
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 缓存
        get_user(1)
        assert call_count == 1
        
        # 使用缓存
        get_user(1)
        assert call_count == 1
        
        # 等待过期
        time.sleep(1.5)
        
        # 应该重新查询
        get_user(1)
        assert call_count == 2
    
    def test_kwargs_support(self):
        """测试关键字参数支持"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int, with_roles: bool = False) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 不同的 kwargs 应该有不同的缓存
        get_user(1, with_roles=False)
        get_user(1, with_roles=True)
        assert call_count == 2
        
        # 相同参数应该使用缓存
        get_user(1, with_roles=False)
        get_user(1, with_roles=True)
        assert call_count == 2
    
    def test_function_metadata_preserved(self):
        """测试函数元信息保留"""
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            """获取用户"""
            return _fake_db.get(user_id)
        
        assert get_user.__name__ == "get_user"
        assert get_user.__doc__ == "获取用户"
        assert isinstance(get_user, CachedFunction)
    
    def test_custom_key_prefix(self):
        """测试自定义键前缀"""
        @cached(ttl=60, key_prefix="user:auth")
        def get_user(user_id: int) -> Optional[User]:
            return _fake_db.get(user_id)
        
        stats = get_user.stats()
        assert stats["function"] == "user:auth"


class TestMemoryCacheDecorator:
    """测试 @memory_cache 装饰器"""
    
    def test_memory_cache_shortcut(self):
        """测试 memory_cache 快捷方式"""
        call_count = 0
        
        @memory_cache(ttl=60)
        def get_user(user_id: int) -> Optional[User]:
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        get_user(1)
        get_user(1)
        assert call_count == 1
        
        stats = get_user.stats()
        assert stats["backend"] == "memory"


class TestCacheWithDifferentTypes:
    """测试不同类型的缓存"""
    
    def test_cache_dict_result(self):
        """测试缓存字典结果"""
        call_count = 0

        @cached(ttl=60)
        def get_config(key: str) -> dict:
            nonlocal call_count
            call_count += 1
            return {"key": key, "value": f"value_{key}"}
        
        result1 = get_config("app")
        result2 = get_config("app")
        assert result1 == result2
        assert result1["key"] == "app"
        # 关键断言：同参数二次调用应命中缓存，而不是仅比较结果相等
        assert call_count == 1
    
    def test_cache_list_result(self):
        """测试缓存列表结果"""
        call_count = 0

        @cached(ttl=60)
        def list_users(limit: int) -> list:
            nonlocal call_count
            call_count += 1
            return list(_fake_db.values())[:limit]
        
        result1 = list_users(2)
        result2 = list_users(2)
        assert len(result1) == 2
        assert result1 == result2
        # 关键断言：验证缓存命中，避免“纯结果相等”的虚假测试
        assert call_count == 1


class TestCacheIntegrationExample:
    """模拟真实使用场景的集成测试"""
    
    def test_user_auth_cache_scenario(self):
        """测试用户认证缓存场景"""
        db_calls = 0
        
        # 模拟带缓存的用户获取函数
        @cached(ttl=60)
        def get_user_by_id(user_id: int) -> Optional[User]:
            nonlocal db_calls
            db_calls += 1
            user = _fake_db.get(user_id)
            if user and user.is_active:
                return user
            return None
        
        # 模拟多次 API 请求（同一用户）
        for _ in range(10):
            user = get_user_by_id(1)
            assert user is not None
            assert user.name == "Alice"
        
        # 应该只查询一次数据库
        assert db_calls == 1
        
        # 模拟用户信息更新后失效缓存
        get_user_by_id.invalidate(1)
        
        # 下次请求会重新查询
        get_user_by_id(1)
        assert db_calls == 2
        
        # 验证统计
        stats = get_user_by_id.stats()
        assert stats["hits"] == 9  # 10次调用 - 1次初始miss
        assert stats["misses"] == 2  # 初始 + 失效后
