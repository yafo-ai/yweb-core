# 03. 关系定义与使用

本文档详细介绍 SQLAlchemy ORM 中的各种关系类型及其在 YWeb 中的使用方式。

## 概述

### 关系类型一览

| 关系类型 | 说明 | 典型场景 |
|----------|------|----------|
| **一对一** | 一条记录对应另一条记录 | 用户 ↔ 用户详情 |
| **一对多** | 一条记录对应多条记录 | 部门 → 员工 |
| **多对一** | 多条记录对应一条记录 | 员工 → 部门 |
| **多对多** | 多条记录对应多条记录 | 用户 ↔ 角色 |
| **自关联** | 记录关联同表的其他记录 | 部门的父子层级 |

### 定义方式对比

| 方式 | 代码量 | 适用场景 |
|------|--------|----------|
| `ForeignKeyField` | 1 行 | 简单外键关系，推荐日常使用 |
| `soft_relationship` | 2-3 行 | 需要级联软删除的关系 |
| `relationship` | 3-5 行 | 完全自定义，复杂场景 |

---

## 一对一关系 (One-to-One)

一条记录只能关联另一条记录。

### 关系示意图

```
┌─────────────────┐              ┌─────────────────┐
│   User (父表)   │  1       1   │ UserProfile     │
│─────────────────│◄─────────────│ (子表)          │
│ id (PK)         │              │ id (PK)         │
│ username        │              │ user_id (FK,UQ) │ ← 唯一约束确保一对一
│                 │              │ bio             │
│ profile ────────┼──────────────┤ avatar          │
└─────────────────┘              └─────────────────┘
```

### 方式1：使用 ForeignKeyField + ONE_TO_ONE（推荐）

```python
from yweb.orm import BaseModel, ForeignKeyField, ONE_TO_ONE, IGNORE
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    # profile 属性由 backref 自动创建（单数形式）

class UserProfile(BaseModel):
    bio: Mapped[str] = mapped_column(String(500), nullable=True)
    avatar: Mapped[str] = mapped_column(String(200), nullable=True)
    
    # 一对一：使用 backref=ONE_TO_ONE 自动生成单数名称
    user = ForeignKeyField(
        User,
        on_delete=IGNORE,
        nullable=False,
        backref=ONE_TO_ONE,  # 自动创建 User.user_profile（单数）
        # 其他 backref 写法：
        # backref=ONE_TO_ONE,  # → User.user_profile（单数，一对一推荐）
        # backref=True,        # → User.user_profiles（复数，一对多默认）
        # backref="profile",   # → User.profile（自定义名称）
        # backref=False,       # → 不创建反向引用（级联也不生效！）
    )
    
    # 添加唯一约束确保一对一
    __table_args__ = (
        # user_id 唯一，确保一个用户只有一个 profile
    )

# 使用
user = User(username="zhangsan")
user.save(True)

profile = UserProfile(bio="Hello", avatar="/avatar.png")
profile.user = user
profile.save(True)

# 访问
print(user.user_profile.bio)  # 正向：用户 → 详情（自动单数名称）
print(profile.user.username)  # 反向：详情 → 用户
```

### backref 参数说明

| 值 | 效果 | 适用场景 |
|------|------|----------|
| `ONE_TO_ONE` | 自动生成**单数**名称 + `uselist=False` | 一对一关系（推荐） |
| `True`（默认） | 自动生成**复数**名称 | 一对多关系 |
| `"profile"` | 使用指定名称 | 自定义名称 |
| `False` | 不创建反向引用（**级联也不生效**） | 不需要反向访问 |

### 方式2：其他 backref 写法

```python
# 写法1：自定义名称
user = ForeignKeyField(User, backref="profile")      # → User.profile

# 写法2：默认复数（一对多场景）
user = ForeignKeyField(User, backref=True)           # → User.user_profiles

# 写法3：禁用反向引用（注意：级联也不生效）
user = ForeignKeyField(User, backref=False)          # → 无 backref
```

