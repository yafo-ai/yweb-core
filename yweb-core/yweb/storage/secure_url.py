# -*- coding: utf-8 -*-
"""
安全URL生成器

提供两种安全的文件访问机制：
1. Token访问：生成随机Token，信息存储在服务端，支持用户绑定、下载次数限制
2. 签名URL：使用HMAC签名，无需服务端存储，适合公开分享

使用示例:
    # Token访问（需要登录）
    generator = SecureURLGenerator(secret_key="your-key")
    secure_url = generator.generate("private/report.pdf", user_id=123)
    
    # 签名URL（可公开分享）
    signed_url = generator.generate_signed("public/image.jpg", expires_in=86400)
"""

import base64
import hashlib
import hmac
import logging
import secrets
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class SecureURL:
    """安全访问URL
    
    Attributes:
        url: 完整的访问URL
        token: 访问令牌
        expires_at: 过期时间
        file_path: 原始文件路径
    """
    url: str
    token: str
    expires_at: datetime
    file_path: str
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'url': self.url,
            'token': self.token,
            'expires_at': self.expires_at.isoformat(),
            'file_path': self.file_path,
        }


@dataclass
class TokenInfo:
    """Token信息
    
    存储在服务端的Token元数据。
    
    Attributes:
        file_path: 文件路径
        expires_at: 过期时间
        user_id: 限制访问的用户ID（可选）
        download: 是否强制下载
        filename: 下载时的文件名（可选）
        max_downloads: 最大下载次数（可选）
        download_count: 当前下载次数
        metadata: 附加元数据
    """
    file_path: str
    expires_at: datetime
    user_id: Optional[int] = None
    download: bool = False
    filename: Optional[str] = None
    max_downloads: Optional[int] = None
    download_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'file_path': self.file_path,
            'expires_at': self.expires_at.isoformat(),
            'user_id': self.user_id,
            'download': self.download,
            'filename': self.filename,
            'max_downloads': self.max_downloads,
            'download_count': self.download_count,
            'metadata': self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'TokenInfo':
        """从字典创建"""
        return cls(
            file_path=data['file_path'],
            expires_at=datetime.fromisoformat(data['expires_at']),
            user_id=data.get('user_id'),
            download=data.get('download', False),
            filename=data.get('filename'),
            max_downloads=data.get('max_downloads'),
            download_count=data.get('download_count', 0),
            metadata=data.get('metadata', {}),
        )


class TokenStore:
    """Token存储接口
    
    定义Token存储的抽象接口，可以有不同的实现（内存、Redis等）。
    """
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        """存储Token
        
        Args:
            token: Token字符串
            info: Token信息
            ttl: 过期时间（秒）
        """
        raise NotImplementedError
    
    def get(self, token: str) -> Optional[TokenInfo]:
        """获取Token信息
        
        Args:
            token: Token字符串
            
        Returns:
            TokenInfo: Token信息，不存在或已过期返回 None
        """
        raise NotImplementedError
    
    def delete(self, token: str) -> None:
        """删除Token
        
        Args:
            token: Token字符串
        """
        raise NotImplementedError
    
    def increment_downloads(self, token: str) -> int:
        """增加下载计数
        
        Args:
            token: Token字符串
            
        Returns:
            int: 新的下载计数，Token不存在返回 0
        """
        raise NotImplementedError


class MemoryTokenStore(TokenStore):
    """内存Token存储
    
    将Token存储在内存中，适用于开发和测试环境。
    
    Note:
        - 重启后数据丢失
        - 不适合多进程/多实例部署
        - 生产环境建议使用 RedisTokenStore
    """
    
    def __init__(self):
        self._store: Dict[str, TokenInfo] = {}
        self._lock = threading.RLock()
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        with self._lock:
            self._store[token] = info
    
    def get(self, token: str) -> Optional[TokenInfo]:
        with self._lock:
            info = self._store.get(token)
            if info is None:
                return None
            
            # 检查是否过期
            if datetime.now() > info.expires_at:
                del self._store[token]
                return None
            
            return info
    
    def delete(self, token: str) -> None:
        with self._lock:
            self._store.pop(token, None)
    
    def increment_downloads(self, token: str) -> int:
        with self._lock:
            info = self._store.get(token)
            if info is None:
                return 0
            info.download_count += 1
            return info.download_count
    
    def clear(self) -> None:
        """清空所有Token（仅用于测试）"""
        with self._lock:
            self._store.clear()
    
    def count(self) -> int:
        """获取Token数量（仅用于测试）"""
        return len(self._store)


