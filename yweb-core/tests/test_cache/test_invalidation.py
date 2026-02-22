"""缓存自动失效测试"""

import pytest
from typing import Optional
from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from yweb.cache import (
    cached,
    cache_invalidator,
    CacheInvalidator,
    no_auto_invalidation,
)


# 模拟用户类
@dataclass
class MockUser:
    id: int
    name: str
    username: str
    is_active: bool = True


# 模拟数据库
_fake_db = {
    1: MockUser(id=1, name="Alice", username="alice"),
    2: MockUser(id=2, name="Bob", username="bob"),
    3: MockUser(id=3, name="Charlie", username="charlie"),
}


class TestCacheInvalidator:
    """测试 CacheInvalidator"""
    
    def setup_method(self):
        """每个测试前重置"""
        # 创建新的 invalidator 避免测试间干扰
        self.invalidator = CacheInvalidator()
    
    def test_register_basic(self):
        """测试基本注册"""
        @cached(ttl=60)
        def get_user(user_id: int):
            return _fake_db.get(user_id)
        
        # 注册
        result = self.invalidator.register(MockUser, get_user)
        
        # 验证链式调用
        assert result is self.invalidator
        
        # 验证注册信息
        regs = self.invalidator.get_registrations(MockUser)
        assert "MockUser" in regs
        assert len(regs["MockUser"]) == 1
        assert regs["MockUser"][0]["func"] == "get_user"
    
    def test_register_invalid_func(self):
        """测试注册无效函数"""
        def plain_func():
            pass
        
        with pytest.raises(ValueError) as exc_info:
            self.invalidator.register(MockUser, plain_func)
        
        assert "必须是被 @cached 装饰的函数" in str(exc_info.value)
    
    def test_register_custom_key_extractor(self):
        """测试自定义 key 提取器"""
        call_count = 0

        @cached(ttl=60)
        def get_user_by_username(username: str):
            nonlocal call_count
            call_count += 1
            for user in _fake_db.values():
                if user.username == username:
                    return user
            return None
        
        self.invalidator.register(
            MockUser,
            get_user_by_username,
            key_extractor=lambda user: user.username
        )
        
        regs = self.invalidator.get_registrations(MockUser)
        assert len(regs["MockUser"]) == 1
        # 同参数命中缓存
        get_user_by_username("alice")
        get_user_by_username("alice")
        assert call_count == 1

        # 触发失效后应重新查询
        self.invalidator._invalidate_for_target(MockUser, _fake_db[1], "after_update")
        get_user_by_username("alice")
        assert call_count == 2
    
    def test_register_multiple_funcs(self):
        """测试注册多个函数"""
        id_calls = 0
        username_calls = 0

        @cached(ttl=60)
        def get_user_by_id(user_id: int):
            nonlocal id_calls
            id_calls += 1
            return _fake_db.get(user_id)
        
        @cached(ttl=60)
        def get_user_by_username(username: str):
            nonlocal username_calls
            username_calls += 1
            for user in _fake_db.values():
                if user.username == username:
                    return user
            return None
        
        self.invalidator.register(MockUser, get_user_by_id)
        self.invalidator.register(
            MockUser, 
            get_user_by_username,
            key_extractor=lambda u: u.username
        )
        
        regs = self.invalidator.get_registrations(MockUser)
        assert len(regs["MockUser"]) == 2
        # 两个函数都命中缓存
        get_user_by_id(1)
        get_user_by_id(1)
        get_user_by_username("alice")
        get_user_by_username("alice")
        assert id_calls == 1
        assert username_calls == 1

        # 触发失效后两个缓存都应失效
        self.invalidator._invalidate_for_target(MockUser, _fake_db[1], "after_update")
        get_user_by_id(1)
        get_user_by_username("alice")
        assert id_calls == 2
        assert username_calls == 2
    
    def test_unregister_all(self):
        """测试取消所有注册"""
        @cached(ttl=60)
        def get_user(user_id: int):
            return _fake_db.get(user_id)
        
        self.invalidator.register(MockUser, get_user)
        assert MockUser.__name__ in self.invalidator.get_registrations()
        
        result = self.invalidator.unregister(MockUser)
        assert result is True
        assert MockUser.__name__ not in self.invalidator.get_registrations()
    
    def test_unregister_specific_func(self):
        """测试取消特定函数注册"""
        @cached(ttl=60)
        def get_user_by_id(user_id: int):
            return _fake_db.get(user_id)
        
        @cached(ttl=60)
        def get_user_by_username(username: str):
            return None
        
        self.invalidator.register(MockUser, get_user_by_id)
        self.invalidator.register(
            MockUser, 
            get_user_by_username,
            key_extractor=lambda u: u.username
        )
        
        # 只取消一个
        result = self.invalidator.unregister(MockUser, get_user_by_id)
        assert result is True
        
        regs = self.invalidator.get_registrations(MockUser)
        assert len(regs["MockUser"]) == 1
        assert regs["MockUser"][0]["func"] == "get_user_by_username"
    
    def test_disable_enable(self):
        """测试禁用/启用"""
        assert self.invalidator.is_enabled is True
        
        self.invalidator.disable()
        assert self.invalidator.is_enabled is False
        
        self.invalidator.enable()
        assert self.invalidator.is_enabled is True
    
    def test_clear(self):
        """测试清空所有注册"""
        @cached(ttl=60)
        def get_user(user_id: int):
            return _fake_db.get(user_id)
        
        self.invalidator.register(MockUser, get_user)
        assert len(self.invalidator.get_registrations()) > 0
        
        self.invalidator.clear()
        assert len(self.invalidator.get_registrations()) == 0
    
    def test_invalidate_for_target(self):
        """测试手动触发失效"""
        call_count = 0
        
        @cached(ttl=60)
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        self.invalidator.register(MockUser, get_user)
        
        # 先缓存
        get_user(1)
        assert call_count == 1
        get_user(1)
        assert call_count == 1  # 使用缓存
        
        # 模拟触发失效
        user = _fake_db[1]
        self.invalidator._invalidate_for_target(MockUser, user, "after_update")
        
        # 再次调用应该重新查询
        get_user(1)
        assert call_count == 2


