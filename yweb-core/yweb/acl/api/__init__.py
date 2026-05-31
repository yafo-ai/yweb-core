"""
ACL 模块 - API 路由组装
"""

from fastapi import APIRouter

from .rule_controller import AclRuleController, init_rule_controller
from .resource_controller import AclResourceController, init_resource_controller
from .permission_controller import AclPermissionController, init_permission_controller


def create_acl_router(
    acl_service=None,
    tags: list = None,
    dependencies: list = None,
) -> APIRouter:
    """组装 ACL 模块的所有路由

    Args:
        acl_service: AclService 实例
        tags: OpenAPI 标签
        dependencies: 路由全局依赖

    Returns:
        包含所有 ACL 端点的 APIRouter
    """
    if acl_service is not None:
        init_rule_controller(acl_service)
        init_resource_controller(acl_service)
        init_permission_controller(acl_service)

    acl_router = APIRouter(tags=tags or ["ACL"])
    acl_router.include_router(AclRuleController.router)
    acl_router.include_router(AclResourceController.router)
    acl_router.include_router(AclPermissionController.router)
    return acl_router


__all__ = [
    "create_acl_router",
    "AclRuleController",
    "AclResourceController",
    "AclPermissionController",
]
