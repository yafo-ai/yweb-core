"""日志过滤钩子模块

提供日志数据的过滤功能，用于：
- 过滤敏感数据（密码、token等）
- 自定义日志过滤规则
- 保护用户隐私

使用示例:
    from yweb.log import (
        log_filter_hook_manager,
        SensitiveDataFilterHook,
        LogFilterHook,
    )
    
    # 使用默认配置（已自动注册敏感数据过滤器）
    filtered_data = log_filter_hook_manager.apply_filters(log_data)
    
    # 自定义敏感字段模式
    custom_hook = SensitiveDataFilterHook(
        sensitive_patterns=[r'.*credit_card.*', r'.*ssn.*'],
        sensitive_paths=['/payment', '/user/profile']
    )
    log_filter_hook_manager.register_hook(custom_hook)
"""

from abc import ABC, abstractmethod
from typing import Dict, Any, List
import re

# 默认敏感字段名模式
DEFAULT_SENSITIVE_PATTERNS = [
    r'.*(password|pwd|passwd).*',
    r'.*(token|access_token|refresh_token).*',
    r'.*(secret|key|apikey|api_key).*',
    r'.*(credential|credentials).*',
    r'.*(auth|authentication).*'
]

# 默认需要特殊处理的URL路径
DEFAULT_SENSITIVE_PATHS = [
    '/auth/login',
    '/auth/token',
    '/admin/login'
]


