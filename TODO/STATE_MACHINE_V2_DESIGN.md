# YWeb 状态机 V2 设计文档

本文档用于单独说明 YWeb 状态机能力的 v2 升级方案。

设计前提：

- **不推倒重来**
- **不直接引入外部状态机库作为主 API**
- **继续增强现有 `StateMachineMixin` 体系**
- **让状态机更像框架级业务建模能力，而不是单纯工具类**

本文档与 `TODO/LIGHTWEIGHT_DOMAIN_EVENTS_AND_OWNSONE_DESIGN.md` 中的“状态机 v2 设计补充”章节互补：

- 那份文档负责说明整体方向
- 本文档负责状态机 v2 的单独细化设计

---

## 1. 背景

YWeb 当前已经具备一套基础状态机模块：

- `StateFieldMixin`
- `IntStateFieldMixin`
- `StateMachineMixin`
- `StateHistoryMixin`

现有能力已经支持：

- 状态字段定义
- 合法状态迁移校验
- 迁移前后钩子
- 守卫条件
- 状态历史记录

这意味着 YWeb **不是缺状态机**，而是：

- 已经有第一版
- 需要升级成第二版

当前版本更像“轻量状态流转工具”，而 v2 的目标是把它升级成：

- 更声明式
- 更有业务动作语义
- 更容易被 API / 前端 / Service / 领域事件复用
- 更适合生产级业务状态管理

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| 保持兼容 | 不破坏现有 `transition_to()` 和 `__state_transitions__` 用法 |
| 动作语义优先 | 从“切换到某状态”升级为“执行某动作” |
| 声明式增强 | 引入 `@transition` 装饰器，减少散落配置 |
| 元数据可读 | 支持输出状态定义、动作定义、当前可执行动作 |
| 与事务集成 | 动作成功后的副作用可纳入事务提交语义 |
| 与领域事件集成 | 动作成功后可自然记录领域事件 |
| 与历史集成 | 历史记录从“状态变化”升级为“迁移动作记录” |
| 与权限集成 | 动作可声明权限码，便于 API 层和前端使用 |
| 适合中后台业务 | 优先覆盖订单、审批、发布、履约、启停等常见场景 |

---

## 3. 非目标

状态机 v2 明确不做以下事情：

- 不实现 BPM / 工作流引擎
- 不支持可视化流程设计器
- 不支持复杂会签 / 或签 / 流程回退编排
- 不支持任意脚本节点执行
- 不在第一阶段支持分层状态机和并行状态机 DSL
- 不试图覆盖所有流程平台场景

如果未来有“动态流程编排”需求，应单独设计 `workflow` 模块，而不是继续往 ORM 状态机里塞能力。

---

## 4. 当前版本问题分析

当前状态机的优点：

- 轻量
- 易用
- 学习成本低
- 与现有 ORM 风格一致
- 已有状态历史能力

当前状态机的主要不足：

### 4.1 迁移入口偏“目标状态驱动”

现有写法更偏：

```python
order.transition_to(Order.Status.PAID)
```

但真实业务语义往往是：

- 用户支付订单
- 仓库发货
- 审批通过
- 审批驳回

也就是说，业务更关心“动作”，而不是“目标状态值”。

### 4.2 配置较分散

当前迁移规则主要靠：

- `__state_transitions__`
- 命名约定钩子
- `guard_can_xxx()`

这种方式在简单场景足够，但在稍复杂业务里会出现：

- 规则定义与动作逻辑分散
- IDE 跟踪跳转不够直观
- 元数据难以统一提取

### 4.3 与领域事件衔接不够自然

状态变化其实是领域事件最常见的来源之一：

- `OrderPaid`
- `OrderShipped`
- `ApprovalRejected`

当前状态机还没有天然表达“某个迁移动作成功后顺手登记领域事件”的机制。

### 4.4 与权限和前端动作展示的衔接不够好

很多前端页面都需要知道：

- 当前有哪些可执行动作
- 这些动作的中文名是什么
- 谁可以执行
- 执行后会进入哪个状态

当前状态机没有统一的元数据输出模型。

### 4.5 并发与事务语义没有被系统性强调

