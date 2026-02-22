# StateMachineMixin 状态机指南

## 概述

`StateMachineMixin` 提供通用的状态机功能，支持：

- **状态转换验证**：只允许合法的状态转换
- **钩子回调**：转换前后执行自定义逻辑
- **守卫条件**：转换前的条件检查
- **状态历史**：可选的状态变更记录

## 快速开始

### 导入

```python
from yweb.orm import BaseModel, StateFieldMixin, StateMachineMixin
```

### 基本使用

```python
from enum import Enum

class Order(BaseModel, StateFieldMixin, StateMachineMixin):
    __tablename__ = "order"
    
    # 1. 定义状态枚举
    class Status(str, Enum):
        PENDING = "pending"
        PAID = "paid"
        SHIPPED = "shipped"
        COMPLETED = "completed"
        CANCELLED = "cancelled"
    
    # 2. 配置状态机
    __state_enum__ = Status
    __state_initial__ = Status.PENDING
    __state_transitions__ = {
        Status.PENDING: [Status.PAID, Status.CANCELLED],
        Status.PAID: [Status.SHIPPED, Status.CANCELLED],
        Status.SHIPPED: [Status.COMPLETED],
        Status.COMPLETED: [],  # 终态
        Status.CANCELLED: [],  # 终态
    }
    
    # 3. 业务字段
    total_amount: Mapped[int] = mapped_column(Integer)

# 使用
order = Order(total_amount=100)
order.init_state()  # 设置初始状态
order.save()

order.transition_to(Order.Status.PAID)  # 状态转换
```

## 组件说明

### StateFieldMixin

提供字符串类型的 `state` 字段：

```python
class StateFieldMixin:
    state: Mapped[str] = mapped_column(String(50), default="initial", index=True)
```

### IntStateFieldMixin

提供整数类型的 `status` 字段（用于 IntEnum）：

```python
class IntStateFieldMixin:
    status: Mapped[int] = mapped_column(Integer, default=0, index=True)
```

### StateMachineMixin

提供状态机功能，**不包含**字段定义。

**配置属性**：

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `__state_field__` | str | `"state"` | 状态字段名 |
| `__state_enum__` | Type[Enum] | None | 状态枚举类 |
| `__state_initial__` | Any | None | 初始状态 |
| `__state_transitions__` | dict | `{}` | 转换规则 |
| `__strict_transitions__` | bool | True | 是否严格验证 |

## 配置详解

### 状态转换规则

```python
__state_transitions__ = {
    源状态: [目标状态1, 目标状态2, ...],
    ...
}
```

- **Key**: 源状态
- **Value**: 允许转换到的目标状态列表
- **空列表**: 表示终态（无法再转换）

### 状态图示例

```
PENDING ──────┬──────> PAID ──────┬──────> SHIPPED ──────> COMPLETED
              │                   │
              └──────> CANCELLED <┘
```

对应配置：

```python
__state_transitions__ = {
    Status.PENDING: [Status.PAID, Status.CANCELLED],
    Status.PAID: [Status.SHIPPED, Status.CANCELLED],
    Status.SHIPPED: [Status.COMPLETED],
    Status.COMPLETED: [],
    Status.CANCELLED: [],
}
```

## 钩子方法

### 命名约定

| 钩子类型 | 方法名格式 | 说明 |
|----------|------------|------|
| 进入状态 | `on_enter_{state}(**context)` | 进入指定状态时触发 |
| 离开状态 | `on_exit_{state}(**context)` | 离开指定状态时触发 |
| 特定转换 | `on_transition_{from}_{to}(**context)` | 特定转换时触发 |
| 守卫条件 | `guard_can_{state}() -> bool` | 转换前检查 |
| 通用钩子 | `before_transition()` / `after_transition()` | 所有转换 |

### 示例

