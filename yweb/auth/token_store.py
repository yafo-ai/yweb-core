"""Token 存储和撤销模块

提供 Token 撤销/黑名单功能，支持多种存储后端。

使用示例:
    from yweb.auth.token_store import InMemoryTokenStore, TokenBlacklist
    
    # 使用内存存储（适用于单实例）
    store = InMemoryTokenStore()
    blacklist = TokenBlacklist(store)
    
    # 撤销单个 Token
    blacklist.revoke_token(token, reason="user_logout")
    
    # 撤销用户所有 Token
    blacklist.revoke_all_user_tokens(user_id=1)
    
    # 检查 Token 是否被撤销
    if blacklist.is_revoked(token):
        raise HTTPException(status_code=401, detail="Token 已被撤销")

Redis 存储示例:
    from yweb.auth.token_store import RedisTokenStore, TokenBlacklist
    import redis
    
    redis_client = redis.Redis(host='localhost', port=6379, db=0)
    store = RedisTokenStore(redis_client, prefix="token_blacklist:")
    blacklist = TokenBlacklist(store)
"""

from abc import ABC, abstractmethod
from datetime import datetime, timezone, timedelta
from typing import Optional, Dict, Any, Set, List
from dataclasses import dataclass, field


@dataclass
class RevokedTokenInfo:
    """被撤销的 Token 信息"""
    token_hash: str  # Token 的哈希值（不存储原始 Token）
    user_id: Optional[int] = None
    revoked_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None  # Token 原本的过期时间
    reason: str = ""  # 撤销原因
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "token_hash": self.token_hash,
            "user_id": self.user_id,
            "revoked_at": self.revoked_at.isoformat() if self.revoked_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "reason": self.reason,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RevokedTokenInfo":
        revoked_at = data.get("revoked_at")
        expires_at = data.get("expires_at")
        return cls(
            token_hash=data["token_hash"],
            user_id=data.get("user_id"),
            revoked_at=datetime.fromisoformat(revoked_at) if revoked_at else datetime.now(timezone.utc),
            expires_at=datetime.fromisoformat(expires_at) if expires_at else None,
            reason=data.get("reason", ""),
        )


class TokenStore(ABC):
    """Token 存储抽象基类
    
    定义 Token 撤销所需的存储接口。
    """
    
    @abstractmethod
    def add(self, info: RevokedTokenInfo) -> bool:
        """添加被撤销的 Token
        
        Args:
            info: 撤销信息
            
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    def exists(self, token_hash: str) -> bool:
        """检查 Token 是否在黑名单中
        
        Args:
            token_hash: Token 哈希值
            
        Returns:
            是否存在
        """
        pass
    
    @abstractmethod
    def get(self, token_hash: str) -> Optional[RevokedTokenInfo]:
        """获取撤销信息
        
        Args:
            token_hash: Token 哈希值
            
        Returns:
            撤销信息，不存在返回 None
        """
        pass
    
    @abstractmethod
    def remove(self, token_hash: str) -> bool:
        """从黑名单中移除（用于清理过期记录）
        
        Args:
            token_hash: Token 哈希值
            
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    def get_by_user(self, user_id: int) -> List[RevokedTokenInfo]:
        """获取用户所有被撤销的 Token
        
        Args:
            user_id: 用户 ID
            
        Returns:
            撤销信息列表
        """
        pass
    
    @abstractmethod
    def add_user_revocation(self, user_id: int, revoked_at: datetime) -> bool:
        """记录用户级别的撤销（撤销该时间之前的所有 Token）
        
        Args:
            user_id: 用户 ID
            revoked_at: 撤销时间
            
        Returns:
            是否成功
        """
        pass
    
    @abstractmethod
    def get_user_revocation_time(self, user_id: int) -> Optional[datetime]:
        """获取用户的撤销时间
        
        Args:
            user_id: 用户 ID
            
        Returns:
            撤销时间，未设置返回 None
        """
        pass
    
    @abstractmethod
    def cleanup_expired(self) -> int:
        """清理过期的记录
        
        Returns:
            清理的数量
        """
        pass