### 方式3：使用原生 relationship + uselist=False

```python
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey, Integer

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # uselist=False 表示一对一（不是列表）
    profile = relationship("UserProfile", back_populates="user", uselist=False)

class UserProfile(BaseModel):
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), unique=True)
    bio: Mapped[str] = mapped_column(String(500), nullable=True)
    
    user = relationship("User", back_populates="profile")
```

**关键点**：
- 父表设置 `uselist=False`（返回单个对象而非列表）
- 子表外键添加 `unique=True`（确保一对一）

---

## 一对多关系 (One-to-Many)

一条记录可以关联多条记录。

### 关系示意图

```
┌─────────────────┐              ┌─────────────────┐
│ Department      │  1       N   │ Employee        │
│ (父表/一)       │◄─────────────│ (子表/多)       │
│─────────────────│              │─────────────────│
│ id (PK)         │              │ id (PK)         │
│ name            │              │ dept_id (FK)    │
│                 │              │ name            │
│ employees ──────┼──────────────┤ department ─────│
│   (list)        │              │   (单个对象)    │
└─────────────────┘              └─────────────────┘
```

### 方式1：使用 ForeignKeyField（推荐）

```python
from yweb.orm import BaseModel, ForeignKeyField, CLEAR_FK

class Department(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    # employees 属性由 backref 自动创建（返回列表）

class Employee(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # 多对一：员工属于一个部门
    department = ForeignKeyField(
        Department,
        on_delete=CLEAR_FK,    # 部门删除时，员工的 dept_id 设为 NULL
        nullable=True,         # 允许员工暂时没有部门
        # backref 写法：
        # backref=True,          # → Department.employees（自动复数，默认  不需要显示的写）
        # backref="employees",   # → Department.employees（自定义名称）
        # backref=ONE_TO_ONE,    # → Department.employee（单数，一对一场景）
        # backref=False,         # → 不创建反向引用（级联也不生效！）
    )

# 使用
dept = Department(name="技术部")
dept.save(True)

emp1 = Employee(name="张三")
emp1.department = dept
emp1.save(True)

emp2 = Employee(name="李四", department_id=dept.id)
emp2.save(True)

# 访问
print(dept.employees)        # [Employee1, Employee2] - 列表
print(emp1.department.name)  # "技术部" - 单个对象
```

### 方式2：使用 soft_relationship（支持级联软删除）

```python
from yweb.orm import BaseModel, soft_relationship, DELETE

class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    
    # 一对多：订单有多个订单项
    items = soft_relationship(
        "OrderItem",
        backref="order",
        on_delete=DELETE,  # 订单删除时，订单项也软删除
    )

class OrderItem(BaseModel):
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("order.id"))
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer, default=1)

# 使用
order = Order(order_no="ORD-001")
order.save(True)

item1 = OrderItem(product_name="iPhone", quantity=1)
item2 = OrderItem(product_name="AirPods", quantity=2)
order.items.append(item1)
order.items.append(item2)
order.save(True)

# 删除订单（订单项也会被级联软删除）
order.delete(True)
print(item1.is_deleted)  # True
```

### 方式3：使用原生 relationship

```python
from sqlalchemy.orm import relationship

class Department(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # 一对多关系
    employees = relationship(
        "Employee",
        back_populates="department",
        lazy="selectin",  # 加载策略
    )

class Employee(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    department_id: Mapped[int] = mapped_column(Integer, ForeignKey("department.id"), nullable=True)
    
    # 多对一关系
    department = relationship("Department", back_populates="employees")
```

---

## 多对多关系 (Many-to-Many)

多条记录可以关联多条记录，需要中间表。

### 关系示意图

