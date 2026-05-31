"""
ACL 模块 - 权限判定引擎

纯算法，只依赖 rule_model 和 resource_model（ORM 抽象模型）。
不认识 User、Department、Role——调用者负责将用户转为身份标签集合。
"""

from typing import Optional

from .enums import Effect


class AclEngine:
    """ACL 权限判定引擎

    入参全部是基本类型（set[str]、str、int），不引入任何外部模块。

    核心算法：
    1. 从目标资源沿树向上收集所有相关规则
    2. 按 DENY 优先 + 深度排序解析最终权限等级
    """

    def __init__(self, rule_model, resource_model):
        self._rule_model = rule_model
        self._resource_model = resource_model

    def check(
        self,
        identities: set[str],
        resource_type: str,
        resource_id: str,
        required_level: int,
    ) -> bool:
        """核心接口：这组身份对这个资源有没有指定等级的权限？"""
        return (
            self.get_effective_level(identities, resource_type, resource_id)
            >= required_level
        )

    def get_effective_level(
        self,
        identities: set[str],
        resource_type: str,
        resource_id: str,
    ) -> int:
        """计算有效权限等级"""
        rules = self._collect_rules(resource_type, resource_id)
        return self._resolve(rules, identities)

    def get_accessible(
        self,
        identities: set[str],
        resource_type: Optional[str] = None,
        min_level: int = 1,
    ) -> list[str]:
        """反向查询：这组身份能访问哪些资源（返回 resource_id 列表）

        算法：先按 subject_id 从规则表查出所有相关规则涉及的资源，
        再对每个资源计算有效权限等级，过滤出 >= min_level 的。
        """
        query = self._rule_model.query.filter(
            self._rule_model.subject_id.in_(identities),
            self._rule_model.deleted_at.is_(None),
        )
        if resource_type:
            query = query.filter(self._rule_model.resource_type == resource_type)

        rules = query.all()

        candidate_keys: set[tuple[str, str]] = set()
        for rule in rules:
            candidate_keys.add((rule.resource_type, rule.resource_id))

        if resource_type:
            inherited = self._find_inherited_resources(resource_type, identities)
            candidate_keys.update(inherited)

        result = []
        for rt, rid in candidate_keys:
            level = self.get_effective_level(identities, rt, rid)
            if level >= min_level:
                result.append(rid)

        return result

    def _find_inherited_resources(
        self, resource_type: str, identities: set[str]
    ) -> set[tuple[str, str]]:
        """查找通过继承获得权限的子资源"""
        inherited_rules = (
            self._rule_model.query.filter(
                self._rule_model.subject_id.in_(identities),
                self._rule_model.inherit.is_(True),
                self._rule_model.deleted_at.is_(None),
            )
            .all()
        )

        parent_keys = set()
        for rule in inherited_rules:
            parent_keys.add((rule.resource_type, rule.resource_id))

        result: set[tuple[str, str]] = set()
        for rt, rid in parent_keys:
            parent_resource = (
                self._resource_model.query.filter(
                    self._resource_model.resource_type == rt,
                    self._resource_model.resource_id == rid,
                    self._resource_model.deleted_at.is_(None),
                )
                .first()
            )
            if not parent_resource:
                continue

            descendants = parent_resource.get_descendants()
            for desc in descendants:
                if desc.resource_type == resource_type:
                    result.add((desc.resource_type, desc.resource_id))

        return result

    def _collect_rules(
        self, resource_type: str, resource_id: str
    ) -> list[tuple]:
        """从资源沿树向上遍历到根，收集所有 (rule, depth) 对

        depth=0 表示直接规则，depth>0 表示从祖先继承。
        遇到 inherit_parent=False 的节点就停止向上遍历。
        """
        resource_node = (
            self._resource_model.query.filter(
                self._resource_model.resource_type == resource_type,
                self._resource_model.resource_id == resource_id,
                self._resource_model.deleted_at.is_(None),
            )
            .first()
        )

        rules_with_depth: list[tuple] = []

        if resource_node is None:
            direct_rules = (
                self._rule_model.query.filter(
                    self._rule_model.resource_type == resource_type,
                    self._rule_model.resource_id == resource_id,
                    self._rule_model.deleted_at.is_(None),
                )
                .all()
            )
            for rule in direct_rules:
                rules_with_depth.append((rule, 0))
            return rules_with_depth

        current = resource_node
        depth = 0

        while current is not None:
            node_rules = (
                self._rule_model.query.filter(
                    self._rule_model.resource_type == current.resource_type,
                    self._rule_model.resource_id == current.resource_id,
                    self._rule_model.deleted_at.is_(None),
                )
                .all()
            )

            for rule in node_rules:
                if depth == 0:
                    rules_with_depth.append((rule, depth))
                elif rule.inherit:
                    rules_with_depth.append((rule, depth))

            depth += 1

            if current.parent_id is None:
                break

            parent = (
                self._resource_model.query.filter(
                    self._resource_model.id == current.parent_id,
                    self._resource_model.deleted_at.is_(None),
                )
                .first()
            )

            if parent is None:
                break
            if not current.inherit_parent and depth > 0:
                break

            current = parent

        return rules_with_depth

    def _resolve(self, rules: list[tuple], identities: set[str]) -> int:
        """DENY 优先 + 深度排序 → 最终等级

        算法：
        1. 过滤：只保留 subject_id 在 identities 中的规则
        2. DENY 命中 → 返回 0
        3. ALLOW 按深度升序排列（直接规则优先），取最高 permission_level
        """
        matched = []
        for rule, depth in rules:
            if rule.subject_id in identities:
                matched.append((rule, depth))

        for rule, _depth in matched:
            if rule.effect == Effect.DENY:
                return 0

        if not matched:
            return 0

        matched.sort(key=lambda x: x[1])

        max_level = 0
        for rule, _depth in matched:
            if rule.effect == Effect.ALLOW and rule.permission_level > max_level:
                max_level = rule.permission_level

        return max_level


__all__ = ["AclEngine"]
