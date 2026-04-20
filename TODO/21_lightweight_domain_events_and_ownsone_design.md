# 21. 轻量领域事件与 `OwnsOne` 设计方案

本文档描述在 YWeb ORM 中补充两项能力的设计方案：

1. **轻量领域事件（Lightweight Domain Events）**
2. **值对象拥有关系 `OwnsOne`**

设计目标不是把 YWeb 改造成“重 DDD 框架”，而是在保持 **Active Record + SQLAlchemy + 简洁开发体验** 的前提下，补足复杂业务演进时最容易缺失的两项能力。

---

## 1. 背景

当前 YWeb ORM 已具备以下能力：

- 基于 `CoreModel` / `BaseModel` 的 Active Record 模型体系
- `fields.OneToOne` / `fields.ManyToOne` / `fields.ManyToMany` 关系定义
- 事务管理器 `TransactionManager`
- `before_commit` / `after_commit` / `after_rollback` 等事务钩子

这套能力已经足够支撑绝大多数 CRUD 和后台管理场景，但在业务复杂度上升后，会逐渐暴露两个空缺：

### 1.1 领域事件空缺

当前框架有“事务生命周期钩子”，但没有“业务语义事件”：

- 有 `after_commit`
- 没有 `OrderCreated`
- 没有 `UserRegistered`
- 没有“提交成功后统一发布业务事件”的模型

结果是：

- 业务副作用容易堆在 Service 方法里
- 跨模块协作依赖显式调用，耦合变重
- 事务提交后行为缺少统一表达
- 难以演进到 Outbox、消息队列、审计轨迹

### 1.2 `OwnsOne` 空缺

当前框架支持：

- 一对一：`OneToOne`
- 多对一：`ManyToOne`
- 多对多：`ManyToMany`

但这些都属于“实体之间的关系”。对于 DDD 中常见的“值对象组合”场景，目前只能：

- 直接把字段平铺在父模型上
- 或者退化成独立子表 + `OneToOne`

这会带来两个问题：

- 无法显式表达“这是聚合内部的值对象，而不是独立实体”
- 地址、金额区间、联系人、审计信息等可复用值对象缺少统一抽象

---

## 2. 设计目标

| 目标 | 说明 |
|------|------|
| **保持轻量** | 不引入重量级 DDD 基础设施，不要求完整聚合根模型 |
| **兼容 Active Record** | 不破坏当前 `save/add/delete/query` 的使用方式 |
| **优先复用现有能力** | 领域事件复用事务钩子，`OwnsOne` 复用 SQLAlchemy 单表映射能力 |
| **默认简单** | 常见场景下写法尽量接近现有 `fields.*` 风格 |
| **逐步演进** | 第一阶段只覆盖 80% 高频需求，复杂需求后续扩展 |

---

## 3. 非目标

本次设计**不追求**以下能力：

- 不引入完整 Event Bus / Message Bus 架构
- 不强制所有业务都改造成聚合根驱动
- 不在第一阶段支持 `OwnsMany`
- 不在第一阶段支持深层嵌套值对象
- 不自动把所有模型变成事件源
- 不内置分布式消息投递、重试和死信处理

---

## 4. 总体原则

### 4.1 领域事件是“业务语义”，不是“技术钩子”

领域事件用于表达：

- “发生了什么业务事实”
- “这件事已经可以被其他模块感知”

它不等同于：

- SQLAlchemy `before_flush`
- `after_commit`
- ORM Hook

事务钩子是实现手段，领域事件是业务抽象。

### 4.2 `OwnsOne` 是“值对象内嵌”，不是“一对一外键”

`OwnsOne` 表示：

- 子对象没有独立表
- 子对象没有独立主键
- 生命周期依附父模型
- 存储上展开为父表字段

因此它与 `OneToOne` 的区别不是“都是 1 对 1”，而是：

- `OneToOne`：两个实体，两张表，外键关联
- `OwnsOne`：一个实体 + 一个值对象，一张表，字段内嵌

