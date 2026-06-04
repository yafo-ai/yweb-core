"""
ACL 模块 - API 路由组装
"""

from fastapi import APIRouter

from .rule_controller import AclRuleController, create_rule_router
from .resource_controller import AclResourceController, create_resource_router
from .permission_controller import AclPermissionController, create_permission_router


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
    acl_router = APIRouter(tags=tags or ["ACL"])
    acl_router.include_router(create_rule_router(acl_service))
    acl_router.include_router(create_resource_router(acl_service))
    acl_router.include_router(create_permission_router(acl_service))
    return acl_router


__all__ = [
    "create_acl_router",
    "create_rule_router",
    "create_resource_router",
    "create_permission_router",
    "AclRuleController",
    "AclResourceController",
    "AclPermissionController",
]
