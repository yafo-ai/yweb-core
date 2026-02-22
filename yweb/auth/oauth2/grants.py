"""OAuth 2.0 授权类型实现

实现各种 OAuth 2.0 授权流程。
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, Callable
from enum import Enum
import hashlib
import base64

from .client import OAuth2Client
from .token import (
    OAuth2Token, 
    AuthorizationCode, 
    DeviceCode,
    generate_token,
    generate_authorization_code,
    generate_device_code,
    generate_user_code,
    TokenType,
)


class GrantType(str, Enum):
    """授权类型"""
    AUTHORIZATION_CODE = "authorization_code"
    CLIENT_CREDENTIALS = "client_credentials"
    REFRESH_TOKEN = "refresh_token"
    DEVICE_CODE = "urn:ietf:params:oauth:grant-type:device_code"
    PASSWORD = "password"  # 不推荐使用


@dataclass
class GrantContext:
    """授权上下文
    
    包含授权过程中需要的所有信息。
    """
    client: OAuth2Client
    grant_type: GrantType
    scope: Optional[str] = None
    user_id: Optional[Any] = None
    
    # Authorization Code 相关
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    code_verifier: Optional[str] = None  # PKCE
    
    # Refresh Token 相关
    refresh_token: Optional[str] = None
    
    # Device Code 相关
    device_code: Optional[str] = None
    
    # 额外参数
    extra: Dict[str, Any] = None
    
    def __post_init__(self):
        if self.extra is None:
            self.extra = {}


class BaseGrant(ABC):
    """授权基类"""
    
    @property
    @abstractmethod
    def grant_type(self) -> GrantType:
        """返回授权类型"""
        pass
    
    @abstractmethod
    def validate(self, context: GrantContext) -> tuple:
        """验证授权请求
        
        Args:
            context: 授权上下文
            
        Returns:
            tuple: (is_valid, error_or_data)
        """
        pass
    
    @abstractmethod
    def create_token(self, context: GrantContext) -> OAuth2Token:
        """创建访问令牌
        
        Args:
            context: 授权上下文
            
        Returns:
            OAuth2Token: 访问令牌
        """
        pass


class AuthorizationCodeGrant(BaseGrant):
    """授权码授权
    
    标准的 OAuth 2.0 Authorization Code 流程。
    
    使用示例:
        grant = AuthorizationCodeGrant(
            code_store=get_code_from_db,
            code_consumer=mark_code_used,
        )
        
        context = GrantContext(
            client=client,
            grant_type=GrantType.AUTHORIZATION_CODE,
            code="auth_code_xxx",
            redirect_uri="http://localhost:8000/callback",
        )
        
        is_valid, data = grant.validate(context)
        if is_valid:
            token = grant.create_token(context)
    """
    
    def __init__(
        self,
        code_store: Callable[[str], Optional[AuthorizationCode]],
        code_consumer: Callable[[str], bool],
        access_token_expire_seconds: int = 3600,
        refresh_token_expire_seconds: int = 86400 * 30,
    ):
        """
        Args:
            code_store: 根据授权码获取 AuthorizationCode 对象
            code_consumer: 标记授权码已使用
            access_token_expire_seconds: 访问令牌过期时间
            refresh_token_expire_seconds: 刷新令牌过期时间
        """
        self.code_store = code_store
        self.code_consumer = code_consumer
        self.access_token_expire_seconds = access_token_expire_seconds
        self.refresh_token_expire_seconds = refresh_token_expire_seconds
    
    @property
    def grant_type(self) -> GrantType:
        return GrantType.AUTHORIZATION_CODE
    
    def validate(self, context: GrantContext) -> tuple:
        """验证授权码"""
        if not context.code:
            return False, {"error": "invalid_request", "error_description": "Missing code"}
        
        if not context.redirect_uri:
            return False, {"error": "invalid_request", "error_description": "Missing redirect_uri"}
        
        # 获取授权码信息
        auth_code = self.code_store(context.code)
        if not auth_code:
            return False, {"error": "invalid_grant", "error_description": "Invalid authorization code"}
        
        # 检查是否已使用
        if auth_code.is_used:
            return False, {"error": "invalid_grant", "error_description": "Authorization code already used"}
        
        # 检查是否过期
        if auth_code.is_expired():
            return False, {"error": "invalid_grant", "error_description": "Authorization code expired"}
        
        # 验证客户端
        if auth_code.client_id != context.client.client_id:
            return False, {"error": "invalid_grant", "error_description": "Client mismatch"}
        
        # 验证重定向 URI
        if auth_code.redirect_uri != context.redirect_uri:
            return False, {"error": "invalid_grant", "error_description": "Redirect URI mismatch"}
        
        # 验证 PKCE（如果使用）
        if auth_code.code_challenge:
            if not context.code_verifier:
                return False, {"error": "invalid_request", "error_description": "Missing code_verifier"}
            
            if not self._verify_pkce(
                context.code_verifier,
                auth_code.code_challenge,
                auth_code.code_challenge_method
            ):
                return False, {"error": "invalid_grant", "error_description": "Invalid code_verifier"}
        
        # 存储用户信息到上下文
        context.user_id = auth_code.user_id
        context.scope = auth_code.scope
        context.extra["nonce"] = auth_code.nonce
        
        return True, auth_code
    
    def _verify_pkce(
        self, 
        code_verifier: str, 
        code_challenge: str, 
        method: str
    ) -> bool:
        """验证 PKCE"""
        if method == "plain":
            return code_verifier == code_challenge
        elif method == "S256":
            computed = base64.urlsafe_b64encode(
                hashlib.sha256(code_verifier.encode()).digest()
            ).decode().rstrip("=")
            return computed == code_challenge
        return False
    
    def create_token(self, context: GrantContext) -> OAuth2Token:
        """创建访问令牌"""
        # 标记授权码已使用
        self.code_consumer(context.code)
        
        now = datetime.now(timezone.utc)
        
        return OAuth2Token(
            access_token=generate_token(32),
            token_type=TokenType.BEARER,
            expires_in=self.access_token_expire_seconds,
            refresh_token=generate_token(32),
            scope=context.scope,
            client_id=context.client.client_id,
            user_id=context.user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.access_token_expire_seconds),
            refresh_token_expires_at=now + timedelta(seconds=self.refresh_token_expire_seconds),
        )


class ClientCredentialsGrant(BaseGrant):
    """客户端凭证授权
    
    用于服务间通信，不涉及用户。
    
    使用示例:
        grant = ClientCredentialsGrant()
        
        context = GrantContext(
            client=client,
            grant_type=GrantType.CLIENT_CREDENTIALS,
            scope="api.read api.write",
        )
        
        is_valid, data = grant.validate(context)
        if is_valid:
            token = grant.create_token(context)
    """
    
    def __init__(
        self,
        access_token_expire_seconds: int = 3600,
    ):
        self.access_token_expire_seconds = access_token_expire_seconds
    
    @property
    def grant_type(self) -> GrantType:
        return GrantType.CLIENT_CREDENTIALS
    
    def validate(self, context: GrantContext) -> tuple:
        """验证客户端凭证"""
        # 客户端凭证模式不需要用户，只需要验证客户端
        if context.client.is_public():
            return False, {
                "error": "unauthorized_client",
                "error_description": "Public clients cannot use client_credentials grant"
            }
        
        # 验证权限范围
        if context.scope:
            is_valid, result = context.client.validate_scope(context.scope)
            if not is_valid:
                return False, {
                    "error": "invalid_scope",
                    "error_description": f"Invalid scopes: {result}"
                }
            context.scope = " ".join(result)
        else:
            context.scope = " ".join(context.client.default_scopes or [])
        
        return True, None
    
    def create_token(self, context: GrantContext) -> OAuth2Token:
        """创建访问令牌"""
        now = datetime.now(timezone.utc)
        
        return OAuth2Token(
            access_token=generate_token(32),
            token_type=TokenType.BEARER,
            expires_in=self.access_token_expire_seconds,
            refresh_token=None,  # 客户端凭证模式通常不提供刷新令牌
            scope=context.scope,
            client_id=context.client.client_id,
            user_id=None,  # 无用户
            created_at=now,
            expires_at=now + timedelta(seconds=self.access_token_expire_seconds),
        )


class RefreshTokenGrant(BaseGrant):
    """刷新令牌授权
    
    使用刷新令牌获取新的访问令牌。
    """
    
    def __init__(
        self,
        token_store: Callable[[str], Optional[OAuth2Token]],
        token_revoker: Callable[[str], bool],
        access_token_expire_seconds: int = 3600,
        refresh_token_expire_seconds: int = 86400 * 30,
        rotate_refresh_token: bool = True,
    ):
        """
        Args:
            token_store: 根据刷新令牌获取 Token 信息
            token_revoker: 撤销旧的刷新令牌
            access_token_expire_seconds: 访问令牌过期时间
            refresh_token_expire_seconds: 刷新令牌过期时间
            rotate_refresh_token: 是否轮换刷新令牌
        """
        self.token_store = token_store
        self.token_revoker = token_revoker
        self.access_token_expire_seconds = access_token_expire_seconds
        self.refresh_token_expire_seconds = refresh_token_expire_seconds
        self.rotate_refresh_token = rotate_refresh_token
    
    @property
    def grant_type(self) -> GrantType:
        return GrantType.REFRESH_TOKEN
    
    def validate(self, context: GrantContext) -> tuple:
        """验证刷新令牌"""
        if not context.refresh_token:
            return False, {"error": "invalid_request", "error_description": "Missing refresh_token"}
        
        # 获取 Token 信息
        token_data = self.token_store(context.refresh_token)
        if not token_data:
            return False, {"error": "invalid_grant", "error_description": "Invalid refresh token"}
        
        # 检查是否已撤销
        if token_data.is_revoked:
            return False, {"error": "invalid_grant", "error_description": "Refresh token revoked"}
        
        # 检查是否过期
        if token_data.is_refresh_token_expired():
            return False, {"error": "invalid_grant", "error_description": "Refresh token expired"}
        
        # 验证客户端
        if token_data.client_id != context.client.client_id:
            return False, {"error": "invalid_grant", "error_description": "Client mismatch"}
        
        # 存储信息到上下文
        context.user_id = token_data.user_id
        context.scope = token_data.scope
        context.extra["old_token"] = token_data
        
        return True, token_data
    
    def create_token(self, context: GrantContext) -> OAuth2Token:
        """创建新的访问令牌"""
        # 撤销旧的刷新令牌（如果轮换）
        if self.rotate_refresh_token:
            self.token_revoker(context.refresh_token)
        
        now = datetime.now(timezone.utc)
        
        new_refresh_token = None
        refresh_token_expires_at = None
        
        if self.rotate_refresh_token:
            new_refresh_token = generate_token(32)
            refresh_token_expires_at = now + timedelta(seconds=self.refresh_token_expire_seconds)
        else:
            # 保留原刷新令牌
            old_token = context.extra.get("old_token")
            if old_token:
                new_refresh_token = old_token.refresh_token
                refresh_token_expires_at = old_token.refresh_token_expires_at
        
        return OAuth2Token(
            access_token=generate_token(32),
            token_type=TokenType.BEARER,
            expires_in=self.access_token_expire_seconds,
            refresh_token=new_refresh_token,
            scope=context.scope,
            client_id=context.client.client_id,
            user_id=context.user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.access_token_expire_seconds),
            refresh_token_expires_at=refresh_token_expires_at,
        )


class DeviceCodeGrant(BaseGrant):
    """设备码授权
    
    用于智能设备和 CLI 工具。
    
    流程：
    1. 设备请求设备码和用户码
    2. 用户在浏览器中访问验证 URL 并输入用户码
    3. 用户授权后，设备使用设备码获取访问令牌
    """
    
    def __init__(
        self,
        device_code_store: Callable[[str], Optional[DeviceCode]],
        device_code_updater: Callable[[str, Dict[str, Any]], bool],
        access_token_expire_seconds: int = 3600,
        refresh_token_expire_seconds: int = 86400 * 30,
    ):
        """
        Args:
            device_code_store: 根据设备码获取 DeviceCode 对象
            device_code_updater: 更新设备码状态
            access_token_expire_seconds: 访问令牌过期时间
            refresh_token_expire_seconds: 刷新令牌过期时间
        """
        self.device_code_store = device_code_store
        self.device_code_updater = device_code_updater
        self.access_token_expire_seconds = access_token_expire_seconds
        self.refresh_token_expire_seconds = refresh_token_expire_seconds
    
    @property
    def grant_type(self) -> GrantType:
        return GrantType.DEVICE_CODE
    
    def validate(self, context: GrantContext) -> tuple:
        """验证设备码"""
        if not context.device_code:
            return False, {"error": "invalid_request", "error_description": "Missing device_code"}
        
        # 获取设备码信息
        device_code = self.device_code_store(context.device_code)
        if not device_code:
            return False, {"error": "invalid_grant", "error_description": "Invalid device code"}
        
        # 检查是否过期
        if device_code.is_expired():
            return False, {"error": "expired_token", "error_description": "Device code expired"}
        
        # 检查是否被拒绝
        if device_code.is_denied:
            return False, {"error": "access_denied", "error_description": "User denied the request"}
        
        # 检查是否已授权
        if not device_code.is_authorized:
            return False, {"error": "authorization_pending", "error_description": "Authorization pending"}
        
        # 验证客户端
        if device_code.client_id != context.client.client_id:
            return False, {"error": "invalid_grant", "error_description": "Client mismatch"}
        
        # 存储信息到上下文
        context.user_id = device_code.user_id
        context.scope = device_code.scope
        
        return True, device_code
    
    def create_token(self, context: GrantContext) -> OAuth2Token:
        """创建访问令牌"""
        now = datetime.now(timezone.utc)
        
        return OAuth2Token(
            access_token=generate_token(32),
            token_type=TokenType.BEARER,
            expires_in=self.access_token_expire_seconds,
            refresh_token=generate_token(32),
            scope=context.scope,
            client_id=context.client.client_id,
            user_id=context.user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=self.access_token_expire_seconds),
            refresh_token_expires_at=now + timedelta(seconds=self.refresh_token_expire_seconds),
        )
    
    def create_device_code(
        self,
        client: OAuth2Client,
        scope: str,
        verification_uri: str,
        expires_in: int = 1800,
        interval: int = 5,
    ) -> DeviceCode:
        """创建设备码
        
        Args:
            client: OAuth2 客户端
            scope: 权限范围
            verification_uri: 验证 URL
            expires_in: 过期时间（秒）
            interval: 轮询间隔（秒）
            
        Returns:
            DeviceCode: 设备码对象
        """
        device_code_str = generate_device_code(32)
        user_code = generate_user_code(8)
        
        # 构建完整的验证 URL
        verification_uri_complete = f"{verification_uri}?user_code={user_code}"
        
        return DeviceCode(
            device_code=device_code_str,
            user_code=user_code,
            client_id=client.client_id,
            scope=scope,
            verification_uri=verification_uri,
            verification_uri_complete=verification_uri_complete,
            expires_in=expires_in,
            interval=interval,
        )