---

## 5. 轻量领域事件设计

## 5.1 设计定位

轻量领域事件的核心能力只有三点：

1. **模型或 Service 可记录领域事件**
2. **事件在事务成功提交后统一分发**
3. **其他模块可注册本地事件处理器**

这样即可解决当前最关键的问题：

- 主业务流程与副作用解耦
- 确保“提交成功后再处理”
- 为未来 Outbox 留出演进空间

## 5.2 核心概念

| 概念 | 说明 |
|------|------|
| `DomainEvent` | 领域事件基类，表示一个业务事实 |
| `EventRecorder` | 事件记录接口，负责暂存待发布事件 |
| `DomainEventDispatcher` | 事件分发器，提交成功后调度处理器 |
| `DomainEventHandler` | 本地处理器，响应某类领域事件 |
| `TransactionEventQueue` | 事务上下文中的事件队列 |

## 5.3 建议 API

### 5.3.1 事件定义

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
```

建议特性：

- 使用 `dataclass`
- 事件对象默认不可变或约定只读
- 包含 `event_id`、`occurred_on`
- 负载只放业务必要信息，不直接塞整个 ORM 实体

### 5.3.2 模型或 Service 记录事件

```python
class User(BaseModel):
    def mark_registered(self):
        self.add_domain_event(
            UserRegistered(user_id=self.id, username=self.username)
        )
```

或：

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

### 5.3.3 处理器注册

```python
from yweb.orm.domain_events import domain_event_handler


@domain_event_handler(UserRegistered)
def init_user_profile(event: UserRegistered):
    ...


@domain_event_handler(UserRegistered)
def send_welcome_message(event: UserRegistered):
    ...
```

### 5.3.4 事务提交后自动分发

```python
@tm.transactional()
def register_user(data: dict):
    user = User(**data)
    user.save()
    user.add_domain_event(UserRegistered(user_id=user.id, username=user.username))
    return user

