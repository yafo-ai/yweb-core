"""
ACL 模块 - 权限检查相关 Schema
"""

from typing import Optional, List

from pydantic import BaseModel, Field


class CheckRequest(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型")
    resource_id: str = Field(..., max_length=256, description="资源ID")
    required_level: int = Field(..., description="所需权限等级")
    target_user_id: Optional[int] = Field(
        None, description="目标用户ID（管理员查其他用户，省略则查自己）"
    )


class CheckItem(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型")
    resource_id: str = Field(..., max_length=256, description="资源ID")
    required_level: int = Field(..., description="所需权限等级")


class BatchCheckRequest(BaseModel):
    checks: List[CheckItem] = Field(..., description="批量检查项")
    target_user_id: Optional[int] = Field(
        None, description="目标用户ID（管理员查其他用户，省略则查自己）"
    )
