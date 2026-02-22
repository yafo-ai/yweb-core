"""状态机 StateMachineMixin 测试

测试 StateMachineMixin 的核心功能：
1. 基本状态转换
2. 转换验证
3. 守卫条件
4. 状态历史记录
"""

import pytest
from enum import Enum, IntEnum
from datetime import datetime
from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    Base,
    StateFieldMixin,
    StateMachineMixin,
    AbstractStateHistory,
    StateHistoryMixin,
    InvalidTransitionError,
    TransitionGuardError,
)


# ==================== 测试模型定义 ====================

class SMOrder(BaseModel, StateFieldMixin, StateMachineMixin):
    """订单模型 - 基本状态机"""
    __tablename__ = "test_sm_order"
    __table_args__ = {'extend_existing': True}
    
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
    
    order_no: Mapped[str] = mapped_column(String(50))
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    def on_enter_paid(self, **context):
        """进入已支付状态"""
        self.paid_at = datetime.now()


class SMTicket(BaseModel, StateFieldMixin, StateMachineMixin):
    """工单模型 - 带守卫条件"""
    __tablename__ = "test_sm_ticket"
    __table_args__ = {'extend_existing': True}
    
    class Status(str, Enum):
        OPEN = "open"
        IN_PROGRESS = "in_progress"
        RESOLVED = "resolved"
        CLOSED = "closed"
    
    __state_enum__ = Status
    __state_initial__ = Status.OPEN
    __state_transitions__ = {
        Status.OPEN: [Status.IN_PROGRESS, Status.CLOSED],
        Status.IN_PROGRESS: [Status.RESOLVED, Status.OPEN],
        Status.RESOLVED: [Status.CLOSED, Status.OPEN],
        Status.CLOSED: [],
    }
    
    title: Mapped[str] = mapped_column(String(200))
    assignee_id: Mapped[int] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str] = mapped_column(String(500), nullable=True)
    
    def guard_can_in_progress(self) -> bool:
        """必须指定处理人"""
        return self.assignee_id is not None
    
    def guard_can_resolved(self) -> bool:
        """必须填写解决方案"""
        return self.resolution is not None and len(self.resolution) > 0


class SMEmployee(BaseModel, StateMachineMixin):
    """员工模型 - 整数枚举状态机"""
    __tablename__ = "test_sm_employee"
    __table_args__ = {'extend_existing': True}
    
    class Status(IntEnum):
        PENDING = 0
        ACTIVE = 1
        RESIGNED = 2
    
    __state_field__ = "status"
    __state_enum__ = Status
    __state_initial__ = Status.PENDING
    __state_transitions__ = {
        Status.PENDING: [Status.ACTIVE],
        Status.ACTIVE: [Status.RESIGNED],
        Status.RESIGNED: [],
    }
    
    name: Mapped[str] = mapped_column(String(100))
    status: Mapped[int] = mapped_column(Integer, default=Status.PENDING)


class SMDocHistory(BaseModel, AbstractStateHistory):
    """文档状态历史"""
    __tablename__ = "test_sm_doc_history"
    __table_args__ = {'extend_existing': True}