# 提交成功后：
# 1. dispatcher 拉取事务中的待发布事件
# 2. 按注册顺序或优先级分发处理器
# 3. 处理失败记录日志，不影响已提交事务
```

## 5.4 运行时行为

### 5.4.1 有事务时

在 `@transactional()` 或 `with tm.transaction()` 场景中：

1. 事件先记录到当前事务上下文
2. 事务成功提交后统一分发
3. 如果事务回滚，则事件全部丢弃

这是推荐路径，也是框架保证语义最清晰的路径。

### 5.4.2 无事务时

建议第一阶段采用**保守策略**：

- 默认仍允许记录事件
- 但只在显式保存成功后立即分发
- 文档中明确推荐：**涉及领域事件的业务应放在事务中执行**

可选配置：

| 配置项 | 含义 | 默认值 |
|------|------|------|
| `dispatch_events_without_transaction` | 无事务时是否立即发布 | `True` |
| `warn_on_event_without_transaction` | 无事务记录事件时是否警告 | `True` |

## 5.5 与现有事务钩子的集成

当前框架已有事务钩子，因此不需要单独重建一套提交监听机制。

建议复用方式：

1. 在事务上下文 `TransactionContext` 中增加事件队列
2. 在 `after_commit` 阶段统一执行事件分发
3. 在 `after_rollback` 阶段清空未发布事件

推荐实现位置：

- `yweb/orm/transaction/context.py`
- `yweb/orm/transaction/manager.py`
- `yweb/orm/transaction/hooks.py`
- `yweb/orm/core_model.py`
- 新增 `yweb/orm/domain_events.py`

## 5.6 失败处理策略

第一阶段建议采用**本地同步分发**：

| 场景 | 策略 |
|------|------|
| 事务提交前失败 | 事件不发布 |
| 事务提交后某处理器失败 | 记录日志，不回滚已提交事务 |
| 某个处理器重复执行 | 由处理器自身保证幂等 |
| 分发顺序要求 | 支持简单优先级，默认注册顺序 |

说明：

- 这与现有 `after_commit` 语义一致
- 对外部系统集成，未来再升级为 Outbox

## 5.7 对现有框架的价值

补充轻量领域事件后，框架会获得以下能力：

- 业务主流程更短、更聚焦
- 审计、通知、缓存失效、索引刷新等副作用可解耦
- 领域语义更清晰
- 为未来接入 MQ / Outbox 提前统一编程模型

## 5.8 暂不引入的能力

第一阶段不建议实现：

- 异步事件总线
- 跨进程订阅
- 失败重试中心
- Outbox 持久化表
- 自动扫描所有模块进行处理器装配

这些能力可以在轻量事件模型稳定后逐步追加。

---

## 6. `OwnsOne` 设计 ✅ 已实现

> **状态**：已于 2026-03 完成实现并通过全部测试（33 项专项测试 + 620 项回归测试）。
>
> **实际实现文件**：
> - `yweb/orm/owned_types.py` — OwnedType 基类、owned_field、OwnedMeta
> - `yweb/orm/fields.py` — OwnsOne()、_process_owns_one()、comparator_factory
> - `yweb/orm/core_model.py` — to_dict() 嵌套/平铺支持
> - `yweb/orm/__init__.py` — 公开导出
> - `tests/test_orm/unit/test_owns_one.py` — 功能测试
> - `tests/test_orm/unit/test_owns_one_risk_points.py` — 风险点专项测试
>
> **与设计的差异**：
> - 采用 `comparator_factory` 替代了最初构想的 `OwnedColumnProxy`，避免与 SQLAlchemy composite 描述符冲突
> - 采用 `__init_subclass__` 替代了元类 `OwnedTypeMeta`，更简单安全
> - `OwnedType.__init__` 使用 `object.__setattr__` 绕过变更追踪，避免构造阶段误触 `changed()`

## 6.1 设计定位

`OwnsOne` 用于表达“当前实体拥有一个值对象”。

典型场景：

- 订单拥有一个收货地址
- 用户拥有一个实名信息对象
- 商品拥有一个价格区间对象
- 审批单拥有一个时间窗口对象

这些对象的共同特点：

- 没有独立主键
- 不需要独立表
- 生命周期依附父对象
- 更适合被视为聚合内部状态

## 6.2 设计目标

| 目标 | 说明 |
|------|------|
| **显式表达值对象语义** | 避免所有字段都裸露在模型顶层 |
| **单表存储** | 列展开到父表，不额外创建子表 |
| **对象化访问** | Python 层仍能用 `order.shipping_address.city` |
| **兼容 SQLAlchemy** | 底层尽量基于 `composite()` 或等价能力实现 |
| **兼容现有序列化** | `to_dict()` 和 schema 未来可识别值对象 |

## 6.3 非目标

第一阶段不支持：

- `OwnsMany`
- 值对象单独查询仓储
- 跨表嵌套拥有关系
- 值对象中再包含 ORM relationship
- 自动生成复杂索引和约束 DSL

## 6.4 建议 API

### 6.4.1 值对象定义

建议新增“值对象基类”或“拥有类型基类”，用于声明可嵌入字段：

```python
from yweb.orm.owned_types import OwnedType, owned_field
from sqlalchemy import String


class Address(OwnedType):
    street = owned_field(String(200), comment="街道")
    city = owned_field(String(100), comment="城市")
    province = owned_field(String(100), comment="省份")
    zip_code = owned_field(String(20), comment="邮编", nullable=True)
```

### 6.4.2 父模型使用

```python
from yweb.orm import fields


class Order(BaseModel):
    shipping_address = fields.OwnsOne(
        Address,
        prefix="shipping",
        nullable=False,
    )
