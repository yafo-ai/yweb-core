"""
权限模块 - 枚举定义

提供权限模块相关的枚举类型
"""

from enum import Enum, IntEnum


class UserType(str, Enum):
    """用户类型
    
    区分内部员工和外部用户
    """
    EMPLOYEE = "employee"      # 内部员工（来自 organization.Employee）
    EXTERNAL = "external"      # 外部用户（来自 permission.ExternalUser）


class PermissionAction(str, Enum):
    """权限操作类型
    
    常用的 CRUD 操作
    """
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    LIST = "list"
    EXPORT = "export"
    IMPORT = "import"
    APPROVE = "approve"
    REJECT = "reject"
    ALL = "*"  # 所有操作


class DataScopeType(str, Enum):
    """数据范围类型
    
    用于数据级权限控制
    """
    ALL = "all"                      # 全部数据
    SELF = "self"                    # 仅本人数据
    DEPT = "dept"                    # 本部门数据
    DEPT_AND_CHILDREN = "dept_tree"  # 本部门及下级部门
    CUSTOM = "custom"                # 自定义条件


class GrantType(str, Enum):
    """授权类型"""
    PERMANENT = "permanent"    # 永久授权
    TEMPORARY = "temporary"    # 临时授权（有过期时间）


__all__ = [
    "UserType",
    "PermissionAction",
    "DataScopeType",
    "GrantType",
]
