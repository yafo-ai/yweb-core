"""
权限模块基础演示

演示：
1. 定义权限模型
2. 创建权限和角色
3. 分配角色和检查权限
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import init_database, get_engine
from yweb.orm.core_model import CoreModel
from yweb.permission.models import (
    AbstractPermission,
    AbstractRole,
    AbstractSubjectRole,
    AbstractRolePermission,
    AbstractSubjectPermission,
)
from yweb.permission.services import PermissionService, RoleService


# ==================== 1. 定义模型 ====================

class Permission(AbstractPermission):
    __tablename__ = "demo_permission"


class Role(AbstractRole):
    __tablename__ = "demo_role"
    __role_tablename__ = "demo_role"


class SubjectRole(AbstractSubjectRole):
    __tablename__ = "demo_subject_role"
    __role_tablename__ = "demo_role"


class RolePermission(AbstractRolePermission):
    __tablename__ = "demo_role_permission"
    __role_tablename__ = "demo_role"
    __permission_tablename__ = "demo_permission"


class SubjectPermission(AbstractSubjectPermission):
    __tablename__ = "demo_subject_permission"
    __permission_tablename__ = "demo_permission"


# ==================== 2. 初始化 ====================

def main():
    print("=" * 60)
    print("权限模块基础演示")
    print("=" * 60)
    
    # 初始化数据库（保存在脚本所在目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_basic.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}")
    
    # 设置 query 属性
    CoreModel.query = session_scope.query_property()
    
    # 创建表（先删后建，确保干净）
    CoreModel.metadata.drop_all(engine)
    CoreModel.metadata.create_all(engine)
    print(f"\n✓ 数据库初始化完成: {db_path}")
    
    # 创建服务
    perm_service = PermissionService(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
        use_cache=False,  # 演示时禁用缓存，方便查看结果
    )
    
    role_service = RoleService(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    )
    
    # ==================== 3. 创建权限 ====================
    print("\n--- 创建权限 ---")
    
    permissions = [
        ("user:read", "查看用户"),
        ("user:write", "编辑用户"),
        ("user:delete", "删除用户"),
        ("order:read", "查看订单"),
        ("order:write", "编辑订单"),
        ("system:config", "系统配置"),
    ]
    
    for code, name in permissions:
        perm = perm_service.create_permission(code=code, name=name)
        print(f"  创建权限: {perm.code} - {perm.name}")
    
    # ==================== 4. 创建角色 ====================
    print("\n--- 创建角色 ---")
    
    admin = role_service.create_role(
        code="admin",
        name="管理员",
        description="系统管理员，拥有所有权限",
        is_system=True,
    )
    print(f"  创建角色: {admin.code} - {admin.name}")
    
    user_role = role_service.create_role(
        code="user",
        name="普通用户",
        description="普通用户，只有查看权限",
    )
    print(f"  创建角色: {user_role.code} - {user_role.name}")
    
    # ==================== 5. 设置角色权限 ====================
    print("\n--- 设置角色权限 ---")
    
    # admin 拥有所有权限
    role_service.set_role_permissions("admin", [
        "user:read", "user:write", "user:delete",
        "order:read", "order:write",
        "system:config",
    ])
    print("  admin 角色权限: user:*, order:*, system:config")
    
    # user 只有查看权限
    role_service.set_role_permissions("user", [
        "user:read",
        "order:read",
    ])
    print("  user 角色权限: user:read, order:read")
    
    # ==================== 6. 分配角色 ====================
    print("\n--- 分配角色 ---")
    
    # 给员工 ID=1 分配 admin 角色
    perm_service.assign_role("employee:1", "admin")
    print("  employee:1 -> admin")
    
    # 给员工 ID=2 分配 user 角色
    perm_service.assign_role("employee:2", "user")
    print("  employee:2 -> user")
    
    # ==================== 7. 检查权限 ====================
    print("\n--- 检查权限 ---")
    
    test_cases = [
        ("employee:1", "user:read"),
        ("employee:1", "user:delete"),
        ("employee:1", "system:config"),
        ("employee:2", "user:read"),
        ("employee:2", "user:delete"),
        ("employee:2", "system:config"),
    ]
    
    for subject_id, permission_code in test_cases:
        has_perm = perm_service.check_permission(subject_id, permission_code)
        status = "✓" if has_perm else "✗"
        print(f"  {subject_id} -> {permission_code}: {status}")
    
    # ==================== 8. 获取用户所有权限 ====================
    print("\n--- 用户权限汇总 ---")
    
    for subject_id in ["employee:1", "employee:2"]:
        roles = perm_service.get_all_roles(subject_id)
        perms = perm_service.get_all_permissions(subject_id)
        print(f"\n  {subject_id}:")
        print(f"    角色: {roles}")
        print(f"    权限: {perms}")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
