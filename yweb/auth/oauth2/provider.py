"""OAuth 2.0 认证提供者

实现 AuthProvider 接口，用于统一认证管理。
"""

from typing import Optional, Any, Callable

from ..base import AuthProvider, AuthType, UserIdentity, AuthResult
from .manager import OAuth2Manager
from .token import OAuth2Token


class OAuth2AuthProvider(AuthProvider):
    """OAuth 2.0 认证提供者
    
    将 OAuth2Manager 包装为统一的 AuthProvider 接口。
    
    使用示例:
        oauth2_manager = OAuth2Manager(secret_key="xxx")
        provider = OAuth2AuthProvider(
            oauth2_manager=oauth2_manager,
            user_getter=get_user_by_id,
        )
        
        # 验证 Token
        result = provider.validate_token("access_token_xxx")
        if result.success:
            print(result.identity.username)
    """
    
    def __init__(
        self,
        oauth2_manager: OAuth2Manager,
        user_getter: Optional[Callable[[Any], Optional[Any]]] = None,
    ):
        """
        Args:
            oauth2_manager: OAuth 2.0 管理器
            user_getter: 根据 user_id 获取用户的函数
        """
        self.oauth2_manager = oauth2_manager
        self.user_getter = user_getter
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.OAUTH2
    
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证凭证
        
        支持多种凭证格式：
        - {"grant_type": "client_credentials", "client_id": "xxx", "client_secret": "xxx"}
        - {"grant_type": "authorization_code", "code": "xxx", ...}
        - {"grant_type": "refresh_token", "refresh_token": "xxx", ...}
        
        Args:
            credentials: 凭证字典
            
        Returns:
            AuthResult: 认证结果
        """
        if not isinstance(credentials, dict):
            return AuthResult.fail("Invalid credentials format", "INVALID_CREDENTIALS")
        
        grant_type = credentials.get("grant_type")
        
        if grant_type == "client_credentials":
            return self._handle_client_credentials(credentials)
        elif grant_type == "authorization_code":
            return self._handle_authorization_code(credentials)
        elif grant_type == "refresh_token":
            return self._handle_refresh_token(credentials)
        elif grant_type == "urn:ietf:params:oauth:grant-type:device_code":
            return self._handle_device_code(credentials)
        else:
            return AuthResult.fail(f"Unsupported grant type: {grant_type}", "UNSUPPORTED_GRANT")
    
    def _handle_client_credentials(self, credentials: dict) -> AuthResult:
        """处理客户端凭证授权"""
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        scope = credentials.get("scope")
        
        if not client_id or not client_secret:
            return AuthResult.fail("Missing client credentials", "MISSING_CREDENTIALS")
        
        success, result = self.oauth2_manager.client_credentials_token(
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
        )
        
        if not success:
            return AuthResult.fail(
                result.get("error_description", "Authentication failed"),
                result.get("error", "AUTH_FAILED"),
            )
        
        return self._token_to_result(result)
    
    def _handle_authorization_code(self, credentials: dict) -> AuthResult:
        """处理授权码授权"""
        code = credentials.get("code")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        redirect_uri = credentials.get("redirect_uri")
        code_verifier = credentials.get("code_verifier")
        
        if not code or not client_id or not redirect_uri:
            return AuthResult.fail("Missing required parameters", "MISSING_PARAMS")
        
        success, result = self.oauth2_manager.exchange_code(
            code=code,
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=redirect_uri,
            code_verifier=code_verifier,
        )
        
        if not success:
            return AuthResult.fail(
                result.get("error_description", "Authentication failed"),
                result.get("error", "AUTH_FAILED"),
            )
        
        return self._token_to_result(result)
    
    def _handle_refresh_token(self, credentials: dict) -> AuthResult:
        """处理刷新令牌"""
        refresh_token = credentials.get("refresh_token")
        client_id = credentials.get("client_id")
        client_secret = credentials.get("client_secret")
        scope = credentials.get("scope")
        
        if not refresh_token or not client_id:
            return AuthResult.fail("Missing required parameters", "MISSING_PARAMS")
        
        success, result = self.oauth2_manager.refresh_token(
            refresh_token=refresh_token,
            client_id=client_id,
            client_secret=client_secret,
            scope=scope,
        )
        
        if not success:
            return AuthResult.fail(
                result.get("error_description", "Refresh failed"),
                result.get("error", "REFRESH_FAILED"),
            )
        
        return self._token_to_result(result)
    
    def _handle_device_code(self, credentials: dict) -> AuthResult:
        """处理设备码授权"""
        device_code = credentials.get("device_code")
        client_id = credentials.get("client_id")
        
        if not device_code or not client_id:
            return AuthResult.fail("Missing required parameters", "MISSING_PARAMS")
        
        success, result = self.oauth2_manager.device_code_token(
            device_code=device_code,
            client_id=client_id,
        )
        
        if not success:
            error = result.get("error", "AUTH_FAILED")
            # 设备码特殊错误
            if error == "authorization_pending":
                return AuthResult.fail("Authorization pending", "AUTHORIZATION_PENDING")
            elif error == "slow_down":
                return AuthResult.fail("Slow down", "SLOW_DOWN")
            elif error == "expired_token":
                return AuthResult.fail("Device code expired", "EXPIRED_TOKEN")
            elif error == "access_denied":
                return AuthResult.fail("Access denied", "ACCESS_DENIED")
            
            return AuthResult.fail(
                result.get("error_description", "Authentication failed"),
                error,
            )
        
        return self._token_to_result(result)
    
    def _token_to_result(self, token: OAuth2Token) -> AuthResult:
        """将 OAuth2Token 转换为 AuthResult"""
        user = None
        username = None
        email = None
        roles = []
        
        # 如果有用户 ID，尝试获取用户信息
        if token.user_id and self.user_getter:
            user = self.user_getter(token.user_id)
            if user:
                username = getattr(user, "username", str(token.user_id))
                email = getattr(user, "email", None)
                roles = getattr(user, "roles", [])
        
        if not username:
            username = str(token.user_id) if token.user_id else token.client_id
        
        # 解析权限范围
        scopes = token.scope.split() if token.scope else []
        
        identity = UserIdentity(
            user_id=token.user_id or token.client_id,
            username=username,
            email=email,
            roles=roles,
            permissions=scopes,
            auth_type=AuthType.OAUTH2,
            attributes={
                "client_id": token.client_id,
                "token_type": token.token_type.value,
            },
        )
        
        return AuthResult.ok(
            identity,
            access_token=token.access_token,
            refresh_token=token.refresh_token,
            expires_in=token.expires_in,
            scope=token.scope,
            token_type=token.token_type.value,
        )
    
    def validate_token(self, token: str) -> AuthResult:
        """验证访问令牌"""
        is_valid, result = self.oauth2_manager.validate_token(token)
        
        if not is_valid:
            return AuthResult.fail(result, "INVALID_TOKEN")
        
        token_data = result
        
        # 获取用户信息
        user = None
        username = None
        email = None
        roles = []
        
        if token_data.user_id and self.user_getter:
            user = self.user_getter(token_data.user_id)
            if user:
                username = getattr(user, "username", str(token_data.user_id))
                email = getattr(user, "email", None)
                roles = getattr(user, "roles", [])
        
        if not username:
            username = str(token_data.user_id) if token_data.user_id else token_data.client_id
        
        scopes = token_data.scope.split() if token_data.scope else []
        
        identity = UserIdentity(
            user_id=token_data.user_id or token_data.client_id,
            username=username,
            email=email,
            roles=roles,
            permissions=scopes,
            auth_type=AuthType.OAUTH2,
            attributes={
                "client_id": token_data.client_id,
                "token_type": token_data.token_type.value,
            },
        )
        
        return AuthResult.ok(identity)
    
    def refresh_token(self, refresh_token: str) -> AuthResult:
        """刷新 Token（简化接口）
        
        注意：此方法需要知道 client_id 才能工作。
        完整的刷新流程应使用 authenticate 方法。
        """
        return AuthResult.fail(
            "Use authenticate with grant_type=refresh_token",
            "NOT_SUPPORTED",
        )
    
    def revoke_token(self, token: str) -> bool:
        """撤销 Token"""
        return self.oauth2_manager.revoke_token(token)
