"""
ACL 模块 - AclService

在 AclEngine 之上提供业务操作门面：权限检查 + 规则 CRUD + 资源树管理。
"""

from typing import Any, Optional

from yweb.log import get_logger

from .engine import AclEngine
from .enums import Effect
from .exceptions import (
    AclDuplicateResource,
    AclResourceNotFound,
    AclRuleNotFound,
)

logger = get_logger("yweb.acl.service")


class AclService:
    """ACL 服务

    提供权限检查、规则 CRUD、资源树管理的统一门面。
    """

    def __init__(self, engine: AclEngine, rule_model, resource_model):
        self._engine = engine
        self._rule_model = rule_model
        self._resource_model = resource_model

    # ------------------------------------------------------------------
    # 权限检查（委托给 engine，透传 identities）
    # ------------------------------------------------------------------

    def check(
        self,
        identities: set[str],
        resource_type: str,
        resource_id: str,
        required_level: int,
    ) -> bool:
        """检查权限"""
        return self._engine.check(identities, resource_type, resource_id, required_level)

    def get_effective_level(
        self,
        identities: set[str],
        resource_type: str,
        resource_id: str,
    ) -> int:
        """获取有效权限等级"""
        return self._engine.get_effective_level(identities, resource_type, resource_id)

    def get_accessible(
        self,
        identities: set[str],
        resource_type: Optional[str] = None,
        min_level: int = 1,
    ) -> list[str]:
        """查询可访问资源列表"""
        return self._engine.get_accessible(identities, resource_type, min_level)

    def batch_check(
        self,
        identities: set[str],
        checks: list[dict],
    ) -> dict[str, bool]:
        """批量权限检查

        Args:
            identities: 身份标签集合
            checks: 检查列表，每项包含 resource_type, resource_id, required_level

        Returns:
            key 为 "{resource_type}:{resource_id}"，value 为是否有权限
        """
        result = {}
        for item in checks:
            rt = item["resource_type"]
            rid = item["resource_id"]
            level = item["required_level"]
            key = f"{rt}:{rid}"
            result[key] = self._engine.check(identities, rt, rid, level)
        return result

    # ------------------------------------------------------------------
    # 规则 CRUD
    # ------------------------------------------------------------------

    def create_rule(
        self,
        resource_type: str,
        resource_id: str,
        subject_id: str,
        permission_level: int,
        effect: str = "ALLOW",
        inherit: bool = True,
        **kwargs: Any,
    ):
        """创建 ACL 规则"""
        Effect(effect)

        rule = self._rule_model(
            resource_type=resource_type,
            resource_id=resource_id,
            subject_id=subject_id,
            permission_level=permission_level,
            effect=effect,
            inherit=inherit,
            subject_type=kwargs.get("subject_type", "user"),
            dept_scope=kwargs.get("dept_scope"),
            priority=kwargs.get("priority", 0),
            conditions=kwargs.get("conditions"),
        )
        rule.save(commit=True)
        logger.info(
            "ACL rule created: %s/%s → %s [%s %d]",
            resource_type, resource_id, subject_id, effect, permission_level,
        )
        return rule

    def update_rule(self, rule_id: Any, **kwargs: Any):
        """更新 ACL 规则"""
        rule = self._rule_model.get(rule_id)
        if not rule:
            raise AclRuleNotFound(rule_id)

        if "effect" in kwargs:
            Effect(kwargs["effect"])

        for key, value in kwargs.items():
            if hasattr(rule, key):
                setattr(rule, key, value)
        rule.save(commit=True)
        logger.info("ACL rule updated: id=%s", rule_id)
        return rule

    def delete_rule(self, rule_id: Any) -> bool:
        """删除 ACL 规则"""
        rule = self._rule_model.get(rule_id)
        if not rule:
            raise AclRuleNotFound(rule_id)
        rule.delete(commit=True)
        logger.info("ACL rule deleted: id=%s", rule_id)
        return True

    def get_rules_for_resource(
        self, resource_type: str, resource_id: str
    ) -> list:
        """查询资源的所有规则"""
        return (
            self._rule_model.query.filter(
                self._rule_model.resource_type == resource_type,
                self._rule_model.resource_id == resource_id,
                self._rule_model.deleted_at.is_(None),
            )
            .all()
        )

    def get_rules_for_subject(self, subject_id: str) -> list:
        """查询身份的所有规则"""
        return (
            self._rule_model.query.filter(
                self._rule_model.subject_id == subject_id,
                self._rule_model.deleted_at.is_(None),
            )
            .all()
        )

    # ------------------------------------------------------------------
    # 资源树管理
    # ------------------------------------------------------------------

    def get_resource(
        self, resource_type: str, resource_id: str
    ) -> Optional[Any]:
        """查询资源节点"""
        return (
            self._resource_model.query.filter(
                self._resource_model.resource_type == resource_type,
                self._resource_model.resource_id == resource_id,
                self._resource_model.deleted_at.is_(None),
            )
            .first()
        )

    def register_resource(
        self,
        resource_type: str,
        resource_id: str,
        display_name: str,
        parent_id: Optional[int] = None,
    ):
        """注册资源节点到 ACL 资源树"""
        existing = self.get_resource(resource_type, resource_id)
        if existing:
            raise AclDuplicateResource(resource_type, resource_id)

        resource = self._resource_model(
            resource_type=resource_type,
            resource_id=resource_id,
            display_name=display_name,
            parent_id=parent_id,
        )
        resource.save(commit=True)
        logger.info(
            "ACL resource registered: %s/%s [parent=%s]",
            resource_type, resource_id, parent_id,
        )
        return resource

    def unregister_resource(
        self, resource_type: str, resource_id: str
    ) -> bool:
        """注销资源节点"""
        resource = self.get_resource(resource_type, resource_id)
        if not resource:
            raise AclResourceNotFound(resource_type, resource_id)
        resource.delete(commit=True)
        logger.info("ACL resource unregistered: %s/%s", resource_type, resource_id)
        return True

    def set_inherit_parent(
        self, resource_type: str, resource_id: str, inherit: bool
    ):
        """设置资源节点是否继承父级规则"""
        resource = self.get_resource(resource_type, resource_id)
        if not resource:
            raise AclResourceNotFound(resource_type, resource_id)
        resource.inherit_parent = inherit
        resource.save(commit=True)
        logger.info(
            "ACL resource inherit_parent=%s: %s/%s",
            inherit, resource_type, resource_id,
        )
        return resource

    def get_resource_tree(
        self, resource_type: Optional[str] = None
    ) -> list[dict]:
        """获取资源树（嵌套结构）

        显式过滤 ``deleted_at IS NULL``，不依赖隐式软删除重写器，
        避免重写器被旁路（如 ``execution_options(include_deleted=True)``）
        时已删除的资源节点泄漏进树。
        """
        from yweb.orm.tree.tree_utils import build_tree_list

        resource_model = self._resource_model
        query = resource_model.query.filter(
            resource_model.deleted_at.is_(None),
        )
        if resource_type is not None:
            query = query.filter(resource_model.resource_type == resource_type)

        # 排序与 TreeMixin.get_tree_list 保持一致：level 优先，sort_order 可用则附加
        sort_field = getattr(resource_model, "sort_order", None)
        if sort_field is not None:
            query = query.order_by(resource_model.level, sort_field)
        else:
            query = query.order_by(resource_model.level)

        nodes = query.all()
        node_dicts = []
        for node in nodes:
            if hasattr(node, "to_dict"):
                node_dicts.append(node.to_dict())
            else:
                node_dicts.append({
                    "id": node.id,
                    "parent_id": node.parent_id,
                    "resource_type": node.resource_type,
                    "resource_id": node.resource_id,
                    "display_name": node.display_name,
                    "path": node.path,
                    "level": node.level,
                    "inherit_parent": node.inherit_parent,
                })
        return build_tree_list(node_dicts)


__all__ = ["AclService"]
