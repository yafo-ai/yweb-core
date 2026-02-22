"""统一认证接口基类

提供认证提供者的抽象基类和认证管理器。

使用示例:
    from yweb.auth import AuthProvider, AuthManager, UserIdentity
    
    # 自定义认证提供者
    class MyAuthProvider(AuthProvider):
        def authenticate(self, credentials):
            # 验证逻辑
            return UserIdentity(user_id=1, username="admin")
        
        def validate_token(self, token):
            # Token 验证逻辑
            return TokenData(...)
    
    # 使用认证管理器
    auth_manager = AuthManager()
    auth_manager.register_provider("my_auth", MyAuthProvider())
    
    identity = auth_manager.authenticate("my_auth", credentials)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Any, Dict, List, TypeVar, Generic, Callable
from datetime import datetime, timezone
from enum import Enum


class AuthType(str, Enum):
    """认证类型枚举"""
    JWT = "jwt"
    API_KEY = "api_key"
    OAUTH2 = "oauth2"
    OIDC = "oidc"
    SESSION = "session"
    LDAP = "ldap"
    MFA = "mfa"


@dataclass
class UserIdentity:
    """用户身份信息
    
    统一的用户身份表示，所有认证方式都应返回此对象。
    
    Attributes:
        user_id: 用户唯一标识
        username: 用户名
        email: 用户邮箱
        roles: 角色列表
        permissions: 权限列表
        groups: 用户组列表
        attributes: 额外属性（如来自 LDAP 或 OIDC 的属性）
        auth_type: 认证类型
        auth_time: 认证时间
        session_id: 会话ID（可选）
        mfa_verified: 是否通过 MFA 验证
    """
    user_id: Any
    username: str
    email: Optional[str] = None
    roles: List[str] = field(default_factory=list)
    permissions: List[str] = field(default_factory=list)
    groups: List[str] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)
    auth_type: AuthType = AuthType.JWT
    auth_time: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    session_id: Optional[str] = None
    mfa_verified: bool = False
    
    def has_role(self, role: str) -> bool:
        """检查是否拥有指定角色"""
        return role in self.roles
    
    def has_any_role(self, roles: List[str]) -> bool:
        """检查是否拥有任一角色"""
        return any(role in self.roles for role in roles)
    
    def has_all_roles(self, roles: List[str]) -> bool:
        """检查是否拥有所有角色"""
        return all(role in self.roles for role in roles)
    
    def has_permission(self, permission: str) -> bool:
        """检查是否拥有指定权限"""
        return permission in self.permissions
    
    def has_any_permission(self, permissions: List[str]) -> bool:
        """检查是否拥有任一权限"""
        return any(perm in self.permissions for perm in permissions)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "user_id": self.user_id,
            "username": self.username,
            "email": self.email,
            "roles": self.roles,
            "permissions": self.permissions,
            "groups": self.groups,
            "attributes": self.attributes,
            "auth_type": self.auth_type.value,
            "auth_time": self.auth_time.isoformat(),
            "session_id": self.session_id,
            "mfa_verified": self.mfa_verified,
        }


@dataclass
class AuthResult:
    """认证结果
    
    Attributes:
        success: 认证是否成功
        identity: 用户身份信息（成功时）
        error: 错误信息（失败时）
        error_code: 错误代码
        requires_mfa: 是否需要 MFA 验证
        mfa_token: MFA 临时令牌
        extra: 额外信息
    """
    success: bool
    identity: Optional[UserIdentity] = None
    error: Optional[str] = None
    error_code: Optional[str] = None
    requires_mfa: bool = False
    mfa_token: Optional[str] = None
    extra: Dict[str, Any] = field(default_factory=dict)
    
    @classmethod
    def ok(cls, identity: UserIdentity, **extra) -> "AuthResult":
        """创建成功结果"""
        return cls(success=True, identity=identity, extra=extra)
    
    @classmethod
    def fail(cls, error: str, error_code: str = "AUTH_FAILED", **extra) -> "AuthResult":
        """创建失败结果"""
        return cls(success=False, error=error, error_code=error_code, extra=extra)
    
    @classmethod
    def require_mfa(cls, mfa_token: str, **extra) -> "AuthResult":
        """创建需要 MFA 的结果"""
        return cls(success=False, requires_mfa=True, mfa_token=mfa_token, extra=extra)


# 用户类型变量
UserType = TypeVar("UserType")


class AuthProvider(ABC):
    """认证提供者抽象基类
    
    所有认证方式都应继承此类并实现相关方法。
    
    使用示例:
        class MyAuthProvider(AuthProvider):
            @property
            def auth_type(self):
                return AuthType.JWT
            
            def authenticate(self, credentials):
                # 验证凭证
                return AuthResult.ok(UserIdentity(...))
            
            def validate_token(self, token):
                # 验证 Token
                return AuthResult.ok(UserIdentity(...))
    """
    
    @property
    @abstractmethod
    def auth_type(self) -> AuthType:
        """返回认证类型"""
        pass
    
    @abstractmethod
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证凭证
        
        Args:
            credentials: 认证凭证（可以是用户名密码、API Key 等）
            
        Returns:
            AuthResult: 认证结果
        """
        pass
    
    def validate_token(self, token: str) -> AuthResult:
        """验证 Token
        
        Args:
            token: Token 字符串
            
        Returns:
            AuthResult: 验证结果
        """
        return AuthResult.fail("Token validation not supported", "NOT_SUPPORTED")
    
    def refresh_token(self, refresh_token: str) -> AuthResult:
        """刷新 Token
        
        Args:
            refresh_token: 刷新令牌
            
        Returns:
            AuthResult: 包含新 Token 的结果
        """
        return AuthResult.fail("Token refresh not supported", "NOT_SUPPORTED")
    
    def revoke_token(self, token: str) -> bool:
        """撤销 Token
        
        Args:
            token: 要撤销的 Token
            
        Returns:
            bool: 是否成功撤销
        """
        return False
    
    def logout(self, identity: UserIdentity) -> bool:
        """登出
        
        Args:
            identity: 用户身份
            
        Returns:
            bool: 是否成功登出
        """
        return True


