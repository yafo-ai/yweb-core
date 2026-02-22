"""状态历史记录

提供状态变更历史记录功能。

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.statemachine import (
        StateFieldMixin, 
        StateMachineMixin, 
        StateHistoryMixin,
        AbstractStateHistory,
    )
    
    # 定义历史记录模型
    class OrderStateHistory(AbstractStateHistory):
        __tablename__ = "order_state_history"
    
    # 定义业务模型
    class Order(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
        __tablename__ = "order"
        __state_history_model__ = OrderStateHistory
        
        # ... 状态机配置 ...
    
    # 使用
    order.transition_to(Order.Status.PAID, reason="用户支付")
    history = order.get_state_history()
"""

from datetime import datetime, timedelta
from typing import Optional, List, Type, TYPE_CHECKING, Any
from sqlalchemy import Integer, String, DateTime, Text
from sqlalchemy.orm import Mapped, mapped_column

if TYPE_CHECKING:
    from ..base_model import BaseModel


class AbstractStateHistory:
    """状态历史记录抽象模型
    
    记录状态变更的历史信息。
    
    字段说明:
        - target_id: 关联的记录ID
        - target_type: 关联的模型类型（可选，用于多模型共用历史表）
        - from_state: 源状态
        - to_state: 目标状态
        - changed_at: 变更时间
        - changed_by: 变更人ID
        - reason: 变更原因
        - context: 变更上下文（JSON）
    
    使用示例:
        from yweb.orm import BaseModel
        from yweb.orm.statemachine import AbstractStateHistory
        
        class OrderStateHistory(BaseModel, AbstractStateHistory):
            __tablename__ = "order_state_history"
    """
    
    # 关联的记录ID
    target_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="关联记录ID"
    )
    
    # 关联的模型类型（可选，用于多模型共用历史表）
    target_type: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        index=True,
        comment="关联模型类型"
    )
    
    # 源状态
    from_state: Mapped[str] = mapped_column(
        String(50),
        nullable=True,
        comment="源状态"
    )
    
    # 目标状态
    to_state: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="目标状态"
    )
    
    # 变更时间
    changed_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        index=True,
        comment="变更时间"
    )
    
    # 变更人ID
    changed_by: Mapped[int] = mapped_column(
        Integer,
        nullable=True,
        index=True,
        comment="变更人ID"
    )
    
    # 变更原因
    reason: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="变更原因"
    )
    
    # 变更上下文（JSON格式）
    context: Mapped[str] = mapped_column(
        Text,
        nullable=True,
        comment="变更上下文（JSON）"
    )


