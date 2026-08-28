"""
ACL 模块 - FastAPI 依赖

提供 get_acl_service、get_current_identities、require_acl 等 FastAPI 依赖。

前置条件：
1. 应用层通过 init_acl_dependency() 完成配置
2. IdentityProvider 和 get_current_user_func 均已注册
"""

from typing import Any, Callable, Optional

from .exceptions import AclException, AclPermissionDenied

_acl_service = None
_identity_provider = None
_get_current_user_func: Optional[Callable] = None


def init_acl_dependency(
    acl_service=None,
    identity_provider=None,
    get_current_user_func: Optional[Callable] = None,
):
    """初始化 ACL 依赖

    Args:
        acl_service: AclService 实例
        identity_provider: IdentityProvider 实例（可选，require_acl 时需要）
        get_current_user_func: 获取当前用户的回调（可选，从 auth 模块传入）
    """
    global _acl_service, _identity_provider, _get_current_user_func
    if acl_service is not None:
        _acl_service = acl_service
    if identity_provider is not None:
        _identity_provider = identity_provider
    if get_current_user_func is not None:
        _get_current_user_func = get_current_user_func


def get_acl_service():
    """获取全局 AclService 实例"""
    if _acl_service is None:
        raise AclException("AclService not configured. Call setup_acl() first.")
    return _acl_service


def get_identity_provider():
    """获取 IdentityProvider 实例"""
    if _identity_provider is None:
        raise AclException(
            "IdentityProvider not configured. "
            "Call setup_acl(identity_provider=...) or "
            "acl.init_dependency(identity_provider=...) first."
        )
    return _identity_provider


def resolve_identities(user: Any) -> set[str]:
    """将用户对象转换为身份标签集合

    Args:
        user: 用户对象

    Returns:
        身份标签集合
    """
    provider = get_identity_provider()
    return provider.get_identities(user)


def get_current_identities() -> set[str]:
    """FastAPI 依赖——从请求上下文获取当前用户的身份标签集合

    内部流程：get_current_user_func() → IdentityProvider.get_identities(user)

    前置条件：
    1. IdentityProvider 已配置
    2. get_current_user_func 已配置

    使用示例::

        from fastapi import Depends
        from yweb.acl import get_current_identities

        @app.get("/docs/{doc_id}")
        def get_doc(
            doc_id: int,
            identities: set[str] = Depends(get_current_identities),
        ):
            acl_service.check(identities, "DOCUMENT", str(doc_id), 10)
    """
    if _get_current_user_func is None:
        raise AclException(
            "get_current_user_func not configured. "
            "Call setup_acl(get_current_user_func=...) or "
            "init_acl_dependency(get_current_user_func=...) first."
        )

    user = _get_current_user_func()
    if user is None:
        raise AclPermissionDenied(message="未登录")

    return resolve_identities(user)


def resolve_identities_for_target(target_user_id: Optional[int] = None) -> set[str]:
    """解析目标用户的身份标签

    如果 target_user_id 为 None，尝试从 auth 模块获取当前用户。
    如果指定了 target_user_id，通过 get_current_user_func 查找该用户。

    此函数用于同步 (def) 路由中。
    """
    provider = get_identity_provider()

    if _get_current_user_func is None:
        raise AclException(
            "get_current_user_func not configured. "
            "Call init_acl_dependency(get_current_user_func=...) to enable "
            "automatic identity resolution in API endpoints."
        )

    user = _get_current_user_func(target_user_id)
    return provider.get_identities(user)


def require_acl(
    resource_type: str,
    required_level: int,
    resource_id_param: str = "resource_id",
):
    """FastAPI 依赖——检查当前请求的 ACL 权限

    Args:
        resource_type: 资源类型
        required_level: 所需权限等级
        resource_id_param: 从请求参数中提取 resource_id 的字段名

    使用示例::

        from yweb.acl import require_acl
        from fastapi import Depends

        class DocumentController(ResourceController):
            prefix = "/documents"
            dependencies = [Depends(require_acl("DOCUMENT", 30))]

            async def update(self, body: UpdateRequest):
                ...
    """
    from fastapi import Request

    async def _check_acl(request: Request):
        if _get_current_user_func is None:
            raise AclException(
                "get_current_user_func not configured for require_acl."
            )

        user = _get_current_user_func()
        if user is None:
            raise AclPermissionDenied(
                message="未登录",
                resource_type=resource_type,
                required_level=required_level,
            )

        identities = resolve_identities(user)

        resource_id = None
        if resource_id_param in request.path_params:
            resource_id = request.path_params[resource_id_param]
        elif resource_id_param in request.query_params:
            resource_id = request.query_params[resource_id_param]

        if resource_id is None:
            raise AclException(
                f"Cannot extract '{resource_id_param}' from request"
            )

        service = get_acl_service()
        if not service.check(identities, resource_type, resource_id, required_level):
            raise AclPermissionDenied(
                resource_type=resource_type,
                resource_id=resource_id,
                required_level=required_level,
            )

    return _check_acl


__all__ = [
    "init_acl_dependency",
    "get_acl_service",
    "get_identity_provider",
    "get_current_identities",
    "resolve_identities",
    "resolve_identities_for_target",
    "require_acl",
]
