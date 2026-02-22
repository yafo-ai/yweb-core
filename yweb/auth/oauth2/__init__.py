"""OAuth 2.0 认证模块

提供完整的 OAuth 2.0 实现，支持多种授权流程。

支持的授权流程:
    - Authorization Code: 标准 Web 应用授权
    - Client Credentials: 服务间通信
    - Device Code: 智能设备和 CLI 工具
    - Refresh Token: Token 刷新

使用示例:
    from yweb.auth.oauth2 import (
        OAuth2Manager,
        OAuth2Client,
        AuthorizationCodeGrant,
        ClientCredentialsGrant,
    )
    
    # 创建 OAuth2 管理器
    oauth2_manager = OAuth2Manager(
        secret_key="your-secret-key",
        authorization_code_expire_minutes=10,
        access_token_expire_minutes=30,
    )
    
    # 注册客户端
    client = OAuth2Client(
        client_id="my-app",
        client_secret="secret",
        redirect_uris=["http://localhost:8000/callback"],
        allowed_grant_types=["authorization_code", "refresh_token"],
        allowed_scopes=["openid", "profile", "email"],
    )
    oauth2_manager.register_client(client)
    
    # 使用授权码流程
    auth_code = oauth2_manager.create_authorization_code(
        client_id="my-app",
        user_id=1,
        redirect_uri="http://localhost:8000/callback",
        scope="openid profile",
    )
    
    # 交换访问令牌
    token_response = oauth2_manager.exchange_code(
        code=auth_code,
        client_id="my-app",
        client_secret="secret",
        redirect_uri="http://localhost:8000/callback",
    )
"""

from .client import OAuth2Client, ClientType
from .token import OAuth2Token, TokenType
from .grants import (
    GrantType,
    AuthorizationCodeGrant,
    ClientCredentialsGrant,
    RefreshTokenGrant,
    DeviceCodeGrant,
)
from .manager import OAuth2Manager
from .provider import OAuth2AuthProvider

__all__ = [
    # Client
    "OAuth2Client",
    "ClientType",
    
    # Token
    "OAuth2Token",
    "TokenType",
    
    # Grants
    "GrantType",
    "AuthorizationCodeGrant",
    "ClientCredentialsGrant",
    "RefreshTokenGrant",
    "DeviceCodeGrant",
    
    # Manager
    "OAuth2Manager",
    
    # Provider
    "OAuth2AuthProvider",
]