class StateHistoryMixin:
    """状态历史记录 Mixin
    
    需要配合 AbstractStateHistory 使用，自动记录每次状态变更。
    
    配置属性（子类可覆盖）:
        __state_history_model__: 历史记录模型类
        __track_state_changes__: bool = True  是否记录变更
    
    使用示例:
        class OrderStateHistory(BaseModel, AbstractStateHistory):
            __tablename__ = "order_state_history"
        
        class Order(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
            __tablename__ = "order"
            __state_history_model__ = OrderStateHistory
            
            # ... 状态机配置 ...
        
        # 转换时自动记录历史
        order.transition_to(Order.Status.PAID, reason="用户支付", changed_by=user_id)
        
        # 查询历史
        history = order.get_state_history()
        for record in history:
            print(f"{record.from_state} -> {record.to_state}")
    """
    
    # 历史记录模型类
    __state_history_model__: Type = None
    
    # 是否记录状态变更
    __track_state_changes__: bool = True
    
    def _get_history_model(self) -> Optional[Type]:
        """获取历史记录模型类"""
        model = getattr(self.__class__, '__state_history_model__', None)
        if model is None:
            return None
        
        # 如果是字符串，尝试从当前模块查找
        if isinstance(model, str):
            import sys
            # 尝试从当前模块的全局命名空间查找
            frame = sys._getframe(1)
            while frame:
                if model in frame.f_globals:
                    return frame.f_globals[model]
                frame = frame.f_back
            return None
        
        return model
    
    def _record_state_change(
        self,
        from_state: Any,
        to_state: Any,
        **context
    ) -> None:
        """记录状态变更
        
        Args:
            from_state: 源状态
            to_state: 目标状态
            **context: 上下文参数（可包含 reason, changed_by 等）
        """
        if not getattr(self.__class__, '__track_state_changes__', True):
            return
        
        history_model = self._get_history_model()
        if history_model is None:
            return
        
        # 必须有 ID 才能记录历史
        if not hasattr(self, 'id') or self.id is None:
            return
        
        # 获取状态值（处理枚举）
        from_value = from_state.value if hasattr(from_state, 'value') else str(from_state) if from_state else None
        to_value = to_state.value if hasattr(to_state, 'value') else str(to_state)
        
        # 创建历史记录
        record = history_model(
            target_id=self.id,
            target_type=self.__class__.__name__,
            from_state=from_value,
            to_state=to_value,
            changed_at=datetime.now(),
            changed_by=context.get('changed_by'),
            reason=context.get('reason'),
        )
        
        # 保存上下文
        extra_context = {k: v for k, v in context.items() 
                        if k not in ('changed_by', 'reason')}
        if extra_context:
            import json
            try:
                record.context = json.dumps(extra_context, default=str)
            except (TypeError, ValueError):
                pass
        
        # 保存记录
        if hasattr(record, 'save'):
            record.save()
    
    def get_state_history(
        self, 
        limit: int = None,
        order_desc: bool = True
    ) -> List:
        """获取状态变更历史
        
        Args:
            limit: 限制返回数量
            order_desc: 是否按时间降序（最新在前）
            
        Returns:
            历史记录列表
        """
        history_model = self._get_history_model()
        if history_model is None:
            return []
        
        query = history_model.query.filter_by(
            target_id=self.id,
            target_type=self.__class__.__name__
        )
        
        if order_desc:
            query = query.order_by(history_model.changed_at.desc())
        else:
            query = query.order_by(history_model.changed_at)
        
        if limit:
            query = query.limit(limit)
        
        return query.all()
    
    def get_last_state_change(self):
        """获取最近一次状态变更
        
        Returns:
            最近的历史记录，如果没有返回 None
        """
        history = self.get_state_history(limit=1)
        return history[0] if history else None
    
    def get_state_change_count(self) -> int:
        """获取状态变更次数
        
        Returns:
            变更次数
        """
        history_model = self._get_history_model()
        if history_model is None:
            return 0
        
        return history_model.query.filter_by(
            target_id=self.id,
            target_type=self.__class__.__name__
        ).count()
    
    def get_time_in_state(self, state: Any = None) -> Optional[timedelta]:
        """获取在某状态停留的时间
        
        Args:
            state: 要查询的状态，None 表示当前状态
            
        Returns:
            停留时间，如果无法计算返回 None
        """
        history_model = self._get_history_model()
        if history_model is None:
            return None
        
        if state is None:
            # 当前状态
            current_state = self.get_state()
            state_value = current_state.value if hasattr(current_state, 'value') else str(current_state)
            
            # 查找最近一次进入当前状态的记录
            record = history_model.query.filter_by(
                target_id=self.id,
                target_type=self.__class__.__name__,
                to_state=state_value
            ).order_by(history_model.changed_at.desc()).first()
            
            if record:
                return datetime.now() - record.changed_at
        else:
            # 指定状态
            state_value = state.value if hasattr(state, 'value') else str(state)
            
            # 查找进入和离开该状态的记录
            enter_record = history_model.query.filter_by(
                target_id=self.id,
                target_type=self.__class__.__name__,
                to_state=state_value
            ).order_by(history_model.changed_at.desc()).first()
            
            if not enter_record:
                return None
            
            exit_record = history_model.query.filter(
                history_model.target_id == self.id,
                history_model.target_type == self.__class__.__name__,
                history_model.from_state == state_value,
                history_model.changed_at > enter_record.changed_at
            ).order_by(history_model.changed_at).first()
            
            if exit_record:
                return exit_record.changed_at - enter_record.changed_at
            else:
                # 还在该状态
                return datetime.now() - enter_record.changed_at
        
        return None
    
    def get_states_timeline(self) -> List[dict]:
        """获取状态时间线
        
        Returns:
            状态时间线，格式为 [{"state": "...", "entered_at": ..., "exited_at": ..., "duration": ...}, ...]
        """
        history = self.get_state_history(order_desc=False)
        if not history:
            return []
        
        timeline = []
        for i, record in enumerate(history):
            entry = {
                "state": record.to_state,
                "entered_at": record.changed_at,
                "exited_at": None,
                "duration": None,
                "changed_by": record.changed_by,
                "reason": record.reason,
            }
            
            # 查找离开时间（下一条记录的时间）
            if i + 1 < len(history):
                entry["exited_at"] = history[i + 1].changed_at
                entry["duration"] = entry["exited_at"] - entry["entered_at"]
            else:
                # 最后一个状态，计算到现在的时间
                entry["duration"] = datetime.now() - entry["entered_at"]
            
            timeline.append(entry)
        
        return timeline


__all__ = [
    "AbstractStateHistory",
    "StateHistoryMixin",
]