class TestNoAutoInvalidationContext:
    """测试 no_auto_invalidation 上下文"""
    
    def test_context_manager(self):
        """测试上下文管理器"""
        invalidator = CacheInvalidator()
        
        assert invalidator.is_enabled is True
        
        with no_auto_invalidation():
            # 全局 cache_invalidator 被禁用
            from yweb.cache import cache_invalidator as global_invalidator
            assert global_invalidator.is_enabled is False
        
        # 退出后恢复
        assert global_invalidator.is_enabled is True
    
    def test_nested_context(self):
        """测试嵌套上下文"""
        from yweb.cache import cache_invalidator as global_invalidator
        
        assert global_invalidator.is_enabled is True
        
        with no_auto_invalidation():
            assert global_invalidator.is_enabled is False
            
            with no_auto_invalidation():
                assert global_invalidator.is_enabled is False
            
            # 内层退出后仍禁用（因为外层还在）
            assert global_invalidator.is_enabled is False
        
        # 外层退出后恢复
        assert global_invalidator.is_enabled is True


class TestIntegrationWithSQLAlchemy:
    """SQLAlchemy 集成测试（模拟）"""
    
    def test_sqlalchemy_event_simulation(self):
        """模拟 SQLAlchemy 事件触发"""
        call_count = 0
        invalidator = CacheInvalidator()
        
        @cached(ttl=60)
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        # 注册（不实际监听 SQLAlchemy 事件）
        invalidator._registrations[MockUser] = [{
            "func": get_user,
            "key_extractor": lambda u: u.id,
            "events": ("after_update", "after_delete"),
        }]
        
        # 缓存用户
        get_user(1)
        assert call_count == 1
        get_user(1)
        assert call_count == 1
        
        # 模拟 after_update 事件
        user = _fake_db[1]
        invalidator._invalidate_for_target(MockUser, user, "after_update")
        
        # 缓存已失效
        get_user(1)
        assert call_count == 2
    
    def test_disabled_during_bulk_operation(self):
        """测试批量操作时禁用自动失效"""
        call_count = 0
        invalidator = CacheInvalidator()
        
        @cached(ttl=60)
        def get_user(user_id: int):
            nonlocal call_count
            call_count += 1
            return _fake_db.get(user_id)
        
        invalidator._registrations[MockUser] = [{
            "func": get_user,
            "key_extractor": lambda u: u.id,
            "events": ("after_update",),
        }]
        
        # 缓存
        get_user(1)
        assert call_count == 1
        
        # 禁用期间的失效不会执行
        invalidator.disable()
        user = _fake_db[1]
        invalidator._invalidate_for_target(MockUser, user, "after_update")
        
        # 缓存仍然有效
        get_user(1)
        assert call_count == 1
        
        # 启用后手动失效
        invalidator.enable()
        invalidator._invalidate_for_target(MockUser, user, "after_update")
        
        # 现在缓存失效了
        get_user(1)
        assert call_count == 2


class TestChainRegistration:
    """测试链式注册"""
    
    def test_chain_register(self):
        """测试链式注册多个模型"""
        invalidator = CacheInvalidator()
        
        @cached(ttl=60)
        def get_user(user_id: int):
            return None
        
        @cached(ttl=60)
        def get_org(org_id: int):
            return None
        
        @dataclass
        class MockOrg:
            id: int
            name: str
        
        # 链式注册
        invalidator \
            .register(MockUser, get_user) \
            .register(MockOrg, get_org)
        
        regs = invalidator.get_registrations()
        assert "MockUser" in regs
        assert "MockOrg" in regs