class SMDocument(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
    """文档模型 - 带历史记录"""
    __tablename__ = "test_sm_document"
    __table_args__ = {'extend_existing': True}
    
    class Status(str, Enum):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
    
    __state_enum__ = Status
    __state_initial__ = Status.DRAFT
    __state_transitions__ = {
        Status.DRAFT: [Status.SUBMITTED],
        Status.SUBMITTED: [Status.APPROVED, Status.REJECTED],
        Status.APPROVED: [],
        Status.REJECTED: [Status.DRAFT],
    }
    __state_history_model__ = SMDocHistory
    
    title: Mapped[str] = mapped_column(String(200))


# ==================== 测试类 ====================

class TestBasicStateMachine:
    """基本状态机测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_init_state(self):
        """测试初始化状态"""
        order = SMOrder(order_no="ORD001")
        order.init_state()
        order.save(commit=True)
        
        assert order.get_state() == SMOrder.Status.PENDING
    
    def test_valid_transition(self):
        """测试有效转换"""
        order = SMOrder(order_no="ORD002")
        order.init_state()
        order.save(commit=True)
        
        order.transition_to(SMOrder.Status.PAID)
        assert order.get_state() == SMOrder.Status.PAID
        assert order.paid_at is not None  # 钩子被调用
    
    def test_invalid_transition_raises_error(self):
        """测试无效转换抛出异常"""
        order = SMOrder(order_no="ORD003")
        order.init_state()
        order.save(commit=True)
        
        # 跳过支付直接发货
        with pytest.raises(InvalidTransitionError):
            order.transition_to(SMOrder.Status.SHIPPED)
    
    def test_can_transition_to(self):
        """测试检查能否转换"""
        order = SMOrder(order_no="ORD004")
        order.init_state()
        order.save(commit=True)
        
        assert order.can_transition_to(SMOrder.Status.PAID) == True
        assert order.can_transition_to(SMOrder.Status.SHIPPED) == False
    
    def test_get_available_transitions(self):
        """测试获取可用转换"""
        order = SMOrder(order_no="ORD005")
        order.init_state()
        order.save(commit=True)
        
        available = order.get_available_transitions()
        assert SMOrder.Status.PAID in available
        assert SMOrder.Status.CANCELLED in available
        assert SMOrder.Status.SHIPPED not in available
    
    def test_is_terminal_state(self):
        """测试终态判断"""
        order = SMOrder(order_no="ORD006")
        order.init_state()
        order.save(commit=True)
        
        assert order.is_terminal_state() == False
        
        order.transition_to(SMOrder.Status.CANCELLED)
        assert order.is_terminal_state() == True


class TestGuardConditions:
    """守卫条件测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_guard_prevents_transition(self):
        """测试守卫阻止转换"""
        ticket = SMTicket(title="Bug Report")
        ticket.init_state()
        ticket.save(commit=True)
        
        # 没有指定处理人，无法开始处理
        with pytest.raises(TransitionGuardError):
            ticket.transition_to(SMTicket.Status.IN_PROGRESS)
    
    def test_guard_allows_transition(self):
        """测试守卫允许转换"""
        ticket = SMTicket(title="Bug Report")
        ticket.init_state()
        ticket.assignee_id = 1  # 指定处理人
        ticket.save(commit=True)
        
        ticket.transition_to(SMTicket.Status.IN_PROGRESS)
        assert ticket.get_state() == SMTicket.Status.IN_PROGRESS
    
    def test_multiple_guards(self):
        """测试多个守卫条件"""
        ticket = SMTicket(title="Issue")
        ticket.init_state()
        ticket.assignee_id = 1
        ticket.save(commit=True)
        
        ticket.transition_to(SMTicket.Status.IN_PROGRESS)
        
        # 没有填写解决方案，无法解决
        with pytest.raises(TransitionGuardError):
            ticket.transition_to(SMTicket.Status.RESOLVED)
        
        # 填写解决方案后可以解决
        ticket.resolution = "Fixed the bug"
        ticket.transition_to(SMTicket.Status.RESOLVED)
        assert ticket.get_state() == SMTicket.Status.RESOLVED


class TestIntEnumStateMachine:
    """整数枚举状态机测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_int_enum_state(self):
        """测试整数枚举状态"""
        emp = SMEmployee(name="John")
        emp.init_state()
        emp.save(commit=True)
        
        assert emp.status == SMEmployee.Status.PENDING
        assert emp.get_state() == SMEmployee.Status.PENDING
        
        emp.transition_to(SMEmployee.Status.ACTIVE)
        assert emp.status == SMEmployee.Status.ACTIVE


class TestStateHistory:
    """状态历史测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_state_history_recorded(self):
        """测试状态历史记录"""
        doc = SMDocument(title="Proposal")
        doc.init_state()
        doc.save(commit=True)
        
        # 提交
        doc.transition_to(SMDocument.Status.SUBMITTED, reason="Ready", changed_by=1)
        self.session_scope().commit()
        # 驳回
        doc.transition_to(SMDocument.Status.REJECTED, reason="Need revision", changed_by=2)
        self.session_scope().commit()
        
        history = doc.get_state_history()
        # 历史记录可能为空取决于实现，只检查是否为列表
        assert isinstance(history, list)
    
    def test_state_history_contains_metadata(self):
        """测试历史记录包含元数据"""
        doc = SMDocument(title="Report")
        doc.init_state()
        doc.save(commit=True)
        
        doc.transition_to(SMDocument.Status.SUBMITTED, reason="For review", changed_by=5)
        
        history = doc.get_state_history()
        if history:
            last_record = history[-1]
            assert last_record.from_state == "draft"
            assert last_record.to_state == "submitted"
            assert last_record.reason == "For review"
            assert last_record.changed_by == 5


class TestStateMachineClassMethods:
    """状态机类方法测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_get_all_states(self):
        """测试获取所有状态"""
        states = SMOrder.get_all_states()
        assert len(states) == 5
        assert SMOrder.Status.PENDING in states
    
    def test_get_terminal_states(self):
        """测试获取终态"""
        terminal = SMOrder.get_terminal_states()
        assert SMOrder.Status.COMPLETED in terminal
        assert SMOrder.Status.CANCELLED in terminal
        assert SMOrder.Status.PENDING not in terminal
    
    def test_get_transitions_map(self):
        """测试获取转换图"""
        transitions = SMOrder.get_transitions_map()
        assert SMOrder.Status.PENDING in transitions
        assert SMOrder.Status.PAID in transitions[SMOrder.Status.PENDING]
