# YWeb 轻量领域事件、`OwnsOne` 与状态机 v2 设计文档

本文档描述在 YWeb 中补充三项能力的设计方案：

1. 轻量领域事件（Lightweight Domain Events）
2. 值对象拥有关系 `OwnsOne`
3. 状态机 v2（State Machine V2）

本文档面向当前 `Active Record + DDD 分层思想` 的 YWeb 架构，目标不是把框架升级为“重 DDD 框架”，而是在保持简单、低心智负担的前提下，补足复杂业务演进中最容易出现的三块短板。

---

## 1. 背景

当前 YWeb 已具备以下基础能力：

- `CoreModel` / `BaseModel` 的 Active Record 模型体系
- `fields.OneToOne` / `fields.ManyToOne` / `fields.ManyToMany` 关系定义
- `transaction_manager` 事务管理器
- `before_commit` / `after_commit` / `after_rollback` 等事务钩子
- `validate_xxx()` + Service 层的 DDD 分层约定

这套能力已经足以支撑绝大多数 CRUD 和后台管理场景，但当业务复杂度逐步上升时，容易暴露三类不足：

### 1.1 缺少领域事件

当前框架已有“事务钩子”，但还没有“业务语义事件”这一层统一抽象。

也就是说，现在能表达：

- 某个事务已经提交成功
- 某段代码需要在提交后执行

但还不能很好表达：

- `OrderPaid`
- `UserRegistered`
- `DepartmentLeaderChanged`
- “某个聚合刚刚发生了一个值得被其他模块感知的业务事实”

缺少这层抽象后，常见问题是：

- Service 方法越来越像“总控脚本”
- 通知、审计、缓存、积分、索引刷新等副作用逐渐堆在主流程里
- 跨模块协作依赖显式调用，耦合变重
- 将来如果要接入 Outbox / MQ，需要重新梳理业务事实边界

### 1.2 缺少 `OwnsOne`

当前关系字段主要覆盖的是“实体与实体之间的关系”：

- `OneToOne`
- `ManyToOne`
- `ManyToMany`

但 DDD 中还有一类很常见的建模需求：实体拥有一个值对象。

典型例子：

- 订单拥有一个收货地址
- 用户拥有一个实名信息对象
- 商品拥有一个价格区间对象
- 审批单拥有一个时间窗口对象

这些对象通常具有以下特征：

- 没有独立主键
- 不需要独立表
- 生命周期依附父实体
- 更像聚合内部状态，而不是独立实体

当前没有 `OwnsOne` 时，通常只能二选一：

- 把字段平铺在父模型上
- 退化为子表 + `OneToOne`

前者丢失语义，后者又会把“值对象”错误建模成“独立实体”。

### 1.3 状态机能力已有基础，但还不够“框架化”

当前 YWeb 实际上已经具备一套轻量状态机能力，包括：

- `StateFieldMixin`
- `IntStateFieldMixin`
- `StateMachineMixin`
- `StateHistoryMixin`

它已经可以覆盖很多基础场景：

- 订单状态流转
- 审批单状态变更
- 员工在职 / 离职状态
- 发布 / 下线 / 归档状态

但从“框架能力”角度看，当前版本仍偏向轻量工具，而不是一个可沉淀、可扩展、可与事务/领域事件协同的统一机制。主要短板包括：

- 更偏“目标状态驱动”，缺少 `pay()` / `approve()` / `ship()` 这类动作语义
- 主要依赖 `__state_transitions__` 和命名约定，声明式体验仍可增强
- 与事务管理、领域事件、权限校验的联动还不够自然
- 缺少“当前可执行动作列表”等面向 API / 前端的元数据输出
- 缺少面向并发和版本控制的一体化约束建议

因此，对 YWeb 来说，不是“要不要增加状态机机制”，而是应该把现有状态机升级成更像框架能力的第二版。

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| 保持轻量 | 不引入完整事件总线、仓储体系、聚合根基础设施 |
| 保持兼容 | 不破坏现有 `save/add/delete/query` 使用方式 |
| 复用现有能力 | 领域事件复用事务钩子，`OwnsOne` 复用 SQLAlchemy 复合映射能力 |
| 强化语义 | 让“业务事实”和“值对象组合”在代码里更显式 |
| 分阶段落地 | 第一阶段优先解决 80% 的高频问题 |

---

## 3. 非目标

本次设计明确不追求以下能力：

- 不引入完整 Event Bus / Message Bus 架构
- 不强制所有模型都必须成为事件源
- 不把所有副作用都改造成领域事件
- 不在第一阶段支持 `OwnsMany`
- 不在第一阶段支持深层嵌套 `OwnsOne`
- 不引入事件溯源（Event Sourcing）
- 不内置分布式消息投递、重试中心、死信队列

