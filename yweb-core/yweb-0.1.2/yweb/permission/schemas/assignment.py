"""
权限模块 - 授权相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
"""

from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class RoleAssignment(BaseModel):
    """角色分配请求"""
    subject_id: str = Field(..., description="主体标识，如 employee:123")
    role_code: str = Field(..., description="角色编码")
    expires_at: Optional[datetime] = Field(None, description="过期时间（NULL 表示永久）")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": "employee:123",
                "role_code": "manager",
                "expires_at": "2026-12-31T23:59:59"
            }
        }


class RoleUnassignment(BaseModel):
    """撤销角色请求"""
    subject_id: str = Field(..., description="主体标识")
    role_code: str = Field(..., description="角色编码")


class PermissionAssignment(BaseModel):
    """直接权限分配请求"""
    subject_id: str = Field(..., description="主体标识")
    permission_code: str = Field(..., description="权限编码")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    reason: Optional[str] = Field(None, description="授权原因")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": "employee:123",
                "permission_code": "finance:report",
                "expires_at": "2026-06-30T23:59:59",
                "reason": "临时需要查看财务报告"
            }
        }


class PermissionRevocation(BaseModel):
    """撤销权限请求"""
    subject_id: str = Field(..., description="主体标识")
    permission_code: str = Field(..., description="权限编码")


class SubjectRoleResponse(BaseModel):
    """主体角色响应"""
    id: int = Field(..., description="关联ID")
    subject_type: str = Field(..., description="主体类型")
    subject_id: int = Field(..., description="主体ID")
    role_id: int = Field(..., description="角色ID")
    role_code: Optional[str] = Field(None, description="角色编码")
    role_name: Optional[str] = Field(None, description="角色名称")
    granted_by: Optional[int] = Field(None, description="授权人ID")
    granted_at: datetime = Field(..., description="授权时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    is_active: bool = Field(..., description="是否启用")
    is_expired: bool = Field(..., description="是否已过期")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class SubjectPermissionResponse(BaseModel):
    """主体直接权限响应"""
    id: int = Field(..., description="关联ID")
    subject_type: str = Field(..., description="主体类型")
    subject_id: int = Field(..., description="主体ID")
    permission_id: int = Field(..., description="权限ID")
    permission_code: Optional[str] = Field(None, description="权限编码")
    permission_name: Optional[str] = Field(None, description="权限名称")
    granted_by: Optional[int] = Field(None, description="授权人ID")
    granted_at: datetime = Field(..., description="授权时间")
    expires_at: Optional[datetime] = Field(None, description="过期时间")
    reason: Optional[str] = Field(None, description="授权原因")
    is_active: bool = Field(..., description="是否启用")
    is_expired: bool = Field(..., description="是否已过期")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


class SubjectPermissionsResponse(BaseModel):
    """主体权限汇总响应"""
    subject_id: str = Field(..., description="主体标识")
    roles: List[str] = Field(..., description="角色编码列表")
    permissions: List[str] = Field(..., description="权限编码列表（含继承）")
    direct_permissions: List[str] = Field(..., description="直接授予的权限编码")
    
    class Config:
        json_schema_extra = {
            "example": {
                "subject_id": "employee:123",
                "roles": ["manager", "admin"],
                "permissions": ["user:read", "user:write", "order:read"],
                "direct_permissions": ["finance:report"]
            }
        }


class BatchRoleAssignment(BaseModel):
    """批量角色分配请求"""
    subject_ids: List[str] = Field(..., description="主体标识列表")
    role_code: str = Field(..., description="角色编码")
    expires_at: Optional[datetime] = Field(None, description="过期时间")


class BatchRoleUnassignment(BaseModel):
    """批量撤销角色请求"""
    subject_ids: List[str] = Field(..., description="主体标识列表")
    role_code: str = Field(..., description="角色编码")


__all__ = [
    "RoleAssignment",
    "RoleUnassignment",
    "PermissionAssignment",
    "PermissionRevocation",
    "SubjectRoleResponse",
    "SubjectPermissionResponse",
    "SubjectPermissionsResponse",
    "BatchRoleAssignment",
    "BatchRoleUnassignment",
]
