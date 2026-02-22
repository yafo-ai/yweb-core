"""
权限模块 - Pydantic Schema

提供 API 请求/响应的数据模型定义。
"""

from .permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
    PermissionListResponse,
)
from .role import (
    RoleCreate,
    RoleUpdate,
    RoleResponse,
    RoleTreeResponse,
    RolePermissionSet,
)
from .assignment import (
    RoleAssignment,
    PermissionAssignment,
    SubjectRoleResponse,
    SubjectPermissionResponse,
)

__all__ = [
    # Permission
    "PermissionCreate",
    "PermissionUpdate",
    "PermissionResponse",
    "PermissionListResponse",
    
    # Role
    "RoleCreate",
    "RoleUpdate",
    "RoleResponse",
    "RoleTreeResponse",
    "RolePermissionSet",
    
    # Assignment
    "RoleAssignment",
    "PermissionAssignment",
    "SubjectRoleResponse",
    "SubjectPermissionResponse",
]
