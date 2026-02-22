"""状态机 Mixin 使用示例

演示 StateMachineMixin 的各种使用场景：
1. 基本订单状态机
2. 带守卫条件的状态转换
3. 整数枚举状态机（员工状态）
4. 带历史记录的文档审批流程
"""

import sys
from pathlib import Path
from enum import Enum, IntEnum
from datetime import datetime

# 添加 yweb-core 到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import (
    BaseModel,
    Base,
    init_database,
    StateFieldMixin,
    StateMachineMixin,
    AbstractStateHistory,
    StateHistoryMixin,
    InvalidTransitionError,
    TransitionGuardError,
)


# ==================== 示例 1: 基本订单状态机 ====================

class Order(BaseModel, StateFieldMixin, StateMachineMixin):
    """订单模型 - 基本状态机示例"""
    __tablename__ = "demo_order"
    
    # 定义状态枚举
    class Status(str, Enum):
        PENDING = "pending"      # 待支付
        PAID = "paid"            # 已支付
        SHIPPED = "shipped"      # 已发货
        COMPLETED = "completed"  # 已完成
        CANCELLED = "cancelled"  # 已取消
    
    # 状态机配置
    __state_enum__ = Status
    __state_initial__ = Status.PENDING
    __state_transitions__ = {
        Status.PENDING: [Status.PAID, Status.CANCELLED],
        Status.PAID: [Status.SHIPPED, Status.CANCELLED],
        Status.SHIPPED: [Status.COMPLETED],
        Status.COMPLETED: [],  # 终态
        Status.CANCELLED: [],  # 终态
    }
    
    # 业务字段
    order_no: Mapped[str] = mapped_column(String(50), comment="订单号")
    total_amount: Mapped[int] = mapped_column(Integer, default=0, comment="总金额（分）")
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="支付时间")
    shipped_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="发货时间")
    
    # ==================== 钩子方法 ====================
    
    def on_enter_paid(self, **context):
        """进入已支付状态"""
        self.paid_at = datetime.now()
        print(f"  [Hook] Order {self.order_no}: Payment received at {self.paid_at}")
    
    def on_enter_shipped(self, **context):
        """进入已发货状态"""
        self.shipped_at = datetime.now()
        print(f"  [Hook] Order {self.order_no}: Shipped at {self.shipped_at}")
    
    def on_exit_pending(self, **context):
        """离开待支付状态"""
        print(f"  [Hook] Order {self.order_no}: Leaving pending state")
    
    def on_transition_paid_shipped(self, **context):
        """从已支付转换到已发货"""
        tracking_no = context.get('tracking_no')
        if tracking_no:
            print(f"  [Hook] Order {self.order_no}: Tracking number: {tracking_no}")
    
    def after_transition(self, from_state, to_state, **context):
        """转换后钩子"""
        print(f"  [Hook] Order {self.order_no}: {from_state} -> {to_state}")


# ==================== 示例 2: 带守卫条件的状态机 ====================

class Ticket(BaseModel, StateFieldMixin, StateMachineMixin):
    """工单模型 - 带守卫条件示例"""
    __tablename__ = "demo_ticket"
    
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
    
    title: Mapped[str] = mapped_column(String(200), comment="标题")
    assignee_id: Mapped[int] = mapped_column(Integer, nullable=True, comment="处理人ID")
    resolution: Mapped[str] = mapped_column(String(500), nullable=True, comment="解决方案")
    
    # ==================== 守卫方法 ====================
    
    def guard_can_in_progress(self) -> bool:
        """开始处理前必须指定处理人"""
        return self.assignee_id is not None
    
    def guard_can_resolved(self) -> bool:
        """解决前必须填写解决方案"""
        return self.resolution is not None and len(self.resolution) > 0


# ==================== 示例 3: 整数枚举状态机 ====================

class Employee(BaseModel, StateMachineMixin):
    """员工模型 - 整数枚举状态机示例"""
    __tablename__ = "demo_employee"
    
    class Status(IntEnum):
        PENDING = 5     # 待入职
        PROBATION = 3   # 试用期
        ACTIVE = 1      # 在职
        SUSPENDED = 4   # 停职
        RESIGNED = 2    # 离职
    
    __state_field__ = "status"
    __state_enum__ = Status
    __state_initial__ = Status.PENDING
    __state_transitions__ = {
        Status.PENDING: [Status.PROBATION, Status.ACTIVE],
        Status.PROBATION: [Status.ACTIVE, Status.RESIGNED],
        Status.ACTIVE: [Status.SUSPENDED, Status.RESIGNED],
        Status.SUSPENDED: [Status.ACTIVE, Status.RESIGNED],
        Status.RESIGNED: [],  # 终态
    }
    
    name: Mapped[str] = mapped_column(String(100), comment="姓名")
    status: Mapped[int] = mapped_column(Integer, default=Status.PENDING, comment="状态")
    joined_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="入职时间")
    resigned_at: Mapped[datetime] = mapped_column(DateTime, nullable=True, comment="离职时间")
    
    def on_enter_active(self, **context):
        """正式入职"""
        if self.joined_at is None:
            self.joined_at = datetime.now()
        print(f"  [Hook] Employee {self.name}: Now active")
    
    def on_enter_resigned(self, **context):
        """离职"""
        self.resigned_at = datetime.now()
        reason = context.get('reason', 'Unknown')
        print(f"  [Hook] Employee {self.name}: Resigned, reason: {reason}")


