# ORM 使用指南

## 目录

1. [快速开始](#1-快速开始)
2. [数据库初始化](#2-数据库初始化)
3. [模型定义](#3-模型定义)
4. [Session 管理](#4-session-管理)
5. [CRUD 操作](#5-crud-操作)
6. [分页查询](#6-分页查询)
7. [软删除](#7-软删除)
8. [历史记录](#8-历史记录)
9. [线程池安全使用](#9-线程池安全使用)
10. [最佳实践](#10-最佳实践)

---

## 1. 快速开始

```python
from yweb.orm import BaseModel, init_database, get_engine, Base
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

# 1. 一行初始化（自动设置 CoreModel.query）
# 返回值可选：如果需要手动管理 engine 和 session_scope，可以接收返回值
init_database("sqlite:///./app.db")
# 或者：engine, session_scope = init_database("sqlite:///./app.db")

# 2. 定义模型（继承 BaseModel 自动获得 id/name/code/时间戳/软删除等字段）
class User(BaseModel):
    # __tablename__ 自动生成为 "user"（类名驼峰转下划线）
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100))

# 3. 创建表
Base.metadata.create_all(get_engine())

# 4. 直接使用 CRUD
user = User(name="张三", username="zhangsan", email="zhang@example.com")
user.save(commit=True)

user = User.get(1)                              # 根据ID查询
user = User.get_by_name("张三")                  # 根据名称查询
users = User.query.filter_by(is_active=True).all()  # 条件查询
```

> **说明**：
> - `init_database()` 返回 `(engine, session_scope)` 元组，可选择性接收
> - 如果不需要手动管理 engine 和 session_scope，可以不接收返回值
> - 函数会自动执行 `CoreModel.query = session_scope.query_property()`，使得 `User.get()`、`User.query.filter()` 等方法开箱即用

---

## 2. 数据库初始化

### 2.1 使用配置对象（推荐）

```python
from pydantic_settings import BaseSettings

class DatabaseSettings(BaseSettings):
    url: str = "postgresql://user:pass@localhost/dbname"
    echo: bool = False
    pool_size: int = 5
    max_overflow: int = 10

class Settings(BaseSettings):
    database: DatabaseSettings = DatabaseSettings()

settings = Settings()

# 使用配置对象初始化
engine, session_scope = init_database(config=settings.database)
```

### 2.2 手工指定数据库参数

```python
from yweb.orm import init_database

engine, session_scope = init_database(
    database_url="sqlite:///./app.db",  # 数据库连接 URL
    echo=False,              # 是否打印 SQL（调试用）
    pool_size=5,             # 连接池大小
    max_overflow=10,         # 最大溢出连接数（总连接 = pool_size + max_overflow）
    pool_timeout=30,         # 获取连接超时（秒）
    pool_recycle=3600,       # 连接回收时间（秒），防止连接过期
    pool_pre_ping=True,      # 使用前 ping 检测连接是否有效
    auto_setup_query=True,   # 自动设置 CoreModel.query（默认 True）
)
```

| 参数 | 默认值 | 说明 |
|-----|-------|------|
| `database_url` | 必填 | 数据库连接 URL |
| `pool_size` | 5 | 连接池常驻连接数 |
| `max_overflow` | 10 | 超出 pool_size 后可创建的额外连接数 |
| `pool_timeout` | 30 | 等待可用连接的超时时间（秒） |
| `pool_recycle` | 3600 | 连接最大存活时间（秒） |
| `auto_setup_query` | True | 自动设置 `CoreModel.query` 属性 |

### 2.3 在 FastAPI 中初始化

```python
from fastapi import FastAPI
from yweb.orm import init_database, Base, get_engine
from yweb.middleware import RequestIDMiddleware

app = FastAPI()

# 添加请求ID中间件（推荐）
# 作用：1. 请求结束时自动清理 session  2. 添加 X-Request-ID 响应头
app.add_middleware(RequestIDMiddleware)

@app.on_event("startup")
def startup():
    init_database(config=settings.database)
    Base.metadata.create_all(get_engine())
```

> **RequestIDMiddleware 是否必须？**
> 
> | 使用方式 | 是否需要 | 原因 |
> |---------|---------|------|
> | 直接使用 `User.get()`、`User.query.filter()` | **必须** | 无自动清理，session 会堆积 |
> | 使用 `Depends(get_db)` | 可选 | `get_db()` 内部会自动清理 |
> | 使用 `db_session_scope()` | 可选 | 上下文管理器会自动清理 |
> | 使用 `@with_db_session()` | 可选 | 装饰器会自动清理 |
> 
> **建议始终添加**：实际项目通常混合使用多种方式，且中间件还提供 `X-Request-ID` 响应头便于日志追踪。

<details>
<summary><b>Session 堆积的技术原理</b>（点击展开）</summary>

**核心机制**：`scoped_session` 使用 `request_id` 作为 key 存储 session

```python
# scoped_session 内部结构（简化）
registry = {
    "abc123": Session1,  # 请求1 的 session
    "def456": Session2,  # 请求2 的 session
    "ghi789": Session3,  # 请求3 的 session
    # ... 不断累积
}
```

**有自动清理的情况**：

```python
# db_session_scope / @with_db_session / get_db 都会在 finally 中调用 on_request_end()
with db_session_scope() as session:
    user = User.get(1)
# finally 自动调用 on_request_end() → registry.pop("abc123") → session 被移除
```

**无自动清理的情况**：

```python
@app.get("/users/{id}")
def get_user(id: int):
    user = User.get(id)  # 自动生成 request_id，创建 session 存入 registry
    return user
# 请求结束，但没有任何代码调用 on_request_end()
# registry 中的 session 永远不会被移除 → 内存泄漏
```

**RequestIDMiddleware 的作用**：

```python
class RequestIDMiddleware:
    async def __call__(self, scope, receive, send):
        try:
            await self.app(scope, receive, send)
        finally:
            on_request_end()  # 请求结束时清理 session
```

</details>

### 2.4 SQLite 连接池行为

| 数据库类型 | 连接池类型 | pool_size/max_overflow |
|-----------|-----------|------------------------|
| `sqlite:///:memory:` | StaticPool（单连接） | 不适用 |
| `sqlite:///file.db` | QueuePool（多连接） | 支持配置 |
| PostgreSQL/MySQL | QueuePool | 支持配置 |

---

## 3. 模型定义

### 3.1 模型层级结构

```
Base (SQLAlchemy declarative_base)
  └── IdModel (动态主键)
        └── CoreModel (CRUD、分页、序列化、历史记录)
              └── BaseModel (软删除 + name/code/note/caption 字段)
```

#### CoreModel vs BaseModel

**CoreModel**：
- 提供核心 CRUD 方法（`get()`, `save()`, `update()`, `delete()` 等）
- 提供分页查询功能（`paginate()`）
- 提供序列化方法（`to_dict()`, `to_json()`）
- 提供历史记录功能（可选启用）
- **不包含**软删除功能
- **不包含**通用业务字段（name/code/note/caption）
- 适用于不需要软删除的场景（如日志表、统计表）

**BaseModel**：
- 继承 CoreModel 的所有功能
- **额外提供**软删除功能（`soft_delete()`, `undelete()` 等）
- **额外提供**通用业务字段：
  - `name`：名称字段（String(100)）
  - `code`：编码字段（String(50)，唯一索引）
  - `note`：备注字段（Text）
  - `caption`：标题字段（String(200)）
- **额外提供**便捷查询方法：`get_by_name()`, `get_by_code()`
- 适用于大多数业务表（如用户表、订单表、商品表）

**选择建议**：
- 业务表（需要软删除和通用字段）→ 使用 `BaseModel`
- 日志表、统计表（不需要软删除）→ 使用 `CoreModel`
- 关联表、中间表（简单结构）→ 使用 `CoreModel`

### 3.2 自动表名规则

表名会**自动根据类名生成**（驼峰转下划线），无需手动设置 `__tablename__`：

| 类名 | 自动生成的表名 |
|-----|--------------|
| `User` | `user` |
| `OrderItem` | `order_item` |
| `LoginRecord` | `login_record` |

如需自定义表名，可手动指定：
```python
class User(BaseModel):
    __tablename__ = "sys_users"  # 自定义表名
```

### 3.3 主键策略配置

ORM 支持多种主键生成策略，可全局配置或按模型覆盖。

#### 支持的主键类型

| 类型 | 枚举值 | 数据库类型 | 说明 |
|------|--------|-----------|------|
| 自增ID | `IdType.AUTO_INCREMENT` | `Integer` | 默认，数据库自增 |
| 雪花ID | `IdType.SNOWFLAKE` | `BigInteger` | 64位整数，趋势递增，分布式唯一 |
| UUID | `IdType.UUID` | `String(36)` | 完整UUID（36位） |
| 短UUID | `IdType.SHORT_UUID` | `String(n)` | 可配置长度（8-32位），默认10位 |
| 自定义 | `IdType.CUSTOM` | `String(64)` | 使用自定义生成器 |

> **主键生成时机**：所有主键都在 `flush` 时生成 —— 自增主键由数据库生成，非自增主键在 `before_insert` 事件中生成。访问 `id` 属性时会自动触发 flush。

> ⚠️ **手动指定主键注意事项**：
>
> 如果手动指定 `model.id = "xxx"`，访问 id 时**不会触发自动 flush**（因为 id 不是 None），
> 且 `generate_with_retry` 冲突重试机制**不会生效**。主键冲突将延迟到 commit 时才被检测到。
> 详见 [模型定义 - 手动指定主键的注意事项](./orm_docs/02_model_definition.md#手动指定主键的注意事项)。

#### 全局配置

```python
from yweb.orm import configure_primary_key, IdType

# 配置短UUID（推荐）
configure_primary_key(
    strategy=IdType.SHORT_UUID,
    short_uuid_length=10,      # 长度（8-32位）
    max_retries=5              # 冲突重试次数（generate_with_retry 机制）
)

# 配置雪花ID（分布式场景）
configure_primary_key(
    strategy=IdType.SNOWFLAKE,
    snowflake_worker_id=1,     # 工作节点ID（0-31）
    snowflake_datacenter_id=1  # 数据中心ID（0-31）
)

# 配置自定义生成器
import uuid

def my_id_generator():
    return f"ORD-{uuid.uuid4().hex[:8]}"

configure_primary_key(
    strategy=IdType.CUSTOM,
    custom_generator=my_id_generator
)
```

#### 模型级别覆盖

```python
from yweb.orm import BaseModel, IdType, configure_primary_key
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

# 全局使用自增ID 可以不配置
# configure_primary_key(strategy=IdType.AUTO_INCREMENT)

# 订单模型使用短UUID
class Order(BaseModel):
    id_type = IdType.SHORT_UUID  # 覆盖全局配置
    order_no: Mapped[str] = mapped_column(String(50))

# 日志模型使用自增ID（继承全局配置）
class LogRecord(BaseModel):
    message: Mapped[str] = mapped_column(String(1000))
```

#### 主键影响范围

主键策略会影响以下功能：

| 影响范围 | 说明 |
|---------|------|
| **历史记录表** | `Transaction` 表（全局唯一，记录事务元数据）的主键类型与配置一致，可通过 `init_versioning(transaction_cls=MyTransaction)` 自定义表名和字段 |
| **版本表** | `*_version` 表的主键类型与主模型一致（后缀可通过 `init_versioning(options={'table_name': '%s_history'})` 自定义） |
| **外键关联** | 外键字段类型需与主键类型匹配 |
| **查询性能** | 整数主键通常比字符串主键性能更好 |

#### 配置顺序（重要）

> ⚠️ **配置顺序非常重要**：必须在 `init_versioning()` 之前调用 `configure_primary_key()`，
> 否则 `Transaction` 表会使用默认的整数主键。

```python
from yweb.orm import configure_primary_key, init_versioning, IdType

# ✅ 正确顺序
configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=10)
init_versioning()  # Transaction 表使用短UUID

# ❌ 错误顺序
# init_versioning()  # Transaction 表已使用默认整数主键
# configure_primary_key(strategy=IdType.SHORT_UUID)  # 太晚了！
```

### 3.4 使用 BaseModel（推荐）

```python
from yweb.orm import BaseModel
from sqlalchemy import String, Integer, Boolean
from sqlalchemy.orm import Mapped, mapped_column

class User(BaseModel):
    """用户模型（表名自动生成为 "user"）
    
    自动继承字段：
    - id: 主键
    - name: 名称
    - code: 编码
    - note: 备注
    - caption: 介绍
    - created_at: 创建时间
    - updated_at: 更新时间
    - deleted_at: 删除时间（软删除标记）
    - ver: 版本号（乐观锁）
    """
    username: Mapped[str] = mapped_column(String(50), unique=True)
    email: Mapped[str] = mapped_column(String(100), nullable=True)
    age: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

### 3.5 使用 CoreModel（不需要软删除时）

```python
from yweb.orm import CoreModel
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class LogRecord(CoreModel):
    """日志记录（表名自动生成为 "log_record"）"""
    level: Mapped[str] = mapped_column(String(20))
    message: Mapped[str] = mapped_column(String(1000))
```

### 3.6 启用历史记录

```python
from yweb.orm import BaseModel, init_versioning

# 在定义模型之前初始化版本化
init_versioning()

class Document(BaseModel):
    """文档模型（表名自动生成为 "document"）"""
    enable_history = True  # 启用历史记录
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(10000))
```

### 3.7 外键关联

使用 `fields.*` API 可以用 Django 风格简化外键定义，一行代码自动创建外键列 + relationship + backref。

#### 关系示意图

```
┌─────────────────┐              ┌─────────────────┐
│  Order (父表)   │  1       N   │ OrderItem (子表)│
│─────────────────│◄─────────────│─────────────────│
│ id (PK)         │              │ id (PK)         │
│ order_no        │              │ order_id (FK) ←─┼── fields.ManyToOne 自动创建
│                 │              │ order      ←────┼── relationship 自动创建
│ order_items ────┼──────────────┤ product_name    │
│   (backref)     │              │ quantity        │
└─────────────────┘              └─────────────────┘
      父表                              子表
    （被引用）                      （包含外键）
```

**fields.ManyToOne(Order, ...) 的含义：**
- `Order` 是**父表**（被引用的表，主键所在）
- `OrderItem` 是**子表**（包含外键的表）
- 外键 `order_id` 存在于子表 `OrderItem` 中，指向父表 `Order.id`

#### 基本用法

```python
from yweb.orm import BaseModel, fields

class Order(BaseModel):
    order_no: Mapped[str] = mapped_column(String(50))
    # order_items 属性由 backref 自动创建（复数）

class OrderItem(BaseModel):
    # 多对一关系
    order = fields.ManyToOne(Order, on_delete=fields.DELETE)
    # 自动创建：order_id 列 + order relationship + Order.order_items backref（复数）
    
    product_name: Mapped[str] = mapped_column(String(100))
    quantity: Mapped[int] = mapped_column(Integer)

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    # user_profile 属性由 backref 自动创建（单数）

class UserProfile(BaseModel):
    # 一对一关系
    user = fields.OneToOne(User, on_delete=fields.DO_NOTHING)
    # 自动创建：user_id 列 + user relationship + User.user_profile backref（单数）
    
    bio: Mapped[str] = mapped_column(String(500))
```

#### fields.* 参数说明

| 参数 | 类型 | 说明 |
|------|------|------|
| `target_model` | class | 父表模型类（必须是类引用，不能是字符串） |
| `on_delete` | 常量 | 父表软删除时的级联行为（见下表） |
| `nullable` | bool | 外键是否可为空，默认 `True` |
| `backref` | 多种 | `True`（默认自动生成）、`"name"`（自定义）、`False`（不创建） |

#### on_delete 级联类型

| 常量 | 说明 | 适用场景 |
|------|------|----------|
| `fields.DELETE` | 父表删除时，子表也软删除 | 订单→订单项（强聚合） |
| `fields.SET_NULL` | 父表删除时，子表外键设为 NULL | 部门→员工（可调岗） |
| `fields.PROTECT` | 有子记录时禁止删除父表 | 分类→商品（保护数据） |
| `fields.UNLINK` | 解除多对多关联 | 用户→角色（多对多） |
| `fields.DO_NOTHING` | 不做任何处理 | 日志等弱关联 |

#### 完整示例：员工关联用户

```python
from yweb.orm import BaseModel, fields

class User(BaseModel):
    username: Mapped[str] = mapped_column(String(50))
    # employee 属性由 fields.ManyToOne 的 backref 自动创建

class Employee(BaseModel):
    name: Mapped[str] = mapped_column(String(100))
    
    # 员工关联用户账号
    user = fields.ManyToOne(
        User,                       # 父表模型
        on_delete=fields.DO_NOTHING,  # 员工删除时不影响用户
        nullable=True,              # 允许员工不关联用户
        backref="employee",         # 在 User 上创建 user.employee 反向引用
    )

# 使用
emp = Employee(name="张三")
emp.user = some_user           # 通过 relationship 设置
emp.user_id = user.id          # 也可以直接设置外键值

# 反向访问
user.employee                  # 获取关联的员工
```

> **详细说明**：参见 [08_cascade_soft_delete.md](orm_docs/08_cascade_soft_delete.md)

---

## 4. Session 管理

### 4.1 核心概念

yweb ORM 使用 `scoped_session` + `request_id` 实现 session 隔离：
- **相同的 request_id** → 返回同一个 session
- **不同的 request_id** → 返回不同的 session

### 4.2 HTTP 请求场景（FastAPI）

**方式1：使用 RequestIDMiddleware（推荐）**

```python
from fastapi import FastAPI
from yweb.middleware import RequestIDMiddleware

app = FastAPI()
app.add_middleware(RequestIDMiddleware)

@app.get("/users/{user_id}")
def get_user(user_id: int):
    # 直接使用模型方法，session 由中间件自动管理
    user = User.get(user_id)
    return user.to_dict()

@app.post("/users")
def create_user(name: str, email: str):
    user = User(name=name, email=email)
    user.save(commit=True)
    return {"id": user.id}
```

**方式2：使用 get_db() 依赖**

```python
from fastapi import Depends
from yweb.orm import get_db

@app.post("/users")
def create_user(name: str, db=Depends(get_db)):
    user = User(name=name)
    user.save()
    # get_db 会自动提交和清理
    return {"id": user.id}
```

### 4.3 非 HTTP 场景

**方式1：db_session_scope() 上下文管理器（推荐）**

```python
from yweb.orm import db_session_scope

# 脚本/定时任务/后台任务
def daily_report():
    # request_id 不传则自动生成唯一值（推荐）
    with db_session_scope() as session:
        users = User.query.filter_by(is_active=True).all()
        # 业务逻辑...
        
        # 创建新记录
        report = Report(title="日报", content="...")
        report.save()
    # 退出时自动提交并清理 session

# 手动控制提交
def batch_update():
    with db_session_scope(auto_commit=False) as session:
        for user in User.query.all():
            user.status = "processed"
        session.commit()  # 手动提交
```

> **request_id 参数说明**：
> - 不传（推荐）：自动生成唯一 ID，如 `"a1b2c3d4"`
> - 传入固定值：仅用于**不会并发执行**的场景，便于日志追踪

**方式2：@with_db_session() 装饰器**

```python
from yweb.orm import with_db_session

@with_db_session()
def import_users(session, user_data_list):
    """session 作为第一个参数自动注入"""
    for data in user_data_list:
        user = User(**data)
        session.add(user)
    # 自动提交

# 调用时不需要传 session
import_users([{"name": "张三"}, {"name": "李四"}])

# 定时任务
@scheduler.scheduled_job('cron', hour=2)
@with_db_session(request_id="nightly-cleanup")
def nightly_cleanup(session):
    # 清理过期数据
    User.cleanup_soft_deleted(days=30, commit=True)
```

### 4.4 线程池场景（重点）

在线程池中，**每个任务必须有独立的 request_id**，否则会导致 session 污染。

**正确方式：使用 db_session_scope()**

```python
from concurrent.futures import ThreadPoolExecutor
from yweb.orm import db_session_scope

def worker_task(task_id: int, user_id: int):
    """线程池中的工作任务"""
    # 每个任务使用独立的 session 上下文
    with db_session_scope(request_id=f"task-{task_id}") as session:
        user = User.get(user_id)
        user.status = "processed"
        user.save()
    # 自动提交、自动清理

# 主程序
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(worker_task, i, i + 1)
        for i in range(10)
    ]
    for future in futures:
        future.result()
```

**正确方式：使用 @with_db_session() 装饰器**

```python
from concurrent.futures import ThreadPoolExecutor
from yweb.orm import with_db_session

@with_db_session()  # 自动生成唯一 request_id
def process_user(session, user_id: int):
    user = User.get(user_id)
    user.status = "processed"
    return user.id

# 主程序
with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(process_user, i)  # 不需要传 session
        for i in range(10)
    ]
    results = [f.result() for f in futures]
```

**❌ 错误示例**

```python
from yweb.orm import db_manager

# 错误1：多个线程共享同一个 request_id
db_manager._set_request_id("shared-id")  # 在主线程设置
with ThreadPoolExecutor(max_workers=5) as executor:
    # 所有任务可能共享同一个 session！
    futures = [executor.submit(some_db_work) for _ in range(10)]

# 错误2：没有清理 session
def bad_task():
    db_manager._set_request_id("task-1")
    session = db_manager.get_session()
    # 做一些操作...
    # 没有调用 on_request_end()！→ session 泄漏
```

**✅ 正确做法：使用 db_session_scope 或 @with_db_session**

```python
from yweb.orm import db_session_scope, with_db_session

# 方式1：上下文管理器
def good_task():
    with db_session_scope(request_id="task-1") as session:
        # 做一些操作...
    # 自动清理

# 方式2：装饰器
@with_db_session(request_id="task-1")
def another_good_task(session):
    # 做一些操作...
# 自动清理
```

---

## 5. CRUD 操作

### 5.1 创建

```python
# 单个创建
user = User(name="张三", username="zhangsan", email="zhang@example.com")
user.save(commit=True)

# 批量创建
users = [
    User(name=f"用户{i}", username=f"user{i}")
    for i in range(100)
]
User.save_all(users, commit=True)
```

> **关于 commit 参数**：
> - `commit=True`：立即提交事务到数据库
> - `commit=False`（默认）：不提交，需要手动调用 `session.commit()`
> - 在事务上下文中（如 `db_session_scope()`），`commit=True` 会被抑制，由上下文管理器统一提交

### 5.2 查询

```python
# 根据 ID 查询
user = User.get(1)

# 根据名称查询（BaseModel 提供）
user = User.get_by_name("张三")

# 根据编码查询（BaseModel 提供）
user = User.get_by_code("USER001")

# 条件查询
users = User.query.filter_by(is_active=True).all()
users = User.query.filter(User.age > 18).all()

# 获取所有
all_users = User.get_all()

# 根据条件获取列表
users = User.get_list_by_conditions({"status": "active", "role": "admin"})
```

### 5.3 更新

```python
# 单个更新
user = User.get(1)
user.name = "新名称"
user.update(commit=True)

# 通过 kwargs 更新
user.update(name="新名称", age=25, commit=True)

# 批量更新（相同值）
users = User.query.filter_by(status="pending").all()
User.update_all(users, status="approved", commit=True)

# 批量更新（通过条件）
affected = User.bulk_update(
    filters={"status": "pending"},
    values={"status": "approved"},
    commit=True
)

# 根据 ID 列表批量更新
affected = User.bulk_update_by_ids(
    ids=[1, 2, 3],
    values={"is_active": False},
    commit=True
)
```

> **关于 `commit=True` 的重要说明**：
> 
> 在**事务上下文**中，`commit=True` 会被**自动抑制**，由事务管理器统一控制提交：
> ```python
> from yweb.orm import transaction_manager
> 
> with transaction_manager() as tx:
>     user.update(name="新名称", commit=True)  # commit 被抑制，不会立即提交
>     order.save(commit=True)                   # commit 被抑制
> # 事务结束时统一提交（或回滚）
> ```
> 
> 这是为了保证事务的原子性，避免部分提交导致数据不一致。

### 5.4 删除

```python
# 软删除（推荐，BaseModel 默认行为）
user = User.get(1)
user.soft_delete(commit=True)  # 设置 deleted_at

# 批量软删除
User.bulk_soft_delete(filters={"status": "inactive"}, commit=True)
User.bulk_soft_delete_by_ids(ids=[1, 2, 3], commit=True)

# 物理删除（慎用）
user.delete(commit=True)
User.bulk_delete(filters={"status": "test"}, commit=True)
User.bulk_delete_by_ids(ids=[1, 2, 3], commit=True)

# 清理软删除数据（定期任务）
count = User.cleanup_soft_deleted(days=30, commit=True)  # 删除30天前的
```

### 5.5 序列化与 DTO 转换

```python
# 转字典
user_dict = user.to_dict()
user_dict = user.to_dict(exclude={"password", "salt"})

# 包含关联对象
user_dict = user.to_dict_with_relations(
    relations=["roles", "department"],
    exclude={"password"}
)

# 转换为 DTO（推荐用于 API 响应）
from yweb.orm import DTO

class UserDTO(DTO):
    """DTO 继承自 Pydantic BaseModel，支持字段验证和自动序列化"""
    id: int = 0
    name: str = ""
    email: str = ""
    created_at: str = ""  # datetime 自动格式化为字符串

user = User.get(1)
user_dto = UserDTO.from_entity(user)  # 自动映射同名字段
return user_dto  # FastAPI 自动序列化
```

**DTO 特性说明**：

| 方法 | 用途 | 示例 |
|------|------|------|
| `from_entity(obj)` | 从 ORM 对象创建 | `UserDTO.from_entity(user)` |
| `from_list(items)` | 从列表批量转换 | `UserDTO.from_list(users)` |
| `from_page(page_result)` | 从分页结果转换 | `UserDTO.from_page(page_result)` |
| `from_dict(dict)` | 从字典创建（忽略额外字段） | `UserDTO.from_dict(data)` |

> **配置说明**：DTO 默认配置 `extra='ignore'`，从字典创建时会自动忽略未定义的额外字段，
> 详见 [DTO 与响应处理规范](webapi项目开发规范/dto_response_guide.md)。

---

## 6. 分页查询

### 6.1 基本分页

```python
# Query 对象分页
page_result = User.query.filter_by(is_active=True).paginate(
    page=1,
    page_size=10
)

print(f"总记录数: {page_result.total_records}")
print(f"总页数: {page_result.total_pages}")
print(f"当前页: {page_result.page}")
print(f"每页大小: {page_result.page_size}")

for user in page_result.rows:
    print(user.name)
```

### 6.2 复杂查询分页

```python
from sqlalchemy import select

# Select 语句分页
stmt = select(User).where(
    User.is_active == True,
    User.age >= 18
).order_by(User.created_at.desc())

page_result = User.paginate(stmt, page=1, page_size=20)
```

### 6.3 带过滤条件的分页

```python
# 动态构建查询
query = User.query

if keyword:
    query = query.filter(User.name.ilike(f"%{keyword}%"))
if status:
    query = query.filter(User.status == status)

query = query.order_by(User.created_at.desc())
page_result = query.paginate(page=page, page_size=page_size)
```

---

## 7. 软删除

> **前提条件**：模型必须继承 `BaseModel`（包含 `SimpleSoftDeleteMixin`）才能使用软删除功能。
> `CoreModel` 不包含软删除功能。

### 7.1 软删除相关方法速查

| 方法 | 来源 | 说明 |
|------|------|------|
| `delete(commit)` | CoreModel | 删除对象（配合软删除钩子自动转为软删除） |
| `soft_delete()` | SimpleSoftDeleteMixin | 直接设置 `deleted_at = now()` |
| `undelete()` | SimpleSoftDeleteMixin | ⚠️ 恢复软删除（**不推荐使用**） |
| `is_deleted` | SimpleSoftDeleteMixin | 属性，检查是否已软删除 |
| `bulk_soft_delete(filters)` | CoreModel | 批量软删除 |
| `bulk_soft_delete_by_ids(ids)` | CoreModel | 按ID批量软删除 |
| `get_soft_deleted_count(days)` | CoreModel | 获取软删除数据数量 |
| `cleanup_soft_deleted(days)` | CoreModel | 清理软删除数据（物理删除） |
| `cleanup_all_soft_deleted(days)` | CoreModel | 清理所有表的软删除数据 |

### 7.2 基本使用

```python
# 软删除
user = User.get(1)
user.delete(commit=True)  # 自动设置 deleted_at = now()

# 查询时自动过滤软删除的记录
active_users = User.query.all()

# 包含软删除的记录
all_users = User.query.execution_options(include_deleted=True).all()
```

> **关于恢复软删除**：
> 
> 提供了 `undelete()` 方法用于恢复软删除的记录：
> 
> ```python
> user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()
> if user and user.is_deleted:
>     user.undelete()
>     user.update(commit=True)
> ```
> 
> **但强烈不推荐使用**，原因：
> 1. 级联软删除的子记录不会自动恢复，导致父子记录状态不一致
> 2. 软删除通常表示业务上的"作废"，恢复应该是新的业务流程
> 
> **推荐做法**：重新创建记录，或在业务层实现完整的恢复逻辑

### 7.3 级联软删除

```python
from yweb.orm import BaseModel, fields

class Department(BaseModel):
    __tablename__ = "departments"
    name: Mapped[str] = mapped_column(String(100))

class Employee(BaseModel):
    __tablename__ = "employees"
    name: Mapped[str] = mapped_column(String(100))
    
    # 级联软删除：部门软删除时，员工也软删除
    department = fields.ManyToOne(Department, on_delete=fields.DELETE)

# 软删除部门时，关联的员工也会被软删除
dept = Department.get(1)
dept.delete(commit=True)  # 钩子自动转为软删除，员工也被级联软删除
```

### 7.4 清理软删除数据

```python
# 查看软删除数据数量
count = User.get_soft_deleted_count()
count = User.get_soft_deleted_count(days=30)  # 30天前的

# 清理软删除数据（物理删除）
deleted_count = User.cleanup_soft_deleted(commit=True)  # 所有
deleted_count = User.cleanup_soft_deleted(days=30, commit=True)  # 30天前的

# 清理所有表的软删除数据
result = BaseModel.cleanup_all_soft_deleted(days=30, commit=True)
for table, count in result.items():
    print(f"{table}: 清理了 {count} 条记录")
```

---

## 8. 历史记录

### 8.1 启用历史记录

```python
from yweb.orm import init_versioning

# 在定义模型之前初始化
init_versioning()

class Document(BaseModel):
    __tablename__ = "documents"
    enable_history = True  # 启用历史记录
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(10000))
```

### 8.2 查询历史

```python
doc = Document.get(1)

# 获取所有历史记录
history = doc.get_history()
# 或使用属性
history = doc.history

# 获取特定版本
history = doc.get_history(version=5)

# 只获取特定字段
history = doc.get_history(field_names=['title', 'content', 'ver'])

# 历史记录数量
count = doc.history_count

# 不需要先获取实例
history = Document.get_history_by_id(doc_id=1)
```

### 8.3 版本对比

```python
# 比较两个版本的差异
diff = doc.get_history_diff(from_version=1, to_version=3)
for field, change in diff.items():
    print(f"{field}: {change['from']} -> {change['to']}")

# 文本字段的详细差异
detail = doc.get_field_text_diff("content", from_version=1, to_version=3)
print(detail["diff"])  # unified diff 格式

# HTML 格式
detail = doc.get_field_text_diff("content", 1, 3, output_format="html")
```

### 8.4 版本恢复

```python
# 恢复到指定版本
doc.restore_to_version(version=2)
session.commit()  # 会创建新的历史记录
```

---

## 9. 线程池安全使用

### 9.1 推荐模式

```python
from concurrent.futures import ThreadPoolExecutor
from yweb.orm import db_session_scope, with_db_session

# 模式1：使用上下文管理器
def process_task(task_id: int, data: dict):
    # request_id 参数可选：
    # - 传入：使用指定的 request_id（便于日志追踪）
    # - 不传：自动生成唯一 ID
    with db_session_scope(request_id=f"task-{task_id}") as session:
        # 所有数据库操作在这个上下文中
        item = Item.get(data["id"])
        item.status = "processed"
        item.save()
    # 自动提交并清理

# 模式2：使用装饰器
@with_db_session()
def process_item(session, item_id: int):
    item = Item.get(item_id)
    item.status = "processed"
    return item.id

# 执行
with ThreadPoolExecutor(max_workers=10) as executor:
    # 模式1
    futures = [executor.submit(process_task, i, {"id": i}) for i in range(100)]
    
    # 或模式2
    futures = [executor.submit(process_item, i) for i in range(100)]
    
    results = [f.result() for f in futures]
```

> **关于 request_id 参数**：
> - `request_id` 是可选参数，不传则自动生成唯一ID（使用 `uuid.uuid4().hex`）
> - 建议在需要日志追踪时传入有意义的 request_id（如 `f"task-{task_id}"`）
> - 在简单场景下可以省略，让系统自动生成

### 9.2 读取密集型任务

```python
@with_db_session()
def read_task(session, user_id: int):
    """只读任务"""
    user = User.get(user_id)
    # 分离对象，避免跨 session 访问问题
    if user:
        user.detach()
    return user

# 并发读取
with ThreadPoolExecutor(max_workers=20) as executor:
    futures = [executor.submit(read_task, i) for i in range(100)]
    users = [f.result() for f in futures]
```

### 9.3 批量处理模式

```python
from yweb.orm import db_session_scope

def batch_process(batch_id: int, items: list):
    """批量处理一组数据"""
    with db_session_scope(request_id=f"batch-{batch_id}") as session:
        for item_data in items:
            item = Item(**item_data)
            item.save()
        # 批量提交，减少事务开销

# 分批处理
all_items = [...]  # 大量数据
batch_size = 100
batches = [all_items[i:i+batch_size] for i in range(0, len(all_items), batch_size)]

with ThreadPoolExecutor(max_workers=5) as executor:
    futures = [
        executor.submit(batch_process, i, batch)
        for i, batch in enumerate(batches)
    ]
    for future in futures:
        future.result()
```

---

## 10. 最佳实践

### 10.1 Session 管理规则

| 场景 | 推荐方式 |
|-----|---------|
| FastAPI 路由 | `RequestIDMiddleware` 或 `Depends(get_db)` |
| 脚本/定时任务 | `db_session_scope()` 或 `@with_db_session()` |
| 线程池任务 | `db_session_scope()` 或 `@with_db_session()` |
| 异步任务 | `@with_db_session()`（支持异步函数） |

### 10.2 提交策略

```python
# 方式1：每次操作提交（简单场景）
user.save(commit=True)

# 方式2：批量操作后统一提交（性能更好）
with db_session_scope() as session:
    for data in user_data_list:
        user = User(**data)
        user.save()  # commit=False
    # 退出时自动提交所有更改

# 方式3：使用事务管理器
from yweb.orm import transaction_manager as tm

with tm.transaction() as tx:
    user1.save()
    user2.save()
    order.save()
    # 全部成功才提交，任一失败全部回滚
```

### 10.3 查询优化

```python
# 预加载关联对象
from sqlalchemy.orm import joinedload

users = User.query.options(
    joinedload(User.roles),
    joinedload(User.department)
).all()

# 只查询需要的字段
from sqlalchemy import select

stmt = select(User.id, User.name, User.email).where(User.is_active == True)
result = User.query.session.execute(stmt).mappings().all()

# 分页时避免 N+1 问题
query = User.query.options(joinedload(User.roles))
page_result = query.paginate(page=1, page_size=20)
```

### 10.4 异常处理

```python
from sqlalchemy.exc import IntegrityError

try:
    user = User(username="existing_user")
    user.save(commit=True)
except IntegrityError:
    # 唯一约束冲突
    print("用户名已存在")
```

### 10.5 跨请求对象传递

```python
# 需要将对象传递到其他请求/线程时
user = User.get(1)
user.detach()  # 分离对象

# 现在可以安全地传递 user 对象
# 在其他请求中重新关联
new_session.merge(user)
```

### 10.6 多租户实现

ORM 核心模块不提供内置多租户支持，需要在业务层实现：

```python
from contextvars import ContextVar
from sqlalchemy import String, event
from sqlalchemy.orm import Mapped, mapped_column

# 租户上下文
current_tenant_id: ContextVar[str] = ContextVar('tenant_id', default=None)

# 在模型中添加租户字段
class User(BaseModel):
    tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    username: Mapped[str] = mapped_column(String(50))

# 查询时手动过滤
tenant_id = current_tenant_id.get()
users = User.query.filter_by(tenant_id=tenant_id).all()

# 或使用事件监听器自动过滤（参考软删除实现）
@event.listens_for(User, 'before_insert')
def set_tenant_id(mapper, connection, target):
    if not target.tenant_id:
        target.tenant_id = current_tenant_id.get()
```

---

## 附录：API 速查表

### Session 管理

| API | 说明 |
|-----|------|
| `init_database(...)` | 初始化数据库连接 |
| `get_engine()` | 获取数据库引擎 |
| `db_manager.get_session()` | 获取 scoped session（低级 API） |
| `get_db()` | FastAPI 依赖注入 |
| `db_session_scope()` | session 上下文管理器 |
| `@with_db_session()` | session 装饰器 |
| `on_request_end()` | 清理 session |
| `db_manager._set_request_id()` | 设置请求 ID（内部 API） |

### 模型方法

| 方法 | 说明 |
|-----|------|
| `Model.get(id)` | 根据 ID 获取 |
| `Model.get_by_name(name)` | 根据名称获取（BaseModel） |
| `Model.get_by_code(code)` | 根据编码获取（BaseModel） |
| `Model.get_all()` | 获取所有记录 |
| `instance.save(commit=False)` | 保存（新增/更新） |
| `instance.update(**kwargs)` | 更新属性 |
| `instance.delete()` | 物理删除 |
| `instance.soft_delete()` | 软删除（BaseModel） |
| `instance.undelete()` | 恢复软删除（BaseModel，不推荐使用） |
| `instance.to_dict()` | 转字典 |
| `instance.detach()` | 分离对象 |
| `Model.save_all(objects)` | 批量保存 |
| `Model.bulk_update(...)` | 批量更新 |
| `Model.bulk_delete(...)` | 批量删除 |

### 分页

| 方法 | 说明 |
|-----|------|
| `query.paginate(page, page_size)` | Query 分页 |
| `Model.paginate(stmt, page, page_size)` | Select 语句分页 |

### 历史记录

| 方法 | 说明 |
|-----|------|
| `instance.history` | 获取历史记录 |
| `instance.history_count` | 历史记录数量 |
| `instance.get_history(version)` | 获取指定版本 |
| `instance.get_history_diff(v1, v2)` | 版本差异 |
| `instance.restore_to_version(v)` | 恢复到版本 |


## 更多资源

- [分页功能详细指南](pagination_guide.md)
- [BaseResponse使用指南](base_response_guide.md)
- [示例应用](../examples/demo_app/)

