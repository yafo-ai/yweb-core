# 04. 查询与过滤

## 概述

YWeb ORM 提供了强大的查询功能，支持：

- Query 对象查询
- Select 语句查询
- 条件过滤
- 排序和限制
- 关联查询

## 获取 Session

本文档中的 `session` 变量通过以下方式获取：

```python
from yweb.orm import db_manager

# 获取当前请求的 session
session = db_manager.get_session()
```

> **推荐**：在大多数情况下，直接使用 `User.query` 即可，无需显式获取 session。

## Query 对象

### 基本查询

```python
# 获取所有记录
users = User.query.all()

# 获取第一条
user = User.query.first()

# 获取数量
count = User.query.count()

# 检查是否存在
exists = User.query.filter(User.username == "tom").first() is not None
```

### 条件过滤

```python
# 等于
users = User.query.filter(User.is_active == True).all()

# 不等于
users = User.query.filter(User.status != "deleted").all()

# 大于/小于
users = User.query.filter(User.age > 18).all()
users = User.query.filter(User.age >= 18).all()
users = User.query.filter(User.age < 60).all()
users = User.query.filter(User.age <= 60).all()

# 空值检查
users = User.query.filter(User.email.is_(None)).all()
users = User.query.filter(User.email.isnot(None)).all()
```

### 字符串匹配

```python
# LIKE 查询
users = User.query.filter(User.username.like("%tom%")).all()

# ILIKE 查询（不区分大小写）
users = User.query.filter(User.username.ilike("%TOM%")).all()

# 以...开头
users = User.query.filter(User.username.startswith("tom")).all()

# 以...结尾
users = User.query.filter(User.email.endswith("@example.com")).all()

# 包含
users = User.query.filter(User.username.contains("tom")).all()
```

### IN 查询

```python
# IN
users = User.query.filter(User.id.in_([1, 2, 3])).all()

# NOT IN
users = User.query.filter(User.id.not_in([1, 2, 3])).all()

# 使用子查询
subquery = Department.query.filter(
    Department.is_active == True
).with_entities(Department.id)
users = User.query.filter(User.department_id.in_(subquery)).all()
```

### 逻辑组合

```python
from sqlalchemy import and_, or_, not_

# AND（默认）
users = User.query.filter(
    User.is_active == True,
    User.age >= 18
).all()

# 显式 AND
users = User.query.filter(
    and_(
        User.is_active == True,
        User.age >= 18
    )
).all()

# OR
users = User.query.filter(
    or_(
        User.role == "admin",
        User.role == "manager"
    )
).all()

# NOT
users = User.query.filter(
    not_(User.is_active == False)
).all()

# 复杂组合
users = User.query.filter(
    and_(
        User.is_active == True,
        or_(
            User.role == "admin",
            and_(
                User.role == "user",
                User.age >= 18
            )
        )
    )
).all()
```

### 链式调用

```python
# 多个 filter 等同于 AND
users = User.query\
    .filter(User.is_active == True)\
    .filter(User.age >= 18)\
    .filter(User.department_id == 1)\
    .all()
```

## 排序

```python
# 升序
users = User.query.order_by(User.created_at.asc()).all()

# 降序
users = User.query.order_by(User.created_at.desc()).all()

# 多字段排序
users = User.query.order_by(
    User.is_active.desc(),
    User.created_at.desc()
).all()

# 空值排序
from sqlalchemy import nullsfirst, nullslast
users = User.query.order_by(nullslast(User.updated_at.desc())).all()
```

## 限制和偏移

```python
# 限制数量
users = User.query.limit(10).all()

# 偏移
users = User.query.offset(20).all()

# 组合（分页）
users = User.query.offset(20).limit(10).all()

# 获取前 N 条
users = User.query.order_by(User.created_at.desc()).limit(5).all()
```

## Select 语句查询

### 基本用法

```python
from sqlalchemy import select

# 创建 select 语句
stmt = select(User)
users = session.execute(stmt).scalars().all()

# 带条件
stmt = select(User).where(User.is_active == True)
users = session.execute(stmt).scalars().all()
```

### 复杂查询

```python
from sqlalchemy import select, and_, or_

stmt = select(User).where(
    and_(
        User.is_active == True,
        or_(
            User.role == "admin",
            User.role == "manager"
        )
    )
).order_by(User.created_at.desc())

users = session.execute(stmt).scalars().all()
```

