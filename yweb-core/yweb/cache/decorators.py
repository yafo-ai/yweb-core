"""缓存装饰器模块

提供通用的函数缓存装饰器。

使用示例:
    from yweb.cache import cached
    
    # 基本用法（内存缓存）
    @cached(ttl=60)
    def get_user(user_id: int):
        return User.get_by_id(user_id)
    
    # 使用 Redis 缓存
    @cached(ttl=60, backend="redis", redis=redis_client)
    def get_user(user_id: int):
        return User.get_by_id(user_id)
    
    # 自动失效（ORM 变更时自动清除缓存）
    @cached(ttl=60, invalidate_on=User)
    def get_user(user_id: int):
        return User.get_by_id(user_id)
    
    # 多模型自动失效
    @cached(ttl=60, invalidate_on=[User, Department])
    def get_user_with_dept(user_id: int):
        ...
    
    # 自定义 key 提取器
    @cached(ttl=60, invalidate_on={
        User: lambda user: user.id,
        Department: lambda dept: [e.user_id for e in dept.employees]
    })
    def get_user_with_dept(user_id: int):
        ...
    
    # 手动失效
    get_user.invalidate(user_id=123)
    
    # 批量失效
    get_user.invalidate_many([123, 456, 789])
    
    # 清空所有缓存
    get_user.clear()
    
    # 获取统计
    stats = get_user.stats()
"""

from functools import wraps
from typing import (
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Type,
    TypeVar,
    Union,
    Hashable,
)
import hashlib
import json
import time

from yweb.log import get_logger
from .backends import MemoryBackend, RedisBackend, CacheBackend

logger = get_logger("yweb.cache")

_SENSITIVE_KEYWORDS = (
    "password",
    "secret",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "apikey",
    "api_key",
)


def _is_sensitive_field(field_name: str) -> bool:
    name = str(field_name).lower()
    return any(keyword in name for keyword in _SENSITIVE_KEYWORDS)


def _build_value_preview(value: Any, depth: int = 0) -> Any:
    """构建缓存值预览，自动脱敏并限制体积。"""
    if depth > 2:
        return "<max_depth_reached>"
    
    if value is None or isinstance(value, (bool, int, float)):
        return value
    
    if isinstance(value, str):
        if len(value) <= 120:
            return value
        return f"{value[:117]}..."
    
    if isinstance(value, dict):
        preview = {}
        for index, (k, v) in enumerate(value.items()):
            if index >= 20:
                preview["..."] = "<truncated>"
                break
            if _is_sensitive_field(k):
                preview[k] = "***"
            else:
                preview[k] = _build_value_preview(v, depth + 1)
        return preview
    
    if isinstance(value, (list, tuple, set)):
        seq = list(value)
        result = [_build_value_preview(item, depth + 1) for item in seq[:20]]
        if len(seq) > 20:
            result.append("<truncated>")
        return result
    
    if hasattr(value, "__dict__"):
        data = {}
        for index, (k, v) in enumerate(vars(value).items()):
            if k.startswith("_"):
                continue
            if index >= 20:
                data["..."] = "<truncated>"
                break
            if _is_sensitive_field(k):
                data[k] = "***"
            else:
                data[k] = _build_value_preview(v, depth + 1)
        return {
            "__type__": type(value).__name__,
            "fields": data,
        }
    
    return f"<{type(value).__name__}>"


# ==================== 全局缓存注册表 ====================