---

## 4. 总体原则

### 4.1 领域事件是业务语义，不是事务钩子别名

事务钩子表达的是“什么时候执行代码”。

领域事件表达的是“发生了什么业务事实”。

例如：

- `after_commit` 是事务时机
- `OrderPaid` 是领域事实

前者是实现机制，后者是业务建模。

### 4.2 `OwnsOne` 是值对象组合，不是一对一外键关系

`OwnsOne` 和 `OneToOne` 的差别不是“都是 1 对 1，只是换个名字”。

它们在语义上不同：

- `OneToOne`：两个实体，两张表，外键关联
- `OwnsOne`：一个实体 + 一个值对象，一张表，字段内嵌

### 4.3 与当前 YWeb 架构保持一致

补充这两项能力时，仍应遵守当前框架的基本定位：

- API 层负责参数和响应
- Service 层负责跨聚合编排和事务边界
- Domain Model 负责单聚合业务规则
- ORM 层提供低样板、高可用的建模能力

也就是说，这次设计是“补洞”，不是“重构世界观”。

---

## 5. 轻量领域事件设计

## 5.1 设计定位

轻量领域事件的核心诉求只有三件事：

1. 模型或 Service 可以记录领域事件
2. 事件在事务成功提交后统一发布
3. 其他模块可以注册本地处理器来响应事件

只要做到这三点，就能解决当前最容易出现的几个痛点：

- 主业务流程和副作用解耦
- 保证“提交成功后再处理”
- 为未来 Outbox / MQ 演进留出自然路径

## 5.2 与现有事务钩子的关系

当前框架已经有事务钩子，因此不需要重新发明“提交后触发”的底层机制。

推荐关系如下：

- 事务钩子：基础设施级时机能力
- 领域事件：业务级事实能力
- 领域事件发布：底层通过 `after_commit` 实现

换句话说：

- 不用领域事件替代事务钩子
- 也不直接把事务钩子暴露为领域建模能力
- 而是在两者之间增加一层轻量的“业务事实抽象”

## 5.3 核心概念

| 概念 | 说明 |
|------|------|
| `DomainEvent` | 领域事件基类，表示一个业务事实 |
| `DomainEventRecorder` | 事件记录接口，用于暂存待发布事件 |
| `DomainEventDispatcher` | 领域事件分发器，负责把事件交给处理器 |
| `domain_event_handler()` | 处理器注册装饰器 |
| `TransactionEventQueue` | 当前事务上下文中的待发布事件队列 |

## 5.4 建议 API

### 5.4.1 事件定义

```python
from dataclasses import dataclass, field
from datetime import datetime
from uuid import uuid4

from yweb.orm.domain_events import DomainEvent


@dataclass(slots=True)
class UserRegistered(DomainEvent):
    user_id: int
    username: str
    occurred_on: datetime = field(default_factory=datetime.utcnow)
    event_id: str = field(default_factory=lambda: str(uuid4()))

    @classmethod
    def from_model(cls, model: "User") -> "UserRegistered":
        return cls(user_id=model.id, username=model.username)
```

建议约束：

- 使用 `dataclass`
- 事件对象默认只读或约定只读
- 包含 `event_id`、`occurred_on`
- 只携带必要业务数据，不直接塞整个 ORM 实体
- 推荐提供 `from_model()` 工厂方法，封装模型到事件的字段映射

### 5.4.2 在模型中记录事件（基础写法）

```python
class User(BaseModel):
    def mark_registered(self):
        self.add_domain_event(
            UserRegistered(user_id=self.id, username=self.username)
        )
```

### 5.4.3 在 Service 中记录事件（基础写法）

```python
@tm.transactional()
def register_user(data: dict) -> User:
    user = User(**data)
    user.save()
    user.add_domain_event(
        UserRegistered(user_id=user.id, username=user.username)
    )
    return user
```

### 5.4.4 便捷事件记录方式

上面两种写法每次都要手动构造事件对象、手动传字段、手动调 `add_domain_event()`，在事件类型多或动作多时会比较繁琐。

建议框架提供以下便捷机制，按需组合使用。

#### 便捷方式 1：`from_model()` 工厂方法

事件类提供 `from_model()`，封装"从模型实例提取字段"的逻辑：

```python
@dataclass(slots=True)
class UserRegistered(DomainEvent):
    user_id: int
    username: str

    @classmethod
    def from_model(cls, model: "User") -> "UserRegistered":
        return cls(user_id=model.id, username=model.username)
```

使用时只需一行：

```python
self.add_domain_event(UserRegistered.from_model(self))
```

