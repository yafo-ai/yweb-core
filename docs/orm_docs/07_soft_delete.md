# 07. 软删除

## 概述

软删除（Soft Delete）是一种数据管理策略，不物理删除数据库记录，而是通过标记字段（`deleted_at`）来标识记录已被"删除"。

YWeb ORM 提供了完整的软删除解决方案：

- **自动查询过滤**：SELECT 查询自动排除已删除记录
- **软删除转换**：DELETE 操作自动转为软删除
- **恢复功能**：支持通过 `undelete()` 方法恢复已软删除的记录
- **灵活配置**：可忽略特定表、自定义字段名
- **按需禁用**：可在单个查询中禁用软删除过滤

## 快速开始

### 使用 BaseModel（推荐）

BaseModel 已内置软删除支持：

```python
from yweb.orm import BaseModel

# 注意：使用 BaseModel 时，软删除钩子会自动激活，不需要手动调用 activate_soft_delete_hook()
# 因为 BaseModel 继承 SimpleSoftDeleteMixin，SimpleSoftDeleteMixin 在生成时会自动激活钩子

class User(BaseModel):
    __tablename__ = "user"
    username: Mapped[str] = mapped_column(String(50))

# 创建用户
user = User(username="tom")
user.add(True)

# 软删除
user.delete(True)  # 调用 session.delete(self)，被钩子拦截转换为软删除

# 正常查询不会返回已删除的记录
users = User.query.all()  # 不包含已删除的

# 包含已删除的记录
all_users = User.query.execution_options(include_deleted=True).all()
```

> **工作原理**：
>
> - BaseModel 继承 SimpleSoftDeleteMixin
> - SimpleSoftDeleteMixin 在生成时会自动调用 `activate_soft_delete_hook()` 激活软删除钩子
> - 因此使用 BaseModel 时，软删除功能已经自动启用，不需要手动调用 `activate_soft_delete_hook()`

### 使用 SoftDeleteMixin

如果使用 CoreModel，可以添加 SoftDeleteMixin：

```python
from yweb.orm import CoreModel, SimpleSoftDeleteMixin

class CustomModel(CoreModel, SimpleSoftDeleteMixin):
    __tablename__ = "custom"
    # ...
```

## 核心组件

### activate_soft_delete_hook()

激活软删除钩子，注册 SQLAlchemy 事件监听器。

```python
from yweb.orm import activate_soft_delete_hook, IgnoredTable

activate_soft_delete_hook(
    deleted_field_name="deleted_at",           # 软删除字段名
    disable_soft_delete_option_name="include_deleted",  # 禁用选项名
    ignored_tables=[                           # 忽略的表
        IgnoredTable(name='audit_log'),
        IgnoredTable(name='system_config'),
    ]
)
```

### SimpleSoftDeleteMixin

提供软删除相关的方法（`deleted_at` 字段由 CoreModel 提供）：

```python
class SimpleSoftDeleteMixin:
    # 注意：deleted_at 字段由 CoreModel 提供，SimpleSoftDeleteMixin 只提供方法
    # 不生成字段，只提供 soft_delete/undelete 方法和激活钩子

    @property
    def is_deleted(self) -> bool:
        """是否已删除"""
        return self.deleted_at is not None

    def soft_delete(self, v: Optional[Any] = None):
        """执行软删除
      
        Args:
            v: 可选，自定义删除时间，默认为 datetime.now()
        """
        self.deleted_at = v or datetime.now()

    def undelete(self):
        """恢复删除"""
        self.deleted_at = None
```

> **注意**：
>
> - `SimpleSoftDeleteMixin` 在生成时设置了 `deleted_field_type=None`，所以不生成字段，只提供方法
> - 使用 `SimpleSoftDeleteMixin` 时会自动调用 `activate_soft_delete_hook()` 激活软删除钩子
> - 因此使用 BaseModel 时，软删除钩子已经自动激活，不需要手动调用 `activate_soft_delete_hook()`

### IgnoredTable

定义需要忽略软删除的表：

