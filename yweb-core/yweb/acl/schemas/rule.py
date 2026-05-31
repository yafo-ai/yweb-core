"""
ACL 模块 - 规则相关 Schema
"""

from typing import Optional

from pydantic import BaseModel, Field


class CreateRuleRequest(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型")
    resource_id: str = Field(..., max_length=256, description="资源ID")
    subject_type: str = Field("user", max_length=20, description="主体类型")
    subject_id: str = Field(..., max_length=256, description="身份标签")
    permission_level: int = Field(..., description="权限等级")
    effect: str = Field("ALLOW", pattern="^(ALLOW|DENY)$", description="效果")
    inherit: bool = Field(True, description="是否向子资源传播")
    dept_scope: Optional[str] = Field(None, max_length=20, description="部门范围")


class UpdateRuleRequest(BaseModel):
    rule_id: int = Field(..., description="规则ID")
    permission_level: Optional[int] = Field(None, description="权限等级")
    effect: Optional[str] = Field(None, pattern="^(ALLOW|DENY)$", description="效果")
    inherit: Optional[bool] = Field(None, description="是否向子资源传播")
    dept_scope: Optional[str] = Field(None, max_length=20, description="部门范围")


class DeleteRuleRequest(BaseModel):
    rule_id: int = Field(..., description="规则ID")
