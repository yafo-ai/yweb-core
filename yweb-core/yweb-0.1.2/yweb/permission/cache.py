"""
权限模块 - 权限缓存

提供基于内存的权限缓存，支持 TTL 自动过期和主动失效。

使用示例:
    from yweb.permission.cache import permission_cache
    
    # 获取用户权限（缓存优先）
    perms = permission_cache.get_permissions("employee:123")
    if perms is None:
        perms = load_from_db(...)
        permission_cache.set_permissions("employee:123", perms)
    
    # 权限变更时失效缓存
    permission_cache.invalidate_subject("employee:123")
    
    # 查看缓存统计
    info = permission_cache.get_cache_info()
"""

from dataclasses import dataclass, field
from threading import Lock
from typing import Set, Optional, Dict, List
from datetime import datetime

try:
    from cachetools import TTLCache
    CACHETOOLS_AVAILABLE = True
except ImportError:
    CACHETOOLS_AVAILABLE = False
    TTLCache = None

from yweb.log import get_logger

logger = get_logger("yweb.permission.cache")


@dataclass
class CacheStats:
    """缓存统计信息"""
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    
    @property
    def hit_rate(self) -> float:
        """缓存命中率"""
        total = self.hits + self.misses
        return self.hits / total if total > 0 else 0.0
    
    @property
    def total_requests(self) -> int:
        """总请求数"""
        return self.hits + self.misses
    
    def reset(self):
        """重置统计"""
        self.hits = 0
        self.misses = 0
        self.invalidations = 0