```python
class Order(BaseModel, StateFieldMixin, StateMachineMixin):
    # ... 配置省略 ...
    
    paid_at: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    
    def on_enter_paid(self, **context):
        """进入已支付状态时记录时间"""
        self.paid_at = datetime.now()
    
    def on_exit_pending(self, **context):
        """离开待支付状态"""
        print("Order is no longer pending")
    
    def on_transition_paid_shipped(self, **context):
        """从已支付转到已发货"""
        tracking_no = context.get('tracking_no')
        self.tracking_no = tracking_no
    
    def guard_can_shipped(self) -> bool:
        """发货前检查是否有收货地址"""
        return self.address is not None
    
    def before_transition(self, from_state, to_state, **context):
        """所有转换前的通用检查"""
        print(f"About to transition: {from_state} -> {to_state}")
        return True  # 返回 False 阻止转换
```

### 钩子执行顺序

1. `before_transition()` - 可阻止转换
2. `guard_can_{to_state}()` - 守卫检查
3. `on_exit_{from_state}()` - 离开源状态
4. **状态变更**
5. `on_enter_{to_state}()` - 进入目标状态
6. `on_transition_{from}_{to}()` - 特定转换钩子
7. `after_transition()` - 转换后钩子

## API 参考

### 实例方法

#### 核心方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_state()` | Any | 获取当前状态 |
| `set_state(state)` | None | 直接设置状态（跳过验证） |
| `transition_to(state, **context)` | bool | 执行状态转换 |
| `can_transition_to(state)` | bool | 检查能否转换 |
| `get_available_transitions()` | List | 获取可用转换 |
| `init_state()` | None | 初始化为初始状态 |

#### 状态查询

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `is_state(state)` | bool | 是否为指定状态 |
| `is_any_state(*states)` | bool | 是否为其中之一 |
| `is_terminal_state()` | bool | 是否为终态 |
| `is_initial_state()` | bool | 是否为初始状态 |

### transition_to 参数

```python
order.transition_to(
    Order.Status.PAID,
    force=False,        # 强制转换（跳过规则验证）
    save=False,         # 自动保存
    raise_on_error=True,  # 失败时抛异常
    # 以下为上下文参数，传递给钩子
    reason="用户支付",
    changed_by=user_id,
)
```

### 类方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_all_states()` | List | 所有状态 |
| `get_terminal_states()` | List | 所有终态 |
| `get_initial_states()` | List | 所有初始状态 |
| `get_transitions_map()` | Dict | 转换规则映射 |
| `find_by_state(state)` | List | 按状态查询 |
| `count_by_state(state)` | int | 按状态计数 |
| `count_by_states()` | Dict | 各状态计数 |

## 使用场景

### 场景 1：订单状态机

```python
class Order(BaseModel, StateFieldMixin, StateMachineMixin):
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

# 使用
order.transition_to(Order.Status.PAID)
```

### 场景 2：整数枚举（员工状态）

```python
from enum import IntEnum

class Employee(BaseModel, StateMachineMixin):
    class Status(IntEnum):
        PENDING = 5
        PROBATION = 3
        ACTIVE = 1
        SUSPENDED = 4
        RESIGNED = 2
    
    __state_field__ = "status"  # 使用 status 字段
    __state_enum__ = Status
    __state_initial__ = Status.PENDING
    __state_transitions__ = {
        Status.PENDING: [Status.PROBATION, Status.ACTIVE],
        Status.PROBATION: [Status.ACTIVE, Status.RESIGNED],
        Status.ACTIVE: [Status.SUSPENDED, Status.RESIGNED],
        Status.SUSPENDED: [Status.ACTIVE, Status.RESIGNED],
        Status.RESIGNED: [],
    }
    
    # 自定义整数状态字段
    status: Mapped[int] = mapped_column(Integer, default=Status.PENDING)
```

### 场景 3：带守卫条件

