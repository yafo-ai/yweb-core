"""
组织管理模块 - 组织相关 Schema

支持用户扩展字段：
    响应 Schema 使用 extra="allow"，允许返回模型中存在但 Schema 未定义的字段。
    这样用户继承 AbstractOrganization 并添加自定义字段时，API 响应会自动包含这些字段。
"""

from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from yweb.orm import DTO


class OrganizationCreate(BaseModel):
    """创建组织请求"""
    name: str = Field(..., min_length=1, max_length=100, description="组织名称")
    code: str = Field(..., min_length=1, max_length=50, description="组织编码")
    note: Optional[str] = Field(None, description="备注")
    caption: Optional[str] = Field(None, description="介绍")
    external_source: Optional[str] = Field(None, max_length=50, description="外部系统来源")
    external_corp_id: Optional[str] = Field(None, max_length=255, description="外部企业ID")
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "总公司",
                "code": "HEAD",
                "note": "集团总部"
            }
        }


class OrganizationUpdate(BaseModel):
    """更新组织请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=100, description="组织名称")
    code: Optional[str] = Field(None, min_length=1, max_length=50, description="组织编码")
    note: Optional[str] = Field(None, description="备注")
    caption: Optional[str] = Field(None, description="介绍")


class OrganizationResponse(DTO):
    """组织响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    用户继承 AbstractOrganization 添加的自定义字段会自动包含在响应中。
    """
    id: int = Field(..., description="组织ID")
    name: str = Field(..., description="组织名称")
    code: Optional[str] = Field(None, description="组织编码")
    note: Optional[str] = Field(None, description="备注")
    caption: Optional[str] = Field(None, description="介绍")
    external_source: Optional[str] = Field(None, description="外部系统来源")
    external_corp_id: Optional[str] = Field(None, description="外部企业ID")
    is_active: bool = Field(True, description="是否启用")
    created_at: Optional[str] = Field(None, description="创建时间")
    updated_at: Optional[str] = Field(None, description="更新时间")
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


__all__ = [
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
]
