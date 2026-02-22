"""
权限模块 - 类型定义

提供权限模块的类型别名和协议定义
"""

from typing import Protocol, Set, List, Optional, Union, runtime_checkable
from datetime import datetime

from .enums import UserType


# 主体ID类型：格式为 "user_type:id"，如 "employee:123", "external:456"
SubjectId = str

# 权限编码类型：格式为 "resource:action"，如 "user:read", "order:write"
PermissionCode = str

# 角色编码类型
RoleCode = str


@runtime_checkable
class SubjectProtocol(Protocol):
    """权限主体协议
    
    所有可以被授权的实体（员工、外部用户）都应实现此协议
    
    使用示例:
        class Employee(AbstractEmployee):
            @property
            def subject_id(self) -> str:
                return f"employee:{self.id}"
            
            @property
            def subject_type(self) -> UserType:
                return UserType.EMPLOYEE
    """
    
    @property
    def subject_id(self) -> SubjectId:
        """获取主体唯一标识
        
        格式: "{user_type}:{id}"
        例如: "employee:123", "external:456"
        """
        ...
    
    @property
    def subject_type(self) -> UserType:
        """获取主体类型"""
        ...


def parse_subject_id(subject_id: SubjectId) -> tuple[str, int]:
    """解析主体ID
    
    Args:
        subject_id: 主体标识，如 "employee:123"
    
    Returns:
        (subject_type, id) 元组
    
    Raises:
        ValueError: 格式不正确时
    
    Example:
        >>> parse_subject_id("employee:123")
        ("employee", 123)
    """
    if ":" not in subject_id:
        raise ValueError(f"Invalid subject_id format: {subject_id}, expected 'type:id'")
    
    parts = subject_id.split(":", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid subject_id format: {subject_id}")
    
    subject_type, id_str = parts
    try:
        subject_id_int = int(id_str)
    except ValueError:
        raise ValueError(f"Invalid subject_id: id part must be integer, got '{id_str}'")
    
    return subject_type, subject_id_int


def make_subject_id(subject_type: Union[str, UserType], id: int) -> SubjectId:
    """构造主体ID
    
    Args:
        subject_type: 主体类型
        id: 主体ID
    
    Returns:
        主体标识字符串
    
    Example:
        >>> make_subject_id(UserType.EMPLOYEE, 123)
        "employee:123"
    """
    if isinstance(subject_type, UserType):
        subject_type = subject_type.value
    return f"{subject_type}:{id}"


def make_permission_code(resource: str, action: str) -> PermissionCode:
    """构造权限编码
    
    Args:
        resource: 资源类型
        action: 操作类型
    
    Returns:
        权限编码字符串
    
    Example:
        >>> make_permission_code("user", "read")
        "user:read"
    """
    return f"{resource}:{action}"


def parse_permission_code(permission_code: PermissionCode) -> tuple[str, str]:
    """解析权限编码
    
    Args:
        permission_code: 权限编码，如 "user:read"
    
    Returns:
        (resource, action) 元组
    
    Example:
        >>> parse_permission_code("user:read")
        ("user", "read")
    """
    if ":" not in permission_code:
        raise ValueError(f"Invalid permission_code format: {permission_code}")
    
    parts = permission_code.split(":", 1)
    return parts[0], parts[1]


__all__ = [
    # 类型别名
    "SubjectId",
    "PermissionCode",
    "RoleCode",
    
    # 协议
    "SubjectProtocol",
    
    # 工具函数
    "parse_subject_id",
    "make_subject_id",
    "make_permission_code",
    "parse_permission_code",
]
