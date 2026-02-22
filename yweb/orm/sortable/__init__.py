"""排序管理模块

提供通用的排序功能支持。

导出:
    - SortFieldMixin: 排序字段 Mixin（提供 sort_order 字段）
    - SortableMixin: 排序管理 Mixin（提供排序操作方法）

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.sortable import SortFieldMixin, SortableMixin
    
    # 方式1：从 sortable 模块导入
    class Banner(BaseModel, SortFieldMixin, SortableMixin):
        __tablename__ = "banner"
        title = mapped_column(String(100))
    
    # 方式2：从 orm 模块直接导入（推荐）
    from yweb.orm import BaseModel, SortFieldMixin, SortableMixin
    
    class Banner(BaseModel, SortFieldMixin, SortableMixin):
        __tablename__ = "banner"
        title = mapped_column(String(100))
    
    # 使用排序方法
    banner = Banner.get(1)
    banner.move_up()          # 上移
    banner.move_down()        # 下移
    banner.move_to_top()      # 置顶
    banner.move_to_bottom()   # 置底
    banner.move_to(3)         # 移动到第3位
    
    # 批量重排序
    Banner.reorder([3, 1, 2])  # 按此顺序重新编号
"""

from .sortable_fields import SortFieldMixin
from .sortable_mixin import SortableMixin

__all__ = [
    "SortFieldMixin",
    "SortableMixin",
]
