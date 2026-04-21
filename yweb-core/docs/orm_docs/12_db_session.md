# 12. 数据库会话管理

## 概述

YWeb ORM 提供了完整的数据库会话管理功能，包括：

- 数据库初始化
- 连接池管理
- 请求作用域的 session
- FastAPI 依赖注入支持
- **非 HTTP 场景支持**（脚本、定时任务、后台任务）

## 初始化数据库

### init_database() 函数

```python
from yweb.orm import init_database

# 基本用法
engine, session_scope = init_database("sqlite:///./app.db")

# 完整配置
engine, session_scope = init_database(
    database_url="postgresql://user:pass@localhost/db",
    echo=False,           # 是否打印 SQL
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出连接数
    pool_timeout=30,      # 连接超时（秒）
    pool_recycle=1800,    # 连接回收时间（秒）
)
```

### 支持的数据库

```python
# SQLite
init_database("sqlite:///./app.db")
init_database("sqlite:///:memory:")  # 内存数据库

# PostgreSQL
init_database("postgresql://user:pass@localhost/db")
init_database("postgresql+psycopg2://user:pass@localhost/db")

# MySQL
init_database("mysql+pymysql://user:pass@localhost/db")

# SQL Server
init_database("mssql+pyodbc://user:pass@localhost/db")
```

### 返回值

```python
engine, session_scope = init_database("sqlite:///./app.db")

# engine: SQLAlchemy Engine 对象
# session_scope: scoped_session 对象
```

## 获取引擎和会话

### get_engine()

```python
from yweb.orm import get_engine

engine = get_engine()

# 创建表
BaseModel.metadata.create_all(bind=engine)

# 删除表
BaseModel.metadata.drop_all(bind=engine)
```

### db_manager.get_session()

> ⚠️ **警告**：这是低级 API，直接使用需要自行管理异常和清理。
> 
> **推荐使用以下安全方式：**
> - FastAPI 路由：`get_db()` 依赖
> - 脚本/测试：`db_session_scope()` 上下文管理器
> - 定时任务：`@with_db_session` 装饰器
> - 事务控制：`tm.transaction()` 事务管理器

```python
from yweb.orm import db_manager

session = db_manager.get_session()

# 使用 session
user = session.query(User).first()
session.commit()
```

**直接使用的风险：**

```python
# ❌ 危险：无异常处理，无清理
from yweb.orm import db_manager
session = db_manager.get_session()
user = User(name="tom")
session.add(user)
session.commit()  # 如果失败，session 状态不明确，可能连接泄漏

# ✅ 安全：使用 db_session_scope
from yweb.orm import db_session_scope
with db_session_scope() as session:
    user = User(name="tom")
    session.add(user)
# 自动提交、自动回滚、自动清理
```

## FastAPI 集成

### get_db() 依赖

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from yweb.orm import get_db

app = FastAPI()

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    users = db.query(User).all()
    return users

@app.post("/users")
def create_user(data: dict, db: Session = Depends(get_db)):
    user = User(**data)
    db.add(user)
    db.commit()
    return user
```

### 应用启动配置

```python
from fastapi import FastAPI
from yweb.orm import init_database, BaseModel, get_engine

app = FastAPI()

@app.on_event("startup")
def startup():
    # 初始化数据库
    init_database("sqlite:///./app.db")

    # 创建表
    BaseModel.metadata.create_all(bind=get_engine())

@app.on_event("shutdown")
def shutdown():
    # 清理资源（可选）
    pass
```

### 使用 lifespan（推荐）

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from yweb.orm import init_database, BaseModel, get_engine

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    init_database("sqlite:///./app.db")
    BaseModel.metadata.create_all(bind=get_engine())
    yield
    # 关闭时
    pass

app = FastAPI(lifespan=lifespan)
```

## 请求作用域管理

### db_manager._set_request_id()

设置当前请求 ID，用于日志追踪（内部 API）：

```python
from yweb.orm import db_manager
import uuid

@app.middleware("http")
async def add_request_id(request, call_next):
    request_id = str(uuid.uuid4())
    db_manager._set_request_id(request_id)
    response = await call_next(request)
    return response
```

