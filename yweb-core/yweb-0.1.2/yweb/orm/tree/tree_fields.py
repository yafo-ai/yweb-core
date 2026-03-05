"""树形结构字段定义

提供标准的树形字段定义 Mixin，简化模型定义。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.tree import TreeFieldsMixin, TreeMixin
    
    class Category(BaseModel, TreeFieldsMixin, TreeMixin):
        __tablename__ = "category"
        
        # parent_id 需要自行定义（因为外键目标表名不同）
        parent_id = mapped_column(Integer, ForeignKey("category.id"), nullable=True)
        
        # path, level, sort_order 由 TreeFieldsMixin 自动提供
        title = mapped_column(String(100))
"""

from typing import Optional
from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column

# 复用排序字段定义
from ..sortable import SortFieldMixin


class TreeFieldsMixin(SortFieldMixin):
    """树形结构字段 Mixin
    
    提供标准的树形字段定义，包括：
    - path: 节点路径（如 "/1/2/3/"）
    - level: 节点层级（根节点为1）
    - sort_order: 排序序号（继承自 SortFieldMixin）
    
    继承关系：
    - 继承自 SortFieldMixin，自动获得 sort_order 字段
    - 配合 SortableMixin 使用可获得完整排序操作能力
    
    注意：
    - parent_id 字段需要用户自行定义，因为外键目标表名因模型而异
    - 继承顺序：TreeFieldsMixin 应在 TreeMixin 之前
    
    使用示例:
        from yweb.orm import BaseModel, SortableMixin
        from yweb.orm.tree import TreeFieldsMixin, TreeMixin
        
        class Menu(BaseModel, TreeFieldsMixin, TreeMixin, SortableMixin):
            __tablename__ = "menu"
            __sort_group_by__ = "parent_id"  # 按父节点分组排序
            
            parent_id = mapped_column(Integer, ForeignKey("menu.id"), nullable=True)
            title = mapped_column(String(100))
        
        # 现在可以使用排序方法
        menu = Menu.get(1)
        menu.move_up()    # 在同级菜单中上移
        menu.move_down()  # 在同级菜单中下移
    """
    
    # 节点路径，格式如 "/1/2/3/"
    # 用于快速查询祖先/子孙节点
    path: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
        default=None,
        index=True,
        comment="节点路径（如 /1/2/3/）"
    )
    
    # 节点层级，根节点为 1
    # 用于快速判断深度和排序
    level: Mapped[int] = mapped_column(
        Integer,
        default=1,
        nullable=False,
        index=True,
        comment="节点层级（根节点为1）"
    )
    
    # sort_order 字段由 SortFieldMixin 自动提供（含索引）
    # 用于同级节点排序


class TreeFieldsWithParentMixin(TreeFieldsMixin):
    """带 parent_id 的树形字段 Mixin（自关联场景）
    
    包含 parent_id 字段，但不带外键约束。
    适用于简单场景，外键约束需要用户自行添加。
    
    注意：如果需要外键约束，建议使用 TreeFieldsMixin 并自行定义 parent_id。
    
    使用示例:
        from sqlalchemy import ForeignKey
        
        class SimpleTree(BaseModel, TreeFieldsWithParentMixin, TreeMixin):
            __tablename__ = "simple_tree"
            # 如需外键约束，需要在模型定义后手动添加
            # 或者覆盖 parent_id 字段
    """
    
    # 父节点 ID（不带外键约束）
    parent_id: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        default=None,
        index=True,
        comment="父节点ID"
    )


__all__ = [
    "TreeFieldsMixin",
    "TreeFieldsWithParentMixin",
]
