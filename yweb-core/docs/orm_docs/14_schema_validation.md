# 14. Schema 与验证

## 概述

YWeb ORM 提供了与 Pydantic 集成的 Schema 支持，用于：

- 请求数据验证
- 响应数据格式化
- 分页参数处理
- ORM 对象转换

## BaseSchemas

### 基本用法

```python
from yweb.orm import BaseSchemas

class UserSchema(BaseSchemas):
    id: int
    username: str
    email: str

# 从 ORM 对象创建
user = User.get(1)
user_schema = UserSchema.model_validate(user)
print(user_schema.username)
```

### from_attributes 配置

BaseSchemas 默认启用 `from_attributes`，可以直接从 ORM 对象创建：

```python
class UserSchema(BaseSchemas):
    id: int
    username: str

# 自动从 ORM 对象属性读取
user = User.get(1)
schema = UserSchema.model_validate(user)
```

## PaginationField

### 分页参数

```python
from yweb.orm import PaginationField

# 创建分页参数
pagination = PaginationField(page=1, page_size=10)

print(pagination.page)       # 1
print(pagination.page_size)  # 10
```

### 默认值

```python
# 使用默认值
pagination = PaginationField()
print(pagination.page)       # 1（默认）
print(pagination.page_size)  # 10（默认）
```

### 参数验证

```python
# 页码自动修正为最小值 1
pagination = PaginationField(page=0, page_size=10)
print(pagination.page)  # 1（最小值）

pagination = PaginationField(page=-1, page_size=10)
print(pagination.page)  # 1（最小值）

# 页大小自动修正为最小值 1
pagination = PaginationField(page=1, page_size=0)
print(pagination.page_size)  # 1（最小值）

# 注意：PaginationField 不限制最大值
# 最大值限制由 paginate() 的 max_page_size 参数控制
pagination = PaginationField(page=1, page_size=200)
print(pagination.page_size)  # 200（不会被限制）
```

### 计算偏移量

```python
pagination = PaginationField(page=3, page_size=20)

# 计算偏移量
offset = (pagination.page - 1) * pagination.page_size
print(offset)  # 40
```

## Page 响应

### Page 对象

```python
from yweb.orm import Page

page = Page(
    rows=[{"id": 1}, {"id": 2}],
    total_records=100,
    page=1,
    page_size=10,
    total_pages=10
)

print(page.rows)           # [{"id": 1}, {"id": 2}]
print(page.total_records)  # 100
print(page.page)           # 1
print(page.page_size)      # 10
print(page.total_pages)    # 10
print(page.has_next)       # True
print(page.has_prev)       # False
```

### 转换为字典

```python
page_dict = page.to_dict()
# {
#     "rows": [...],
#     "total_records": 100,
#     "page": 1,
#     "page_size": 10,
#     "total_pages": 10,
#     "has_next": True,
#     "has_prev": False
# }
```

## 在 FastAPI 中使用

### 请求验证

```python
from fastapi import FastAPI, Query
from pydantic import BaseModel, EmailStr

class UserCreate(BaseModel):
    username: str
    email: EmailStr
    password: str

class UserUpdate(BaseModel):
    username: str | None = None
    email: EmailStr | None = None

@app.post("/users")
def create_user(data: UserCreate):
    user = User(
        username=data.username,
        email=data.email,
        password=hash_password(data.password)
    )
    user.save(True)
    return OK(user)

@app.put("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate):
    user = User.get(user_id)
    if data.username:
        user.username = data.username
    if data.email:
        user.email = data.email
    user.save(True)
    return OK(user)
```

### 响应模型

```python
from yweb.orm import BaseSchemas

class UserResponse(BaseSchemas):
    id: int
    username: str
    email: str
    created_at: str

@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int):
    user = User.get(user_id)
    return user  # 自动转换
```

### 分页参数

```python
from fastapi import Query

@app.get("/users")
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量")
):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)
```

### 搜索参数