> **注意**：通常不需要手动调用此函数，`RequestIDMiddleware` 会自动处理。

### db_manager._get_request_id()

获取当前请求 ID（内部 API）：

```python
from yweb.orm import db_manager

request_id = db_manager._get_request_id()
print(f"当前请求: {request_id}")
```

### on_request_end()

请求结束时清理 session。**此函数是幂等的**，可以安全地多次调用：

```python
from yweb.orm import on_request_end

@app.middleware("http")
async def cleanup_session(request, call_next):
    try:
        response = await call_next(request)
        return response
    finally:
        on_request_end()  # 幂等，多次调用安全
```

> **注意**：`get_db()` 依赖项已内置调用 `on_request_end()`，如果同时使用 `RequestIDMiddleware`，两者都会调用此函数，但由于幂等设计，不会产生副作用。

## 连接池配置

### 基本配置

```python
init_database(
    database_url="postgresql://...",
    pool_size=5,          # 连接池大小
    max_overflow=10,      # 最大溢出
    pool_timeout=30,      # 获取连接超时
    pool_recycle=1800,    # 连接回收时间
)
```

### 参数说明

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `pool_size` | 5 | 连接池中保持的连接数 |
| `max_overflow` | 10 | 超出 pool_size 后可创建的最大连接数 |
| `pool_timeout` | 30 | 获取连接的超时时间（秒） |
| `pool_recycle` | 1800 | 连接回收时间（秒），防止连接过期 |

### SQLite 特殊处理

SQLite 不支持连接池，会自动使用 `NullPool`：

```python
# SQLite 自动使用 NullPool
init_database("sqlite:///./app.db")
```

## SQL 日志

### 启用 SQL 日志

```python
# 开发环境：打印 SQL
init_database("sqlite:///./app.db", echo=True)

# 生产环境：关闭 SQL 日志
init_database("sqlite:///./app.db", echo=False)
```

### 自定义日志

```python
import logging

# 配置 SQLAlchemy 日志
logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)
```

## 多数据库支持

### 配置多个数据库

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

# 主数据库
main_engine = create_engine("postgresql://...")
MainSession = scoped_session(sessionmaker(bind=main_engine))

# 从数据库
replica_engine = create_engine("postgresql://...")
ReplicaSession = scoped_session(sessionmaker(bind=replica_engine))

# 使用
def get_main_db():
    return MainSession()

def get_replica_db():
    return ReplicaSession()
```

### 读写分离

```python
@app.get("/users")
def list_users(db: Session = Depends(get_replica_db)):
    """读操作使用从库"""
    return db.query(User).all()

@app.post("/users")
def create_user(data: dict, db: Session = Depends(get_main_db)):
    """写操作使用主库"""
    user = User(**data)
    db.add(user)
    db.commit()
    return user
```

## 最佳实践

### 0. 选择正确的 API（重要）

| 场景 | 推荐 API | 安全等级 |
|------|----------|---------|
| FastAPI 路由 | `get_db()` | 🟢 安全 |
| 脚本/测试 | `db_session_scope()` | 🟢 安全 |
| 定时任务 | `@with_db_session` | 🟢 安全 |
| 事务控制 | `tm.transaction()` | 🟢 安全 |
| 直接操作 | `db_manager.get_session()` | 🔴 需谨慎 |

### 1. 应用启动时初始化

```python
# 在应用启动时调用一次
init_database("sqlite:///./app.db")
```

### 2. 使用安全的 Session 获取方式

```python
# ✅ 推荐：FastAPI 依赖（自动清理）
@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    pass

# ✅ 推荐：上下文管理器（自动清理）
with db_session_scope() as session:
    pass

# ✅ 推荐：装饰器（自动清理）
@with_db_session()
def my_task(session):
    pass

# ❌ 不推荐：直接获取（需自行管理）
@app.get("/users")
def list_users():
    session = db_manager.get_session()  # 危险！
    pass
```

### 3. 合理配置连接池

```python
# 根据并发量配置
# 低并发
init_database(url, pool_size=5, max_overflow=5)

