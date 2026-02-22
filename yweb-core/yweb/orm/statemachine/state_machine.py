"""状态机 Mixin

提供通用的状态机功能，支持状态转换验证、钩子回调等。

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
    
    # 使用
    order = Order()
    order.transition_to(Order.Status.PAID)
"""

from typing import Any, Dict, List, Optional, Type, Union, TYPE_CHECKING
from enum import Enum
import re

from .exceptions import (
    InvalidStateError,
    InvalidTransitionError,
    TransitionGuardError,
    TransitionBlockedError,
    TransitionCallbackError,
)

if TYPE_CHECKING:
    pass


def _normalize_state_name(state: Any) -> str:
    """将状态值规范化为方法名格式
    
    例如:
        Status.PENDING -> "pending"
        "PENDING" -> "pending"
        1 -> "1"
    """
    if isinstance(state, Enum):
        return state.name.lower()
    return str(state).lower()


class StateMachineMixin:
    """状态机 Mixin
    
    为模型提供状态机功能，包括状态转换验证、钩子回调等。
    
    配置属性（子类可覆盖）:
        __state_field__: str = "state"
            状态字段名
        
        __state_transitions__: Dict[Any, List[Any]] = {}
            状态转换规则，key 为源状态，value 为允许的目标状态列表
        
        __state_initial__: Any = None
            初始状态
        
        __state_enum__: Type[Enum] = None
            状态枚举类
        
        __strict_transitions__: bool = True
            是否严格验证转换（False 时允许任意转换）
    
    钩子方法命名约定:
        on_enter_{state}(**context)     进入状态时触发
        on_exit_{state}(**context)      离开状态时触发
        on_transition_{from}_{to}(**context)  特定转换时触发
        guard_can_{state}() -> bool     转换守卫条件
    
    使用示例:
        class Order(BaseModel, StateFieldMixin, StateMachineMixin):
            class Status(str, Enum):
                PENDING = "pending"
                PAID = "paid"
            
            __state_enum__ = Status
            __state_initial__ = Status.PENDING
            __state_transitions__ = {
                Status.PENDING: [Status.PAID],
                Status.PAID: [],
            }
            
            def on_enter_paid(self, **context):
                self.paid_at = datetime.now()
        
        order = Order()
        order.transition_to(Order.Status.PAID)
    """
    
    # ==================== 配置 ====================
    
    # 状态字段名（子类可覆盖）
    __state_field__: str = "state"
    
    # 状态转换规则
    # 格式: {源状态: [目标状态1, 目标状态2, ...]}
    __state_transitions__: Dict[Any, List[Any]] = {}
    
    # 初始状态
    __state_initial__: Any = None
    
    # 状态枚举类
    __state_enum__: Type[Enum] = None
    
    # 是否严格验证转换
    __strict_transitions__: bool = True
    
    # ==================== 内部方法 ====================
    
    def _get_state_field_name(self) -> str:
        """获取状态字段名"""
        return getattr(self.__class__, '__state_field__', 'state')
    
    def _get_state_enum(self) -> Optional[Type[Enum]]:
        """获取状态枚举类"""
        return getattr(self.__class__, '__state_enum__', None)
    
    def _get_transitions_map(self) -> Dict[Any, List[Any]]:
        """获取状态转换映射"""
        return getattr(self.__class__, '__state_transitions__', {})
    
    def _normalize_state(self, state: Any) -> Any:
        """规范化状态值
        
        如果配置了枚举类，将值转换为枚举成员。
        """
        state_enum = self._get_state_enum()
        if state_enum is None:
            return state
        
        # 已经是枚举成员
        if isinstance(state, state_enum):
            return state
        
        # 尝试从值转换
        try:
            return state_enum(state)
        except ValueError:
            pass
        
        # 尝试从名称转换
        if isinstance(state, str):
            try:
                return state_enum[state.upper()]
            except KeyError:
                pass
        
        return state
    
    def _get_state_value(self, state: Any) -> Any:
        """获取状态的存储值
        
        如果是枚举，返回其 value；否则直接返回。
        """
        if isinstance(state, Enum):
            return state.value
        return state
    
    def _call_hook(
        self, 
        hook_name: str, 
        **context
    ) -> Optional[bool]:
        """调用钩子方法
        
        Args:
            hook_name: 钩子方法名
            **context: 传递给钩子的上下文参数
            
        Returns:
            钩子返回值，如果钩子不存在返回 None
        """
        hook = getattr(self, hook_name, None)
        if hook is not None and callable(hook):
            return hook(**context)
        return None
    
    def _call_guard(
        self, 
        to_state: Any
    ) -> bool:
        """调用守卫方法
        
        Args:
            to_state: 目标状态
            
        Returns:
            守卫是否通过
        """
        state_name = _normalize_state_name(to_state)
        guard_name = f"guard_can_{state_name}"
        
        guard = getattr(self, guard_name, None)
        if guard is not None and callable(guard):
            return bool(guard())
        
        return True
    
    # ==================== 核心方法 ====================
    
    def get_state(self) -> Any:
        """获取当前状态
        
        Returns:
            当前状态（如果配置了枚举，返回枚举成员）
            
        Example:
            order = Order.get(1)
            print(order.get_state())  # Status.PENDING
        """
        field_name = self._get_state_field_name()
        raw_value = getattr(self, field_name, None)
        return self._normalize_state(raw_value)
    
    def set_state(self, new_state: Any) -> None:
        """直接设置状态（跳过验证，内部使用）
        
        Args:
            new_state: 新状态
        """
        field_name = self._get_state_field_name()
        value = self._get_state_value(new_state)
        setattr(self, field_name, value)
    
    def transition_to(
        self, 
        new_state: Any, 
        *,
        force: bool = False,
        save: bool = False,
        raise_on_error: bool = True,
        **context
    ) -> bool:
        """执行状态转换
        
        Args:
            new_state: 目标状态
            force: 是否强制转换（跳过转换规则验证）
            save: 是否自动保存（调用 self.save()）
            raise_on_error: 转换失败时是否抛出异常
            **context: 传递给钩子的上下文参数
            
        Returns:
            是否转换成功
            
        Raises:
            InvalidStateError: 无效的状态值
            InvalidTransitionError: 转换不合法
            TransitionGuardError: 守卫条件不满足
            TransitionBlockedError: 被 before_transition 阻止
            TransitionCallbackError: 钩子执行失败
            
        Example:
            order = Order.get(1)
            
            # 基本转换
            order.transition_to(Order.Status.PAID)
            
            # 强制转换（跳过验证）
            order.transition_to(Order.Status.CANCELLED, force=True)
            
            # 自动保存
            order.transition_to(Order.Status.SHIPPED, save=True)
            
            # 传递上下文
            order.transition_to(Order.Status.CANCELLED, reason="用户取消")
        """
        # 规范化状态
        new_state = self._normalize_state(new_state)
        current_state = self.get_state()
        
        # 验证目标状态有效性
        state_enum = self._get_state_enum()
        if state_enum is not None and not isinstance(new_state, state_enum):
            if raise_on_error:
                raise InvalidStateError(new_state, list(state_enum))
            return False
        
        # 如果状态相同，不执行转换
        if current_state == new_state:
            return True
        
        # 验证转换合法性（除非强制转换）
        if not force and self.__strict_transitions__:
            if not self.can_transition_to(new_state):
                if raise_on_error:
                    allowed = self.get_available_transitions()
                    raise InvalidTransitionError(current_state, new_state, allowed)
                return False
        
        # 检查守卫条件
        guard_name = f"guard_can_{_normalize_state_name(new_state)}"
        if not self._call_guard(new_state):
            if raise_on_error:
                raise TransitionGuardError(current_state, new_state, guard_name)
            return False
        
        # 调用 before_transition 钩子
        try:
            result = self.before_transition(current_state, new_state, **context)
            if result is False:
                if raise_on_error:
                    raise TransitionBlockedError(current_state, new_state)
                return False
        except TransitionBlockedError:
            raise
        except Exception as e:
            if raise_on_error:
                raise TransitionCallbackError(
                    current_state, new_state, "before_transition", e
                )
            return False
        
        # 调用 on_exit_{state} 钩子
        try:
            exit_hook = f"on_exit_{_normalize_state_name(current_state)}"
            self._call_hook(exit_hook, **context)
        except Exception as e:
            if raise_on_error:
                raise TransitionCallbackError(
                    current_state, new_state, exit_hook, e
                )
            return False
        
        # 执行状态变更
        old_state = current_state
        self.set_state(new_state)
        
        # 调用 on_enter_{state} 钩子
        try:
            enter_hook = f"on_enter_{_normalize_state_name(new_state)}"
            self._call_hook(enter_hook, **context)
        except Exception as e:
            # 回滚状态
            self.set_state(old_state)
            if raise_on_error:
                raise TransitionCallbackError(
                    old_state, new_state, enter_hook, e
                )
            return False
        
        # 调用 on_transition_{from}_{to} 钩子
        try:
            transition_hook = (
                f"on_transition_"
                f"{_normalize_state_name(old_state)}_"
                f"{_normalize_state_name(new_state)}"
            )
            self._call_hook(transition_hook, **context)
        except Exception as e:
            if raise_on_error:
                raise TransitionCallbackError(
                    old_state, new_state, transition_hook, e
                )
            # 不回滚，因为状态已变更且 on_enter 已执行
        
        # 调用 after_transition 钩子
        try:
            self.after_transition(old_state, new_state, **context)
        except Exception as e:
            if raise_on_error:
                raise TransitionCallbackError(
                    old_state, new_state, "after_transition", e
                )
            # 不回滚
        
        # 调用状态历史记录（如果启用了 StateHistoryMixin）
        if hasattr(self, '_record_state_change'):
            try:
                self._record_state_change(old_state, new_state, **context)
            except Exception:
                pass  # 历史记录失败不影响主流程
        
        # 自动保存
        if save and hasattr(self, 'save'):
            self.save()
        
        return True
    
    def can_transition_to(self, new_state: Any) -> bool:
        """检查是否可以转换到目标状态
        
        Args:
            new_state: 目标状态
            
        Returns:
            是否可以转换
            
        Example:
            order = Order.get(1)
            if order.can_transition_to(Order.Status.SHIPPED):
                order.transition_to(Order.Status.SHIPPED)
        """
        new_state = self._normalize_state(new_state)
        current_state = self.get_state()
        
        # 相同状态视为可转换
        if current_state == new_state:
            return True
        
        # 非严格模式允许任意转换
        if not self.__strict_transitions__:
            return True
        
        # 检查转换规则
        transitions = self._get_transitions_map()
        allowed = transitions.get(current_state, [])
        
        return new_state in allowed
    
    def get_available_transitions(self) -> List[Any]:
        """获取当前状态可用的转换目标
        
        Returns:
            可转换到的状态列表
            
        Example:
            order = Order.get(1)
            available = order.get_available_transitions()
            print(f"可转换到: {available}")
        """
        current_state = self.get_state()
        transitions = self._get_transitions_map()
        return list(transitions.get(current_state, []))
    
    # ==================== 状态查询 ====================
    
    def is_state(self, state: Any) -> bool:
        """判断是否为指定状态
        
        Args:
            state: 要判断的状态
            
        Returns:
            是否为该状态
            
        Example:
            if order.is_state(Order.Status.PENDING):
                print("订单待支付")
        """
        state = self._normalize_state(state)
        return self.get_state() == state
    
    def is_any_state(self, *states) -> bool:
        """判断是否为指定状态之一
        
        Args:
            *states: 要判断的状态列表
            
        Returns:
            是否为其中之一
            
        Example:
            if order.is_any_state(Order.Status.COMPLETED, Order.Status.CANCELLED):
                print("订单已结束")
        """
        current = self.get_state()
        return any(self._normalize_state(s) == current for s in states)
    
    def is_terminal_state(self) -> bool:
        """判断是否为终态（无法再转换的状态）
        
        Returns:
            是否为终态
        """
        return len(self.get_available_transitions()) == 0
    
    def is_initial_state(self) -> bool:
        """判断是否为初始状态
        
        Returns:
            是否为初始状态
        """
        initial = getattr(self.__class__, '__state_initial__', None)
        if initial is None:
            return False
        return self.get_state() == self._normalize_state(initial)
    
    # ==================== 钩子方法（子类可覆盖）====================
    
    def before_transition(
        self, 
        from_state: Any, 
        to_state: Any, 
        **context
    ) -> bool:
        """转换前钩子
        
        在状态转换前调用，返回 False 可阻止转换。
        
        Args:
            from_state: 源状态
            to_state: 目标状态
            **context: 上下文参数
            
        Returns:
            是否允许转换
        """
        return True
    
    def after_transition(
        self, 
        from_state: Any, 
        to_state: Any, 
        **context
    ) -> None:
        """转换后钩子
        
        在状态转换完成后调用。
        
        Args:
            from_state: 源状态
            to_state: 目标状态
            **context: 上下文参数
        """
        pass
    
    def on_transition_error(
        self, 
        from_state: Any, 
        to_state: Any, 
        error: Exception,
        **context
    ) -> None:
        """转换失败钩子
        
        当转换过程中发生异常时调用。
        
        Args:
            from_state: 源状态
            to_state: 目标状态
            error: 发生的异常
            **context: 上下文参数
        """
        pass
    
    # ==================== 初始化方法 ====================
    
    def init_state(self) -> None:
        """初始化状态为初始状态
        
        在创建新记录时调用，设置为配置的初始状态。
        
        Example:
            order = Order(total=100)
            order.init_state()  # 设置为 PENDING
            order.save()
        """
        initial = getattr(self.__class__, '__state_initial__', None)
        if initial is not None:
            self.set_state(initial)
    
    # ==================== 类方法 ====================
    
    @classmethod
    def get_all_states(cls) -> List[Any]:
        """获取所有状态
        
        Returns:
            所有状态列表
        """
        state_enum = getattr(cls, '__state_enum__', None)
        if state_enum is not None:
            return list(state_enum)
        
        transitions = getattr(cls, '__state_transitions__', {})
        states = set(transitions.keys())
        for targets in transitions.values():
            states.update(targets)
        return list(states)
    
    @classmethod
    def get_terminal_states(cls) -> List[Any]:
        """获取所有终态
        
        Returns:
            终态列表（没有出边的状态）
        """
        transitions = getattr(cls, '__state_transitions__', {})
        return [state for state, targets in transitions.items() if not targets]
    
    @classmethod
    def get_initial_states(cls) -> List[Any]:
        """获取所有初始状态
        
        Returns:
            初始状态列表（没有入边的状态）
        """
        transitions = getattr(cls, '__state_transitions__', {})
        
        # 收集所有作为目标的状态
        target_states = set()
        for targets in transitions.values():
            target_states.update(targets)
        
        # 找出不在目标中的状态
        all_states = set(transitions.keys())
        return [state for state in all_states if state not in target_states]
    
    @classmethod
    def get_transitions_map(cls) -> Dict[Any, List[Any]]:
        """获取状态转换映射
        
        Returns:
            转换映射字典
        """
        return getattr(cls, '__state_transitions__', {})
    
    @classmethod
    def find_by_state(cls, state: Any, limit: int = None):
        """按状态查询记录
        
        Args:
            state: 状态值
            limit: 限制返回数量
            
        Returns:
            记录列表
        """
        field_name = getattr(cls, '__state_field__', 'state')
        state_enum = getattr(cls, '__state_enum__', None)
        
        # 获取存储值
        if state_enum is not None and isinstance(state, state_enum):
            query_value = state.value
        elif isinstance(state, Enum):
            query_value = state.value
        else:
            query_value = state
        
        query = cls.query.filter(getattr(cls, field_name) == query_value)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    @classmethod
    def count_by_state(cls, state: Any) -> int:
        """按状态统计记录数
        
        Args:
            state: 状态值
            
        Returns:
            记录数量
        """
        field_name = getattr(cls, '__state_field__', 'state')
        state_enum = getattr(cls, '__state_enum__', None)
        
        # 获取存储值
        if state_enum is not None and isinstance(state, state_enum):
            query_value = state.value
        elif isinstance(state, Enum):
            query_value = state.value
        else:
            query_value = state
        
        return cls.query.filter(getattr(cls, field_name) == query_value).count()
    
    @classmethod
    def count_by_states(cls) -> Dict[Any, int]:
        """统计各状态的记录数
        
        Returns:
            状态到数量的映射
        """
        result = {}
        for state in cls.get_all_states():
            result[state] = cls.count_by_state(state)
        return result


__all__ = [
    "StateMachineMixin",
]
