# 02. 模型定义

## 概述

YWeb ORM 提供了两个核心基类：

- **CoreModel**：核心模型基类，提供所有 ORM 操作方法，包含基础字段（id、时间戳、版本控制）
- **BaseModel**：业务模型基类，继承 CoreModel 和 SimpleSoftDeleteMixin，添加常用业务字段（name、code、note、caption）

> **注意**：CoreModel 本身已包含 `deleted_at` 字段，但软删除功能（自动过滤已删除记录）是通过 SimpleSoftDeleteMixin 提供的。BaseModel 继承了 SimpleSoftDeleteMixin，因此具有完整的软删除功能。

## CoreModel

CoreModel 是核心模型基类，提供了所有 ORM 操作方法，并包含通用的基础字段。

### CoreModel 预定义字段

```python
class CoreModel(Base):
    # 主键（动态类型，根据主键策略自动确定）
    # 支持策略：auto_increment(int), snowflake(int), uuid(str), short_uuid(str), custom(str)
    # 类型：PKType = Union[int, str]
    id: Mapped[PKType] = mapped_column(...)  # 由 @declared_attr 动态生成

    # 时间戳字段
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        server_default=func.now(),
        comment="创建时间"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        nullable=True,
        onupdate=func.now(),
        comment="更新时间"
    )
    deleted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False), 
        nullable=True,
        default=None,
        comment="删除时间（软删除标记）"
    )

    # 版本控制（乐观锁）
    ver: Mapped[int] = mapped_column(Integer, default=1, nullable=False, comment="版本号")
    __mapper_args__ = {"version_id_col": ver}  # 配置乐观锁
```

> **注意**：
>
> - `id` 字段是动态生成的，根据主键策略自动确定类型（int 或 str）
> - 主键策略可以通过 `configure_primary_key()` 全局配置，或通过模型的 `__pk_strategy__` 或 `id_type` 属性覆盖
> - `ver` 字段用于乐观锁，通过 `__mapper_args__` 配置，更新时会自动递增

### 使用场景

- 需要基础的 CRUD 功能
- 不需要 BaseModel 的 name/code/note/caption 字段
- 需要与现有数据库表结构兼容
- 需要自定义软删除逻辑（CoreModel 有 deleted_at 字段，但需要手动实现软删除过滤）

> **注意**：如果只需要基础的软删除功能（自动过滤已删除记录），建议使用 BaseModel，它继承了 SimpleSoftDeleteMixin。

### 示例

```python
from yweb.orm import CoreModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer

class CustomModel(CoreModel):
    __tablename__ = "custom_table"

    # 自定义字段（CoreModel 已提供 id, created_at, updated_at, deleted_at, ver 字段）
    custom_name: Mapped[str] = mapped_column(String(100))
  
    # 如果需要启用历史记录
    # enable_history = True
```

### 主键策略配置

CoreModel 支持多种主键策略，可以通过全局配置或模型级别配置：

```python
from yweb.orm import CoreModel, configure_primary_key
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

# 方式1：全局配置（推荐在应用启动时配置）
configure_primary_key(strategy="short_uuid", short_uuid_length=10)

# 方式2：模型级别配置（优先级更高）
class MyModel(CoreModel):
    __tablename__ = "my_table"
    __pk_strategy__ = "uuid"  # 或 "snowflake", "short_uuid", "custom"
    # 或者使用 id_type（优先级低于 __pk_strategy__）
    # id_type = "uuid"
  
    name: Mapped[str] = mapped_column(String(100))
```

支持的主键策略：

| 策略名称 | 主键类型 | 生成方式 | 长度 | 适用场景 |
|---------|---------|---------|------|---------|
| `auto_increment` | int | 数据库自增 | - | 默认，单机应用 |
| `uuid` | str | UUID4完整版 | 36 | 分布式系统，需要全局唯一 |
| `short_uuid` | str | 短UUID（可配置长度） | 8-32 | 小型系统，需要短ID |
| `snowflake` | int | 雪花算法 | 64位 | 分布式系统，需要有序ID |
| `custom` | str | 自定义函数 | 自定义 | 特殊业务需求 |

