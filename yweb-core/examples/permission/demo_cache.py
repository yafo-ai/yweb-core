"""
缓存机制演示

演示：
1. 缓存配置
2. 缓存命中和未命中
3. 缓存失效策略
4. 缓存统计
"""

from yweb.permission.cache import PermissionCache, configure_cache, permission_cache


def main():
    print("=" * 60)
    print("权限缓存机制演示")
    print("=" * 60)
    
    # ==================== 1. 创建缓存实例 ====================
    print("\n--- 1. 创建缓存实例 ---")
    
    cache = PermissionCache(
        maxsize=1000,      # 最大缓存条目数
        ttl=60,            # 过期时间（秒）
        enable_stats=True,  # 启用统计
    )
    print(f"  maxsize: {cache._maxsize}")
    print(f"  ttl: {cache._ttl} 秒")
    
    # ==================== 2. 缓存用户权限 ====================
    print("\n--- 2. 缓存用户权限 ---")
    
    # 模拟从数据库加载的权限
    user1_perms = {"user:read", "user:write", "order:read"}
    user2_perms = {"user:read"}
    
    # 设置缓存
    cache.set_permissions("employee:1", user1_perms)
    cache.set_permissions("employee:2", user2_perms)
    print("  已缓存 employee:1 和 employee:2 的权限")
    
    # ==================== 3. 缓存命中测试 ====================
    print("\n--- 3. 缓存命中测试 ---")
    
    # 缓存命中
    result = cache.get_permissions("employee:1")
    print(f"  employee:1 (命中): {result}")
    
    # 缓存未命中
    result = cache.get_permissions("employee:999")
    print(f"  employee:999 (未命中): {result}")
    
    # 权限检查
    has_perm = cache.has_permission("employee:1", "user:read")
    print(f"  employee:1 有 user:read: {has_perm}")
    
    has_perm = cache.has_permission("employee:1", "admin:config")
    print(f"  employee:1 有 admin:config: {has_perm}")
    
    # ==================== 4. 缓存角色 ====================
    print("\n--- 4. 缓存角色 ---")
    
    cache.set_roles("employee:1", {"admin", "manager"})
    cache.set_roles("employee:2", {"user"})
    
    roles = cache.get_roles("employee:1")
    print(f"  employee:1 的角色: {roles}")
    
    has_role = cache.has_role("employee:1", "admin")
    print(f"  employee:1 有 admin 角色: {has_role}")
    
    # ==================== 5. 缓存失效 ====================
    print("\n--- 5. 缓存失效 ---")
    
    # 失效单个用户
    print("\n  失效 employee:1 的缓存...")
    cache.invalidate_subject("employee:1")
    
    result = cache.get_permissions("employee:1")
    print(f"  employee:1 权限 (已失效): {result}")
    
    result = cache.get_permissions("employee:2")
    print(f"  employee:2 权限 (未失效): {result}")
    
    # 重新设置
    cache.set_permissions("employee:1", user1_perms)
    cache.set_permissions("employee:3", {"order:read"})
    
    # 批量失效
    print("\n  批量失效 employee:1, employee:2...")
    cache.invalidate_subjects_batch(["employee:1", "employee:2"])
    
    print(f"  employee:1: {cache.get_permissions('employee:1')}")
    print(f"  employee:2: {cache.get_permissions('employee:2')}")
    print(f"  employee:3: {cache.get_permissions('employee:3')}")  # 未失效
    
    # ==================== 6. 版本号失效 ====================
    print("\n--- 6. 版本号失效（全部失效）---")
    
    # 重新设置一些缓存
    cache.set_permissions("employee:1", user1_perms)
    cache.set_permissions("employee:2", user2_perms)
    print(f"  当前版本: {cache._version}")
    
    # 全部失效（通过版本号递增）
    cache.invalidate_all()
    print(f"  失效后版本: {cache._version}")
    
    # 旧缓存无法命中
    print(f"  employee:1: {cache.get_permissions('employee:1')}")
    print(f"  employee:2: {cache.get_permissions('employee:2')}")
    
    # ==================== 7. 缓存统计 ====================
    print("\n--- 7. 缓存统计 ---")
    
    # 模拟一些操作
    cache.set_permissions("employee:1", user1_perms)
    
    for _ in range(5):
        cache.get_permissions("employee:1")  # 命中
    
    for _ in range(3):
        cache.get_permissions("employee:999")  # 未命中
    
    info = cache.get_cache_info()
    print(f"  缓存大小: {info['permission_cache_size']}")
    print(f"  命中次数: {info['stats']['hits']}")
    print(f"  未命中次数: {info['stats']['misses']}")
    print(f"  命中率: {info['stats']['hit_rate']}")
    print(f"  失效次数: {info['stats']['invalidations']}")
    
    # ==================== 8. 全局缓存配置 ====================
    print("\n--- 8. 全局缓存配置 ---")
    
    print(f"  默认全局缓存配置:")
    global_info = permission_cache.get_cache_info()
    print(f"    maxsize: {global_info['maxsize']}")
    print(f"    ttl: {global_info['ttl']}")
    
    print("\n  重新配置全局缓存...")
    configure_cache(maxsize=5000, ttl=180)
    
    new_info = permission_cache.get_cache_info()
    print(f"    maxsize: {new_info['maxsize']}")
    print(f"    ttl: {new_info['ttl']}")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
