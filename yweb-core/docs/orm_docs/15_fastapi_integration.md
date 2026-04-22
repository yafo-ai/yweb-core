# 15. FastAPI 集成

## 概述

YWeb ORM 与 FastAPI 完美集成，提供：

- 依赖注入支持
- 自动序列化
- 分页响应
- 统一错误处理

## 应用配置

### 基本配置

```python
from fastapi import FastAPI
from yweb.orm import (
    init_database,
    BaseModel,
    get_engine,
    activate_soft_delete_hook,
    configure_cascade_soft_delete,
)

app = FastAPI()

@app.on_event("startup")
def startup():
    # 1. 激活软删除
    activate_soft_delete_hook()
    configure_cascade_soft_delete()

    # 2. 初始化数据库
    init_database("sqlite:///./app.db")

    # 3. 创建表
    BaseModel.metadata.create_all(bind=get_engine())
```

### 使用 lifespan（推荐）

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时
    activate_soft_delete_hook()
    configure_cascade_soft_delete()
    init_database("sqlite:///./app.db")
    BaseModel.metadata.create_all(bind=get_engine())
    yield
    # 关闭时（可选清理）

app = FastAPI(lifespan=lifespan)
```

## async def vs def 路由（重要）

YWeb ORM 基于 SQLAlchemy 同步 Session。路由函数的声明方式直接影响并发性能：

| 声明方式 | ORM 调用 | 是否安全 | 说明 |
|----------|----------|---------|------|
| `def` | `User.query.all()` | ✅ 安全 | FastAPI 自动放入线程池 |
| `async def` —— 读路径 | **`await User.query.xxx()`（HybridQuery）** | ✅ 安全（推荐） | 链式不变、终端加 `await`，自动线程池 |
| `async def` —— 写路径 / 多语句 | `await async_db_call(func)` | ✅ 安全 | 手动放入线程池，批量共享 session |
| `async def` —— 漏 `await` | `users = User.query.all()` 后访问 `.name` | ❌ `TypeError` | 终端返回 `_HybridTerminal`，后续使用时暴露 |

### 推荐：使用 def 路由（最简）

```python
# ✅ def 路由，FastAPI 自动在线程池中执行
@app.get("/users")
def list_users():
    return User.query.filter(User.is_active.is_(True)).all()

@app.post("/users")
def create_user(data: UserCreate):
    user = User(**data.dict())
    user.save(True)
    return user
```

### async 读路径首选：HybridQuery

`Model.query` 是 HybridQuery，**同步代码零改动**；`async def` 里链式不变、终端加 `await` 即可：

```python
@app.get("/users")
async def list_users():
    users = await User.query.filter(User.is_active.is_(True)).all()
    return users

@app.get("/users/{uid}")
async def get_user(uid: int):
    u = await User.query.get(uid)
    return u

@app.get("/users/by-email/{email}")
async def by_email(email: str):
    return await User.query.filter_by(email=email).first()

@app.get("/users/page")
async def page(page: int = 1, size: int = 20):
    return await User.query.order_by(User.id.desc()).paginate(page=page, size=size)
```

支持的终端：`all / first / one / one_or_none / count / get / scalar / delete / update / paginate`。
同一请求内多次 `await` 共享同一个 Session（中间件在请求结束时统一清理）。

**回滚开关**：环境变量 `YWEB_HYBRID_QUERY=off` 切回老行为（async 下 `.query.xxx()` 原地抛
`SynchronousOnlyOperation`），用于发布初期的紧急定位。

### 混合 async I/O / 写路径 / 多语句：`async_db_call()`

当路由需要**同时**使用异步 I/O 和数据库操作、或者要做**写操作 / 多语句事务**时，
仍建议用 `async_db_call` 手动包装一段同步代码，让整段 DB 逻辑在同一个 session 内跑：

```python
from yweb.orm import async_db_call

@app.post("/users")
async def create_user(body: UserCreate):
    def _tx():
        u = User(**body.dict())
        u.save(commit=True)
        return u.to_dict()
    return await async_db_call(_tx)

@app.get("/users-with-extra")
async def list_with_extra():
    users = await async_db_call(User.get_all)
    extra = await some_async_http_call()
    return {"users": users, "extra": extra}
