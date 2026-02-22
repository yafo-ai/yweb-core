"""
组织管理模块 - 员工相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
    这样用户继承 AbstractEmployee 并添加自定义字段时，API 响应会自动包含这些字段。
"""

from typing import Optional, List
from pydantic import BaseModel, Field, ConfigDict

from yweb.orm import DTO
from ..enums import EmployeeStatus


# ==================== 员工基础 Schema ====================

class EmployeeCreate(BaseModel):
    """创建员工请求"""
    name: str = Field(..., min_length=1, max_length=100, description="姓名")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    gender: int = Field(0, ge=0, le=2, description="性别（0-未知，1-男，2-女）")
    avatar: Optional[str] = Field(None, max_length=500, description="头像URL")
    is_senior: bool = Field(False, description="是否高管")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "张三",
                "mobile": "13800138000",
                "email": "zhangsan@example.com",
                "gender": 1
            }
        }


class EmployeeUpdate(BaseModel):
    """更新员工请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="姓名")
    mobile: Optional[str] = Field(None, max_length=20, description="手机号")
    email: Optional[str] = Field(None, max_length=255, description="邮箱")
    gender: Optional[int] = Field(None, ge=0, le=2, description="性别")
    avatar: Optional[str] = Field(None, max_length=500, description="头像URL")
    is_senior: Optional[bool] = Field(None, description="是否高管")


class EmployeeResponse(DTO):
    """员工响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    用户继承 AbstractEmployee 添加的自定义字段会自动包含在响应中。
    """
    id: int = Field(..., description="员工ID")
    name: str = Field(..., description="姓名")
    mobile: Optional[str] = Field(None, description="手机号")
    email: Optional[str] = Field(None, description="邮箱")
    gender: int = Field(0, description="性别")
    avatar: Optional[str] = Field(None, description="头像URL")
    is_senior: bool = Field(False, description="是否高管")
    user_id: Optional[int] = Field(None, description="关联的用户账号ID")
    primary_org_id: Optional[int] = Field(None, description="主组织ID")
    primary_dept_id: Optional[int] = Field(None, description="主部门ID")
    account_status: Optional[int] = Field(None, description="账号状态（-1-已禁用，0-未激活，1-已激活），从关联用户推导")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    
    # 附加信息（通过 include 参数控制）
    primary_org_name: Optional[str] = Field(None, description="主组织名称")
    primary_dept_name: Optional[str] = Field(None, description="主部门名称")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class EmployeeOrgInfo(DTO):
    """员工在组织中的信息"""
    org_id: int = Field(..., description="组织ID")
    org_name: Optional[str] = Field(None, description="组织名称")
    emp_no: Optional[str] = Field(None, description="工号")
    position: Optional[str] = Field(None, description="职位")
    status: int = Field(EmployeeStatus.ACTIVE.value, description="状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）")
    joined_at: Optional[str] = Field(None, description="入职日期")
    is_primary: bool = Field(False, description="是否主组织")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class EmployeeDeptInfo(DTO):
    """员工在部门中的信息"""
    dept_id: int = Field(..., description="部门ID")
    dept_name: Optional[str] = Field(None, description="部门名称")
    is_primary: bool = Field(False, description="是否主部门")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class EmployeeDetailResponse(EmployeeResponse):
    """员工详情响应（包含关联信息）"""
    organizations: List[EmployeeOrgInfo] = Field(default_factory=list, description="所属组织列表")
    departments: List[EmployeeDeptInfo] = Field(default_factory=list, description="所属部门列表")


# ==================== 员工-组织关联 Schema ====================

class EmployeeOrgRelCreate(BaseModel):
    """员工加入组织请求"""
    employee_id: int = Field(..., description="员工ID")
    org_id: int = Field(..., description="组织ID")
    emp_no: Optional[str] = Field(None, max_length=100, description="工号")
    position: Optional[str] = Field(None, max_length=255, description="职位")
    status: int = Field(EmployeeStatus.ACTIVE.value, description="状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）")
    set_primary: bool = Field(False, description="是否设为主组织")
    
    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": 1,
                "org_id": 1,
                "emp_no": "EMP001",
                "position": "工程师",
                "set_primary": True
            }
        }


class EmployeeOrgRelUpdate(BaseModel):
    """更新员工组织关联请求"""
    emp_no: Optional[str] = Field(None, max_length=100, description="工号")
    position: Optional[str] = Field(None, max_length=255, description="职位")
    status: Optional[int] = Field(None, description="状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）")


class EmployeeOrgRelResponse(DTO):
    """员工-组织关联响应"""
    id: int = Field(..., description="关联ID")
    employee_id: int = Field(..., description="员工ID")
    org_id: int = Field(..., description="组织ID")
    emp_no: Optional[str] = Field(None, description="工号")
    position: Optional[str] = Field(None, description="职位")
    status: int = Field(EmployeeStatus.ACTIVE.value, description="状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）")
    joined_at: Optional[str] = Field(None, description="入职日期")
    created_at: Optional[str] = Field(None, description="创建时间")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


# ==================== 员工-部门关联 Schema ====================

class EmployeeDeptRelCreate(BaseModel):
    """员工加入部门请求"""
    employee_id: int = Field(..., description="员工ID")
    dept_id: int = Field(..., description="部门ID")
    set_primary: bool = Field(False, description="是否设为主部门")
    
    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": 1,
                "dept_id": 1,
                "set_primary": True
            }
        }


class EmployeeDeptRelResponse(DTO):
    """员工-部门关联响应"""
    id: int = Field(..., description="关联ID")
    employee_id: int = Field(..., description="员工ID")
    dept_id: int = Field(..., description="部门ID")
    created_at: Optional[str] = Field(None, description="创建时间")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


# ==================== 部门负责人 Schema ====================

class DeptLeaderCreate(BaseModel):
    """添加部门负责人请求"""
    employee_id: int = Field(..., description="员工ID")
    dept_id: int = Field(..., description="部门ID")
    set_primary: bool = Field(False, description="是否设为主负责人")
    
    class Config:
        json_schema_extra = {
            "example": {
                "employee_id": 1,
                "dept_id": 1,
                "set_primary": True
            }
        }


class DeptLeaderResponse(DTO):
    """部门负责人响应"""
    id: int = Field(..., description="关联ID")
    dept_id: int = Field(..., description="部门ID")
    employee_id: int = Field(..., description="员工ID")
    is_primary: bool = Field(False, description="是否主负责人")
    created_at: Optional[str] = Field(None, description="创建时间")
    
    # 附加信息
    employee_name: Optional[str] = Field(None, description="员工姓名")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


__all__ = [
    # Employee
    "EmployeeCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "EmployeeDetailResponse",
    "EmployeeOrgInfo",
    "EmployeeDeptInfo",
    
    # Employee-Org Relation
    "EmployeeOrgRelCreate",
    "EmployeeOrgRelUpdate",
    "EmployeeOrgRelResponse",
    
    # Employee-Dept Relation
    "EmployeeDeptRelCreate",
    "EmployeeDeptRelResponse",
    
    # Dept Leader
    "DeptLeaderCreate",
    "DeptLeaderResponse",
]
