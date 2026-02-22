# 06. 批量操作

## 概述

YWeb ORM 提供了高效的批量操作方法，用于处理大量数据的更新和删除。

## 批量添加

### save_all() 方法（推荐）

批量保存对象到数据库。对于新对象和已存在的对象都是安全的（SQLAlchemy 的 `session.add()` 是幂等的）。

```python
# 创建多个对象
users = [
    User(username="user1", email="user1@example.com"),
    User(username="user2", email="user2@example.com"),
    User(username="user3", email="user3@example.com"),
]

# 批量保存（不提交）
User.save_all(users)

# 批量保存并提交
User.save_all(users, commit=True)

# 所有对象都有 ID
for user in users:
    print(f"{user.username}: {user.id}")

# 也可以保存已存在的对象（更新场景）
existing_users = User.query.filter(User.is_active == True).all()
for user in existing_users:
    user.status = "verified"
User.save_all(existing_users, commit=True)
```

### add_all() 方法（已废弃）

> ⚠️ **已废弃**：建议使用 `save_all()` 方法，`add_all()` 将在未来版本中移除。

```python
# 已废弃的用法
User.add_all(users, commit=True)

# 推荐用法
User.save_all(users, commit=True)
```

### 大批量数据

```python
# 分批处理大量数据
BATCH_SIZE = 1000

all_users = [User(username=f"user{i}") for i in range(10000)]

for i in range(0, len(all_users), BATCH_SIZE):
    batch = all_users[i:i + BATCH_SIZE]
    User.save_all(batch, commit=True)
    print(f"已处理 {i + len(batch)} 条")
```

### 性能警告：事务中避免循环 save(True)

在 `@transactional` 中循环调用 `save(True)` 会导致严重性能问题：

```python
# ❌ 糟糕：每次 save(True) 都会 flush，1000 次网络往返
@tm.transactional()
def batch_import_bad(users_data):
    for data in users_data:  # 1000 条
        user = User(**data)
        user.save(True)  # 每次都 flush！约 5-10 秒

# ✅ 好：使用 save() 或 save_all()
@tm.transactional()
def batch_import_good(users_data):
    users = [User(**data) for data in users_data]
    User.save_all(users)  # 只 add，不 flush
    # 事务结束时自动 commit，约 0.1-0.5 秒
```

| 方式 | 1000 条数据 | 说明 |
|-----|------------|------|
| 循环 `save(True)` | ~5-10 秒 | 1000 次 flush |
| `save_all()` | ~0.1-0.5 秒 | 1 次 commit |

### refresh_all() 批量刷新（特殊场景）

从数据库重新加载对象状态。**仅在特殊场景下使用**，大多数情况应使用单次提交模式避免需要 refresh。

```python
# 批量刷新对象
roles = [Role(name="admin"), Role(name="editor")]
Role.save_all(roles, commit=True)
Role.refresh_all(roles)  # 刷新所有对象

# 只刷新特定属性
Role.refresh_all(roles, ['name', 'permissions'])
```

> ⚠️ **性能警告**：`refresh_all(N个对象)` = N 次 SELECT 查询。
> 批量操作时请谨慎使用，优先考虑单次提交模式。

**推荐：使用单次提交模式避免 refresh_all**

```python
# ✅ 推荐：单次提交，不需要 refresh_all
roles = [Role(name="admin"), Role(name="editor")]
user = User(name="tom")
user.roles.extend(roles)  # 都是新对象，直接关联
session.add_all(roles + [user])
session.commit()

# ❌ 不推荐：需要 refresh_all
Role.save_all(roles, commit=True)
Role.refresh_all(roles)  # 额外的 N 次查询
user.roles.extend(roles)
user.save(commit=True)
```

## 批量更新

### bulk_update() 方法

根据条件批量更新：

```python
# 将所有未激活用户设为激活
count = User.bulk_update(
    filters={'is_active': False},
    values={'is_active': True}
)
print(f"更新了 {count} 条记录")

# 多条件更新
count = User.bulk_update(
    filters={
        'department_id': 1,
        'is_active': True
    },
    values={
        'department_id': 2,
        'updated_at': datetime.now()
    }
)
```

