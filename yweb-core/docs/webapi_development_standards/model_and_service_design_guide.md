# Model 与 Service 层设计规范

本文档定义了 yweb 框架中 Model（ORM 模型）和 Service 层的设计规范。

---

## 目录

1. [Model 设计规范](#1-model-设计规范)
2. [Service 层设计规范](#2-service-层设计规范)
3. [设计决策记录](#3-设计决策记录)

---

## 1. Model 设计规范

### 1.1 字段必须有 comment（强制）

**所有 Model 字段必须添加 `comment` 参数**，用于：
- 生成数据库字段注释
- 提高代码可读性
- 便于自动生成文档

#### 正确示例

```python
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column
from yweb.orm import BaseModel

class Department(BaseModel):
    """部门模型"""
    __tablename__ = "department"
    
    # ✅ 正确：每个字段都有 comment
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="部门名称"  # ✅ 必须有
    )
    
    code: Mapped[str] = mapped_column(
        String(100),
        nullable=True,
        comment="部门编码"  # ✅ 必须有
    )
    
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        comment="是否启用"  # ✅ 必须有
    )
    
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="排序序号"  # ✅ 必须有
    )
    
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("department.id"),
        nullable=True,
        comment="父部门ID"  # ✅ 必须有
    )
```

#### 错误示例

```python
class Department(BaseModel):
    # ❌ 错误：缺少 comment
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    
    # ❌ 错误：缺少 comment
    code: Mapped[str] = mapped_column(String(100))
```

### 1.2 字段命名规范

| 字段类型 | 命名规范 | 示例 |
|---------|---------|------|
| 主键 | `id` | `id` |
| 外键 | `{关联表名单数}_id` | `department_id`, `user_id` |
| 布尔值 | `is_{状态}` 或 `has_{属性}` | `is_active`, `is_deleted`, `has_children` |
| 时间戳 | `{动作}_at` | `created_at`, `updated_at`, `deleted_at` |
| 计数 | `{对象}_count` | `employee_count`, `view_count` |
| 排序 | `sort_order` 或 `sequence` | `sort_order` |

### 1.3 继承 BaseModel

所有业务模型应继承 `BaseModel`，自动获得：
- `id`: 主键（支持自增、UUID、雪花ID 等）
- `created_at`: 创建时间
- `updated_at`: 更新时间
- `deleted_at`: 软删除时间
- `ver`: 乐观锁版本号
- `name`, `code`, `note`, `caption`: 常用业务字段

```python
from yweb.orm import BaseModel

class Organization(BaseModel):
    """组织模型"""
    __tablename__ = "organization"
    
    # 自定义字段
    full_name: Mapped[str] = mapped_column(
        String(500),
        nullable=True,
        comment="组织全称"
    )
```

### 1.4 declared_attr 字段规范

使用 `@declared_attr` 定义动态字段时，同样需要在 `mapped_column` 中添加 comment：

```python
from sqlalchemy.orm import declared_attr, Mapped, mapped_column

class AbstractDepartment(BaseModel):
    __abstract__ = True
    
    @declared_attr
    def org_id(cls) -> Mapped[int]:
        """所属组织ID"""
        org_tablename = getattr(cls, '__org_tablename__', 'organization')
        return mapped_column(
            Integer,
            ForeignKey(f"{org_tablename}.id"),
            nullable=False,
            comment="所属组织ID"  # ✅ 必须有
        )
```

### 1.5 关系定义规范（重要）

> ⚠️ **重要**：定义模型关系时，**必须使用 `fields.*` API**，而不是传统的 `ForeignKey` + `relationship`。框架提供了级联软删除功能，正确配置 `on_delete` 参数可自动处理关联数据。

#### 推荐方式：使用 fields.* API

```python
from yweb.orm import BaseModel, fields

class OrderItem(BaseModel):
    """订单项"""
    product_name: Mapped[str] = mapped_column(String(100), comment="产品名称")
    
    # ✅ 推荐：使用 fields.ManyToOne，支持级联删除
    order = fields.ManyToOne(
        Order,
        on_delete=fields.DELETE,  # 订单删除时，订单项也被软删除
        nullable=False,
    )

class Employee(BaseModel):
    """员工"""
    name: Mapped[str] = mapped_column(String(100), comment="姓名")
    
    # ✅ 推荐：部门删除时，员工的 department_id 设为 NULL
    department = fields.ManyToOne(
        Department,
        on_delete=fields.SET_NULL,
        nullable=True,
    )

class User(BaseModel):
    """用户"""
    # ✅ 推荐：用户删除时，解除与角色的关联
    roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)
```

#### 不推荐方式：传统 ForeignKey

```python
# ❌ 不推荐：传统方式没有级联删除功能
class OrderItem(BaseModel):
    order_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("order.id"),  # ❌ 没有级联删除配置
        nullable=False,
    )
```

#### 级联删除类型

| 类型 | 常量 | 说明 | 适用场景 |
|------|------|------|----------|
| DELETE | `fields.DELETE` | 级联软删除子记录 | 订单→订单项（强聚合） |
| SET_NULL | `fields.SET_NULL` | 将外键设为 NULL | 部门→员工（员工可调岗） |
| UNLINK | `fields.UNLINK` | 解除多对多关联 | 用户→角色 |
| PROTECT | `fields.PROTECT` | 有子记录时禁止删除 | 分类→产品 |
| DO_NOTHING | `fields.DO_NOTHING` | 不处理 | 日志等弱关联 |

详细说明请参考 [08_级联软删除](../orm_docs/08_cascade_soft_delete.md) 文档。

#### 特殊场景：框架内部动态添加关系

在框架内部（如 `setup_org_relationships()`）**动态**为已存在的模型添加关系时，需使用原生 `relationship()`：

```python
# 框架内部动态设置关系示例
def setup_org_relationships(org_model, dept_model, employee_model, ...):
    # 必须使用 back_populates 双向绑定
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

> **注意**：此场景仅限框架内部使用，业务代码应始终使用 `fields.*` API。

---

## 2. Service 层设计规范

### 2.1 不使用泛型（重要）

**服务基类不使用 Python 泛型（Generic）**，避免 IDE 类型推断问题。

#### 设计决策背景

Python 的泛型类型系统存在以下问题：
1. TypeVar 没有 bound 时，IDE 无法推断方法返回类型
2. 即使添加 bound，子类仍需显式指定泛型参数才能获得精确类型推断
3. 多个 TypeVar 参数（如 6 个）使用起来非常繁琐

#### 推荐设计

使用简单的基类继承，通过类属性指定具体模型：

```python
from abc import ABC
from typing import Type, Optional, List
from yweb.orm import BaseModel

class BaseOrganizationService(ABC):
    """组织服务基类
    
    设计说明：
    - 不使用泛型，避免 IDE 类型推断问题
    - 子类通过类属性指定具体的模型类
    - 返回类型使用 BaseModel，实际返回具体模型实例
    """
    
    # 模型类配置（子类必须设置）
    org_model: Type[BaseModel] = None
    dept_model: Type[BaseModel] = None
    employee_model: Type[BaseModel] = None
    
    def create_org(self, name: str, code: str, **kwargs) -> BaseModel:
        """创建组织"""
        org = self.org_model(name=name, code=code, **kwargs)
        org.save(commit=True)
        return org
    
    def get_org(self, org_id: int) -> Optional[BaseModel]:
        """获取组织"""
        return self.org_model.get(org_id)
```

#### 子类实现

```python
from yweb.organization import BaseOrganizationService
from .models import Organization, Department, Employee

class OrganizationService(BaseOrganizationService):
    """组织服务实现"""
    org_model = Organization
    dept_model = Department
    employee_model = Employee
    # ... 其他模型
```

### 2.2 为什么不使用泛型？

| 方案 | 优点 | 缺点 |
|------|------|------|
| **泛型方案** | 理论上类型更精确 | IDE 推断困难、使用繁琐、学习成本高 |
| **BaseModel 方案（推荐）** | 简单易用、IDE 友好 | 返回类型不够精确（但实际使用影响小） |

Python 是动态类型语言，类型注解只是辅助，不影响运行时行为。牺牲一点类型精确度，换来更简单的代码，是合理的取舍。

### 2.3 方法返回类型规范

| 操作类型 | 返回类型 | 示例 |
|---------|---------|------|
| 创建单个对象 | `BaseModel` | `def create_org(...) -> BaseModel` |
| 获取单个对象 | `Optional[BaseModel]` | `def get_org(...) -> Optional[BaseModel]` |
| 获取列表 | `List[BaseModel]` | `def list_orgs() -> List[BaseModel]` |
| 更新对象 | `BaseModel` 或 `Optional[BaseModel]` | `def update_org(...) -> BaseModel` |
| 删除对象 | `None` 或 `Dict[str, Any]` | `def delete_org(...) -> None` |

### 2.4 向后兼容

为保持向后兼容，旧的类名保留为别名：

```python
# services/__init__.py
from .org_service import BaseOrganizationService
from .sync_service import BaseSyncService

# 向后兼容别名
AbstractOrganizationService = BaseOrganizationService
AbstractSyncService = BaseSyncService
```

---

## 3. 设计决策记录

### 3.1 ADR-001: 服务层放弃泛型设计

**日期**: 2026-01-29

**状态**: 已采纳

**背景**:
原服务层设计使用 Python 泛型：
```python
class AbstractOrganizationService(ABC, Generic[TOrg, TDept, TEmployee, ...]):
    org_model: Type[TOrg] = None
```

存在问题：
1. `TOrg = TypeVar('TOrg')` 没有 bound，IDE 无法推断 `TOrg` 的方法
2. F12 无法导航到 `dept.save()`, `service.create_org()` 等方法
3. 6 个泛型参数使用繁琐

**决策**:
- 移除 `Generic[...]` 和所有 `TypeVar` 定义
- 类属性使用 `Type[BaseModel]` 作为类型
- 方法返回类型使用 `BaseModel` 或 `Optional[BaseModel]`
- 类名从 `AbstractXxxService` 改为 `BaseXxxService`
- 保留旧类名作为向后兼容别名

**影响**:
- ✅ IDE 类型推断正常工作（F12 可导航）
- ✅ 代码更简洁易懂
- ⚠️ 返回类型不够精确（返回 `BaseModel` 而非具体类型）
- ✅ 运行时行为完全相同

### 3.2 ADR-002: Model 字段必须有 comment

**日期**: 2026-01-29

**状态**: 已采纳

**背景**:
部分 Model 字段没有添加 `comment` 参数，导致：
- 数据库字段没有注释
- 代码可读性降低
- 难以自动生成文档

**决策**:
- 所有 Model 字段必须添加 `comment` 参数
- Code Review 时检查此项
- 可考虑添加自动检查工具

**示例**:
```python
# ✅ 正确
name: Mapped[str] = mapped_column(String(255), comment="名称")

# ❌ 错误
name: Mapped[str] = mapped_column(String(255))
```

---

## 4. 检查清单

### Model 检查清单

- [ ] 所有字段都有 `comment` 参数
- [ ] 字段命名符合规范（外键用 `_id` 后缀，布尔值用 `is_` 前缀）
- [ ] 继承正确的基类（`BaseModel` 或抽象模型）
- [ ] `__tablename__` 已定义
- [ ] **关系使用 `fields.*` API 定义**，而不是传统 `ForeignKey`
- [ ] **已配置正确的 `on_delete` 参数**（DELETE/SET_NULL/UNLINK/PROTECT）

### Service 检查清单

- [ ] 继承 `BaseXxxService` 基类
- [ ] 所有必需的模型类属性已设置
- [ ] 方法返回类型使用 `BaseModel` 或 `Optional[BaseModel]`
- [ ] 业务逻辑抛出 `ValueError` 表示规则违反
- [ ] 复杂方法使用 `@transactional` 装饰器自动管理事务
- [ ] 内部辅助方法（`_xxx`）不自行提交，由事务管理器统一处理