class CacheRegistry:
    """全局缓存函数注册表
    
    自动跟踪所有通过 @cached 装饰的函数，提供统一的查询和管理入口。
    
    使用示例:
        from yweb.cache import cache_registry
        
        # 查看所有已注册的缓存函数
        cache_registry.list_functions()
        
        # 获取汇总统计
        cache_registry.get_all_stats()
        
        # 清空指定函数的缓存
        cache_registry.clear_function("get_user")
        
        # 清空所有缓存
        cache_registry.clear_all()
    """
    
    def __init__(self):
        self._functions: Dict[str, "CachedFunction"] = {}
    
    def register(self, func: "CachedFunction") -> None:
        """注册缓存函数"""
        name = func.__name__
        self._functions[name] = func
        logger.debug(f"Cache function registered: {name}")
    
    def unregister(self, name: str) -> bool:
        """取消注册"""
        if name in self._functions:
            del self._functions[name]
            return True
        return False
    
    def get(self, name: str) -> Optional["CachedFunction"]:
        """获取指定的缓存函数"""
        return self._functions.get(name)
    
    def list_functions(self) -> List[Dict[str, Any]]:
        """列出所有已注册的缓存函数信息
        
        Returns:
            缓存函数摘要列表
        """
        result = []
        for name, func in self._functions.items():
            result.append({
                "name": name,
                "module": func.__module__,
                "ttl": func._ttl,
                "backend": func._backend_type,
                "key_prefix": func._key_prefix or name,
            })
        return result
    
    def get_all_stats(self) -> Dict[str, Any]:
        """获取所有缓存函数的汇总统计
        
        Returns:
            包含各函数统计和汇总的字典
        """
        functions_stats = {}
        total_hits = 0
        total_misses = 0
        
        for name, func in self._functions.items():
            stats = func.stats()
            functions_stats[name] = stats
            total_hits += stats.get("hits", 0)
            total_misses += stats.get("misses", 0)
        
        total = total_hits + total_misses
        return {
            "total_functions": len(self._functions),
            "total_hits": total_hits,
            "total_misses": total_misses,
            "total_hit_rate": round(total_hits / total * 100, 2) if total > 0 else 0,
            "functions": functions_stats,
        }
    
    def clear_function(self, name: str) -> bool:
        """清空指定函数的缓存
        
        Args:
            name: 函数名
            
        Returns:
            是否成功
        """
        func = self._functions.get(name)
        if func is None:
            return False
        func.clear()
        return True
    
    def clear_all(self) -> int:
        """清空所有缓存
        
        Returns:
            清空的函数数量
        """
        count = 0
        for func in self._functions.values():
            func.clear()
            count += 1
        return count
    
    def list_entries(self, name: str, limit: int = 50) -> Optional[Dict[str, Any]]:
        """查看指定函数的缓存条目列表（预览）。"""
        func = self._functions.get(name)
        if func is None:
            return None
        entries = func.inspect_entries(limit=limit)
        return {
            "function": name,
            "total": len(entries),
            "entries": entries,
        }
    
    def get_entry(self, name: str, key: str) -> Optional[Dict[str, Any]]:
        """查看指定函数的单个缓存条目（预览）。"""
        func = self._functions.get(name)
        if func is None:
            return None
        return func.inspect_entry(key)
    
    @property
    def size(self) -> int:
        """已注册的缓存函数数量"""
        return len(self._functions)


# 全局实例
cache_registry = CacheRegistry()


# 类型定义
InvalidateOnType = Union[
    Type,                                    # 单个模型
    List[Type],                              # 多个模型（默认 key_extractor）
    Dict[Type, Callable[[Any], Any]],        # 模型 -> key_extractor 映射
]

F = TypeVar("F", bound=Callable[..., Any])


def _make_cache_key(func_name: str, args: tuple, kwargs: dict) -> str:
    """生成缓存键
    
    将函数名和参数组合成唯一的缓存键。
    func_name 为空时只用参数生成键（Redis 后端场景，前缀由后端处理）。
    """
    key_parts = []
    if func_name:
        key_parts.append(func_name)
    
    for arg in args:
        if isinstance(arg, Hashable):
            key_parts.append(str(arg))
        else:
            # 对于不可哈希的参数，使用 JSON 序列化后的哈希
            key_parts.append(hashlib.md5(
                json.dumps(arg, default=str, sort_keys=True).encode()
            ).hexdigest()[:8])
    
    for k, v in sorted(kwargs.items()):
        if isinstance(v, Hashable):
            key_parts.append(f"{k}={v}")
        else:
            key_parts.append(f"{k}={hashlib.md5(json.dumps(v, default=str, sort_keys=True).encode()).hexdigest()[:8]}")
    
    return ":".join(key_parts)


