# 05. 分页查询

## 概述

YWeb ORM 提供了强大的分页功能，支持两种分页方式：

- **Query 对象分页**：使用 `Model.query.paginate()`
- **Select 语句分页**：使用 `Model.paginate(stmt)`

## Page 对象

分页查询返回 `Page` 对象，包含以下属性：

```python
@dataclass
class Page(Generic[T]):
    rows: List[T]          # 当前页数据列表
    total_records: int     # 总记录数
    page: int              # 当前页码
    page_size: int         # 每页数量
    total_pages: int       # 总页数

    @property
    def has_next(self) -> bool:    # 是否有下一页
        return self.page < self.total_pages

    @property
    def has_prev(self) -> bool:    # 是否有上一页
        return self.page > 1
```

## Query 对象分页

### 基本用法

```python
# 简单分页
page_result = User.query.paginate(page=1, page_size=10)

# 访问结果
print(f"总记录数: {page_result.total_records}")
print(f"当前页: {page_result.page}")
print(f"每页数量: {page_result.page_size}")
print(f"总页数: {page_result.total_pages}")
print(f"是否有下一页: {page_result.has_next}")
print(f"是否有上一页: {page_result.has_prev}")

# 遍历数据
for user in page_result.rows:
    print(user.username)
```

### 带条件的分页

```python
# 单条件
page_result = User.query.filter(
    User.is_active == True
).paginate(page=1, page_size=10)

# 多条件
page_result = User.query.filter(
    User.is_active == True
).filter(
    User.department_id == 1
).paginate(page=1, page_size=10)
```

### 带排序的分页

```python
# 单字段排序
page_result = User.query.order_by(
    User.created_at.desc()
).paginate(page=1, page_size=10)

# 多字段排序
page_result = User.query.order_by(
    User.is_active.desc(),
    User.created_at.desc()
).paginate(page=1, page_size=10)
```

### 链式调用

```python
page_result = User.query\
    .filter(User.is_active == True)\
    .filter(User.age >= 18)\
    .order_by(User.created_at.desc())\
    .paginate(page=1, page_size=10)
```

### 动态条件构建

```python
def get_users(username=None, status=None, page=1, page_size=10):
    query = User.query

    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))

    if status:
        query = query.filter(User.status == status)

    return query.order_by(User.created_at.desc()).paginate(
        page=page,
        page_size=page_size
    )
```

## Select 语句分页

### 基本用法

```python
from sqlalchemy import select

# 创建 select 语句
stmt = select(User).order_by(User.created_at.desc())

# 分页
page_result = User.paginate(stmt, page=1, page_size=10)
```

### 带条件的分页

```python
from sqlalchemy import select, and_, or_

# 简单条件
stmt = select(User).where(User.is_active == True)
page_result = User.paginate(stmt, page=1, page_size=10)

# 复杂条件
stmt = select(User).where(
    and_(
        User.is_active == True,
        or_(
            User.role == "admin",
            User.role == "manager"
        )
    )
).order_by(User.created_at.desc())

page_result = User.paginate(stmt, page=1, page_size=10)
```

## 在 FastAPI 中使用

### 基本示例

```python
from fastapi import FastAPI, Query
from yweb import OK

app = FastAPI()

@app.get("/users")
def list_users(
    page: int = Query(1, ge=1, description="页码"),
    page_size: int = Query(10, ge=1, le=100, description="每页数量")
):
    page_result = User.query.paginate(page=page, page_size=page_size)
    return OK(page_result)
```

### 带搜索条件

```python
from typing import Optional

@app.get("/users")
def list_users(
    username: Optional[str] = Query(None, description="用户名"),
    status: Optional[str] = Query(None, description="状态"),
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=100)
):
    query = User.query

    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))

    if status:
        query = query.filter(User.status == status)

    page_result = query.order_by(User.created_at.desc()).paginate(
        page=page,
        page_size=page_size
    )

    return OK(page_result, "查询成功")
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

## 性能优化

### 只查询需要的字段

```python
# 方法1：使用 with_entities
page_result = User.query.with_entities(
    User.id,
    User.username,
    User.email
).paginate(page=1, page_size=10)

# 注意：with_entities 返回的是元组，不是模型对象
for row in page_result.rows:
    id, username, email = row
```

### 使用 load_only

```python
from sqlalchemy.orm import load_only

# 只加载指定字段
page_result = User.query.options(
    load_only(User.id, User.username, User.email)
).paginate(page=1, page_size=10)

# 返回的是模型对象，但只有指定字段有值
```

### 使用 defer 排除字段

```python
from sqlalchemy.orm import defer

# 排除大字段
page_result = User.query.options(
    defer(User.avatar),      # 排除头像
    defer(User.bio)          # 排除简介
).paginate(page=1, page_size=10)
```

### 预加载关联数据

```python
from sqlalchemy.orm import selectinload, joinedload

# selectinload：分两次查询（推荐用于一对多）
page_result = User.query.options(
    selectinload(User.roles),
    selectinload(User.posts)
).paginate(page=1, page_size=10)

# joinedload：JOIN 查询（推荐用于多对一）
page_result = User.query.options(
    joinedload(User.department)
).paginate(page=1, page_size=10)
```

#### 避免 N+1 查询问题

```python
# ❌ 不推荐：会导致 N+1 查询
users = User.query.filter(User.is_active == True).all()
for user in users:
    print(user.username, user.roles)  # 每次访问 roles 都会触发数据库查询