状态机是最容易受并发影响的场景之一：

- 双击支付
- 重复审核
- 并发发货

虽然 YWeb 已有事务和版本控制能力，但状态机模块本身还缺一套“推荐使用方式”与“最佳实践约束”。

---

## 5. 设计原则

### 5.1 继续增强，不另起炉灶

保留现有：

- `StateFieldMixin`
- `IntStateFieldMixin`
- `StateMachineMixin`
- `StateHistoryMixin`

新增能力要以“兼容扩展”为前提。

### 5.2 动作优先，状态保留

状态仍然存在，继续承担：

- 持久化存储
- 查询过滤
- 合法迁移判断
- 展示和统计

但业务入口应优先由“动作”承载。

### 5.3 声明式与约定式并存

v2 推荐声明式写法，但保留旧写法兼容：

- 老项目继续可用
- 新项目优先采用 `@transition`

### 5.4 状态机本身不做不可回滚副作用

状态机动作中可以：

- 变更模型字段
- 做守卫校验
- 记录状态历史
- 登记领域事件

不推荐直接在动作内部做：

- 发消息
- 发邮件
- 调第三方 HTTP
- 推送 Webhook

这类副作用应放到领域事件处理器中，由事务提交后统一执行。

---

## 6. 核心模型

建议引入以下核心抽象。

| 抽象 | 说明 |
|------|------|
| `TransitionDefinition` | 单个迁移动作的定义 |
| `TransitionRegistry` | 模型级动作注册表 |
| `transition()` | 声明式动作装饰器 |
| `ActionDescriptor` | 对外暴露给 API / 前端的动作元数据 |
| `StateDescriptor` | 状态标签、说明、终态等元数据 |

---

## 7. 建议 API 设计

## 7.1 模型定义方式

