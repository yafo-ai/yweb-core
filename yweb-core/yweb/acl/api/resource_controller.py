"""
ACL 模块 - 资源树管理 API

基于 ResourceController 的 ACL 资源树管理端点。
"""

from typing import Optional

from fastapi import APIRouter

from yweb.controller import ResourceController, get
from yweb.response import Resp

from ..schemas import RegisterResourceRequest, InheritRequest

class AclResourceController(ResourceController):
    prefix = "/resources"
    tags = ["ACL 资源树"]
    acl_service = None

    def _get_service(self):
        if self.acl_service is None:
            from ..dependencies import get_acl_service
            return get_acl_service()
        return self.acl_service

    @get
    def tree(self, resource_type: Optional[str] = None):
        """获取资源树"""
        service = self._get_service()
        tree = service.get_resource_tree(resource_type)
        return Resp.OK(data=tree)

    def register(self, body: RegisterResourceRequest):
        """注册资源节点"""
        service = self._get_service()
        resource = service.register_resource(
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            display_name=body.display_name,
            parent_id=body.parent_id,
        )
        return Resp.OK(data=resource.to_dict())

    def inherit(self, body: InheritRequest):
        """设置继承开关"""
        service = self._get_service()
        resource = service.set_inherit_parent(
            resource_type=body.resource_type,
            resource_id=body.resource_id,
            inherit=body.inherit_parent,
        )
        return Resp.OK(data=resource.to_dict())


def create_resource_router(acl_service=None) -> APIRouter:
    return AclResourceController.create_router(acl_service=acl_service)