class PermissionCache:
    """权限缓存管理器
    
    特点：
    - 基于 cachetools.TTLCache，自动过期
    - 线程安全
    - 支持主动失效
    - 版本号机制支持批量失效
    - 内置统计功能
    
    缓存结构：
    - permission_cache: 用户权限缓存 (subject_id -> Set[permission_code])
    - role_cache: 用户角色缓存 (subject_id -> Set[role_code])
    - role_permission_cache: 角色权限缓存 (role_code -> Set[permission_code])
    
    使用示例:
        cache = PermissionCache(maxsize=10000, ttl=300)
        
        # 获取用户权限
        perms = cache.get_permissions("employee:123")
        if perms is None:
            perms = load_from_db(...)
            cache.set_permissions("employee:123", perms)
        
        # 权限变更时失效
        cache.invalidate_subject("employee:123")
        
        # 查看统计
        info = cache.get_cache_info()
    """
    
    def __init__(
        self,
        maxsize: int = 10000,
        ttl: int = 300,
        enable_stats: bool = True
    ):
        """初始化权限缓存
        
        Args:
            maxsize: 每个缓存的最大条目数
                     - 实际支持的用户数约等于 maxsize
                     - 建议设置为活跃用户数的 1.5 倍
            ttl: 缓存过期时间（秒），默认 300 秒（5 分钟）
            enable_stats: 是否启用统计功能
        """
        if not CACHETOOLS_AVAILABLE:
            raise ImportError(
                "cachetools 未安装。请运行: pip install cachetools"
            )
        
        self._maxsize = maxsize
        self._ttl = ttl
        self._enable_stats = enable_stats
        
        # 用户权限缓存: subject_id -> Set[permission_code]
        self._permission_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 用户角色缓存: subject_id -> Set[role_code]
        self._role_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 角色权限缓存: role_code -> Set[permission_code]
        self._role_permission_cache: TTLCache = TTLCache(maxsize=maxsize, ttl=ttl)
        
        # 线程锁
        self._lock = Lock()
        
        # 版本号（用于批量失效）
        self._version: int = 0
        
        # 统计
        self._stats = CacheStats() if enable_stats else None
        
        logger.debug(f"PermissionCache initialized: maxsize={maxsize}, ttl={ttl}")
    
    def _make_key(self, subject_id: str, prefix: str = "perm") -> str:
        """生成缓存 key
        
        格式: {prefix}:{subject_id}:v{version}
        """
        return f"{prefix}:{subject_id}:v{self._version}"
    
    # ==================== 权限缓存 ====================
    
    def get_permissions(self, subject_id: str) -> Optional[Set[str]]:
        """获取用户权限
        
        Args:
            subject_id: 主体标识，如 "employee:123"
            
        Returns:
            权限编码集合，缓存未命中返回 None
        """
        key = self._make_key(subject_id, "perm")
        result = self._permission_cache.get(key)
        
        if self._stats:
            if result is not None:
                self._stats.hits += 1
            else:
                self._stats.misses += 1
        
        return result
    
    def set_permissions(self, subject_id: str, permissions: Set[str]):
        """设置用户权限
        
        Args:
            subject_id: 主体标识
            permissions: 权限编码集合
        """
        key = self._make_key(subject_id, "perm")
        with self._lock:
            self._permission_cache[key] = permissions
    
    def has_permission(self, subject_id: str, permission_code: str) -> Optional[bool]:
        """检查用户是否有某个权限（从缓存）
        
        Args:
            subject_id: 主体标识
            permission_code: 权限编码
            
        Returns:
            True/False 或 None（缓存未命中）
        """
        perms = self.get_permissions(subject_id)
        if perms is None:
            return None
        return permission_code in perms
    
    # ==================== 角色缓存 ====================
    
    def get_roles(self, subject_id: str) -> Optional[Set[str]]:
        """获取用户角色
        
        Args:
            subject_id: 主体标识
            
        Returns:
            角色编码集合，缓存未命中返回 None
        """
        key = self._make_key(subject_id, "role")
        return self._role_cache.get(key)
    
    def set_roles(self, subject_id: str, roles: Set[str]):
        """设置用户角色
        
        Args:
            subject_id: 主体标识
            roles: 角色编码集合
        """
        key = self._make_key(subject_id, "role")
        with self._lock:
            self._role_cache[key] = roles
    
    def has_role(self, subject_id: str, role_code: str) -> Optional[bool]:
        """检查用户是否有某个角色（从缓存）
        
        Args:
            subject_id: 主体标识
            role_code: 角色编码
            
        Returns:
            True/False 或 None（缓存未命中）
        """
        roles = self.get_roles(subject_id)
        if roles is None:
            return None
        return role_code in roles
    
    # ==================== 角色权限缓存 ====================
    
    def get_role_permissions(self, role_code: str) -> Optional[Set[str]]:
        """获取角色权限
        
        Args:
            role_code: 角色编码
            
        Returns:
            权限编码集合，缓存未命中返回 None
        """
        key = f"role_perm:{role_code}:v{self._version}"
        return self._role_permission_cache.get(key)
    
    def set_role_permissions(self, role_code: str, permissions: Set[str]):
        """设置角色权限
        
        Args:
            role_code: 角色编码
            permissions: 权限编码集合
        """
        key = f"role_perm:{role_code}:v{self._version}"
        with self._lock:
            self._role_permission_cache[key] = permissions
    
    # ==================== 失效策略 ====================
    
    def invalidate_subject(self, subject_id: str):
        """使单个主体的缓存失效
        
        当用户的角色或权限发生变更时调用。
        
        Args:
            subject_id: 主体标识
        """
        with self._lock:
            perm_key = self._make_key(subject_id, "perm")
            role_key = self._make_key(subject_id, "role")
            self._permission_cache.pop(perm_key, None)
            self._role_cache.pop(role_key, None)
            
            if self._stats:
                self._stats.invalidations += 1
        
        logger.debug(f"Cache invalidated for subject: {subject_id}")
    
    def invalidate_role(self, role_code: str):
        """使角色权限缓存失效
        
        当角色的权限发生变更时调用。
        注意：这不会自动失效拥有该角色的用户缓存，
        需要配合 invalidate_subjects_batch 使用。
        
        Args:
            role_code: 角色编码
        """
        key = f"role_perm:{role_code}:v{self._version}"
        with self._lock:
            self._role_permission_cache.pop(key, None)
        
        logger.debug(f"Cache invalidated for role: {role_code}")
    
    def invalidate_subjects_batch(self, subject_ids: List[str]):
        """批量失效多个主体的缓存
        
        Args:
            subject_ids: 主体标识列表
        """
        with self._lock:
            for subject_id in subject_ids:
                perm_key = self._make_key(subject_id, "perm")
                role_key = self._make_key(subject_id, "role")
                self._permission_cache.pop(perm_key, None)
                self._role_cache.pop(role_key, None)
            
            if self._stats:
                self._stats.invalidations += len(subject_ids)
        
        logger.debug(f"Cache invalidated for {len(subject_ids)} subjects")
    
    def invalidate_all(self):
        """使所有缓存失效（通过版本号递增）
        
        适用于：
        - 权限模型发生重大变更
        - 紧急清除所有缓存
        
        注意：旧版本的缓存不会立即删除，而是等待 TTL 过期
        """
        with self._lock:
            self._version += 1
            
            if self._stats:
                self._stats.invalidations += 1
        
        logger.info(f"All cache invalidated, new version: {self._version}")
    
    def clear(self):
        """清空所有缓存
        
        立即清除所有缓存数据。
        """
        with self._lock:
            self._permission_cache.clear()
            self._role_cache.clear()
            self._role_permission_cache.clear()
        
        logger.info("All cache cleared")
    
    # ==================== 统计与监控 ====================
    
    @property
    def stats(self) -> Optional[CacheStats]:
        """获取缓存统计"""
        return self._stats
    
    def get_cache_info(self) -> Dict:
        """获取缓存详细信息
        
        Returns:
            包含缓存大小、配置、统计等信息的字典
        """
        return {
            "permission_cache_size": len(self._permission_cache),
            "role_cache_size": len(self._role_cache),
            "role_permission_cache_size": len(self._role_permission_cache),
            "maxsize": self._maxsize,
            "ttl": self._ttl,
            "version": self._version,
            "stats": {
                "hits": self._stats.hits if self._stats else 0,
                "misses": self._stats.misses if self._stats else 0,
                "total_requests": self._stats.total_requests if self._stats else 0,
                "hit_rate": f"{self._stats.hit_rate:.2%}" if self._stats else "N/A",
                "invalidations": self._stats.invalidations if self._stats else 0,
            } if self._stats else None
        }
    
    def reset_stats(self):
        """重置统计数据"""
        if self._stats:
            self._stats.reset()


# 全局单例
permission_cache = PermissionCache()


def get_permission_cache() -> PermissionCache:
    """获取全局权限缓存实例
    
    Returns:
        全局 PermissionCache 实例
    """
    return permission_cache


def configure_cache(
    maxsize: int = None,
    ttl: int = None,
    enable_stats: bool = None
):
    """配置全局权限缓存
    
    注意：这会创建一个新的缓存实例，旧缓存数据会丢失。
    
    Args:
        maxsize: 最大缓存条目数
        ttl: 过期时间（秒）
        enable_stats: 是否启用统计
    """
    global permission_cache
    
    current_maxsize = maxsize if maxsize is not None else permission_cache._maxsize
    current_ttl = ttl if ttl is not None else permission_cache._ttl
    current_stats = enable_stats if enable_stats is not None else permission_cache._enable_stats
    
    permission_cache = PermissionCache(
        maxsize=current_maxsize,
        ttl=current_ttl,
        enable_stats=current_stats
    )
    
    logger.info(f"Permission cache reconfigured: maxsize={current_maxsize}, ttl={current_ttl}")


__all__ = [
    "PermissionCache",
    "CacheStats",
    "permission_cache",
    "get_permission_cache",
    "configure_cache",
]
