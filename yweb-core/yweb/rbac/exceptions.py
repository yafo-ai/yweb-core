"""
权限模块 - 异常定义

提供权限相关的异常类
"""

from typing import Optional, List, Any

from yweb.exceptions import BusinessException, ErrorCode, ErrorCodeType
from fastapi import status


class PermissionException(BusinessException):
    """权限异常基类
    
    所有权限相关异常的基类，继承自 BusinessException。
    
    使用示例:
        raise PermissionException("权限错误")
        raise PermissionException("需要管理员权限", code=ErrorCode.ADMIN_REQUIRED)
    """
    
    def __init__(
        self,
        message: str = "权限错误",
        code: ErrorCodeType = ErrorCode.PERMISSION_DENIED,
        status_code: int = status.HTTP_403_FORBIDDEN,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
            **extra
        )


class PermissionDeniedException(PermissionException):
    """权限拒绝异常
    
    当用户没有所需权限时抛出
    
    使用示例:
        if not perm_service.check_permission(subject_id, "user:delete"):
            raise PermissionDeniedException(
                permission_code="user:delete",
                subject_id=subject_id
            )
    """
    
    def __init__(
        self,
        message: str = "权限不足",
        permission_code: Optional[str] = None,
        subject_id: Optional[str] = None,
        required_permissions: Optional[List[str]] = None,
        required_roles: Optional[List[str]] = None,
    ):
        details = []
        if permission_code:
            details.append(f"所需权限: {permission_code}")
        if required_permissions:
            details.append(f"所需权限列表: {', '.join(required_permissions)}")
        if required_roles:
            details.append(f"所需角色: {', '.join(required_roles)}")
        
        if permission_code and not message.endswith(permission_code):
            message = f"{message}: {permission_code}"
        
        super().__init__(
            message=message,
            code=ErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details or None,
            permission_code=permission_code,
            subject_id=subject_id,
            required_permissions=required_permissions,
            required_roles=required_roles,
        )
        self.permission_code = permission_code
        self.subject_id = subject_id
        self.required_permissions = required_permissions
        self.required_roles = required_roles


class RoleNotFoundException(PermissionException):
    """角色不存在异常"""
    
    def __init__(self, role_code: str):
        super().__init__(
            message=f"角色不存在: {role_code}",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            role_code=role_code,
        )
        self.role_code = role_code


class PermissionNotFoundException(PermissionException):
    """权限不存在异常"""
    
    def __init__(self, permission_code: str):
        super().__init__(
            message=f"权限不存在: {permission_code}",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            permission_code=permission_code,
        )
        self.permission_code = permission_code


class SubjectNotFoundException(PermissionException):
    """主体（用户）不存在异常"""
    
    def __init__(self, subject_id: str):
        super().__init__(
            message=f"用户不存在: {subject_id}",
            code=ErrorCode.USER_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            subject_id=subject_id,
        )
        self.subject_id = subject_id


class DuplicateRoleException(PermissionException):
    """角色已存在异常"""
    
    def __init__(self, role_code: str):
        super().__init__(
            message=f"角色已存在: {role_code}",
            code=ErrorCode.DUPLICATE_ENTRY,
            status_code=status.HTTP_409_CONFLICT,
            role_code=role_code,
        )
        self.role_code = role_code


class DuplicatePermissionException(PermissionException):
    """权限已存在异常"""
    
    def __init__(self, permission_code: str):
        super().__init__(
            message=f"权限已存在: {permission_code}",
            code=ErrorCode.DUPLICATE_ENTRY,
            status_code=status.HTTP_409_CONFLICT,
            permission_code=permission_code,
        )
        self.permission_code = permission_code


class RoleInheritanceCycleException(PermissionException):
    """角色继承循环异常
    
    当设置角色父子关系会导致循环时抛出
    """
    
    def __init__(self, role_code: str, parent_code: str):
        super().__init__(
            message=f"角色继承循环: {role_code} -> {parent_code}",
            code=ErrorCode.BUSINESS_ERROR,
            status_code=status.HTTP_400_BAD_REQUEST,
            role_code=role_code,
            parent_code=parent_code,
        )
        self.role_code = role_code
        self.parent_code = parent_code


class SystemRoleModifyException(PermissionException):
    """系统角色不可修改异常"""
    
    def __init__(self, role_code: str, operation: str = "修改"):
        super().__init__(
            message=f"系统角色不可{operation}: {role_code}",
            code=ErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
            role_code=role_code,
            operation=operation,
        )
        self.role_code = role_code


__all__ = [
    "PermissionException",
    "PermissionDeniedException",
    "RoleNotFoundException",
    "PermissionNotFoundException",
    "SubjectNotFoundException",
    "DuplicateRoleException",
    "DuplicatePermissionException",
    "RoleInheritanceCycleException",
    "SystemRoleModifyException",
]