```

语义上等价于在 `orders` 表中生成如下列：

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

`OwnsOne` 不创建外键，也不创建子表，而是把值对象字段展开到当前表：

| 父模型属性 | 展开列 |
|------|------|
| `shipping_address.street` | `shipping_street` |
| `shipping_address.city` | `shipping_city` |
| `shipping_address.province` | `shipping_province` |
| `shipping_address.zip_code` | `shipping_zip_code` |

### 6.5.2 Python 对象层

建议底层使用 SQLAlchemy `composite()` 或等效封装：

- 读取记录时，自动组装成值对象实例
- 给 `shipping_address` 重新赋值时，同步更新展开列
- 比较以值为主，而不是以实体标识为主

### 6.5.3 空值策略

建议提供以下规则：

| 场景 | 行为 |
|------|------|
| `nullable=False` | 值对象所有关键列都不能为空 |
| `nullable=True` | 允许整组为空，读取时返回 `None` |
| 部分字段为空 | 由值对象定义与校验逻辑决定是否允许 |

建议默认语义：

- `nullable=True` 时，若所有展开列均为 `NULL`，则属性返回 `None`
- 否则返回完整值对象实例

## 6.6 命名规则

### 6.6.1 列名前缀

建议默认规则：

- 若显式传入 `prefix="shipping"`，则生成 `shipping_*`
- 否则使用属性名本身作为前缀

例如：

```python
billing_address = fields.OwnsOne(Address)
```

默认生成：

- `billing_address_street`
- `billing_address_city`

若希望更短，可显式写：

```python
billing_address = fields.OwnsOne(Address, prefix="billing")
```

### 6.6.2 注释规则

建议 `owned_field(..., comment="街道")` 生成列注释时支持两种模式：

| 模式 | 示例 |
|------|------|
| 保留原注释 | `街道` |
| 自动拼接前缀 | `收货地址-街道` |

推荐默认拼接，避免数据库层字段语义过弱。

## 6.7 值对象定义约束

`OwnedType` 建议满足以下约束：

- 不是 ORM Model
- 没有 `id`
- 不参与 `metadata.create_all()` 建表
- 不允许声明 relationship
- 可以实现 `__composite_values__()`、`__eq__()`、`__repr__()`

如需不可变语义，建议值对象实例设计为只读。

## 6.8 与现有 `OneToOne` 的边界

| 对比项 | `OneToOne` | `OwnsOne` |
|------|------|------|
| 数据表 | 两张表 | 一张表 |
| 子对象主键 | 有 | 无 |
| 生命周期 | 可相对独立 | 完全依附父对象 |
| 查询方式 | join 关系 | 父表直接读取 |
| 适用场景 | 用户-档案、订单-扩展实体 | 地址、金额、时间范围、联系人 |

判断建议：

- 如果子对象需要独立增删改查，用 `OneToOne`
- 如果子对象只是父对象的一部分，用 `OwnsOne`

## 6.9 与序列化和 DTO 的集成

建议后续逐步支持：

1. `to_dict()` 自动输出为嵌套对象
2. `to_dict(flatten_owned=True)` 输出平铺字段
3. `BaseSchemas` 能识别 `OwnedType`

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

这样可以同时获得：

- 清晰的聚合内部建模
- 清晰的业务行为表达

---

## 8. 推荐实现路径

## 8.1 第一阶段：先补轻量领域事件

原因：

- 复用现有事务钩子，落地成本低
- 对框架收益最大
- 不涉及数据库结构生成复杂度

建议新增或修改：

- `yweb/orm/domain_events.py`
- `yweb/orm/transaction/context.py`
- `yweb/orm/transaction/manager.py`
- `yweb/orm/core_model.py`
- `yweb/orm/__init__.py`

## 8.2 第二阶段：补 `OwnsOne` ✅ 已完成

已新增或修改：

- ✅ `yweb/orm/fields.py` — OwnsOne()、_OwnsOneConfig、_process_owns_one()、_make_owned_comparator()
- ✅ `yweb/orm/core_model.py` — __init_subclass__ 扩展、to_dict() 嵌套/平铺
- ✅ 新增 `yweb/orm/owned_types.py` — OwnedType、owned_field、OwnedField、OwnedMeta
- ✅ 新增 `tests/test_orm/unit/test_owns_one.py` — 33 项功能测试
- ✅ 新增 `tests/test_orm/unit/test_owns_one_risk_points.py` — 31 项风险点专项测试
- ✅ 更新 `yweb/orm/__init__.py` — 导出 OwnsOne、OwnedType、owned_field、OwnedMeta
- ✅ 更新 `docs/orm_docs/21_owns_one.md` — 完整用户文档

## 8.3 第三阶段：根据实际需求扩展

后续可选扩展：

- Outbox 模式
- 异步分发
- `OwnsMany`
- 值对象校验与 schema 自动生成
- 事件处理器优先级与模块化注册

---

## 9. 测试建议

### 9.1 轻量领域事件

应至少覆盖：

- 事务提交成功后发布事件
- 事务回滚后不发布事件
- 多个事件按顺序分发
- 某个处理器失败不影响已提交事务
- 无事务场景下的立即分发行为

### 9.2 `OwnsOne`

应至少覆盖：

- 自动展开列名
- 读取时组装值对象
- 赋值值对象后持久化成功
- `nullable=True` 时整组为空返回 `None`
- `to_dict()` / 查询 / 更新行为正确

根据 pytest 规范，值对象辅助类不要以 `Test` 开头命名。

---

## 10. 风险与注意事项

| 风险点 | 说明 | 建议 | 状态 |
|------|------|------|------|
| 事件滥用 | 所有操作都发事件会导致语义泛滥 | 只对关键业务事实发事件 | 待实现 |
| 事务外事件语义不稳 | 无事务时很难严格保证“一定提交后再发” | 文档中明确推荐事务内使用 | 待实现 |
| `OwnsOne` 过度嵌套 | 会增加序列化、查询、迁移复杂度 | 第一阶段只支持单层 | ✅ 已限制 |
| 值对象变更追踪 | SQLAlchemy 对可变复合对象追踪较敏感 | 采用 MutableComposite + object.\_\_setattr\_\_ | ✅ 已解决 |
| 查询表达式复杂 | 嵌套对象查询最终仍要落回平铺列 | 通过 comparator_factory 实现透明代理 | ✅ 已解决 |
| OwnedColumnProxy 与 composite 冲突 | 自定义描述符与 SQLAlchemy composite 冲突 | 改用 comparator_factory | ✅ 已解决 |
| OwnedTypeMeta 元类不必要 | 元类可能与 MutableComposite 冲突 | 改用 \_\_init_subclass\_\_ | ✅ 已解决 |
| \_\_init\_\_ 期间误触 changed() | 构造值对象时不应触发变更追踪 | 构造阶段用 object.\_\_setattr\_\_ 绕过 | ✅ 已解决 |
| OwnsOne(nullable=True) 展开列覆盖 | 整体可空时个别列的 nullable 应被覆盖 | _process_owns_one() 中强制覆盖 | ✅ 已解决 |
| \_\_owned_composites\_\_ 继承隔离 | 子类不应共享父类的 dict 引用 | 子类独立拷贝一份 | ✅ 已解决 |

---

## 11. 结论

对 YWeb 当前定位而言，最合适的方向不是引入完整 DDD 基础设施，而是补充两项**轻量但高价值**的能力：

1. **轻量领域事件**
   - 复用现有事务钩子
   - 解决“提交后副作用解耦”的核心问题
   - 为 Outbox 和异步事件保留演进空间

2. **`OwnsOne`**
   - 提供值对象组合表达力
   - 保持单表存储和简单使用体验
   - 补足当前只有“实体关系”没有“值对象拥有”的空白

推荐落地顺序：

1. 先实现轻量领域事件
2. 再实现 `OwnsOne`
3. 最后按实际业务压力决定是否扩展 Outbox / `OwnsMany`
