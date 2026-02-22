"""OAuth 2.0 Token 定义

定义 OAuth 2.0 Token 数据结构。
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
import secrets


class TokenType(str, Enum):
    """Token 类型"""
    BEARER = "Bearer"
    MAC = "MAC"  # 较少使用


@dataclass
class OAuth2Token:
    """OAuth 2.0 Token
    
    Attributes:
        access_token: 访问令牌
        token_type: Token 类型
        expires_in: 过期时间（秒）
        refresh_token: 刷新令牌
        scope: 权限范围
        id_token: ID Token（OIDC）
    """
    access_token: str
    token_type: TokenType = TokenType.BEARER
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None  # 用于 OIDC
    
    # 内部使用
    client_id: Optional[str] = None
    user_id: Optional[Any] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    refresh_token_expires_at: Optional[datetime] = None
    is_revoked: bool = False
    
    def __post_init__(self):
        if self.expires_at is None and self.expires_in:
            self.expires_at = self.created_at + timedelta(seconds=self.expires_in)
    
    def is_expired(self) -> bool:
        """检查访问令牌是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_refresh_token_expired(self) -> bool:
        """检查刷新令牌是否过期"""
        if self.refresh_token_expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.refresh_token_expires_at
    
    def to_response(self) -> Dict[str, Any]:
        """转换为 OAuth 2.0 标准响应格式"""
        response = {
            "access_token": self.access_token,
            "token_type": self.token_type.value,
            "expires_in": self.expires_in,
        }
        
        if self.refresh_token:
            response["refresh_token"] = self.refresh_token
        
        if self.scope:
            response["scope"] = self.scope
        
        if self.id_token:
            response["id_token"] = self.id_token
        
        return response


@dataclass
class AuthorizationCode:
    """授权码
    
    用于 Authorization Code 流程。
    """
    code: str
    client_id: str
    user_id: Any
    redirect_uri: str
    scope: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    is_used: bool = False
    
    # PKCE
    code_challenge: Optional[str] = None
    code_challenge_method: Optional[str] = None  # plain, S256
    
    # OIDC
    nonce: Optional[str] = None
    
    def __post_init__(self):
        if self.expires_at is None:
            # 授权码默认 1 分钟过期
            self.expires_at = self.created_at + timedelta(minutes=10)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


@dataclass
class DeviceCode:
    """设备码
    
    用于 Device Code 流程。
    """
    device_code: str
    user_code: str
    client_id: str
    scope: str
    verification_uri: str
    verification_uri_complete: Optional[str] = None
    expires_in: int = 1800  # 30 分钟
    interval: int = 5  # 轮询间隔
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    user_id: Optional[Any] = None  # 用户授权后设置
    is_authorized: bool = False
    is_denied: bool = False
    
    def __post_init__(self):
        if self.expires_at is None:
            self.expires_at = self.created_at + timedelta(seconds=self.expires_in)
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at


def generate_token(length: int = 32) -> str:
    """生成随机 Token
    
    Args:
        length: Token 长度
        
    Returns:
        str: Token 字符串
    """
    return secrets.token_urlsafe(length)


def generate_authorization_code(length: int = 32) -> str:
    """生成授权码
    
    Args:
        length: 授权码长度
        
    Returns:
        str: 授权码
    """
    return secrets.token_urlsafe(length)


def generate_device_code(length: int = 32) -> str:
    """生成设备码
    
    Args:
        length: 设备码长度
        
    Returns:
        str: 设备码
    """
    return secrets.token_urlsafe(length)


def generate_user_code(length: int = 8) -> str:
    """生成用户码（用于设备授权）
    
    生成易于输入的用户码（大写字母和数字，排除易混淆字符）
    
    Args:
        length: 用户码长度
        
    Returns:
        str: 用户码
    """
    # 排除易混淆字符：0, O, I, L, 1
    chars = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(chars) for _ in range(length))