```
┌─────────────┐          ┌─────────────┐          ┌─────────────┐
│    User     │    N     │ user_roles  │    M     │    Role     │
│─────────────│◄─────────│ (自动创建)  │─────────►│─────────────│
│ id (PK)     │          │ user_id(FK) │          │ id (PK)     │
│ username    │          │ role_id(FK) │          │ role_name   │
│             │          └─────────────┘          │             │
│ roles ──────┼──────────────────────────────────►│ users ──────│
│   (list)    │                                   │ (backref)   │
└─────────────┘                                   └─────────────┘
```

### 方式1：使用 ManyToManyField（推荐，自动创建中间表）

```python
from yweb.orm import BaseModel, ManyToManyField, UNLINK
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class Role(BaseModel):
    name: Mapped[str] = mapped_column(String(50))
    # users 属性由 backref 自动创建

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # 多对多关系：自动创建中间表
    roles = ManyToManyField(Role, on_delete=UNLINK)
    # 自动创建：
    #   - user_roles 中间表（user_id, role_id）
    #   - roles relationship（正向关系，列表）
    #   - Role.users backref（反向关系，列表）
    # 
    # backref 写法：
    # backref=True,          # → Role.users（自动复数，默认）
    # backref="members",     # → Role.members（自定义名称）
    # backref=False,         # → 不创建反向引用

# ✅ 推荐：使用单次提交模式
role1 = Role(name="管理员")
role2 = Role(name="编辑")
user = User(username="admin")

# 先建立关联（此时都是新对象，可以直接 append）
user.roles.append(role1)
user.roles.append(role2)

# 一次性提交所有对象
from yweb.orm import db_manager
session = db_manager.get_session()
session.add_all([role1, role2, user])
session.commit()

# 访问
print(user.roles)    # [Role1, Role2] - 正向访问
print(role1.users)   # [User1] - 反向访问

# 移除角色
user.roles.remove(role1)
user.save(True)
```

> ⚠️ **重要：使用单次提交模式**
>
> 操作多对多关系时，**必须使用单次提交模式**，将所有相关对象在同一事务中提交。
> 避免以下模式，否则 append 操作可能不生效：
>
> ```python
> # ❌ 不推荐：先提交再关联
> role.save(commit=True)        # 先提交角色
> user.roles.append(role)       # ⚠️ 可能失败！
> user.save(commit=True)
>
> # ✅ 推荐：单次提交
> user.roles.append(role)       # 先关联
> session.add_all([role, user])
> session.commit()              # 再提交
> ```
>
> **原因**：SQLAlchemy 默认配置 `expire_on_commit=True`，commit 后对象状态过期，
> 再执行 append 时可能被 SQLAlchemy 跳过。
>
> 如果必须先提交再关联，需要使用 `refresh()` 刷新对象：
> ```python
> role.save(commit=True)
> role.refresh()                # 刷新对象状态
> user.roles.append(role)       # 现在可以正常工作
> ```

### ManyToManyField 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `target_model` | class | 必填 | 关联的模型类（必须是类引用） |
| `on_delete` | 常量 | `None` | 软删除时的行为（`UNLINK` 推荐） |
| `backref` | 多种 | `True` | 反向引用名 |
| `table_name` | str | `None` | 中间表名（None 自动生成） |
| `related_name` | str | `None` | Django 风格反向引用（等同 backref） |

### 方式2：使用 Table + relationship（手动创建中间表）

```python
from sqlalchemy import Table, Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from yweb.orm import BaseModel, Base

# 手动定义中间表（不继承 BaseModel）
user_role = Table(
    "user_role",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("user.id"), primary_key=True),
    Column("role_id", Integer, ForeignKey("role.id"), primary_key=True),
)

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # 多对多关系
    roles = relationship(
        "Role",
        secondary=user_role,      # 指定中间表
        back_populates="users",
        lazy="selectin",
    )

class Role(BaseModel):
    role_name: Mapped[str] = mapped_column(String(50))
    
    users = relationship(
        "User",
        secondary=user_role,
        back_populates="roles",
    )

# 使用
user = User(username="admin")
role1 = Role(role_name="管理员")
role2 = Role(role_name="编辑")
role1.save(True)
role2.save(True)

# 添加角色
user.roles.append(role1)
user.roles.append(role2)
user.save(True)

# 访问
print(user.roles)   # [Role1, Role2]
print(role1.users)  # [User1]

# 移除角色
user.roles.remove(role1)
user.save(True)
```