class RedisTokenStore(TokenStore):
    """Redis Token存储
    
    将Token存储在Redis中，适用于生产环境。
    
    Args:
        redis_client: Redis客户端实例
        prefix: Key前缀
    
    Example:
        import redis
        
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        store = RedisTokenStore(redis_client)
    
    Note:
        需要安装 redis 包: pip install redis
    """
    
    def __init__(self, redis_client, prefix: str = "storage:token:"):
        self.redis = redis_client
        self.prefix = prefix
    
    def _key(self, token: str) -> str:
        """构建Redis Key"""
        return f"{self.prefix}{token}"
    
    def set(self, token: str, info: TokenInfo, ttl: int) -> None:
        import json
        data = json.dumps(info.to_dict())
        self.redis.setex(self._key(token), ttl, data)
    
    def get(self, token: str) -> Optional[TokenInfo]:
        import json
        data = self.redis.get(self._key(token))
        if data is None:
            return None
        
        try:
            return TokenInfo.from_dict(json.loads(data))
        except Exception:
            return None
    
    def delete(self, token: str) -> None:
        self.redis.delete(self._key(token))
    
    def increment_downloads(self, token: str) -> int:
        """原子性地增加下载计数"""
        import json
        
        # 使用 Lua 脚本保证原子性
        script = """
        local data = redis.call('GET', KEYS[1])
        if not data then return -1 end
        local obj = cjson.decode(data)
        obj.download_count = (obj.download_count or 0) + 1
        redis.call('SET', KEYS[1], cjson.encode(obj), 'KEEPTTL')
        return obj.download_count
        """
        
        try:
            result = self.redis.eval(script, 1, self._key(token))
            return result if result >= 0 else 0
        except Exception:
            # 降级为非原子操作
            info = self.get(token)
            if info is None:
                return 0
            info.download_count += 1
            # 获取剩余TTL
            ttl = self.redis.ttl(self._key(token))
            if ttl > 0:
                self.set(token, info, ttl)
            return info.download_count


