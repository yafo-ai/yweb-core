"""
ACL 模块 - 规则管理 API

基于 ResourceController 的 ACL 规则 CRUD 端点。
"""

from fastapi import APIRouter

from yweb.controller import ResourceController, get
from yweb.response import Resp

from ..schemas import (
    BatchCreateRuleRequest,
    CreateRuleRequest,
    DeleteRuleRequest,
    UpdateRuleRequest,
)

class AclRuleController(ResourceController):
    prefix = "/rules"
    tags = ["ACL 规则管理"]
    acl_service = None

    def _get_service(self):
        if self.acl_service is None:
            from ..dependencies import get_acl_service
            return get_acl_service()
        return self.acl_service

    @get
    def list(self, resource_type: str, resource_id: str):
        """查询资源的规则列表"""
        service = self._get_service()
        rules = service.get_rules_for_resource(resource_type, resource_id)
        return Resp.OK(data=[r.to_dict() for r in rules])

    def create(self, body: CreateRuleRequest):
        """创建 ACL 规则"""
        service = self._get_service()
        rule = service.create_rule(
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            subject_id=body.subject_id,
            permission_level=body.permission_level,
            effect=body.effect,
            inherit=body.inherit,
            subject_type=body.subject_type,
            dept_scope=body.dept_scope,
        )
        return Resp.OK(data=rule.to_dict())

    def create_batch(self, body: BatchCreateRuleRequest):
        """批量创建/更新 ACL 规则（同一主体写到多个资源；等级不同则更新现有规则）"""
        service = self._get_service()
        try:
            result = service.batch_create_rules(
                resources=[item.model_dump() for item in body.resources],
                subject_id=body.subject_id,
                permission_level=body.permission_level,
                effect=body.effect,
                inherit=body.inherit,
                subject_type=body.subject_type,
                dept_scope=body.dept_scope,
            )
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
        return Resp.OK(
            data={
                "created": [r.to_dict() for r in result["created"]],
                "updated": [r.to_dict() for r in result["updated"]],
                "skipped": result["skipped"],
            }
        )

    def update(self, body: UpdateRuleRequest):
        """更新 ACL 规则"""
        service = self._get_service()
        update_data = body.model_dump(exclude_none=True, exclude={"rule_id"})
        rule = service.update_rule(body.rule_id, **update_data)
        return Resp.OK(data=rule.to_dict())

    def delete(self, body: DeleteRuleRequest):
        """删除 ACL 规则"""
        service = self._get_service()
        service.delete_rule(body.rule_id)
        return Resp.OK()


def create_rule_router(acl_service=None) -> APIRouter:
    return AclRuleController.create_router(acl_service=acl_service)