# 高并发
init_database(url, pool_size=20, max_overflow=30)
```

### 4. 设置连接回收

```python
# 防止连接过期（MySQL 默认 8 小时）
init_database(url, pool_recycle=3600)  # 1 小时
```

## 非 HTTP 场景支持

对于脚本、定时任务、后台任务等非 HTTP 场景，YWeb ORM 提供了专门的工具来安全管理 session 生命周期。

### 为什么需要特殊处理？

在 HTTP 场景中，`RequestIDMiddleware` 或 `get_db()` 会自动清理 session。但在非 HTTP 场景中：

```python
# ❌ 危险：session 永远不会被清理，导致连接泄漏
from yweb.orm import db_manager

def run_script():
    session = db_manager.get_session()
    # 执行操作...
    session.commit()
    # 脚本结束，session 未清理！
```

### db_session_scope() 上下文管理器

推荐用于脚本和一次性任务：

```python
from yweb.orm import db_session_scope

# 基本用法
with db_session_scope() as session:
    user = User(name="test")
    session.add(user)
# 自动提交并清理，无需手动调用

# 手动控制提交
with db_session_scope(auto_commit=False) as session:
    user = session.query(User).first()
    user.name = "updated"
    session.commit()  # 手动提交

# 带请求ID（便于日志追踪）
with db_session_scope(request_id="data-migration") as session:
    # 迁移逻辑...
    pass
```

#### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `request_id` | `str` | `None` | 请求ID，用于日志追踪，不传则自动生成 |
| `auto_commit` | `bool` | `True` | 是否自动提交 |

#### 完整脚本示例

```python
#!/usr/bin/env python
"""数据迁移脚本"""
from yweb.orm import init_database, db_session_scope, BaseModel

# 初始化数据库
init_database("postgresql://user:pass@localhost/db")

def migrate_users():
    with db_session_scope(request_id="migrate-users") as session:
        old_users = session.query(OldUser).all()
        for old_user in old_users:
            new_user = NewUser(
                name=old_user.name,
                email=old_user.email
            )
            session.add(new_user)
        # 自动提交
    # 自动清理 session

if __name__ == "__main__":
    migrate_users()
    print("迁移完成")
```

### @with_db_session 装饰器

推荐用于定时任务和后台任务函数：

```python
from yweb.orm import with_db_session

# 基本用法 - session 作为第一个参数自动注入
@with_db_session()
def import_data(session):
    users = session.query(User).all()
    for user in users:
        # 处理逻辑...
        pass

import_data()  # 调用时不需要传 session

# 带其他参数
@with_db_session()
def create_user(session, name, email):
    user = User(name=name, email=email)
    session.add(user)
    return user

user = create_user(name="Tom", email="tom@example.com")

# 手动控制提交
@with_db_session(auto_commit=False)
def batch_update(session, user_ids):
    for uid in user_ids:
        user = session.query(User).get(uid)
        user.status = "updated"
    session.commit()  # 手动提交
```

#### 定时任务集成

```python
from apscheduler.schedulers.background import BackgroundScheduler
from yweb.orm import with_db_session

scheduler = BackgroundScheduler()

@scheduler.scheduled_job('cron', hour=2)
@with_db_session(request_id="nightly-cleanup")
def nightly_cleanup(session):
    """每天凌晨2点清理过期数据"""
    expired = session.query(ExpiredToken).filter(
        ExpiredToken.expires_at < datetime.now()
    ).delete()
    print(f"清理了 {expired} 条过期记录")

@scheduler.scheduled_job('interval', minutes=30)
@with_db_session(request_id="sync-data")
def sync_external_data(session):
    """每30分钟同步外部数据"""
    # 同步逻辑...
    pass

scheduler.start()
```

#### 异步函数支持

```python
@with_db_session()
async def async_task(session):
    """支持异步函数（装饰器内部处理线程安全）"""
    users = session.query(User).all()
    await send_notifications(users)
