"""
权限模块 - 工厂函数

提供动态模型创建、一站式设置等功能，与 auth/organization/scheduler 模块风格一致。

使用示例:
=========

方式1：一站式设置（推荐）
------------------------
    from yweb.permission import setup_permission
    
    perm = setup_permission(
        app=app,
        api_prefix="/api/v1",
        table_prefix="sys_",
        dependencies=[Depends(require_role("admin"))],
    )
    
    # 访问模型
    Permission = perm.Permission
    Role = perm.Role

方式2：分步设置
--------------
    from yweb.permission import create_permission_models
    
    perm = create_permission_models(table_prefix="sys_")
    
    # 中间可插入自定义逻辑...
    
    # 挂载路由
    perm.mount_routes(app, prefix="/api/v1/permission")

方式3：传统方式（手动继承抽象类）
------------------------------
    from yweb.permission.models import AbstractPermission, AbstractRole, ...
    
    class Permission(AbstractPermission):
        __tablename__ = "sys_permission"
    # ... 手动定义所有模型
"""

from dataclasses import dataclass, field
from typing import Type, Any, Optional, List, Callable


# ============================================================================
# 动态模型创建辅助函数
# ============================================================================

def _create_dynamic_model(
    base_class: Type,
    tablename: str,
    unique_name: str,
    extra_attrs: dict = None,
) -> Type:
    """动态创建模型类
    
    Args:
        base_class: 抽象基类
        tablename: 表名
        unique_name: 类名（需唯一避免 registry 冲突）
        extra_attrs: 额外属性
        
    Returns:
        动态创建的模型类
    """
    attrs = {
        "__tablename__": tablename,
        "__module__": "yweb.permission.factory",
    }
    
    if extra_attrs:
        attrs.update(extra_attrs)
    
    # 动态创建类
    return type(unique_name, (base_class,), attrs)


# ============================================================================
# PermissionModels 容器类
# ============================================================================

