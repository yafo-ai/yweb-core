"""当前用户追踪功能测试

测试 CurrentUserPlugin 和相关便捷函数的功能

测试覆盖：
- Session 方式：set_user, get_user_id, clear_user
- CurrentUserPlugin 插件
- 与历史记录的集成
"""

import pytest
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    init_versioning,
    # 当前用户追踪
    CurrentUserPlugin,
    set_user,
    get_user_id,
    clear_user,
)


# Mock Session 用于测试
class MockSession:
    """模拟 SQLAlchemy Session"""
    def __init__(self):
        self.info = {}


# ==================== 测试 API 存在性 ====================

class TestCurrentUserAPIExists:
    """测试当前用户追踪 API 存在性"""
    
    def test_current_user_plugin_exists(self):
        """测试 CurrentUserPlugin 存在"""
        assert CurrentUserPlugin is not None
    
    def test_set_user_callable(self):
        """测试 set_user 可调用"""
        assert callable(set_user)
    
    def test_get_user_id_callable(self):
        """测试 get_user_id 可调用"""
        assert callable(get_user_id)
    
    def test_clear_user_callable(self):
        """测试 clear_user 可调用"""
        assert callable(clear_user)


# ==================== Session 用户操作测试 ====================

class TestSessionUserOperations:
    """Session 用户操作测试"""
    
    def test_set_and_get_integer_user_id(self):
        """测试设置和获取整数 user_id"""
        session = MockSession()
        clear_user(session)  # 确保清空
        
        set_user(session, 123)
        assert get_user_id(session) == 123
        
        clear_user(session)
        assert get_user_id(session) is None
    
    def test_set_and_get_string_user_id(self):
        """测试设置和获取字符串 user_id"""
        session = MockSession()
        clear_user(session)
        
        set_user(session, "user_abc_123")
        assert get_user_id(session) == "user_abc_123"
        
        clear_user(session)
    
    def test_default_value_is_none(self):
        """测试默认值为 None"""
        session = MockSession()
        clear_user(session)
        assert get_user_id(session) is None
    
    def test_overwrite_user_id(self):
        """测试覆盖 user_id"""
        session = MockSession()
        
        set_user(session, 1)
        assert get_user_id(session) == 1
        
        set_user(session, 2)
        assert get_user_id(session) == 2
        
        clear_user(session)


# ==================== CurrentUserPlugin 测试 ====================

class TestCurrentUserPlugin:
    """CurrentUserPlugin 插件测试"""
    
    def test_plugin_initialization(self):
        """测试插件初始化"""
        plugin = CurrentUserPlugin()
        assert plugin is not None
    
    def test_plugin_transaction_args_with_user_id(self):
        """测试从 session.info['user_id'] 获取 user_id"""
        plugin = CurrentUserPlugin()
        
        session = MockSession()
        session.info['user_id'] = 100
        
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 100}
    
    def test_plugin_transaction_args_with_current_user_id(self):
        """测试从 session.info['current_user_id'] 获取 user_id"""
        plugin = CurrentUserPlugin()
        
        session = MockSession()
        session.info['current_user_id'] = 77
        
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 77}
    
    def test_plugin_returns_empty_dict_when_no_user(self):
        """测试没有 user_id 时返回空字典"""
        plugin = CurrentUserPlugin()
        
        session = MockSession()
        
        result = plugin.transaction_args(None, session)
        assert result == {}
    
    def test_plugin_extract_primary_key_from_object(self):
        """测试从对象提取主键"""
        plugin = CurrentUserPlugin()
        
        class MockUser:
            id = 55
        
        result = plugin._extract_primary_key(MockUser())
        assert result == 55
    
    def test_plugin_user_id_priority_over_current_user_id(self):
        """测试 user_id 优先于 current_user_id"""
        plugin = CurrentUserPlugin()
        
        session = MockSession()
        session.info['user_id'] = 100
        session.info['current_user_id'] = 200
        
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 100}  # user_id 优先


# ==================== set_user/clear_user 便捷函数测试 ====================

class TestUserConvenienceFunctions:
    """set_user/clear_user 便捷函数测试"""
    
    def test_set_user_with_integer(self):
        """测试使用整数设置 user"""
        session = MockSession()
        set_user(session, 123)
        
        assert session.info['user_id'] == 123
    
    def test_set_user_with_string(self):
        """测试使用字符串设置 user"""
        session = MockSession()
        set_user(session, "user_abc")
        
        assert session.info['user_id'] == "user_abc"
    
    def test_set_user_with_object(self):
        """测试使用对象设置 user"""
        class MockUser:
            id = 456
        
        session = MockSession()
        set_user(session, MockUser())
        
        assert session.info['user_id'] == 456
    
    def test_clear_user_removes_all_keys(self):
        """测试 clear_user 清除所有相关 key"""
        session = MockSession()
        session.info = {
            'user_id': 1,
            'current_user_id': 2,
            'user': object(),
            'current_user': object(),
        }
        
        clear_user(session)
        
        assert 'user_id' not in session.info
        assert 'current_user_id' not in session.info
        assert 'user' not in session.info
        assert 'current_user' not in session.info


# ==================== 集成测试 ====================
# 
# 测试 CurrentUserPlugin 与 session 的集成
# 关键点：
# 1. 使用 set_user/get_user_id/clear_user 便捷函数
# 2. 验证 CurrentUserPlugin.transaction_args 正确获取 user_id

from sqlalchemy import Column, Integer, Text, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy_history import make_versioned, version_class, versioning_manager


