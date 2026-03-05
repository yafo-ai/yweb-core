"""
权限模块 - API 路由

提供权限管理的 API 路由。使用动词风格，只使用 GET 和 POST 请求。

使用示例:
=========

方式1：一次性挂载全部路由
------------------------
    from yweb.permission.api import create_permission_router
    
    router = create_permission_router(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
        api_resource_model=APIResource,  # 可选
        prefix="/api/permission",
        dependencies=[Depends(require_role("admin"))],
    )
    app.include_router(router)

方式2：按需挂载独立路由
----------------------
    from yweb.permission.api import (
        create_permission_crud_router,
        create_role_crud_router,
        create_subject_router,
    )
    
    # 只挂载需要的部分
    app.include_router(
        create_permission_crud_router(permission_model=Permission),
        prefix="/api/admin/permissions"
    )
    app.include_router(
        create_role_crud_router(role_model=Role, ...),
        prefix="/api/admin/roles"
    )

方式3：完全自定义
----------------
    # 只使用 Service 类，自己写 API
    from yweb.permission import PermissionService, RoleService
    
    perm_service = PermissionService(...)
    
    @app.post("/my-api/grant")
    async def my_api():
        perm_service.grant_subject_permission(...)
"""

from typing import Type, List, Optional, TYPE_CHECKING
from fastapi import APIRouter, Depends

if TYPE_CHECKING:
    from ..models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
        AbstractAPIResource,
    )

from .permission_api import create_permission_crud_router
from .role_api import create_role_crud_router
from .subject_api import create_subject_router
from .api_resource_api import create_api_resource_router
from .cache_api import create_cache_router


def create_permission_router(
    permission_model: Type["AbstractPermission"],
    role_model: Type["AbstractRole"],
    subject_role_model: Type["AbstractSubjectRole"],
    role_permission_model: Type["AbstractRolePermission"],
    subject_permission_model: Type["AbstractSubjectPermission"],
    api_resource_model: Optional[Type["AbstractAPIResource"]] = None,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[List] = None,
) -> APIRouter:
    """创建完整的权限管理路由
    
    一次性创建所有权限管理相关的 API 路由。
    使用动词风格，只使用 GET 和 POST 请求。
    
    Args:
        permission_model: 权限模型类
        role_model: 角色模型类
        subject_role_model: 主体-角色关联模型类
        role_permission_model: 角色-权限关联模型类
        subject_permission_model: 主体-权限关联模型类
        api_resource_model: API资源模型类（可选）
        prefix: 路由前缀
        tags: OpenAPI 标签
        dependencies: 路由依赖（如权限检查）
        
    Returns:
        配置好的 APIRouter
    
    使用示例:
        router = create_permission_router(
            permission_model=Permission,
            role_model=Role,
            subject_role_model=SubjectRole,
            role_permission_model=RolePermission,
            subject_permission_model=SubjectPermission,
            prefix="/api/permission",
            dependencies=[Depends(require_role("admin"))],
        )
        app.include_router(router)
    
    生成的路由:
    
        权限管理 {prefix}/permissions:
        - GET  /list           获取权限列表
        - GET  /get            获取权限详情
        - POST /create         创建权限
        - POST /update         更新权限
        - POST /delete         删除权限
        - GET  /modules/list   获取模块列表
        - GET  /resources/list 获取资源列表
        
        角色管理 {prefix}/roles:
        - GET  /list              获取角色列表
        - GET  /tree              获取角色树
        - GET  /get               获取角色详情
        - POST /create            创建角色
        - POST /update            更新角色
        - POST /delete            删除角色
        - GET  /permissions       获取角色权限
        - POST /set-permissions   设置角色权限（全量）
        - POST /add-permission    添加角色权限
        - POST /remove-permission 移除角色权限
        - GET  /subjects          获取角色用户
        
        用户授权 {prefix}/subjects:
        - POST /assign-role        分配角色
        - POST /unassign-role      撤销角色
        - POST /assign-role-batch  批量分配角色
        - POST /grant-permission   授予权限
        - POST /revoke-permission  撤销权限
        - GET  /get                获取用户权限
        - GET  /roles              获取用户角色
        - POST /check              检查权限
        - POST /check-batch        批量检查权限
        - POST /invalidate-cache   失效用户缓存
        
        API 资源管理 {prefix}/api-resources（如果提供 api_resource_model）:
        - GET  /list                 获取 API 资源列表
        - GET  /get                  获取 API 资源详情
        - POST /create               创建 API 资源
        - POST /update               更新 API 资源
        - POST /delete               删除 API 资源
        - POST /scan                 扫描路由
        - GET  /modules/list         获取模块列表
        - POST /batch-set-permission 批量设置权限
        
        缓存管理 {prefix}/cache:
        - GET  /stats           获取缓存统计
        - POST /invalidate      失效缓存
        - POST /invalidate-batch 批量失效缓存
        - POST /clear           清空缓存
        - POST /reset-stats     重置统计
        - POST /configure       配置缓存
    """
    router = APIRouter(
        prefix=prefix,
        tags=tags or ["权限管理"],
        dependencies=dependencies or [],
    )
    
    # 权限 CRUD
    router.include_router(
        create_permission_crud_router(permission_model=permission_model),
        prefix="/permissions",
        tags=["权限管理 - 权限"],
    )
    
    # 角色 CRUD
    router.include_router(
        create_role_crud_router(
            role_model=role_model,
            permission_model=permission_model,
            role_permission_model=role_permission_model,
            subject_role_model=subject_role_model,
        ),
        prefix="/roles",
        tags=["权限管理 - 角色"],
    )
    
    # 用户授权
    router.include_router(
        create_subject_router(
            permission_model=permission_model,
            role_model=role_model,
            subject_role_model=subject_role_model,
            role_permission_model=role_permission_model,
            subject_permission_model=subject_permission_model,
        ),
        prefix="/subjects",
        tags=["权限管理 - 用户授权"],
    )
    
    # API 资源管理（可选）
    if api_resource_model:
        router.include_router(
            create_api_resource_router(
                api_resource_model=api_resource_model,
                permission_model=permission_model,
            ),
            prefix="/api-resources",
            tags=["权限管理 - API资源"],
        )
    
    # 缓存管理
    router.include_router(
        create_cache_router(),
        prefix="/cache",
        tags=["权限管理 - 缓存"],
    )
    
    return router


__all__ = [
    # 完整路由
    "create_permission_router",
    
    # 独立路由
    "create_permission_crud_router",
    "create_role_crud_router",
    "create_subject_router",
    "create_api_resource_router",
    "create_cache_router",
]