### 选择特定字段

```python
from sqlalchemy import select

# 选择特定字段
stmt = select(User.id, User.username, User.email)
results = session.execute(stmt).all()

for id, username, email in results:
    print(f"{id}: {username} <{email}>")
```

## 关联查询

### 预加载（Eager Loading）

```python
from sqlalchemy.orm import selectinload, joinedload

# selectinload：分两次查询（推荐用于一对多）
users = User.query.options(
    selectinload(User.roles)
).all()

# joinedload：JOIN 查询（推荐用于多对一）
users = User.query.options(
    joinedload(User.department)
).all()

# 多个关联
users = User.query.options(
    selectinload(User.roles),
    joinedload(User.department),
    selectinload(User.posts)
).all()
```

### 嵌套预加载

```python
from sqlalchemy.orm import selectinload

# 用户 -> 角色 -> 权限
users = User.query.options(
    selectinload(User.roles).selectinload(Role.permissions)
).all()
```

### 限制加载字段

```python
from sqlalchemy.orm import selectinload, load_only

# 只加载关联对象的特定字段
users = User.query.options(
    selectinload(User.roles).load_only(Role.id, Role.name)
).all()
```

### 延迟加载（Lazy Loading）

```python
# 默认是延迟加载
user = User.query.first()
# 访问 roles 时才会查询
for role in user.roles:  # 触发查询
    print(role.name)
```

## 聚合查询

```python
from sqlalchemy import func

# 计数
count = session.query(func.count(User.id)).scalar()

# 求和
total = session.query(func.sum(Order.amount)).scalar()

# 平均值
avg = session.query(func.avg(User.age)).scalar()

# 最大/最小值
max_age = session.query(func.max(User.age)).scalar()
min_age = session.query(func.min(User.age)).scalar()

# 分组
from sqlalchemy import func
results = session.query(
    User.department_id,
    func.count(User.id)
).group_by(User.department_id).all()
```

## 子查询

```python
from sqlalchemy import select

# 子查询
subquery = select(Department.id).where(
    Department.is_active == True
).scalar_subquery()

users = User.query.filter(
    User.department_id.in_(subquery)
).all()
```

## 动态查询构建

```python
def search_users(
    username: str = None,
    email: str = None,
    is_active: bool = None,
    department_id: int = None,
    min_age: int = None,
    max_age: int = None
):
    query = User.query

    if username:
        query = query.filter(User.username.ilike(f"%{username}%"))

    if email:
        query = query.filter(User.email.ilike(f"%{email}%"))

    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    if department_id:
        query = query.filter(User.department_id == department_id)

    if min_age:
        query = query.filter(User.age >= min_age)

    if max_age:
        query = query.filter(User.age <= max_age)

    return query.order_by(User.created_at.desc()).all()
```

## 原生 SQL

```python
from sqlalchemy import text

# 执行原生 SQL
result = session.execute(
    text("SELECT * FROM user WHERE is_active = :active"),
    {"active": True}
)
users = result.fetchall()

# 使用 ORM 映射
users = session.query(User).from_statement(
    text("SELECT * FROM user WHERE is_active = :active")
).params(active=True).all()
```

## 最佳实践

### 1. 使用 query 属性

```python
# 推荐
users = User.query.filter(User.is_active == True).all()

# 不推荐
users = session.query(User).filter(User.is_active == True).all()
```

### 2. 避免 N+1 问题

```python
# 不推荐：N+1 查询
users = User.query.all()
for user in users:
    print(user.department.name)  # 每次循环都查询

# 推荐：预加载
users = User.query.options(
    joinedload(User.department)
).all()
for user in users:
    print(user.department.name)  # 不会额外查询
```

### 3. 只查询需要的字段

```python
# 推荐：只查询需要的字段
users = User.query.with_entities(
    User.id, User.username
).all()

# 或使用 load_only
from sqlalchemy.orm import load_only
users = User.query.options(
    load_only(User.id, User.username)
).all()
```

### 4. 使用索引字段过滤

```python
# 推荐：使用索引字段
users = User.query.filter(User.id == 1).first()

# 避免：在非索引字段上使用 LIKE
users = User.query.filter(User.bio.like("%keyword%")).all()
```

## 下一步

- [05_分页查询](05_pagination.md) - 学习分页功能
- [06_批量操作](06_bulk_operations.md) - 学习批量操作
