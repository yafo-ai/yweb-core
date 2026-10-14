"""
ACL 模块 - 规则相关 Schema
"""

from typing import List, Optional

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


class BatchCreateResourceItem(BaseModel):
    resource_type: str = Field(..., max_length=50, description="资源类型（与 acl_resource.resource_type 一致）")
    resource_id: str = Field(..., max_length=256, description="资源业务 ID（与 acl_resource.resource_id 一致）")


class BatchCreateRuleRequest(BaseModel):
    """同一主体/效果/等级，向多个资源批量创建或更新 ACL 规则。

    请求内重复的 (resource_type, resource_id) 会去重；
    目标资源上已存在相同 subject_id + effect 的规则时：
    permission_level 与 inherit 均相同则跳过，否则更新现有规则。
    """

    resources: List[BatchCreateResourceItem] = Field(
        ...,
        min_length=1,
        max_length=500,
        description=(
            "目标资源列表（1~500 项）。每项含 resource_type、resource_id；"
            "列表内重复资源会去重；已有相同主体+效果规则时，"
            "等级与继承均相同则跳过，否则更新"
        ),
    )
    subject_type: str = Field("user", max_length=20, description="主体类型，如 user/dept/role/post/everyone")
    subject_id: str = Field(..., max_length=256, description="身份标签，如 user:123、role:5")
    permission_level: int = Field(..., description="权限等级（应用层定义语义）")
    effect: str = Field("ALLOW", pattern="^(ALLOW|DENY)$", description="效果：ALLOW 或 DENY")
    inherit: bool = Field(True, description="是否向子资源传播")
    dept_scope: Optional[str] = Field(None, max_length=20, description="部门范围（仅 subject_type=dept 时有意义；省略为 null）")


class UpdateRuleRequest(BaseModel):
    rule_id: int = Field(..., description="规则ID")
    permission_level: Optional[int] = Field(None, description="权限等级")
    effect: Optional[str] = Field(None, pattern="^(ALLOW|DENY)$", description="效果")
    inherit: Optional[bool] = Field(None, description="是否向子资源传播")
    dept_scope: Optional[str] = Field(None, max_length=20, description="部门范围")


class DeleteRuleRequest(BaseModel):
    rule_id: int = Field(..., description="规则ID")