### bulk_update_by_ids() 方法

根据 ID 列表批量更新：

```python
# 更新指定 ID 的记录
count = User.bulk_update_by_ids(
    ids=[1, 2, 3, 4, 5],
    values={'is_active': False}
)
print(f"更新了 {count} 条记录")
```

### 使用原生 SQL

```python
from sqlalchemy import update

# 更复杂的批量更新
stmt = update(User).where(
    User.created_at < datetime(2024, 1, 1)
).values(
    status='archived'
)
result = session.execute(stmt)
session.commit()
print(f"更新了 {result.rowcount} 条记录")
```

## 批量删除

### delete_all() 方法

对已查询出的对象列表进行批量删除：

```python
# 查询出需要删除的对象
inactive_users = User.query.filter(User.is_active == False).all()

# 批量删除（不提交）
User.delete_all(inactive_users)

# 批量删除并提交
User.delete_all(inactive_users, commit=True)
```

> **注意**：
> - `delete_all()` 会对每个对象调用 `session.delete()`
> - 如果是 BaseModel（继承 SimpleSoftDeleteMixin），会触发软删除
> - 如果是 CoreModel，会执行物理删除
> - 会触发 ORM 事件（如 `before_delete`）

### bulk_delete() 方法（物理删除）

根据条件直接执行 SQL DELETE，不加载对象到内存：

```python
# 根据条件批量删除
count = User.bulk_delete(filters={'is_active': False})
print(f"删除了 {count} 条记录")
```

### bulk_delete_by_ids() 方法

```python
# 根据 ID 列表删除
count = User.bulk_delete_by_ids(ids=[1, 2, 3])
print(f"删除了 {count} 条记录")
```

### delete_all() vs bulk_delete() 的区别

| 特性 | delete_all() | bulk_delete() |
|------|-------------|---------------|
| 输入 | 对象列表 | 条件字典 |
| 触发事件 | ✅ 触发 ORM 事件 | ❌ 不触发 |
| 软删除支持 | ✅ 支持（BaseModel） | ❌ 物理删除 |
| 性能 | 需要先查询对象 | 直接执行 SQL |
| 适用场景 | 需要触发事件/软删除 | 大批量物理删除 |

## 批量软删除

### bulk_soft_delete() 方法

```python
# 根据条件批量软删除
count = User.bulk_soft_delete(filters={'is_active': False})
print(f"软删除了 {count} 条记录")

# 多条件软删除
count = User.bulk_soft_delete(filters={
    'department_id': 1,
    'status': 'inactive'
})
```

### bulk_soft_delete_by_ids() 方法

```python
# 根据 ID 列表软删除
count = User.bulk_soft_delete_by_ids(ids=[1, 2, 3, 4, 5])
print(f"软删除了 {count} 条记录")
```

## 性能优化

### 使用 bulk_insert_mappings

对于超大批量插入，使用 SQLAlchemy 的 bulk 方法：

```python
from sqlalchemy.orm import Session

# 准备数据（字典列表）
user_data = [
    {"username": f"user{i}", "email": f"user{i}@example.com"}
    for i in range(100000)
]

# 批量插入
session.bulk_insert_mappings(User, user_data)
session.commit()
```

### 使用 bulk_update_mappings

```python
# 准备更新数据（必须包含主键）
update_data = [
    {"id": 1, "is_active": True},
    {"id": 2, "is_active": True},
    {"id": 3, "is_active": False},
]

session.bulk_update_mappings(User, update_data)
session.commit()
```

### 禁用自动刷新

```python
# 大批量操作时禁用自动刷新
with session.no_autoflush:
    for i in range(10000):
        user = User(username=f"user{i}")
        session.add(user)

    session.commit()
```

### 分批提交

```python
BATCH_SIZE = 1000

for i, data in enumerate(large_dataset):
    user = User(**data)
    session.add(user)

    if (i + 1) % BATCH_SIZE == 0:
        session.commit()
        print(f"已提交 {i + 1} 条")

# 提交剩余的
session.commit()
```