@dataclass
class PermissionModels:
    """权限模型容器
    
    包含所有权限相关的模型类，支持点号访问。
    
    属性:
        Permission: 权限模型
        Role: 角色模型
        SubjectRole: 主体-角色关联模型
        RolePermission: 角色-权限关联模型
        SubjectPermission: 主体-权限关联模型
        APIResource: API 资源模型（可选）
    
    使用示例:
        perm = create_permission_models(table_prefix="sys_")
        
        # 访问模型
        permission = perm.Permission(code="user:read", name="查看用户", ...)
        
        # 获取服务
        perm_service = perm.get_permission_service()
        role_service = perm.get_role_service()
    """
    # 核心模型
    Permission: Type
    Role: Type
    SubjectRole: Type
    RolePermission: Type
    SubjectPermission: Type
    
    # 可选模型
    APIResource: Optional[Type] = None
    
    # 私有：单例服务实例
    _permission_service: Any = field(default=None, repr=False)
    _role_service: Any = field(default=None, repr=False)
    
    def as_dict(self) -> dict:
        """返回模型字典，方便传递给 create_permission_router"""
        result = {
            "permission_model": self.Permission,
            "role_model": self.Role,
            "subject_role_model": self.SubjectRole,
            "role_permission_model": self.RolePermission,
            "subject_permission_model": self.SubjectPermission,
        }
        if self.APIResource:
            result["api_resource_model"] = self.APIResource
        return result
    
    def get_permission_service(self):
        """获取权限服务单例
        
        Returns:
            PermissionService 实例（单例模式）
        
        使用示例:
            perm = create_permission_models(table_prefix="sys_")
            service = perm.get_permission_service()
            
            # 检查权限
            has_perm = service.check_permission("employee:123", "user:read")
        """
        if self._permission_service is None:
            from .services import PermissionService
            
            service = PermissionService(
                permission_model=self.Permission,
                role_model=self.Role,
                subject_role_model=self.SubjectRole,
                role_permission_model=self.RolePermission,
                subject_permission_model=self.SubjectPermission,
            )
            object.__setattr__(self, '_permission_service', service)
        
        return self._permission_service
    
    def get_role_service(self):
        """获取角色服务单例
        
        Returns:
            RoleService 实例（单例模式）
        
        使用示例:
            perm = create_permission_models(table_prefix="sys_")
            service = perm.get_role_service()
            
            # 创建角色
            role = service.create_role(code="admin", name="管理员")
        """
        if self._role_service is None:
            from .services import RoleService
            
            service = RoleService(
                role_model=self.Role,
                permission_model=self.Permission,
                role_permission_model=self.RolePermission,
                subject_role_model=self.SubjectRole,
            )
            object.__setattr__(self, '_role_service', service)
        
        return self._role_service
    
    def mount_routes(
        self,
        app,
        prefix: str = "/api/permission",
        tags: list = None,
        dependencies: list = None,
    ):
        """挂载权限管理路由到 FastAPI 应用
        
        与 auth.mount_routes() / org.mount_routes() 风格一致的路由挂载方法。
        
        Args:
            app: FastAPI 应用实例
            prefix: API 路由前缀（默认 "/api/permission"）
            tags: OpenAPI 标签
            dependencies: 路由依赖（如权限检查）
        
        使用示例:
            perm = create_permission_models(table_prefix="sys_")
            perm.mount_routes(
                app,
                prefix="/api/v1/permission",
                dependencies=[Depends(require_role("admin"))],
            )
        """
        from .api import create_permission_router
        
        router = create_permission_router(
            permission_model=self.Permission,
            role_model=self.Role,
            subject_role_model=self.SubjectRole,
            role_permission_model=self.RolePermission,
            subject_permission_model=self.SubjectPermission,
            api_resource_model=self.APIResource,
            prefix="",
            tags=tags or ["权限管理"],
            dependencies=dependencies,
        )
        app.include_router(router, prefix=prefix)
    
    def init_dependency(self):
        """初始化权限依赖注入
        
        调用 init_permission_dependency，使 require_permission / require_role 等依赖可用。
        
        使用示例:
            perm = create_permission_models(table_prefix="sys_")
            perm.init_dependency()
            
            # 现在可以使用 require_permission / require_role
            @app.get("/users")
            async def list_users(user = Depends(require_permission("user:list"))):
                ...
        """
        from .dependencies import init_permission_dependency
        
        init_permission_dependency(
            permission_model=self.Permission,
            role_model=self.Role,
            subject_role_model=self.SubjectRole,
            role_permission_model=self.RolePermission,
            subject_permission_model=self.SubjectPermission,
        )


# ============================================================================
# create_permission_models - 动态模型工厂
# ============================================================================

