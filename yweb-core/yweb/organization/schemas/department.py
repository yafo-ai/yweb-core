"""
组织管理模块 - 部门相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
    这样用户继承 AbstractDepartment 并添加自定义字段时，API 响应会自动包含这些字段。
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict

from yweb.orm import DTO


class DepartmentCreate(BaseModel):
    """创建部门请求"""
    org_id: int = Field(..., description="所属组织ID")
    name: str = Field(..., min_length=1, max_length=100, description="部门名称")
    code: Optional[str] = Field(None, max_length=50, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")
    sort_order: int = Field(0, ge=0, description="排序序号")
    note: Optional[str] = Field(None, description="备注")
    
    class Config:
        json_schema_extra = {
            "example": {
                "org_id": 1,
                "name": "技术部",
                "parent_id": None,
                "sort_order": 0
            }
        }


class DepartmentUpdate(BaseModel):
    """更新部门请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="部门名称")
    code: Optional[str] = Field(None, max_length=50, description="部门编码")
    sort_order: Optional[int] = Field(None, ge=0, description="排序序号")
    note: Optional[str] = Field(None, description="备注")
    primary_leader_id: Optional[int] = Field(None, description="主负责人ID")


class DepartmentResponse(DTO):
    """部门响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    用户继承 AbstractDepartment 添加的自定义字段会自动包含在响应中。
    """
    id: int = Field(..., description="部门ID")
    org_id: int = Field(..., description="所属组织ID")
    name: str = Field(..., description="部门名称")
    code: Optional[str] = Field(None, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")
    path: Optional[str] = Field(None, description="部门路径")
    level: int = Field(1, description="部门层级")
    sort_order: int = Field(0, description="排序序号")
    primary_leader_id: Optional[int] = Field(None, description="主负责人ID")
    note: Optional[str] = Field(None, description="备注")
    is_active: bool = Field(True, description="是否启用")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class DepartmentTreeNode(DTO):
    """部门树节点
    
    用于返回树形结构的部门数据。
    使用 extra="allow" 允许返回用户扩展的字段。
    """
    id: int = Field(..., description="部门ID")
    org_id: int = Field(..., description="所属组织ID")
    name: str = Field(..., description="部门名称")
    code: Optional[str] = Field(None, description="部门编码")
    parent_id: Optional[int] = Field(None, description="父部门ID")
    level: int = Field(1, description="部门层级")
    sort_order: int = Field(0, description="排序序号")
    
    # 树形特有字段
    children: List["DepartmentTreeNode"] = Field(default_factory=list, description="子部门")
    
    # 附加信息（通过 include 参数控制）
    employee_count: Optional[int] = Field(None, description="员工数量")
    full_name: Optional[str] = Field(None, description="完整路径名称")
    primary_leader_name: Optional[str] = Field(None, description="主负责人姓名")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


# 支持递归引用
DepartmentTreeNode.model_rebuild()


__all__ = [
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "DepartmentTreeNode",
]