# ✅ 推荐：使用 selectinload 预加载关联数据
page_result = User.query.options(
    selectinload(User.roles)
).filter(User.is_active == True).paginate(page=1, page_size=10)
```

#### 限制关联表字段

```python
from sqlalchemy.orm import selectinload, load_only

# 只加载关联表中的必要字段
page_result = User.query.options(
    selectinload(User.roles).load_only(Role.id, Role.name, Role.code),
    selectinload(User.departments).load_only(Department.id, Department.name)
).paginate(page=1, page_size=10)
```

#### 排除关联表大字段

```python
from sqlalchemy.orm import selectinload, defer

# 排除关联表中的大字段或敏感字段
page_result = User.query.options(
    selectinload(User.profile).defer(Profile.avatar),  # 排除头像等大字段
    selectinload(User.settings).defer(Settings.config_data)  # 排除配置数据
).paginate(page=1, page_size=10)
```

#### 多层关联查询优化

```python
from sqlalchemy.orm import selectinload, load_only

def get_users_with_roles_and_permissions(page: int = 1, page_size: int = 10):
    """获取用户及其角色和权限（高度优化）"""
    
    # 使用多个 selectinload 预加载多层关联数据
    page_result = User.query.options(
        # 预加载角色，只取必要字段
        selectinload(User.roles).load_only(Role.id, Role.name, Role.code),
        # 预加载角色的权限（嵌套关联）
        selectinload(User.roles).selectinload(Role.permissions).load_only(
            Permission.id, Permission.name, Permission.code
        )
    ).filter(
        User.deleted_at == None
    ).order_by(
        User.created_at.desc()
    ).paginate(page=page, page_size=page_size)
    
    return page_result
```

### 组合优化

```python
from sqlalchemy.orm import selectinload, load_only

# 方式1：预加载关联并限制字段（推荐）
page_result = User.query.options(
    selectinload(User.roles).load_only(Role.id, Role.name),
    selectinload(User.department).load_only(Department.id, Department.name)
).paginate(page=1, page_size=10)

# 方式2：只查询主表字段（不包含关联）
page_result = User.query.with_entities(
    User.id,
    User.username,
    User.email
).paginate(page=1, page_size=10)
```

> **注意**：
>
> - `with_entities()` 和 `selectinload()` 不能同时使用
> - `with_entities()` 返回元组，不是模型对象，因此无法访问关联数据
> - 如果需要关联数据，使用 `selectinload()` + `load_only()` 组合
> - 如果只需要主表字段，使用 `with_entities()` 或 `load_only()`
    User.email
).filter(
    User.deleted_at == None
).order_by(
    User.created_at.desc()
).paginate(page=1, page_size=10)
```

## 大数据量分页

### 游标分页

对于大数据量，传统的 OFFSET 分页性能较差，可以使用游标分页：

```python
def cursor_pagination(last_id: int = 0, limit: int = 10):
    """游标分页：基于 ID 的分页"""
    return User.query.filter(
        User.id > last_id
    ).order_by(User.id.asc()).limit(limit).all()

# 使用
first_page = cursor_pagination(last_id=0, limit=10)
# 获取最后一条的 ID
last_id = first_page[-1].id if first_page else 0
# 下一页
next_page = cursor_pagination(last_id=last_id, limit=10)
```

### 基于时间的游标

```python
def time_cursor_pagination(last_time: datetime = None, limit: int = 10):
    """基于时间的游标分页"""
    query = User.query.order_by(User.created_at.desc())

    if last_time:
        query = query.filter(User.created_at < last_time)

    return query.limit(limit).all()
```

## 分页参数验证

### 使用 PaginationField

```python
from yweb.orm import PaginationField

# 创建分页参数
pagination = PaginationField(page=1, page_size=10)

# 自动验证最小值
pagination = PaginationField(page=0, page_size=0)
print(pagination.page)       # 1（自动修正为最小值 1）
print(pagination.page_size)  # 1（自动修正为最小值 1）

# 注意：PaginationField 不限制最大值
# 最大值限制由 paginate() 的 max_page_size 参数控制
```

### 设置最大页大小

```python
# 在 paginate 中限制
page_result = User.query.paginate(
    page=page,
    page_size=page_size,
    max_page_size=100  # 最大 100 条
)
```

## 常见问题

### Q1: 如何处理空结果？

```python
page_result = User.query.filter(
    User.username == "nonexistent"
).paginate(page=1, page_size=10)

# 空结果的 Page 对象
print(page_result.total_records)  # 0
print(page_result.rows)           # []
print(page_result.total_pages)    # 0
print(page_result.has_next)       # False
print(page_result.has_prev)       # False
```

### Q2: 如何获取总数而不获取数据？

```python
# 只获取总数
total = User.query.filter(User.is_active == True).count()
```

### Q3: 分页查询慢怎么办？

1. **添加索引**：为常用的过滤和排序字段添加索引
2. **只查询需要的字段**：使用 `load_only` 或 `with_entities`
3. **使用游标分页**：对于大数据量，避免使用 OFFSET
4. **优化查询条件**：避免在大表上使用 `LIKE '%xxx%'`

### Q4: 如何在分页中使用 Schema 转换？

```python
from pydantic import BaseModel as PydanticModel

class UserSchema(PydanticModel):
    id: int
    username: str
    email: str

    model_config = {"from_attributes": True}

# 在分页中使用
page_result = User.query.paginate(page=1, page_size=10, schema=UserSchema)
# rows 中的数据会自动转换为 UserSchema
```

## 下一步

- [06_批量操作](06_bulk_operations.md) - 学习批量操作
- [04_查询与过滤](04_query_and_filter.md) - 深入学习查询