### 方式3：使用 soft_relationship + UNLINK

```python
from yweb.orm import BaseModel, soft_relationship, UNLINK

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    
    # 多对多 + 软删除时解除关联
    roles = soft_relationship(
        "Role",
        secondary=user_role,
        backref="users",
        on_delete=UNLINK,  # 用户删除时，解除与角色的关联（不删除角色）
    )

# 使用
user.delete(True)  # 用户被软删除，user_role 中间表的关联记录被删除
# 但 Role 记录保持不变
```

### 带额外字段的中间表

如果中间表需要额外字段（如加入时间），使用关联对象模式：

```python
from datetime import datetime

class UserRole(BaseModel):
    """用户-角色关联表（带额外字段）"""
    __tablename__ = "user_role"
    __use_auto_pk__ = False  # 使用复合主键
    
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey("user.id"), primary_key=True)
    role_id: Mapped[int] = mapped_column(Integer, ForeignKey("role.id"), primary_key=True)
    
    # 额外字段
    granted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)
    granted_by: Mapped[str] = mapped_column(String(50), nullable=True)
    
    # 关系
    user = relationship("User", back_populates="user_roles")
    role = relationship("Role", back_populates="role_users")

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    user_roles = relationship("UserRole", back_populates="user")
    
    @property
    def roles(self):
        """便捷访问角色列表"""
        return [ur.role for ur in self.user_roles]

class Role(BaseModel):
    role_name: Mapped[str] = mapped_column(String(50))
    role_users = relationship("UserRole", back_populates="role")

# 使用
user = User(username="admin")
role = Role(role_name="管理员")
user.save(True)
role.save(True)

# 通过关联对象添加
user_role = UserRole(
    user_id=user.id,
    role_id=role.id,
    granted_by="system"
)
user_role.save(True)

# 访问额外字段
for ur in user.user_roles:
    print(f"{ur.role.role_name} - 授予于 {ur.granted_at}")
```

---

## 自关联 (Self-Referential)

记录关联同一张表的其他记录，常用于树形结构。

### 关系示意图

```
┌─────────────────────────────────────┐
│            Department               │
│─────────────────────────────────────│
│ id (PK)                             │
│ parent_id (FK) ──────┐              │
│ name                 │              │
│                      │              │
│ parent ◄─────────────┘              │
│   (单个对象，指向父节点)             │
│                                     │
│ children ────────────────────────►  │
│   (列表，包含所有子节点)             │
└─────────────────────────────────────┘
```

### 树形部门示例

```python
from sqlalchemy.orm import relationship
from sqlalchemy import ForeignKey, Integer

class Department(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("department.id"),  # 自引用
        nullable=True  # 根节点没有父节点
    )
    
    # 父节点（多对一）
    parent = relationship(
        "Department",
        remote_side="Department.id",  # 指定远端是 id 字段
        back_populates="children",
    )
    
    # 子节点（一对多）
    children = relationship(
        "Department",
        back_populates="parent",
        lazy="selectin",
    )
    
    def get_ancestors(self):
        """获取所有祖先节点"""
        ancestors = []
        current = self.parent
        while current:
            ancestors.append(current)
            current = current.parent
        return ancestors
    
    def get_descendants(self):
        """获取所有后代节点（递归）"""
        descendants = []
        for child in self.children:
            descendants.append(child)
            descendants.extend(child.get_descendants())
        return descendants
    
    def get_full_path(self, separator=" > "):
        """获取完整路径名"""
        ancestors = self.get_ancestors()
        names = [a.name for a in reversed(ancestors)] + [self.name]
        return separator.join(names)

# 使用
# 创建树形结构
root = Department(name="总公司")
root.save(True)

tech = Department(name="技术部", parent_id=root.id)
sales = Department(name="销售部", parent_id=root.id)
tech.save(True)
sales.save(True)

frontend = Department(name="前端组", parent_id=tech.id)
backend = Department(name="后端组", parent_id=tech.id)
frontend.save(True)
backend.save(True)

# 访问
print(frontend.parent.name)      # "技术部"
print(frontend.get_full_path())  # "总公司 > 技术部 > 前端组"
print(tech.children)             # [前端组, 后端组]
print(root.get_descendants())    # [技术部, 前端组, 后端组, 销售部]
```

