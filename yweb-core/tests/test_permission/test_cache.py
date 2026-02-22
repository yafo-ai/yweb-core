"""
权限模块 - 缓存测试
"""

import pytest
from yweb.permission.cache import PermissionCache
from tests.helpers import get_cache_version


class TestPermissionCache:
    """权限缓存测试"""
    
    @pytest.fixture
    def cache(self):
        """创建测试用缓存实例"""
        return PermissionCache(maxsize=100, ttl=60, enable_stats=True)
    
    # ==================== 权限缓存测试 ====================
    
    def test_set_and_get_permissions(self, cache):
        """测试设置和获取用户权限"""
        permissions = {"user:read", "user:write"}
        cache.set_permissions("employee:1", permissions)
        
        result = cache.get_permissions("employee:1")
        assert result == permissions
    
    def test_get_permissions_miss(self, cache):
        """测试缓存未命中"""
        result = cache.get_permissions("employee:999")
        assert result is None
    
    def test_has_permission_hit(self, cache):
        """测试权限检查 - 命中"""
        cache.set_permissions("employee:1", {"user:read", "user:write"})
        
        assert cache.has_permission("employee:1", "user:read") is True
        assert cache.has_permission("employee:1", "user:delete") is False
    
    def test_has_permission_miss(self, cache):
        """测试权限检查 - 缓存未命中"""
        result = cache.has_permission("employee:999", "user:read")
        assert result is None
    
    # ==================== 角色缓存测试 ====================
    
    def test_set_and_get_roles(self, cache):
        """测试设置和获取用户角色"""
        roles = {"admin", "manager"}
        cache.set_roles("employee:1", roles)
        
        result = cache.get_roles("employee:1")
        assert result == roles
    
    def test_has_role(self, cache):
        """测试角色检查"""
        cache.set_roles("employee:1", {"admin", "manager"})
        
        assert cache.has_role("employee:1", "admin") is True
        assert cache.has_role("employee:1", "user") is False
    
    # ==================== 失效测试 ====================
    
    def test_invalidate_subject(self, cache):
        """测试失效单个用户缓存"""
        cache.set_permissions("employee:1", {"user:read"})
        cache.set_roles("employee:1", {"admin"})
        
        cache.invalidate_subject("employee:1")
        
        assert cache.get_permissions("employee:1") is None
        assert cache.get_roles("employee:1") is None
    
    def test_invalidate_role(self, cache):
        """测试失效角色权限缓存"""
        cache.set_role_permissions("admin", {"user:read", "user:write"})
        
        cache.invalidate_role("admin")
        
        assert cache.get_role_permissions("admin") is None
    
    def test_invalidate_subjects_batch(self, cache):
        """测试批量失效用户缓存"""
        cache.set_permissions("employee:1", {"a"})
        cache.set_permissions("employee:2", {"b"})
        cache.set_permissions("employee:3", {"c"})
        
        cache.invalidate_subjects_batch(["employee:1", "employee:2"])
        
        assert cache.get_permissions("employee:1") is None
        assert cache.get_permissions("employee:2") is None
        assert cache.get_permissions("employee:3") == {"c"}  # 未失效
    
    def test_invalidate_all(self, cache):
        """测试失效所有缓存（版本号递增）"""
        cache.set_permissions("employee:1", {"user:read"})
        old_version = get_cache_version(cache)
        
        cache.invalidate_all()
        
        # 版本号递增后，旧的 key 无法命中
        assert get_cache_version(cache) == old_version + 1
        assert cache.get_permissions("employee:1") is None
    
    def test_clear(self, cache):
        """测试清空缓存"""
        cache.set_permissions("employee:1", {"user:read"})
        cache.set_roles("employee:1", {"admin"})
        
        cache.clear()
        
        assert cache.get_permissions("employee:1") is None
        assert cache.get_roles("employee:1") is None
    
    # ==================== 统计测试 ====================
    
    def test_stats_hit_miss(self, cache):
        """测试统计 - 命中和未命中"""
        cache.set_permissions("employee:1", {"user:read"})
        
        # 1 次命中
        cache.get_permissions("employee:1")
        # 2 次未命中
        cache.get_permissions("employee:2")
        cache.get_permissions("employee:3")
        
        assert cache.stats.hits == 1
        assert cache.stats.misses == 2
        assert cache.stats.total_requests == 3
    
    def test_get_cache_info(self, cache):
        """测试获取缓存信息"""
        cache.set_permissions("employee:1", {"user:read"})
        
        info = cache.get_cache_info()
        
        assert info["permission_cache_size"] == 1
        assert info["maxsize"] == 100
        assert info["ttl"] == 60
        assert "stats" in info