### v1 兼容写法

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
```

### v2 推荐写法

```python
class Order(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
    class Status(str, Enum):
        PENDING = "pending"
        PAID = "paid"
        SHIPPED = "shipped"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    __state_enum__ = Status
    __state_initial__ = Status.PENDING
```

迁移规则由动作装饰器表达，而不是完全依赖 `__state_transitions__`。

## 7.2 `@transition` 装饰器

建议用法：

```python
from yweb.orm.statemachine import transition


class Order(BaseModel, StateFieldMixin, StateMachineMixin, StateHistoryMixin):
    class Status(str, Enum):
        PENDING = "pending"
        PAID = "paid"
        SHIPPED = "shipped"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    __state_enum__ = Status
    __state_initial__ = Status.PENDING

    @transition(
        source=Status.PENDING,
        target=Status.PAID,
        label="支付",
        description="将订单从待支付流转为已支付",
        permission="order.pay",
        event="OrderPaid",
        record_history=True,
    )
    def pay(self, *, operator_id: int, reason: str | None = None):
        self.paid_by = operator_id
        self.pay_reason = reason

    @transition(
        source=Status.PAID,
        target=Status.SHIPPED,
        label="发货",
        permission="order.ship",
        event="OrderShipped",
    )
    def ship(self, *, tracking_no: str, operator_id: int):
        self.tracking_no = tracking_no
        self.shipped_by = operator_id
```

## 7.3 装饰器参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `source` | 单值 / 列表 / `"*"` | 允许的源状态 |
| `target` | 单值 | 目标状态 |
| `label` | `str` | 动作显示名称 |
| `description` | `str` | 动作说明 |
| `permission` | `str` | 动作权限码 |
| `guard` | `str` / callable | 显式守卫方法 |
| `event` | type / str / callable | 成功后登记的领域事件 |
| `save` | `bool` | 是否在动作后自动保存 |
| `record_history` | `bool` | 是否记录状态历史 |
| `terminal` | `bool` | 是否为进入终态动作，可选元数据 |
| `tags` | `list[str]` | 动作标签，用于分类或 UI |

说明：

- `source="*"` 表示任意源状态都可触发，但仍建议慎用
- `event` 若传字符串，仅作为设计占位；正式实现更推荐传事件类或工厂函数
- `save=False` 仍应作为默认值，保持与当前 ORM 使用习惯一致

## 7.4 动作执行入口

推荐同时支持两种方式：

### 方式 1：直接调用动作方法

```python
order.pay(operator_id=1, reason="用户支付")
```

### 方式 2：统一入口执行

```python
order.execute_action(
    "pay",
    operator_id=1,
    reason="用户支付",
)
```

统一入口的价值：

- 适合 API 层按字符串调用
- 适合后台按钮驱动场景
- 更容易统一权限校验和审计

## 7.5 元数据查询接口

建议新增：

- `get_available_actions()`
- `get_action_definition(name)`
- `can_execute_action(name, **context)`
- `get_state_machine_schema()`

### `get_available_actions()` 示例

```python
[
    {
        "name": "pay",
        "label": "支付",
        "description": "将订单从待支付流转为已支付",
        "source": "pending",
        "target": "paid",
        "permission": "order.pay",
    }
]
```

### `get_state_machine_schema()` 示例

```python
{
    "state_field": "state",
    "initial_state": "pending",
    "states": [
        {"name": "pending", "label": "待支付"},
        {"name": "paid", "label": "已支付"},
        {"name": "shipped", "label": "已发货"},
        {"name": "completed", "label": "已完成"},
        {"name": "cancelled", "label": "已取消"},
    ],
    "actions": [
        {"name": "pay", "source": ["pending"], "target": "paid"},
        {"name": "ship", "source": ["paid"], "target": "shipped"},
    ],
}
```

---

## 8. 校验分层设计

状态机 v2 建议明确区分 4 层检查。

## 8.1 状态规则检查

判断：

- 当前状态是否属于 `source`
- 目标状态是否允许迁移

这是最基础的一层，不涉及业务语义。

## 8.2 业务守卫检查

判断业务条件是否满足。

示例：

- 发货前必须有物流单号
- 完成前必须已支付
- 审批通过前必须有审批意见

建议支持两种写法：

```python
@transition(..., guard="guard_can_ship")
def ship(...):
    ...
```

或：

```python
@transition(..., guard=lambda self, **ctx: self.address is not None)
def ship(...):
    ...
```

## 8.3 权限检查

判断操作者是否有权执行动作。

建议不把权限逻辑硬编码进状态机核心，而是：

- 动作定义里声明 `permission`
- 执行入口支持 `permission_checker`
- 由 API / Service 注入当前用户上下文

## 8.4 并发检查

状态迁移通常是高并发敏感点。

建议与已有 `ver` 乐观锁协同：

- 核心迁移动作应在事务中执行
- 更新时依赖现有乐观锁机制避免并发覆盖
- 若出现并发冲突，抛出清晰错误

---

## 9. 动作执行生命周期

建议 v2 统一迁移生命周期如下：

1. 解析动作定义
2. 读取当前状态
3. 校验源状态是否合法
4. 执行业务守卫
5. 校验权限
6. 调用 `before_transition`
7. 调用动作方法本体
8. 执行 `on_exit_{from_state}`
9. 设置目标状态
10. 执行 `on_enter_{to_state}`
11. 执行 `on_transition_{from}_{to}`
12. 记录状态历史
13. 登记领域事件
14. 调用 `after_transition`
15. 根据策略决定是否保存

说明：

- v1 中已有的命名约定钩子继续保留
- v2 中动作方法成为迁移生命周期的一部分

---

## 10. 与领域事件集成

这是状态机 v2 的关键增强点之一。

## 10.1 设计原则

状态迁移成功后，可以登记一个或多个领域事件，但不直接做不可回滚副作用。

推荐流程：

1. 动作执行成功
2. 状态变更成功
3. 历史记录入队
4. 领域事件入队
5. 事务提交后统一发布

## 10.2 示例

```python
@transition(
    source=Status.PAID,
    target=Status.SHIPPED,
    event=lambda self, **ctx: OrderShipped(
        order_id=self.id,
        tracking_no=ctx["tracking_no"],
    ),
)
def ship(self, *, tracking_no: str, operator_id: int):
    self.tracking_no = tracking_no
    self.shipped_by = operator_id
```

### 推荐支持的 `event` 写法

| 写法 | 说明 |
|------|------|
| 事件类 | 由框架按约定构造，适合简单场景 |
| 工厂函数 | `lambda self, **ctx: Event(...)`，适合需要上下文参数 |
| 列表 | 一个动作触发多个领域事件，第一阶段可不急着支持 |

## 10.3 业务收益

好处包括：

- 状态变化天然成为业务事实
- 通知、缓存、审计、索引等副作用可解耦
- 状态机与领域事件形成统一业务语言

---

## 11. 与状态历史集成

当前 `StateHistoryMixin` 已经存在，v2 应优先复用。

## 11.1 现状问题

现有历史记录更偏：

- `from_state`
- `to_state`
- `changed_by`
- `reason`

但在动作驱动模型下，还应补充：

- `transition_name`
- `action_label`
- 关键上下文摘要

## 11.2 建议历史模型增强

建议新增字段：

| 字段 | 说明 |
|------|------|
| `transition_name` | 动作名，如 `pay` / `ship` |
| `action_label` | 动作显示名，如“支付” |
| `operator_id` | 操作人，若与 `changed_by` 重合可择一 |
| `context_summary` | 关键上下文摘要，避免完整存储敏感数据 |

## 11.3 历史写入策略

建议：

- 历史记录与主模型状态变更处于同一事务中
- 不允许历史先落库、状态后失败
- 若事务回滚，历史记录也一起回滚

---

## 12. 与 API / 前端协同

状态机 v2 需要照顾前后端协作场景。

## 12.1 API 层典型诉求

API 层通常希望知道：

- 当前对象可执行哪些动作
- 每个动作是否需要权限
- 每个动作对应哪个目标状态
- 是否需要填写理由、物流单号等参数

因此建议状态机元数据支持扩展字段：

| 字段 | 说明 |
|------|------|
| `form_schema` | 动作表单结构，可选 |
| `requires_reason` | 是否要求填写理由 |
| `requires_confirmation` | 是否需要二次确认 |
| `button_style` | 前端按钮样式提示，可选 |

说明：

- 第一阶段不一定实现 UI 表单 DSL
- 但元数据模型建议预留

## 12.2 推荐输出能力

建议后续提供：

- `obj.get_available_actions()`
- `obj.to_dict_with_actions()`
- `Model.get_state_machine_schema()`

这样前端可以自然渲染：

- 当前状态标签
- 可执行动作按钮
- 每个动作的显示文字与参数要求

---

## 13. 模块拆分建议

建议在现有目录基础上演进。

## 13.1 目录建议

```text
yweb/orm/statemachine/
├── __init__.py
├── state_field.py
├── state_machine.py
├── state_history.py
├── exceptions.py
├── transition.py
├── metadata.py
└── permissions.py
```

## 13.2 各模块职责

### `state_field.py`

继续负责：

- `StateFieldMixin`
- `IntStateFieldMixin`

### `state_machine.py`

继续负责：

- 状态读取 / 设置
- 兼容 v1 的 `transition_to()`
- 动作执行主流程
- 钩子调度

### `transition.py`

负责：

- `@transition` 装饰器
- `TransitionDefinition`
- 动作注册与解析

### `metadata.py`

负责：

- 提取状态机 schema
- 输出状态和动作元数据
- 支持前端 / API 层读取

### `state_history.py`

继续负责：

- 状态历史记录
- 增强支持动作名和动作标签

### `permissions.py`

可选模块，负责：

- 权限检查协议
- 默认权限校验适配接口

---

## 14. 兼容策略

## 14.1 向后兼容原则

以下能力必须保持可用：

- `transition_to()`
- `can_transition_to()`
- `get_available_transitions()`
- `guard_can_xxx()`
- `on_enter_xxx()` / `on_exit_xxx()` / `on_transition_xxx_yyy()`

## 14.2 推荐迁移方式

老模型可以继续运行，新模型逐步切换到：

1. 保留原 `__state_transitions__`
2. 逐步把关键迁移改造成 `@transition`
3. 再把领域事件和动作元数据接入

### 示例：渐进迁移

第一步：

```python
__state_transitions__ = {
    Status.PENDING: [Status.PAID],
}
```

第二步：

```python
@transition(source=Status.PENDING, target=Status.PAID, label="支付")
def pay(self, *, operator_id: int):
    self.paid_by = operator_id
```

第三步：

```python
@transition(
    source=Status.PENDING,
    target=Status.PAID,
    label="支付",
    event=OrderPaid,
    permission="order.pay",
)
def pay(self, *, operator_id: int):
    self.paid_by = operator_id
```

---

## 15. 分阶段实施计划

## 15.1 第一阶段：声明式动作能力

目标：

- 引入 `@transition`
- 建立动作注册表
- 增加元数据输出
- 保持与 v1 兼容

建议修改：

- `yweb/orm/statemachine/state_machine.py`
- 新增 `yweb/orm/statemachine/transition.py`
- 新增 `yweb/orm/statemachine/metadata.py`

## 15.2 第二阶段：与领域事件打通

目标：

- 动作成功后支持登记领域事件
- 事务提交后统一发布

依赖：

- 轻量领域事件先落地

## 15.3 第三阶段：与历史、权限、并发治理打通

目标：

- 完善生产级可用性
- 让状态机真正成为业务框架能力

建议补充：

- 权限协议
- 历史模型增强
- 并发错误语义
- 最佳实践文档

---

## 16. 测试建议

至少应覆盖以下测试。

## 16.1 基础迁移

- 动作从合法源状态迁移成功
- 非法源状态拒绝迁移
- `source="*"` 场景工作正常
- `transition_to()` 与 `@transition` 并存时行为一致

## 16.2 守卫与权限

- 守卫通过时允许迁移
- 守卫失败时阻止迁移
- 权限不足时拒绝执行动作

## 16.3 钩子与历史

- `before_transition` / `after_transition` 正常触发
- `on_enter_xxx` / `on_exit_xxx` 正常触发
- 历史记录正确记录动作名和状态变化

## 16.4 领域事件

- 动作成功后登记事件
- 事务提交后才真正发布
- 回滚后事件不发布

## 16.5 并发与事务

- 乐观锁冲突时迁移失败
- 并发重复迁移被正确拦截
- 历史与状态在同一事务中保持一致

根据 pytest 规范，测试中用于辅助的模型或值对象类不要以 `Test` 开头命名。

---

## 17. 开源库参考建议

## 17.1 `sqlalchemy-fsm`

适合重点参考：

- `@transition` 风格
- ORM 模型动作定义方式
- 基于模型字段的状态迁移体验

适合借鉴，不建议直接作为主 API 依赖。

## 17.2 `transitions`

适合重点参考：

- 通用状态机抽象
- 回调体系
- 守卫与迁移生命周期设计

适合作为理念参考，不建议直接拿来替代 YWeb 当前模块。

---

## 18. 风险与注意事项

| 风险点 | 说明 | 建议 |
|------|------|------|
| 动作过多导致模型过重 | 所有业务都塞进模型动作会膨胀 | 保持“单聚合规则在模型，跨聚合编排在 Service” |
| 动作中直接做副作用 | 事务回滚时容易造成不一致 | 动作中只登记领域事件 |
| 状态机与权限耦合过深 | 会污染核心实现 | 通过协议或适配器注入权限校验 |
| 元数据设计过重 | 容易走向流程引擎 | 第一阶段只做轻量 schema |
| 历史记录过量 | 可能导致存储膨胀 | 记录关键上下文，不保存冗余大对象 |

---

## 19. 结论

YWeb 状态机 v2 的最佳路线不是“增加另一套状态机”，而是：

1. 保留现有 `StateMachineMixin` 体系
2. 增加 `@transition` 声明式动作能力
3. 提供统一动作元数据输出
4. 与事务、领域事件、状态历史、权限逐步打通
5. 把状态机从轻量工具升级为框架级业务建模能力

这条路线的优势在于：

- 对现有代码破坏最小
- 与 YWeb ORM 风格一致
- 更适合订单、审批、履约、发布等典型中后台业务
- 可与轻量领域事件、`OwnsOne` 一起形成一套更完整的建模体系
