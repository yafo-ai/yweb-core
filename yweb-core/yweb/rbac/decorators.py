"""
权限模块 - 装饰器

提供权限检查装饰器，适用于普通函数和方法。

使用示例:
    from yweb.permission import permission_required, role_required
    
    @permission_required("user:read")
    def get_user(subject_id: str, user_id: int):
        ...
    
    @role_required("admin")
    def delete_user(subject_id: str, user_id: int):
        ...
"""

from typing import List, Union, Callable, Optional
from functools import wraps

from .dependencies import get_permission_service
from .types import PermissionCode, RoleCode, SubjectId
from .exceptions import PermissionDeniedException
from yweb.log import get_logger

logger = get_logger("yweb.permission.decorators")


def permission_required(
    *permissions: PermissionCode,
    require_all: bool = True,
    subject_id_param: str = "subject_id",
    raise_exception: bool = True
) -> Callable:
    """权限检查装饰器
    
    用于装饰普通函数或方法，检查调用者是否有所需权限。
    
    Args:
        *permissions: 需要的权限编码
        require_all: True 需要全部权限，False 只需任一
        subject_id_param: 函数参数中表示 subject_id 的参数名
        raise_exception: 无权限时是否抛出异常
        
    Returns:
        装饰器函数
    
    使用示例:
        @permission_required("user:read", "user:list")
        def get_users(subject_id: str):
            # subject_id 会被自动用于权限检查
            return User.query.all()
        
        # 自定义参数名
        @permission_required("order:read", subject_id_param="current_user_id")
        def get_orders(current_user_id: str):
            ...
        
        # 只需任一权限
        @permission_required("user:read", "admin:*", require_all=False)
        def view_data(subject_id: str):
            ...
    
    注意:
        - 被装饰的函数必须有一个参数用于传递 subject_id
        - 可以是位置参数或关键字参数
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取 subject_id
            subject_id = _extract_subject_id(
                func,
                args,
                kwargs,
                subject_id_param
            )
            
            if subject_id is None:
                logger.warning(
                    f"Cannot extract subject_id from {func.__name__}, "
                    f"param '{subject_id_param}' not found"
                )
                if raise_exception:
                    raise PermissionDeniedException(
                        message="无法获取用户标识",
                        required_permissions=list(permissions)
                    )
                return None
            
            # 检查权限
            perm_service = get_permission_service()
            has_permission = perm_service.check_permissions(
                subject_id=subject_id,
                permission_codes=list(permissions),
                require_all=require_all
            )
            
            if not has_permission:
                logger.warning(
                    f"Permission denied: {subject_id} requires "
                    f"{permissions} (all={require_all})"
                )
                if raise_exception:
                    raise PermissionDeniedException(
                        subject_id=subject_id,
                        required_permissions=list(permissions)
                    )
                return None
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def role_required(
    *roles: RoleCode,
    require_all: bool = False,
    subject_id_param: str = "subject_id",
    raise_exception: bool = True
) -> Callable:
    """角色检查装饰器
    
    用于装饰普通函数或方法，检查调用者是否有所需角色。
    
    Args:
        *roles: 需要的角色编码
        require_all: True 需要全部角色，False 只需任一（默认）
        subject_id_param: 函数参数中表示 subject_id 的参数名
        raise_exception: 无角色时是否抛出异常
        
    Returns:
        装饰器函数
    
    使用示例:
        @role_required("admin")
        def admin_only(subject_id: str):
            ...
        
        @role_required("admin", "super_admin", require_all=False)
        def high_level_access(subject_id: str):
            ...
    """
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            # 获取 subject_id
            subject_id = _extract_subject_id(
                func,
                args,
                kwargs,
                subject_id_param
            )
            
            if subject_id is None:
                logger.warning(
                    f"Cannot extract subject_id from {func.__name__}, "
                    f"param '{subject_id_param}' not found"
                )
                if raise_exception:
                    raise PermissionDeniedException(
                        message="无法获取用户标识",
                        required_roles=list(roles)
                    )
                return None
            
            # 检查角色
            perm_service = get_permission_service()
            user_roles = perm_service.get_all_roles(subject_id)
            
            if require_all:
                has_role = all(r in user_roles for r in roles)
            else:
                has_role = any(r in user_roles for r in roles)
            
            if not has_role:
                logger.warning(
                    f"Role check failed: {subject_id} requires "
                    f"{roles} (all={require_all})"
                )
                if raise_exception:
                    raise PermissionDeniedException(
                        message="角色不足",
                        subject_id=subject_id,
                        required_roles=list(roles)
                    )
                return None
            
            return func(*args, **kwargs)
        
        return wrapper
    return decorator


def _extract_subject_id(
    func: Callable,
    args: tuple,
    kwargs: dict,
    param_name: str
) -> Optional[SubjectId]:
    """从函数参数中提取 subject_id
    
    Args:
        func: 被装饰的函数
        args: 位置参数
        kwargs: 关键字参数
        param_name: 参数名
        
    Returns:
        subject_id 或 None
    """
    # 先尝试从关键字参数获取
    if param_name in kwargs:
        return kwargs[param_name]
    
    # 尝试从位置参数获取
    import inspect
    sig = inspect.signature(func)
    params = list(sig.parameters.keys())
    
    if param_name in params:
        idx = params.index(param_name)
        if idx < len(args):
            return args[idx]
    
    return None


# 便捷的预定义装饰器
def admin_required(func: Callable) -> Callable:
    """管理员角色检查装饰器
    
    等价于 @role_required("admin")
    """
    return role_required("admin")(func)


def super_admin_required(func: Callable) -> Callable:
    """超级管理员角色检查装饰器
    
    等价于 @role_required("super_admin")
    """
    return role_required("super_admin")(func)


__all__ = [
    "permission_required",
    "role_required",
    "admin_required",
    "super_admin_required",
]
