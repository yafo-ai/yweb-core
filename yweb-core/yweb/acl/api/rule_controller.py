"""
ACL 模块 - 规则管理 API

基于 ResourceController 的 ACL 规则 CRUD 端点。
"""

from yweb.controller import ResourceController, get
from yweb.response import Resp

from ..schemas import CreateRuleRequest, UpdateRuleRequest, DeleteRuleRequest

_acl_service = None


def _get_service():
    if _acl_service is None:
        from ..dependencies import get_acl_service
        return get_acl_service()
    return _acl_service


class AclRuleController(ResourceController):
    prefix = "/rules"
    tags = ["ACL 规则管理"]

    @get
    def list(self, resource_type: str, resource_id: str):
        """查询资源的规则列表"""
        service = _get_service()
        rules = service.get_rules_for_resource(resource_type, resource_id)
        return Resp.OK(data=[r.to_dict() for r in rules])

    def create(self, body: CreateRuleRequest):
        """创建 ACL 规则"""
        service = _get_service()
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

    def update(self, body: UpdateRuleRequest):
        """更新 ACL 规则"""
        service = _get_service()
        update_data = body.model_dump(exclude_none=True, exclude={"rule_id"})
        rule = service.update_rule(body.rule_id, **update_data)
        return Resp.OK(data=rule.to_dict())

    def delete(self, body: DeleteRuleRequest):
        """删除 ACL 规则"""
        service = _get_service()
        service.delete_rule(body.rule_id)
        return Resp.OK()


def init_rule_controller(acl_service):
    global _acl_service
    _acl_service = acl_service