如果事件需要额外参数，`from_model()` 也可以接受：

```python
@dataclass(slots=True)
class OrderShipped(DomainEvent):
    order_id: int
    tracking_no: str

    @classmethod
    def from_model(cls, model: "Order", *, tracking_no: str) -> "OrderShipped":
        return cls(order_id=model.id, tracking_no=tracking_no)
```

```python
self.add_domain_event(OrderShipped.from_model(self, tracking_no=tracking_no))
```

特点：

- 零框架魔法，纯 Python
- IDE 跳转和类型提示完整
- 事件与模型的映射关系显式可审查

#### 便捷方式 2：`emit()` 快捷方法

在模型基类上提供 `emit()` 方法，进一步减少样板代码：

```python
self.emit(UserRegistered)
```

框架内部处理逻辑：

1. 检查事件类是否有 `from_model()` 方法
2. 如果有，调用 `EventClass.from_model(self)` 构造事件
3. 如果没有，尝试按字段名自动匹配模型属性
4. 调用 `add_domain_event()`

如果需要传额外参数：

```python
self.emit(OrderShipped, tracking_no="SF123456")
```

框架会把额外关键字参数一并传给 `from_model()`。

特点：

- 最简洁的调用方式
- 简单事件零配置
- 复杂事件通过 `from_model()` 精确控制

#### 便捷方式 3：`@emits()` 装饰器

用于模型上的领域动作方法，方法执行成功后自动登记事件：

```python
from yweb.orm.domain_events import emits


class User(BaseModel):
    @emits(UserRegistered)
    def mark_registered(self):
        pass
```

框架在装饰器内部做：

1. 先执行方法本体
2. 方法无异常，则通过 `from_model()` 或字段自动匹配构造事件
3. 调用 `add_domain_event()`

如果事件需要方法执行过程中产生的参数，可通过返回值或上下文传递：

```python
class Order(BaseModel):
    @emits(OrderShipped)
    def ship(self, *, tracking_no: str, operator_id: int):
        self.tracking_no = tracking_no
        self.shipped_by = operator_id
```

框架约定：

- 优先调用 `EventClass.from_model(self)`
- 如果事件类没有 `from_model()`，尝试按字段名自动匹配
- 如果都无法构造，报明确错误

特点：

- 方法体内不需要写任何事件代码
- 声明式，一眼看出"这个方法会触发什么事件"
- 与状态机 v2 的 `@transition(event=...)` 风格完全统一

#### 三种方式对比

| 方式 | 调用简洁度 | 显式程度 | IDE 友好 | 适用场景 |
|------|-----------|---------|---------|---------|
| `from_model()` | 中 | 高 | 高 | 通用基础，所有场景 |
| `emit()` | 高 | 中 | 中 | Service 层或模型内快捷发事件 |
| `@emits()` | 最高 | 高 | 高 | 模型领域动作方法 |

#### 推荐组合

建议框架同时提供这三种能力：

- `from_model()` 作为基础约定，所有事件类都推荐提供
- `emit()` 作为模型快捷方法，适合 Service 层和简单场景
- `@emits()` 作为动作装饰器，适合模型上的领域动作

三种场景的推荐写法：

```python
# 场景 1：模型动作方法 —— 零样板
@emits(UserRegistered)
def mark_registered(self):
    pass

# 场景 2：Service 层快捷发事件 —— 一行
user.emit(UserRegistered)

# 场景 3：需要额外参数 —— 仍然简洁
self.add_domain_event(OrderShipped.from_model(self, tracking_no=tracking_no))
```

这套设计与状态机 v2 的 `@transition(event=OrderPaid)` 天然统一，因为 `@transition` 内部也可以复用同样的事件构造机制。

### 5.4.5 处理器注册

```python
from yweb.orm.domain_events import domain_event_handler


@domain_event_handler(UserRegistered)
def init_user_profile(event: UserRegistered):
    ...


@domain_event_handler(UserRegistered)
def send_welcome_message(event: UserRegistered):
    ...
```

## 5.5 运行时行为

### 5.5.1 有事务时

在 `@transactional()` 或 `with tm.transaction()` 场景中：

1. 领域事件先记录到当前事务上下文
2. 事务成功提交后统一分发
3. 如果事务回滚，则待发布事件全部丢弃

这是推荐路径，也是语义最稳的路径。

### 5.5.2 无事务时

第一阶段建议采用保守兼容策略：

- 允许记录领域事件
- 保存成功后可立即分发
- 同时对外明确建议：涉及领域事件的业务应尽量运行在事务中

可选配置建议：

