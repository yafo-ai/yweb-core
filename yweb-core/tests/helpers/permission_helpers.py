"""权限缓存测试辅助工具

提供测试专用的权限缓存辅助函数
"""

from yweb.permission.cache import PermissionCache


def get_cache_version(cache: PermissionCache) -> int:
    """获取缓存版本号
    
    Args:
        cache: PermissionCache 实例
        
    Returns:
        int: 当前缓存版本号
    """
    return cache._version