```

> **注意**：`@with_db_session()` 装饰器内部管理 session 的生命周期和线程上下文。
> 这与 FastAPI 路由不同——在 FastAPI 路由中，应使用 `def` 路由或 `run_db()` 包装。

#### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `request_id` | `str` | `None` | 请求ID，不传则使用 `{函数名}-{随机ID}` 格式 |
| `auto_commit` | `bool` | `True` | 是否自动提交 |

### 场景选择指南

| 场景 | 推荐方式 | 原因 |
|------|----------|------|
| FastAPI 路由 | `get_db()` 依赖 | 自动清理，与中间件配合 |
| 一次性脚本 | `db_session_scope()` | 上下文管理器，代码清晰 |
| 定时任务 | `@with_db_session` | 装饰器方式，简洁优雅 |
| 后台任务 | `@with_db_session` | 自动注入 session |
| 测试代码 | `db_session_scope()` | 便于控制事务边界 |

## 异步路由与同步 ORM

### 问题背景

YWeb ORM 基于 SQLAlchemy 同步 Session。当你在 `async def` 路由中直接调用同步 ORM 方法时，
这些同步调用会**阻塞事件循环**，导致所有并发请求被串行化，最终引发 `QueuePool TimeoutError`。

```python
# ❌ 危险：async def 中直接调用同步 ORM，会阻塞事件循环
@app.get("/users")
async def list_users():
    return User.query.all()  # 阻塞！所有并发请求被串行化
```

### 异步安全检测

YWeb 内置了异步安全检测机制，当你在 `async def` 中直接调用同步 ORM 时，
框架会抛出 `SynchronousOnlyOperation` 异常并给出修复指引：

```python
from yweb.orm import SynchronousOnlyOperation

# 在 async 上下文中访问 Model.query 或 db_manager.get_session() 时
# 框架自动检测并抛出 SynchronousOnlyOperation
```

检测行为可通过环境变量 `YWEB_ASYNC_SAFETY` 控制：

| 值 | 行为 |
|----|------|
| `error`（默认） | 抛出 `SynchronousOnlyOperation` 异常 |
| `warn` | 发出 `RuntimeWarning` 警告，继续执行 |
| `off` | 禁用检测（不推荐，仅用于调试） |

### 推荐方式

**方式 1（推荐）：使用 `def` 路由**

FastAPI 会自动将 `def` 路由放入线程池执行，不会阻塞事件循环：

```python
# ✅ 推荐：def 路由，FastAPI 自动放线程池
@app.get("/users")
def list_users():
    return User.query.all()  # 安全！在线程池中执行
```

**方式 2：使用 `run_db()` 包装**

当路由需要混合使用异步 I/O 和同步 ORM 时：

```python
from yweb.orm import run_db

# ✅ async def + run_db()，同步调用在线程池中执行
@app.get("/users")
async def list_users():
    users = await run_db(User.get_all)
    extra = await some_async_http_call()
    return {"users": users, "extra": extra}

# 支持 lambda 包裹复杂查询
@app.get("/active-users")
async def get_active_users():
    users = await run_db(
        lambda: User.query.filter_by(is_active=True).all()
    )
    return users
```

### run_db() API

```python
from yweb.orm import run_db

result = await run_db(func, *args, **kwargs)
```

| 参数 | 说明 |
|------|------|
| `func` | 同步的可调用对象（函数或 lambda） |
| `*args` | 传给 func 的位置参数 |
| `**kwargs` | 传给 func 的关键字参数 |

内部通过 Starlette 的 `run_in_threadpool` 将同步调用移交到线程池，
`ContextVar`（request_id）会自动传递，因此同一请求内的多次 `run_db()` 调用共享同一个 Session。

### 场景选择指南

| 场景 | 推荐方式 | 原因 |
|------|----------|------|
| 纯数据库操作 | `def` 路由 | 最简单，FastAPI 自动线程池 |
| 混合 async I/O + DB | `async def` + `run_db()` | 保持异步 I/O 优势 |
| 脚本/定时任务 | `db_session_scope()` / `@with_db_session` | 非 HTTP 场景 |
| 测试代码 | 直接调用（非 async 上下文） | 检测自动放行 |

## 常见问题

### Q1: 连接池耗尽怎么办？

```python
# 增加连接池大小
init_database(url, pool_size=20, max_overflow=30)

