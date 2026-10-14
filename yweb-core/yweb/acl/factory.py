"""
ACL 模块 - 工厂函数

提供动态模型创建、一站式设置等功能。

使用示例::

    from yweb.acl import setup_acl

    acl = setup_acl(app=app, table_prefix="sys_")

    # 访问模型
    AclRule = acl.AclRule
    AclResource = acl.AclResource

    # 获取服务
    service = acl.get_service()
    engine = acl.get_engine()
"""

import uuid
from dataclasses import dataclass, field
from typing import Type, Any, Optional

from .engine import AclEngine
from .service import AclService


@dataclass
class AclModels:
    """ACL 模型容器

    Attributes:
        AclRule: ACL 规则模型类
        AclResource: ACL 资源树模型类
    """
    AclRule: Type
    AclResource: Type

    _engine: Any = field(default=None, repr=False)
    _service: Any = field(default=None, repr=False)

    def get_engine(self) -> AclEngine:
        """获取 AclEngine 单例"""
        if self._engine is None:
            engine = AclEngine(self.AclRule, self.AclResource)
            object.__setattr__(self, "_engine", engine)
        return self._engine

    def get_service(self) -> AclService:
        """获取 AclService 单例"""
        if self._service is None:
            service = AclService(
                engine=self.get_engine(),
                rule_model=self.AclRule,
                resource_model=self.AclResource,
            )
            object.__setattr__(self, "_service", service)
        return self._service

    def mount_routes(
        self,
        app,
        prefix: str = "/acl",
        tags: list = None,
        dependencies: list = None,
    ):
        """挂载 ACL 管理路由到 FastAPI 应用"""
        from .api import create_acl_router

        router = create_acl_router(
            acl_service=self.get_service(),
            tags=tags,
            dependencies=dependencies,
        )
        app.include_router(router, prefix=prefix)

    def init_dependency(self, identity_provider=None, get_current_user_func=None):
        """初始化 ACL 依赖注入

        Args:
            identity_provider: IdentityProvider 实例（可选，require_acl 时必传）
            get_current_user_func: 获取用户的回调（可选，权限检查端点需要）
        """
        from .dependencies import init_acl_dependency

        init_acl_dependency(
            acl_service=self.get_service(),
            identity_provider=identity_provider,
            get_current_user_func=get_current_user_func,
        )


def create_acl_models(
    table_prefix: str = "",
    rule_tablename: Optional[str] = None,
    resource_tablename: Optional[str] = None,
    rule_mixin: Optional[Type] = None,
    resource_mixin: Optional[Type] = None,
) -> AclModels:
    """创建 ACL 模型集合

    动态创建 AclRule 和 AclResource 模型类，返回 AclModels 容器。

    Args:
        table_prefix: 表名前缀（如 "sys_"）
        rule_tablename: 自定义规则表名（覆盖 table_prefix）
        resource_tablename: 自定义资源表名
        rule_mixin: 规则模型的 Mixin 扩展
        resource_mixin: 资源模型的 Mixin 扩展

    Returns:
        AclModels 容器
    """
    from .models import AbstractAclRule, AbstractAclResource

    suffix = uuid.uuid4().hex[:8]

    rule_table = rule_tablename or f"{table_prefix}acl_rule"
    resource_table = resource_tablename or f"{table_prefix}acl_resource"

    rule_bases = (
        (rule_mixin, AbstractAclRule) if rule_mixin else (AbstractAclRule,)
    )
    AclRule = type(
        f"AclRule_{suffix}",
        rule_bases,
        {
            "__tablename__": rule_table,
            "__module__": "yweb.acl.factory",
        },
    )

    resource_bases = (
        (resource_mixin, AbstractAclResource)
        if resource_mixin
        else (AbstractAclResource,)
    )
    AclResource = type(
        f"AclResource_{suffix}",
        resource_bases,
        {
            "__tablename__": resource_table,
            "__module__": "yweb.acl.factory",
        },
    )

    return AclModels(AclRule=AclRule, AclResource=AclResource)


def setup_acl(
    app=None,
    table_prefix: str = "",
    rule_mixin: Optional[Type] = None,
    resource_mixin: Optional[Type] = None,
    rule_tablename: Optional[str] = None,
    resource_tablename: Optional[str] = None,
    api_prefix: str = "/api/v1",
    acl_prefix: str = "/acl",
    tags: list = None,
    dependencies: list = None,
    identity_provider=None,
    get_current_user_func=None,
) -> AclModels:
    """一站式设置 ACL 模块

    创建模型、初始化依赖、挂载路由，一行代码完成全部配置。

    Args:
        app: FastAPI 应用实例（可选，传入时自动挂载路由）
        table_prefix: 表名前缀（如 "sys_"）
        rule_mixin: 规则模型的 Mixin 扩展
        resource_mixin: 资源模型的 Mixin 扩展
        rule_tablename: 自定义规则表名
        resource_tablename: 自定义资源表名
        api_prefix: API 全局路由前缀（默认 "/api/v1"）
        acl_prefix: ACL 模块路由前缀（默认 "/acl"）
        tags: OpenAPI 标签
        dependencies: 路由依赖
        identity_provider: IdentityProvider 实例（可选）
        get_current_user_func: 获取用户的回调（可选，权限检查端点需要）

    Returns:
        AclModels 容器

    使用示例::

        acl = setup_acl(app=app, table_prefix="sys_")
        service = acl.get_service()
    """
    acl = create_acl_models(
        table_prefix=table_prefix,
        rule_tablename=rule_tablename,
        resource_tablename=resource_tablename,
        rule_mixin=rule_mixin,
        resource_mixin=resource_mixin,
    )

    acl.init_dependency(
        identity_provider=identity_provider,
        get_current_user_func=get_current_user_func,
    )

    if app is not None:
        acl.mount_routes(
            app,
            prefix=f"{api_prefix}{acl_prefix}",
            tags=tags,
            dependencies=dependencies,
        )

    return acl


__all__ = [
    "AclModels",
    "create_acl_models",
    "setup_acl",
]
