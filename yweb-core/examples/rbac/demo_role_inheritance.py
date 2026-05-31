"""
角色继承演示

演示：
1. 创建树形角色结构
2. 子角色继承父角色权限
3. 权限检查包含继承的权限
"""

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


# ==================== 定义模型 ====================

class Permission(AbstractPermission):
    __tablename__ = "demo2_permission"


class Role(AbstractRole):
    __tablename__ = "demo2_role"
    __role_tablename__ = "demo2_role"


class SubjectRole(AbstractSubjectRole):
    __tablename__ = "demo2_subject_role"
    __role_tablename__ = "demo2_role"


class RolePermission(AbstractRolePermission):
    __tablename__ = "demo2_role_permission"
    __role_tablename__ = "demo2_role"
    __permission_tablename__ = "demo2_permission"


class SubjectPermission(AbstractSubjectPermission):
    __tablename__ = "demo2_subject_permission"
    __permission_tablename__ = "demo2_permission"


def main():
    print("=" * 60)
    print("角色继承演示")
    print("=" * 60)
    
    # 初始化数据库（保存在脚本所在目录）
    import os
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, "demo_role_inheritance.db")
    engine, session_scope = init_database(f"sqlite:///{db_path}")
    
    # 设置 query 属性
    CoreModel.query = session_scope.query_property()
    
    # 创建表
    CoreModel.metadata.drop_all(engine)
    CoreModel.metadata.create_all(engine)
    print(f"✓ 数据库: {db_path}")
    
    perm_service = PermissionService(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
        use_cache=False,
    )
    
    role_service = RoleService(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    )
    
    # ==================== 创建权限 ====================
    print("\n--- 创建权限 ---")
    
    permissions = [
        # 基础权限
        ("basic:read", "基础查看"),
        # 管理权限
        ("manage:user", "管理用户"),
        ("manage:order", "管理订单"),
        ("manage:report", "管理报表"),
        # 高级权限
        ("admin:config", "系统配置"),
        ("admin:audit", "审计日志"),
        # 超级权限
        ("super:all", "超级权限"),
    ]
    
    for code, name in permissions:
        perm_service.create_permission(code=code, name=name)
        print(f"  {code}")
    
    # ==================== 创建角色层级 ====================
    print("\n--- 创建角色层级 ---")
    print("""
    super_admin (超级管理员)
    └── admin (管理员)
        ├── manager (经理)
        │   └── staff (员工)
        └── auditor (审计员)
    """)
    
    # 超级管理员 - 顶级角色
    super_admin = role_service.create_role(
        code="super_admin",
        name="超级管理员",
        is_system=True,
    )
    
    # 管理员 - 继承超级管理员
    admin = role_service.create_role(
        code="admin",
        name="管理员",
        parent_code="super_admin",
    )
    
    # 经理 - 继承管理员
    manager = role_service.create_role(
        code="manager",
        name="经理",
        parent_code="admin",
    )
    
    # 员工 - 继承经理
    staff = role_service.create_role(
        code="staff",
        name="员工",
        parent_code="manager",
    )
    
    # 审计员 - 继承管理员
    auditor = role_service.create_role(
        code="auditor",
        name="审计员",
        parent_code="admin",
    )
    
    # ==================== 设置角色权限 ====================
    print("--- 设置角色权限 ---")
    
    # 每个角色只设置自己独有的权限，子角色会自动继承
    role_service.set_role_permissions("super_admin", ["super:all"])
    print("  super_admin: super:all")
    
    role_service.set_role_permissions("admin", ["admin:config", "admin:audit"])
    print("  admin: admin:config, admin:audit")
    
    role_service.set_role_permissions("manager", ["manage:user", "manage:order", "manage:report"])
    print("  manager: manage:user, manage:order, manage:report")
    
    role_service.set_role_permissions("staff", ["basic:read"])
    print("  staff: basic:read")
    
    role_service.set_role_permissions("auditor", ["admin:audit"])
    print("  auditor: admin:audit")
    
    # ==================== 分配角色 ====================
    print("\n--- 分配角色 ---")
    
    users = [
        ("employee:1", "staff", "张三"),
        ("employee:2", "manager", "李四"),
        ("employee:3", "admin", "王五"),
        ("employee:4", "super_admin", "超管"),
        ("employee:5", "auditor", "审计"),
    ]
    
    for subject_id, role_code, name in users:
        perm_service.assign_role(subject_id, role_code)
        print(f"  {name}({subject_id}) -> {role_code}")
    
    # ==================== 验证继承 ====================
    print("\n--- 验证权限继承 ---")
    
    for subject_id, role_code, name in users:
        roles = perm_service.get_all_roles(subject_id)
        perms = perm_service.get_all_permissions(subject_id)
        
        print(f"\n  {name} ({role_code}):")
        print(f"    继承的角色: {sorted(roles)}")
        print(f"    拥有的权限: {sorted(perms)}")
    
    # ==================== 权限检查示例 ====================
    print("\n--- 权限检查示例 ---")
    
    # 张三(staff) 检查各种权限
    print("\n  张三(staff) 权限检查:")
    for perm in ["basic:read", "manage:user", "admin:config", "super:all"]:
        has = perm_service.check_permission("employee:1", perm)
        print(f"    {perm}: {'✓' if has else '✗'}")
    
    # 李四(manager) 检查各种权限
    print("\n  李四(manager) 权限检查:")
    for perm in ["basic:read", "manage:user", "admin:config", "super:all"]:
        has = perm_service.check_permission("employee:2", perm)
        print(f"    {perm}: {'✓' if has else '✗'}")
    
    # 超管检查所有权限
    print("\n  超管(super_admin) 权限检查:")
    for perm in ["basic:read", "manage:user", "admin:config", "super:all"]:
        has = perm_service.check_permission("employee:4", perm)
        print(f"    {perm}: {'✓' if has else '✗'}")
    
    print("\n" + "=" * 60)
    print("演示完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