### 使用 adjacency_list 优化（大量数据）

对于大量树形数据，可以使用物化路径（Materialized Path）优化：

```python
class Department(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    parent_id: Mapped[int] = mapped_column(Integer, ForeignKey("department.id"), nullable=True)
    
    # 物化路径：如 "/1/2/3/" 表示根->技术部->前端组
    path: Mapped[str] = mapped_column(String(500), default="/")
    level: Mapped[int] = mapped_column(Integer, default=1)
    
    def save(self, commit=False):
        """保存时自动更新路径"""
        if self.parent:
            self.path = f"{self.parent.path}{self.parent.id}/"
            self.level = self.parent.level + 1
        else:
            self.path = "/"
            self.level = 1
        return super().save(commit)
    
    @classmethod
    def get_subtree(cls, dept_id):
        """高效获取整个子树"""
        dept = cls.get(dept_id)
        if not dept:
            return []
        # 使用 LIKE 查询所有后代
        return cls.query.filter(
            cls.path.like(f"{dept.path}{dept.id}/%")
        ).all()
```

---

## 加载策略 (Loading Strategies)

### lazy 参数选项

| 策略 | 说明 | 适用场景 |
|------|------|----------|
| `select` | 访问时单独查询（默认） | 偶尔访问关联数据 |
| `selectin` | 使用 IN 子句批量加载 | 一对多，避免 N+1 |
| `joined` | 使用 JOIN 一次性加载 | 一对一，总是需要关联数据 |
| `subquery` | 使用子查询加载 | 复杂查询场景 |
| `dynamic` | 返回 Query 对象 | 大量关联数据，需要再过滤 |
| `noload` | 不加载关联数据 | 明确不需要关联数据 |

### 定义时指定

```python
class Department(BaseModel):
    # 使用 selectin 策略（推荐用于一对多）
    employees = relationship("Employee", lazy="selectin")

class User(BaseModel):
    # 使用 joined 策略（推荐用于一对一）
    profile = relationship("UserProfile", lazy="joined", uselist=False)
```

### 查询时覆盖

```python
from sqlalchemy.orm import joinedload, selectinload, noload

# 预加载关联数据
users = User.query.options(
    joinedload(User.profile),           # JOIN 加载 profile
    selectinload(User.roles),           # IN 子句加载 roles
).all()

# 不加载某个关联
users = User.query.options(
    noload(User.roles)
).all()

# 多层嵌套预加载
depts = Department.query.options(
    selectinload(Department.employees).selectinload(Employee.tasks)
).all()
```

### 避免 N+1 问题

```python
# ❌ 错误：N+1 问题（每个部门都会单独查询员工）
depts = Department.query.all()
for dept in depts:
    print(dept.employees)  # 每次循环都执行一次查询

# ✅ 正确：使用预加载
depts = Department.query.options(
    selectinload(Department.employees)
).all()
for dept in depts:
    print(dept.employees)  # 不会额外查询
```

---

## ForeignKeyField vs relationship 对比

### 使用 ForeignKeyField（推荐）

```python
class OrderItem(BaseModel):
    order = ForeignKeyField(Order, on_delete=DELETE)
    # 一行搞定：外键列 + relationship + backref
```

