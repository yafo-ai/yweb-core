"""缓存后端模块

提供不同的缓存存储后端实现。
"""

from abc import ABC, abstractmethod
from typing import Any, Optional, Dict
from dataclasses import dataclass, field
from datetime import datetime
import threading
import time
import json
import pickle

from yweb.log import get_logger

logger = get_logger("yweb.cache")


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    
    @property
    def hit_rate(self) -> float:
        """命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    def record_hit(self):
        self.hits += 1
    
    def record_miss(self):
        self.misses += 1
    
    def record_invalidation(self):
        self.invalidations += 1
    
    def reset(self):
        self.hits = 0
        self.misses = 0
        self.invalidations = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "hits": self.hits,
            "misses": self.misses,
            "invalidations": self.invalidations,
            "hit_rate": f"{self.hit_rate:.2%}",
        }


class CacheBackend(ABC):
    """缓存后端抽象基类"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[Any]:
        """获取缓存值"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        """设置缓存值"""
        pass
    
    @abstractmethod
    def delete(self, key: str) -> bool:
        """删除缓存"""
        pass
    
    @abstractmethod
    def clear(self) -> None:
        """清空所有缓存"""
        pass
    
    @abstractmethod
    def get_stats(self) -> Dict[str, Any]:
        """获取统计信息"""
        pass


class _ExpiringValue:
    """值包装器，支持独立于 TTLCache 的自定义过期时间
    
    当 per-key TTL 与 MemoryBackend 的默认 TTL 不同时使用此包装器。
    TTLCache 的全局 TTL 作为最大上限，此包装器提供更短的自定义过期。
    """
    __slots__ = ("value", "expires_at")
    
    def __init__(self, value: Any, expires_at: float):
        self.value = value
        self.expires_at = expires_at


class MemoryBackend(CacheBackend):
    """内存缓存后端
    
    基于 cachetools.TTLCache 实现，支持自动过期。
    支持 per-key TTL：自定义 TTL 小于默认值时精确控制过期，
    大于默认值时以默认值为上限（TTLCache 会先行淘汰）。
    
    使用示例:
        backend = MemoryBackend(maxsize=1000, ttl=60)
        backend.set("key", "value")
        backend.set("key2", "value2", ttl=10)  # 10 秒后过期
        value = backend.get("key")
    """
    
    def __init__(
        self,
        maxsize: int = 1000,
        ttl: int = 300,
        enable_stats: bool = True
    ):
        """
        Args:
            maxsize: 最大缓存条目数
            ttl: 默认过期时间（秒）
            enable_stats: 是否启用统计
        """
        try:
            from cachetools import TTLCache
        except ImportError:
            raise ImportError(
                "cachetools 未安装。请运行: pip install cachetools"
            )
        
        self._cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        self._default_ttl = ttl
        self._maxsize = maxsize
        self._lock = threading.RLock()
        self._stats = CacheStats() if enable_stats else None
        
        logger.debug(f"MemoryBackend initialized: maxsize={maxsize}, ttl={ttl}")
    
    def get(self, key: str) -> Optional[Any]:
        with self._lock:
            raw = self._cache.get(key)
            if raw is None:
                if self._stats:
                    self._stats.record_miss()
                return None
            
            # 检查自定义过期时间
            if isinstance(raw, _ExpiringValue):
                if time.monotonic() >= raw.expires_at:
                    # 自定义 TTL 已过期，移除并返回 miss
                    del self._cache[key]
                    if self._stats:
                        self._stats.record_miss()
                    return None
                value = raw.value
            else:
                value = raw
            
            if self._stats:
                self._stats.record_hit()
            return value
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        with self._lock:
            effective_ttl = ttl if ttl is not None else self._default_ttl
            if effective_ttl != self._default_ttl:
                # Per-key TTL: 用 _ExpiringValue 包装，get() 时检查过期
                self._cache[key] = _ExpiringValue(
                    value, time.monotonic() + effective_ttl
                )
            else:
                # 默认 TTL: 直接存储，由 TTLCache 统一管理过期
                self._cache[key] = value
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                if self._stats:
                    self._stats.record_invalidation()
                return True
            return False
    
    def clear(self) -> None:
        with self._lock:
            self._cache.clear()
            if self._stats:
                self._stats.record_invalidation()
            logger.info("MemoryBackend cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            stats = {
                "backend": "memory",
                "size": len(self._cache),
                "maxsize": self._maxsize,
                "ttl": self._default_ttl,
            }
            if self._stats:
                stats.update(self._stats.to_dict())
            return stats


class PickleSerializer:
    """pickle 序列化器（RedisBackend 默认）
    
    使用 Python 标准 pickle 模块，支持任意 Python 对象的序列化，
    包括 SQLAlchemy ORM 模型实例。
    
    注意：反序列化后的 ORM 实例处于 detached 状态（不绑定 Session），
    适用于只读缓存场景（如用户认证）。
    """
    
    def dumps(self, value: Any) -> bytes:
        return pickle.dumps(value, protocol=pickle.HIGHEST_PROTOCOL)
    
    def loads(self, data: bytes) -> Any:
        return pickle.loads(data)


class JsonSerializer:
    """JSON 序列化器
    
    仅支持 JSON 可序列化的类型（dict, list, str, int, float, bool, None）。
    不支持 ORM 模型等复杂 Python 对象。
    适用于缓存简单数据且需要 Redis 中数据可读的场景。
    """
    
    def dumps(self, value: Any) -> str:
        return json.dumps(value, default=str)
    
    def loads(self, data: str) -> Any:
        return json.loads(data)


# 默认序列化器实例（全局复用，无状态）
_default_pickle_serializer = PickleSerializer()


class RedisBackend(CacheBackend):
    """Redis 缓存后端
    
    支持分布式缓存，多实例共享。
    默认使用 pickle 序列化，支持任意 Python 对象（包括 ORM 模型）。
    
    使用示例:
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0)
        backend = RedisBackend(redis_client, prefix="myapp:", ttl=300)
        
        # 使用 JSON 序列化（仅支持简单类型）
        backend = RedisBackend(redis_client, serializer=JsonSerializer())
    """
    
    def __init__(
        self,
        redis_client,
        prefix: str = "cache:",
        ttl: int = 300,
        enable_stats: bool = True,
        serializer: Optional[Any] = None
    ):
        """
        Args:
            redis_client: Redis 客户端实例
            prefix: 缓存键前缀
            ttl: 默认过期时间（秒）
            enable_stats: 是否启用统计（本地统计，非分布式）
            serializer: 序列化器，默认使用 PickleSerializer
        """
        self._redis = redis_client
        self._prefix = prefix
        self._default_ttl = ttl
        self._stats = CacheStats() if enable_stats else None
        self._serializer = serializer or _default_pickle_serializer
        
        logger.debug(f"RedisBackend initialized: prefix={prefix}, ttl={ttl}")
    
    def _make_key(self, key: str) -> str:
        """生成完整的 Redis 键"""
        return f"{self._prefix}{key}"
    
    def _serialize(self, value: Any) -> bytes:
        """序列化值"""
        return self._serializer.dumps(value)
    
    def _deserialize(self, data: bytes) -> Any:
        """反序列化值"""
        return self._serializer.loads(data)
    
    def get(self, key: str) -> Optional[Any]:
        try:
            data = self._redis.get(self._make_key(key))
            if data is not None:
                if self._stats:
                    self._stats.record_hit()
                return self._deserialize(data)
            else:
                if self._stats:
                    self._stats.record_miss()
                return None
        except Exception as e:
            logger.warning(f"Redis get error: {e}")
            if self._stats:
                self._stats.record_miss()
            return None
    
    def set(self, key: str, value: Any, ttl: Optional[int] = None) -> None:
        try:
            ttl = ttl or self._default_ttl
            data = self._serialize(value)
            self._redis.setex(self._make_key(key), ttl, data)
        except Exception as e:
            logger.warning(f"Redis set error: {e}")
    
    def delete(self, key: str) -> bool:
        try:
            result = self._redis.delete(self._make_key(key))
            if result and self._stats:
                self._stats.record_invalidation()
            return bool(result)
        except Exception as e:
            logger.warning(f"Redis delete error: {e}")
            return False
    
    def clear(self) -> None:
        """清空所有带前缀的缓存键"""
        try:
            pattern = f"{self._prefix}*"
            cursor = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                if keys:
                    self._redis.delete(*keys)
                if cursor == 0:
                    break
            if self._stats:
                self._stats.record_invalidation()
            logger.info(f"RedisBackend cleared: prefix={self._prefix}")
        except Exception as e:
            logger.warning(f"Redis clear error: {e}")
    
    def get_stats(self) -> Dict[str, Any]:
        stats = {
            "backend": "redis",
            "prefix": self._prefix,
            "ttl": self._default_ttl,
        }
        if self._stats:
            stats.update(self._stats.to_dict())
        return stats


__all__ = [
    "CacheStats",
    "CacheBackend",
    "MemoryBackend",
    "RedisBackend",
    "PickleSerializer",
    "JsonSerializer",
]