| 配置项 | 含义 | 默认值 |
|------|------|------|
| `dispatch_events_without_transaction` | 无事务时是否立即分发 | `True` |
| `warn_on_event_without_transaction` | 无事务记录事件时是否输出警告 | `True` |

## 5.6 推荐实现位置

建议新增或修改如下模块：

- 新增 `yweb/orm/domain_events.py`
- 修改 `yweb/orm/transaction/context.py`
- 修改 `yweb/orm/transaction/manager.py`
- 修改 `yweb/orm/core_model.py`
- 修改 `yweb/orm/__init__.py`

各模块职责建议如下：

### `yweb/orm/domain_events.py`

负责：

- `DomainEvent` 基类（含 `from_model()` 约定）
- `@emits()` 装饰器
- `@domain_event_handler()` 处理器注册装饰器
- 处理器注册表
- 事件分发器

### `yweb/orm/core_model.py`

负责：

- 增加 `add_domain_event()` / `pull_domain_events()` 等基础能力
- 增加 `emit()` 快捷方法
- 让模型实例可作为轻量事件源

### `yweb/orm/transaction/context.py`

负责：

- 在事务上下文中保存待发布事件
- 提交成功后统一分发
- 回滚后清空事件队列

## 5.7 失败处理策略

第一阶段建议采用“本地同步分发 + 失败记录日志”的策略：

| 场景 | 处理方式 |
|------|------|
| 提交前失败 | 不发布事件 |
| 提交后某处理器失败 | 记录日志，不回滚已提交事务 |
| 多处理器执行顺序 | 默认注册顺序，可预留优先级扩展 |
| 处理器重复执行 | 由处理器自身保证幂等 |

这样做的原因是：

- 与现有 `after_commit` 语义一致
- 实现简单，可快速落地
- 为未来接入 Outbox 保留空间

## 5.8 优势

补充轻量领域事件后，框架可以得到以下收益：

- Service 主流程更短、更聚焦
- 审计、通知、缓存、索引等副作用更容易解耦
- 领域事实在代码层更显式
- 后续接入 Outbox / MQ 时迁移成本更低

## 5.9 暂不实现的能力

第一阶段不建议引入：

- 跨进程事件总线
- 异步消息投递
- 持久化 Outbox 表
- 全局自动扫描模块并装配处理器
- 分布式重试和死信治理

---

## 6. `OwnsOne` 设计

## 6.1 设计定位

`OwnsOne` 用于表达：

- 当前实体拥有一个值对象
- 值对象没有独立表
- 值对象没有独立主键
- 值对象生命周期完全依附父实体

典型使用场景：

- `Order.shipping_address`
- `User.real_name_info`
- `Product.price_range`
- `Approval.time_window`

## 6.2 为什么不能只用 `OneToOne`

`OneToOne` 解决的是实体间关联问题：

- 独立表
- 独立主键
- 外键关系
- 可独立查询和持久化

但值对象并不需要这些能力。对值对象而言，真正重要的是：

- 结构化表达
- 单表存储
- 生命周期依附
- 领域语义清晰

因此 `OwnsOne` 不是 `OneToOne` 的语法糖，而是另一种建模方式。

## 6.3 设计目标

| 目标 | 说明 |
|------|------|
| 显式表达值对象语义 | 区分“聚合内部状态”与“独立实体” |
| 单表存储 | 展开为父表字段，不增加子表 |
| 对象化访问 | Python 层可使用 `order.shipping_address.city` |
| 兼容现有 ORM | 底层优先基于 SQLAlchemy `composite()` 或等效封装 |
| 支持后续序列化 | `to_dict()` / DTO 后续可识别嵌套值对象 |

## 6.4 建议 API

### 6.4.1 值对象定义

```python
from yweb.orm.owned_types import OwnedType, owned_field
from sqlalchemy import String


class Address(OwnedType):
    street = owned_field(String(200), comment="街道")
    city = owned_field(String(100), comment="城市")
    province = owned_field(String(100), comment="省份")
    zip_code = owned_field(String(20), comment="邮编", nullable=True)
```

### 6.4.2 在父模型中使用

```python
class Order(BaseModel):
    shipping_address = fields.OwnsOne(
        Address,
        prefix="shipping",
        nullable=False,
    )
```

语义上等价于为 `orders` 表生成以下列：

- `shipping_street`
- `shipping_city`
- `shipping_province`
- `shipping_zip_code`

同时在 Python 层暴露：

```python
order.shipping_address.city
order.shipping_address.street
```

## 6.5 运行机制

### 6.5.1 存储层

`OwnsOne` 不创建外键，也不创建子表，而是把值对象字段直接展开到当前表。

例如：