# ==================== 示例 4: 带历史记录的审批流程 ====================

class DocumentStateHistory(BaseModel, AbstractStateHistory):
    """文档状态历史记录"""
    __tablename__ = "demo_document_state_history"


class Document(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
    """文档模型 - 带历史记录的审批流程"""
    __tablename__ = "demo_document"
    
    class Status(str, Enum):
        DRAFT = "draft"
        SUBMITTED = "submitted"
        APPROVED = "approved"
        REJECTED = "rejected"
        ARCHIVED = "archived"
    
    __state_enum__ = Status
    __state_initial__ = Status.DRAFT
    __state_transitions__ = {
        Status.DRAFT: [Status.SUBMITTED],
        Status.SUBMITTED: [Status.APPROVED, Status.REJECTED],
        Status.APPROVED: [Status.ARCHIVED],
        Status.REJECTED: [Status.DRAFT],  # 可重新编辑后提交
        Status.ARCHIVED: [],
    }
    __state_history_model__ = DocumentStateHistory
    
    title: Mapped[str] = mapped_column(String(200), comment="标题")
    content: Mapped[str] = mapped_column(String(2000), nullable=True, comment="内容")


# ==================== 演示函数 ====================

def demo_basic_state_machine():
    """演示基本状态机"""
    print("\n" + "=" * 60)
    print("Demo 1: Basic Order State Machine")
    print("=" * 60)
    
    # 创建订单
    order = Order(order_no="ORD001", total_amount=10000)
    order.init_state()
    order.save()
    
    print(f"\n[Created] Order {order.order_no}")
    print(f"  State: {order.get_state()}")
    print(f"  Available transitions: {order.get_available_transitions()}")
    
    # 支付
    print(f"\n[Action] Pay order")
    order.transition_to(Order.Status.PAID)
    print(f"  State: {order.get_state()}")
    print(f"  Is terminal: {order.is_terminal_state()}")
    
    # 发货（带上下文参数）
    print(f"\n[Action] Ship order")
    order.transition_to(Order.Status.SHIPPED, tracking_no="SF123456789")
    print(f"  State: {order.get_state()}")
    
    # 完成
    print(f"\n[Action] Complete order")
    order.transition_to(Order.Status.COMPLETED)
    print(f"  State: {order.get_state()}")
    print(f"  Is terminal: {order.is_terminal_state()}")
    print(f"  Available transitions: {order.get_available_transitions()}")


def demo_invalid_transition():
    """演示无效转换"""
    print("\n" + "=" * 60)
    print("Demo 2: Invalid Transition Handling")
    print("=" * 60)
    
    order = Order(order_no="ORD002", total_amount=5000)
    order.init_state()
    order.save()
    
    print(f"\n[Created] Order {order.order_no}, state: {order.get_state()}")
    
    # 尝试直接发货（跳过支付）
    print(f"\n[Action] Try to ship without payment")
    try:
        order.transition_to(Order.Status.SHIPPED)
    except InvalidTransitionError as e:
        print(f"  Error: {e}")
        print(f"  Current state: {order.get_state()}")
    
    # 检查能否转换
    print(f"\n[Check] Can transition to SHIPPED: {order.can_transition_to(Order.Status.SHIPPED)}")
    print(f"[Check] Can transition to PAID: {order.can_transition_to(Order.Status.PAID)}")


def demo_guard_conditions():
    """演示守卫条件"""
    print("\n" + "=" * 60)
    print("Demo 3: Guard Conditions")
    print("=" * 60)
    
    ticket = Ticket(title="Bug: Login failed")
    ticket.init_state()
    ticket.save()
    
    print(f"\n[Created] Ticket: {ticket.title}")
    print(f"  State: {ticket.get_state()}")
    
    # 尝试开始处理（没有指定处理人）
    print(f"\n[Action] Try to start without assignee")
    try:
        ticket.transition_to(Ticket.Status.IN_PROGRESS)
    except TransitionGuardError as e:
        print(f"  Error: {e}")
    
    # 指定处理人后再开始
    print(f"\n[Action] Assign and start")
    ticket.assignee_id = 1
    ticket.transition_to(Ticket.Status.IN_PROGRESS)
    print(f"  State: {ticket.get_state()}")
    
    # 尝试解决（没有填写解决方案）
    print(f"\n[Action] Try to resolve without resolution")
    try:
        ticket.transition_to(Ticket.Status.RESOLVED)
    except TransitionGuardError as e:
        print(f"  Error: {e}")
    
    # 填写解决方案后解决
    print(f"\n[Action] Add resolution and resolve")
    ticket.resolution = "Fixed by updating the authentication module"
    ticket.transition_to(Ticket.Status.RESOLVED)
    print(f"  State: {ticket.get_state()}")


def demo_int_enum_state_machine():
    """演示整数枚举状态机"""
    print("\n" + "=" * 60)
    print("Demo 4: Integer Enum State Machine (Employee)")
    print("=" * 60)
    
    emp = Employee(name="John Doe")
    emp.init_state()
    emp.save()
    
    print(f"\n[Created] Employee: {emp.name}")
    print(f"  State: {emp.get_state()} (value: {emp.status})")
    
    # 试用期 -> 正式入职
    print(f"\n[Action] Start probation")
    emp.transition_to(Employee.Status.PROBATION)
    print(f"  State: {emp.get_state()}")
    
    print(f"\n[Action] Convert to full-time")
    emp.transition_to(Employee.Status.ACTIVE)
    print(f"  State: {emp.get_state()}")
    print(f"  Joined at: {emp.joined_at}")
    
    # 离职
    print(f"\n[Action] Resign")
    emp.transition_to(Employee.Status.RESIGNED, reason="Personal reasons")
    print(f"  State: {emp.get_state()}")
    print(f"  Resigned at: {emp.resigned_at}")
    print(f"  Is terminal: {emp.is_terminal_state()}")


def demo_state_history():
    """演示状态历史记录"""
    print("\n" + "=" * 60)
    print("Demo 5: State History (Document Approval)")
    print("=" * 60)
    
    doc = Document(title="Project Proposal", content="...")
    doc.init_state()
    doc.save(commit=True)  # 确保有 ID 后才能记录历史
    
    print(f"\n[Created] Document: {doc.title} (id={doc.id})")
    print(f"  State: {doc.get_state()}")
    
    # 提交审批
    print(f"\n[Action] Submit for approval")
    doc.transition_to(Document.Status.SUBMITTED, reason="Ready for review", changed_by=1)
    
    # 驳回
    print(f"\n[Action] Reject")
    doc.transition_to(Document.Status.REJECTED, reason="Need more details", changed_by=2)
    
    # 重新编辑后提交
    print(f"\n[Action] Edit and resubmit")
    doc.transition_to(Document.Status.DRAFT, reason="Editing")
    doc.transition_to(Document.Status.SUBMITTED, reason="Resubmitted", changed_by=1)
    
    # 批准
    print(f"\n[Action] Approve")
    doc.transition_to(Document.Status.APPROVED, reason="Looks good", changed_by=3)
    
    # 查看历史
    print(f"\n[History] State changes:")
    history = doc.get_state_history()
    for record in history:
        print(f"  {record.from_state} -> {record.to_state}")
        print(f"    at: {record.changed_at}, by: {record.changed_by}")
        print(f"    reason: {record.reason}")
    
    # 获取时间线
    print(f"\n[Timeline]")
    timeline = doc.get_states_timeline()
    for entry in timeline:
        print(f"  {entry['state']}: {entry['duration']}")


def demo_class_methods():
    """演示类方法"""
    print("\n" + "=" * 60)
    print("Demo 6: Class Methods")
    print("=" * 60)
    
    print(f"\n[Order] All states: {Order.get_all_states()}")
    print(f"[Order] Terminal states: {Order.get_terminal_states()}")
    print(f"[Order] Initial states: {Order.get_initial_states()}")
    print(f"[Order] Transitions map: {Order.get_transitions_map()}")
    
    # 按状态统计
    print(f"\n[Order] Count by states:")
    counts = Order.count_by_states()
    for state, count in counts.items():
        print(f"  {state}: {count}")


def main():
    """主函数"""
    print("=" * 60)
    print("StateMachineMixin Demo")
    print("=" * 60)
    
    # 初始化数据库（内存数据库）
    # init_database 返回 engine 和 session_scope
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    
    # 创建所有表
    Base.metadata.create_all(engine)
    
    try:
        # 运行演示
        demo_basic_state_machine()
        demo_invalid_transition()
        demo_guard_conditions()
        demo_int_enum_state_machine()
        demo_state_history()
        demo_class_methods()
        
        print("\n" + "=" * 60)
        print("All demos completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[Error] {e}")
        import traceback
        traceback.print_exc()
        session_scope.rollback()
    finally:
        session_scope.remove()


if __name__ == "__main__":
    main()
