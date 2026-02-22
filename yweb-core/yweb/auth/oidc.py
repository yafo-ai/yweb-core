"""OpenID Connect (OIDC) 模块

基于 OAuth 2.0 的身份认证层，提供标准化的用户身份认证。

主要功能：
- ID Token 生成和验证
- UserInfo 端点
- Discovery 端点
- 标准声明 (claims)

使用示例:
    from yweb.auth.oidc import OIDCManager, OIDCProvider
    
    # 创建 OIDC 管理器
    oidc_manager = OIDCManager(
        issuer="https://sso.example.com",
        secret_key="your-secret-key",
        oauth2_manager=oauth2_manager,
    )
    
    # 创建 ID Token
    id_token = oidc_manager.create_id_token(
        user_id=1,
        client_id="my-app",
        nonce="random-nonce",
    )
    
    # 验证 ID Token
    claims = oidc_manager.verify_id_token(id_token)
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any, Callable
import time

from fastapi import HTTPException, status

from .base import AuthProvider, AuthType, UserIdentity, AuthResult

# 尝试导入 JWT 库
try:
    from jose import jwt, JWTError
    JOSE_AVAILABLE = True
except ImportError:
    JOSE_AVAILABLE = False
    jwt = None
    JWTError = Exception


@dataclass
class OIDCClaims:
    """OIDC 标准声明
    
    定义 OpenID Connect 标准声明。
    """
    # 必需声明
    sub: str  # Subject - 用户唯一标识
    iss: str  # Issuer - 发行者
    aud: str  # Audience - 受众（客户端 ID）
    exp: int  # Expiration - 过期时间
    iat: int  # Issued At - 签发时间
    
    # 可选声明
    auth_time: Optional[int] = None  # 认证时间
    nonce: Optional[str] = None  # 随机数（防重放）
    acr: Optional[str] = None  # 认证上下文类引用
    amr: Optional[List[str]] = None  # 认证方法引用
    azp: Optional[str] = None  # 授权方
    
    # Profile 声明
    name: Optional[str] = None
    given_name: Optional[str] = None
    family_name: Optional[str] = None
    middle_name: Optional[str] = None
    nickname: Optional[str] = None
    preferred_username: Optional[str] = None
    profile: Optional[str] = None  # 个人主页 URL
    picture: Optional[str] = None  # 头像 URL
    website: Optional[str] = None
    gender: Optional[str] = None
    birthdate: Optional[str] = None  # YYYY-MM-DD
    zoneinfo: Optional[str] = None  # 时区
    locale: Optional[str] = None  # 语言
    updated_at: Optional[int] = None
    
    # Email 声明
    email: Optional[str] = None
    email_verified: Optional[bool] = None
    
    # Phone 声明
    phone_number: Optional[str] = None
    phone_number_verified: Optional[bool] = None
    
    # Address 声明
    address: Optional[Dict[str, str]] = None
    
    # 自定义声明
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self, include_empty: bool = False) -> Dict[str, Any]:
        """转换为字典"""
        data = {
            "sub": self.sub,
            "iss": self.iss,
            "aud": self.aud,
            "exp": self.exp,
            "iat": self.iat,
        }
        
        # 添加可选声明
        optional_fields = [
            "auth_time", "nonce", "acr", "amr", "azp",
            "name", "given_name", "family_name", "middle_name",
            "nickname", "preferred_username", "profile", "picture",
            "website", "gender", "birthdate", "zoneinfo", "locale",
            "updated_at", "email", "email_verified",
            "phone_number", "phone_number_verified", "address",
        ]
        
        for field_name in optional_fields:
            value = getattr(self, field_name)
            if value is not None or include_empty:
                data[field_name] = value
        
        # 添加自定义声明
        data.update(self.extra)
        
        return data


# OIDC 标准 Scope 定义
OIDC_SCOPES = {
    "openid": {
        "description": "OpenID Connect authentication",
        "claims": ["sub"],
    },
    "profile": {
        "description": "User profile information",
        "claims": [
            "name", "family_name", "given_name", "middle_name",
            "nickname", "preferred_username", "profile", "picture",
            "website", "gender", "birthdate", "zoneinfo", "locale",
            "updated_at",
        ],
    },
    "email": {
        "description": "User email address",
        "claims": ["email", "email_verified"],
    },
    "phone": {
        "description": "User phone number",
        "claims": ["phone_number", "phone_number_verified"],
    },
    "address": {
        "description": "User address",
        "claims": ["address"],
    },
}


class OIDCManager:
    """OpenID Connect 管理器
    
    提供 OIDC 核心功能：
    - ID Token 创建和验证
    - UserInfo 处理
    - 声明管理
    
    使用示例:
        manager = OIDCManager(
            issuer="https://sso.example.com",
            secret_key="your-secret-key",
        )
        
        # 创建 ID Token
        id_token = manager.create_id_token(
            user_id=1,
            client_id="my-app",
        )
        
        # 验证 ID Token
        claims = manager.verify_id_token(id_token)
    """
    
    def __init__(
        self,
        issuer: str,
        secret_key: str,
        algorithm: str = "HS256",
        id_token_expire_minutes: int = 60,
        user_claims_getter: Callable[[Any], Dict[str, Any]] = None,
    ):
        """
        Args:
            issuer: 发行者 URL
            secret_key: 签名密钥
            algorithm: 签名算法
            id_token_expire_minutes: ID Token 过期时间（分钟）
            user_claims_getter: 获取用户声明的回调函数
        """
        if not JOSE_AVAILABLE:
            raise ImportError(
                "python-jose 未安装。请运行: pip install python-jose[cryptography]"
            )
        
        self.issuer = issuer
        self.secret_key = secret_key
        self.algorithm = algorithm
        self.id_token_expire_seconds = id_token_expire_minutes * 60
        self.user_claims_getter = user_claims_getter
        
        # RSA 密钥对（用于签名，可选）
        self._private_key = None
        self._public_key = None
        self._jwks = None
    
    def set_keys(
        self,
        private_key: str = None,
        public_key: str = None,
        jwks: Dict = None,
    ) -> "OIDCManager":
        """设置签名密钥
        
        Args:
            private_key: RSA 私钥（PEM 格式）
            public_key: RSA 公钥（PEM 格式）
            jwks: JSON Web Key Set
            
        Returns:
            self: 支持链式调用
        """
        self._private_key = private_key
        self._public_key = public_key
        self._jwks = jwks
        return self
    
    def set_user_claims_getter(
        self,
        getter: Callable[[Any], Dict[str, Any]],
    ) -> "OIDCManager":
        """设置用户声明获取函数
        
        Args:
            getter: 回调函数，接收 user_id，返回声明字典
            
        Returns:
            self: 支持链式调用
        """
        self.user_claims_getter = getter
        return self
    
    def create_id_token(
        self,
        user_id: Any,
        client_id: str,
        scope: str = "openid",
        nonce: Optional[str] = None,
        auth_time: Optional[int] = None,
        access_token: Optional[str] = None,
        extra_claims: Optional[Dict[str, Any]] = None,
    ) -> str:
        """创建 ID Token
        
        Args:
            user_id: 用户 ID
            client_id: 客户端 ID
            scope: 权限范围
            nonce: 随机数
            auth_time: 认证时间戳
            access_token: 访问令牌（用于计算 at_hash）
            extra_claims: 额外声明
            
        Returns:
            str: ID Token (JWT)
        """
        now = int(time.time())
        
        # 基础声明
        claims = {
            "iss": self.issuer,
            "sub": str(user_id),
            "aud": client_id,
            "exp": now + self.id_token_expire_seconds,
            "iat": now,
        }
        
        # 添加 nonce
        if nonce:
            claims["nonce"] = nonce
        
        # 添加认证时间
        if auth_time:
            claims["auth_time"] = auth_time
        else:
            claims["auth_time"] = now
        
        # 添加 at_hash（访问令牌哈希）
        if access_token:
            claims["at_hash"] = self._compute_hash(access_token)
        
        # 根据 scope 添加声明
        scopes = scope.split() if scope else ["openid"]
        user_claims = self._get_user_claims(user_id, scopes)
        claims.update(user_claims)
        
        # 添加额外声明
        if extra_claims:
            claims.update(extra_claims)
        
        # 签名
        return jwt.encode(
            claims,
            self._get_signing_key(),
            algorithm=self.algorithm,
        )
    
    def verify_id_token(
        self,
        id_token: str,
        client_id: Optional[str] = None,
        nonce: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """验证 ID Token
        
        Args:
            id_token: ID Token 字符串
            client_id: 期望的客户端 ID
            nonce: 期望的 nonce
            
        Returns:
            Dict: 声明字典，验证失败返回 None
        """
        try:
            claims = jwt.decode(
                id_token,
                self._get_verification_key(),
                algorithms=[self.algorithm],
                audience=client_id,
                issuer=self.issuer,
            )
            
            # 验证 nonce
            if nonce and claims.get("nonce") != nonce:
                return None
            
            return claims
            
        except JWTError:
            return None
        except Exception:
            return None
    
    def _get_signing_key(self) -> str:
        """获取签名密钥"""
        if self._private_key and self.algorithm.startswith("RS"):
            return self._private_key
        return self.secret_key
    
    def _get_verification_key(self) -> str:
        """获取验证密钥"""
        if self._public_key and self.algorithm.startswith("RS"):
            return self._public_key
        return self.secret_key
    
    def _compute_hash(self, value: str) -> str:
        """计算哈希（用于 at_hash, c_hash）"""
        import hashlib
        import base64
        
        # 使用算法对应的哈希
        if self.algorithm in ("HS256", "RS256"):
            hash_func = hashlib.sha256
        elif self.algorithm in ("HS384", "RS384"):
            hash_func = hashlib.sha384
        else:
            hash_func = hashlib.sha512
        
        digest = hash_func(value.encode()).digest()
        # 取前半部分并 Base64URL 编码
        half = len(digest) // 2
        return base64.urlsafe_b64encode(digest[:half]).decode().rstrip("=")
    
    def _get_user_claims(
        self,
        user_id: Any,
        scopes: List[str],
    ) -> Dict[str, Any]:
        """获取用户声明"""
        if not self.user_claims_getter:
            return {}
        
        # 获取完整的用户信息
        user_data = self.user_claims_getter(user_id)
        if not user_data:
            return {}
        
        # 根据 scope 过滤声明
        claims = {}
        for scope in scopes:
            if scope in OIDC_SCOPES:
                for claim in OIDC_SCOPES[scope]["claims"]:
                    if claim in user_data:
                        claims[claim] = user_data[claim]
        
        return claims
    
    def get_userinfo(
        self,
        user_id: Any,
        scopes: List[str],
    ) -> Dict[str, Any]:
        """获取 UserInfo
        
        Args:
            user_id: 用户 ID
            scopes: 权限范围列表
            
        Returns:
            Dict: UserInfo 响应
        """
        claims = self._get_user_claims(user_id, scopes)
        claims["sub"] = str(user_id)
        return claims
    
    def get_discovery_document(self, base_url: str) -> Dict[str, Any]:
        """获取 OIDC Discovery 文档
        
        Args:
            base_url: 服务器基础 URL
            
        Returns:
            Dict: Discovery 文档
        """
        base_url = base_url.rstrip("/")
        
        return {
            "issuer": self.issuer,
            "authorization_endpoint": f"{base_url}/oauth2/authorize",
            "token_endpoint": f"{base_url}/oauth2/token",
            "userinfo_endpoint": f"{base_url}/oauth2/userinfo",
            "jwks_uri": f"{base_url}/.well-known/jwks.json",
            "revocation_endpoint": f"{base_url}/oauth2/revoke",
            "introspection_endpoint": f"{base_url}/oauth2/introspect",
            "device_authorization_endpoint": f"{base_url}/oauth2/device/code",
            
            "response_types_supported": [
                "code",
                "token",
                "id_token",
                "code token",
                "code id_token",
                "token id_token",
                "code token id_token",
            ],
            "subject_types_supported": ["public"],
            "id_token_signing_alg_values_supported": [self.algorithm],
            "scopes_supported": list(OIDC_SCOPES.keys()),
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
                "none",
            ],
            "claims_supported": [
                "sub", "iss", "aud", "exp", "iat", "auth_time", "nonce",
                "name", "given_name", "family_name", "nickname",
                "preferred_username", "profile", "picture", "website",
                "email", "email_verified", "gender", "birthdate",
                "zoneinfo", "locale", "phone_number", "phone_number_verified",
                "address", "updated_at",
            ],
            "code_challenge_methods_supported": ["plain", "S256"],
            "grant_types_supported": [
                "authorization_code",
                "refresh_token",
                "client_credentials",
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
        }
    
    def get_jwks(self) -> Dict[str, Any]:
        """获取 JSON Web Key Set"""
        if self._jwks:
            return self._jwks
        
        # 如果使用对称密钥，不公开
        if not self._public_key:
            return {"keys": []}
        
        # TODO: 从公钥生成 JWK
        return {"keys": []}


class OIDCAuthProvider(AuthProvider):
    """OIDC 认证提供者"""
    
    def __init__(
        self,
        oidc_manager: OIDCManager,
        user_getter: Callable[[Any], Optional[Any]] = None,
    ):
        self.oidc_manager = oidc_manager
        self.user_getter = user_getter
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.OIDC
    
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证 ID Token"""
        if isinstance(credentials, str):
            id_token = credentials
            client_id = None
            nonce = None
        elif isinstance(credentials, dict):
            id_token = credentials.get("id_token")
            client_id = credentials.get("client_id")
            nonce = credentials.get("nonce")
        else:
            return AuthResult.fail("Invalid credentials format", "INVALID_CREDENTIALS")
        
        if not id_token:
            return AuthResult.fail("ID Token required", "ID_TOKEN_REQUIRED")
        
        # 验证 ID Token
        claims = self.oidc_manager.verify_id_token(
            id_token=id_token,
            client_id=client_id,
            nonce=nonce,
        )
        
        if not claims:
            return AuthResult.fail("Invalid ID Token", "INVALID_ID_TOKEN")
        
        # 构建用户身份
        user_id = claims.get("sub")
        
        # 尝试获取完整用户信息
        user = None
        if self.user_getter and user_id:
            user = self.user_getter(user_id)
        
        identity = UserIdentity(
            user_id=user_id,
            username=claims.get("preferred_username") or claims.get("name") or user_id,
            email=claims.get("email"),
            roles=getattr(user, "roles", []) if user else [],
            auth_type=AuthType.OIDC,
            attributes=claims,
        )
        
        return AuthResult.ok(identity)
    
    def validate_token(self, token: str) -> AuthResult:
        """验证 ID Token"""
        return self.authenticate(token)