| 值对象属性 | 生成列 |
|------|------|
| `shipping_address.street` | `shipping_street` |
| `shipping_address.city` | `shipping_city` |
| `shipping_address.province` | `shipping_province` |
| `shipping_address.zip_code` | `shipping_zip_code` |

### 6.5.2 Python 对象层

建议底层使用 SQLAlchemy `composite()` 或等效机制完成：

- 读取记录时组装值对象实例
- 给 `shipping_address` 赋值时同步更新展开列
- 以值相等为核心，而不是实体标识相等

### 6.5.3 空值策略

建议规则如下：

| 场景 | 行为 |
|------|------|
| `nullable=False` | 值对象关键列必须完整满足约束 |
| `nullable=True` | 整组列都为 `NULL` 时返回 `None` |
| 部分列为空 | 由值对象自身定义和校验逻辑决定 |

推荐默认语义：

- `nullable=True` 时，如果整组展开列全为 `NULL`，则属性返回 `None`
- 否则返回一个完整值对象实例

## 6.6 命名规则

### 6.6.1 列名前缀

建议规则：

- 显式传入 `prefix="shipping"` 时，生成 `shipping_*`
- 未显式传入时，默认使用属性名作为前缀

示例：

```python
billing_address = fields.OwnsOne(Address)
```

默认生成：

- `billing_address_street`
- `billing_address_city`

如果想要更短的列名，可显式指定：

```python
billing_address = fields.OwnsOne(Address, prefix="billing")
```

### 6.6.2 注释规则

建议 `owned_field(..., comment="街道")` 在生成列注释时支持：

- 保留原注释
- 或自动拼接前缀，如“收货地址-街道”

推荐默认采用拼接模式，避免数据库层字段语义过弱。

## 6.7 值对象类型约束

`OwnedType` 建议满足以下约束：

- 不是 ORM Model
- 没有 `id`
- 不参与 `metadata.create_all()`
- 不允许声明 relationship
- 支持 `__composite_values__()`、`__eq__()`、`__repr__()`

如需增强领域表达，建议值对象实例默认不可变。

## 6.8 与现有 `OneToOne` 的边界

| 对比项 | `OneToOne` | `OwnsOne` |
|------|------|------|
| 数据表 | 两张表 | 一张表 |
| 子对象主键 | 有 | 无 |
| 生命周期 | 可相对独立 | 完全依附父对象 |
| 查询方式 | 通过关系或 join | 父表直接读取 |
| 适用场景 | 用户档案、扩展实体 | 地址、金额区间、时间范围、联系人 |

判断建议：

- 子对象需要独立增删改查，用 `OneToOne`
- 子对象只是父实体的一部分，用 `OwnsOne`

## 6.9 与序列化 / DTO 的集成建议

后续建议逐步支持：

1. `to_dict()` 自动输出嵌套值对象
2. `to_dict(flatten_owned=True)` 输出平铺字段
3. DTO / Schema 自动识别 `OwnedType`

例如：

```python
{
    "id": 1,
    "order_no": "ORD-001",
    "shipping_address": {
        "street": "世纪大道 1 号",
        "city": "上海",
        "province": "上海"
    }
}
```

---

## 7. 轻量领域事件与 `OwnsOne` 的关系

这两项能力是互补的：

- `OwnsOne` 负责表达聚合内部状态
- 领域事件负责表达聚合发生了什么业务事实

例如：

```python
class Order(BaseModel):
    shipping_address = fields.OwnsOne(Address, prefix="shipping")

    def change_shipping_address(self, new_address: Address):
        self.shipping_address = new_address
        self.add_domain_event(
            OrderShippingAddressChanged(order_id=self.id)
        )
```

这样可以同时得到：

- 清晰的聚合内部建模
- 清晰的业务事实表达

---

## 8. 分阶段落地建议

## 8.1 第一阶段：先实现轻量领域事件

原因：

- 最大程度复用现有事务钩子
- 落地成本低
- 对框架收益最大
- 不涉及数据库结构扩展复杂度

建议新增或修改：

- `yweb/orm/domain_events.py`
- `yweb/orm/core_model.py`
- `yweb/orm/transaction/context.py`
- `yweb/orm/transaction/manager.py`
- `yweb/orm/__init__.py`

## 8.2 第二阶段：实现 `OwnsOne`

建议新增或修改：

- 新增 `yweb/orm/owned_types.py`
- 修改 `yweb/orm/fields.py`
- 修改 `yweb/orm/core_model.py`
- 更新 `yweb/orm/__init__.py`
- 更新 `docs/orm_docs/03_relationships.md`
- 新增 `tests/test_orm/unit/test_owns_one.py`

## 8.3 第三阶段：按业务压力扩展

后续可选扩展：