## 在 FastAPI 中使用

### 批量创建

```python
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List

class UserCreate(BaseModel):
    username: str
    email: str

@app.post("/users/batch")
def create_users_batch(users: List[UserCreate]):
    user_objects = [User(**u.model_dump()) for u in users]  # Pydantic v2 使用 model_dump()
    User.save_all(user_objects, commit=True)
    return OK({"created": len(user_objects)})
```

### 批量更新

```python
class BulkUpdateRequest(BaseModel):
    ids: List[int]
    values: dict

@app.put("/users/batch")
def update_users_batch(request: BulkUpdateRequest):
    count = User.bulk_update_by_ids(
        ids=request.ids,
        values=request.values
    )
    return OK({"updated": count})
```

### 批量删除

```python
@app.delete("/users/batch")
def delete_users_batch(ids: List[int]):
    count = User.bulk_soft_delete_by_ids(ids=ids)
    return OK({"deleted": count})
```

## 事务处理

### 批量操作的事务

```python
from yweb.orm import db_manager

session = db_manager.get_session()

try:
    # 批量更新用户
    User.bulk_update(
        filters={'department_id': 1},
        values={'department_id': 2}
    )

    # 批量更新部门
    Department.bulk_update(
        filters={'id': 1},
        values={'is_active': False}
    )

    session.commit()
except Exception as e:
    session.rollback()
    raise
```

### 部分失败处理

```python
def batch_create_with_validation(users_data: list):
    """批量创建，跳过无效数据"""
    created = []
    failed = []

    for data in users_data:
        try:
            user = User(**data)
            user.add(True)
            created.append(user)
        except Exception as e:
            failed.append({"data": data, "error": str(e)})

    return {
        "created": len(created),
        "failed": len(failed),
        "errors": failed
    }
```

## 最佳实践

### 1. 选择合适的批量大小

```python
# 根据数据量选择批量大小
if total_count < 1000:
    BATCH_SIZE = 100
elif total_count < 10000:
    BATCH_SIZE = 500
else:
    BATCH_SIZE = 1000
```

### 2. 使用进度反馈

```python
from tqdm import tqdm

users = [User(username=f"user{i}") for i in range(10000)]

for i in tqdm(range(0, len(users), BATCH_SIZE)):
    batch = users[i:i + BATCH_SIZE]
    User.save_all(batch, commit=True)
```

### 3. 避免 N+1 问题

```python
# 不推荐：循环中单独更新
for user_id in user_ids:
    user = User.get(user_id)
    user.is_active = True
    user.update(True)

# 推荐：批量更新
User.bulk_update_by_ids(
    ids=user_ids,
    values={'is_active': True}
)
```

### 4. 记录操作日志

```python
import logging

logger = logging.getLogger(__name__)

def bulk_update_with_logging(filters, values):
    count = User.bulk_update(filters=filters, values=values)
    logger.info(f"批量更新: filters={filters}, values={values}, count={count}")
    return count
```

## 常见问题

### Q1: 批量操作会触发事件吗？

批量操作（如 `bulk_update`）直接执行 SQL，不会触发 SQLAlchemy 的 ORM 事件（如 `before_update`）。如果需要触发事件，应该逐条更新。

### Q2: 批量软删除会触发级联吗？

`bulk_soft_delete` 不会触发级联软删除。如果需要级联，应该逐条调用 `delete()` 方法。

### Q3: 如何处理批量操作的错误？

```python
try:
    User.bulk_update(filters, values)
    session.commit()
except Exception as e:
    session.rollback()
    logger.error(f"批量更新失败: {e}")
    raise
```

### Q4: 批量操作的性能如何？

批量操作比逐条操作快很多，因为：
1. 减少了数据库往返次数
2. 减少了 ORM 对象创建开销
3. 数据库可以优化批量操作

## 下一步

- [07_软删除](07_soft_delete.md) - 了解软删除机制
- [11_事务管理](11_transaction.md) - 学习事务控制
