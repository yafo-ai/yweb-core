"""
ACL 模块 - 资源相关 Schema
"""

from typing import Optional

from pydantic import BaseModel, Field


class RegisterResourceRequest(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型")
    resource_id: str = Field(..., max_length=256, description="业务资源ID")
    display_name: str = Field(..., max_length=256, description="显示名称")
    parent_id: Optional[int] = Field(None, description="父节点ID（ACL 资源树的 id）")


class InheritRequest(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型")
    resource_id: str = Field(..., max_length=256, description="业务资源ID")
    inherit_parent: bool = Field(..., description="是否继承父级规则")