- Outbox 模式
- 异步事件分发
- 事件处理器优先级
- 值对象校验与 DTO 自动推导
- 查询辅助 API

明确不在当前路线中的能力：

- `OwnsMany`
- 复杂深层嵌套值对象
- 重型事件总线

---

## 9. 测试建议

### 9.1 轻量领域事件

至少覆盖以下场景：

- 事务提交成功后发布事件
- 事务回滚后不发布事件
- 多个事件按顺序分发
- 某个处理器失败不影响已提交事务
- 无事务场景下的立即分发行为

### 9.2 `OwnsOne`

至少覆盖以下场景：

- 自动展开列名
- 读取时正确组装值对象
- 重新赋值值对象后可持久化
- `nullable=True` 时整组为空返回 `None`
- `to_dict()` / 查询 / 更新行为符合预期

注意：

- 测试辅助类不要以 `Test` 开头命名
- 值对象测试更适合采用“替换式赋值”而不是原地修改

---

## 10. 风险与注意事项

| 风险点 | 说明 | 建议 |
|------|------|------|
| 事件滥用 | 所有业务都发事件会导致语义泛滥 | 只对关键业务事实发事件 |
| 事务外事件语义较弱 | 无事务时很难严格保证“提交后再发” | 明确推荐事务内使用 |
| `OwnsOne` 过度嵌套 | 会增加序列化、查询、迁移复杂度 | 第一阶段只支持单层 |
| 值对象变更追踪复杂 | SQLAlchemy 对复合对象的原地变更追踪较敏感 | 优先采用替换式赋值 |
| 查询表达式不够直观 | 嵌套对象查询最终仍会落回平铺列 | 后续提供字段映射辅助 |

---

## 11. 结论

对当前 YWeb 的定位而言，最合适的方向不是引入一整套重量级 DDD 基础设施，而是在现有架构上补充三项“轻量但高价值”的能力：

1. 轻量领域事件
   - 解决“提交后副作用解耦”的核心问题
   - 保持与现有事务管理器兼容
   - 为 Outbox / MQ 演进保留空间

2. `OwnsOne`
   - 补足值对象组合表达力
   - 保持单表存储和简单使用体验
   - 避免把值对象错误建模成独立实体

3. 状态机 v2
   - 在现有 `StateMachineMixin` 基础上升级，而不是另起炉灶
   - 强化动作语义、声明式配置、事务一致性和可观察性
   - 与轻量领域事件自然协同，形成更完整的业务建模能力

推荐实施顺序：

1. 先实现轻量领域事件
2. 再实现 `OwnsOne`
3. 再升级状态机到 v2
4. 最后根据实际业务复杂度决定是否继续扩展

---

## 12. 状态机 v2 设计补充

## 12.1 设计定位

状态机 v2 不是一套全新的工作流引擎，也不是为了替换现有 `StateMachineMixin`。

它的定位是：

- **继续增强现有状态机**
- **把轻量状态机升级成更像框架能力的第二版**
- **让状态流转、领域事件、事务提交、历史记录、权限控制能够自然协同**

也就是说，v2 的目标不是“做一个什么都能配的流程平台”，而是为 YWeb 中最常见的业务状态流转提供一套更统一、更声明式、更可扩展的建模机制。

## 12.2 为什么不直接引入第三方状态机库

当前 Python 生态中，比较值得参考的状态机开源库主要有两类：

- `transitions`：功能成熟、社区活跃、通用 FSM 设计优秀
- `sqlalchemy-fsm`：更贴近 SQLAlchemy 模型场景，声明式迁移体验较好

但对 YWeb 来说，直接把第三方库作为框架主 API 并不是最优解，原因包括：

- YWeb 已经有自己的 `StateMachineMixin` 体系
- 当前状态机与 ORM、Mixin、历史记录的风格是一致的
- 直接换库会把框架编程模型拉散
- 第三方库很难天然匹配 YWeb 的事务管理器、轻量领域事件和 Active Record 习惯

因此更合适的路线是：

- **参考成熟库的设计**
- **保留 YWeb 自己的公开 API 风格**
- **在现有模块上渐进升级**

## 12.3 v2 的设计目标

| 目标 | 说明 |
|------|------|
| 保持兼容 | 尽量兼容现有 `StateFieldMixin` / `StateMachineMixin` 用法 |
| 动作语义优先 | 从“切到某状态”提升为“执行某动作” |
| 声明式增强 | 提供 `@transition` 风格 API，减少散落配置 |
| 与事务集成 | 迁移后的副作用和事件可挂接到事务提交语义 |
| 与领域事件集成 | 状态变更成功后可自然发布领域事件 |
| 支持元数据输出 | 可提供“当前允许动作”“动作说明”“状态标签”等信息 |
| 适合中后台业务 | 覆盖订单、审批、发布、履约等典型状态流转 |

