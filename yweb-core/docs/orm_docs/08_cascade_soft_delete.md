# 08. 级联软删除

## 概述

当删除主表记录时，如何处理关联的子表记录？YWeb ORM 提供了灵活的级联软删除机制，支持多种业务场景。

## 级联类型

| 类型 | 常量 | 说明 | 适用场景 |
|------|------|------|----------|
| DELETE | `fields.DELETE` | 级联软删除子记录 | 订单-订单项（强聚合关系） |
| SET_NULL | `fields.SET_NULL` | 将子记录的外键设为 NULL | 部门-员工（员工可调岗） |
| UNLINK | `fields.UNLINK` | 解除多对多关联（删除关联表记录） | 用户-角色（多对多关系） |
| PROTECT | `fields.PROTECT` | 禁止删除（有子记录时抛出异常） | 分类-商品（保护数据完整性） |
| DO_NOTHING | `fields.DO_NOTHING` | 不做任何处理 | 日志记录等弱关联 |

## 快速开始

### 1. 激活钩子

```python
from yweb.orm import activate_soft_delete_hook, configure_cascade_soft_delete

# 激活软删除钩子
activate_soft_delete_hook()

# 配置级联软删除
configure_cascade_soft_delete()
```

### 2. 定义模型（使用 fields.* API + HasMany 类型标记）

```python
from __future__ import annotations  # 必须放在文件最开头

from yweb.orm import BaseModel, fields
from yweb.orm.fields import HasMany

# 父模型：订单
class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    
    # HasMany 类型标记：提供 IDE 自动补全
    order_items: HasMany[OrderItem]

# 子模型：订单项
class OrderItem(BaseModel):
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    
    # 多对一关系 + 级联软删除（自动使用 "order_items" 作为 backref）
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)
```

> **提示**：使用 `from __future__ import annotations` 后，可以直接写 `HasMany[OrderItem]` 而无需字符串引号，且 IDE 支持自动补全和重命名重构。

### 3. 使用

```python
# 创建订单
order = Order(order_no="ORD-001")
order.add(True)

# 添加订单项（通过自动创建的 backref）
item1 = OrderItem(product_name="iPhone")
item2 = OrderItem(product_name="AirPods")
order.order_items.append(item1)
order.order_items.append(item2)
order.save(True)

# 删除订单（订单项也会被级联软删除）
order.delete(True)

# 验证
print(order.is_deleted)  # True
print(item1.is_deleted)  # True
print(item2.is_deleted)  # True
```

---

## fields.* API 详解

### fields.ManyToOne（多对一关系）

```python
from yweb.orm import BaseModel, fields

class Employee(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # 多对一：员工属于部门
    department = fields.ManyToOne(
        Department,                    # 目标模型
        on_delete=fields.SET_NULL,     # 部门删除时，员工的 department_id 设为 NULL
        nullable=True,                 # 外键可为空
    )
```

**自动创建**：
- 外键列：`department_id`
- relationship：`employee.department`
- backref：`department.employees`（在 Department 上）

### fields.OneToOne（一对一关系）

```python
class UserProfile(BaseModel):
    bio: Mapped[str] = mapped_column(String(500))
    
    # 一对一：用户详情
    user = fields.OneToOne(
        User,
        on_delete=fields.DELETE,  # 用户删除时，详情也删除
    )
```

### fields.ManyToMany（多对多关系）

```python
class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # 多对多：用户-角色
    roles = fields.ManyToMany(
        Role,
        on_delete=fields.UNLINK,  # 用户删除时，解除与角色的关联
    )
```

**自动创建**：
- 中间表：`user_roles`
- relationship：`user.roles`
- backref：`role.users`

---

## 完整示例

### 场景1：DELETE - 订单-订单项（强聚合）

```python
from yweb.orm import BaseModel, fields

class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    total_amount: Mapped[int] = mapped_column(Integer, default=0)

class OrderItem(BaseModel):
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1)
    price: Mapped[int] = mapped_column(Integer, default=0)
    
    # DELETE：订单删除时，订单项也被软删除
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)

# 使用
order = Order(order_no="ORD-001", total_amount=1500)
order.add(True)

item = OrderItem(product_name="iPhone", quantity=1, price=1500)
order.order_items.append(item)
order.save(True)

# 删除订单
order.delete(True)

# 订单和订单项都被软删除
assert order.is_deleted == True
assert item.is_deleted == True
assert item.order_id == order.id  # 外键保持不变
```

### 场景2：SET_NULL - 部门-员工（可选父子）

```python
class Department(BaseModel):
    name: Mapped[str] = mapped_column(String(100))

class Employee(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # SET_NULL：部门删除时，员工的 department_id 设为 NULL
    department = fields.ManyToOne(
        Department, 
        on_delete=fields.SET_NULL,
        nullable=True,
    )

# 使用
dept = Department(name="技术部")
dept.add(True)

emp = Employee(name="张三")
dept.employees.append(emp)
dept.save(True)

# 删除部门
dept.delete(True)

# 部门被软删除，员工的外键被清空
assert dept.is_deleted == True
assert emp.is_deleted == False  # 员工未被删除
assert emp.department_id is None  # 外键被清空
```

### 场景3：PROTECT - 分类-产品（保护）

