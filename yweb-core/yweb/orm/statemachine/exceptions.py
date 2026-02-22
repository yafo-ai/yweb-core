"""状态机异常定义

提供状态机相关的异常类。
"""

from typing import Any, List


class StateMachineError(Exception):
    """状态机基础异常"""
    pass


class InvalidStateError(StateMachineError):
    """无效状态异常
    
    当尝试设置一个不在状态枚举中的状态值时抛出。
    
    Attributes:
        state: 无效的状态值
        valid_states: 有效的状态列表
    """
    
    def __init__(self, state: Any, valid_states: List[Any]):
        self.state = state
        self.valid_states = valid_states
        super().__init__(
            f"Invalid state '{state}'. Valid states: {valid_states}"
        )


class InvalidTransitionError(StateMachineError):
    """无效转换异常
    
    当尝试执行一个不允许的状态转换时抛出。
    
    Attributes:
        from_state: 源状态
        to_state: 目标状态
        allowed_transitions: 允许的转换目标列表
    """
    
    def __init__(
        self, 
        from_state: Any, 
        to_state: Any, 
        allowed_transitions: List[Any]
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.allowed_transitions = allowed_transitions
        super().__init__(
            f"Cannot transition from '{from_state}' to '{to_state}'. "
            f"Allowed transitions: {allowed_transitions}"
        )


class TransitionGuardError(StateMachineError):
    """转换守卫条件不满足异常
    
    当转换的守卫条件返回 False 时抛出。
    
    Attributes:
        from_state: 源状态
        to_state: 目标状态
        guard_name: 守卫方法名
        message: 可选的错误消息
    """
    
    def __init__(
        self, 
        from_state: Any, 
        to_state: Any, 
        guard_name: str,
        message: str = None
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.guard_name = guard_name
        
        msg = (
            f"Guard '{guard_name}' rejected transition "
            f"from '{from_state}' to '{to_state}'"
        )
        if message:
            msg += f": {message}"
        super().__init__(msg)


class TransitionBlockedError(StateMachineError):
    """转换被钩子阻止异常
    
    当 before_transition 钩子返回 False 时抛出。
    
    Attributes:
        from_state: 源状态
        to_state: 目标状态
        reason: 阻止原因
    """
    
    def __init__(
        self, 
        from_state: Any, 
        to_state: Any, 
        reason: str = None
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.reason = reason
        
        msg = f"Transition from '{from_state}' to '{to_state}' was blocked"
        if reason:
            msg += f": {reason}"
        super().__init__(msg)


class TransitionCallbackError(StateMachineError):
    """转换回调执行异常
    
    当转换过程中的钩子方法抛出异常时抛出。
    
    Attributes:
        from_state: 源状态
        to_state: 目标状态
        callback_name: 回调方法名
        original_error: 原始异常
    """
    
    def __init__(
        self, 
        from_state: Any, 
        to_state: Any, 
        callback_name: str,
        original_error: Exception
    ):
        self.from_state = from_state
        self.to_state = to_state
        self.callback_name = callback_name
        self.original_error = original_error
        super().__init__(
            f"Callback '{callback_name}' failed during transition "
            f"from '{from_state}' to '{to_state}': {original_error}"
        )


__all__ = [
    "StateMachineError",
    "InvalidStateError",
    "InvalidTransitionError",
    "TransitionGuardError",
    "TransitionBlockedError",
    "TransitionCallbackError",
]