```python
from yweb.orm import IgnoredTable

ignored_tables = [
    IgnoredTable(name='audit_log'),
    IgnoredTable(name='system_config'),
    IgnoredTable(name='public_table', table_schema='public'),  # 指定 schema
]
```

## 软删除操作

### 执行软删除

#### 方式1：使用 delete() 方法（推荐）

BaseModel 的 `delete()` 方法来自 CoreModel，调用 `session.delete(self)`，然后被软删除钩子拦截转换为软删除：

```python
user = User.get(1)
user.delete(True)  # 调用 session.delete(self)，被钩子拦截转换为软删除
```

#### 方式2：使用 soft_delete() 方法

SimpleSoftDeleteMixin 提供了 `soft_delete()` 方法，可以直接设置 `deleted_at`：

```python
user = User.get(1)
user.soft_delete()  # 设置 deleted_at = datetime.now()
user.save(True)

# 或自定义删除时间
user.soft_delete(datetime(2024, 1, 1, 12, 0, 0))  # 设置自定义删除时间
user.save(True)
```

> **工作原理**：
>
> - `delete()` 方法：调用 `session.delete(self)`，软删除钩子在 `before_flush` 事件中拦截，将对象从 `deleted` 集合移到 `dirty` 集合，并设置 `deleted_at`
> - `soft_delete()` 方法：直接设置 `deleted_at` 字段，然后需要手动 `save()` 或 `commit()`
> - 两种方式最终都会设置 `deleted_at` 字段，但 `delete()` 方法更符合 ORM 的使用习惯

> **注意**：不要直接设置 `deleted_at` 字段，应该使用上述方法

### 查询包含已删除的记录、恢复软删除

```python
# 先查询包含已删除的记录
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()

# 恢复软删除（使用 SimpleSoftDeleteMixin 提供的 undelete() 方法）
if user and user.is_deleted:
    user.undelete()  # 设置 deleted_at = None
    user.save(True)  # 提交更改
```

> **注意**：
>
> - `undelete()` 和 `is_deleted` 是 `SimpleSoftDeleteMixin` 提供的方法和属性
> - 只有继承 `SimpleSoftDeleteMixin` 的模型（如 BaseModel）才有这些功能
> - 恢复后，正常查询会重新返回该记录

### 查询已删除的记录

```python
# 包含已删除的记录
all_users = User.query.execution_options(include_deleted=True).all()

# 只查询已删除的记录
deleted_users = User.query.execution_options(include_deleted=True).filter(
    User.deleted_at.isnot(None)
).all()

# 只查询未删除的记录（默认行为）
active_users = User.query.all()
```

### 永久删除（物理删除）

```python
from sqlalchemy import delete
from yweb.orm import db_manager

session = db_manager.get_session()

# 方法1：使用 delete 语句（推荐）
# 注意：execution_options 应该用在查询上，不是 delete 语句上
stmt = delete(User).where(User.id == 1)
session.execute(stmt)
session.commit()

# 方法2：先查询再删除（需要包含已删除记录）
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()
if user:
    session.delete(user)  # 物理删除
    session.commit()
```

> **警告**：物理删除会永久删除数据，无法恢复。请谨慎使用！

## 高级配置

### 自定义软删除字段名

```python
activate_soft_delete_hook(deleted_field_name="removed_at")

class User(BaseModel):
    __tablename__ = "user"
    removed_at: Mapped[Optional[datetime]] = mapped_column(nullable=True)
```

### 自定义禁用选项名

```python
activate_soft_delete_hook(
    disable_soft_delete_option_name="show_deleted"
)

# 使用时
users = User.query.execution_options(show_deleted=True).all()
```

### 忽略特定表

```python
activate_soft_delete_hook(
    ignored_tables=[
        IgnoredTable(name='audit_log'),      # 审计日志不使用软删除
        IgnoredTable(name='system_config'),  # 系统配置不使用软删除
    ]
)
```

### 检查软删除状态

```python
from yweb.orm import is_soft_delete_active

if is_soft_delete_active():
    print("软删除已激活")
else:
    print("软删除未激活")
```

### 停用软删除