def create_permission_models(
    table_prefix: str = "",
    # 自定义表名（可选）
    permission_tablename: str = None,
    role_tablename: str = None,
    subject_role_tablename: str = None,
    role_permission_tablename: str = None,
    subject_permission_tablename: str = None,
    api_resource_tablename: str = None,
    # 是否创建 APIResource 模型
    include_api_resource: bool = False,
    # Mixin 扩展（可选）
    permission_mixin: Type = None,
    role_mixin: Type = None,
    subject_role_mixin: Type = None,
    role_permission_mixin: Type = None,
    subject_permission_mixin: Type = None,
    api_resource_mixin: Type = None,
) -> PermissionModels:
    """创建权限模型集合
    
    动态创建所有权限相关的模型类，返回 PermissionModels 容器。
    
    Args:
        table_prefix: 表名前缀（如 "sys_"）
        permission_tablename: 自定义权限表名（覆盖 table_prefix）
        role_tablename: 自定义角色表名
        subject_role_tablename: 自定义主体角色关联表名
        role_permission_tablename: 自定义角色权限关联表名
        subject_permission_tablename: 自定义主体权限关联表名
        api_resource_tablename: 自定义 API 资源表名
        include_api_resource: 是否创建 APIResource 模型
        permission_mixin: 权限模型的 Mixin
        role_mixin: 角色模型的 Mixin
        subject_role_mixin: 主体角色关联模型的 Mixin
        role_permission_mixin: 角色权限关联模型的 Mixin
        subject_permission_mixin: 主体权限关联模型的 Mixin
        api_resource_mixin: API 资源模型的 Mixin
        
    Returns:
        PermissionModels 容器
    
    使用示例:
        # 基础用法
        perm = create_permission_models(table_prefix="sys_")
        
        # 自定义表名
        perm = create_permission_models(
            permission_tablename="my_permission",
            role_tablename="my_role",
        )
        
        # 使用 Mixin 扩展
        class PermissionMixin:
            extra_field: Mapped[str] = mapped_column(String(100), nullable=True)
        
        perm = create_permission_models(
            table_prefix="sys_",
            permission_mixin=PermissionMixin,
        )
    """
    from .models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
        AbstractAPIResource,
    )
    
    # 生成唯一后缀避免 registry 冲突
    import uuid
    suffix = uuid.uuid4().hex[:8]
    
    # 计算表名
    perm_table = permission_tablename or f"{table_prefix}permission"
    role_table = role_tablename or f"{table_prefix}role"
    sr_table = subject_role_tablename or f"{table_prefix}subject_role"
    rp_table = role_permission_tablename or f"{table_prefix}role_permission"
    sp_table = subject_permission_tablename or f"{table_prefix}subject_permission"
    api_table = api_resource_tablename or f"{table_prefix}api_resource"
    
    # 创建 Permission 模型
    perm_bases = (permission_mixin, AbstractPermission) if permission_mixin else (AbstractPermission,)
    Permission = type(
        f"Permission_{suffix}",
        perm_bases,
        {
            "__tablename__": perm_table,
            "__module__": "yweb.permission.factory",
        }
    )
    
    # 创建 Role 模型
    role_bases = (role_mixin, AbstractRole) if role_mixin else (AbstractRole,)
    Role = type(
        f"Role_{suffix}",
        role_bases,
        {
            "__tablename__": role_table,
            "__role_tablename__": role_table,
            "__module__": "yweb.permission.factory",
        }
    )
    
    # 创建 SubjectRole 模型
    sr_bases = (subject_role_mixin, AbstractSubjectRole) if subject_role_mixin else (AbstractSubjectRole,)
    SubjectRole = type(
        f"SubjectRole_{suffix}",
        sr_bases,
        {
            "__tablename__": sr_table,
            "__role_tablename__": role_table,
            "__module__": "yweb.permission.factory",
        }
    )
    
    # 创建 RolePermission 模型
    rp_bases = (role_permission_mixin, AbstractRolePermission) if role_permission_mixin else (AbstractRolePermission,)
    RolePermission = type(
        f"RolePermission_{suffix}",
        rp_bases,
        {
            "__tablename__": rp_table,
            "__role_tablename__": role_table,
            "__permission_tablename__": perm_table,
            "__module__": "yweb.permission.factory",
        }
    )
    
    # 创建 SubjectPermission 模型
    sp_bases = (subject_permission_mixin, AbstractSubjectPermission) if subject_permission_mixin else (AbstractSubjectPermission,)
    SubjectPermission = type(
        f"SubjectPermission_{suffix}",
        sp_bases,
        {
            "__tablename__": sp_table,
            "__permission_tablename__": perm_table,
            "__module__": "yweb.permission.factory",
        }
    )
    
    # 创建 APIResource 模型（可选）
    APIResource = None
    if include_api_resource:
        api_bases = (api_resource_mixin, AbstractAPIResource) if api_resource_mixin else (AbstractAPIResource,)
        APIResource = type(
            f"APIResource_{suffix}",
            api_bases,
            {
                "__tablename__": api_table,
                "__permission_tablename__": perm_table,
                "__module__": "yweb.permission.factory",
            }
        )
    
    return PermissionModels(
        Permission=Permission,
        Role=Role,
        SubjectRole=SubjectRole,
        RolePermission=RolePermission,
        SubjectPermission=SubjectPermission,
        APIResource=APIResource,
    )