class SecureURLGenerator:
    """安全URL生成器
    
    提供两种安全访问机制：
    1. Token访问：生成随机Token，信息存储在服务端
    2. 签名URL：使用HMAC签名，无需服务端存储
    
    Args:
        secret_key: 签名密钥（建议至少32字符）
        base_url: URL前缀
        token_store: Token存储实现（默认使用内存存储）
    
    Example:
        # 初始化
        generator = SecureURLGenerator(
            secret_key="your-secret-key-at-least-32-chars",
            base_url="/api/files",
        )
        
        # 生成Token访问URL（需要验证用户）
        secure_url = generator.generate(
            file_path="private/report.pdf",
            expires_in=3600,
            user_id=123,
            download=True,
            filename="报告.pdf",
            max_downloads=3,
        )
        print(secure_url.url)  # /api/files/t/abc123...
        
        # 生成签名URL（可分享，无需登录）
        signed_url = generator.generate_signed(
            file_path="public/image.jpg",
            expires_in=86400,
        )
        print(signed_url)  # /api/files/s/cHVibGljL2ltYWdl...?e=1234567890&s=abc123
    """
    
    def __init__(
        self,
        secret_key: str,
        base_url: str = "/api/files",
        token_store: Optional[TokenStore] = None,
    ):
        if len(secret_key) < 16:
            logger.warning("secret_key 长度小于16字符，建议使用更长的密钥")
        
        self.secret_key = secret_key
        self.base_url = base_url.rstrip('/')
        self.token_store = token_store or MemoryTokenStore()
    
    def generate(
        self,
        file_path: str,
        expires_in: int = 3600,
        user_id: Optional[int] = None,
        download: bool = False,
        filename: Optional[str] = None,
        max_downloads: Optional[int] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SecureURL:
        """生成Token访问URL
        
        Args:
            file_path: 文件路径
            expires_in: 过期时间（秒），默认1小时
            user_id: 限制访问的用户ID（仅该用户可访问）
            download: 是否强制下载
            filename: 下载时的文件名
            max_downloads: 最大下载次数
            metadata: 附加元数据
            
        Returns:
            SecureURL: 安全URL对象
            
        Example:
            url = generator.generate(
                "private/report.pdf",
                expires_in=3600,
                user_id=123,
                download=True,
                filename="Q1报告.pdf",
                max_downloads=3,
            )
        """
        # 生成随机Token
        token = secrets.token_urlsafe(32)
        expires_at = datetime.now() + timedelta(seconds=expires_in)
        
        # 创建Token信息
        info = TokenInfo(
            file_path=file_path,
            expires_at=expires_at,
            user_id=user_id,
            download=download,
            filename=filename,
            max_downloads=max_downloads,
            download_count=0,
            metadata=metadata or {},
        )
        
        # 存储Token
        self.token_store.set(token, info, expires_in)
        
        # 构建URL
        url = f"{self.base_url}/t/{token}"
        
        return SecureURL(
            url=url,
            token=token,
            expires_at=expires_at,
            file_path=file_path,
        )
    
    def generate_signed(
        self,
        file_path: str,
        expires_in: int = 3600,
    ) -> str:
        """生成签名URL
        
        签名URL无需服务端存储，可公开分享。
        
        Args:
            file_path: 文件路径
            expires_in: 过期时间（秒），默认1小时
            
        Returns:
            str: 签名URL
            
        Example:
            url = generator.generate_signed("public/image.jpg", expires_in=86400)
            # -> /api/files/s/cHVibGljL2ltYWdlLmpwZw?e=1234567890&s=abc123def456
        """
        # 计算过期时间戳
        expires = int((datetime.now() + timedelta(seconds=expires_in)).timestamp())
        
        # 生成签名
        sign_str = f"{file_path}:{expires}"
        signature = hmac.new(
            self.secret_key.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()[:24]
        
        # Base64 URL安全编码路径
        encoded_path = base64.urlsafe_b64encode(
            file_path.encode()
        ).decode().rstrip('=')
        
        return f"{self.base_url}/s/{encoded_path}?e={expires}&s={signature}"
    
    def validate_token(
        self,
        token: str,
        user_id: Optional[int] = None,
    ) -> Optional[TokenInfo]:
        """验证Token
        
        Args:
            token: 访问Token
            user_id: 当前用户ID（用于验证用户限制）
            
        Returns:
            TokenInfo: 验证通过返回Token信息，否则返回 None
        """
        # 获取Token信息
        info = self.token_store.get(token)
        if info is None:
            logger.debug(f"Token不存在或已过期: {token[:8]}...")
            return None
        
        # 双重检查过期时间
        if datetime.now() > info.expires_at:
            self.token_store.delete(token)
            return None
        
        # 检查用户限制
        if info.user_id is not None and info.user_id != user_id:
            logger.warning(
                f"用户ID不匹配: expected={info.user_id}, actual={user_id}"
            )
            return None
        
        # 检查下载次数
        if info.max_downloads is not None:
            count = self.token_store.increment_downloads(token)
            if count > info.max_downloads:
                logger.debug(
                    f"超过最大下载次数: {count}/{info.max_downloads}"
                )
                self.token_store.delete(token)
                return None
            info.download_count = count
        
        return info
    
    def validate_signed(
        self,
        encoded_path: str,
        expires: int,
        signature: str,
    ) -> Optional[str]:
        """验证签名URL
        
        Args:
            encoded_path: Base64编码的文件路径
            expires: 过期时间戳
            signature: 签名
            
        Returns:
            str: 验证通过返回文件路径，否则返回 None
        """
        # 检查过期
        if datetime.now().timestamp() > expires:
            return None
        
        # 解码路径（处理缺失的padding）
        padding = 4 - len(encoded_path) % 4
        if padding != 4:
            encoded_path_padded = encoded_path + '=' * padding
        else:
            encoded_path_padded = encoded_path
        
        try:
            file_path = base64.urlsafe_b64decode(encoded_path_padded).decode()
        except Exception:
            logger.warning("Base64解码失败")
            return None
        
        # 验证签名
        sign_str = f"{file_path}:{expires}"
        expected_sig = hmac.new(
            self.secret_key.encode(),
            sign_str.encode(),
            hashlib.sha256
        ).hexdigest()[:24]
        
        if not hmac.compare_digest(signature, expected_sig):
            logger.warning(f"签名验证失败: {file_path}")
            return None
        
        return file_path
    
    def revoke(self, token: str) -> None:
        """撤销Token
        
        Args:
            token: 要撤销的Token
        """
        self.token_store.delete(token)


__all__ = [
    'SecureURL',
    'TokenInfo',
    'TokenStore',
    'MemoryTokenStore',
    'RedisTokenStore',
    'SecureURLGenerator',
]