```python
from yweb.orm import deactivate_soft_delete_hook

deactivate_soft_delete_hook()
```

> **注意**：SQLAlchemy 的事件监听器一旦注册就无法移除，此函数只是将全局重写器设为 None，使其不再生效。

## 使用 generate_soft_delete_mixin_class

动态生成自定义的软删除 Mixin：

```python
from yweb.orm import generate_soft_delete_mixin_class
from datetime import datetime

CustomSoftDeleteMixin = generate_soft_delete_mixin_class(
    deleted_field_name="deleted_at",
    class_name="CustomSoftDeleteMixin",
    generate_delete_method=True,
    delete_method_name="soft_delete",
    delete_method_default_value=lambda: datetime.now(),
    generate_undelete_method=True,
    undelete_method_name="restore",
)

class User(BaseModel, CustomSoftDeleteMixin):
    __tablename__ = "user"
    # ...
```

## 最佳实践

### 1. 在应用启动时激活

```python
# main.py
from fastapi import FastAPI
from yweb.orm import activate_soft_delete_hook, IgnoredTable

def create_app():
    app = FastAPI()

    # 激活软删除（在创建数据库连接前）
    activate_soft_delete_hook(
        ignored_tables=[
            IgnoredTable(name='audit_log'),
        ]
    )

    return app
```

### 2. 审计日志不使用软删除

```python
activate_soft_delete_hook(
    ignored_tables=[IgnoredTable(name='audit_log')]
)
```

### 3. 定期清理软删除数据

CoreModel 内置了清理软删除数据的方法：

```python
# 查看软删除数据数量
count = User.get_soft_deleted_count()
print(f"共有 {count} 条软删除记录")

# 查看超过30天的软删除数据数量
count = User.get_soft_deleted_count(days=30)
print(f"有 {count} 条记录软删除超过30天")

# 清理所有软删除的记录（物理删除）
deleted_count = User.cleanup_soft_deleted(commit=True)
print(f"清理了 {deleted_count} 条记录")

# 只清理超过30天的软删除记录
deleted_count = User.cleanup_soft_deleted(days=30, commit=True)
print(f"清理了 {deleted_count} 条超过30天的记录")

# 清理所有表的软删除数据
from yweb.orm import BaseModel
result = BaseModel.cleanup_all_soft_deleted(days=30, commit=True)
for table, count in result.items():
    if count > 0:
        print(f"{table}: 清理了 {count} 条记录")
```

### 4. 软删除时记录操作者

```python
class User(BaseModel):
    __tablename__ = "user"

    deleted_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    def soft_delete(self, operator_id: int = None):
        self.deleted_at = datetime.now()
        if operator_id:
            self.deleted_by = operator_id
```

## 常见问题

### Q1: 为什么查询不到刚删除的记录？

因为软删除钩子自动过滤了 `deleted_at IS NOT NULL` 的记录。使用 `execution_options(include_deleted=True)` 可以包含已删除记录。

### Q2: 软删除会影响性能吗？

软删除钩子会为每个 SELECT 查询添加 `WHERE deleted_at IS NULL` 条件。建议在 `deleted_at` 字段上创建索引：

```sql
CREATE INDEX idx_user_deleted_at ON user(deleted_at);
```

### Q3: 如何处理关联数据的软删除？

使用级联软删除，详见 [08_级联软删除](08_cascade_soft_delete.md)。

### Q4: 可以同时使用软删除和物理删除吗？

可以。使用 `execution_options(include_deleted=True)` 配合原生 DELETE 语句即可物理删除。

### Q5: 软删除后如何恢复外键关联？

需要同时恢复父记录和子记录：

```python
# 恢复用户
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()
user.undelete()

# 恢复用户的订单
orders = Order.query.execution_options(include_deleted=True).filter(
    Order.user_id == user.id
).all()
for order in orders:
    order.undelete()

session.commit()
```

## 下一步

- [08_级联软删除](08_cascade_soft_delete.md) - 学习级联软删除
- [09_版本控制](09_version_control.md) - 了解乐观锁机制
