"""
ACL 模块 - 异常定义
"""

from typing import Optional, List, Any

from yweb.exceptions import BusinessException, ErrorCode, ErrorCodeType
from fastapi import status


class AclException(BusinessException):
    """ACL 异常基类"""

    def __init__(
        self,
        message: str = "ACL 错误",
        code: ErrorCodeType = ErrorCode.BUSINESS_ERROR,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[List[str]] = None,
        **extra: Any,
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status_code,
            details=details,
            **extra,
        )


class AclPermissionDenied(AclException):
    """ACL 权限拒绝"""

    def __init__(
        self,
        message: str = "权限不足",
        resource_type: Optional[str] = None,
        resource_id: Optional[str] = None,
        required_level: Optional[int] = None,
    ):
        details = []
        if resource_type:
            details.append(f"资源类型: {resource_type}")
        if resource_id:
            details.append(f"资源ID: {resource_id}")
        if required_level is not None:
            details.append(f"所需等级: {required_level}")

        super().__init__(
            message=message,
            code=ErrorCode.PERMISSION_DENIED,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details or None,
            resource_type=resource_type,
            resource_id=resource_id,
            required_level=required_level,
        )


class AclResourceNotFound(AclException):
    """ACL 资源不存在"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"ACL 资源不存在: {resource_type}/{resource_id}",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            resource_type=resource_type,
            resource_id=resource_id,
        )


class AclRuleNotFound(AclException):
    """ACL 规则不存在"""

    def __init__(self, rule_id: Any):
        super().__init__(
            message=f"ACL 规则不存在: {rule_id}",
            code=ErrorCode.RESOURCE_NOT_FOUND,
            status_code=status.HTTP_404_NOT_FOUND,
            rule_id=rule_id,
        )


class AclDuplicateResource(AclException):
    """ACL 资源已存在"""

    def __init__(self, resource_type: str, resource_id: str):
        super().__init__(
            message=f"ACL 资源已存在: {resource_type}/{resource_id}",
            code=ErrorCode.DUPLICATE_ENTRY,
            status_code=status.HTTP_409_CONFLICT,
            resource_type=resource_type,
            resource_id=resource_id,
        )


__all__ = [
    "AclException",
    "AclPermissionDenied",
    "AclResourceNotFound",
    "AclRuleNotFound",
    "AclDuplicateResource",
]
