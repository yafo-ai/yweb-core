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

### 1. 使用依赖注入

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
