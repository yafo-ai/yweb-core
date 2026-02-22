"""API Key 认证模块

提供 API Key 的创建、验证和管理功能。

使用示例:
    from yweb.auth import APIKeyManager, APIKeyAuthProvider
    
    # 创建 API Key 管理器
    api_key_manager = APIKeyManager(
        secret_key="your-secret-key",
        prefix="yweb"
    )
    
    # 生成 API Key
    key_data = api_key_manager.generate_key(
        user_id=1,
        name="My API Key",
        scopes=["read", "write"],
        expires_days=365
    )
    print(key_data.key)  # yweb_xxxxxxxxxxxx
    
    # 验证 API Key
    result = api_key_manager.validate_key(key_data.key)
    if result:
        print(f"User ID: {result.user_id}")
    
    # 创建 FastAPI 依赖
    from fastapi import Depends
    get_api_key_user = api_key_manager.create_dependency(user_getter=get_user_by_id)
    
    @app.get("/api/data")
    def get_data(user = Depends(get_api_key_user)):
        return {"user": user.username}
"""

import secrets
import hashlib
import hmac
from datetime import datetime, timezone, timedelta
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Any, Callable
from functools import wraps

from fastapi import Depends, HTTPException, status, Request, Security
from fastapi.security import APIKeyHeader, APIKeyQuery, APIKeyCookie

from .base import AuthProvider, AuthType, UserIdentity, AuthResult


