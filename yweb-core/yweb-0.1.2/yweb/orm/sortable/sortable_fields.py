"""排序字段定义

提供标准的排序字段定义 Mixin，简化模型定义。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.sortable import SortFieldMixin, SortableMixin
    
    class Banner(BaseModel, SortFieldMixin, SortableMixin):
        __tablename__ = "banner"
        
        title = mapped_column(String(100))
        # sort_order 字段由 SortFieldMixin 自动提供
"""

from sqlalchemy import Integer
from sqlalchemy.orm import Mapped, mapped_column


class SortFieldMixin:
    """排序字段 Mixin
    
    提供标准的 sort_order 字段定义。
    
    字段说明:
        - sort_order: 排序序号，默认为0，值越小越靠前
    
    使用示例:
        class Banner(BaseModel, SortFieldMixin, SortableMixin):
            __tablename__ = "banner"
            title: Mapped[str]
        
        # 查询时按排序字段排序
        Banner.query.order_by(Banner.sort_order).all()
    """
    
    # 排序序号，值越小越靠前
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="排序序号"
    )


__all__ = [
    "SortFieldMixin",
]