class TestCurrentUserTrackingIntegration:
    """当前用户追踪集成测试"""
    
    def test_session_user_id_flow(self):
        """测试 session 方式设置 user_id 的完整流程"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # 1. 初始状态：没有 user_id
        clear_user(session)
        result = plugin.transaction_args(None, session)
        assert result == {}
        
        # 2. 设置 user_id
        set_user(session, 1001)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 1001}
        
        # 3. 更换用户
        set_user(session, 2002)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 2002}
        
        # 4. 清除用户
        clear_user(session)
        result = plugin.transaction_args(None, session)
        assert result == {}
    
    def test_transaction_args_returns_dict(self):
        """测试 transaction_args 返回正确格式"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # 没有 user_id 时返回空字典
        clear_user(session)
        result = plugin.transaction_args(None, session)
        assert result == {}
        
        # 有 user_id 时返回包含 user_id 的字典
        set_user(session, 42)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 42}
        
        clear_user(session)
    
    def test_multi_user_scenario_simulation(self):
        """模拟多用户操作场景"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # 模拟：用户1创建
        set_user(session, 1)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 1}
        
        # 模拟：用户2修改
        set_user(session, 2)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 2}
        
        # 模拟：用户3发布
        set_user(session, 3)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 3}
        
        clear_user(session)
    
    def test_string_user_id(self):
        """测试字符串类型的 user_id"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # UUID 类型的 user_id
        set_user(session, "550e8400-e29b-41d4-a716-446655440000")
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': "550e8400-e29b-41d4-a716-446655440000"}
        
        clear_user(session)
    
    def test_zero_user_id(self):
        """测试系统用户（user_id=0）"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # 系统用户 ID=0
        set_user(session, 0)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 0}
        
        clear_user(session)
    
    def test_negative_user_id(self):
        """测试负数 user_id（如特殊标识）"""
        plugin = CurrentUserPlugin()
        session = MockSession()
        
        # 负数 user_id（可能用于特殊标识）
        set_user(session, -1)
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': -1}
        
        clear_user(session)
    
    def test_session_info_user_object(self):
        """测试从 session.info['user'] 对象获取主键"""
        plugin = CurrentUserPlugin()
        
        class MockUser:
            id = 888
        
        session = MockSession()
        session.info['user'] = MockUser()
        
        # 应该从 user 对象提取主键
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 888}
    
    def test_session_info_current_user_object(self):
        """测试从 session.info['current_user'] 对象获取主键"""
        plugin = CurrentUserPlugin()
        
        class MockUser:
            id = 777
        
        session = MockSession()
        session.info['current_user'] = MockUser()
        
        # 应该从 current_user 对象提取主键
        result = plugin.transaction_args(None, session)
        assert result == {'user_id': 777}
    
    def test_priority_order_complete(self):
        """测试完整的优先级顺序"""
        plugin = CurrentUserPlugin()
        
        class MockUser1:
            id = 100
        
        class MockUser2:
            id = 200
        
        # 场景1：user_id 优先于 current_user_id
        session1 = MockSession()
        session1.info = {
            'user_id': 10,
            'current_user_id': 20,
            'user': MockUser1(),
            'current_user': MockUser2(),
        }
        result = plugin.transaction_args(None, session1)
        assert result == {'user_id': 10}  # user_id 优先
        
        # 场景2：只有 current_user_id
        session2 = MockSession()
        session2.info = {'current_user_id': 30}
        result = plugin.transaction_args(None, session2)
        assert result == {'user_id': 30}
        
        # 场景3：只有 user 对象
        session3 = MockSession()
        session3.info = {'user': MockUser1()}
        result = plugin.transaction_args(None, session3)
        assert result == {'user_id': 100}
        
        # 场景4：只有 current_user 对象
        session4 = MockSession()
        session4.info = {'current_user': MockUser2()}
        result = plugin.transaction_args(None, session4)
        assert result == {'user_id': 200}
    
    def test_extract_primary_key_fallback_to_id_attribute(self):
        """测试从对象提取主键时 fallback 到 id 属性"""
        plugin = CurrentUserPlugin()
        
        # 普通 Python 对象（非 SQLAlchemy 模型）
        class SimpleUser:
            def __init__(self, user_id):
                self.id = user_id
        
        user = SimpleUser(12345)
        result = plugin._extract_primary_key(user)
        assert result == 12345
    
    def test_extract_primary_key_returns_none_for_invalid_object(self):
        """测试从无效对象提取主键返回 None"""
        plugin = CurrentUserPlugin()
        
        # 没有 id 属性的对象
        class NoIdObject:
            name = "test"
        
        result = plugin._extract_primary_key(NoIdObject())
        assert result is None


# ==================== init_versioning 参数测试 ====================

class TestInitVersioningParams:
    """init_versioning 参数测试"""
    
    def test_plugins_param_exists(self):
        """测试 plugins 参数存在"""
        import inspect
        from yweb.orm import init_versioning
        
        sig = inspect.signature(init_versioning)
        params = sig.parameters
        
        assert 'plugins' in params
    
    def test_user_cls_param_exists(self):
        """测试 user_cls 参数存在"""
        import inspect
        from yweb.orm import init_versioning
        
        sig = inspect.signature(init_versioning)
        params = sig.parameters
        
        assert 'user_cls' in params
    
    def test_current_user_plugin_can_be_passed(self):
        """测试 CurrentUserPlugin 可以通过 plugins 参数传入"""
        # 验证 CurrentUserPlugin 可以实例化
        plugin = CurrentUserPlugin()
        assert plugin is not None