class CachedFunction:
    """带缓存的函数包装器
    
    包装原函数，添加缓存功能和管理方法。
    """
    
    def __init__(
        self,
        func: Callable,
        backend: CacheBackend,
        ttl: int,
        key_prefix: Optional[str] = None,
        key_builder: Optional[Callable] = None,
        backend_type: str = "memory",
        invalidate_on: Optional[InvalidateOnType] = None,
    ):
        self._func = func
        self._backend = backend
        self._ttl = ttl
        self._key_prefix = key_prefix if key_prefix is not None else func.__name__
        self._key_builder = key_builder
        self._backend_type = backend_type
        self._invalidate_on = invalidate_on
        
        # 保留原函数的元信息
        self.__name__ = func.__name__
        self.__doc__ = func.__doc__
        self.__module__ = func.__module__
        self.__wrapped__ = func
        
        # 自动注册到全局注册表
        cache_registry.register(self)
        
        # 自动注册缓存失效
        if invalidate_on is not None:
            self._register_invalidation(invalidate_on)
    
    def _register_invalidation(self, invalidate_on: InvalidateOnType) -> None:
        """注册模型变更时的缓存自动失效
        
        Args:
            invalidate_on: 模型或模型列表或模型->key_extractor 字典
        """
        from .invalidation import cache_invalidator
        
        # 统一转换为 {model: key_extractor} 格式
        model_extractors: Dict[Type, Optional[Callable]] = {}
        
        if isinstance(invalidate_on, dict):
            # 字典形式：{User: lambda u: u.id, Department: lambda d: ...}
            model_extractors = invalidate_on
        elif isinstance(invalidate_on, (list, tuple)):
            # 列表形式：[User, Department] -> 都用默认 key_extractor
            for model in invalidate_on:
                model_extractors[model] = None
        else:
            # 单个模型
            model_extractors[invalidate_on] = None
        
        # 注册每个模型
        for model, key_extractor in model_extractors.items():
            try:
                cache_invalidator.register(
                    model=model,
                    cached_func=self,
                    key_extractor=key_extractor,
                )
                logger.debug(
                    f"Auto-registered invalidation: {model.__name__} -> {self.__name__}"
                )
            except Exception as e:
                logger.warning(
                    f"Failed to register invalidation for {model.__name__}: {e}"
                )
    
    def __call__(self, *args, **kwargs) -> Any:
        """调用函数，优先返回缓存"""
        cache_key = self._build_key(args, kwargs)
        
        # 尝试从缓存获取
        cached_value = self._backend.get(cache_key)
        if cached_value is not None:
            logger.debug(
                f"Cache hit: {cache_key} | "
                f"func={self.__name__}, backend={self._backend_type}, ttl={self._ttl}s"
            )
            return cached_value
        
        # 缓存未命中，调用原函数
        logger.debug(
            f"Cache miss: {cache_key} | "
            f"func={self.__name__}, backend={self._backend_type}, ttl={self._ttl}s"
        )
        result = self._func(*args, **kwargs)
        
        # 只缓存非 None 结果
        if result is not None:
            self._backend.set(cache_key, result, self._ttl)
        
        return result
    
    def _build_key(self, args: tuple, kwargs: dict) -> str:
        """构建缓存键"""
        if self._key_builder:
            return self._key_builder(self._key_prefix, args, kwargs)
        return _make_cache_key(self._key_prefix, args, kwargs)
    
    def invalidate(self, *args, **kwargs) -> bool:
        """使特定参数的缓存失效
        
        使用示例:
            get_user.invalidate(123)           # 位置参数
            get_user.invalidate(user_id=123)   # 关键字参数
        """
        cache_key = self._build_key(args, kwargs)
        result = self._backend.delete(cache_key)
        if result:
            logger.debug(f"Cache invalidated: {cache_key}")
        return result
    
    def invalidate_many(self, keys: List[Any]) -> int:
        """批量失效缓存
        
        使用示例:
            get_user.invalidate_many([123, 456, 789])
        """
        count = 0
        for key in keys:
            if isinstance(key, (list, tuple)):
                # 支持 [(arg1, arg2), (arg3, arg4)] 格式
                if self.invalidate(*key):
                    count += 1
            else:
                # 支持 [id1, id2, id3] 格式
                if self.invalidate(key):
                    count += 1
        logger.debug(f"Cache invalidated: {count}/{len(keys)} keys")
        return count
    
    def clear(self) -> None:
        """清空此函数的所有缓存"""
        self._backend.clear()
        logger.info(f"Cache cleared for: {self._key_prefix or self.__name__}")
    
    def stats(self) -> Dict[str, Any]:
        """获取缓存统计信息"""
        stats = self._backend.get_stats()
        stats["function"] = self._key_prefix or self.__name__
        stats["ttl"] = self._ttl
        return stats
    
    def refresh(self, *args, **kwargs) -> Any:
        """强制刷新缓存
        
        先失效旧缓存，再调用函数获取新值。
        """
        self.invalidate(*args, **kwargs)
        return self(*args, **kwargs)
    
    def inspect_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        """查看缓存条目列表（脱敏预览）。"""
        if isinstance(self._backend, MemoryBackend):
            return self._inspect_memory_entries(limit=limit)
        if isinstance(self._backend, RedisBackend):
            return self._inspect_redis_entries(limit=limit)
        return []
    
    def inspect_entry(self, key: str) -> Optional[Dict[str, Any]]:
        """查看单个缓存条目（脱敏预览）。"""
        if isinstance(self._backend, MemoryBackend):
            value = self._backend.get(key)
            if value is None:
                return None
            return {
                "key": key,
                "ttl_remaining": None,
                "value_type": type(value).__name__,
                "value_size": len(repr(value)),
                "value_preview": _build_value_preview(value),
            }
        
        if isinstance(self._backend, RedisBackend):
            try:
                full_key = self._backend._make_key(key)
                raw = self._backend._redis.get(full_key)
                if raw is None:
                    return None
                value = self._backend._deserialize(raw)
                ttl = self._backend._redis.ttl(full_key)
                return {
                    "key": key,
                    "ttl_remaining": ttl if ttl and ttl > 0 else None,
                    "value_type": type(value).__name__,
                    "value_size": len(raw),
                    "value_preview": _build_value_preview(value),
                }
            except Exception as e:
                logger.warning(f"inspect redis cache entry failed: {e}")
        return None
    
    def _inspect_memory_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        try:
            cache_items = list(self._backend._cache.items())
            for index, (key, raw_value) in enumerate(cache_items):
                if index >= limit:
                    break
                
                ttl_remaining = None
                value = raw_value
                if hasattr(raw_value, "value") and hasattr(raw_value, "expires_at"):
                    value = raw_value.value
                    ttl_remaining = max(int(raw_value.expires_at - time.monotonic()), 0)
                
                entries.append({
                    "key": key,
                    "ttl_remaining": ttl_remaining,
                    "value_type": type(value).__name__,
                    "value_size": len(repr(value)),
                    "value_preview": _build_value_preview(value),
                })
        except Exception as e:
            logger.warning(f"inspect memory cache entries failed: {e}")
        return entries
    
    def _inspect_redis_entries(self, limit: int = 50) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        try:
            cursor = 0
            pattern = f"{self._backend._prefix}*"
            while True:
                cursor, keys = self._backend._redis.scan(cursor, match=pattern, count=100)
                for full_key in keys:
                    if len(entries) >= limit:
                        return entries
                    key_text = full_key.decode() if isinstance(full_key, bytes) else str(full_key)
                    plain_key = key_text[len(self._backend._prefix):]
                    raw_value = self._backend._redis.get(full_key)
                    if raw_value is None:
                        continue
                    value = self._backend._deserialize(raw_value)
                    ttl = self._backend._redis.ttl(full_key)
                    entries.append({
                        "key": plain_key,
                        "ttl_remaining": ttl if ttl and ttl > 0 else None,
                        "value_type": type(value).__name__,
                        "value_size": len(raw_value) if isinstance(raw_value, (bytes, bytearray)) else len(str(raw_value)),
                        "value_preview": _build_value_preview(value),
                    })
                if cursor == 0:
                    break
        except Exception as e:
            logger.warning(f"inspect redis cache entries failed: {e}")
        return entries
    
    @property
    def backend(self) -> CacheBackend:
        """获取缓存后端"""
        return self._backend