# ============================================================================
# setup_permission - 一站式设置函数
# ============================================================================

def setup_permission(
    app=None,
    api_prefix: str = "/api/permission",
    table_prefix: str = "",
    tags: list = None,
    dependencies: list = None,
    # 自定义表名
    permission_tablename: str = None,
    role_tablename: str = None,
    subject_role_tablename: str = None,
    role_permission_tablename: str = None,
    subject_permission_tablename: str = None,
    api_resource_tablename: str = None,
    # 是否创建 APIResource 模型
    include_api_resource: bool = False,
    # Mixin 扩展
    permission_mixin: Type = None,
    role_mixin: Type = None,
    subject_role_mixin: Type = None,
    role_permission_mixin: Type = None,
    subject_permission_mixin: Type = None,
    api_resource_mixin: Type = None,
    # 是否初始化依赖
    init_dependency: bool = True,
) -> PermissionModels:
    """一站式设置权限模块
    
    创建所有模型、初始化依赖、挂载路由，一行代码完成全部配置。
    
    Args:
        app: FastAPI 应用实例（可选，传入时自动挂载路由）
        api_prefix: API 路由前缀（默认 "/api/permission"）
        table_prefix: 表名前缀（如 "sys_"）
        tags: OpenAPI 标签
        dependencies: 路由依赖（如权限检查）
        permission_tablename: 自定义权限表名
        role_tablename: 自定义角色表名
        subject_role_tablename: 自定义主体角色关联表名
        role_permission_tablename: 自定义角色权限关联表名
        subject_permission_tablename: 自定义主体权限关联表名
        api_resource_tablename: 自定义 API 资源表名
        include_api_resource: 是否创建 APIResource 模型
        permission_mixin: 权限模型的 Mixin
        role_mixin: 角色模型的 Mixin
        subject_role_mixin: 主体角色关联模型的 Mixin
        role_permission_mixin: 角色权限关联模型的 Mixin
        subject_permission_mixin: 主体权限关联模型的 Mixin
        api_resource_mixin: API 资源模型的 Mixin
        init_dependency: 是否初始化权限依赖（默认 True）
        
    Returns:
        PermissionModels 容器
    
    使用示例:
        # 最简用法
        perm = setup_permission(app=app)
        
        # 完整配置
        perm = setup_permission(
            app=app,
            api_prefix="/api/v1/permission",
            table_prefix="sys_",
            dependencies=[Depends(require_role("admin"))],
            include_api_resource=True,
        )
        
        # 不挂载路由（仅创建模型和初始化依赖）
        perm = setup_permission(app=None)
        # 稍后手动挂载
        perm.mount_routes(app, prefix="/api/v1/permission")
    """
    # 创建模型
    perm = create_permission_models(
        table_prefix=table_prefix,
        permission_tablename=permission_tablename,
        role_tablename=role_tablename,
        subject_role_tablename=subject_role_tablename,
        role_permission_tablename=role_permission_tablename,
        subject_permission_tablename=subject_permission_tablename,
        api_resource_tablename=api_resource_tablename,
        include_api_resource=include_api_resource,
        permission_mixin=permission_mixin,
        role_mixin=role_mixin,
        subject_role_mixin=subject_role_mixin,
        role_permission_mixin=role_permission_mixin,
        subject_permission_mixin=subject_permission_mixin,
        api_resource_mixin=api_resource_mixin,
    )
    
    # 初始化依赖
    if init_dependency:
        perm.init_dependency()
    
    # 挂载路由
    if app is not None:
        perm.mount_routes(
            app,
            prefix=api_prefix,
            tags=tags,
            dependencies=dependencies,
        )
    
    return perm


__all__ = [
    "PermissionModels",
    "create_permission_models",
    "setup_permission",
]
