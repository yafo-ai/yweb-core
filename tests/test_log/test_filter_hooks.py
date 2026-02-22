"""日志过滤钩子测试

测试敏感数据过滤和日志钩子管理
"""

import pytest
import logging
from typing import Dict, Any

from yweb.log import (
    LogFilterHook,
    SensitiveDataFilterHook,
    LogFilterHookManager,
    log_filter_hook_manager,
    DEFAULT_SENSITIVE_PATTERNS,
    DEFAULT_SENSITIVE_PATHS,
)


class TestLogFilterHook:
    """LogFilterHook 抽象类测试"""
    
    def test_abstract_class(self):
        """测试抽象类不能直接实例化"""
        with pytest.raises(TypeError):
            LogFilterHook()
    
    def test_custom_filter_hook(self):
        """测试自定义过滤钩子"""
        class UppercaseFilterHook(LogFilterHook):
            def should_apply(self, log_data: Dict[str, Any]) -> bool:
                return True
            
            def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
                result = log_data.copy()
                if 'message' in result:
                    result['message'] = result['message'].upper()
                return result
        
        hook = UppercaseFilterHook()
        result = hook.filter({'message': 'hello world'})
        
        assert result['message'] == "HELLO WORLD"
    
    def test_custom_filter_hook_should_apply(self):
        """测试自定义过滤钩子的 should_apply"""
        class ConditionalFilterHook(LogFilterHook):
            def should_apply(self, log_data: Dict[str, Any]) -> bool:
                return 'url' in log_data and '/api/' in log_data['url']
            
            def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
                result = log_data.copy()
                result['filtered'] = True
                return result
        
        hook = ConditionalFilterHook()
        
        # 应该应用
        assert hook.should_apply({'url': '/api/users'}) == True
        # 不应该应用
        assert hook.should_apply({'url': '/health'}) == False
        assert hook.should_apply({}) == False


