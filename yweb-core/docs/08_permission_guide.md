# 权限管理模块使用指南

本指南详细介绍如何使用 YWeb 的权限管理模块（Permission Module）。

## 概述

权限管理模块提供了一套完整的 RBAC（基于角色的访问控制）框架，支持：

- **角色管理**：支持树形角色继承结构
- **权限管理**：灵活的权限定义（resource:action 格式）
- **双用户体系**：内部员工和外部用户统一授权
- **多级授权**：通过角色授权 + 直接授权
- **权限缓存**：TTL 自动过期 + 主动失效
- **FastAPI 集成**：依赖注入和装饰器
- **API 管理**：提供完整的管理接口

## 目录

- [快速开始](#快速开始)
- [定义模型](#定义模型)
  - [扩展模型字段](#扩展模型字段)
- [初始化服务](#初始化服务)
- [权限检查](#权限检查)
- [角色管理](#角色管理)
- [用户授权](#用户授权)
- [缓存管理](#缓存管理)
- [API 路由](#api-路由)
- [与组织模块集成](#与组织模块集成)
- [最佳实践](#最佳实践)
  - [路由前缀约定](#6-路由前缀约定)
  - [细粒度权限控制](#7-细粒度权限控制)
  - [API 资源与权限绑定](#8-api-资源与权限绑定)
- [异常处理](#异常处理)

---

## 快速开始

权限模块提供三种使用级别，按需选择：

| 级别 | 代码量 | 灵活性 | 适用场景 |
|------|--------|--------|----------|
| 级别1 | ~5行 | 低 | 快速原型、零自定义 |
| 级别2 | ~15行 | 中 | 需要少量扩展字段 |
| 级别3 | ~80行 | 高 | 复杂定制需求 |

### 级别1：一站式设置（推荐新项目）

```python
from fastapi import FastAPI, Depends
from yweb.permission import setup_permission, require_permission

app = FastAPI()

# 一行代码完成全部配置
perm = setup_permission(
    app=app,
    api_prefix="/api/v1/permission",
    table_prefix="sys_",
)

# 直接使用权限检查
@app.get("/users")
async def list_users(user = Depends(require_permission("user:list"))):
    return {"users": [...]}
```

`setup_permission()` 会自动完成以下步骤：

1. 创建所有模型（Permission, Role, SubjectRole, RolePermission, SubjectPermission）
2. 初始化权限依赖（`init_permission_dependency`）
3. 创建完整的管理 API 路由
4. 将路由挂载到 FastAPI 应用

返回的 `perm` 对象包含所有模型和服务入口，详见 [PermissionModels 返回对象](#permissionmodels-返回对象)。

### 级别2：分步设置（更灵活）

适用于需要在创建模型和挂载路由之间插入自定义逻辑的场景：

```python
from yweb.permission import create_permission_models

# 1. 创建所有模型
perm = create_permission_models(table_prefix="sys_")

# 2. 在此处可插入自定义逻辑...

# 3. 初始化依赖
perm.init_dependency()

# 4. 挂载路由
perm.mount_routes(
    app,
    prefix="/api/v1/permission",
    dependencies=[Depends(require_role("admin"))],
)
```

### 级别3：完全自定义（继承抽象类）

需要完全控制时，继承抽象模型：

```python
from yweb.permission.models import (
    AbstractPermission,
    AbstractRole,
    AbstractSubjectRole,
    AbstractRolePermission,
    AbstractSubjectPermission,
    AbstractAPIResource,
)
from yweb.permission import setup_permission_relationships  # 辅助函数

# 权限模型
class Permission(AbstractPermission):
    __tablename__ = "sys_permission"
    enable_history = True  # 启用变更历史记录

# 角色模型（支持树形继承）
class Role(AbstractRole):
    __tablename__ = "sys_role"
    __role_tablename__ = "sys_role"  # 用于自引用外键
    enable_history = True

# 主体-角色关联
class SubjectRole(AbstractSubjectRole):
    __tablename__ = "sys_subject_role"
    __role_tablename__ = "sys_role"

# 角色-权限关联
class RolePermission(AbstractRolePermission):
    __tablename__ = "sys_role_permission"
    __role_tablename__ = "sys_role"
    __permission_tablename__ = "sys_permission"

# 主体直接权限（可选）
class SubjectPermission(AbstractSubjectPermission):
    __tablename__ = "sys_subject_permission"
    __permission_tablename__ = "sys_permission"

# API 资源（可选）
class APIResource(AbstractAPIResource):
    __tablename__ = "sys_api_resource"
    __permission_tablename__ = "sys_permission"

# 使用辅助函数自动设置所有 relationship（推荐）
setup_permission_relationships(
    Permission, Role, SubjectRole, RolePermission, SubjectPermission
)
```

> **提示**：`setup_permission_relationships()` 会自动为角色添加 `parent`、`children` 树形关系，以及各关联模型添加 `role`、`permission` 等 relationship 属性。

**初始化服务**（级别3 需手动初始化）：

```python
from fastapi import FastAPI
from yweb.permission import init_permission_dependency

app = FastAPI()

@app.on_event("startup")
async def startup():
    init_permission_dependency(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
    )
```

### PermissionModels 返回对象

`create_permission_models()` 和 `setup_permission()` 返回的 `PermissionModels` 对象包含：

```python
perm = create_permission_models()

# 模型类
perm.Permission          # 权限模型
perm.Role                # 角色模型
perm.SubjectRole         # 主体-角色关联
perm.RolePermission      # 角色-权限关联
perm.SubjectPermission   # 主体-权限关联
perm.APIResource         # API 资源模型（需 include_api_resource=True）

# 服务（单例模式）
perm.get_permission_service()   # 权限服务
perm.get_role_service()         # 角色服务

# 工具方法
perm.as_dict()           # 返回所有模型的字典，用于 create_permission_router(**perm.as_dict())
perm.init_dependency()   # 初始化权限依赖
perm.mount_routes(app)   # 挂载路由
```

### 在路由中使用权限检查

```python
from fastapi import Depends
from yweb.permission import require_permission, require_role

@app.get("/users")
async def list_users(user = Depends(require_permission("user:list"))):
    """需要 user:list 权限"""
    return {"users": [...]}

@app.delete("/users/{id}")
async def delete_user(id: int, user = Depends(require_role("admin"))):
    """需要 admin 角色"""
    return {"message": "deleted"}
```

### Mixin 扩展字段

使用 Mixin 为模型添加自定义字段（适用于级别1和级别2）：

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

# 为权限模型添加额外字段
class PermissionMixin:
    icon: Mapped[str] = mapped_column(String(50), nullable=True, comment="图标")

# 为角色模型添加额外字段
class RoleMixin:
    color: Mapped[str] = mapped_column(String(20), nullable=True, comment="显示颜色")

perm = setup_permission(
    app=app,
    table_prefix="sys_",
    permission_mixin=PermissionMixin,
    role_mixin=RoleMixin,
)
```

---

## 定义模型

### 权限模型 (AbstractPermission)

权限是系统中最小的授权单元，格式为 `resource:action`。

```python
class Permission(AbstractPermission):
    __tablename__ = "sys_permission"
    enable_history = True
```

**内置字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | String(100) | 权限编码，唯一，如 `user:read` |
| `name` | String(100) | 权限名称，如 "查看用户" |
| `resource` | String(50) | 资源类型，如 `user` |
| `action` | String(50) | 操作类型，如 `read` |
| `description` | Text | 权限描述 |
| `module` | String(50) | 所属模块，用于分组 |
| `is_active` | Boolean | 是否启用 |
| `sort_order` | Integer | 排序 |

### 角色模型 (AbstractRole)

继承自 `yweb.auth.AbstractSimpleRole`（轻量级角色），在此基础上扩展树形继承结构。
子角色自动继承父角色的所有权限。从轻量版升级到完整版时，`User.has_role()` / `User.role_codes` 等 API 保持不变。

```python
class Role(AbstractRole):
    __tablename__ = "sys_role"
    __role_tablename__ = "sys_role"
    enable_history = True
```

**内置字段**：

| 字段 | 类型 | 说明 |
|------|------|------|
| `code` | String(50) | 角色编码，唯一 |
| `name` | String(100) | 角色名称 |
| `description` | Text | 角色描述 |
| `parent_id` | Integer | 父角色ID（支持继承） |
| `is_active` | Boolean | 是否启用 |
| `is_system` | Boolean | 是否系统内置（不可删除） |
| `path` | String(500) | 树形路径 |
| `level` | Integer | 层级 |
| `sort_order` | Integer | 排序 |

**角色继承示例**：

```
super_admin
├── admin (继承 super_admin 的权限)
│   ├── manager (继承 admin 的权限)
│   └── operator (继承 admin 的权限)
└── auditor
```

### 用户模型（与认证模块集成）

权限模块不单独提供用户模型。用户模型由认证模块的 `AbstractUser` 提供，通过混入 `ExternalUserSubjectMixin` 获得权限主体能力：

```python
from yweb.auth import AbstractUser
from yweb.permission.mixins import ExternalUserSubjectMixin

class User(AbstractUser, ExternalUserSubjectMixin):
    __tablename__ = "sys_user"
    
    # 可添加自定义字段
    company = mapped_column(String(200), comment="公司名称")

# User 实例自动拥有 subject_id 属性
user = User.get(456)
user.subject_id  # "external:456"
```

**AbstractUser 内置字段**（来自 `yweb.auth`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| `username` | String(50) | 用户名，唯一 |
| `password_hash` | String(255) | 密码哈希 |
| `email` | String(255) | 邮箱 |
| `phone` | String(20) | 手机号 |
| `is_active` | Boolean | 是否启用 |
| `last_login_at` | DateTime | 最后登录时间 |

### 扩展模型字段

框架支持在继承抽象模型时添加自定义字段，**扩展字段会自动出现在 API 响应中**，无需修改任何框架代码。

#### 示例：为角色添加部门关联

```python
from yweb.permission import AbstractRole
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class Role(AbstractRole):
    __tablename__ = "sys_role"
    __role_tablename__ = "sys_role"
    
    # 添加自定义字段
    department_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("sys_department.id"), 
        nullable=True,
        comment="所属部门ID"
    )
    
    remark: Mapped[str] = mapped_column(
        String(500), 
        nullable=True,
        comment="备注信息"
    )
```

#### API 响应自动包含扩展字段

无需任何额外配置，调用 API 时扩展字段会自动返回：

```bash
GET /api/permission/roles/get?code=admin
```

```json
{
    "code": 200,
    "data": {
        "id": 1,
        "code": "admin",
        "name": "管理员",
        "description": "系统管理员",
        "is_active": true,
        "is_system": true,
        "level": 1,
        "sort_order": 0,
        "created_at": "2026-01-25T10:00:00",
        "department_id": 5,
        "remark": "这是管理员角色的备注"
    }
}
```

#### 工作原理

1. **SQLAlchemy 自动合并字段**：继承的子类会自动包含父类和子类的所有 `mapped_column`
2. **数据库自动创建列**：`create_all()` 时会自动创建扩展字段对应的列
3. **`to_dict()` 返回完整数据**：ORM 的 `to_dict()` 方法使用反射获取所有列，包括扩展字段
4. **Schema 允许额外字段**：响应 Schema 配置了 `extra="allow"`，允许额外字段通过

```python
# Schema 定义（框架内部）
class RoleResponse(BaseModel):
    id: int
    code: str
    name: str
    # ... 核心字段
    
    # 允许额外字段通过
    model_config = ConfigDict(from_attributes=True, extra="allow")
```

#### 适用范围

以下模型都支持扩展字段自动返回：

| 模型 | 响应 Schema |
|------|------------|
| `AbstractPermission` | `PermissionResponse` |
| `AbstractRole` | `RoleResponse` |
| `AbstractSubjectRole` | `SubjectRoleResponse` |
| `AbstractSubjectPermission` | `SubjectPermissionResponse` |
| `AbstractAPIResource` | `APIResourceResponse` |

#### 注意事项

- **数据库初始化**：扩展模型的使用流程与标准模型完全一致，无需特殊配置

```python
# main.py
from yweb.orm import init_database, Base, get_engine

# 1. 导入扩展后的模型（确保模型被 Python 加载）
from myapp.models.permission import Permission, Role  # 你的扩展模型

# 2. 初始化数据库
init_database("sqlite:///./app.db")

# 3. 创建表（会自动包含扩展字段对应的列）
Base.metadata.create_all(get_engine())
```

- **OpenAPI 文档**：扩展字段会正常返回，但 Swagger 文档中不会显示这些字段的类型定义（因为 Schema 中未定义）
- **如需完整文档**：可以自定义响应 Schema 继承基类并添加扩展字段定义

```python
from yweb.permission.schemas import RoleResponse

# 自定义 Schema（可选，仅为了完整的 OpenAPI 文档）
class MyRoleResponse(RoleResponse):
    department_id: Optional[int] = None
    remark: Optional[str] = None
```

---

## 权限检查

### 使用 FastAPI 依赖注入

```python
from yweb.permission import require_permission, require_role, require_any_permission

# 需要单个权限
@app.get("/users")
async def list_users(user = Depends(require_permission("user:list"))):
    ...

# 需要多个权限（全部满足）
@app.put("/users/{id}")
async def update_user(
    id: int,
    user = Depends(require_permission("user:read", "user:update"))
):
    ...

# 需要任一权限
@app.get("/reports")
async def view_reports(
    user = Depends(require_any_permission("report:view", "admin:*"))
):
    ...

# 需要角色
@app.delete("/users/{id}")
async def delete_user(id: int, user = Depends(require_role("admin"))):
    ...

# 需要任一角色
@app.post("/system/config")
async def update_config(user = Depends(require_role("admin", "super_admin"))):
    ...
```

### 使用装饰器

适用于普通函数：

```python
from yweb.permission import permission_required, role_required

@permission_required("user:read")
def get_user(subject_id: str, user_id: int):
    """subject_id 参数用于权限检查"""
    return User.get(user_id)

@role_required("admin")
def admin_operation(subject_id: str):
    ...

# 自定义参数名
@permission_required("order:read", subject_id_param="current_user")
def get_orders(current_user: str):
    ...
```

### 使用服务类

更灵活的检查方式：

```python
from yweb.permission import get_permission_service

perm_service = get_permission_service()

# 检查单个权限
if perm_service.check_permission("employee:123", "user:read"):
    # 有权限
    ...

# 检查多个权限
if perm_service.check_permissions(
    "employee:123",
    ["user:read", "user:write"],
    require_all=True  # 需要全部权限
):
    ...

# 检查角色
if perm_service.check_role("employee:123", "admin"):
    ...

# 获取用户所有权限
permissions = perm_service.get_all_permissions("employee:123")
# {"user:read", "user:write", "order:list", ...}

# 获取用户所有角色
roles = perm_service.get_all_roles("employee:123")
# {"admin", "manager"}
```

---

## 角色管理

### 创建角色

```python
from yweb.permission import RoleService

role_service = RoleService(
    role_model=Role,
    permission_model=Permission,
    role_permission_model=RolePermission,
    subject_role_model=SubjectRole,
)

# 创建根角色
admin = role_service.create_role(
    code="admin",
    name="管理员",
    description="系统管理员",
    is_system=True,  # 系统角色不可删除
)

# 创建子角色（继承 admin 的权限）
manager = role_service.create_role(
    code="manager",
    name="经理",
    parent_code="admin",  # 继承 admin
)
```

### 设置角色权限

```python
# 全量设置
role_service.set_role_permissions("admin", [
    "user:read", "user:write", "user:delete",
    "order:read", "order:write",
    "system:config",
])

# 添加单个权限
role_service.add_role_permission("manager", "report:view")

# 移除权限
role_service.remove_role_permission("manager", "system:config")

# 获取角色权限
permissions = role_service.get_role_permissions("admin")
# 仅直接权限

all_permissions = role_service.get_role_all_permissions("manager")
# 含继承的权限
```

### 角色树操作

```python
# 获取角色树
tree = role_service.get_role_tree()

# 获取角色的子角色
role = Role.get_by_code("admin")
children = role.get_children()

# 获取角色的所有后代
descendants = role.get_descendants()

# 获取角色的祖先
ancestors = role.get_ancestors()
```

---

## 用户授权

### 主体标识 (Subject ID)

权限系统使用统一的主体标识格式：`{type}:{id}`

- 内部员工：`employee:123`
- 外部用户：`external:456`

```python
from yweb.permission import make_subject_id, parse_subject_id, UserType

# 创建主体ID
subject_id = make_subject_id(UserType.EMPLOYEE, 123)
# "employee:123"

# 解析主体ID
subject_type, id_value = parse_subject_id("employee:123")
# ("employee", 123)
```

### 分配角色

```python
perm_service = get_permission_service()

# 分配角色
perm_service.assign_role(
    subject_id="employee:123",
    role_code="manager",
    granted_by=admin_id,  # 可选：授权人
)

# 分配临时角色（有过期时间）
from datetime import datetime, timedelta

perm_service.assign_role(
    subject_id="employee:123",
    role_code="temp_admin",
    expires_at=datetime.now() + timedelta(days=7),
)

# 撤销角色
perm_service.unassign_role("employee:123", "manager")
```

### 直接授权

绕过角色，直接给用户授权（适用于临时权限）：

```python
# 授予直接权限
perm_service.grant_subject_permission(
    subject_id="employee:123",
    permission_code="finance:report",
    expires_at=datetime(2026, 12, 31),
    reason="临时需要查看财务报告",
)

# 撤销直接权限
perm_service.revoke_subject_permission("employee:123", "finance:report")
```

---

## 缓存管理

权限模块使用内存缓存提升性能，基于 `cachetools.TTLCache`。

### 缓存配置

```python
from yweb.permission import configure_cache

# 配置缓存参数
configure_cache(
    maxsize=10000,    # 最大缓存条目数（约等于活跃用户数）
    ttl=300,          # 过期时间（秒），默认 5 分钟
    enable_stats=True,  # 启用统计
)
```

### 缓存结构

权限缓存包含三个独立的缓存：

| 缓存 | 键格式 | 值 | 说明 |
|------|--------|-----|------|
| permission_cache | `perm:{subject_id}:v{version}` | `Set[permission_code]` | 用户权限 |
| role_cache | `role:{subject_id}:v{version}` | `Set[role_code]` | 用户角色 |
| role_permission_cache | `role_perm:{role_code}:v{version}` | `Set[permission_code]` | 角色权限 |

### 版本号批量失效机制

权限缓存使用**版本号机制**实现高效的批量失效，无需遍历删除所有缓存。

**原理：**

```
┌─────────────────────────────────────────────────────────────┐
│                    版本号批量失效原理                        │
└─────────────────────────────────────────────────────────────┘

  初始状态（version=0）:
  ┌─────────────────────────────────────┐
  │  缓存内容                            │
  │  perm:user1:v0 → {read, write}      │
  │  perm:user2:v0 → {read}             │
  │  perm:user3:v0 → {admin}            │
  └─────────────────────────────────────┘

  调用 invalidate_all() 后（version=1）:
  ┌─────────────────────────────────────┐
  │  缓存内容（旧数据还在，但访问不到）    │
  │  perm:user1:v0 → {read, write}  ← 旧版本，匹配不到 │
  │  perm:user2:v0 → {read}         ← 旧版本，匹配不到 │
  │  perm:user3:v0 → {admin}        ← 旧版本，匹配不到 │
  └─────────────────────────────────────┘
  
  新请求查询 user1 的权限:
  - 生成键: perm:user1:v1  ← 新版本
  - 在缓存中找不到（因为旧数据是 v0）
  - 返回 None（缓存未命中）
  - 重新从数据库加载
```

**优点：**
- O(1) 复杂度实现批量失效
- 不需要遍历删除所有缓存
- 旧数据等 TTL 过期后自动回收

### 自动缓存失效

权限服务层（PermissionService、RoleService）在执行变更操作时会**自动调用**相应的缓存失效方法，无需手动处理。

**服务层自动失效对照表：**

| 操作 | 服务方法 | 自动调用的失效方法 |
|------|---------|-------------------|
| 分配权限给用户 | `assign_permission()` | `invalidate_subject(subject_id)` |
| 撤销用户权限 | `revoke_permission()` | `invalidate_subject(subject_id)` |
| 同步用户权限 | `sync_permissions()` | `invalidate_subject(subject_id)` |
| 分配角色给用户 | `assign_role()` | `invalidate_subject(subject_id)` |
| 撤销用户角色 | `unassign_role()` | `invalidate_subject(subject_id)` |
| 修改权限状态 | `update_permission()` | `invalidate_all()` |
| 删除权限 | `delete_permission()` | `invalidate_all()` |
| 修改角色状态 | `update_role()` | `invalidate_all()` |
| 删除角色 | `delete_role()` | `invalidate_all()` |
| 更新角色权限 | `set_role_permissions()` | `invalidate_role()` + `invalidate_subjects_batch()` |
| 添加角色权限 | `add_role_permission()` | `invalidate_role()` + `invalidate_subjects_batch()` |
| 移除角色权限 | `remove_role_permission()` | `invalidate_role()` + `invalidate_subjects_batch()` |

**级联失效说明：**

当角色权限变更时，除了失效角色缓存，还需要失效所有拥有该角色的用户缓存：

```python
# 服务层内部实现（自动处理）
def add_role_permission(self, role_code: str, permission_code: str):
    # 1. 数据库操作...
    
    # 2. 失效角色权限缓存
    permission_cache.invalidate_role(role_code)
    
    # 3. 级联失效：所有拥有该角色的用户
    subject_ids = self._get_subjects_with_role(role.id)
    permission_cache.invalidate_subjects_batch(subject_ids)
```

### 手动缓存失效

通常不需要手动失效（服务层已自动处理），但以下场景可能需要：

```python
from yweb.permission import permission_cache

# 失效单个用户缓存
permission_cache.invalidate_subject("employee:123")

# 失效角色缓存（角色权限变更时）
permission_cache.invalidate_role("admin")

# 批量失效用户缓存
permission_cache.invalidate_subjects_batch([
    "employee:1", "employee:2", "employee:3"
])

# 失效所有缓存（通过版本号递增）
permission_cache.invalidate_all()

# 清空缓存（立即删除所有数据）
permission_cache.clear()
```

**何时需要手动失效：**

| 场景 | 说明 |
|------|------|
| 通过原生 SQL 修改权限数据 | 绕过服务层，不会自动失效 |
| 从外部系统同步权限数据 | 批量导入后手动 `invalidate_all()` |
| 直接操作数据库修复数据 | 修复后手动失效相关缓存 |

### 缓存统计

```python
# 获取缓存信息
info = permission_cache.get_cache_info()
# {
#     "permission_cache_size": 500,
#     "role_cache_size": 500,
#     "role_permission_cache_size": 50,
#     "maxsize": 10000,
#     "ttl": 300,
#     "version": 1,
#     "stats": {
#         "hits": 12345,
#         "misses": 678,
#         "total_requests": 13023,
#         "hit_rate": "94.80%",
#         "invalidations": 100,
#     }
# }

# 重置统计
permission_cache.reset_stats()
```

### 缓存与通用缓存模块的区别

| 特性 | PermissionCache | yweb.cache |
|------|----------------|------------|
| 定位 | 权限模块专用 | 通用函数缓存 |
| 使用方式 | 手动 get/set | 装饰器自动 |
| 自动失效 | 服务层调用 | ORM 事件监听 |
| 版本号机制 | ✅ 支持 | ❌ 不支持 |
| 多后端 | ❌ 仅内存 | ✅ 内存/Redis |
| 适用场景 | 复杂级联失效 | 简单单点失效 |

权限缓存使用手动模式是因为权限模型复杂（涉及多表级联），简单的 ORM 事件监听难以覆盖所有场景。

---

## API 路由

权限模块提供完整的管理 API，可按需使用。

### 方式1：一次性挂载全部

```python
from yweb.permission import create_permission_router

router = create_permission_router(
    permission_model=Permission,
    role_model=Role,
    subject_role_model=SubjectRole,
    role_permission_model=RolePermission,
    subject_permission_model=SubjectPermission,
    api_resource_model=APIResource,  # 可选
    prefix="/api/permission",
    tags=["权限管理"],
    dependencies=[Depends(require_role("admin"))],  # 保护管理接口
)

app.include_router(router)
```

**生成的端点**：

权限管理使用动词风格路由，只使用 GET 和 POST 请求：

**权限管理 `/permissions`**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/permissions/list` | GET | 获取权限列表 |
| `/permissions/get?code=xxx` | GET | 获取权限详情 |
| `/permissions/create` | POST | 创建权限 |
| `/permissions/update?code=xxx` | POST | 更新权限 |
| `/permissions/delete?code=xxx` | POST | 删除权限 |
| `/permissions/modules/list` | GET | 获取模块列表 |
| `/permissions/resources/list` | GET | 获取资源列表 |

**角色管理 `/roles`**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/roles/list` | GET | 获取角色列表 |
| `/roles/tree` | GET | 获取角色树 |
| `/roles/get?code=xxx` | GET | 获取角色详情 |
| `/roles/create` | POST | 创建角色 |
| `/roles/update?code=xxx` | POST | 更新角色 |
| `/roles/delete?code=xxx` | POST | 删除角色 |
| `/roles/permissions?code=xxx` | GET | 获取角色权限 |
| `/roles/set-permissions?code=xxx` | POST | 设置角色权限（全量） |
| `/roles/add-permission?code=xxx&perm_code=xxx` | POST | 添加角色权限 |
| `/roles/remove-permission?code=xxx&perm_code=xxx` | POST | 移除角色权限 |
| `/roles/subjects?code=xxx` | GET | 获取角色用户 |

**用户授权 `/subjects`**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/subjects/assign-role` | POST | 分配角色 |
| `/subjects/unassign-role?subject_id=xxx&role_code=xxx` | POST | 撤销角色 |
| `/subjects/assign-role-batch` | POST | 批量分配角色 |
| `/subjects/grant-permission` | POST | 授予权限 |
| `/subjects/revoke-permission?subject_id=xxx&permission_code=xxx` | POST | 撤销权限 |
| `/subjects/get?subject_id=xxx` | GET | 获取用户权限 |
| `/subjects/roles?subject_id=xxx` | GET | 获取用户角色 |
| `/subjects/check?subject_id=xxx` | POST | 检查权限 |
| `/subjects/check-batch?subject_id=xxx` | POST | 批量检查权限 |
| `/subjects/invalidate-cache?subject_id=xxx` | POST | 失效用户缓存 |

**API 资源管理 `/api-resources`（如果提供 api_resource_model）**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/api-resources/list` | GET | 获取 API 资源列表 |
| `/api-resources/get?resource_id=xxx` | GET | 获取 API 资源详情 |
| `/api-resources/create` | POST | 创建 API 资源 |
| `/api-resources/update?resource_id=xxx` | POST | 更新 API 资源 |
| `/api-resources/delete?resource_id=xxx` | POST | 删除 API 资源 |
| `/api-resources/scan` | POST | 扫描路由 |
| `/api-resources/modules/list` | GET | 获取模块列表 |
| `/api-resources/batch-set-permission` | POST | 批量设置权限 |

**缓存管理 `/cache`**：

| 端点 | 方法 | 功能 |
|------|------|------|
| `/cache/stats` | GET | 获取缓存统计 |
| `/cache/invalidate` | POST | 失效缓存 |
| `/cache/invalidate-batch` | POST | 批量失效缓存 |
| `/cache/clear` | POST | 清空缓存 |
| `/cache/reset-stats` | POST | 重置统计 |
| `/cache/configure` | POST | 配置缓存 |

### 方式2：按需挂载

```python
from yweb.permission import (
    create_permission_crud_router,
    create_role_crud_router,
    create_subject_router,
)

# 只挂载需要的部分
app.include_router(
    create_permission_crud_router(permission_model=Permission),
    prefix="/api/admin/permissions",
    dependencies=[Depends(require_role("admin"))],
)

app.include_router(
    create_role_crud_router(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    ),
    prefix="/api/admin/roles",
)
```

### 方式3：完全自定义

只使用 Service 类，自己编写 API：

```python
from yweb.permission import PermissionService, RoleService

perm_service = PermissionService(...)
role_service = RoleService(...)

@app.post("/my-api/grant-permission")
async def my_grant_api(data: MySchema):
    # 完全自定义的逻辑
    perm_service.grant_subject_permission(...)
    return {"custom": "response"}
```

---

## 与组织模块集成

### 员工集成权限主体

使用 `EmployeeSubjectMixin` 让员工模型支持权限系统：

```python
from yweb.organization import AbstractEmployee
from yweb.permission.mixins import EmployeeSubjectMixin

class Employee(AbstractEmployee, EmployeeSubjectMixin):
    __tablename__ = "sys_employee"
    __org_tablename__ = "sys_organization"
    __dept_tablename__ = "sys_department"
```

使用：

```python
employee = Employee.get(123)

# 自动拥有 subject_id 属性
subject_id = employee.subject_id
# "employee:123"

# 直接用于权限检查
perm_service.check_permission(employee.subject_id, "user:read")
```

### 双用户体系

同时支持内部员工和外部用户：

```python
# 内部员工（AbstractEmployee + EmployeeSubjectMixin）
employee = Employee.get(123)
perm_service.assign_role(employee.subject_id, "manager")

# 外部用户（AbstractUser + ExternalUserSubjectMixin）
user = User.get(456)
perm_service.assign_role(user.subject_id, "customer")

# 权限检查方式完全一致
perm_service.check_permission("employee:123", "order:read")
perm_service.check_permission("external:456", "order:read")
```

---

## 最佳实践

### 1. 权限编码规范

推荐使用 `resource:action` 格式：

```
user:read        # 查看用户
user:write       # 创建/修改用户
user:delete      # 删除用户
user:*           # 用户所有权限

order:list       # 订单列表
order:detail     # 订单详情
order:create     # 创建订单
order:cancel     # 取消订单

system:config    # 系统配置
admin:*          # 管理员所有权限
```

### 2. 角色设计

```python
# 系统角色（不可删除）
super_admin = role_service.create_role(
    code="super_admin",
    name="超级管理员",
    is_system=True,
)

# 分层角色（利用继承）
admin = role_service.create_role(code="admin", name="管理员")
manager = role_service.create_role(code="manager", parent_code="admin")
operator = role_service.create_role(code="operator", parent_code="manager")

# 功能角色（独立）
auditor = role_service.create_role(code="auditor", name="审计员")
```

### 3. 缓存策略

```python
# 生产环境推荐配置
configure_cache(
    maxsize=10000,    # 根据活跃用户数调整
    ttl=300,          # 5分钟过期，平衡实时性和性能
    enable_stats=True,
)

# 权限变更时主动失效
@app.put("/admin/roles/{code}/permissions")
async def update_role_permissions(code: str, data: PermissionSet):
    role_service.set_role_permissions(code, data.permissions)
    # 自动失效相关用户缓存（服务层已处理）
    return {"message": "success"}
```

### 4. 保护管理接口

```python
# 所有权限管理 API 都应该加权限保护
router = create_permission_router(
    ...,
    dependencies=[Depends(require_role("admin"))],
)

# 或者更细粒度
@app.delete("/admin/roles/{code}")
async def delete_role(
    code: str,
    user = Depends(require_permission("role:delete"))
):
    ...
```

### 5. 审计追踪

启用 `enable_history = True` 记录所有变更：

```python
class Permission(AbstractPermission):
    __tablename__ = "sys_permission"
    enable_history = True  # 自动记录变更历史

class Role(AbstractRole):
    __tablename__ = "sys_role"
    enable_history = True
```

配合 `yweb.orm.history` 模块查询历史：

```python
from yweb.orm.history import get_model_history

# 查看权限变更历史
history = get_model_history(Permission, permission_id)
```

### 6. 路由前缀约定

为避免底层模块提供的管理 API 与业务 API 冲突，推荐使用统一的前缀约定：

| 前缀 | 用途 | 示例 |
|------|------|------|
| `/api/_sys/` | 系统级别管理 API（底层模块提供） | `/api/_sys/permission` |
| `/api/admin/` | 业务管理后台 API | `/api/admin/users` |
| `/api/v1/` | 业务 API | `/api/v1/orders` |

**推荐的挂载方式：**

```python
from yweb.permission import create_permission_router

# 系统管理 API 使用 _sys 前缀
router = create_permission_router(
    permission_model=Permission,
    role_model=Role,
    subject_role_model=SubjectRole,
    role_permission_model=RolePermission,
    subject_permission_model=SubjectPermission,
    prefix="/api/_sys/permission",  # 系统管理 API
    dependencies=[Depends(require_role("super_admin"))],
)

app.include_router(router)
```

### 7. 细粒度权限控制

如果需要对不同管理接口设置不同权限，可以分开挂载子路由：

**预定义系统管理权限：**

```python
# 初始化时创建系统权限
SYS_PERMISSIONS = [
    # 权限管理
    {"code": "sys:permission:read", "name": "查看权限", "module": "sys"},
    {"code": "sys:permission:write", "name": "管理权限", "module": "sys"},
    # 角色管理
    {"code": "sys:role:read", "name": "查看角色", "module": "sys"},
    {"code": "sys:role:write", "name": "管理角色", "module": "sys"},
    # 用户授权
    {"code": "sys:subject:read", "name": "查看用户权限", "module": "sys"},
    {"code": "sys:subject:write", "name": "管理用户权限", "module": "sys"},
    # 缓存管理
    {"code": "sys:cache:manage", "name": "管理缓存", "module": "sys"},
]

# 启动时初始化
@app.on_event("startup")
async def init_sys_permissions():
    for perm_data in SYS_PERMISSIONS:
        existing = Permission.query.filter_by(code=perm_data["code"]).first()
        if not existing:
            Permission(**perm_data).save()
```

**分开挂载，设置不同权限：**

```python
from yweb.permission import (
    create_permission_crud_router,
    create_role_crud_router,
    create_subject_router,
    create_cache_router,
    require_permission,
)

# 权限管理 - 需要 sys:permission:write
app.include_router(
    create_permission_crud_router(permission_model=Permission),
    prefix="/api/_sys/permissions",
    tags=["系统管理 - 权限"],
    dependencies=[Depends(require_permission("sys:permission:write"))],
)

# 角色管理 - 需要 sys:role:write
app.include_router(
    create_role_crud_router(
        role_model=Role,
        permission_model=Permission,
        role_permission_model=RolePermission,
        subject_role_model=SubjectRole,
    ),
    prefix="/api/_sys/roles",
    tags=["系统管理 - 角色"],
    dependencies=[Depends(require_permission("sys:role:write"))],
)

# 用户授权 - 需要 sys:subject:write
app.include_router(
    create_subject_router(
        permission_model=Permission,
        role_model=Role,
        subject_role_model=SubjectRole,
        role_permission_model=RolePermission,
        subject_permission_model=SubjectPermission,
    ),
    prefix="/api/_sys/subjects",
    tags=["系统管理 - 用户授权"],
    dependencies=[Depends(require_permission("sys:subject:write"))],
)

# 缓存管理 - 需要 sys:cache:manage
app.include_router(
    create_cache_router(),
    prefix="/api/_sys/cache",
    tags=["系统管理 - 缓存"],
    dependencies=[Depends(require_permission("sys:cache:manage"))],
)
```

### 8. API 资源与权限绑定

利用 API 资源自动扫描功能，实现接口级别的权限控制：

**步骤 1：挂载 API 资源管理路由**

```python
from yweb.permission import create_api_resource_router

app.include_router(
    create_api_resource_router(
        api_resource_model=APIResource,
        permission_model=Permission,
    ),
    prefix="/api/_sys/api-resources",
    dependencies=[Depends(require_role("super_admin"))],
)
```

**步骤 2：扫描并注册所有 API 路由**

```bash
# 调用扫描接口
POST /api/_sys/api-resources/scan
```

这会自动将应用中的所有路由注册为 API 资源。

**步骤 3：为 API 资源绑定权限**

```bash
# 查看未配置权限的 API 资源
GET /api/_sys/api-resources/list?has_permission=false

# 为单个 API 设置权限
POST /api/_sys/api-resources/update?resource_id=123
Body: {"permission_code": "user:read"}

# 批量设置权限
POST /api/_sys/api-resources/batch-set-permission
Body: {"resource_ids": [1, 2, 3], "permission_code": "user:write"}
```

**步骤 4：实现基于 API 资源的动态权限检查（可选）**

```python
from fastapi import Request

async def dynamic_permission_check(request: Request):
    """根据 API 资源配置动态检查权限"""
    path = request.url.path
    method = request.method
    
    # 查询 API 资源
    resource = APIResource.query.filter_by(
        path=path, method=method, is_active=True
    ).first()
    
    if not resource:
        return  # 未注册的 API 不检查
    
    if resource.is_public:
        return  # 公开 API 不检查
    
    if resource.permission_id:
        # 获取当前用户并检查权限
        user = await get_current_user(request)
        perm = Permission.get(resource.permission_id)
        if not perm_service.check_permission(user.subject_id, perm.code):
            raise HTTPException(status_code=403, detail="权限不足")

# 作为全局中间件或依赖使用
app.middleware("http")(dynamic_permission_check)
```

---

## 异常处理

权限模块提供以下异常类：

| 异常类 | HTTP状态码 | 说明 |
|--------|-----------|------|
| `PermissionDeniedException` | 403 | 权限不足 |
| `RoleNotFoundException` | 404 | 角色不存在 |
| `PermissionNotFoundException` | 404 | 权限不存在 |
| `DuplicateRoleException` | 409 | 角色已存在 |
| `DuplicatePermissionException` | 409 | 权限已存在 |
| `RoleInheritanceCycleException` | 400 | 角色继承循环 |
| `SystemRoleModifyException` | 403 | 系统角色不可修改 |

```python
from yweb.permission import PermissionDeniedException

try:
    perm_service.check_permission(
        "employee:123",
        "admin:config",
        raise_exception=True
    )
except PermissionDeniedException as e:
    print(f"权限不足: {e.permission_code}")
    print(f"用户: {e.subject_id}")
```

---

## API 参考

详细 API 文档请参考源代码注释或使用 FastAPI 自动生成的 OpenAPI 文档。

```python
# 启动应用后访问
# http://localhost:8000/docs
```