class AuthManager:
    """认证管理器
    
    管理多个认证提供者，支持多种认证方式。
    
    使用示例:
        auth_manager = AuthManager()
        
        # 注册认证提供者
        auth_manager.register_provider("jwt", JWTAuthProvider(...))
        auth_manager.register_provider("api_key", APIKeyAuthProvider(...))
        
        # 使用指定提供者认证
        result = auth_manager.authenticate("jwt", {"username": "admin", "password": "123"})
        
        # 自动检测认证方式
        result = auth_manager.authenticate_auto(request)
    """
    
    def __init__(self):
        self._providers: Dict[str, AuthProvider] = {}
        self._default_provider: Optional[str] = None
        self._token_extractors: List[Callable] = []
    
    def register_provider(
        self, 
        name: str, 
        provider: AuthProvider,
        is_default: bool = False
    ) -> "AuthManager":
        """注册认证提供者
        
        Args:
            name: 提供者名称
            provider: 认证提供者实例
            is_default: 是否设为默认提供者
            
        Returns:
            self: 支持链式调用
        """
        self._providers[name] = provider
        if is_default or self._default_provider is None:
            self._default_provider = name
        return self
    
    def unregister_provider(self, name: str) -> "AuthManager":
        """注销认证提供者
        
        Args:
            name: 提供者名称
            
        Returns:
            self: 支持链式调用
        """
        if name in self._providers:
            del self._providers[name]
            if self._default_provider == name:
                self._default_provider = next(iter(self._providers), None)
        return self
    
    def get_provider(self, name: str) -> Optional[AuthProvider]:
        """获取认证提供者
        
        Args:
            name: 提供者名称
            
        Returns:
            AuthProvider: 认证提供者实例
        """
        return self._providers.get(name)
    
    def get_default_provider(self) -> Optional[AuthProvider]:
        """获取默认认证提供者"""
        if self._default_provider:
            return self._providers.get(self._default_provider)
        return None
    
    def list_providers(self) -> List[str]:
        """列出所有已注册的提供者名称"""
        return list(self._providers.keys())
    
    def authenticate(
        self, 
        provider_name: str, 
        credentials: Any
    ) -> AuthResult:
        """使用指定提供者进行认证
        
        Args:
            provider_name: 提供者名称
            credentials: 认证凭证
            
        Returns:
            AuthResult: 认证结果
        """
        provider = self._providers.get(provider_name)
        if not provider:
            return AuthResult.fail(
                f"Authentication provider '{provider_name}' not found",
                "PROVIDER_NOT_FOUND"
            )
        return provider.authenticate(credentials)
    
    def authenticate_default(self, credentials: Any) -> AuthResult:
        """使用默认提供者进行认证
        
        Args:
            credentials: 认证凭证
            
        Returns:
            AuthResult: 认证结果
        """
        if not self._default_provider:
            return AuthResult.fail("No default provider configured", "NO_DEFAULT_PROVIDER")
        return self.authenticate(self._default_provider, credentials)
    
    def validate_token(
        self, 
        token: str, 
        provider_name: Optional[str] = None
    ) -> AuthResult:
        """验证 Token
        
        Args:
            token: Token 字符串
            provider_name: 提供者名称（可选，不指定则尝试所有提供者）
            
        Returns:
            AuthResult: 验证结果
        """
        if provider_name:
            provider = self._providers.get(provider_name)
            if not provider:
                return AuthResult.fail(
                    f"Authentication provider '{provider_name}' not found",
                    "PROVIDER_NOT_FOUND"
                )
            return provider.validate_token(token)
        
        # 尝试所有提供者
        for name, provider in self._providers.items():
            result = provider.validate_token(token)
            if result.success:
                return result
        
        return AuthResult.fail("Invalid token", "INVALID_TOKEN")
    
    def add_token_extractor(self, extractor: Callable) -> "AuthManager":
        """添加 Token 提取器
        
        Token 提取器从请求中提取 Token，用于自动检测认证方式。
        
        Args:
            extractor: Token 提取函数，接收 request，返回 (token, provider_name) 或 None
            
        Returns:
            self: 支持链式调用
        """
        self._token_extractors.append(extractor)
        return self
