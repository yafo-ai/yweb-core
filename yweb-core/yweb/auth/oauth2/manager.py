"""OAuth 2.0 管理器

统一管理 OAuth 2.0 客户端、Token 和授权流程。
"""

from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Callable, List
import hashlib
import hmac
import base64

from .client import OAuth2Client, generate_client_id, generate_client_secret
from .token import (
    OAuth2Token,
    AuthorizationCode,
    DeviceCode,
    generate_token,
    generate_authorization_code,
)
from .grants import (
    GrantType,
    GrantContext,
    BaseGrant,
    AuthorizationCodeGrant,
    ClientCredentialsGrant,
    RefreshTokenGrant,
    DeviceCodeGrant,
)


class OAuth2Manager:
    """OAuth 2.0 管理器
    
    提供完整的 OAuth 2.0 功能：
    - 客户端管理
    - Token 管理
    - 授权流程处理
    
    使用示例:
        manager = OAuth2Manager(
            secret_key="your-secret-key",
            access_token_expire_minutes=30,
        )
        
        # 设置存储回调
        manager.set_stores(
            client_getter=get_client_by_id,
            token_saver=save_token,
            token_getter=get_token,
            code_saver=save_auth_code,
            code_getter=get_auth_code,
        )
        
        # 注册客户端
        client = manager.create_client(
            name="My App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        # 创建授权码
        code = manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid profile",
        )
        
        # 交换 Token
        token = manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
    """
    
    def __init__(
        self,
        secret_key: str,
        access_token_expire_minutes: int = 30,
        refresh_token_expire_days: int = 30,
        authorization_code_expire_minutes: int = 10,
        device_code_expire_minutes: int = 30,
        rotate_refresh_token: bool = True,
    ):
        """
        Args:
            secret_key: 密钥
            access_token_expire_minutes: 访问令牌过期时间（分钟）
            refresh_token_expire_days: 刷新令牌过期时间（天）
            authorization_code_expire_minutes: 授权码过期时间（分钟）
            device_code_expire_minutes: 设备码过期时间（分钟）
            rotate_refresh_token: 是否轮换刷新令牌
        """
        self.secret_key = secret_key
        self.access_token_expire_seconds = access_token_expire_minutes * 60
        self.refresh_token_expire_seconds = refresh_token_expire_days * 86400
        self.authorization_code_expire_seconds = authorization_code_expire_minutes * 60
        self.device_code_expire_seconds = device_code_expire_minutes * 60
        self.rotate_refresh_token = rotate_refresh_token
        
        # 内存存储（默认，生产环境应替换为持久化存储）
        self._clients: Dict[str, OAuth2Client] = {}
        self._tokens: Dict[str, OAuth2Token] = {}
        self._refresh_tokens: Dict[str, OAuth2Token] = {}
        self._authorization_codes: Dict[str, AuthorizationCode] = {}
        self._device_codes: Dict[str, DeviceCode] = {}
        
        # 存储回调
        self._client_getter: Optional[Callable[[str], Optional[OAuth2Client]]] = None
        self._client_saver: Optional[Callable[[OAuth2Client], bool]] = None
        self._token_saver: Optional[Callable[[OAuth2Token], bool]] = None
        self._token_getter: Optional[Callable[[str], Optional[OAuth2Token]]] = None
        self._refresh_token_getter: Optional[Callable[[str], Optional[OAuth2Token]]] = None
        self._token_revoker: Optional[Callable[[str], bool]] = None
        self._code_saver: Optional[Callable[[AuthorizationCode], bool]] = None
        self._code_getter: Optional[Callable[[str], Optional[AuthorizationCode]]] = None
        self._code_consumer: Optional[Callable[[str], bool]] = None
        self._device_code_saver: Optional[Callable[[DeviceCode], bool]] = None
        self._device_code_getter: Optional[Callable[[str], Optional[DeviceCode]]] = None
        self._device_code_updater: Optional[Callable[[str, Dict[str, Any]], bool]] = None
        
        # 授权类型处理器
        self._grants: Dict[GrantType, BaseGrant] = {}
        self._init_default_grants()
    
    def _init_default_grants(self):
        """初始化默认授权类型处理器"""
        self._setup_grants()
    
    def set_stores(
        self,
        client_getter: Callable[[str], Optional[OAuth2Client]] = None,
        client_saver: Callable[[OAuth2Client], bool] = None,
        token_saver: Callable[[OAuth2Token], bool] = None,
        token_getter: Callable[[str], Optional[OAuth2Token]] = None,
        refresh_token_getter: Callable[[str], Optional[OAuth2Token]] = None,
        token_revoker: Callable[[str], bool] = None,
        code_saver: Callable[[AuthorizationCode], bool] = None,
        code_getter: Callable[[str], Optional[AuthorizationCode]] = None,
        code_consumer: Callable[[str], bool] = None,
        device_code_saver: Callable[[DeviceCode], bool] = None,
        device_code_getter: Callable[[str], Optional[DeviceCode]] = None,
        device_code_updater: Callable[[str, Dict[str, Any]], bool] = None,
    ) -> "OAuth2Manager":
        """设置存储回调
        
        Args:
            client_getter: 根据 client_id 获取客户端
            client_saver: 保存客户端
            token_saver: 保存 Token
            token_getter: 根据 access_token 获取 Token
            refresh_token_getter: 根据 refresh_token 获取 Token
            token_revoker: 撤销 Token
            code_saver: 保存授权码
            code_getter: 获取授权码
            code_consumer: 标记授权码已使用
            device_code_saver: 保存设备码
            device_code_getter: 获取设备码
            device_code_updater: 更新设备码
            
        Returns:
            self: 支持链式调用
        """
        if client_getter:
            self._client_getter = client_getter
        if client_saver:
            self._client_saver = client_saver
        if token_saver:
            self._token_saver = token_saver
        if token_getter:
            self._token_getter = token_getter
        if refresh_token_getter:
            self._refresh_token_getter = refresh_token_getter
        if token_revoker:
            self._token_revoker = token_revoker
        if code_saver:
            self._code_saver = code_saver
        if code_getter:
            self._code_getter = code_getter
        if code_consumer:
            self._code_consumer = code_consumer
        if device_code_saver:
            self._device_code_saver = device_code_saver
        if device_code_getter:
            self._device_code_getter = device_code_getter
        if device_code_updater:
            self._device_code_updater = device_code_updater
        
        # 初始化授权类型处理器
        self._setup_grants()
        
        return self
    
    def _setup_grants(self):
        """设置授权类型处理器"""
        # Authorization Code
        self._grants[GrantType.AUTHORIZATION_CODE] = AuthorizationCodeGrant(
            code_store=self._get_code,
            code_consumer=self._consume_code,
            access_token_expire_seconds=self.access_token_expire_seconds,
            refresh_token_expire_seconds=self.refresh_token_expire_seconds,
        )
        
        # Client Credentials
        self._grants[GrantType.CLIENT_CREDENTIALS] = ClientCredentialsGrant(
            access_token_expire_seconds=self.access_token_expire_seconds,
        )
        
        # Refresh Token
        self._grants[GrantType.REFRESH_TOKEN] = RefreshTokenGrant(
            token_store=self._get_refresh_token,
            token_revoker=self._revoke_token,
            access_token_expire_seconds=self.access_token_expire_seconds,
            refresh_token_expire_seconds=self.refresh_token_expire_seconds,
            rotate_refresh_token=self.rotate_refresh_token,
        )
        
        # Device Code
        self._grants[GrantType.DEVICE_CODE] = DeviceCodeGrant(
            device_code_store=self._get_device_code,
            device_code_updater=self._update_device_code,
            access_token_expire_seconds=self.access_token_expire_seconds,
            refresh_token_expire_seconds=self.refresh_token_expire_seconds,
        )
    
    # ========== 内部存储方法 ==========
    
    def _get_client(self, client_id: str) -> Optional[OAuth2Client]:
        """获取客户端"""
        if self._client_getter:
            return self._client_getter(client_id)
        return self._clients.get(client_id)
    
    def _save_client(self, client: OAuth2Client) -> bool:
        """保存客户端"""
        if self._client_saver:
            return self._client_saver(client)
        self._clients[client.client_id] = client
        return True
    
    def _get_code(self, code: str) -> Optional[AuthorizationCode]:
        """获取授权码"""
        if self._code_getter:
            return self._code_getter(code)
        return self._authorization_codes.get(code)
    
    def _save_code(self, auth_code: AuthorizationCode) -> bool:
        """保存授权码"""
        if self._code_saver:
            return self._code_saver(auth_code)
        self._authorization_codes[auth_code.code] = auth_code
        return True
    
    def _consume_code(self, code: str) -> bool:
        """标记授权码已使用"""
        if self._code_consumer:
            return self._code_consumer(code)
        if code in self._authorization_codes:
            self._authorization_codes[code].is_used = True
            return True
        return False
    
    def _get_token(self, access_token: str) -> Optional[OAuth2Token]:
        """获取 Token"""
        if self._token_getter:
            return self._token_getter(access_token)
        return self._tokens.get(access_token)
    
    def _get_refresh_token(self, refresh_token: str) -> Optional[OAuth2Token]:
        """获取刷新令牌对应的 Token"""
        if self._refresh_token_getter:
            return self._refresh_token_getter(refresh_token)
        return self._refresh_tokens.get(refresh_token)
    
    def _save_token(self, token: OAuth2Token) -> bool:
        """保存 Token"""
        if self._token_saver:
            return self._token_saver(token)
        self._tokens[token.access_token] = token
        if token.refresh_token:
            self._refresh_tokens[token.refresh_token] = token
        return True
    
    def _revoke_token(self, token: str) -> bool:
        """撤销 Token"""
        if self._token_revoker:
            return self._token_revoker(token)
        
        # 检查是访问令牌还是刷新令牌
        if token in self._tokens:
            self._tokens[token].is_revoked = True
            return True
        if token in self._refresh_tokens:
            self._refresh_tokens[token].is_revoked = True
            return True
        return False
    
    def _get_device_code(self, device_code: str) -> Optional[DeviceCode]:
        """获取设备码"""
        if self._device_code_getter:
            return self._device_code_getter(device_code)
        return self._device_codes.get(device_code)
    
    def _save_device_code(self, device_code: DeviceCode) -> bool:
        """保存设备码"""
        if self._device_code_saver:
            return self._device_code_saver(device_code)
        self._device_codes[device_code.device_code] = device_code
        return True
    
    def _update_device_code(self, device_code: str, updates: Dict[str, Any]) -> bool:
        """更新设备码"""
        if self._device_code_updater:
            return self._device_code_updater(device_code, updates)
        if device_code in self._device_codes:
            for key, value in updates.items():
                setattr(self._device_codes[device_code], key, value)
            return True
        return False
    
    # ========== 客户端管理 ==========
    
    def create_client(
        self,
        name: str,
        redirect_uris: List[str],
        client_type: str = "confidential",
        allowed_grant_types: List[str] = None,
        allowed_scopes: List[str] = None,
        **kwargs,
    ) -> OAuth2Client:
        """创建新客户端
        
        Args:
            name: 客户端名称
            redirect_uris: 重定向 URI 列表
            client_type: 客户端类型
            allowed_grant_types: 允许的授权类型
            allowed_scopes: 允许的权限范围
            **kwargs: 其他参数
            
        Returns:
            OAuth2Client: 新创建的客户端
        """
        from .client import ClientType
        
        client_id = generate_client_id()
        client_secret = None
        client_secret_hash = None
        
        if client_type == "confidential":
            client_secret = generate_client_secret()
            client_secret_hash = self._hash_secret(client_secret)
        
        client = OAuth2Client(
            client_id=client_id,
            client_secret=client_secret,
            client_secret_hash=client_secret_hash,
            client_name=name,
            client_type=ClientType(client_type),
            redirect_uris=redirect_uris,
            allowed_grant_types=allowed_grant_types or ["authorization_code", "refresh_token"],
            allowed_scopes=allowed_scopes or ["openid", "profile", "email"],
            **kwargs,
        )
        
        self._save_client(client)
        return client
    
    def get_client(self, client_id: str) -> Optional[OAuth2Client]:
        """获取客户端"""
        return self._get_client(client_id)
    
    def validate_client(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
    ) -> tuple:
        """验证客户端
        
        Args:
            client_id: 客户端 ID
            client_secret: 客户端密钥
            
        Returns:
            tuple: (is_valid, client_or_error)
        """
        client = self._get_client(client_id)
        if not client:
            return False, "Client not found"
        
        if not client.is_active:
            return False, "Client is disabled"
        
        # 验证密钥
        if client.requires_secret():
            if not client_secret:
                return False, "Client secret required"
            
            # 验证密钥哈希
            if client.client_secret_hash:
                if self._hash_secret(client_secret) != client.client_secret_hash:
                    return False, "Invalid client secret"
            elif client.client_secret:
                if client_secret != client.client_secret:
                    return False, "Invalid client secret"
            else:
                return False, "Client secret not configured"
        
        return True, client
    
    def _hash_secret(self, secret: str) -> str:
        """计算密钥哈希"""
        return hmac.new(
            self.secret_key.encode(),
            secret.encode(),
            hashlib.sha256
        ).hexdigest()
    
    # ========== 授权码流程 ==========
    
    def create_authorization_code(
        self,
        client_id: str,
        user_id: Any,
        redirect_uri: str,
        scope: str,
        code_challenge: Optional[str] = None,
        code_challenge_method: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> str:
        """创建授权码
        
        Args:
            client_id: 客户端 ID
            user_id: 用户 ID
            redirect_uri: 重定向 URI
            scope: 权限范围
            code_challenge: PKCE code_challenge
            code_challenge_method: PKCE 方法
            nonce: OIDC nonce
            
        Returns:
            str: 授权码
        """
        code = generate_authorization_code()
        
        auth_code = AuthorizationCode(
            code=code,
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.authorization_code_expire_seconds),
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
        )
        
        self._save_code(auth_code)
        return code
    
    def exchange_code(
        self,
        code: str,
        client_id: str,
        client_secret: Optional[str],
        redirect_uri: str,
        code_verifier: Optional[str] = None,
    ) -> tuple:
        """交换授权码获取 Token
        
        Args:
            code: 授权码
            client_id: 客户端 ID
            client_secret: 客户端密钥
            redirect_uri: 重定向 URI
            code_verifier: PKCE code_verifier
            
        Returns:
            tuple: (success, token_or_error)
        """
        # 验证客户端
        is_valid, result = self.validate_client(client_id, client_secret)
        if not is_valid:
            return False, {"error": "invalid_client", "error_description": result}
        
        client = result
        
        # 验证授权类型
        if not client.validate_grant_type("authorization_code"):
            return False, {"error": "unauthorized_client", "error_description": "Grant type not allowed"}
        
        # 创建上下文
        context = GrantContext(
            client=client,
            grant_type=GrantType.AUTHORIZATION_CODE,
            code=code,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        
        # 获取授权处理器
        grant = self._grants.get(GrantType.AUTHORIZATION_CODE)
        if not grant:
            return False, {"error": "server_error", "error_description": "Grant handler not configured"}
        
        # 验证
        is_valid, result = grant.validate(context)
        if not is_valid:
            return False, result
        
        # 创建 Token
        token = grant.create_token(context)
        self._save_token(token)
        
        return True, token
    
    # ========== 客户端凭证流程 ==========
    
    def client_credentials_token(
        self,
        client_id: str,
        client_secret: str,
        scope: Optional[str] = None,
    ) -> tuple:
        """客户端凭证获取 Token
        
        Args:
            client_id: 客户端 ID
            client_secret: 客户端密钥
            scope: 权限范围
            
        Returns:
            tuple: (success, token_or_error)
        """
        # 验证客户端
        is_valid, result = self.validate_client(client_id, client_secret)
        if not is_valid:
            return False, {"error": "invalid_client", "error_description": result}
        
        client = result
        
        # 验证授权类型
        if not client.validate_grant_type("client_credentials"):
            return False, {"error": "unauthorized_client", "error_description": "Grant type not allowed"}
        
        # 创建上下文
        context = GrantContext(
            client=client,
            grant_type=GrantType.CLIENT_CREDENTIALS,
            scope=scope,
        )
        
        # 获取授权处理器
        grant = self._grants.get(GrantType.CLIENT_CREDENTIALS)
        if not grant:
            return False, {"error": "server_error", "error_description": "Grant handler not configured"}
        
        # 验证
        is_valid, result = grant.validate(context)
        if not is_valid:
            return False, result
        
        # 创建 Token
        token = grant.create_token(context)
        self._save_token(token)
        
        return True, token
    
    # ========== 刷新令牌流程 ==========
    
    def refresh_token(
        self,
        refresh_token: str,
        client_id: str,
        client_secret: Optional[str] = None,
        scope: Optional[str] = None,
    ) -> tuple:
        """刷新访问令牌
        
        Args:
            refresh_token: 刷新令牌
            client_id: 客户端 ID
            client_secret: 客户端密钥
            scope: 新的权限范围（可选）
            
        Returns:
            tuple: (success, token_or_error)
        """
        # 验证客户端
        is_valid, result = self.validate_client(client_id, client_secret)
        if not is_valid:
            return False, {"error": "invalid_client", "error_description": result}
        
        client = result
        
        # 验证授权类型
        if not client.validate_grant_type("refresh_token"):
            return False, {"error": "unauthorized_client", "error_description": "Grant type not allowed"}
        
        # 创建上下文
        context = GrantContext(
            client=client,
            grant_type=GrantType.REFRESH_TOKEN,
            refresh_token=refresh_token,
            scope=scope,
        )
        
        # 获取授权处理器
        grant = self._grants.get(GrantType.REFRESH_TOKEN)
        if not grant:
            return False, {"error": "server_error", "error_description": "Grant handler not configured"}
        
        # 验证
        is_valid, result = grant.validate(context)
        if not is_valid:
            return False, result
        
        # 创建 Token
        token = grant.create_token(context)
        self._save_token(token)
        
        return True, token
    
    # ========== 设备码流程 ==========
    
    def create_device_code(
        self,
        client_id: str,
        scope: str,
        verification_uri: str,
    ) -> tuple:
        """创建设备码
        
        Args:
            client_id: 客户端 ID
            scope: 权限范围
            verification_uri: 验证 URL
            
        Returns:
            tuple: (success, device_code_or_error)
        """
        client = self._get_client(client_id)
        if not client:
            return False, {"error": "invalid_client", "error_description": "Client not found"}
        
        # 验证授权类型
        grant_type = GrantType.DEVICE_CODE.value
        if not client.validate_grant_type(grant_type):
            return False, {"error": "unauthorized_client", "error_description": "Grant type not allowed"}
        
        # 获取授权处理器
        grant = self._grants.get(GrantType.DEVICE_CODE)
        if not grant:
            return False, {"error": "server_error", "error_description": "Grant handler not configured"}
        
        # 创建设备码
        device_code = grant.create_device_code(
            client=client,
            scope=scope,
            verification_uri=verification_uri,
            expires_in=self.device_code_expire_seconds,
        )
        
        self._save_device_code(device_code)
        return True, device_code
    
    def authorize_device(
        self,
        user_code: str,
        user_id: Any,
        approve: bool = True,
    ) -> tuple:
        """用户授权设备
        
        Args:
            user_code: 用户码
            user_id: 用户 ID
            approve: 是否批准
            
        Returns:
            tuple: (success, message)
        """
        # 查找设备码（通过用户码）
        device_code = None
        for dc in self._device_codes.values():
            if dc.user_code == user_code and not dc.is_expired():
                device_code = dc
                break
        
        if not device_code:
            return False, "Invalid or expired user code"
        
        if device_code.is_authorized or device_code.is_denied:
            return False, "Device code already processed"
        
        if approve:
            self._update_device_code(device_code.device_code, {
                "user_id": user_id,
                "is_authorized": True,
            })
            return True, "Device authorized"
        else:
            self._update_device_code(device_code.device_code, {
                "is_denied": True,
            })
            return True, "Device authorization denied"
    
    def device_code_token(
        self,
        device_code: str,
        client_id: str,
    ) -> tuple:
        """设备码获取 Token
        
        Args:
            device_code: 设备码
            client_id: 客户端 ID
            
        Returns:
            tuple: (success, token_or_error)
        """
        client = self._get_client(client_id)
        if not client:
            return False, {"error": "invalid_client", "error_description": "Client not found"}
        
        # 创建上下文
        context = GrantContext(
            client=client,
            grant_type=GrantType.DEVICE_CODE,
            device_code=device_code,
        )
        
        # 获取授权处理器
        grant = self._grants.get(GrantType.DEVICE_CODE)
        if not grant:
            return False, {"error": "server_error", "error_description": "Grant handler not configured"}
        
        # 验证
        is_valid, result = grant.validate(context)
        if not is_valid:
            return False, result
        
        # 创建 Token
        token = grant.create_token(context)
        self._save_token(token)
        
        return True, token
    
    # ========== Token 验证和撤销 ==========
    
    def validate_token(self, access_token: str) -> tuple:
        """验证访问令牌
        
        Args:
            access_token: 访问令牌
            
        Returns:
            tuple: (is_valid, token_data_or_error)
        """
        token = self._get_token(access_token)
        if not token:
            return False, "Invalid token"
        
        if token.is_revoked:
            return False, "Token revoked"
        
        if token.is_expired():
            return False, "Token expired"
        
        return True, token
    
    def revoke_token(self, token: str, token_type_hint: Optional[str] = None) -> bool:
        """撤销 Token
        
        Args:
            token: Token 字符串
            token_type_hint: Token 类型提示（access_token, refresh_token）
            
        Returns:
            bool: 是否成功
        """
        return self._revoke_token(token)
    
    def introspect_token(self, token: str) -> Dict[str, Any]:
        """Token 内省
        
        返回 Token 的详细信息（RFC 7662）
        
        Args:
            token: Token 字符串
            
        Returns:
            Dict: Token 信息
        """
        is_valid, result = self.validate_token(token)
        
        if not is_valid:
            return {"active": False}
        
        token_data = result
        return {
            "active": True,
            "client_id": token_data.client_id,
            "username": None,  # 需要从用户服务获取
            "scope": token_data.scope,
            "sub": str(token_data.user_id) if token_data.user_id else None,
            "exp": int(token_data.expires_at.timestamp()) if token_data.expires_at else None,
            "iat": int(token_data.created_at.timestamp()) if token_data.created_at else None,
            "token_type": token_data.token_type.value,
        }