```

> **注意**：纯只读单句查询优先走 HybridQuery（方式一），`async_db_call` 适合多语句 /
> 写操作 / 混合 I/O 场景。纯 DB 操作不涉及其他 async I/O 时，`def` 路由最简单。

## 依赖注入

### get_db 依赖

```python
from fastapi import Depends
from sqlalchemy.orm import Session
from yweb.orm import get_db

@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    return db.query(User).all()
```

### 自定义依赖

```python
from fastapi import Depends
from yweb.orm import get_db

def get_user_service(db: Session = Depends(get_db)):
    return UserService(db)

@app.post("/users")
def create_user(
    data: dict,
    service: UserService = Depends(get_user_service)
):
    return service.create_user(data)
```

## CRUD 路由

### 完整示例

```python
from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from yweb.orm import get_db, BaseModel
from yweb import OK, NotFound, BadRequest
from pydantic import BaseModel as PydanticModel

# Pydantic Schema
class UserCreate(PydanticModel):
    username: str
    email: str

class UserUpdate(PydanticModel):
    username: str | None = None
    email: str | None = None

# 路由
@app.get("/users")
def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db)
):
    """获取用户列表"""
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)

@app.get("/users/{user_id}")
def get_user(user_id: int, db: Session = Depends(get_db)):
    """获取单个用户"""
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    return OK(user)

@app.post("/users")
def create_user(data: UserCreate, db: Session = Depends(get_db)):
    """创建用户"""
    # 检查用户名是否存在
    existing = User.query.filter(User.username == data.username).first()
    if existing:
        return BadRequest("用户名已存在")

    user = User(username=data.username, email=data.email)
    user.save(True)
    return OK(user, "创建成功")

@app.put("/users/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdate,
    db: Session = Depends(get_db)
):
    """更新用户"""
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")

    if data.username:
        user.username = data.username
    if data.email:
        user.email = data.email

    user.save(True)
    return OK(user, "更新成功")

@app.delete("/users/{user_id}")
def delete_user(user_id: int, db: Session = Depends(get_db)):
    """删除用户"""
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")

    user.delete(True)
    return OK(None, "删除成功")
```

## 分页查询

### 基本分页

```python
@app.get("/users")
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量")
):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)
```

### 带搜索的分页

```python
from typing import Optional

@app.get("/users")
def list_users(
    username: Optional[str] = Query(None, description="用户名"),
    email: Optional[str] = Query(None, description="邮箱"),
    is_active: Optional[bool] = Query(None, description="是否激活"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    query = User.query

    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))
    if email:
        query = query.filter(User.email.ilike(f"%{email}%"))
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    page_result = query.order_by(User.created_at.desc()).paginate(
        page=page,
        page_size=page_size
    )
    return OK(page_result)
```

### 响应格式

```json
{
    "status": "success",
    "message": "查询成功",
    "data": {
        "rows": [
            {"id": 1, "username": "tom", "email": "tom@example.com"},
            {"id": 2, "username": "jerry", "email": "jerry@example.com"}
        ],
        "total_records": 100,
        "page": 1,
        "page_size": 10,
        "total_pages": 10,
        "has_next": true,
        "has_prev": false
    }
}
```

## 错误处理

### 使用 YWeb 响应

```python
from yweb import OK, NotFound, BadRequest, ServerError

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    return OK(user)

@app.post("/users")
def create_user(data: dict):
    try:
        user = User(**data)
        user.save(True)
        return OK(user, "创建成功")
    except Exception as e:
        return BadRequest(str(e))
```

### 全局异常处理

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm.exc import StaleDataError

@app.exception_handler(StaleDataError)
async def stale_data_handler(request: Request, exc: StaleDataError):
    return JSONResponse(
        status_code=409,
        content={"status": "error", "message": "数据已被修改，请刷新后重试"}
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"status": "error", "message": str(exc)}
    )
```

## 关联数据

### 预加载关联

```python
from sqlalchemy.orm import selectinload

@app.get("/users/{user_id}/with-roles")
def get_user_with_roles(user_id: int):
    user = User.query.options(
        selectinload(User.roles)
    ).filter_by(id=user_id).first()

    if not user:
        return NotFound("用户不存在")

    return OK(user.to_dict_with_relations(relations=['roles']))
```

### 嵌套创建

