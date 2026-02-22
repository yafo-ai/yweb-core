"""树形结构扩展模块

提供通用的树形结构支持，使用物化路径（Materialized Path）模式。

主要组件:
- TreeMixin: 树形操作方法 Mixin
- TreeFieldsMixin: 树形字段定义 Mixin
- 工具函数: 树形数据处理工具

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.tree import TreeMixin, TreeFieldsMixin
    
    # 方式1：自定义字段
    class Menu(BaseModel, TreeMixin):
        __tablename__ = "menu"
        
        parent_id = mapped_column(Integer, ForeignKey("menu.id"), nullable=True)
        path = mapped_column(String(500), nullable=True)
        level = mapped_column(Integer, default=1)
        sort_order = mapped_column(Integer, default=0)
        
        title = mapped_column(String(100))
    
    # 方式2：使用 TreeFieldsMixin 简化
    class Category(BaseModel, TreeFieldsMixin, TreeMixin):
        __tablename__ = "category"
        
        parent_id = mapped_column(Integer, ForeignKey("category.id"), nullable=True)
        # path, level, sort_order 由 TreeFieldsMixin 自动提供
        
        title = mapped_column(String(100))
    
    # 使用
    menu = Menu.get(1)
    children = menu.get_children()       # 获取直接子节点
    descendants = menu.get_descendants() # 获取所有子孙节点
    ancestors = menu.get_ancestors()     # 获取所有祖先节点
    menu.move_to(new_parent_id)          # 移动节点
    
    tree = Menu.get_tree_list()          # 获取嵌套树结构
"""

from .tree_mixin import TreeMixin
from .tree_fields import TreeFieldsMixin, TreeFieldsWithParentMixin
from .tree_utils import (
    build_tree_list,
    flatten_tree,
    find_node_in_tree,
    get_node_path,
    validate_no_circular_reference,
    calculate_tree_depth,
    filter_tree,
)

__all__ = [
    # Mixin 类
    "TreeMixin",
    "TreeFieldsMixin",
    "TreeFieldsWithParentMixin",
    
    # 工具函数
    "build_tree_list",
    "flatten_tree",
    "find_node_in_tree",
    "get_node_path",
    "validate_no_circular_reference",
    "calculate_tree_depth",
    "filter_tree",
]
