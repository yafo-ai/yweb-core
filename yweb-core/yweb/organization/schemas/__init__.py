"""
组织管理模块 - Pydantic Schema

提供 API 请求/响应的数据模型定义。
"""

from .organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
)
from .department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentTreeNode,
)
from .employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeDetailResponse,
    EmployeeOrgRelCreate,
    EmployeeOrgRelResponse,
    EmployeeDeptRelCreate,
    EmployeeDeptRelResponse,
    DeptLeaderCreate,
    DeptLeaderResponse,
)

__all__ = [
    # Organization
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    
    # Department
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "DepartmentTreeNode",
    
    # Employee
    "EmployeeCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "EmployeeDetailResponse",
    "EmployeeOrgRelCreate",
    "EmployeeOrgRelResponse",
    "EmployeeDeptRelCreate",
    "EmployeeDeptRelResponse",
    "DeptLeaderCreate",
    "DeptLeaderResponse",
]
