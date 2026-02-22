"""ORM扩展模块 - 软删除功能

提供完整的软删除解决方案：
- 自动查询过滤（自动排除已删除记录）
- 软删除/恢复方法
- 可配置的忽略表
- 支持execution_options禁用过滤
- 级联软删除

使用示例:
    from yweb.orm import fields, BaseModel
    
    class Department(BaseModel):
        name: Mapped[str] = mapped_column(String(100))
        # employees 由 backref 自动创建
    
    class Employee(BaseModel):
        name: Mapped[str] = mapped_column(String(50))
        # 多对一：部门删除时，员工的 dept_id 设为空
        department = fields.ManyToOne(Department, on_delete=fields.SET_NULL)
"""

from .soft_delete_ignored_table import IgnoredTable
from .soft_delete_rewriter import SoftDeleteRewriter
from .soft_delete_hook import (
    activate_soft_delete_hook,
    deactivate_soft_delete_hook,
    is_soft_delete_active,
)
from .soft_delete_mixin import (
    generate_soft_delete_mixin_class,
    SimpleSoftDeleteMixin,
)

# 级联软删除
from .cascade_soft_delete import (
    CascadeSoftDeleteManager,
    configure_cascade_soft_delete,
    get_cascade_manager,
    # 从 fields 模块导入的常量
    OnDelete,
    DELETE, SET_NULL, PROTECT, UNLINK, DO_NOTHING,
    SOFT_DELETE_CASCADE_KEY,
)

__all__ = [
    # 忽略表配置
    "IgnoredTable",
    # 查询重写器
    "SoftDeleteRewriter",
    # 钩子函数
    "activate_soft_delete_hook",
    "deactivate_soft_delete_hook",
    "is_soft_delete_active",
    # Mixin类
    "generate_soft_delete_mixin_class",
    "SimpleSoftDeleteMixin",
    # 级联软删除
    "CascadeSoftDeleteManager",
    "configure_cascade_soft_delete",
    "get_cascade_manager",
    # 级联类型常量
    "OnDelete",
    "DELETE", "SET_NULL", "PROTECT", "UNLINK", "DO_NOTHING",
    "SOFT_DELETE_CASCADE_KEY",
]