class LogFilterHook(ABC):
    """日志过滤钩子抽象基类
    
    继承此类可以自定义日志过滤逻辑。
    
    使用示例:
        class MyCustomFilterHook(LogFilterHook):
            def should_apply(self, log_data: Dict[str, Any]) -> bool:
                # 只对特定URL应用
                return '/api/v1/' in log_data.get('url', '')
            
            def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
                # 自定义过滤逻辑
                filtered = log_data.copy()
                filtered['custom_field'] = 'filtered'
                return filtered
        
        # 注册钩子
        log_filter_hook_manager.register_hook(MyCustomFilterHook())
    """
    
    @abstractmethod
    def should_apply(self, log_data: Dict[str, Any]) -> bool:
        """判断是否应该应用此过滤器
        
        Args:
            log_data: 日志数据
            
        Returns:
            bool: 是否应该应用此过滤器
        """
        pass
    
    @abstractmethod
    def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤日志数据
        
        Args:
            log_data: 日志数据
            
        Returns:
            Dict[str, Any]: 过滤后的日志数据
        """
        pass


class SensitiveDataFilterHook(LogFilterHook):
    """敏感数据过滤器
    
    自动检测并过滤日志中的敏感信息，如密码、token等。
    
    功能：
    - 根据字段名模式过滤敏感数据
    - 对特定URL路径的请求体进行深度过滤
    - 支持嵌套字典和列表的递归过滤
    
    Args:
        sensitive_patterns: 敏感字段名模式列表（正则表达式）
        sensitive_paths: 敏感URL路径列表
    
    使用示例:
        # 使用默认配置
        hook = SensitiveDataFilterHook()
        
        # 自定义配置
        hook = SensitiveDataFilterHook(
            sensitive_patterns=[
                r'.*password.*',
                r'.*credit_card.*',
            ],
            sensitive_paths=[
                '/payment',
                '/auth/login',
            ]
        )
        log_filter_hook_manager.register_hook(hook)
    """
    
    def __init__(self, sensitive_patterns: List[str] = None, sensitive_paths: List[str] = None):
        """初始化敏感数据过滤器
        
        Args:
            sensitive_patterns: 敏感字段名模式列表，默认使用 DEFAULT_SENSITIVE_PATTERNS
            sensitive_paths: 敏感URL路径列表，默认使用 DEFAULT_SENSITIVE_PATHS
        """
        self.sensitive_patterns = sensitive_patterns if sensitive_patterns is not None else DEFAULT_SENSITIVE_PATTERNS
        
        # 编译正则表达式以提高性能
        self.compiled_patterns = [
            re.compile(pattern, re.IGNORECASE) 
            for pattern in self.sensitive_patterns
        ]
        
        self.sensitive_paths = sensitive_paths if sensitive_paths is not None else DEFAULT_SENSITIVE_PATHS
    
    def should_apply(self, log_data: Dict[str, Any]) -> bool:
        """判断是否应该应用此过滤器"""
        # 总是应用此过滤器
        return True
    
    def filter(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """过滤敏感数据"""
        filtered_data = log_data.copy()
        
        # 检查URL是否为敏感路径
        url = filtered_data.get('url', '')
        is_sensitive_path = any(path in url.lower() for path in self.sensitive_paths)
        
        # 如果有请求体预览且是敏感路径，则过滤敏感字段
        request_body_preview = filtered_data.get('request_body_preview')
        if request_body_preview and is_sensitive_path:
            if isinstance(request_body_preview, str):
                filtered_data['request_body_preview'] = self._filter_sensitive_fields_in_string(request_body_preview)
            elif isinstance(request_body_preview, dict):
                filtered_data['request_body_preview'] = self._filter_sensitive_fields_in_dict(request_body_preview)
        
        return filtered_data
    
    def _filter_sensitive_fields_in_string(self, text: str) -> str:
        """在字符串中过滤敏感字段，保留JSON的所有属性，只过滤敏感字段的值"""
        if text.strip().startswith('{') and text.strip().endswith('}'):
            try:
                import json
                data = json.loads(text)
                if isinstance(data, dict):
                    filtered_data = self._filter_sensitive_fields_in_dict(data)
                    return json.dumps(filtered_data, ensure_ascii=False)
            except (json.JSONDecodeError, TypeError):
                pass
        return text
    
    def _filter_sensitive_fields_in_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """在字典中过滤敏感字段，只将敏感字段的值替换为星号"""
        filtered_data = {}
        for key, value in data.items():
            # 检查键是否匹配敏感模式
            is_sensitive = any(pattern.search(key) for pattern in self.compiled_patterns)
            if is_sensitive:
                filtered_data[key] = "*SENSITIVE DATA FILTERED*"
            elif isinstance(value, dict):
                filtered_data[key] = self._filter_sensitive_fields_in_dict(value)
            elif isinstance(value, list):
                filtered_data[key] = self._filter_sensitive_fields_in_list(value)
            else:
                filtered_data[key] = value
        return filtered_data
    
    def _filter_sensitive_fields_in_list(self, data: List[Any]) -> List[Any]:
        """在列表中过滤敏感字段"""
        filtered_data = []
        for item in data:
            if isinstance(item, dict):
                filtered_data.append(self._filter_sensitive_fields_in_dict(item))
            elif isinstance(item, list):
                filtered_data.append(self._filter_sensitive_fields_in_list(item))
            else:
                filtered_data.append(item)
        return filtered_data


class LogFilterHookManager:
    """日志过滤钩子管理器
    
    单例模式，管理所有已注册的日志过滤钩子。
    
    使用示例:
        from yweb.log import log_filter_hook_manager
        
        # 注册自定义钩子
        log_filter_hook_manager.register_hook(MyCustomHook())
        
        # 应用所有过滤器
        filtered_log = log_filter_hook_manager.apply_filters(raw_log_data)
        
        # 注销钩子
        log_filter_hook_manager.unregister_hook(my_hook)
    """
    
    _instance = None
    _hooks: List[LogFilterHook] = []
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(LogFilterHookManager, cls).__new__(cls)
            cls._hooks = []
        return cls._instance
    
    @classmethod
    def register_hook(cls, hook: LogFilterHook):
        """注册日志过滤钩子
        
        Args:
            hook: 日志过滤钩子实例
        """
        cls._hooks.append(hook)
    
    @classmethod
    def unregister_hook(cls, hook: LogFilterHook):
        """注销日志过滤钩子
        
        Args:
            hook: 日志过滤钩子实例
        """
        if hook in cls._hooks:
            cls._hooks.remove(hook)
    
    @classmethod
    def clear_hooks(cls):
        """清除所有已注册的钩子"""
        cls._hooks.clear()
    
    @classmethod
    def get_hooks(cls) -> List[LogFilterHook]:
        """获取所有已注册的钩子"""
        return cls._hooks.copy()
    
    @classmethod
    def apply_filters(cls, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """应用所有已注册的过滤器
        
        Args:
            log_data: 原始日志数据
            
        Returns:
            Dict[str, Any]: 过滤后的日志数据
        """
        filtered_data = log_data.copy()
        for hook in cls._hooks:
            if hook.should_apply(filtered_data):
                filtered_data = hook.filter(filtered_data)
        return filtered_data


# 创建全局实例
log_filter_hook_manager = LogFilterHookManager()

# 注册默认的敏感数据过滤器
log_filter_hook_manager.register_hook(SensitiveDataFilterHook())