```python
class Ticket(BaseModel, StateFieldMixin, StateMachineMixin):
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
    
    assignee_id: Mapped[int] = mapped_column(Integer, nullable=True)
    resolution: Mapped[str] = mapped_column(String(500), nullable=True)
    
    def guard_can_in_progress(self) -> bool:
        """开始处理前必须指定处理人"""
        return self.assignee_id is not None
    
    def guard_can_resolved(self) -> bool:
        """解决前必须填写解决方案"""
        return bool(self.resolution)
```

### 场景 4：带历史记录

```python
from yweb.orm import AbstractStateHistory, StateHistoryMixin

# 1. 定义历史记录模型
class DocumentStateHistory(BaseModel, AbstractStateHistory):
    __tablename__ = "document_state_history"

# 2. 在业务模型中使用
class Document(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
    __tablename__ = "document"
    __state_history_model__ = DocumentStateHistory
    
    # ... 状态机配置 ...

# 使用
doc.transition_to(Document.Status.SUBMITTED, reason="提交审批", changed_by=1)

# 查询历史
history = doc.get_state_history()
for record in history:
    print(f"{record.from_state} -> {record.to_state} at {record.changed_at}")

# 获取时间线
timeline = doc.get_states_timeline()
```

## 异常处理

```python
from yweb.orm import (
    InvalidStateError,
    InvalidTransitionError,
    TransitionGuardError,
    TransitionBlockedError,
)

try:
    order.transition_to(Order.Status.SHIPPED)
except InvalidTransitionError as e:
    print(f"非法转换: {e.from_state} -> {e.to_state}")
    print(f"允许的转换: {e.allowed_transitions}")
except TransitionGuardError as e:
    print(f"守卫条件不满足: {e.guard_name}")
except TransitionBlockedError as e:
    print(f"转换被阻止: {e.reason}")
```

### 静默处理

```python
# 不抛异常，返回 False
success = order.transition_to(Order.Status.SHIPPED, raise_on_error=False)
if not success:
    print("转换失败")
```

## 最佳实践

1. **继承顺序**：`BaseModel` → `StateFieldMixin` → `StateMachineMixin`

2. **使用枚举**：推荐使用 Enum 定义状态，而非字符串常量

3. **守卫方法**：复杂的前置条件检查应放在 guard 方法中

4. **钩子分离**：
   - 简单逻辑：使用 `on_enter_*` / `on_exit_*`
   - 复杂业务：使用 `after_transition` 或服务层

5. **历史记录**：需要审计的业务使用 `StateHistoryMixin`

6. **状态查询**：使用 `is_state()` 而非直接比较字段值

## 状态历史 API

### StateHistoryMixin 方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_state_history(limit)` | List | 获取历史记录 |
| `get_last_state_change()` | Record | 最近一次变更 |
| `get_state_change_count()` | int | 变更次数 |
| `get_time_in_state(state)` | timedelta | 在某状态停留时间 |
| `get_states_timeline()` | List[dict] | 状态时间线 |

### AbstractStateHistory 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_id` | int | 关联记录ID |
| `target_type` | str | 模型类型 |
| `from_state` | str | 源状态 |
| `to_state` | str | 目标状态 |
| `changed_at` | datetime | 变更时间 |
| `changed_by` | int | 变更人ID |
| `reason` | str | 变更原因 |
| `context` | str | 上下文（JSON） |

## 与其他 Mixin 的关系

| Mixin | 包含状态字段 | 说明 |
|-------|-------------|------|
| `StateFieldMixin` | ✅ state (str) | 字符串状态字段 |
| `IntStateFieldMixin` | ✅ status (int) | 整数状态字段 |
| `StateMachineMixin` | ❌ | 状态机逻辑 |
| `StateHistoryMixin` | ❌ | 历史记录功能 |

## 注意事项

1. **提交事务**：状态转换后需调用 `db.session.commit()` 或使用 `save=True`

2. **钩子异常**：钩子中的异常会导致转换失败并可能回滚

3. **并发安全**：高并发场景建议使用乐观锁或悲观锁

4. **状态值**：数据库存储的是 Enum 的 value，查询时注意使用正确的值