## 12.4 非目标

状态机 v2 明确不追求以下能力：

- 不实现完整 BPM / Workflow 引擎
- 不在第一阶段支持可视化流程编排
- 不支持任意节点脚本执行
- 不支持会签、或签、流程回退编排等复杂审批引擎能力
- 不支持分层状态机和并行状态机的完整 DSL

这些能力如果未来真有需求，应单独设计“流程引擎”模块，而不是塞进 ORM 状态机。

## 12.5 当前状态机与 v2 的差距

当前版本的优势：

- 轻量
- 易懂
- 已支持守卫、钩子、状态历史
- 适合基础状态字段场景

当前版本的不足：

- 迁移入口更偏 `transition_to(target_state)`，动作语义不够强
- 规则以 `__state_transitions__` 为主，复杂业务下可读性会下降
- 钩子多依赖命名约定，不利于显式声明与 IDE 跟踪
- 缺少迁移动作级元数据
- 缺少与权限、领域事件、乐观锁的一体化建模建议

因此 v2 的核心任务不是“补更多特性”，而是“让状态机更像一项可复用的框架能力”。

## 12.6 核心思路：从“状态跳转”升级到“动作驱动迁移”

### 当前写法

```python
order.transition_to(Order.Status.PAID, reason="用户支付")
```

### v2 推荐写法

```python
order.pay(operator_id=current_user_id, reason="用户支付")
```

动作驱动的价值在于：

- 更贴近业务语言
- 更适合封装参数校验和守卫逻辑
- 更适合在动作成功后发布领域事件
- 更适合给 API / 前端暴露“当前可执行动作”

状态本身仍然保留，但更多作为：

- 存储结果
- 查询条件
- 守卫依据
- 展示信息

而不是业务代码里唯一的入口。

## 12.7 建议 API

### 12.7.1 保留现有基础能力

继续保留：

- `StateFieldMixin`
- `IntStateFieldMixin`
- `StateMachineMixin`
- `StateHistoryMixin`
- `transition_to()`
- `can_transition_to()`

这样可保证现有项目基本无需立即迁移。

### 12.7.2 新增 `@transition` 装饰器

建议引入声明式动作定义：

```python
from yweb.orm.statemachine import transition


class Order(BaseModel, StateFieldMixin, StateMachineMixin):
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
        permission="order.pay",
        event="OrderPaid",
    )
    def pay(self, *, operator_id: int, reason: str | None = None):
        self.paid_by = operator_id
        self.pay_reason = reason
```

建议支持的装饰器参数：

| 参数 | 说明 |
|------|------|
| `source` | 允许的源状态，可为单值、列表或 `"*"` |
| `target` | 目标状态 |
| `label` | 动作名称，用于 UI / API 输出 |
| `description` | 动作说明 |
| `permission` | 权限码，可选 |
| `guard` | 显式守卫函数名或可调用对象 |
| `event` | 成功后要发布的领域事件类型或名称 |
| `save` | 是否默认自动保存 |
| `record_history` | 是否记录状态历史 |

### 12.7.3 支持动作元数据查询

建议新增：

- `get_available_actions()`
- `get_action_definition("pay")`
- `can_execute_action("pay")`

示例返回值：

```python
[
    {
        "name": "pay",
        "label": "支付",
        "source": "pending",
        "target": "paid",
        "permission": "order.pay",
    }
]
```

这样前端或 API 层可以直接知道：

- 当前状态下有哪些可执行动作
- 每个动作的显示名称是什么
- 调用后会到哪个目标状态

## 12.8 守卫、权限与校验分层

状态机 v2 建议明确区分三类检查：

### 1. 状态规则检查

只关注“从 A 是否允许到 B”。

例如：

- `pending -> paid` 合法
- `completed -> pending` 非法

### 2. 业务守卫检查

只关注“这次业务条件是否满足”。

例如：

- 发货前必须存在收货地址
- 审批通过前必须填写审批意见
- 完成前必须存在支付记录

### 3. 权限检查

只关注“当前操作者是否有权执行这个动作”。

例如：

- 财务才能执行 `confirm_payment`
- 仓库管理员才能执行 `ship`
- 部门主管才能执行 `approve`

建议 API 上显式区分，不要把三种逻辑都塞进一个 `guard_*` 方法里。

## 12.9 与轻量领域事件的集成

这是状态机 v2 最值得增强的一点。

推荐语义：

1. 动作执行成功
2. 状态切换成功
3. 历史记录写入成功
4. 注册对应领域事件
5. 事务提交后统一发布

示例：