> **主键生成时机**：
>
> 所有主键都是在 `flush` 时生成的（即对象写入数据库时）：
> - **自增主键**：数据库在 INSERT 时生成，flush 后通过 RETURNING 或 LAST_INSERT_ID 获取
> - **非自增主键**（UUID、雪花算法等）：在 SQLAlchemy 的 `before_insert` 事件中生成
>
> 框架在访问 `id` 属性时会自动触发 flush，无需手动处理。详见 [CRUD 操作 - 获取主键 ID](./03_crud_operations.md#获取主键-id)。

### 手动指定主键的注意事项

框架支持手动指定主键值，但需要了解以下行为差异：

```python
# 方式1：让框架自动生成（推荐）
user = User(name="张三")
user.save()
print(user.id)  # 访问 id 触发自动 flush，立即获取值

# 方式2：手动指定主键
user = User(name="张三")
user.id = "my_custom_id"  # 手动指定
user.save()
print(user.id)  # 不触发 flush（id 不是 None），延迟到 commit 时写入
```

| 对比项 | 框架自动生成 | 手动指定主键 |
|-------|------------|-------------|
| 访问 id 触发 flush | ✅ 是 | ❌ 否 |
| flush 次数 | 较多 | 较少 |
| 数据库压力 | 较大 | **较小** |
| `generate_with_retry` 冲突重试 | ✅ 生效 | ❌ **不生效** |
| 主键冲突检测时机 | 早（flush 时） | 晚（commit 时） |

> ⚠️ **风险提示**：
>
> 手动指定主键时，`generate_with_retry` 重试机制不会工作。如果指定的 id 与数据库中已有记录冲突，
> 会在 `flush/commit` 时抛出 `IntegrityError`，导致整个事务回滚。
>
> **建议**：
> - 如果必须手动指定 id，确保 ID 来源是可靠唯一的（如外部系统生成的 UUID）
> - 否则优先让框架自动生成，享受 `generate_with_retry` 的冲突保护

### 短UUID长度与碰撞概率

短UUID通过base62编码压缩长度，同时保持足够的唯一性：

| 长度 | 组合数量 | 碰撞概率（100万条数据） | 适用场景 |
|------|---------|----------------------|---------|
| 8位 | 281万亿 | 0.0000018% | 小型应用（<10万条） |
| 10位 | 839京 | 0.00000000006% | 中小型应用（<1000万条，推荐） |
| 12位 | 3兆 | 极低 | 大型应用 |
| 16位 | 79垓 | 几乎为0 | 超大型应用 |

**推荐配置**：
- 小型系统（<10万条）：8位
- 中型系统（<1000万条）：10位（默认）
- 大型系统（>1000万条）：12-16位

### 主键冲突重试机制（generate_with_retry）

框架在生成非自增主键时，会使用 `generate_with_retry` 机制确保主键唯一：

```python
# 配置时可指定最大重试次数
configure_primary_key(
    strategy=IdType.SHORT_UUID,
    short_uuid_length=10,
    max_retries=5  # 冲突时最多重试5次（默认值）
)
```

**工作原理**：

1. 在 `before_insert` 事件中生成主键
2. 检查生成的 ID 是否已存在于数据库
3. 如果冲突，重新生成并重试（最多 `max_retries` 次）
4. 超过重试次数后抛出异常

**触发条件**：
- 仅对**框架自动生成**的主键生效
- 手动指定 `model.id = "xxx"` 时，此机制**不生效**

```python
# ✅ 框架自动生成，generate_with_retry 生效
user = User(name="张三")
user.save()
print(user.id)  # 如果生成的 ID 冲突，会自动重试

# ❌ 手动指定，generate_with_retry 不生效
user = User(name="张三")
user.id = "my_id"  # 手动指定
user.save()
# 如果 "my_id" 已存在，commit 时直接报 IntegrityError
```

### 性能对比

| 主键类型 | 插入性能 | 查询性能 | 索引大小 | 长度 | 分布式友好 | 推荐场景 |
|---------|---------|---------|---------|------|-----------|---------|
| 整数自增 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | 短 | ❌ | 单机应用 |
| 短UUID(10位) | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 短 | ✅ | 小型分布式系统 |
| 完整UUID | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 长 | ✅ | 大型分布式系统 |
| 雪花算法 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 中 | ✅ | 需要有序ID的分布式系统 |

### 主键策略注意事项

#### 1. 配置时机

必须在定义模型类**之前**配置：

```python
# ✅ 正确：先配置，后定义模型
configure_primary_key(strategy="short_uuid")
class User(BaseModel):
    pass

# ❌ 错误：先定义模型，后配置（不生效）
class User(BaseModel):
    pass
configure_primary_key(strategy="short_uuid")
```

#### 2. 外键类型匹配

使用自定义主键时，外键类型必须匹配：

```python
# 全局配置短UUID（10位）
configure_primary_key(strategy="short_uuid", short_uuid_length=10)

class User(BaseModel):
    __tablename__ = "users"
    username: Mapped[str] = mapped_column(String(50))

class Order(BaseModel):
    __tablename__ = "orders"
    # 外键类型必须是 String(10)，匹配短UUID长度
    user_id: Mapped[str] = mapped_column(String(10), ForeignKey("users.id"))
```

#### 3. 数据库兼容性

- **整数自增** - 所有数据库支持
- **UUID/短UUID** - PostgreSQL原生支持UUID，MySQL/SQLite使用VARCHAR
- **雪花算法** - 使用BIGINT，所有数据库支持

### 迁移现有项目

#### 步骤1：在应用启动时配置

```python
# main.py 或 app.py
from yweb.orm import configure_primary_key, init_database

# 初始化数据库
init_database("sqlite:///./app.db")

# 配置主键策略（只需一次）
configure_primary_key(
    strategy="short_uuid",
    short_uuid_length=10
)
```

#### 步骤2：新表自动使用新策略

```python
# 新建的表自动使用短UUID
class NewTable(BaseModel):
    __tablename__ = "new_table"
    name: Mapped[str] = mapped_column(String(50))
```

#### 步骤3：现有表保持不变

```python
# 现有表继续使用整数主键（已创建的表结构不受影响）
class ExistingTable(BaseModel):
    __tablename__ = "existing_table"
    name: Mapped[str] = mapped_column(String(50))
```

> **注意**：配置只影响新创建的表，已存在的表结构不会改变。

### CoreModel 提供的方法

#### 实例方法

| 方法                                                     | 说明                                               |
| -------------------------------------------------------- | -------------------------------------------------- |
| `save(commit=False)`                                   | 智能保存（新增或更新），自动判断是否需要添加到会话 |
| `add(commit=False)`                                    | 添加到会话（兼容方法，等同于 save）                |
| `update(commit=False)`                                 | 更新对象（标记为dirty，触发flush时更新）           |
| `delete(commit=False)`                                 | 删除对象（物理删除）                               |
| `update_properties(**kwargs)`                          | 批量更新属性                                       |
| `update_with_foreign_key_none(commit=False)`           | 设置外键为 None 时调用，防止被误认为是软删除       |
| `to_dict(exclude=None)`                                | 转换为字典                                         |
| `to_dict_with_relations(relations=None, exclude=None)` | 包含关联对象的字典                                 |
| `detach()`                                             | 分离对象（跨请求安全访问）                         |
| `detach_with_relations(relations=None)`                | 分离对象及关联对象                                 |

#### 类方法

| 方法                                                                | 说明                                                |
| ------------------------------------------------------------------- | --------------------------------------------------- |
| `get(id)`                                                         | 根据ID获取对象，不存在返回None                      |
| `get_all()`                                                       | 获取所有记录                                        |
| `get_list_by_conditions(conditions)`                              | 根据条件字典获取列表                                |
| `add_all(objects, commit=False)`                                  | 批量添加对象到会话                                  |
| `bulk_update(filters, values, commit=False)`                      | 批量更新（返回受影响行数）                          |
| `bulk_update_by_ids(ids, values, commit=False)`                   | 根据ID批量更新（返回受影响行数）                    |
| `bulk_delete(filters, commit=False)`                              | 批量删除（返回受影响行数）                          |
| `bulk_delete_by_ids(ids, commit=False)`                           | 根据ID批量删除（返回受影响行数）                    |
| `bulk_soft_delete(filters, commit=False)`                         | 批量软删除（设置deleted_at，返回受影响行数）        |
| `bulk_soft_delete_by_ids(ids, commit=False)`                      | 根据ID批量软删除（返回受影响行数）                  |
| `cleanup_soft_deleted(days=None, commit=False)`                   | 清理软删除数据（物理删除，返回受影响行数）          |
| `cleanup_all_soft_deleted(days=None, commit=False)`               | 清理所有继承BaseModel的表中的软删除数据（返回字典） |
| `get_soft_deleted_count(days=None)`                               | 获取软删除数据数量（不删除，仅统计）                |
| `paginate(stmt, page, page_size, max_page_size=100, schema=None)` | 分页查询                                            |

#### 历史记录方法（需要 enable_history=True）

如果模型设置了 `enable_history = True`，还会提供以下方法：

| 方法                                                                                                    | 说明                           |
| ------------------------------------------------------------------------------------------------------- | ------------------------------ |
| `get_history(version=None, limit=100, field_names=None)`                                              | 获取当前实例的历史记录         |
| `history`                                                                                             | 便捷属性，获取所有历史记录     |
| `history_count`                                                                                       | 便捷属性，获取历史记录数量     |
| `get_history_diff(from_version, to_version, exclude_fields=None)`                                     | 比较两个版本之间的差异         |
| `get_field_text_diff(field_name, from_version, to_version, output_format="unified", context_lines=3)` | 获取字段的文本细节差异         |
| `restore_to_version(version, exclude_fields=None)`                                                    | 恢复到指定版本                 |
| `get_history_by_id(instance_id, version=None, limit=100, session=None, field_names=None)`             | 类方法，根据ID获取历史记录     |
| `get_history_count_by_id(instance_id, session=None)`                                                  | 类方法，根据ID获取历史记录数量 |

详细说明请参考 [10_历史记录](10_history.md) 文档。

## BaseModel

BaseModel 继承自 CoreModel 和 SimpleSoftDeleteMixin，添加了企业应用常用的字段，并提供完整的软删除功能。

### 预定义字段

BaseModel 继承自 CoreModel，并添加业务常用字段：

```python
class BaseModel(CoreModel, SimpleSoftDeleteMixin):
    # 继承自 CoreModel 的字段：
    # id, created_at, updated_at, deleted_at, ver

    # 基础业务字段
    name: Mapped[str] = mapped_column(String(255), nullable=True, comment="名称")
    code: Mapped[str] = mapped_column(String(255), nullable=True, comment="编码")
    note: Mapped[str] = mapped_column(String(1000), nullable=True, comment="备注")
    caption: Mapped[str] = mapped_column(String(512), nullable=True, comment="介绍")
```

### 字段说明

**CoreModel 提供的字段（所有模型都有）：**

| 字段           | 类型     | 长度/约束                          | 说明                                                                              |
| -------------- | -------- | ---------------------------------- | --------------------------------------------------------------------------------- |
| `id`         | Union[int, str]    | primary_key                        | 主键,类型根据主键策略动态确定（auto_increment/snowflake/uuid/short_uuid/custom） |
| `created_at` | datetime           | server_default=func.now()          | 创建时间,自动设置                                                                |
| `updated_at` | datetime | nullable=True, onupdate=func.now() | 更新时间,自动更新,注意类型是datetime而非Optional[datetime]                                                                |
| `deleted_at` | datetime | nullable=True, default=None        | 软删除时间,注意类型是datetime而非Optional[datetime]                                                                        |
| `ver`        | int                | default=1, nullable=False          | 版本号,用于乐观锁（通过 `__mapper_args__` 配置）                               |

**BaseModel 额外提供的字段：**

| 字段        | 类型 | 长度/约束              | 说明            |
| ----------- | ---- | ---------------------- | --------------- |
| `name`    | str  | String(255), nullable  | 名称，可选      |
| `code`    | str  | String(255), nullable  | 编码，可选      |
| `note`    | str  | String(1000), nullable | 备注，可选      |
| `caption` | str  | String(512), nullable  | 介绍/描述，可选 |

**BaseModel 额外提供的方法：**

| 方法                  | 说明             |
| --------------------- | ---------------- |
| `get_by_name(name)` | 根据名称获取对象 |
| `get_by_code(code)` | 根据编码获取对象 |

### 使用示例

```python
from yweb.orm import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean

class User(BaseModel):
    __tablename__ = "user"

    # 自定义字段
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # 可以覆盖 BaseModel 的字段
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # 覆盖为必填
```

## 表名生成

### 自动生成

如果不指定 `__tablename__`，会自动根据类名生成表名（驼峰转下划线）：

```python
class UserProfile(BaseModel):
    pass
    # 自动生成表名: user_profile

class OrderItem(BaseModel):
    pass
    # 自动生成表名: order_item
```

### 手动指定

```python
class User(BaseModel):
    __tablename__ = "sys_user"  # 手动指定表名
```

## 字段定义

### SQLAlchemy 2.0 风格（推荐）

```python
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean, Text, DateTime, ForeignKey
from typing import Optional
from datetime import datetime

class Article(BaseModel):
    # 如果需要指定tablename 使用：__tablename__ = "article"

    # 必填字段
    title: Mapped[str] = mapped_column(String(200))

    # 可选字段
    content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # 带默认值
    status: Mapped[str] = mapped_column(String(20), default="draft")
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)

    # 外键
    author_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"))

    # 唯一约束
    slug: Mapped[str] = mapped_column(String(100), unique=True)

    # 索引
    category: Mapped[str] = mapped_column(String(50), index=True)
```

### 传统风格（兼容）

```python
from sqlalchemy import Column, String, Integer, Boolean

class Article(BaseModel):
    __tablename__ = "article"

    title = Column(String(200), nullable=False)
    content = Column(Text, nullable=True)
    status = Column(String(20), default="draft")
```

## 关联关系

> **推荐**：定义关系时优先使用 `fields.*` API（如 `fields.ManyToOne`），支持级联软删除。完整使用规范请参考 [03_关系定义](03_relationships.md#使用规范总结)。

### 一对多关系

```python
from sqlalchemy.orm import relationship

class Department(BaseModel):
    __tablename__ = "department"

    dept_name: Mapped[str] = mapped_column(String(100))

    # 一对多：一个部门有多个员工
    employees = relationship("Employee", back_populates="department")

class Employee(BaseModel):
    __tablename__ = "employee"

    emp_name: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("department.id"))

    # 多对一：员工属于一个部门
    department = relationship("Department", back_populates="employees")
```

### 多对多关系

```python
from sqlalchemy import Table, Column, Integer, ForeignKey

# 关联表
user_role = Table(
    "user_role",
    BaseModel.metadata,
    Column("user_id", Integer, ForeignKey("user.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("role.id"), primary_key=True),
)

class User(BaseModel):
    __tablename__ = "user"

    username: Mapped[str] = mapped_column(String(50))

    # 多对多关系
    roles = relationship("Role", secondary=user_role, back_populates="users")

class Role(BaseModel):
    __tablename__ = "role"

    role_name: Mapped[str] = mapped_column(String(50))

    users = relationship("User", secondary=user_role, back_populates="roles")
```

### 使用 fields.*（支持级联软删除）

```python
from yweb.orm import BaseModel, fields

class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    # order_items 属性由 OrderItem 的 backref 自动创建

class OrderItem(BaseModel):
    product_name: Mapped[str] = mapped_column(String(100))
    
    # 多对一 + 级联软删除：订单删除时，订单项也被软删除
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)
```

### 使用 HasMany/HasOne 类型标记（推荐，提供 IDE 提示）

`fields.ManyToOne` 会自动在父模型上创建 backref，但 IDE 无法自动补全。使用 `HasMany`/`HasOne` 类型标记可以获得完整的 IDE 提示：

```python
from __future__ import annotations  # 必须放在文件最开头

from yweb.orm import BaseModel, fields
from yweb.orm.fields import HasMany, HasOne

# 一对多关系示例
class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    
    # HasMany 类型标记：提供 IDE 自动补全
    order_items: HasMany[OrderItem]

class OrderItem(BaseModel):
    product_name: Mapped[str] = mapped_column(String(100))
    
    # ManyToOne 会自动探测父类的 HasMany 注解，使用 "order_items" 作为 backref 名称
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)


# 一对一关系示例
class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # HasOne 类型标记
    profile: HasOne[UserProfile]

class UserProfile(BaseModel):
    bio: Mapped[str] = mapped_column(String(500))
    
    # OneToOne 会自动探测父类的 HasOne 注解，使用 "profile" 作为 backref 名称
    user = fields.OneToOne(User, on_delete=fields.DELETE)
```

**关键点：**

1. **必须使用 `from __future__ import annotations`** - 放在文件最开头，让类型注解延迟评估
2. **无需字符串引号** - 直接写 `HasMany[OrderItem]`，不是 `"HasMany[OrderItem]"`
3. **IDE 完整支持** - 重命名类时会自动更新，支持类型检查
4. **自动 backref 探测** - `ManyToOne`/`OneToOne` 会自动探测父类的 `HasMany`/`HasOne` 注解

**使用效果：**

```python
order = Order(order_no="ORD-001")
order.order_items.append(item)  # ✓ IDE 自动补全 order_items
order.order_items[0].order      # ✓ IDE 自动补全 order
```

## 表配置

### 表参数

```python
class User(BaseModel):
    __tablename__ = "user"
    __table_args__ = {
        'extend_existing': True,  # 允许重新定义
        'mysql_engine': 'InnoDB',
        'mysql_charset': 'utf8mb4',
    }
```

### 复合主键

使用复合主键时，需要禁用自动主键生成：

```python
from sqlalchemy import PrimaryKeyConstraint

class UserRole(CoreModel):
    __use_auto_pk__ = False  # 禁用自动主键生成
    __table_args__ = (
        PrimaryKeyConstraint('user_id', 'role_id'),
    )

    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("role.id"), primary_key=True)
```

> **注意**：设置 `__use_auto_pk__ = False` 后，必须手动定义所有主键字段，并设置 `primary_key=True`。

### 复合索引

```python
from sqlalchemy import Index

class Article(BaseModel):
    __table_args__ = (
        Index('idx_author_status', 'author_id', 'status'),
        Index('idx_created_at', 'created_at'),
    )

    author_id: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20))
```

## 模型继承

### 单表继承

```python
class Animal(BaseModel):

    animal_type: Mapped[str] = mapped_column(String(50))

    __mapper_args__ = {
        'polymorphic_on': animal_type,
        'polymorphic_identity': 'animal'
    }

class Dog(Animal):
    __mapper_args__ = {
        'polymorphic_identity': 'dog'
    }

    breed: Mapped[str] = mapped_column(String(50), nullable=True)
```

### 混入类（Mixin）

Mixin 支持普通列字段和关系字段（`fields.OneToOne` / `fields.ManyToOne` / `fields.ManyToMany`）。框架会自动通过 MRO 扫描识别 Mixin 中的关系字段并正确处理。

```python
# 普通列字段 Mixin
class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(default=datetime.now)
    updated_at: Mapped[Optional[datetime]] = mapped_column(onupdate=datetime.now)

class AuditMixin:
    created_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    updated_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

class Article(BaseModel, AuditMixin):

    title: Mapped[str] = mapped_column(String(200))
    # 自动拥有 created_by, updated_by 字段
```

```python
# 关系字段 Mixin
from yweb.orm import fields

class UserLinkMixin:
    """为模型添加 user 一对一关联"""
    user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)

class Employee(UserLinkMixin, BaseModel):
    __tablename__ = "employee"
    name: Mapped[str] = mapped_column(String(100))
    # 自动拥有 user_id 外键列 + user relationship
```

## 最佳实践

### 1. 使用 BaseModel 作为基类

```python
# 推荐：使用 BaseModel
class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))

# 不推荐：直接使用 DeclarativeBase
class User(DeclarativeBase):
    ...
```

### 2. 明确指定表名

```python
# 推荐：自动生成 类名不能有下划线
class UserProfile(BaseModel):
    pass  # 自动生成 user_profile

# 可以：明确指定
class UserProfile(BaseModel):
    __tablename__ = "user_profile"
```

### 3. 使用类型注解

```python
# 推荐：SQLAlchemy 2.0 风格
username: Mapped[str] = mapped_column(String(50))

# 不推荐：传统风格
username = Column(String(50))
```

### 4. 合理使用可选字段

```python
from typing import Optional

# 可选字段
note: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

# 必填字段
username: Mapped[str] = mapped_column(String(50))
```

### 5. 启用历史记录

如果模型需要版本历史功能，设置 `enable_history = True`：

```python
class Article(BaseModel):
    enable_history = True  # 启用历史记录
  
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(2000))
```

详细说明请参考 [10_历史记录](10_history.md) 文档。

## 下一步

- [03_CRUD操作](03_crud_operations.md) - 学习增删改查操作
- [08_级联软删除](08_cascade_soft_delete.md) - 了解 fields.* 级联软删除
