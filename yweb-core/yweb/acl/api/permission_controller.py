"""
ACL 模块 - 权限检查 API

基于 ResourceController 的权限检查端点。
identities 由服务端通过 IdentityProvider 自动获取，前端无需感知。

前置条件：IdentityProvider + get_current_user_func 已配置。
"""

from typing import Optional

from fastapi import APIRouter

from yweb.controller import ResourceController, get
from yweb.response import Resp

from ..schemas import CheckRequest, BatchCheckRequest

def _resolve_identities(target_user_id: Optional[int] = None) -> set[str]:
    from ..dependencies import resolve_identities_for_target
    return resolve_identities_for_target(target_user_id)


class AclPermissionController(ResourceController):
    prefix = "/permission"
    tags = ["ACL 权限检查"]
    acl_service = None

    def _get_service(self):
        if self.acl_service is None:
            from ..dependencies import get_acl_service
            return get_acl_service()
        return self.acl_service

    def check(self, body: CheckRequest):
        """检查当前用户对某资源的权限"""
        service = self._get_service()
        identities = _resolve_identities(body.target_user_id)
        has_permission = service.check(
            identities,
            body.resource_type,
            body.resource_id,
            body.required_level,
        )
        return Resp.OK(data={
            "has_permission": has_permission,
            "resource_type": body.resource_type,
            "resource_id": body.resource_id,
            "required_level": body.required_level,
        })

    def batch(self, body: BatchCheckRequest):
        """批量检查当前用户对多个资源的权限"""
        service = self._get_service()
        identities = _resolve_identities(body.target_user_id)
        checks = [item.model_dump() for item in body.checks]
        result = service.batch_check(identities, checks)
        return Resp.OK(data=result)

    @get
    def accessible(
        self,
        resource_type: Optional[str] = None,
        min_level: int = 1,
        target_user_id: Optional[int] = None,
    ):
        """查询当前用户可访问的资源列表"""
        service = self._get_service()
        identities = _resolve_identities(target_user_id)
        resource_ids = service.get_accessible(identities, resource_type, min_level)
        return Resp.OK(data=resource_ids)


def create_permission_router(acl_service=None) -> APIRouter:
    return AclPermissionController.create_router(acl_service=acl_service)
