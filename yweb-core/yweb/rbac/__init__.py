"""
yweb 权限模块

提供基于 RBAC 的权限控制框架，支持：
- 角色权限管理（支持树形继承）
- 用户权限检查（支持缓存）
- FastAPI 依赖注入
- 内部员工和外部用户双用户体系

快速开始:
=========

1. 定义模型（继承抽象类）:

    from yweb.permission.models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
    )
    
    class Permission(AbstractPermission):
        __tablename__ = "sys_permission"
        enable_history = True
    
    class Role(AbstractRole):
        __tablename__ = "sys_role"
        __role_tablename__ = "sys_role"
        enable_history = True
    
    class SubjectRole(AbstractSubjectRole):
        __tablename__ = "sys_subject_role"
        __role_tablename__ = "sys_role"
    
    class RolePermission(AbstractRolePermission):
        __tablename__ = "sys_role_permission"
        __role_tablename__ = "sys_role"
        __permission_tablename__ = "sys_permission"
    
    class SubjectPermission(AbstractSubjectPermission):
        __tablename__ = "sys_subject_permission"
        __permission_tablename__ = "sys_permission"

2. 初始化权限服务（FastAPI 启动时）:

    from yweb.permission import init_permission_dependency
    
    @app.on_event("startup")
    async def startup():
        init_permission_dependency(
            permission_model=Permission,
            role_model=Role,
            subject_role_model=SubjectRole,
            role_permission_model=RolePermission,
            subject_permission_model=SubjectPermission,
        )

3. 在路由中使用权限检查:

    from fastapi import Depends
    from yweb.permission import require_permission, require_role
    
    @app.get("/users")
    async def list_users(user = Depends(require_permission("user:list"))):
        ...
    
    @app.delete("/users/{id}")
    async def delete_user(id: int, user = Depends(require_role("admin"))):
        ...

4. 在普通函数中使用装饰器:

    from yweb.permission import permission_required, role_required
    
    @permission_required("user:read")
    def get_user(subject_id: str, user_id: int):
        ...

5. 集成员工系统:

    from yweb.organization import AbstractEmployee
    from yweb.permission.mixins import EmployeeSubjectMixin
    
    class Employee(AbstractEmployee, EmployeeSubjectMixin):
        __tablename__ = "employee"
    
    # Employee 实例自动拥有 subject_id 属性
    emp = Employee.get(123)
    perm_service.check_permission(emp.subject_id, "user:read")
"""

# 版本
__version__ = "0.1.0"

# 枚举
from .enums import (
    UserType,
    PermissionAction,
    DataScopeType,
    GrantType,
)

# 类型
from .types import (
    SubjectId,
    PermissionCode,
    RoleCode,
    SubjectProtocol,
    parse_subject_id,
    make_subject_id,
    make_permission_code,
    parse_permission_code,
)

# 异常
from .exceptions import (
    PermissionException,
    PermissionDeniedException,
    RoleNotFoundException,
    PermissionNotFoundException,
    SubjectNotFoundException,
    DuplicateRoleException,
    DuplicatePermissionException,
    RoleInheritanceCycleException,
    SystemRoleModifyException,
)

# 缓存
from .cache import (
    PermissionCache,
    permission_cache,
    get_permission_cache,
    configure_cache,
)

# 服务
from .services import (
    PermissionService,
    RoleService,
)

# 依赖注入
from .dependencies import (
    init_permission_dependency,
    get_permission_service,
    get_subject_id_from_user,
    PermissionChecker,
    RoleChecker,
    require_permission,
    require_role,
    require_any_permission,
    require_all_roles,
)

# 装饰器
from .decorators import (
    permission_required,
    role_required,
    admin_required,
    super_admin_required,
)

# 辅助函数
from .helpers import setup_permission_relationships

# Mixins
from .mixins import (
    SubjectMixin,
    EmployeeSubjectMixin,
    ExternalUserSubjectMixin,
)

# API 路由
from .api import (
    create_permission_router,
    create_permission_crud_router,
    create_role_crud_router,
    create_subject_router,
    create_api_resource_router,
    create_cache_router,
)

# 工厂函数
from .factory import (
    PermissionModels,
    create_permission_models,
    setup_permission,
)


__all__ = [
    # 版本
    "__version__",
    
    # 枚举
    "UserType",
    "PermissionAction",
    "DataScopeType",
    "GrantType",
    
    # 类型
    "SubjectId",
    "PermissionCode",
    "RoleCode",
    "SubjectProtocol",
    "parse_subject_id",
    "make_subject_id",
    "make_permission_code",
    "parse_permission_code",
    
    # 异常
    "PermissionException",
    "PermissionDeniedException",
    "RoleNotFoundException",
    "PermissionNotFoundException",
    "SubjectNotFoundException",
    "DuplicateRoleException",
    "DuplicatePermissionException",
    "RoleInheritanceCycleException",
    "SystemRoleModifyException",
    
    # 缓存
    "PermissionCache",
    "permission_cache",
    "get_permission_cache",
    "configure_cache",
    
    # 服务
    "PermissionService",
    "RoleService",
    
    # 依赖注入
    "init_permission_dependency",
    "get_permission_service",
    "get_subject_id_from_user",
    "PermissionChecker",
    "RoleChecker",
    "require_permission",
    "require_role",
    "require_any_permission",
    "require_all_roles",
    
    # 装饰器
    "permission_required",
    "role_required",
    "admin_required",
    "super_admin_required",
    
    # 辅助函数
    "setup_permission_relationships",
    
    # Mixins
    "SubjectMixin",
    "EmployeeSubjectMixin",
    "ExternalUserSubjectMixin",
    
    # API 路由
    "create_permission_router",
    "create_permission_crud_router",
    "create_role_crud_router",
    "create_subject_router",
    "create_api_resource_router",
    "create_cache_router",
    
    # 工厂函数
    "PermissionModels",
    "create_permission_models",
    "setup_permission",
]
