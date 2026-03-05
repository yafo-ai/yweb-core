"""
权限模块 - FastAPI 依赖注入

提供用于 FastAPI 路由的权限检查依赖。

使用示例:
    from fastapi import FastAPI, Depends
    from yweb.permission import require_permission, require_role
    
    app = FastAPI()
    
    # 初始化权限依赖
    from yweb.permission import init_permission_dependency
    init_permission_dependency(
        permission_model=Permission,
        role_model=Role,
        # ...
    )
    
    @app.get("/users")
    async def list_users(
        user: UserIdentity = Depends(require_permission("user:list"))
    ):
        return {"users": [...]}
    
    @app.delete("/users/{id}")
    async def delete_user(
        id: int,
        user: UserIdentity = Depends(require_permission("user:delete"))
    ):
        ...
"""

from typing import List, Optional, Callable, Type, TYPE_CHECKING
from functools import wraps

from fastapi import Depends, Request, HTTPException

from yweb.auth import UserIdentity
from yweb.log import get_logger

from .services import PermissionService
from .exceptions import PermissionDeniedException
from .types import SubjectId, PermissionCode, RoleCode

if TYPE_CHECKING:
    from .models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
    )

logger = get_logger("yweb.permission.dependencies")

# 全局权限服务实例
_permission_service: Optional[PermissionService] = None


def init_permission_dependency(
    permission_model: Type["AbstractPermission"],
    role_model: Type["AbstractRole"],
    subject_role_model: Type["AbstractSubjectRole"],
    role_permission_model: Type["AbstractRolePermission"],
    subject_permission_model: Type["AbstractSubjectPermission"],
    use_cache: bool = True
) -> PermissionService:
    """初始化权限依赖
    
    在应用启动时调用，初始化全局权限服务。
    
    Args:
        permission_model: 权限模型类
        role_model: 角色模型类
        subject_role_model: 主体-角色关联模型类
        role_permission_model: 角色-权限关联模型类
        subject_permission_model: 主体-权限关联模型类
        use_cache: 是否使用缓存
        
    Returns:
        PermissionService 实例
    
    使用示例:
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
    """
    global _permission_service
    
    _permission_service = PermissionService(
        permission_model=permission_model,
        role_model=role_model,
        subject_role_model=subject_role_model,
        role_permission_model=role_permission_model,
        subject_permission_model=subject_permission_model,
        use_cache=use_cache
    )
    
    logger.info("Permission dependency initialized")
    return _permission_service


def get_permission_service() -> PermissionService:
    """获取全局权限服务实例
    
    Returns:
        PermissionService 实例
        
    Raises:
        RuntimeError: 如果服务未初始化
    """
    if _permission_service is None:
        raise RuntimeError(
            "Permission service not initialized. "
            "Call init_permission_dependency() first."
        )
    return _permission_service


def get_subject_id_from_user(user: UserIdentity) -> SubjectId:
    """从 UserIdentity 获取 subject_id
    
    根据 user.source 判断用户类型：
    - 如果 source 是 "employee" 或包含 "employee"，使用 "employee:{id}"
    - 否则使用 "external:{id}"
    
    Args:
        user: UserIdentity 对象
        
    Returns:
        subject_id 字符串
    """
    # 尝试从 user 的属性中获取类型信息
    source = getattr(user, 'source', '') or ''
    
    if 'employee' in source.lower():
        return f"employee:{user.user_id}"
    else:
        # 默认使用 external（可以根据实际情况调整）
        return f"external:{user.user_id}"


class PermissionChecker:
    """权限检查器
    
    用于 FastAPI 依赖注入的权限检查类。
    
    使用示例:
        @app.get("/users")
        async def list_users(
            user: UserIdentity = Depends(PermissionChecker("user:list"))
        ):
            ...
    """
    
    def __init__(
        self,
        permissions: List[PermissionCode],
        require_all: bool = True,
        get_user_dependency: Optional[Callable] = None
    ):
        """初始化权限检查器
        
        Args:
            permissions: 需要的权限列表
            require_all: True 需要全部权限，False 只需任一
            get_user_dependency: 获取用户信息的依赖函数。
                如果不传，需要在路由中通过其他方式注入 user 参数。
        """
        self.permissions = permissions
        self.require_all = require_all
        self.get_user_dependency = get_user_dependency
    
    async def __call__(
        self,
        request: Request,
        user: UserIdentity = None
    ) -> UserIdentity:
        """执行权限检查
        
        Args:
            request: FastAPI Request
            user: 用户信息
            
        Returns:
            通过检查的用户信息
            
        Raises:
            HTTPException: 权限不足时抛出 403
        """
        # 获取用户信息
        if user is None:
            if self.get_user_dependency is None:
                raise RuntimeError(
                    "PermissionChecker 未配置认证依赖（get_user_dependency）。"
                    "请在创建时传入，例如: PermissionChecker(permissions, "
                    "get_user_dependency=get_current_user)"
                )
            try:
                user = await self.get_user_dependency(request)
            except HTTPException:
                raise
            except Exception as e:
                raise HTTPException(status_code=401, detail="未认证")
        
        if user is None:
            raise HTTPException(status_code=401, detail="未认证")
        
        # 获取 subject_id
        subject_id = get_subject_id_from_user(user)
        
        # 检查权限
        perm_service = get_permission_service()
        
        has_permission = perm_service.check_permissions(
            subject_id=subject_id,
            permission_codes=self.permissions,
            require_all=self.require_all
        )
        
        if not has_permission:
            logger.warning(
                f"Permission denied: {subject_id} requires {self.permissions}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"权限不足，需要: {', '.join(self.permissions)}"
            )
        
        return user


