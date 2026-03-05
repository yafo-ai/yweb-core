"""状态机模块

提供通用的状态机功能支持。

导出:
    - StateFieldMixin: 状态字段 Mixin（提供 state 字段）
    - IntStateFieldMixin: 整数状态字段 Mixin（提供 status 字段）
    - StateMachineMixin: 状态机 Mixin（提供状态转换方法）
    - 异常类

使用示例:
    from enum import Enum
    from yweb.orm import BaseModel
    from yweb.orm.statemachine import StateFieldMixin, StateMachineMixin
    
    class Order(BaseModel, StateFieldMixin, StateMachineMixin):
        __tablename__ = "order"
        
        class Status(str, Enum):
            PENDING = "pending"
            PAID = "paid"
            SHIPPED = "shipped"
            COMPLETED = "completed"
            CANCELLED = "cancelled"
        
        __state_enum__ = Status
        __state_initial__ = Status.PENDING
        __state_transitions__ = {
            Status.PENDING: [Status.PAID, Status.CANCELLED],
            Status.PAID: [Status.SHIPPED, Status.CANCELLED],
            Status.SHIPPED: [Status.COMPLETED],
            Status.COMPLETED: [],
            Status.CANCELLED: [],
        }
        
        # 钩子方法
        def on_enter_paid(self, **context):
            self.paid_at = datetime.now()
        
        def guard_can_shipped(self) -> bool:
            return self.address is not None
    
    # 使用
    order = Order()
    order.init_state()  # 设置初始状态
    order.transition_to(Order.Status.PAID)  # 状态转换
    
    # 查询
    print(order.get_state())  # Status.PAID
    print(order.can_transition_to(Order.Status.SHIPPED))  # True
    print(order.get_available_transitions())  # [Status.SHIPPED, Status.CANCELLED]
"""

from .exceptions import (
    StateMachineError,
    InvalidStateError,
    InvalidTransitionError,
    TransitionGuardError,
    TransitionBlockedError,
    TransitionCallbackError,
)
from .state_field import StateFieldMixin, IntStateFieldMixin
from .state_machine import StateMachineMixin
from .state_history import AbstractStateHistory, StateHistoryMixin

__all__ = [
    # 字段 Mixin
    "StateFieldMixin",
    "IntStateFieldMixin",
    
    # 状态机 Mixin
    "StateMachineMixin",
    
    # 状态历史 Mixin
    "AbstractStateHistory",
    "StateHistoryMixin",
    
    # 异常
    "StateMachineError",
    "InvalidStateError",
    "InvalidTransitionError",
    "TransitionGuardError",
    "TransitionBlockedError",
    "TransitionCallbackError",
]
