# 模型注册最佳实践

## 问题背景

一个基于 yweb 框架的项目通常有 **多个入口点** 需要感知全部数据库模型：

| 入口 | 用途 | 是否有 FastAPI app |
|------|------|--------------------|
| `main.py` | 应用启动，挂载路由 | 有 |
| `init_db.py` | 初始化建表 + 种子数据 | 无 |
| `alembic/env.py` | 数据库迁移 | 无 |

SQLAlchemy 的 `BaseModel.metadata.create_all()` 和 Alembic 的 `autogenerate` **只能看到已经导入（注册）到 metadata 的模型**。如果某个入口遗漏了导入，对应的表就不会被创建或迁移。

### 项目中的三类模型

| 类型 | 特征 | 示例 |
|------|------|------|
| **静态实体** | 定义在 `entities.py` 或 `model/*.py` 中的普通 class | `User`、`Application`、`Permission`、`SSORole` |
| **动态模型（认证）** | 由 `setup_auth(role_model=True)` 在运行时创建 | `Role`、`user_role` 关联表 |
| **动态模型（组织架构）** | 由 `create_org_models()` / `setup_organization()` 在运行时创建 | `Organization`、`Department`、`Employee` 等 |

动态模型在代码中没有静态的 class 定义，无法通过简单的文件扫描发现。这就是问题的根源。

---

## 推荐方案：统一模型注册中心

在项目中创建 `app/models_registry.py`，**将全部模型的导入/创建集中到一个文件**，所有入口点共享同一份定义。

### 文件结构

```
app/
├── models_registry.py   # <-- 统一模型注册中心
├── main.py
├── domain/
│   ├── auth/model/user.py
│   ├── auth/model/login_record.py
│   ├── application/entities.py
│   ├── permission/entities.py
│   └── sso_role/entities.py
```

### models_registry.py 模板

```python
"""统一模型注册中心

所有入口点（main.py / init_db.py / alembic/env.py）通过此模块注册模型，
确保 BaseModel.metadata 中包含全部表定义。
"""

# ======================== 1. 静态模型（导入即注册） ========================

from app.domain.auth.model.user import User                          # noqa: F401
from app.domain.auth.model.login_record import LoginRecord           # noqa: F401
from app.domain.application.entities import Application              # noqa: F401
from app.domain.permission.entities import Permission, RolePermission  # noqa: F401
# ... 其他实体 ...


# ======================== 2. 共享配置 ========================

from yweb.orm import fields

class EmployeeUserMixin:
    """员工关联用户账号 — 各入口共享此定义"""
    user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)


# ======================== 3. 动态模型（按需创建） ========================

_cached_registry = None

def ensure_dynamic_models():
    """确保动态模型已注册到 metadata（幂等，多次调用返回缓存结果）

    仅用于 init_db.py / alembic/env.py 等不经过 main.py 的场景。
    main.py 通过 setup_auth() / setup_organization() 自行创建，不调用此函数。
    """
    global _cached_registry
    if _cached_registry is not None:
        return _cached_registry

    from yweb.auth import setup_auth
    auth = setup_auth(user_model=User, role_model=True)

    from yweb.organization import create_org_models
    org = create_org_models(employee_mixin=EmployeeUserMixin)

    _cached_registry = (auth, org)
    return _cached_registry
```

### 各入口的使用方式

#### main.py — 有 FastAPI app

`main.py` 需要路由挂载，使用 `setup_auth(app=app)` 和 `setup_organization(app=app)`。
从 `models_registry` 导入静态模型和共享配置，**不调用** `ensure_dynamic_models()`：

```python
from app.models_registry import User, LoginRecord, EmployeeUserMixin
from yweb.auth import setup_auth
from yweb.organization import setup_organization

# setup_auth 内部会创建 Role + user_role
auth = setup_auth(app=app, user_model=User, role_model=True, ...)

# setup_organization 内部会创建组织架构模型
org = setup_organization(app=app, employee_mixin=EmployeeUserMixin, ...)
```

#### init_db.py — 无 app，只需建表

```python
from app.models_registry import User, ensure_dynamic_models

registry = ensure_dynamic_models()
Role = registry.role_model

from yweb.orm import BaseModel
from app.database import get_engine

BaseModel.metadata.create_all(bind=get_engine())
```

#### alembic/env.py — 无 app，只需 metadata

```python
from yweb.orm import BaseModel
from app.models_registry import ensure_dynamic_models

ensure_dynamic_models()

target_metadata = BaseModel.metadata
```

---

## 设计要点

### 为什么不用文件扫描（auto_import_entities）？

一种常见做法是扫描 `app/domain/**/entities.py` 自动导入。存在以下隐患：

1. **命名约定盲区** — 放在 `model/` 目录而非 `entities.py` 的模型会被遗漏（如 `LoginRecord`）
2. **无法发现动态模型** — `Role`、组织架构表没有静态文件可扫描
3. **隐式依赖** — 开发者不清楚哪些模型被注册了，出问题难排查

显式导入虽然多几行代码，但 **可读、可控、不会遗漏**。

### 为什么 EmployeeUserMixin 要定义在共享模块？

`EmployeeUserMixin` 决定了 `Employee` 表的额外字段（如关联 `User`）。如果在 `main.py` 和 `init_db.py` 中各写一份，当一边改了另一边忘改，两个入口看到的表结构就会不一致。

定义在 `models_registry.py` 中，**单一事实来源**，所有入口引用同一份。

### ensure_dynamic_models 的幂等设计

`ensure_dynamic_models()` 使用模块级缓存 `_cached_registry`，多次调用返回同一结果，不会重复创建模型类。这在测试场景中尤其重要。

---

## 新增模型的检查清单

当项目新增一个 ORM 模型时：

- [ ] 在 `app/domain/xxx/entities.py` 或 `model/xxx.py` 中定义模型类
- [ ] 在 `app/models_registry.py` 中添加对应的 `import`
- [ ] 如果是动态模型（工厂函数创建的），在 `ensure_dynamic_models()` 中添加创建逻辑
- [ ] 运行 `alembic revision --autogenerate` 验证迁移脚本是否检测到新表
- [ ] 运行 `init_db.py` 验证建表是否完整

---

## 框架侧说明

yweb 框架提供了两层 API 来支持这种模式：

| API | 功能 | 适用场景 |
|-----|------|----------|
| `setup_auth(app=app, ...)` | 创建模型 + 挂载路由 | main.py |
| `setup_auth(user_model=..., role_model=True)` | 仅创建模型，不挂载路由 | init_db / alembic |
| `setup_organization(app=app, ...)` | 创建模型 + 挂载路由 | main.py |
| `create_org_models(...)` | 仅创建模型，不挂载路由 | init_db / alembic |

不传 `app` 参数（或使用 `create_org_models`）时，框架只做模型注册，不产生任何路由副作用。这使得在脚本环境中安全地使用成为可能。