@dataclass
class APIKeyData:
    """API Key 数据
    
    Attributes:
        key: 完整的 API Key（仅在创建时返回）
        key_id: Key ID（用于标识）
        key_hash: Key 哈希值（用于存储和验证）
        user_id: 关联的用户 ID
        name: Key 名称/描述
        scopes: 权限范围列表
        created_at: 创建时间
        expires_at: 过期时间
        last_used_at: 最后使用时间
        is_active: 是否激活
        metadata: 额外元数据
    """
    key: Optional[str] = None  # 完整 key，仅创建时返回
    key_id: str = ""
    key_hash: str = ""
    user_id: Any = None
    name: str = ""
    scopes: List[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def has_scope(self, scope: str) -> bool:
        """检查是否有指定权限范围"""
        return scope in self.scopes or "*" in self.scopes
    
    def has_any_scope(self, scopes: List[str]) -> bool:
        """检查是否有任一权限范围"""
        if "*" in self.scopes:
            return True
        return any(scope in self.scopes for scope in scopes)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（不包含敏感信息）"""
        return {
            "key_id": self.key_id,
            "user_id": self.user_id,
            "name": self.name,
            "scopes": self.scopes,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "is_active": self.is_active,
            "metadata": self.metadata,
        }


class APIKeyManager:
    """API Key 管理器
    
    提供 API Key 的生成、验证和管理功能。
    
    Args:
        secret_key: 用于签名的密钥
        prefix: API Key 前缀（如 "yweb"）
        key_length: 随机部分的字节长度
        hash_algorithm: 哈希算法
    
    使用示例:
        manager = APIKeyManager(
            secret_key="your-secret-key",
            prefix="yweb"
        )
        
        # 生成 Key
        key_data = manager.generate_key(user_id=1, name="My Key")
        
        # 验证 Key
        is_valid, key_data = manager.validate_key_format(api_key)
    """
    
    def __init__(
        self,
        secret_key: str,
        prefix: str = "yweb",
        key_length: int = 32,
        hash_algorithm: str = "sha256",
    ):
        self.secret_key = secret_key
        self.prefix = prefix
        self.key_length = key_length
        self.hash_algorithm = hash_algorithm
        
        # Key 存储回调（由应用实现）
        self._key_store: Optional[Callable[[str], Optional[APIKeyData]]] = None
        self._key_saver: Optional[Callable[[APIKeyData], bool]] = None
        self._key_updater: Optional[Callable[[str, Dict[str, Any]], bool]] = None
        self._key_revoker: Optional[Callable[[str], bool]] = None
    
    def set_key_store(
        self,
        getter: Callable[[str], Optional[APIKeyData]],
        saver: Optional[Callable[[APIKeyData], bool]] = None,
        updater: Optional[Callable[[str, Dict[str, Any]], bool]] = None,
        revoker: Optional[Callable[[str], bool]] = None,
    ) -> "APIKeyManager":
        """设置 Key 存储回调
        
        Args:
            getter: 根据 key_id 或 key_hash 获取 APIKeyData
            saver: 保存新的 APIKeyData
            updater: 更新 APIKeyData
            revoker: 撤销 Key
            
        Returns:
            self: 支持链式调用
        """
        self._key_store = getter
        self._key_saver = saver
        self._key_updater = updater
        self._key_revoker = revoker
        return self
    
    def generate_key(
        self,
        user_id: Any,
        name: str = "",
        scopes: Optional[List[str]] = None,
        expires_days: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> APIKeyData:
        """生成新的 API Key
        
        Args:
            user_id: 关联的用户 ID
            name: Key 名称/描述
            scopes: 权限范围列表
            expires_days: 过期天数（None 表示永不过期）
            metadata: 额外元数据
            
        Returns:
            APIKeyData: 包含完整 Key 的数据对象
        """
        # 生成随机 Key
        random_bytes = secrets.token_bytes(self.key_length)
        key_id = secrets.token_hex(8)  # 16字符的 ID
        
        # 构建完整的 Key: prefix_keyid_randompart
        random_part = secrets.token_urlsafe(self.key_length)
        full_key = f"{self.prefix}_{key_id}_{random_part}"
        
        # 计算哈希值（用于存储）
        key_hash = self._hash_key(full_key)
        
        # 计算过期时间
        expires_at = None
        if expires_days:
            expires_at = datetime.now(timezone.utc) + timedelta(days=expires_days)
        
        key_data = APIKeyData(
            key=full_key,
            key_id=key_id,
            key_hash=key_hash,
            user_id=user_id,
            name=name,
            scopes=scopes or [],
            expires_at=expires_at,
            metadata=metadata or {},
        )
        
        # 如果设置了存储回调，保存 Key
        if self._key_saver:
            self._key_saver(key_data)
        
        return key_data
    
    def _hash_key(self, key: str) -> str:
        """计算 Key 的哈希值"""
        return hmac.new(
            self.secret_key.encode(),
            key.encode(),
            self.hash_algorithm
        ).hexdigest()
    
    def parse_key(self, api_key: str) -> Optional[tuple]:
        """解析 API Key 格式
        
        Args:
            api_key: API Key 字符串
            
        Returns:
            tuple: (prefix, key_id, random_part) 或 None
        """
        if not api_key:
            return None
        
        # 使用 maxsplit=2 限制分割次数，因为 random_part 可能包含下划线
        parts = api_key.split("_", maxsplit=2)
        if len(parts) != 3:
            return None
        
        prefix, key_id, random_part = parts
        if prefix != self.prefix:
            return None
        
        return prefix, key_id, random_part
    
    def validate_key_format(self, api_key: str) -> tuple:
        """验证 Key 格式
        
        Args:
            api_key: API Key 字符串
            
        Returns:
            tuple: (is_valid, key_id or error_message)
        """
        parsed = self.parse_key(api_key)
        if not parsed:
            return False, "Invalid API Key format"
        
        return True, parsed[1]  # 返回 key_id
    
    def validate_key(self, api_key: str) -> Optional[APIKeyData]:
        """验证 API Key
        
        需要设置 key_store 回调才能工作。
        
        Args:
            api_key: API Key 字符串
            
        Returns:
            APIKeyData: 验证成功返回 Key 数据，失败返回 None
        """
        # 检查格式
        is_valid, result = self.validate_key_format(api_key)
        if not is_valid:
            return None
        
        key_id = result
        
        # 计算哈希
        key_hash = self._hash_key(api_key)
        
        # 从存储中获取 Key 数据
        if not self._key_store:
            return None
        
        key_data = self._key_store(key_hash)
        if not key_data:
            # 尝试用 key_id 查找
            key_data = self._key_store(key_id)
            if not key_data or key_data.key_hash != key_hash:
                return None
        
        # 检查是否激活
        if not key_data.is_active:
            return None
        
        # 检查是否过期
        if key_data.is_expired():
            return None
        
        # 更新最后使用时间
        if self._key_updater:
            self._key_updater(key_data.key_id, {
                "last_used_at": datetime.now(timezone.utc)
            })
        
        return key_data
    
    def revoke_key(self, key_id: str) -> bool:
        """撤销 API Key
        
        Args:
            key_id: Key ID
            
        Returns:
            bool: 是否成功撤销
        """
        if self._key_revoker:
            return self._key_revoker(key_id)
        if self._key_updater:
            return self._key_updater(key_id, {"is_active": False})
        return False
    
    def create_dependency(
        self,
        user_getter: Callable[[Any], Optional[Any]],
        header_name: str = "X-API-Key",
        query_name: str = "api_key",
        cookie_name: Optional[str] = None,
        auto_error: bool = True,
        required_scopes: Optional[List[str]] = None,
    ) -> Callable:
        """创建 FastAPI 依赖
        
        Args:
            user_getter: 根据 user_id 获取用户的函数
            header_name: Header 名称
            query_name: Query 参数名称
            cookie_name: Cookie 名称（可选）
            auto_error: 认证失败是否自动抛出异常
            required_scopes: 必需的权限范围
            
        Returns:
            FastAPI 依赖函数
        """
        api_key_header = APIKeyHeader(name=header_name, auto_error=False)
        api_key_query = APIKeyQuery(name=query_name, auto_error=False)
        api_key_cookie = APIKeyCookie(name=cookie_name, auto_error=False) if cookie_name else None
        
        async def get_api_key(
            request: Request,
            api_key_header: Optional[str] = Security(api_key_header),
            api_key_query: Optional[str] = Security(api_key_query),
        ):
            # 从多个来源获取 API Key
            api_key = api_key_header or api_key_query
            
            # 尝试从 Cookie 获取
            if not api_key and api_key_cookie:
                api_key = request.cookies.get(cookie_name)
            
            if not api_key:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="API Key required",
                        headers={"WWW-Authenticate": "ApiKey"},
                    )
                return None
            
            # 验证 API Key
            key_data = self.validate_key(api_key)
            if not key_data:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Invalid or expired API Key",
                        headers={"WWW-Authenticate": "ApiKey"},
                    )
                return None
            
            # 检查权限范围
            if required_scopes and not key_data.has_any_scope(required_scopes):
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"API Key lacks required scopes: {required_scopes}",
                    )
                return None
            
            # 获取用户
            user = user_getter(key_data.user_id)
            if not user:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found",
                    )
                return None
            
            # 将 key_data 附加到 request.state
            request.state.api_key_data = key_data
            
            return user
        
        return get_api_key


class APIKeyAuthProvider(AuthProvider):
    """API Key 认证提供者
    
    实现 AuthProvider 接口，用于统一认证管理。
    
    使用示例:
        api_key_manager = APIKeyManager(secret_key="xxx")
        provider = APIKeyAuthProvider(
            api_key_manager=api_key_manager,
            user_getter=get_user_by_id
        )
        
        result = provider.authenticate({"api_key": "yweb_xxx_xxx"})
    """
    
    def __init__(
        self,
        api_key_manager: APIKeyManager,
        user_getter: Callable[[Any], Optional[Any]],
    ):
        self.api_key_manager = api_key_manager
        self.user_getter = user_getter
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.API_KEY
    
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证 API Key
        
        Args:
            credentials: 可以是字符串（API Key）或字典 {"api_key": "xxx"}
            
        Returns:
            AuthResult: 认证结果
        """
        # 提取 API Key
        if isinstance(credentials, str):
            api_key = credentials
        elif isinstance(credentials, dict):
            api_key = credentials.get("api_key")
        else:
            return AuthResult.fail("Invalid credentials format", "INVALID_CREDENTIALS")
        
        if not api_key:
            return AuthResult.fail("API Key required", "API_KEY_REQUIRED")
        
        # 验证 API Key
        key_data = self.api_key_manager.validate_key(api_key)
        if not key_data:
            return AuthResult.fail("Invalid or expired API Key", "INVALID_API_KEY")
        
        # 获取用户
        user = self.user_getter(key_data.user_id)
        if not user:
            return AuthResult.fail("User not found", "USER_NOT_FOUND")
        
        # 构建用户身份
        identity = UserIdentity(
            user_id=key_data.user_id,
            username=getattr(user, "username", str(key_data.user_id)),
            email=getattr(user, "email", None),
            roles=getattr(user, "roles", []),
            permissions=key_data.scopes,
            auth_type=AuthType.API_KEY,
            attributes={
                "key_id": key_data.key_id,
                "key_name": key_data.name,
            }
        )
        
        return AuthResult.ok(identity, key_data=key_data)
    
    def validate_token(self, token: str) -> AuthResult:
        """验证 API Key（Token 形式）"""
        return self.authenticate(token)
    
    def revoke_token(self, token: str) -> bool:
        """撤销 API Key"""
        parsed = self.api_key_manager.parse_key(token)
        if not parsed:
            return False
        key_id = parsed[1]
        return self.api_key_manager.revoke_key(key_id)


def require_api_key_scopes(*scopes: str):
    """要求 API Key 具有指定权限范围的装饰器
    
    使用示例:
        @app.get("/admin/data")
        @require_api_key_scopes("admin", "read")
        async def admin_data(request: Request):
            return {"data": "secret"}
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # 从 request.state 获取 key_data
            request = kwargs.get("request")
            if not request:
                for arg in args:
                    if isinstance(arg, Request):
                        request = arg
                        break
            
            if request and hasattr(request.state, "api_key_data"):
                key_data: APIKeyData = request.state.api_key_data
                if not key_data.has_any_scope(list(scopes)):
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail=f"API Key lacks required scopes: {list(scopes)}",
                    )
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator


# FastAPI 安全方案
api_key_header_scheme = APIKeyHeader(name="X-API-Key", auto_error=False)
api_key_query_scheme = APIKeyQuery(name="api_key", auto_error=False)


def get_api_key_from_request(
    request: Request,
    header_name: str = "X-API-Key",
    query_name: str = "api_key",
    cookie_name: Optional[str] = None,
) -> Optional[str]:
    """从请求中提取 API Key
    
    优先级：Header > Query > Cookie
    
    Args:
        request: FastAPI Request 对象
        header_name: Header 名称
        query_name: Query 参数名称
        cookie_name: Cookie 名称
        
    Returns:
        API Key 字符串或 None
    """
    # 从 Header 获取
    api_key = request.headers.get(header_name)
    if api_key:
        return api_key
    
    # 从 Query 获取
    api_key = request.query_params.get(query_name)
    if api_key:
        return api_key
    
    # 从 Cookie 获取
    if cookie_name:
        api_key = request.cookies.get(cookie_name)
        if api_key:
            return api_key
    
    return None
