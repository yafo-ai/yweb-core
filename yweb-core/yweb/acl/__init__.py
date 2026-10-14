"""
yweb ACL 模块

对象级权限（Access Control List）引擎。

核心设计：
- 引擎只认字符串和整数：入参是 identities: set[str] + required_level: int
- 仅依赖 yweb.orm：AbstractAclRule 和 AbstractAclResource 继承 CoreModel/TreeMixin
- 业务语义外置：权限等级、资源类型等枚举由应用层定义
- 集成逻辑外置：身份展开、API 路由中间件等由应用层自行组装

快速开始::

    from yweb.acl import setup_acl

    acl = setup_acl(app=app, table_prefix="sys_")
    service = acl.get_service()

    # 检查权限
    has_perm = service.check(identities, "DOCUMENT", "d001", required_level=10)
"""

from .enums import Effect
from .types import IdentitySet, IdentityProvider
from .exceptions import (
    AclException,
    AclPermissionDenied,
    AclResourceNotFound,
    AclRuleNotFound,
    AclDuplicateResource,
)
from .engine import AclEngine
from .service import AclService
from .factory import AclModels, create_acl_models, setup_acl
from .dependencies import (
    init_acl_dependency,
    get_acl_service,
    get_identity_provider,
    get_current_identities,
    resolve_identities,
    require_acl,
)


__all__ = [
    # 枚举
    "Effect",
    # 类型
    "IdentitySet",
    "IdentityProvider",
    # 异常
    "AclException",
    "AclPermissionDenied",
    "AclResourceNotFound",
    "AclRuleNotFound",
    "AclDuplicateResource",
    # 引擎
    "AclEngine",
    # 服务
    "AclService",
    # 工厂
    "AclModels",
    "create_acl_models",
    "setup_acl",
    # 依赖
    "init_acl_dependency",
    "get_acl_service",
    "get_identity_provider",
    "get_current_identities",
    "resolve_identities",
    "require_acl",
]
