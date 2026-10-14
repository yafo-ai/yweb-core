"""
ACL 模块 - ACL 规则抽象模型

定义 ACL 规则的字段结构。引擎通过 (resource_type, resource_id) 定位资源，
通过 subject_id 匹配身份标签，effect 区分 ALLOW/DENY。

字段 subject_type 和 dept_scope 为辅助字段（方便查询/UI），引擎不使用。
"""

from sqlalchemy import String, Integer, Boolean, Index, JSON
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import CoreModel


class AbstractAclRule(CoreModel):
    """ACL 规则抽象模型

    继承 CoreModel（id + created_at/updated_at/deleted_at/ver）。

    应用层不直接使用，由 setup_acl() 动态生成具体子类。
    """

    __abstract__ = True

    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="资源类型（应用层定义）"
    )
    resource_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="业务资源ID"
    )
    subject_type: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user",
        comment="主体类型（应用层定义，如 user/dept/role/everyone）",
    )
    subject_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="身份标签（如 user:123, dept:456）"
    )
    permission_level: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="权限等级（应用层定义语义）"
    )
    effect: Mapped[str] = mapped_column(
        String(10), nullable=False, default="ALLOW",
        comment="规则效果：ALLOW / DENY",
    )
    inherit: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="此规则是否向子资源传播",
    )
    dept_scope: Mapped[str] = mapped_column(
        String(20), nullable=True, default=None,
        comment="部门范围（应用层定义，仅 subject_type=dept 时有意义）",
    )
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, comment="优先级（预留，v1 不使用）"
    )
    conditions: Mapped[dict] = mapped_column(
        JSON, nullable=True, default=None, comment="扩展条件（预留，v1 不使用）"
    )

    @classmethod
    def __declare_last__(cls):
        if cls.__abstract__:
            return
        table = cls.__table__
        Index(
            f"ix_{table.name}_resource",
            table.c.resource_type,
            table.c.resource_id,
        )
        Index(f"ix_{table.name}_subject", table.c.subject_id)