```python
class Category(BaseModel):
    name: Mapped[str] = mapped_column(String(100))

class Product(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # PROTECT：有产品时禁止删除分类
    category = fields.ManyToOne(
        Category, 
        on_delete=fields.PROTECT,
        nullable=True,
    )

# 使用
category = Category(name="电子产品")
category.add(True)

product = Product(name="iPhone")
category.products.append(product)
category.save(True)

# 尝试删除有产品的分类 - 会抛出异常
try:
    category.delete(True)
except ValueError as e:
    print(f"删除失败: {e}")
    # 输出: 删除失败: 无法删除 Category，存在关联的 Product 记录

# 删除产品后可以删除分类
product.delete(True)
category.delete(True)  # 成功
```

### 场景4：UNLINK - 用户-角色（多对多）

```python
class Role(BaseModel):
    name: Mapped[str] = mapped_column(String(50))
    code: Mapped[str] = mapped_column(String(50))

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # UNLINK：用户删除时，解除与角色的关联
    roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)

# 使用
role_admin = Role(name="管理员", code="ADMIN")
role_user = Role(name="普通用户", code="USER")
Role.add_all([role_admin, role_user], commit=True)

user = User(username="zhangsan")
user.roles.append(role_admin)
user.roles.append(role_user)
user.add(True)

# 删除用户
user.delete(True)

# 用户被软删除，角色未被删除
assert user.is_deleted == True
assert role_admin.is_deleted == False
assert role_user.is_deleted == False
```

### 场景5：DO_NOTHING - 松散关系

```python
class Project(BaseModel):
    name: Mapped[str] = mapped_column(String(100))

class Tag(BaseModel):
    name: Mapped[str] = mapped_column(String(50))
    
    # DO_NOTHING：项目删除时，标签不做任何处理
    project = fields.ManyToOne(
        Project, 
        on_delete=fields.DO_NOTHING,
        nullable=True,
    )

# 使用
project = Project(name="项目A")
project.add(True)

tag = Tag(name="Python")
project.tags.append(tag)
project.save(True)

# 删除项目
project.delete(True)

# 项目被软删除，标签保持不变
assert project.is_deleted == True
assert tag.is_deleted == False
assert tag.project_id == project.id  # 外键保持不变
```

---

## backref 自动命名规则

使用 `fields.*` API 时，backref 名称按以下优先级确定：

### 1. 优先使用 HasMany/HasOne 类型标记（推荐）

如果父模型定义了 `HasMany` 或 `HasOne` 类型标记，框架会自动使用该属性名：

```python
from __future__ import annotations
from yweb.orm.fields import HasMany

class Order(BaseModel):
    items: HasMany[OrderItem]  # 框架会使用 "items" 作为 backref 名称

class OrderItem(BaseModel):
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)
    # 自动探测到 Order.items: HasMany[OrderItem]，使用 "items" 作为 backref

# 使用
order.items.append(item)  # ✓ IDE 自动补全
```

### 2. 自动生成规则（未定义 HasMany/HasOne 时）

| 子模型类名 | backref 名称 | 说明 |
|------------|--------------|------|
| `OrderItem` | `order_items` | 移除 Model 后缀 + 复数 |
| `Employee` | `employees` | 复数 |
| `UserProfile` | `user_profile` | 一对一使用单数 |
| `E2EOrderItem` | `e2e_order_items` | 支持缩写前缀 |
| `APIClient` | `api_clients` | 支持缩写前缀 |

### 3. 手动指定 backref 参数

```python
class OrderItem(BaseModel):
    order = fields.ManyToOne(
        Order, 
        on_delete=fields.DELETE,
        backref="items",  # 手动指定名称
    )

# 使用
order.items.append(item)
```

> **推荐做法**：使用 `HasMany`/`HasOne` 类型标记，既能获得 IDE 自动补全，又能明确表达关系意图。

---

## 配置选项

### configure_cascade_soft_delete

```python
from yweb.orm import configure_cascade_soft_delete

configure_cascade_soft_delete(
    deleted_field_name="deleted_at",  # 软删除字段名（默认 deleted_at）
)
```

### 手动调用级联软删除

通常通过 `model.delete()` 自动触发，但也可以手动调用：

```python
from yweb.orm import get_cascade_manager
from sqlalchemy.orm import object_session

# 获取管理器
manager = get_cascade_manager()

# 获取 session
session = object_session(order)

# 执行级联软删除
manager.soft_delete_with_cascade(order, session)
session.commit()
```

---

## 常见问题

### 1. 为什么删除后子记录没有被级联删除？

检查是否正确配置了 `on_delete`：

```python
# ❌ 错误：未指定 on_delete，默认是 DO_NOTHING
order = fields.ManyToOne(Order)

# ✅ 正确：显式指定 on_delete
order = fields.ManyToOne(Order, on_delete=fields.DELETE)
```

### 2. 如何在 PROTECT 模式下强制删除？

先删除所有子记录，再删除父记录：

```python
# 先删除所有产品
for product in category.products:
    product.delete(True)

# 再删除分类
category.delete(True)
```

### 3. 多对多关系删除后，关联表记录去哪了？

使用 `UNLINK` 模式时，中间表的关联记录会被**硬删除**（物理删除），而不是软删除。

### 4. 如何查询包含已删除记录的关联？

```python
# 查询所有订单（包含已删除）
orders = Order.query.execution_options(include_deleted=True).all()

# 查询所有订单项（包含已删除）
items = OrderItem.query.execution_options(include_deleted=True).all()
```

---

## 下一步

- [03_关系定义](03_relationships.md) - 了解 fields.* API 详细用法
- [04_CRUD操作](04_crud_operations.md) - 学习基本增删改查
- [05_查询与过滤](05_query_and_filter.md) - 学习高级查询技巧