```python
from typing import Optional

class UserSearchParams(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
    is_active: Optional[bool] = None
    page: int = 1
    page_size: int = 10

@app.get("/users/search")
def search_users(params: UserSearchParams = Depends()):
    query = User.query

    if params.username:
        query = query.filter(User.username.ilike(f"%{params.username}%"))

    if params.email:
        query = query.filter(User.email.ilike(f"%{params.email}%"))

    if params.is_active is not None:
        query = query.filter(User.is_active == params.is_active)

    return OK(query.paginate(page=params.page, page_size=params.page_size))
```

## DateTimeStr 类型

### 日期时间格式化

```python
from yweb.orm import DateTimeStr, format_datetime_to_string
from datetime import datetime

# 格式化日期时间
dt = datetime(2024, 1, 15, 10, 30, 45)
result = format_datetime_to_string(dt)
print(result)  # "2024-01-15 10:30:45"

# None 值处理
result = format_datetime_to_string(None)
print(result)  # None
```

### 在 Schema 中使用

```python
from yweb.orm import BaseSchemas, DateTimeStr

class UserSchema(BaseSchemas):
    id: int
    username: str
    created_at: DateTimeStr
```

## 自定义验证

### 字段验证

```python
from pydantic import BaseModel, field_validator

class UserCreate(BaseModel):
    username: str
    email: str
    password: str

    @field_validator('username')
    @classmethod
    def username_must_be_valid(cls, v):
        if len(v) < 3:
            raise ValueError('用户名至少3个字符')
        if not v.isalnum():
            raise ValueError('用户名只能包含字母和数字')
        return v

    @field_validator('password')
    @classmethod
    def password_must_be_strong(cls, v):
        if len(v) < 8:
            raise ValueError('密码至少8个字符')
        return v
```

### 模型验证

```python
from pydantic import BaseModel, model_validator

class DateRange(BaseModel):
    start_date: str
    end_date: str

    @model_validator(mode='after')
    def check_dates(self):
        if self.start_date > self.end_date:
            raise ValueError('开始日期不能晚于结束日期')
        return self
```

## 嵌套 Schema

### 定义嵌套结构

```python
class RoleSchema(BaseSchemas):
    id: int
    name: str

class UserWithRolesSchema(BaseSchemas):
    id: int
    username: str
    roles: list[RoleSchema]
```

### 使用嵌套 Schema

```python
@app.get("/users/{user_id}/with-roles")
def get_user_with_roles(user_id: int):
    user = User.query.options(
        selectinload(User.roles)
    ).filter_by(id=user_id).first()

    return UserWithRolesSchema.model_validate(user)
```

## 最佳实践

### 1. 分离请求和响应 Schema

```python
# 请求 Schema
class UserCreate(BaseModel):
    username: str
    email: str
    password: str

# 响应 Schema
class UserResponse(BaseSchemas):
    id: int
    username: str
    email: str
```

### 2. 使用 Optional 处理可选字段

```python
from typing import Optional

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[str] = None
```

### 3. 定义通用分页响应

```python
from typing import Generic, TypeVar
from pydantic import BaseModel

T = TypeVar('T')

class PageResponse(BaseModel, Generic[T]):
    rows: list[T]
    total_records: int
    page: int
    page_size: int
    total_pages: int
    has_next: bool
    has_prev: bool
```

### 4. 使用 Depends 注入参数

```python
from fastapi import Depends

def get_pagination(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    return {"page": page, "page_size": page_size}

@app.get("/users")
def list_users(pagination: dict = Depends(get_pagination)):
    return User.query.paginate(**pagination)
```

## 常见问题

### Q1: 如何处理日期时间字段？

```python
from datetime import datetime

class UserSchema(BaseSchemas):
    id: int
    created_at: datetime  # 自动处理
```

### Q2: 如何排除某些字段？

```python
class UserSchema(BaseSchemas):
    id: int
    username: str
    # 不包含 password 字段
```

### Q3: 如何添加计算字段？

```python
from pydantic import computed_field

class UserSchema(BaseSchemas):
    id: int
    first_name: str
    last_name: str

    @computed_field
    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"
```

### Q4: 如何处理枚举类型？

```python
from enum import Enum

class UserStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"

class UserSchema(BaseSchemas):
    id: int
    status: UserStatus
```

## 下一步

- [15_FastAPI集成](15_fastapi_integration.md) - 深入学习 FastAPI 集成
- [13_数据序列化](13_serialization.md) - 了解序列化方法