```python
@transition(
    source=Status.PAID,
    target=Status.SHIPPED,
    event=OrderShipped,
)
def ship(self, *, tracking_no: str, operator_id: int):
    self.tracking_no = tracking_no
    self.shipped_by = operator_id
```

当 `ship()` 成功时：

- 模型状态变为 `shipped`
- 写入状态历史
- 记录 `OrderShipped(order_id=self.id, tracking_no=tracking_no)`
- 事务提交后再触发通知、物流同步、缓存失效等处理器

这会让“状态迁移”自然成为“领域事实”的触发点。

## 12.10 与事务和并发控制的集成

状态机最怕两个问题：

- 状态改了但副作用没跟上
- 并发请求重复迁移同一对象

因此 v2 应明确与现有事务机制协同：

- 推荐所有关键状态迁移都在 `@transactional()` 中执行
- 动作成功后只记录领域事件，不直接做不可回滚副作用
- 副作用统一放到提交后事件处理器中执行

并发控制建议：

- 默认配合已有 `ver` 乐观锁机制使用
- 状态迁移失败时，清晰抛出并发相关异常或业务异常
- 文档中明确建议：高价值迁移动作必须纳入事务边界

## 12.11 与状态历史的关系

当前 `StateHistoryMixin` 已具备基础历史能力，v2 应继续复用，而不是另建一套历史系统。

建议增强点：

- 记录动作名，例如 `pay` / `ship` / `approve`
- 除 `from_state` / `to_state` 外，补充 `transition_name`
- 历史记录中保留 `operator_id`、`reason`、关键上下文
- 明确历史写入的事务语义，避免出现“状态未提交但历史已落库”的歧义

建议后续把历史记录语义从“状态变化记录”提升为“状态迁移动作记录”。

## 12.12 推荐模块演进

建议基于现有目录演进：

- `yweb/orm/statemachine/state_machine.py`
- `yweb/orm/statemachine/state_field.py`
- `yweb/orm/statemachine/state_history.py`
- 新增 `yweb/orm/statemachine/transition.py`
- 新增 `yweb/orm/statemachine/metadata.py`

建议职责：

### `transition.py`

负责：

- `@transition` 装饰器
- 动作定义元数据
- 动作注册表

### `metadata.py`

负责：

- 当前模型状态机元数据解析
- 输出可执行动作列表
- 支持 API 层读取状态与动作描述

### `state_machine.py`

继续负责：

- 状态读取与设置
- 基础迁移执行
- 守卫与钩子调度
- 向 v2 迁移的兼容层

## 12.13 推荐分阶段落地

### 第一阶段：兼容式增强

目标：

- 不破坏现有 `transition_to()` 使用方式
- 增加 `@transition` 装饰器
- 增加动作元数据输出

建议改动：

- 新增装饰器与元数据解析
- 在现有 `StateMachineMixin` 中接入动作驱动入口

### 第二阶段：与领域事件打通

目标：

- 支持动作成功后记录领域事件
- 事务提交后再统一发布

建议改动：

- 对接前文的轻量领域事件机制
- 允许 transition 定义声明 `event=...`

### 第三阶段：与权限 / 历史 / 乐观锁打通

目标：

- 增强生产级可用性
- 为审批、订单、发布等核心业务提供统一机制

建议改动：

- 动作权限判断
- 历史记录增强
- 乐观锁和并发失败语义补充

## 12.14 开源库参考建议

推荐参考而非直接替换：

### 参考 `sqlalchemy-fsm`

重点参考：

- `@transition` 风格 API
- 模型动作声明方式
- ORM 状态字段整合思路

适合借鉴原因：

- 更接近 YWeb 的 SQLAlchemy 场景
- 更接近“模型动作驱动迁移”的目标

### 参考 `transitions`

重点参考：

- 状态机概念设计
- 回调组织方式
- 守卫与事件回调的抽象方式

适合借鉴原因：

- 通用状态机抽象更成熟
- 对未来扩展分层状态机有参考价值

但不建议当前直接把它作为 YWeb 的对外主 API。

## 12.15 结论

对于 YWeb 来说，状态机的最优路线不是“再引入一个新的状态机系统”，而是：

1. 保留现有 `StateMachineMixin` 体系
2. 在其上补充 `@transition` 声明式动作能力
3. 让状态迁移与事务、领域事件、历史记录自然协同
4. 把状态机从“轻量工具”升级为“框架级业务建模能力”

这样做的好处是：

- 成本比重做更低
- 与当前框架风格一致
- 能自然服务于订单、审批、履约、发布等主流业务场景
- 还能与本文前述的轻量领域事件、`OwnsOne` 一起形成更完整的业务建模闭环