def cached(
    ttl: int = 300,
    maxsize: int = 1000,
    backend: str = "memory",
    redis: Any = None,
    key_prefix: Optional[str] = None,
    key_builder: Optional[Callable] = None,
    enable_stats: bool = True,
    invalidate_on: Optional[InvalidateOnType] = None,
) -> Callable[[F], CachedFunction]:
    """通用缓存装饰器
    
    Args:
        ttl: 缓存过期时间（秒），默认 300 秒
        maxsize: 最大缓存条目数（仅内存后端有效），默认 1000
        backend: 缓存后端类型，"memory" 或 "redis"
        redis: Redis 客户端实例（当 backend="redis" 时必须提供）
        key_prefix: 缓存键前缀，默认使用函数名
        key_builder: 自定义缓存键生成函数
        enable_stats: 是否启用统计，默认 True
        invalidate_on: 自动失效配置，支持以下形式：
            - 单个模型: invalidate_on=User
            - 多个模型: invalidate_on=[User, Department]
            - 自定义 key 提取: invalidate_on={User: lambda u: u.id}
    
    Returns:
        装饰后的函数，带有缓存管理方法
    
    使用示例:
        # 基本用法
        @cached(ttl=60)
        def get_user(user_id: int):
            return User.get_by_id(user_id)
        
        # 自动失效（推荐）—— User 变更时自动清除缓存
        @cached(ttl=60, invalidate_on=User)
        def get_user(user_id: int):
            return User.get_by_id(user_id)
        
        # 多模型自动失效
        @cached(ttl=60, invalidate_on=[User, Department])
        def get_user_with_dept(user_id: int):
            ...
        
        # 自定义 key 提取器（从关联模型提取）
        @cached(ttl=60, invalidate_on={
            User: lambda user: user.id,
            Department: lambda dept: [e.user_id for e in dept.employees]
        })
        def get_user_with_dept(user_id: int):
            ...
        
        # Redis 缓存
        @cached(ttl=300, backend="redis", redis=redis_client)
        def get_config(key: str):
            return Config.get_by_key(key)
        
        # 自定义键前缀
        @cached(ttl=60, key_prefix="user:auth")
        def get_user(user_id: int):
            return User.get_by_id(user_id)
        
        # 失效缓存
        get_user.invalidate(123)
        
        # 批量失效
        get_user.invalidate_many([1, 2, 3])
        
        # 强制刷新
        user = get_user.refresh(123)
        
        # 获取统计
        print(get_user.stats())
    """
    def decorator(func: F) -> CachedFunction:
        # 创建缓存后端
        if backend == "redis":
            if redis is None:
                raise ValueError(
                    "使用 Redis 后端时必须提供 redis 参数"
                )
            # Redis 后端通过 prefix 管理键命名空间（用于 clear() 扫描）
            redis_prefix = f"{key_prefix or func.__name__}:"
            cache_backend = RedisBackend(
                redis_client=redis,
                prefix=redis_prefix,
                ttl=ttl,
                enable_stats=enable_stats,
            )
            # Redis: 后端已有前缀，CachedFunction 不再重复添加
            effective_key_prefix = ""
        else:
            cache_backend = MemoryBackend(
                maxsize=maxsize,
                ttl=ttl,
                enable_stats=enable_stats,
            )
            # Memory: 后端无前缀，由 CachedFunction 添加
            effective_key_prefix = key_prefix
        
        return CachedFunction(
            func=func,
            backend=cache_backend,
            ttl=ttl,
            key_prefix=effective_key_prefix,
            key_builder=key_builder,
            backend_type=backend,
            invalidate_on=invalidate_on,
        )
    
    return decorator


def memory_cache(
    ttl: int = 300,
    maxsize: int = 1000,
    key_prefix: Optional[str] = None,
    enable_stats: bool = True,
) -> Callable[[F], CachedFunction]:
    """内存缓存装饰器（简写）
    
    等价于 @cached(backend="memory", ...)
    """
    return cached(
        ttl=ttl,
        maxsize=maxsize,
        backend="memory",
        key_prefix=key_prefix,
        enable_stats=enable_stats,
    )


def redis_cache(
    redis: Any,
    ttl: int = 300,
    key_prefix: Optional[str] = None,
    enable_stats: bool = True,
) -> Callable[[F], CachedFunction]:
    """Redis 缓存装饰器（简写）
    
    等价于 @cached(backend="redis", ...)
    
    Args:
        redis: Redis 客户端实例（必须）
        ttl: 缓存过期时间（秒）
        key_prefix: 缓存键前缀
        enable_stats: 是否启用统计
    """
    return cached(
        ttl=ttl,
        backend="redis",
        redis=redis,
        key_prefix=key_prefix,
        enable_stats=enable_stats,
    )


__all__ = [
    "cached",
    "memory_cache",
    "redis_cache",
    "CachedFunction",
    "CacheRegistry",
    "cache_registry",
]