class RoleChecker:
    """角色检查器
    
    用于 FastAPI 依赖注入的角色检查类。
    
    使用示例:
        @app.delete("/users/{id}")
        async def delete_user(
            id: int,
            user: UserIdentity = Depends(RoleChecker(["admin"]))
        ):
            ...
    """
    
    def __init__(
        self,
        roles: List[RoleCode],
        require_all: bool = False,
        get_user_dependency: Optional[Callable] = None
    ):
        """初始化角色检查器
        
        Args:
            roles: 需要的角色列表
            require_all: True 需要全部角色，False 只需任一（默认）
            get_user_dependency: 获取用户信息的依赖函数。
                如果不传，需要在路由中通过其他方式注入 user 参数。
        """
        self.roles = roles
        self.require_all = require_all
        self.get_user_dependency = get_user_dependency
    
    async def __call__(
        self,
        request: Request,
        user: UserIdentity = None
    ) -> UserIdentity:
        """执行角色检查"""
        # 获取用户信息
        if user is None:
            if self.get_user_dependency is None:
                raise RuntimeError(
                    "RoleChecker 未配置认证依赖（get_user_dependency）。"
                    "请在创建时传入，例如: RoleChecker(roles, "
                    "get_user_dependency=get_current_user)"
                )
            try:
                user = await self.get_user_dependency(request)
            except HTTPException:
                raise
            except Exception:
                raise HTTPException(status_code=401, detail="未认证")
        
        if user is None:
            raise HTTPException(status_code=401, detail="未认证")
        
        # 获取 subject_id
        subject_id = get_subject_id_from_user(user)
        
        # 检查角色
        perm_service = get_permission_service()
        user_roles = perm_service.get_all_roles(subject_id)
        
        if self.require_all:
            has_role = all(r in user_roles for r in self.roles)
        else:
            has_role = any(r in user_roles for r in self.roles)
        
        if not has_role:
            logger.warning(
                f"Role check failed: {subject_id} requires {self.roles}"
            )
            raise HTTPException(
                status_code=403,
                detail=f"角色不足，需要: {', '.join(self.roles)}"
            )
        
        return user


def require_permission(
    *permissions: PermissionCode,
    require_all: bool = True
) -> PermissionChecker:
    """创建权限检查依赖
    
    便捷函数，用于创建 PermissionChecker 实例。
    
    Args:
        *permissions: 需要的权限编码
        require_all: True 需要全部权限，False 只需任一
        
    Returns:
        PermissionChecker 实例
    
    使用示例:
        @app.get("/users")
        async def list_users(
            user: UserIdentity = Depends(require_permission("user:list"))
        ):
            ...
        
        @app.put("/users/{id}")
        async def update_user(
            id: int,
            user: UserIdentity = Depends(require_permission("user:update", "user:read"))
        ):
            ...
    """
    return PermissionChecker(
        permissions=list(permissions),
        require_all=require_all
    )


def require_role(*roles: RoleCode, require_all: bool = False) -> RoleChecker:
    """创建角色检查依赖
    
    便捷函数，用于创建 RoleChecker 实例。
    
    Args:
        *roles: 需要的角色编码
        require_all: True 需要全部角色，False 只需任一（默认）
        
    Returns:
        RoleChecker 实例
    
    使用示例:
        @app.delete("/users/{id}")
        async def delete_user(
            id: int,
            user: UserIdentity = Depends(require_role("admin"))
        ):
            ...
    """
    return RoleChecker(
        roles=list(roles),
        require_all=require_all
    )


def require_any_permission(*permissions: PermissionCode) -> PermissionChecker:
    """创建任一权限检查依赖
    
    只需满足任一权限即可通过。
    
    Args:
        *permissions: 权限编码列表
        
    Returns:
        PermissionChecker 实例
    """
    return PermissionChecker(
        permissions=list(permissions),
        require_all=False
    )


def require_all_roles(*roles: RoleCode) -> RoleChecker:
    """创建全部角色检查依赖
    
    需要满足全部角色才能通过。
    
    Args:
        *roles: 角色编码列表
        
    Returns:
        RoleChecker 实例
    """
    return RoleChecker(
        roles=list(roles),
        require_all=True
    )


__all__ = [
    # 初始化
    "init_permission_dependency",
    "get_permission_service",
    "get_subject_id_from_user",
    
    # 检查器类
    "PermissionChecker",
    "RoleChecker",
    
    # 便捷函数
    "require_permission",
    "require_role",
    "require_any_permission",
    "require_all_roles",
]
