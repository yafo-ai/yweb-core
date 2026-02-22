"""
权限模块 - 权限相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
    这样用户继承 AbstractPermission 并添加自定义字段时，API 响应会自动包含这些字段。
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class PermissionCreate(BaseModel):
    """创建权限请求"""
    code: str = Field(..., min_length=1, max_length=100, description="权限编码，如 user:read")
    name: str = Field(..., min_length=1, max_length=100, description="权限名称")
    resource: Optional[str] = Field(None, max_length=50, description="资源类型（不填则从 code 解析）")
    action: Optional[str] = Field(None, max_length=50, description="操作类型（不填则从 code 解析）")
    description: Optional[str] = Field(None, description="权限描述")
    module: Optional[str] = Field(None, max_length=50, description="所属模块")
    
    class Config:
        json_schema_extra = {
            "example": {
                "code": "user:read",
                "name": "查看用户",
                "description": "允许查看用户信息",
                "module": "user"
            }
        }


class PermissionUpdate(BaseModel):
    """更新权限请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="权限名称")
    description: Optional[str] = Field(None, description="权限描述")
    is_active: Optional[bool] = Field(None, description="是否启用")
    module: Optional[str] = Field(None, max_length=50, description="所属模块")
    sort_order: Optional[int] = Field(None, ge=0, description="排序")


class PermissionResponse(BaseModel):
    """权限响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    用户继承 AbstractPermission 添加的自定义字段会自动包含在响应中。
    """
    id: int = Field(..., description="权限ID")
    code: str = Field(..., description="权限编码")
    name: str = Field(..., description="权限名称")
    resource: str = Field(..., description="资源类型")
    action: str = Field(..., description="操作类型")
    description: Optional[str] = Field(None, description="权限描述")
    module: Optional[str] = Field(None, description="所属模块")
    is_active: bool = Field(..., description="是否启用")
    sort_order: int = Field(..., description="排序")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: Optional[datetime] = Field(None, description="更新时间")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class PermissionListResponse(BaseModel):
    """权限列表响应"""
    total: int = Field(..., description="总数")
    items: List[PermissionResponse] = Field(..., description="权限列表")
    
    class Config:
        json_schema_extra = {
            "example": {
                "total": 10,
                "items": [
                    {
                        "id": 1,
                        "code": "user:read",
                        "name": "查看用户",
                        "resource": "user",
                        "action": "read",
                        "is_active": True,
                        "sort_order": 0,
                        "created_at": "2026-01-19T10:00:00"
                    }
                ]
            }
        }


class PermissionCheck(BaseModel):
    """权限检查请求"""
    subject_id: str = Field(..., description="主体标识，如 employee:123")
    permission_code: str = Field(..., description="权限编码")


class PermissionCheckResult(BaseModel):
    """权限检查结果"""
    has_permission: bool = Field(..., description="是否有权限")
    subject_id: str = Field(..., description="主体标识")
    permission_code: str = Field(..., description="权限编码")


__all__ = [
    "PermissionCreate",
    "PermissionUpdate",
    "PermissionResponse",
    "PermissionListResponse",
    "PermissionCheck",
    "PermissionCheckResult",
]
