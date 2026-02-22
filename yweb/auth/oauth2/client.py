"""OAuth 2.0 客户端定义

定义 OAuth 2.0 客户端数据结构和验证逻辑。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Set
from enum import Enum
import secrets


class ClientType(str, Enum):
    """客户端类型"""
    CONFIDENTIAL = "confidential"  # 机密客户端（可安全存储密钥）
    PUBLIC = "public"  # 公开客户端（如 SPA、移动应用）


@dataclass
class OAuth2Client:
    """OAuth 2.0 客户端
    
    Attributes:
        client_id: 客户端 ID
        client_secret: 客户端密钥（机密客户端）
        client_name: 客户端名称
        client_type: 客户端类型
        redirect_uris: 允许的重定向 URI 列表
        allowed_grant_types: 允许的授权类型
        allowed_scopes: 允许的权限范围
        default_scopes: 默认权限范围
        token_endpoint_auth_method: Token 端点认证方法
        created_at: 创建时间
        is_active: 是否激活
        metadata: 额外元数据
    """
    client_id: str
    client_secret: Optional[str] = None
    client_secret_hash: Optional[str] = None  # 存储哈希值
    client_name: str = ""
    client_type: ClientType = ClientType.CONFIDENTIAL
    redirect_uris: List[str] = field(default_factory=list)
    allowed_grant_types: List[str] = field(default_factory=lambda: [
        "authorization_code", "refresh_token"
    ])
    allowed_scopes: List[str] = field(default_factory=lambda: ["openid"])
    default_scopes: List[str] = field(default_factory=list)
    token_endpoint_auth_method: str = "client_secret_basic"  # client_secret_basic, client_secret_post, none
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # PKCE 支持
    require_pkce: bool = False  # 是否强制要求 PKCE
    
    # Token 配置
    access_token_lifetime: int = 3600  # 秒
    refresh_token_lifetime: int = 86400 * 30  # 30 天
    
    def validate_redirect_uri(self, redirect_uri: str) -> bool:
        """验证重定向 URI
        
        Args:
            redirect_uri: 要验证的重定向 URI
            
        Returns:
            bool: 是否有效
        """
        if not redirect_uri:
            return False
        
        # 精确匹配
        if redirect_uri in self.redirect_uris:
            return True
        
        # 检查是否有通配符模式（仅用于开发环境）
        for uri in self.redirect_uris:
            if uri.endswith("*"):
                base_uri = uri[:-1]
                if redirect_uri.startswith(base_uri):
                    return True
        
        return False
    
    def validate_scope(self, scope: str) -> tuple:
        """验证权限范围
        
        Args:
            scope: 空格分隔的权限范围字符串
            
        Returns:
            tuple: (is_valid, validated_scopes)
        """
        if not scope:
            return True, self.default_scopes or self.allowed_scopes[:1]
        
        requested_scopes = set(scope.split())
        allowed = set(self.allowed_scopes)
        
        invalid_scopes = requested_scopes - allowed
        if invalid_scopes:
            return False, list(invalid_scopes)
        
        return True, list(requested_scopes)
    
    def validate_grant_type(self, grant_type: str) -> bool:
        """验证授权类型
        
        Args:
            grant_type: 授权类型
            
        Returns:
            bool: 是否允许
        """
        return grant_type in self.allowed_grant_types
    
    def is_public(self) -> bool:
        """是否是公开客户端"""
        return self.client_type == ClientType.PUBLIC
    
    def requires_secret(self) -> bool:
        """是否需要客户端密钥"""
        return (
            self.client_type == ClientType.CONFIDENTIAL and
            self.token_endpoint_auth_method != "none"
        )
    
    def to_dict(self, include_secret: bool = False) -> Dict[str, Any]:
        """转换为字典
        
        Args:
            include_secret: 是否包含密钥
            
        Returns:
            Dict: 客户端信息
        """
        data = {
            "client_id": self.client_id,
            "client_name": self.client_name,
            "client_type": self.client_type.value,
            "redirect_uris": self.redirect_uris,
            "allowed_grant_types": self.allowed_grant_types,
            "allowed_scopes": self.allowed_scopes,
            "default_scopes": self.default_scopes,
            "token_endpoint_auth_method": self.token_endpoint_auth_method,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "is_active": self.is_active,
            "require_pkce": self.require_pkce,
            "access_token_lifetime": self.access_token_lifetime,
            "refresh_token_lifetime": self.refresh_token_lifetime,
        }
        
        if include_secret and self.client_secret:
            data["client_secret"] = self.client_secret
        
        return data


def generate_client_id(prefix: str = "client") -> str:
    """生成客户端 ID
    
    Args:
        prefix: ID 前缀
        
    Returns:
        str: 客户端 ID
    """
    return f"{prefix}_{secrets.token_hex(16)}"


def generate_client_secret(length: int = 32) -> str:
    """生成客户端密钥
    
    Args:
        length: 密钥长度
        
    Returns:
        str: 客户端密钥
    """
    return secrets.token_urlsafe(length)
