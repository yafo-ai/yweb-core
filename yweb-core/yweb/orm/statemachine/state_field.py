"""状态字段定义

提供标准的状态字段定义 Mixin。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.statemachine import StateFieldMixin, StateMachineMixin
    
    class Order(BaseModel, StateFieldMixin, StateMachineMixin):
        __tablename__ = "order"
        # state 字段由 StateFieldMixin 自动提供
"""

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column


class StateFieldMixin:
    """状态字段 Mixin
    
    提供标准的 state 字段定义。
    
    字段说明:
        - state: 状态字段，字符串类型，最大50字符，带索引
    
    使用示例:
        class Order(BaseModel, StateFieldMixin, StateMachineMixin):
            __tablename__ = "order"
            
            class Status(str, Enum):
                PENDING = "pending"
                PAID = "paid"
            
            __state_enum__ = Status
            __state_initial__ = Status.PENDING
        
        # 查询时按状态过滤
        Order.query.filter_by(state="pending").all()
    
    注意:
        - 如果使用 IntEnum，请自行定义整数类型的状态字段
        - 此 Mixin 提供的是字符串类型字段，适用于 str Enum
    """
    
    # 状态字段
    state: Mapped[str] = mapped_column(
        String(50),
        default="initial",
        nullable=False,
        index=True,
        comment="状态"
    )


class IntStateFieldMixin:
    """整数状态字段 Mixin
    
    提供整数类型的状态字段，适用于 IntEnum。
    
    使用示例:
        from enum import IntEnum
        
        class EmployeeStatus(IntEnum):
            ACTIVE = 1
            RESIGNED = 2
        
        class Employee(BaseModel, IntStateFieldMixin, StateMachineMixin):
            __tablename__ = "employee"
            __state_field__ = "status"  # 使用 status 字段名
            __state_enum__ = EmployeeStatus
    """
    from sqlalchemy import Integer
    
    status: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="状态"
    )


__all__ = [
    "StateFieldMixin",
    "IntStateFieldMixin",
]