**优点**：
- 代码简洁（1 行 vs 4+ 行）
- Django 风格，容易理解
- 自动处理级联软删除

**适用场景**：
- 标准的一对多、多对一关系
- 需要级联软删除

### 使用 relationship（完全控制）

```python
class OrderItem(BaseModel):
    order_id: Mapped[int] = mapped_column(Integer, ForeignKey("order.id"))
    order = relationship(
        "Order",
        back_populates="items",
        lazy="selectin",
        cascade="save-update, merge",
    )
```

**优点**：
- 完全控制所有参数
- 支持更复杂的场景

**适用场景**：
- 需要自定义 lazy 策略
- 需要自定义 cascade 配置
- 多对多关系
- 自关联关系

---

## 常见问题

### 1. DetachedInstanceError

```python
# ❌ 错误：对象已从 session 分离
user = User.get(1)
user.detach()
print(user.roles)  # DetachedInstanceError!

# ✅ 正确：分离前预加载
user = User.query.options(selectinload(User.roles)).get(1)
user.detach()
print(user.roles)  # 正常访问
```

### 2. 循环引用

```python
# ❌ 错误：循环引用导致无限递归
user.to_dict()  # 如果 User 和 Role 互相引用

# ✅ 正确：使用 exclude 或自定义序列化
user.to_dict(exclude={"roles"})
```

### 3. back_populates vs backref

```python
# backref：只需在一边定义
class Order(BaseModel):
    items = relationship("OrderItem", backref="order")
# OrderItem 自动获得 order 属性

# back_populates：两边都要定义
class Order(BaseModel):
    items = relationship("OrderItem", back_populates="order")
    
class OrderItem(BaseModel):
    order = relationship("Order", back_populates="items")
```

**重要：共享外键的双向关系必须使用 `back_populates`**

如果两个 relationship 指向同一个外键列但没有用 `back_populates` 连接，SQLAlchemy 会产生警告：

```
SAWarning: relationship 'X.y' will copy column ... which conflicts with relationship(s): 'Y.x'
```

**示例：部门主负责人的双向关系**

```python
# ❌ 错误：两个关系指向同一外键但没有连接
class Department(BaseModel):
    primary_leader = relationship("Employee", foreign_keys="[Department.primary_leader_id]")

class Employee(BaseModel):
    leading_departments = relationship("Department", foreign_keys="[Department.primary_leader_id]")
    # 警告：与 Department.primary_leader 冲突！

# ✅ 正确：使用 back_populates 双向绑定
class Department(BaseModel):
    primary_leader = relationship(
        "Employee",
        foreign_keys="[Department.primary_leader_id]",
        back_populates="leading_departments",
    )

class Employee(BaseModel):
    leading_departments = relationship(
        "Department",
        foreign_keys="[Department.primary_leader_id]",
        back_populates="primary_leader",
    )
```

### 4. 为什么 append 后关系没有生效？

这通常是因为**先提交再关联**导致的：

```python
# ❌ 问题代码
role = Role(name="admin")
role.save(commit=True)  # 先提交

user = User(username="tom")
user.roles.append(role)  # append 可能被跳过！
user.save(commit=True)

print(len(user.roles))  # 可能是 0！
```

**原因**：SQLAlchemy 默认 `expire_on_commit=True`，commit 后对象状态过期。
当尝试将过期对象添加到关系集合时，SQLAlchemy 会发出警告并跳过操作。

**解决方案**：

```python
# 方案1（推荐）：使用单次提交模式
role = Role(name="admin")
user = User(username="tom")
user.roles.append(role)  # 都是新对象，直接关联
session.add_all([role, user])
session.commit()

# 方案2：使用 refresh() 刷新对象
role = Role(name="admin")
role.save(commit=True)
role.refresh()  # 刷新对象状态
user = User(username="tom")
user.roles.append(role)  # 现在可以正常工作
user.save(commit=True)
```