class TestSensitiveDataFilterHook:
    """SensitiveDataFilterHook 测试"""
    
    def test_filter_password_in_dict(self):
        """测试过滤字典中的密码"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {'username': 'admin', 'password': 'secret123'}
        }
        filtered = hook.filter(log_data)
        
        # 密码应该被过滤
        assert filtered['request_body_preview']['password'] == "*SENSITIVE DATA FILTERED*"
        # 用户名应该保留
        assert filtered['request_body_preview']['username'] == "admin"
    
    def test_filter_token_in_dict(self):
        """测试过滤字典中的令牌"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/token',
            'request_body_preview': {
                'access_token': 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
                'user_id': 123
            }
        }
        filtered = hook.filter(log_data)
        
        assert filtered['request_body_preview']['access_token'] == "*SENSITIVE DATA FILTERED*"
        assert filtered['request_body_preview']['user_id'] == 123
    
    def test_filter_api_key_in_dict(self):
        """测试过滤字典中的 API 密钥"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {'api_key': 'sk-1234567890abcdef', 'action': 'test'}
        }
        filtered = hook.filter(log_data)
        
        assert filtered['request_body_preview']['api_key'] == "*SENSITIVE DATA FILTERED*"
        assert filtered['request_body_preview']['action'] == "test"
    
    def test_filter_json_string(self):
        """测试过滤 JSON 字符串格式数据"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': '{"username": "admin", "password": "secret123"}'
        }
        filtered = hook.filter(log_data)
        
        assert "secret123" not in filtered['request_body_preview']
        assert "*SENSITIVE DATA FILTERED*" in filtered['request_body_preview']
    
    def test_no_filter_non_sensitive_path(self):
        """测试非敏感路径不过滤"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/api/users',  # 非敏感路径
            'request_body_preview': {'password': 'should_not_filter', 'name': 'test'}
        }
        filtered = hook.filter(log_data)
        
        # 非敏感路径不应该过滤
        assert filtered['request_body_preview'] == log_data['request_body_preview']
        # 同时验证不会原地改写输入对象，避免副作用型“伪通过”
        assert log_data['request_body_preview']['password'] == 'should_not_filter'
    
    def test_filter_sensitive_path(self):
        """测试敏感路径过滤"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',  # 敏感路径
            'request_body_preview': {'password': 'secret', 'username': 'user'}
        }
        filtered = hook.filter(log_data)
        
        assert filtered['request_body_preview']['password'] == "*SENSITIVE DATA FILTERED*"
        assert filtered['request_body_preview']['username'] == "user"
    
    def test_no_filter_safe_data(self):
        """测试不过滤安全数据"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {'user_id': 123, 'status': 'active'}
        }
        filtered = hook.filter(log_data)
        
        # 安全字段应该保留
        assert filtered['request_body_preview']['user_id'] == 123
        assert filtered['request_body_preview']['status'] == 'active'
    
    def test_custom_patterns(self):
        """测试自定义过滤模式"""
        custom_patterns = [
            r'.*secret_code.*',
            r'.*private_key.*',
        ]
        hook = SensitiveDataFilterHook(sensitive_patterns=custom_patterns)
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {
                'secret_code': 'ABC123XYZ',
                'public_key': 'pub123'
            }
        }
        filtered = hook.filter(log_data)
        
        assert filtered['request_body_preview']['secret_code'] == "*SENSITIVE DATA FILTERED*"
        assert filtered['request_body_preview']['public_key'] == 'pub123'
    
    def test_custom_sensitive_paths(self):
        """测试自定义敏感路径"""
        custom_paths = ['/payment', '/checkout']
        hook = SensitiveDataFilterHook(sensitive_paths=custom_paths)
        
        log_data = {
            'url': '/payment/process',
            'request_body_preview': {'password': 'secret', 'amount': 100}
        }
        filtered = hook.filter(log_data)
        
        assert filtered['request_body_preview']['password'] == "*SENSITIVE DATA FILTERED*"
        assert filtered['request_body_preview']['amount'] == 100
    
    def test_filter_nested_dict(self):
        """测试过滤嵌套字典"""
        hook = SensitiveDataFilterHook()
        
        # 当 request_body_preview 是 JSON 字符串时，过滤后返回字符串
        log_data = {
            'url': '/auth/login',
            'request_body_preview': '{"user": {"username": "admin", "credentials": {"password": "secret"}}}'
        }
        filtered = hook.filter(log_data)
        
        # 过滤后仍是字符串
        assert isinstance(filtered['request_body_preview'], str)
        assert "secret" not in filtered['request_body_preview']
        assert "*SENSITIVE DATA FILTERED*" in filtered['request_body_preview']
        assert "admin" in filtered['request_body_preview']
    
    def test_filter_nested_dict_object(self):
        """测试过滤嵌套字典对象"""
        hook = SensitiveDataFilterHook()
        
        # 当 request_body_preview 是字典对象时
        # 注意：使用不匹配任何敏感模式的嵌套键名
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {
                'user': {
                    'username': 'admin',
                    'profile': {
                        'password': 'secret',
                        'type': 'basic'
                    }
                }
            }
        }
        filtered = hook.filter(log_data)
        
        # 过滤后仍是字典对象
        assert isinstance(filtered['request_body_preview'], dict)
        # password 字段应该被过滤
        assert filtered['request_body_preview']['user']['profile']['password'] == "*SENSITIVE DATA FILTERED*"
        # 非敏感字段应该保留
        assert filtered['request_body_preview']['user']['profile']['type'] == "basic"
        assert filtered['request_body_preview']['user']['username'] == "admin"
    
    def test_filter_list_of_dicts(self):
        """测试过滤字典列表"""
        hook = SensitiveDataFilterHook()
        
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {
                'users': [
                    {'username': 'user1', 'password': 'pass1'},
                    {'username': 'user2', 'password': 'pass2'},
                ]
            }
        }
        filtered = hook.filter(log_data)
        
        for user in filtered['request_body_preview']['users']:
            assert user['password'] == "*SENSITIVE DATA FILTERED*"
            assert 'user' in user['username']
    
    def test_should_apply_always_true(self):
        """测试 should_apply 总是返回 True"""
        hook = SensitiveDataFilterHook()
        
        assert hook.should_apply({}) == True
        assert hook.should_apply({'url': '/any/path'}) == True


class TestLogFilterHookManager:
    """LogFilterHookManager 测试"""
    
    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """每个测试前清除钩子"""
        # 保存原始钩子
        original_hooks = LogFilterHookManager._hooks.copy()
        LogFilterHookManager.clear_hooks()
        yield
        # 恢复原始钩子
        LogFilterHookManager._hooks = original_hooks
    
    def test_create_manager(self):
        """测试创建管理器"""
        manager = LogFilterHookManager()
        assert manager is not None
    
    def test_register_hook(self):
        """测试注册钩子"""
        hook = SensitiveDataFilterHook()
        
        LogFilterHookManager.register_hook(hook)
        
        assert len(LogFilterHookManager.get_hooks()) == 1
    
    def test_register_multiple_hooks(self):
        """测试注册多个钩子"""
        class HookA(LogFilterHook):
            def should_apply(self, log_data):
                return True
            def filter(self, log_data):
                result = log_data.copy()
                result['a'] = True
                return result
        
        class HookB(LogFilterHook):
            def should_apply(self, log_data):
                return True
            def filter(self, log_data):
                result = log_data.copy()
                result['b'] = True
                return result
        
        LogFilterHookManager.register_hook(HookA())
        LogFilterHookManager.register_hook(HookB())
        
        assert len(LogFilterHookManager.get_hooks()) == 2
    
    def test_unregister_hook(self):
        """测试注销钩子"""
        hook = SensitiveDataFilterHook()
        
        LogFilterHookManager.register_hook(hook)
        LogFilterHookManager.unregister_hook(hook)
        
        assert len(LogFilterHookManager.get_hooks()) == 0

    def test_unregister_only_one_when_duplicate_registered(self):
        """测试重复注册同一 hook 时，单次注销仅移除一个"""
        hook = SensitiveDataFilterHook()

        LogFilterHookManager.register_hook(hook)
        LogFilterHookManager.register_hook(hook)
        assert len(LogFilterHookManager.get_hooks()) == 2

        LogFilterHookManager.unregister_hook(hook)
        # list.remove 语义：单次只移除一个，避免测试与实现错位
        assert len(LogFilterHookManager.get_hooks()) == 1
    
    def test_apply_filters(self):
        """测试应用过滤器"""
        class PrefixHook(LogFilterHook):
            def should_apply(self, log_data):
                return True
            def filter(self, log_data):
                result = log_data.copy()
                result['prefix'] = True
                return result
        
        class SuffixHook(LogFilterHook):
            def should_apply(self, log_data):
                return True
            def filter(self, log_data):
                result = log_data.copy()
                result['suffix'] = True
                return result
        
        LogFilterHookManager.register_hook(PrefixHook())
        LogFilterHookManager.register_hook(SuffixHook())
        
        result = LogFilterHookManager.apply_filters({'message': 'test'})
        
        assert result['prefix'] == True
        assert result['suffix'] == True
        assert result['message'] == 'test'
    
    def test_apply_filters_respects_should_apply(self):
        """测试 apply_filters 尊重 should_apply"""
        class ConditionalHook(LogFilterHook):
            def should_apply(self, log_data):
                return 'apply_me' in log_data
            def filter(self, log_data):
                result = log_data.copy()
                result['filtered'] = True
                return result
        
        LogFilterHookManager.register_hook(ConditionalHook())
        
        # 应该应用
        result1 = LogFilterHookManager.apply_filters({'apply_me': True})
        assert result1.get('filtered') == True
        
        # 不应该应用
        result2 = LogFilterHookManager.apply_filters({'other': True})
        assert result2.get('filtered') is None
    
    def test_clear_hooks(self):
        """测试清除所有钩子"""
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        
        LogFilterHookManager.clear_hooks()
        
        assert len(LogFilterHookManager.get_hooks()) == 0
    
    def test_default_manager_exists(self):
        """测试默认管理器存在"""
        assert log_filter_hook_manager is not None
        assert isinstance(log_filter_hook_manager, LogFilterHookManager)


class TestLogFilterIntegration:
    """日志过滤集成测试"""
    
    @pytest.fixture(autouse=True)
    def reset_manager(self):
        """每个测试前重置钩子"""
        original_hooks = LogFilterHookManager._hooks.copy()
        LogFilterHookManager.clear_hooks()
        yield
        LogFilterHookManager._hooks = original_hooks
    
    def test_filter_log_record(self):
        """测试过滤日志记录"""
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        
        # 模拟日志消息
        log_data = {
            'url': '/auth/login',
            'request_body_preview': {'username': 'admin', 'password': 'secret123'}
        }
        filtered = LogFilterHookManager.apply_filters(log_data)
        
        assert filtered['request_body_preview']['username'] == 'admin'  # 用户名应保留
        assert filtered['request_body_preview']['password'] == "*SENSITIVE DATA FILTERED*"  # 密码应过滤
        # 验证输入对象不被原地改写，避免副作用掩盖过滤逻辑问题
        assert log_data['request_body_preview']['password'] == 'secret123'
    
    def test_filter_preserves_structure(self):
        """测试过滤保留消息结构"""
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        
        log_data = {
            'method': 'POST',
            'url': '/auth/login',
            'status_code': 200,
            'request_body_preview': '{"username": "user", "password": "pass"}'
        }
        filtered = LogFilterHookManager.apply_filters(log_data)
        
        assert filtered['method'] == 'POST'
        assert filtered['url'] == '/auth/login'
        assert filtered['status_code'] == 200
        assert 'username' in filtered['request_body_preview']
    
    def test_empty_log_data(self):
        """测试空日志数据"""
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        
        result = LogFilterHookManager.apply_filters({})
        assert result == {}
    
    def test_log_data_without_request_body(self):
        """测试没有请求体的日志数据"""
        LogFilterHookManager.register_hook(SensitiveDataFilterHook())
        
        log_data = {
            'url': '/auth/login',
            'method': 'GET'
        }
        result = LogFilterHookManager.apply_filters(log_data)
        
        assert result['url'] == '/auth/login'
        assert result['method'] == 'GET'


class TestDefaultPatterns:
    """默认配置测试"""
    
    def test_default_sensitive_patterns_exist(self):
        """测试默认敏感模式存在"""
        assert DEFAULT_SENSITIVE_PATTERNS is not None
        assert len(DEFAULT_SENSITIVE_PATTERNS) > 0
    
    def test_default_sensitive_paths_exist(self):
        """测试默认敏感路径存在"""
        assert DEFAULT_SENSITIVE_PATHS is not None
        assert len(DEFAULT_SENSITIVE_PATHS) > 0
    
    def test_password_pattern_in_defaults(self):
        """测试密码模式在默认配置中"""
        assert any('password' in p.lower() for p in DEFAULT_SENSITIVE_PATTERNS)
    
    def test_token_pattern_in_defaults(self):
        """测试令牌模式在默认配置中"""
        assert any('token' in p.lower() for p in DEFAULT_SENSITIVE_PATTERNS)
    
    def test_login_path_in_defaults(self):
        """测试登录路径在默认配置中"""
        assert any('login' in p.lower() for p in DEFAULT_SENSITIVE_PATHS)
