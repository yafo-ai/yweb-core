"""MFA 管理器

统一管理多种 MFA 方式。

使用示例:
    from yweb.auth.mfa import MFAManager, TOTPProvider, SMSProvider, RecoveryCodeProvider
    
    # 创建管理器
    mfa_manager = MFAManager()
    
    # 注册 MFA 提供者
    mfa_manager.register_provider("totp", TOTPProvider(issuer="MyApp"))
    mfa_manager.register_provider("sms", SMSProvider(sms_sender=send_sms))
    mfa_manager.register_provider("recovery", RecoveryCodeProvider())
    
    # 设置用户偏好的 MFA 方式
    mfa_manager.set_user_mfa(user_id=1, providers=["totp", "sms"])
    
    # 验证
    result = mfa_manager.verify(user_id=1, provider_name="totp", code="123456")
"""

from typing import Optional, Any, Dict, List, Callable

from .base import MFAProvider, MFAType, MFASetupData, MFAVerifyResult


class MFAManager:
    """MFA 管理器
    
    统一管理多种 MFA 方式。
    """
    
    def __init__(self):
        self._providers: Dict[str, MFAProvider] = {}
        
        # 用户 MFA 配置存储
        self._user_mfa_config: Dict[Any, Dict[str, Any]] = {}
        self._user_config_store: Optional[Callable[[Any, Dict], bool]] = None
        self._user_config_getter: Optional[Callable[[Any], Optional[Dict]]] = None
    
    def set_user_config_stores(
        self,
        store: Callable[[Any, Dict], bool],
        getter: Callable[[Any], Optional[Dict]],
    ) -> "MFAManager":
        """设置用户配置存储回调
        
        Args:
            store: 存储用户 MFA 配置
            getter: 获取用户 MFA 配置
            
        Returns:
            self: 支持链式调用
        """
        self._user_config_store = store
        self._user_config_getter = getter
        return self
    
    def register_provider(
        self,
        name: str,
        provider: MFAProvider,
    ) -> "MFAManager":
        """注册 MFA 提供者
        
        Args:
            name: 提供者名称
            provider: MFA 提供者实例
            
        Returns:
            self: 支持链式调用
        """
        self._providers[name] = provider
        return self
    
    def unregister_provider(self, name: str) -> "MFAManager":
        """注销 MFA 提供者"""
        if name in self._providers:
            del self._providers[name]
        return self
    
    def get_provider(self, name: str) -> Optional[MFAProvider]:
        """获取 MFA 提供者"""
        return self._providers.get(name)
    
    def list_providers(self) -> List[str]:
        """列出所有已注册的提供者"""
        return list(self._providers.keys())
    
    def setup(
        self,
        user_id: Any,
        provider_name: str,
        **kwargs,
    ) -> Optional[MFASetupData]:
        """为用户设置 MFA
        
        Args:
            user_id: 用户 ID
            provider_name: 提供者名称
            **kwargs: 额外参数
            
        Returns:
            MFASetupData: 设置数据
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return None
        
        setup_data = provider.setup(user_id, **kwargs)
        
        # 更新用户配置
        config = self._get_user_config(user_id) or {}
        if "enabled_providers" not in config:
            config["enabled_providers"] = []
        if provider_name not in config["enabled_providers"]:
            config["enabled_providers"].append(provider_name)
        self._save_user_config(user_id, config)
        
        return setup_data
    
    def verify(
        self,
        user_id: Any,
        provider_name: str,
        code: str,
        **kwargs,
    ) -> MFAVerifyResult:
        """验证 MFA 代码
        
        Args:
            user_id: 用户 ID
            provider_name: 提供者名称
            code: 验证码
            **kwargs: 额外参数
            
        Returns:
            MFAVerifyResult: 验证结果
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return MFAVerifyResult.fail(f"MFA provider '{provider_name}' not found")
        
        return provider.verify(user_id, code, **kwargs)
    
    def verify_any(
        self,
        user_id: Any,
        code: str,
        **kwargs,
    ) -> MFAVerifyResult:
        """尝试所有已启用的 MFA 方式验证
        
        Args:
            user_id: 用户 ID
            code: 验证码
            **kwargs: 额外参数
            
        Returns:
            MFAVerifyResult: 验证结果
        """
        enabled = self.get_enabled_providers(user_id)
        
        if not enabled:
            return MFAVerifyResult.fail("No MFA configured for this user")
        
        for provider_name in enabled:
            result = self.verify(user_id, provider_name, code, **kwargs)
            if result.success:
                return result
        
        return MFAVerifyResult.fail("Invalid verification code")
    
    def is_enabled(self, user_id: Any) -> bool:
        """检查用户是否启用了任何 MFA
        
        Args:
            user_id: 用户 ID
            
        Returns:
            bool: 是否启用了 MFA
        """
        return len(self.get_enabled_providers(user_id)) > 0
    
    def get_enabled_providers(self, user_id: Any) -> List[str]:
        """获取用户启用的 MFA 提供者列表
        
        Args:
            user_id: 用户 ID
            
        Returns:
            List[str]: 提供者名称列表
        """
        config = self._get_user_config(user_id)
        if not config:
            return []
        return config.get("enabled_providers", [])
    
    def disable(
        self,
        user_id: Any,
        provider_name: str,
    ) -> bool:
        """禁用用户的特定 MFA 方式
        
        Args:
            user_id: 用户 ID
            provider_name: 提供者名称
            
        Returns:
            bool: 是否成功
        """
        provider = self._providers.get(provider_name)
        if provider:
            provider.disable(user_id)
        
        # 更新用户配置
        config = self._get_user_config(user_id) or {}
        enabled = config.get("enabled_providers", [])
        if provider_name in enabled:
            enabled.remove(provider_name)
            config["enabled_providers"] = enabled
            self._save_user_config(user_id, config)
        
        return True
    
    def disable_all(self, user_id: Any) -> bool:
        """禁用用户的所有 MFA
        
        Args:
            user_id: 用户 ID
            
        Returns:
            bool: 是否成功
        """
        for provider_name in self.get_enabled_providers(user_id):
            provider = self._providers.get(provider_name)
            if provider:
                provider.disable(user_id)
        
        self._save_user_config(user_id, {"enabled_providers": []})
        return True
    
    def get_available_providers(self, user_id: Any) -> List[Dict[str, Any]]:
        """获取用户可用的 MFA 提供者信息
        
        Args:
            user_id: 用户 ID
            
        Returns:
            List[Dict]: 提供者信息列表
        """
        enabled = set(self.get_enabled_providers(user_id))
        
        result = []
        for name, provider in self._providers.items():
            result.append({
                "name": name,
                "type": provider.mfa_type.value,
                "enabled": name in enabled,
            })
        
        return result
    
    def set_primary_provider(
        self,
        user_id: Any,
        provider_name: str,
    ) -> bool:
        """设置用户的首选 MFA 方式
        
        Args:
            user_id: 用户 ID
            provider_name: 提供者名称
            
        Returns:
            bool: 是否成功
        """
        if provider_name not in self._providers:
            return False
        
        config = self._get_user_config(user_id) or {}
        config["primary_provider"] = provider_name
        self._save_user_config(user_id, config)
        return True
    
    def get_primary_provider(self, user_id: Any) -> Optional[str]:
        """获取用户的首选 MFA 方式
        
        Args:
            user_id: 用户 ID
            
        Returns:
            str: 提供者名称
        """
        config = self._get_user_config(user_id)
        if not config:
            return None
        
        primary = config.get("primary_provider")
        if primary and primary in self.get_enabled_providers(user_id):
            return primary
        
        # 返回第一个启用的提供者
        enabled = self.get_enabled_providers(user_id)
        return enabled[0] if enabled else None
    
    def _get_user_config(self, user_id: Any) -> Optional[Dict]:
        """获取用户配置"""
        if self._user_config_getter:
            return self._user_config_getter(user_id)
        return self._user_mfa_config.get(user_id)
    
    def _save_user_config(self, user_id: Any, config: Dict) -> bool:
        """保存用户配置"""
        if self._user_config_store:
            return self._user_config_store(user_id, config)
        self._user_mfa_config[user_id] = config
        return True