---

## 使用规范总结

### 模型定义时（推荐）

在定义模型类时，**推荐使用框架提供的高级 API**：

| 场景 | 推荐方式 | 说明 |
|------|---------|------|
| 简单外键（一对多/多对一） | `ForeignKeyField` | 1 行代码，自动处理外键列和 backref |
| 需要级联软删除 | `fields.ManyToOne` | 支持 `on_delete` 配置，推荐日常使用 |
| 一对一关系 | `fields.OneToOne` 或 `ForeignKeyField + ONE_TO_ONE` | 自动添加 `uselist=False` |
| 多对多关系 | `fields.ManyToMany` | 自动创建中间表 |

```python
# ✅ 推荐：使用 fields.* API
class OrderItem(BaseModel):
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)

# ✅ 推荐：使用 ForeignKeyField
class Employee(BaseModel):
    department = ForeignKeyField(Department, on_delete=CLEAR_FK)
```

### 动态添加关系时（框架内部场景）

在**运行时**为已存在的模型动态添加关系时，必须使用原生 `relationship()`：

| 场景 | 使用方式 | 示例 |
|------|---------|------|
| 框架内部动态设置 | `relationship()` | `setup_org_relationships()` |
| 抽象类的关系（子类名称未知） | `relationship()` | 组织模块的关系设置 |

**关键规则**：

1. **双向关系必须使用 `back_populates`**：两边都要显式声明
2. **共享外键的关系必须连接**：避免 SAWarning 警告

```python
# ✅ 正确：动态添加双向关系
dept_model.primary_leader = relationship(
    emp_name,
    foreign_keys=f"[{dept_name}.primary_leader_id]",
    back_populates="leading_departments",  # 必须与另一端匹配
)

employee_model.leading_departments = relationship(
    dept_name,
    foreign_keys=f"[{dept_name}.primary_leader_id]",
    back_populates="primary_leader",  # 必须与另一端匹配
)
```

### 不推荐的方式

| 方式 | 原因 |
|------|------|
| 模型定义时直接使用 `relationship()` | 代码量多，需手动处理外键列，无级联软删除 |
| 共享外键的关系不用 `back_populates` | 会产生 SAWarning 警告 |
| 使用传统 `ForeignKey` + `relationship` | 无法使用框架的级联软删除功能 |

### 选择指南

```
定义模型关系？
    ├── 需要级联软删除 → fields.ManyToOne / fields.ManyToMany
    ├── 简单外键，无级联需求 → ForeignKeyField
    └── 框架内部动态添加 → 原生 relationship() + back_populates
```

---

## 在 Mixin 中定义关系字段

`fields.OneToOne`、`fields.ManyToOne`、`fields.ManyToMany` 均支持在 Mixin 类中定义，框架会自动通过 MRO 扫描识别并处理：

```python
from yweb.orm import fields

# 定义 Mixin
class UserLinkMixin:
    """关联用户账号"""
    user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)

class TaggableMixin:
    """关联标签（多对多）"""
    tags = fields.ManyToMany(Tag, on_delete=fields.UNLINK)

# 使用 Mixin
class Employee(UserLinkMixin, BaseModel):
    __tablename__ = "employee"
    name: Mapped[str] = mapped_column(String(100))
    # 自动拥有 user_id 列 + user relationship

class Article(TaggableMixin, BaseModel):
    __tablename__ = "article"
    title: Mapped[str] = mapped_column(String(200))
    # 自动拥有 tags 多对多关系
```

> **工厂模式同样适用**：通过 `setup_organization(employee_mixin=...)` 等参数传入的 Mixin 也能正常工作。

---

## 下一步

- [04_CRUD操作](04_crud_operations.md) - 学习基本增删改查
- [08_级联软删除](08_cascade_soft_delete.md) - 了解 soft_relationship 详细用法
- [04_查询与过滤](04_query_and_filter.md) - 学习高级查询技巧
