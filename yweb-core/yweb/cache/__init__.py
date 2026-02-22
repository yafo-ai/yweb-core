"""缓存模块

提供通用的函数缓存装饰器，支持内存缓存和 Redis 缓存，以及自动缓存失效。

使用示例:
    from yweb.cache import cached, memory_cache, redis_cache
    
    # 基本用法
    @cached(ttl=60)
    def get_user(user_id: int):
        return User.get_by_id(user_id)
    
    # 自动失效（推荐）—— 在装饰器中声明，ORM 变更时自动清除缓存
    @cached(ttl=60, invalidate_on=User)
    def get_user(user_id: int):
        return User.get_by_id(user_id)
    
    # 多模型自动失效
    @cached(ttl=60, invalidate_on=[User, Department])
    def get_user_with_dept(user_id: int):
        ...
    
    # 自定义 key 提取（关联模型场景）
    @cached(ttl=60, invalidate_on={
        User: lambda user: user.id,
        Department: lambda dept: [e.user_id for e in dept.employees]  # 返回列表，批量失效
    })
    def get_user_with_dept(user_id: int):
        ...
    
    # Redis 缓存
    @cached(ttl=60, backend="redis", redis=redis_client, invalidate_on=User)
    def get_config(key: str):
        return Config.get_by_key(key)
    
    # 缓存管理
    get_user.invalidate(123)              # 失效单个
    get_user.invalidate_many([1, 2, 3])   # 批量失效
    get_user.clear()                      # 清空所有
    get_user.refresh(123)                 # 强制刷新
    stats = get_user.stats()              # 获取统计
"""

from .backends import (
    CacheStats,
    CacheBackend,
    MemoryBackend,
    RedisBackend,
    PickleSerializer,
    JsonSerializer,
)

from .decorators import (
    cached,
    memory_cache,
    redis_cache,
    CachedFunction,
    CacheRegistry,
    cache_registry,
)

from .invalidation import (
    CacheInvalidator,
    cache_invalidator,
    InvalidationContext,
    no_auto_invalidation,
)

from .api import create_cache_router


__all__ = [
    # 装饰器（主要 API）
    "cached",
    "memory_cache",
    "redis_cache",
    
    # 自动失效（推荐）
    "cache_invalidator",
    "no_auto_invalidation",
    
    # 类型
    "CachedFunction",
    "CacheInvalidator",
    "InvalidationContext",
    
    # 后端（高级用法）
    "CacheStats",
    "CacheBackend",
    "MemoryBackend",
    "RedisBackend",
    
    # 序列化器
    "PickleSerializer",
    "JsonSerializer",
    
    # 注册表
    "CacheRegistry",
    "cache_registry",
    
    # API
    "create_cache_router",
]