```python
@app.post("/orders")
def create_order(data: dict, db: Session = Depends(get_db)):
    # 创建订单
    order = Order(
        order_no=data["order_no"],
        customer_name=data["customer_name"]
    )
    order.save()

    # 访问 order.id 时自动 flush，可直接使用
    for item_data in data["items"]:
        item = OrderItem(
            order_id=order.id,
            product_name=item_data["product_name"],
            quantity=item_data["quantity"]
        )
        item.save()

    return OK(order.to_dict_with_relations(relations=['items']))
```

## 事务处理

### 自动事务

```python
@app.post("/transfer")
def transfer_money(
    from_id: int,
    to_id: int,
    amount: float,
    db: Session = Depends(get_db)
):
    try:
        from_account = Account.get(from_id)
        to_account = Account.get(to_id)

        if from_account.balance < amount:
            return BadRequest("余额不足")

        from_account.balance -= amount
        from_account.update()

        to_account.balance += amount
        to_account.update()

        db.commit()
        return OK(None, "转账成功")
    except Exception as e:
        db.rollback()
        return ServerError(str(e))
```

### Service 层

```python
class OrderService:
    def __init__(self, db: Session):
        self.db = db

    def create_order(self, data: dict):
        try:
            order = Order(**data)
            order.add()
            self.db.commit()
            return order
        except Exception:
            self.db.rollback()
            raise

def get_order_service(db: Session = Depends(get_db)):
    return OrderService(db)

@app.post("/orders")
def create_order(
    data: dict,
    service: OrderService = Depends(get_order_service)
):
    order = service.create_order(data)
    return OK(order)
```

## 中间件

### 请求 ID 中间件

```python
import uuid
from yweb.orm import db_manager, on_request_end

@app.middleware("http")
async def request_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    db_manager._set_request_id(request_id)

    try:
        response = await call_next(request)
        return response
    finally:
        on_request_end()
```

### 数据库会话中间件

```python
@app.middleware("http")
async def db_session_middleware(request: Request, call_next):
    try:
        response = await call_next(request)
        return response
    finally:
        # 清理 session
        on_request_end()
```

## 最佳实践

### 1. 路由函数声明

```python
# ✅ 推荐：纯数据库操作使用 def
@app.get("/users")
def list_users():
    return User.query.all()

# ✅ 推荐：async 读路径用 HybridQuery（await 直接用）
@app.get("/users")
async def list_users():
    users = await User.query.filter(User.is_active.is_(True)).all()
    return users

# ✅ 推荐：混合 async I/O / 写路径用 async def + async_db_call
@app.post("/users")
async def create_user(body: UserCreate):
    def _tx():
        u = User(**body.dict())
        u.save(commit=True)
        return u.to_dict()
    return await async_db_call(_tx)

# ❌ 漏 await：得到 _HybridTerminal，后续访问属性时才暴露 TypeError
@app.get("/users")
async def list_users():
    users = User.query.all()          # 漏 await
    return [u.name for u in users]    # → TypeError
```

### 2. 使用依赖注入

```python
# 推荐
@app.get("/users")
def list_users(db: Session = Depends(get_db)):
    pass

# 不推荐
@app.get("/users")
def list_users():
    db = db_manager.get_session()
    pass
```

### 2. 分离业务逻辑

```python
# Service 层
class UserService:
    def create_user(self, data):
        pass

# 路由层
@app.post("/users")
def create_user(
    data: dict,
    service: UserService = Depends(get_user_service)
):
    return service.create_user(data)
```

### 3. 使用 Pydantic 验证

```python
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    username: str
    email: EmailStr

@app.post("/users")
def create_user(data: UserCreate):
    pass
```

### 4. 统一响应格式

```python
from yweb import OK, NotFound, BadRequest

@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    if not user:
        return NotFound("用户不存在")
    return OK(user)
```

## 完整项目结构

```
project/
├── app/
│   ├── __init__.py
│   ├── main.py           # FastAPI 应用
│   ├── models/           # ORM 模型
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── order.py
│   ├── schemas/          # Pydantic Schema
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── order.py
│   ├── services/         # 业务逻辑
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── order.py
│   ├── routers/          # 路由
│   │   ├── __init__.py
│   │   ├── user.py
│   │   └── order.py
│   └── deps.py           # 依赖
├── tests/
└── requirements.txt
```

## 下一步

- [12_数据库会话](12_db_session.md) - 深入了解会话管理
- [11_事务管理](11_transaction.md) - 学习事务控制