class InMemoryTokenStore(TokenStore):
    """内存 Token 存储
    
    适用于单实例部署，重启后数据丢失。
    
    使用示例:
        store = InMemoryTokenStore()
    """
    
    def __init__(self):
        self._tokens: Dict[str, RevokedTokenInfo] = {}
        self._user_tokens: Dict[int, Set[str]] = {}
        self._user_revocations: Dict[int, datetime] = {}
    
    def add(self, info: RevokedTokenInfo) -> bool:
        self._tokens[info.token_hash] = info
        
        if info.user_id:
            if info.user_id not in self._user_tokens:
                self._user_tokens[info.user_id] = set()
            self._user_tokens[info.user_id].add(info.token_hash)
        
        return True
    
    def exists(self, token_hash: str) -> bool:
        return token_hash in self._tokens
    
    def get(self, token_hash: str) -> Optional[RevokedTokenInfo]:
        return self._tokens.get(token_hash)
    
    def remove(self, token_hash: str) -> bool:
        info = self._tokens.pop(token_hash, None)
        if info and info.user_id and info.user_id in self._user_tokens:
            self._user_tokens[info.user_id].discard(token_hash)
        return info is not None
    
    def get_by_user(self, user_id: int) -> List[RevokedTokenInfo]:
        token_hashes = self._user_tokens.get(user_id, set())
        return [self._tokens[h] for h in token_hashes if h in self._tokens]
    
    def add_user_revocation(self, user_id: int, revoked_at: datetime) -> bool:
        self._user_revocations[user_id] = revoked_at
        return True
    
    def get_user_revocation_time(self, user_id: int) -> Optional[datetime]:
        return self._user_revocations.get(user_id)
    
    def cleanup_expired(self) -> int:
        now = datetime.now(timezone.utc)
        expired = [
            h for h, info in self._tokens.items()
            if info.expires_at and info.expires_at < now
        ]
        
        for h in expired:
            self.remove(h)
        
        return len(expired)