# 或设置超时
init_database(url, pool_timeout=60)
```

### Q2: 连接断开怎么处理？

```python
# 设置连接回收
init_database(url, pool_recycle=1800)

# 启用连接预检
init_database(url, pool_pre_ping=True)
```

### Q3: 如何查看连接池状态？

```python
engine = get_engine()
pool = engine.pool

print(f"连接池大小: {pool.size()}")
print(f"已检出连接: {pool.checkedout()}")
print(f"溢出连接: {pool.overflow()}")
```

### Q4: 测试时如何使用内存数据库？

```python
# conftest.py
import pytest
from yweb.orm import init_database, BaseModel

@pytest.fixture
def memory_engine():
    engine, _ = init_database("sqlite:///:memory:")
    BaseModel.metadata.create_all(bind=engine)
    yield engine
    BaseModel.metadata.drop_all(bind=engine)
```

### Q5: 脚本中如何正确使用 session？

```python
# ❌ 错误：直接使用 db_manager.get_session()，忘记清理
from yweb.orm import db_manager

def bad_script():
    session = db_manager.get_session()
    session.query(User).all()
    session.commit()
    # 连接泄漏！

# ✅ 正确：使用 db_session_scope()
from yweb.orm import db_session_scope

def good_script():
    with db_session_scope() as session:
        session.query(User).all()
    # 自动清理

# ✅ 正确：使用 @with_db_session 装饰器
from yweb.orm import with_db_session

@with_db_session()
def another_good_script(session):
    session.query(User).all()
# 自动清理
```

### Q6: get_db() 和 RequestIDMiddleware 同时使用会重复清理吗？

不会。`on_request_end()` 是幂等的，多次调用只会执行一次清理：

```python
from yweb.orm import on_request_end

# 第一次调用：执行清理
on_request_end()

# 第二次调用：检测到已清理，直接跳过
on_request_end()  # 无副作用
```

因此可以放心同时使用 `get_db()` 和 `RequestIDMiddleware`。

### Q7: 为什么 commit 后对象状态变了？关系操作失效？

这是因为 SQLAlchemy 默认配置 `expire_on_commit=True`：

```python
# commit 后对象状态过期
role = Role(name="admin")
role.save(commit=True)  # commit 后 role 状态过期

user = User(username="tom")
user.roles.append(role)  # ⚠️ 可能失败！
```

**解决方案**：

1. **推荐：使用单次提交模式**（最佳实践）

```python
role = Role(name="admin")
user = User(username="tom")
user.roles.append(role)  # 都是新对象，直接关联
session.add_all([role, user])
session.commit()
```

2. **使用 refresh() 刷新对象**（特殊场景）

```python
role = Role(name="admin")
role.save(commit=True)
role.refresh()  # 刷新对象状态
user = User(username="tom")
user.roles.append(role)  # 现在可以正常工作
user.save(commit=True)
```

详细说明请参考 [03_CRUD操作](03_crud_operations.md) 中的"刷新对象"和"关系操作使用单次提交模式"章节。

### Q8: async def 路由中调用 ORM 报 SynchronousOnlyOperation？

这是异步安全检测在保护你。在 `async def` 中直接调用同步 ORM 会阻塞事件循环，导致并发性能严重下降。

```python
# ❌ 触发检测
@app.get("/users")
async def list_users():
    return User.query.all()

# ✅ 方式1：改为 def（推荐）
@app.get("/users")
def list_users():
    return User.query.all()

# ✅ 方式2：使用 run_db()
@app.get("/users")
async def list_users():
    return await run_db(User.get_all)
```

如需临时禁用检测（不推荐），设置环境变量 `YWEB_ASYNC_SAFETY=off`。

## 下一步

- [15_FastAPI集成](15_fastapi_integration.md) - 深入学习 FastAPI 集成
- [11_事务管理](11_transaction.md) - 了解事务控制
