# 09. 版本控制（乐观锁）

## 概述

YWeb ORM 通过 `ver` 字段实现乐观锁机制，用于处理并发更新冲突。

## 工作原理

1. 每条记录都有一个 `ver` 字段，初始值为 1
2. 每次更新时，`ver` 自动递增
3. 更新时会检查 `ver` 是否与数据库中的值一致
4. 如果不一致，说明记录已被其他事务修改，抛出 `StaleDataError`

## 基本使用

### 版本号自动递增

```python
# 创建记录
user = User(username="tom")
user.add(True)
print(user.ver)  # 1

# 第一次更新
user.name = "Tom"
user.update(True)
print(user.ver)  # 2

# 第二次更新
user.email = "tom@example.com"
user.update(True)
print(user.ver)  # 3
```

### 无变更不递增

```python
user = User.get(1)
initial_ver = user.ver

# 不做任何修改，直接 update
user.update(True)

# 版本号不变
assert user.ver == initial_ver

# 设置相同的值
user.name = user.name  # 相同的值
user.update(True)

# 版本号仍然不变
assert user.ver == initial_ver
```

## 并发冲突检测

### 冲突场景

```python
from sqlalchemy.orm.exc import StaleDataError

# 会话1：获取用户
user1 = User.get(1)

# 会话2：获取同一用户（模拟另一个请求）
user2 = session2.query(User).filter_by(id=1).first()

# 会话1：更新并提交
user1.name = "Name from Session 1"
user1.update(True)  # 成功，ver: 1 -> 2

# 会话2：尝试更新（此时 user2.ver 还是 1）
user2.name = "Name from Session 2"
try:
    user2.update(True)  # 失败！
except StaleDataError:
    print("并发冲突：记录已被其他事务修改")
    session2.rollback()
```

### 处理冲突

```python
from sqlalchemy.orm.exc import StaleDataError

def update_user(user_id: int, data: dict):
    """更新用户，处理并发冲突"""
    max_retries = 3

    for attempt in range(max_retries):
        try:
            user = User.get(user_id)
            if not user:
                return {"error": "用户不存在"}

            user.update_properties(**data)
            user.update(True)
            return {"success": True, "user": user}

        except StaleDataError:
            session.rollback()
            if attempt < max_retries - 1:
                continue  # 重试
            return {"error": "更新失败，请刷新后重试"}
```

### 刷新数据后重试

```python
from sqlalchemy.orm.exc import StaleDataError

user = User.get(1)

# 模拟其他事务修改了数据
# ...

user.name = "New Name"
try:
    user.update(True)
except StaleDataError:
    # 刷新获取最新数据
    session.refresh(user)
    print(f"最新版本: {user.ver}")

    # 重新修改并保存
    user.name = "New Name"
    user.update(True)
```

## 在 FastAPI 中使用

### 基本示例

```python
from fastapi import FastAPI, HTTPException
from sqlalchemy.orm.exc import StaleDataError

app = FastAPI()

@app.put("/users/{user_id}")
def update_user(user_id: int, data: dict):
    user = User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    try:
        user.update_properties(**data)
        user.update(True)
        return OK(user)
    except StaleDataError:
        raise HTTPException(
            status_code=409,
            detail="数据已被修改，请刷新后重试"
        )
```

### 带版本号的更新

```python
from pydantic import BaseModel

class UserUpdate(BaseModel):
    name: str
    email: str
    ver: int  # 客户端传入当前版本号

@app.put("/users/{user_id}")
def update_user(user_id: int, data: UserUpdate):
    user = User.get(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")

    # 检查版本号
    if user.ver != data.ver:
        raise HTTPException(
            status_code=409,
            detail=f"数据已被修改（当前版本: {user.ver}），请刷新后重试"
        )

    try:
        user.name = data.name
        user.email = data.email
        user.update(True)
        return OK(user)
    except StaleDataError:
        raise HTTPException(status_code=409, detail="并发冲突")
```

## 事务中的版本控制

### 多次更新

```python
user = User.get(1)
print(user.ver)  # 1

# 第一次更新（不提交）
user.name = "Update 1"
user.update()

# 第二次更新（不提交）
user.email = "update1@example.com"
user.update()

# 统一提交
session.commit()

# 版本号只增加一次
print(user.ver)  # 2
```

### 回滚不影响版本号

```python
user = User.get(1)
original_ver = user.ver

# 更新但不提交
user.name = "New Name"
user.update()

# 回滚
session.rollback()

# 重新查询
user = User.get(1)
assert user.ver == original_ver  # 版本号不变
```

## 跳过版本检查

在某些场景下，可能需要跳过版本检查：

```python
from sqlalchemy import update

# 使用原生 UPDATE 语句（跳过乐观锁）
stmt = update(User).where(User.id == 1).values(name="New Name")
session.execute(stmt)
session.commit()
```

> **警告**：跳过版本检查可能导致数据不一致，请谨慎使用。

## 最佳实践

### 1. 始终处理 StaleDataError

```python
from sqlalchemy.orm.exc import StaleDataError

try:
    user.update(True)
except StaleDataError:
    # 必须处理这个异常
    session.rollback()
    # 通知用户或重试
```

### 2. 在 API 响应中返回版本号

```python
@app.get("/users/{user_id}")
def get_user(user_id: int):
    user = User.get(user_id)
    return {
        "id": user.id,
        "name": user.name,
        "ver": user.ver  # 返回版本号
    }
```

### 3. 客户端传入版本号

```python
# 客户端请求
{
    "name": "New Name",
    "ver": 5  # 客户端当前看到的版本号
}

# 服务端验证
if user.ver != request.ver:
    return {"error": "数据已过期"}
```

### 4. 合理设置重试次数

```python
MAX_RETRIES = 3

for attempt in range(MAX_RETRIES):
    try:
        # 更新操作
        break
    except StaleDataError:
        if attempt == MAX_RETRIES - 1:
            raise
        session.rollback()
        continue
```

## 常见问题

### Q1: 为什么版本号没有递增？

可能原因：
1. 没有实际的数据变更
2. 设置了相同的值
3. 事务被回滚了

### Q2: 如何查看当前版本号？

```python
user = User.get(1)
print(user.ver)
```

### Q3: 版本号会溢出吗？

`ver` 字段是 Integer 类型，理论上可以达到很大的值。在实际应用中，很少会遇到溢出问题。

### Q4: 软删除会增加版本号吗？

是的，软删除也是一种更新操作，会增加版本号。

## 下一步

- [10_历史记录](10_history.md) - 了解版本历史功能
- [11_事务管理](11_transaction.md) - 学习事务控制