class RedisTokenStore(TokenStore):
    """Redis Token 存储
    
    适用于多实例部署，数据持久化。
    
    使用示例:
        import redis
        
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        store = RedisTokenStore(redis_client, prefix="token_blacklist:")
    
    注意: 需要安装 redis 包: pip install redis
    """
    
    def __init__(
        self,
        redis_client,
        prefix: str = "token_blacklist:",
        default_ttl_seconds: int = 86400 * 7,  # 默认 7 天
    ):
        """
        Args:
            redis_client: Redis 客户端实例
            prefix: 键前缀
            default_ttl_seconds: 默认 TTL（秒）
        """
        self._redis = redis_client
        self._prefix = prefix
        self._default_ttl = default_ttl_seconds
    
    def _token_key(self, token_hash: str) -> str:
        return f"{self._prefix}token:{token_hash}"
    
    def _user_key(self, user_id: int) -> str:
        return f"{self._prefix}user:{user_id}"
    
    def _user_revoke_key(self, user_id: int) -> str:
        return f"{self._prefix}user_revoke:{user_id}"
    
    def add(self, info: RevokedTokenInfo) -> bool:
        import json
        
        key = self._token_key(info.token_hash)
        
        # 计算 TTL
        ttl = self._default_ttl
        if info.expires_at:
            remaining = (info.expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining > 0:
                ttl = int(remaining) + 60  # 多保留 1 分钟
        
        self._redis.setex(key, ttl, json.dumps(info.to_dict()))
        
        if info.user_id:
            self._redis.sadd(self._user_key(info.user_id), info.token_hash)
        
        return True
    
    def exists(self, token_hash: str) -> bool:
        return self._redis.exists(self._token_key(token_hash)) > 0
    
    def get(self, token_hash: str) -> Optional[RevokedTokenInfo]:
        import json
        
        data = self._redis.get(self._token_key(token_hash))
        if not data:
            return None
        
        return RevokedTokenInfo.from_dict(json.loads(data))
    
    def remove(self, token_hash: str) -> bool:
        info = self.get(token_hash)
        result = self._redis.delete(self._token_key(token_hash)) > 0
        
        if info and info.user_id:
            self._redis.srem(self._user_key(info.user_id), token_hash)
        
        return result
    
    def get_by_user(self, user_id: int) -> List[RevokedTokenInfo]:
        token_hashes = self._redis.smembers(self._user_key(user_id))
        result = []
        
        for h in token_hashes:
            if isinstance(h, bytes):
                h = h.decode()
            info = self.get(h)
            if info:
                result.append(info)
        
        return result
    
    def add_user_revocation(self, user_id: int, revoked_at: datetime) -> bool:
        key = self._user_revoke_key(user_id)
        self._redis.set(key, revoked_at.isoformat())
        return True
    
    def get_user_revocation_time(self, user_id: int) -> Optional[datetime]:
        key = self._user_revoke_key(user_id)
        data = self._redis.get(key)
        if not data:
            return None
        
        if isinstance(data, bytes):
            data = data.decode()
        
        return datetime.fromisoformat(data)
    
    def cleanup_expired(self) -> int:
        # Redis 自动通过 TTL 清理，这里返回 0
        return 0


class TokenBlacklist:
    """Token 黑名单管理器
    
    提供 Token 撤销和检查的高级接口。
    
    使用示例:
        from yweb.auth.token_store import InMemoryTokenStore, TokenBlacklist
        from yweb.auth import JWTManager
        
        store = InMemoryTokenStore()
        jwt_manager = JWTManager(secret_key="xxx")
        blacklist = TokenBlacklist(store, jwt_manager)
        
        # 撤销 Token
        blacklist.revoke_token(token, reason="user_logout")
        
        # 检查
        if blacklist.is_revoked(token):
            print("Token 已被撤销")
    """
    
    def __init__(
        self,
        store: TokenStore,
        jwt_manager: Optional["JWTManager"] = None,
    ):
        """
        Args:
            store: Token 存储后端
            jwt_manager: JWT 管理器（用于解析 Token）
        """
        self._store = store
        self._jwt_manager = jwt_manager
    
    def _hash_token(self, token: str) -> str:
        """计算 Token 哈希值"""
        import hashlib
        return hashlib.sha256(token.encode()).hexdigest()
    
    def _get_token_info(self, token: str) -> tuple:
        """从 Token 中提取信息
        
        Returns:
            (user_id, expires_at)
        """
        if not self._jwt_manager:
            return None, None
        
        token_data = self._jwt_manager.verify_token(token)
        if not token_data:
            return None, None
        
        user_id = token_data.user_id
        
        # 获取过期时间
        expires_at = None
        if token_data.exp:
            expires_at = datetime.fromtimestamp(token_data.exp, tz=timezone.utc)
        
        return user_id, expires_at
    
    def revoke_token(self, token: str, reason: str = "") -> bool:
        """撤销单个 Token
        
        Args:
            token: JWT Token 字符串
            reason: 撤销原因
            
        Returns:
            是否成功
        """
        token_hash = self._hash_token(token)
        user_id, expires_at = self._get_token_info(token)
        
        info = RevokedTokenInfo(
            token_hash=token_hash,
            user_id=user_id,
            expires_at=expires_at,
            reason=reason,
        )
        
        return self._store.add(info)
    
    def revoke_all_user_tokens(self, user_id: int, reason: str = "all_tokens_revoked") -> bool:
        """撤销用户的所有 Token
        
        通过记录撤销时间实现，之前颁发的所有 Token 都将被视为无效。
        
        Args:
            user_id: 用户 ID
            reason: 撤销原因
            
        Returns:
            是否成功
        """
        return self._store.add_user_revocation(user_id, datetime.now(timezone.utc))
    
    def is_revoked(self, token: str) -> bool:
        """检查 Token 是否被撤销
        
        检查逻辑:
        1. 检查 Token 是否在黑名单中
        2. 检查用户是否有全局撤销记录（撤销时间晚于 Token 颁发时间）
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            是否被撤销
        """
        token_hash = self._hash_token(token)
        
        # 检查单个 Token 是否被撤销
        if self._store.exists(token_hash):
            return True
        
        # 检查用户级别的撤销
        if self._jwt_manager:
            token_data = self._jwt_manager.verify_token(token)
            if token_data and token_data.user_id:
                revoke_time = self._store.get_user_revocation_time(token_data.user_id)
                if revoke_time and token_data.iat:
                    token_issued_at = datetime.fromtimestamp(token_data.iat, tz=timezone.utc)
                    if token_issued_at < revoke_time:
                        return True
        
        return False
    
    def get_revocation_info(self, token: str) -> Optional[RevokedTokenInfo]:
        """获取 Token 的撤销信息
        
        Args:
            token: JWT Token 字符串
            
        Returns:
            撤销信息，未被撤销返回 None
        """
        token_hash = self._hash_token(token)
        return self._store.get(token_hash)
    
    def cleanup(self) -> int:
        """清理过期的记录
        
        Returns:
            清理的数量
        """
        return self._store.cleanup_expired()


# 全局默认黑名单实例（使用内存存储）
_default_blacklist: Optional[TokenBlacklist] = None


def get_token_blacklist() -> Optional[TokenBlacklist]:
    """获取全局 Token 黑名单实例"""
    return _default_blacklist


def configure_token_blacklist(
    store: Optional[TokenStore] = None,
    jwt_manager: Optional["JWTManager"] = None,
) -> TokenBlacklist:
    """配置全局 Token 黑名单
    
    Args:
        store: Token 存储后端，默认使用内存存储
        jwt_manager: JWT 管理器
        
    Returns:
        配置好的 TokenBlacklist 实例
    
    使用示例:
        from yweb.auth import JWTManager
        from yweb.auth.token_store import configure_token_blacklist
        
        jwt_manager = JWTManager(secret_key="xxx")
        blacklist = configure_token_blacklist(jwt_manager=jwt_manager)
    """
    global _default_blacklist
    
    if store is None:
        store = InMemoryTokenStore()
    
    _default_blacklist = TokenBlacklist(store, jwt_manager)
    return _default_blacklist
