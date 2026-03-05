"""
权限模块 - 角色相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
    这样用户继承 AbstractRole 并添加自定义字段时，API 响应会自动包含这些字段。
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RoleCreate(BaseModel):
    """创建角色请求"""
    code: str = Field(..., min_length=1, max_length=50, description="角色编码")
    name: str = Field(..., min_length=1, max_length=100, description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")
    parent_code: Optional[str] = Field(None, description="父角色编码（用于继承）")
    is_system: bool = Field(False, description="是否系统内置")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "admin",
                "name": "管理员",
                "description": "系统管理员角色",
                "parent_code": None,
                "is_system": True
            }
        }


class RoleUpdate(BaseModel):
    """更新角色请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")
    is_active: Optional[bool] = Field(None, description="是否启用")
    parent_code: Optional[str] = Field(None, description="父角色编码（空字符串表示移除）")
    sort_order: Optional[int] = Field(None, ge=0, description="排序")


class RoleResponse(BaseModel):
    """角色响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    用户继承 AbstractRole 添加的自定义字段会自动包含在响应中。
    """
    id: int = Field(..., description="角色ID")
    code: str = Field(..., description="角色编码")
    name: str = Field(..., description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")
    parent_id: Optional[int] = Field(None, description="父角色ID")
    is_active: bool = Field(..., description="是否启用")
    is_system: bool = Field(..., description="是否系统内置")
    level: int = Field(..., description="层级")
    sort_order: int = Field(..., description="排序")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    # 可选的关联数据
    permissions: Optional[List[str]] = Field(None, description="拥有的权限编码列表")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class RoleTreeResponse(BaseModel):
    """角色树响应"""
    id: int = Field(..., description="角色ID")
    code: str = Field(..., description="角色编码")
    name: str = Field(..., description="角色名称")
    description: Optional[str] = Field(None, description="角色描述")
    is_active: bool = Field(..., description="是否启用")
    is_system: bool = Field(..., description="是否系统内置")
    level: int = Field(..., description="层级")
    children: List["RoleTreeResponse"] = Field(default_factory=list, description="子角色")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


# 支持递归引用
RoleTreeResponse.model_rebuild()


class RoleListResponse(BaseModel):
    """角色列表响应"""
    total: int = Field(..., description="总数")
    items: List[RoleResponse] = Field(..., description="角色列表")


class RolePermissionSet(BaseModel):
    """设置角色权限请求"""
    permission_codes: List[str] = Field(..., description="权限编码列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "permission_codes": ["user:read", "user:write", "user:delete"]
            }
        }


class RolePermissionAdd(BaseModel):
    """添加角色权限请求"""
    permission_code: str = Field(..., description="权限编码")


class RoleSubjectsResponse(BaseModel):
    """角色用户列表响应"""
    role_code: str = Field(..., description="角色编码")
    subjects: List[dict] = Field(..., description="用户列表")


__all__ = [
    "RoleCreate",
    "RoleUpdate",
    "RoleResponse",
    "RoleTreeResponse",
    "RoleListResponse",
    "RolePermissionSet",
    "RolePermissionAdd",
    "RoleSubjectsResponse",
]
