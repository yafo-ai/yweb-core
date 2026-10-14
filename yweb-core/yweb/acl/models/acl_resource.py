"""
ACL 模块 - ACL 资源树抽象模型

资源树节点，使用物化路径（Materialized Path）存储层级关系。
引擎通过 (resource_type, resource_id) 定位节点，沿 parent_id 向上遍历收集规则。

inherit_parent 控制此节点是否接收父级传播的规则：
- True（默认）：接收父级规则
- False：断开继承，只看自身的直接授权
"""

from typing import Optional

from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import CoreModel
from yweb.orm.tree import TreeFieldsMixin, TreeMixin


class AbstractAclResource(CoreModel, TreeFieldsMixin, TreeMixin):
    """ACL 资源树节点抽象模型

    继承 CoreModel + TreeFieldsMixin + TreeMixin。
    TreeFieldsMixin 提供 path/level/sort_order 字段。
    TreeMixin 提供树操作方法（get_children/get_ancestors/move_to 等）。

    parent_id 需要在具体子类中通过 __declare_last__ 建立外键。

    应用层不直接使用，由 setup_acl() 动态生成具体子类。
    """

    __abstract__ = True

    resource_type: Mapped[str] = mapped_column(
        String(50), nullable=False, comment="资源类型"
    )
    resource_id: Mapped[str] = mapped_column(
        String(256), nullable=False, comment="业务资源ID（与 AclRule.resource_id 同名同义）"
    )
    display_name: Mapped[str] = mapped_column(
        String(256), nullable=False, default="", comment="显示名称"
    )
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, default=None, index=True, comment="父节点ID"
    )
    inherit_parent: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True,
        comment="此节点是否接收父级传播的规则",
    )

    @classmethod
    def __declare_last__(cls):
        if cls.__abstract__:
            return
        table = cls.__table__
        UniqueConstraint(
            table.c.resource_type,
            table.c.resource_id,
            name=f"uq_{table.name}_type_id",
        )
