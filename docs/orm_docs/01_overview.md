# 01. 概述与快速开始

## 概述

YWeb ORM 是一个基于 SQLAlchemy 2.0 构建的 ORM 扩展模块，提供了丰富的企业级功能，包括：

- **BaseModel 基类**：提供完整的 CRUD 操作、分页查询、批量操作
- **软删除机制**：自动过滤已删除记录，支持级联软删除
- **版本控制**：基于 ver 字段的乐观锁机制
- **历史记录**：可选的 sqlalchemy-history 集成
- **会话管理**：请求作用域的 session 管理，完美支持 FastAPI

## 架构设计

```
┌─────────────────────────────────────────────────────────────┐
│                      应用层 (FastAPI)                        │
├─────────────────────────────────────────────────────────────┤
│                      Service 层                              │
├─────────────────────────────────────────────────────────────┤
│                      YWeb ORM                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  BaseModel  │  │ SoftDelete  │  │  CascadeSoftDelete  │  │
│  │  CoreModel  │  │  Extension  │  │      Manager        │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────┐  │
│  │  DBSession  │  │   History   │  │    DTO/Schemas      │  │
│  │  Manager    │  │   Module    │  │                     │  │
│  └─────────────┘  └─────────────┘  └─────────────────────┘  │
├─────────────────────────────────────────────────────────────┤
│                    SQLAlchemy 2.0                            │
├─────────────────────────────────────────────────────────────┤
│                      数据库                                   │
└─────────────────────────────────────────────────────────────┘
```

## 核心类关系

```
DeclarativeBase
      │
      ▼
  CoreModel ─────────────────────────────────────────┐
      │                                               │
      │  提供：                                        │
      │  - query 类属性                               │
      │  - add/update/delete/save 方法                │
      │  - get/get_all/get_list_by_conditions 方法   │
      │  - 批量操作方法                               │
      │  - 分页方法                                   │
      │                                               │
      ▼                                               │
  BaseModel ◄─────────────────────────────────────────┘
      │
      │  继承 CoreModel，添加：
      │  - id, name, code, note, caption 字段
      │  - created_at, updated_at, deleted_at 字段
      │  - ver 字段（乐观锁）
      │  - SimpleSoftDeleteMixin
      │
      ▼
  YourModel（用户定义的模型）
```

## 快速开始

### 1. 初始化数据库

```python
from yweb.orm import init_database, get_engine

# 初始化数据库连接
engine, session_scope = init_database(
    database_url="sqlite:///./app.db",
    echo=False,           # 是否打印SQL
    pool_size=5,          # 连接池大小
    max_overflow=10       # 最大溢出连接数
)

# 或者简单方式
init_database("sqlite:///./app.db")
```

### 2. 定义模型

```python
from yweb.orm import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String, Integer, Boolean

class User(BaseModel):
    __tablename__ = "user"  # 可选，不指定则自动生成

    # 自定义字段
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100))
    age: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # BaseModel 已提供的字段：
    # id: int          - 主键
    # name: str        - 名称
    # code: str        - 编码
    # note: str        - 备注
    # caption: str     - 介绍
    # created_at       - 创建时间
    # updated_at       - 更新时间
    # deleted_at       - 软删除时间
    # ver: int         - 版本号（乐观锁）
```

### 3. 创建表

```python
from yweb.orm import BaseModel, get_engine

# 创建所有表
BaseModel.metadata.create_all(bind=get_engine())
```

### 4. 基本 CRUD 操作

```python
# 创建
user = User(username="tom", email="tom@example.com")
user.save(True)  # True 表示立即提交

# 查询
user = User.get(1)                    # 根据ID获取
users = User.get_all()                # 获取所有
users = User.get_list_by_conditions(  # 条件查询
    {"is_active": True}
)

# 更新
user.email = "new@example.com"
user.save(True)

# 删除（软删除）
user.delete(True)
```

### 5. 分页查询

```python
# Query 对象分页
page_result = User.query.filter(
    User.is_active == True
).order_by(User.created_at.desc()).paginate(
    page=1,
    page_size=10
)

# 访问分页结果
print(f"总记录数: {page_result.total_records}")
print(f"总页数: {page_result.total_pages}")
print(f"当前页数据: {page_result.rows}")
print(f"是否有下一页: {page_result.has_next}")
```

### 6. FastAPI 集成

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from yweb.orm import init_database, get_db, BaseModel, get_engine
from yweb import OK, NotFound

app = FastAPI()

@app.on_event("startup")
def startup():
    init_database("sqlite:///./app.db")
    BaseModel.metadata.create_all(bind=get_engine())

@app.get("/users")
def list_users(page: int = 1, page_size: int = 10):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    return OK(user)

@app.post("/users")
def create_user(data: dict, db: Session = Depends(get_db)):
    user = User(**data)
    user.save(True)
    return OK(user, "创建成功")

@app.delete("/users/{user_id}")
def delete_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    user.delete(True)  # 软删除
    return OK(None, "删除成功")
```

## 配置选项

### 数据库连接配置

```python
init_database(
    database_url="postgresql://user:pass@localhost/db",
    echo=False,           # SQL日志
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出
    pool_timeout=30,      # 连接超时
    pool_recycle=1800,    # 连接回收时间
)
```

### 软删除配置

```python
from yweb.orm import activate_soft_delete_hook, IgnoredTable

# 激活软删除钩子
activate_soft_delete_hook(
    deleted_field_name="deleted_at",           # 软删除字段名
    disable_soft_delete_option_name="include_deleted",  # 禁用选项名
    ignored_tables=[                           # 忽略的表
        IgnoredTable(name='audit_log'),
    ]
)
```

### 级联软删除配置

```python
from yweb.orm import configure_cascade_soft_delete

# 配置级联软删除
configure_cascade_soft_delete(
    deleted_field_name="deleted_at"
)
```

## 下一步

- [02_模型定义](02_model_definition.md) - 详细了解模型定义
- [03_CRUD操作](03_crud_operations.md) - 深入学习CRUD操作
- [05_分页查询](05_pagination.md) - 掌握分页功能
