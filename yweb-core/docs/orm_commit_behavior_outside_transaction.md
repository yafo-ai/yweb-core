# ORM 框架事务外提交行为分析

## 一、问题场景

在**事务之外**使用模型的 `save()` 方法时，提交行为是怎样的？

```python
# 在事务之外
user.save()           # commit=False (默认)
order.save(True)      # commit=True
```

**问题**：这会提交几次？user 和 order 都会入库吗？

---

## 二、核心答案

### 答案：只提交 1 次

- ✅ **提交 1 次**（在 `order.save(True)` 时）
- ✅ **user 和 order 都会被提交**（因为它们在同一个 session 中）
- 🎯 SQLAlchemy 的 `session.commit()` 会提交 session 中的**所有待处理变更**

---

## 三、详细执行流程分析

### 第 1 步：`user.save()` - 不提交

```python
user = User(name="tom")
user.save()  # commit 参数默认为 False
```

**执行流程**：

```python
# core_model.py:181-194
def save(self, commit: bool = False):  # commit=False
    """保存对象（自动判断新增或更新）"""
    self.session.add(self)  # ✅ 添加到 session
    self.__is_commit(commit)  # 传入 False
    return self

# core_model.py:999-1009
def __is_commit(self, commit=False):
    if commit:  # ❌ False，不进入
        if self._should_suppress_commit():
            return
        self.session.commit()
    # 直接结束，不执行任何提交
```

**结果**：
- ✅ `user` 被添加到 session（处于 **pending** 状态）
- ❌ **没有调用 `session.commit()`**
- 📝 变更保存在 session 的内存中，未写入数据库

**Session 状态**：
```
session.new = [user]  # pending 对象列表
session.dirty = []    # 修改的对象列表
session.deleted = []  # 删除的对象列表
```

---

### 第 2 步：`order.save(True)` - 提交 1 次

```python
order = Order(user_id=user.id)
order.save(True)  # commit=True
```

**执行流程**：

```python
# core_model.py:181-194
def save(self, commit: bool = False):  # commit=True
    self.session.add(self)  # ✅ 添加到 session
    self.__is_commit(commit)  # 传入 True
    return self

# core_model.py:999-1009
def __is_commit(self, commit=False):
    if commit:  # ✅ True，进入
        if self._should_suppress_commit():  # 检查是否抑制
            return
        self.session.commit()  # 🔑 执行提交
```

**抑制检查**：

```python
# core_model.py:1023-1035
def _should_suppress_commit(self) -> bool:
    try:
        from .transaction import get_current_transaction
        tx = get_current_transaction()  # ❌ 返回 None（没有事务）
        if tx is not None and tx.should_suppress_commit():
            return True
    except ImportError:
        pass
    return False  # ✅ 返回 False（不抑制）
```

**结果**：
- ✅ `order` 被添加到 session
- ✅ **调用 `session.commit()`，提交 1 次**
- 🎯 **这次提交会同时提交 `user` 和 `order`**

**Session 状态变化**：
```
提交前：
session.new = [user, order]

提交后：
session.new = []  # 清空
# user 和 order 都已持久化到数据库
```

---

## 四、SQLAlchemy Session 的工作机制

### Session 是工作单元 (Unit of Work)

```python
session = db_manager.get_session()

# 所有操作都在同一个 session 中
user.save()    # session.add(user)  - user 在 session 中
order.save()   # session.add(order) - order 在 session 中

# 一次 commit 提交所有变更
session.commit()  # 同时提交 user 和 order
```

**关键特性**：
1. **累积变更**：session 会跟踪所有添加、修改、删除的对象
2. **统一提交**：`commit()` 一次性提交所有待处理的变更
3. **事务边界**：每次 `commit()` 是一个完整的数据库事务

### Session 状态图

```
初始状态：session 为空
    ↓
user.save()  → session 中有 1 个 pending 对象 (user)
    ↓
order.save(True)  → session 中有 2 个 pending 对象 (user, order)
    ↓
session.commit()  → 🔑 一次性提交所有对象到数据库
    ↓
结果：user 和 order 都被插入数据库
```

### 执行的 SQL

```sql
BEGIN;
INSERT INTO users (name) VALUES ('tom');      -- user 被提交
INSERT INTO orders (user_id) VALUES (1);      -- order 被提交
COMMIT;  -- 一次提交，两条 INSERT
```

---

## 五、Scoped Session 的影响

### 同一个请求中的 Session

```python
# 在同一个请求中
user = User(name="tom")
print(id(user.session))  # 例如：140234567890

order = Order(user_id=user.id)
print(id(order.session))  # 140234567890 (相同！)

# 它们使用的是同一个 scoped_session
```

**关键代码** (`core_model.py:165-177`):

```python
@property
def session(self) -> Session:
    """获取数据库 session"""
    if self._session is None:
        # 优先从 query 获取 session（支持测试环境）
        try:
            self._session = self.__class__.query.session
        except:
            from .db_session import db_manager
            self._session = db_manager.get_session()  # 🔑 同一个请求返回同一个 session
    return self._session
```

**Scoped Session 机制** (`db_session.py`):

```python
# DatabaseManager.init() 中
self._session_scope = scoped_session(self._session_maker, scopefunc=self._get_request_id)
#                                                          ↑ 基于请求 ID 的作用域
```

**作用域函数** (`DatabaseManager._get_request_id`):

```python
def _get_request_id(self) -> str:
    """获取当前请求ID

    优先使用中间件设置的请求ID，如果没有则使用 fallback ID。
    用于数据库 scoped_session 的作用域标识和日志追踪。
    """
    # 优先使用中间件的请求ID
    try:
        from yweb.middleware.request_id import request_id_var
        middleware_id = request_id_var.get()
        if middleware_id:
            return middleware_id
    except ImportError:
        pass

    # Fallback: 使用本地生成的ID
    fallback_id = _fallback_request_id.get()
    if not fallback_id:
        fallback_id = uuid4().hex[:8]
        _fallback_request_id.set(fallback_id)
    return fallback_id
```

**关键点**：
- 同一个请求 ID → 同一个 session 实例
- 不同请求 ID → 不同 session 实例
- 请求结束时调用 `session_scope.remove()` 清理

---

## 六、完整示例验证

### 示例 1：你的场景

```python
# 在事务之外
user = User(name="tom")
user.save()  # commit=False，只添加到 session

order = Order(user_id=user.id)
order.save(True)  # commit=True，触发提交

# 执行的 SQL：
# BEGIN;
# INSERT INTO users (name) VALUES ('tom');  -- user 被提交
# INSERT INTO orders (user_id) VALUES (1);  -- order 被提交
# COMMIT;  -- 一次提交，两条 INSERT
```

**结果**：
- ✅ 提交 **1 次**
- ✅ user 和 order **都被插入**数据库
- 🎯 这是 SQLAlchemy 的 **Unit of Work** 模式

---

### 示例 2：两次都 commit=True

```python
user = User(name="tom")
user.save(True)  # 第 1 次提交

order = Order(user_id=user.id)
order.save(True)  # 第 2 次提交
```

**执行的 SQL**：
```sql
-- 第 1 次提交
BEGIN;
INSERT INTO users (name) VALUES ('tom');
COMMIT;

-- 第 2 次提交
BEGIN;
INSERT INTO orders (user_id) VALUES (1);
COMMIT;
```

**结果**：
- ✅ 提交 **2 次**
- ⚠️ 如果 `order.save(True)` 失败，user 已经提交，无法回滚
- ⚠️ **数据不一致风险**

---

### 示例 3：都不提交

```python
user = User(name="tom")
user.save()  # commit=False

order = Order(user_id=user.id)
order.save()  # commit=False

# ⚠️ 没有任何提交！
# user 和 order 都在 session 中，但未写入数据库
```

**结果**：
- ❌ 提交 **0 次**
- ⚠️ 数据库中没有任何记录
- 📝 需要手动调用 `session.commit()` 或在请求结束时由 `get_db()` 提交

**FastAPI 中的自动提交** (`db_session.py:259-277`):

```python
def get_db():
    """FastAPI依赖项：获取数据库session"""
    db = db_manager.get_session()
    try:
        yield db
        db.commit()  # 🔑 请求结束时自动提交
    except Exception as e:
        db.rollback()
        raise e
```

**使用示例**：
```python
from fastapi import Depends
from yweb.orm import get_db

@app.post("/users")
def create_user(db: Session = Depends(get_db)):
    user = User(name="tom")
    user.save()  # commit=False
    order = Order(user_id=user.id)
    order.save()  # commit=False
    # 请求结束时，get_db() 会自动调用 db.commit()
    return user
```

---

### 示例 4：只提交第一个

```python
user = User(name="tom")
user.save(True)  # 第 1 次提交

order = Order(user_id=user.id)
order.save()  # commit=False，不提交
```

**执行的 SQL**：
```sql
BEGIN;
INSERT INTO users (name) VALUES ('tom');
COMMIT;

-- order 未提交，仍在 session 中
```

**结果**：
- ✅ 提交 **1 次**
- ✅ user 已入库
- ❌ order 未入库（除非后续有其他提交）

---

## 七、总结表格

| 场景 | user.save() | order.save() | 提交次数 | user 入库 | order 入库 | 说明 |
|------|-------------|--------------|---------|----------|-----------|------|
| `user.save()` + `order.save(True)` | commit=False | commit=True | **1 次** | ✅ | ✅ | 推荐：最后统一提交 |
| `user.save(True)` + `order.save(True)` | commit=True | commit=True | **2 次** | ✅ | ✅ | ⚠️ 有数据不一致风险 |
| `user.save()` + `order.save()` | commit=False | commit=False | **0 次** | ❌ | ❌ | 需要手动或自动提交 |
| `user.save(True)` + `order.save()` | commit=True | commit=False | **1 次** | ✅ | ❌ | order 未入库 |

---

## 八、风险提示

### 风险 1：部分提交

```python
user.save(True)  # ✅ 已提交
# 如果这里出错...
order.save(True)  # ❌ 未执行

# 结果：user 已入库，order 未入库，数据不一致！
```

**问题**：
- 无法回滚已提交的 user
- 数据库处于不一致状态

**解决方案**：使用事务

---

### 风险 2：忘记提交

```python
user.save()  # commit=False
order.save()  # commit=False
# 忘记调用 session.commit()

# 结果：数据库中没有任何记录
```

**问题**：
- 数据未持久化
- 请求结束后 session 清理，数据丢失

**解决方案**：
1. 使用 FastAPI 的 `Depends(get_db)`，自动提交
2. 手动调用 `session.commit()`
3. 使用事务管理器

---

### 风险 3：外键约束

```python
user.save()  # commit=False，user.id 未生成
order = Order(user_id=user.id)  # ⚠️ user.id 可能为 None
order.save(True)  # 提交时可能失败
```

**问题**：
- 如果 user.id 是自增主键，在提交前可能为 None
- order 的外键约束可能失败

**解决方案**：
```python
# 方式 1：先提交 user
user.save(True)
order = Order(user_id=user.id)
order.save(True)

# 方式 2：使用 flush
user.save()
session.flush()  # 刷新到数据库，生成 ID，但不提交
order = Order(user_id=user.id)
order.save(True)  # 同时提交 user 和order

# 方式 3：使用事务（推荐）
with tm.transaction() as tx:
    user.save()
    tx.session.flush()  # 生成 ID
    order = Order(user_id=user.id)
    order.save()
```

---

## 九、推荐做法

### ✅ 推荐：使用事务

```python
from yweb.orm import transaction_manager as tm

with tm.transaction() as tx:
    user.save(True)   # 被抑制，不真正提交
    order.save(True)  # 被抑制，不真正提交
    # 统一在这里提交，要么全成功，要么全失败
```

**优势**：
- ✅ 原子性：要么全成功，要么全失败
- ✅ 一致性：数据库状态始终一致
- ✅ 隔离性：事务之间互不干扰
- ✅ 持久性：提交后数据永久保存

---

### ✅ 推荐：使用 FastAPI 依赖注入

```python
from fastapi import Depends
from yweb.orm import get_db

@app.post("/users")
def create_user(db: Session = Depends(get_db)):
    user = User(name="tom")
    user.save()  # commit=False

    order = Order(user_id=user.id)
    order.save()  # commit=False

    # 请求结束时自动提交
    return {"user_id": user.id, "order_id": order.id}
```

**优势**：
- ✅ 自动提交：请求成功时自动提交
- ✅ 自动回滚：请求失败时自动回滚
- ✅ 自动清理：请求结束时自动清理 session

---

### ❌ 不推荐：多次提交

```python
# ❌ 不推荐
user.save(True)   # 第 1 次提交
profile.save(True)  # 第 2 次提交
order.save(True)  # 第 3 次提交
# 如果 order 失败，user 和 profile 已提交，无法回滚
```

---

### ❌ 不推荐：忘记提交

```python
# ❌ 不推荐
user.save()  # commit=False
order.save()  # commit=False
# 忘记提交，数据丢失
```

---

## 十、核心原理总结

### SQLAlchemy Session 的 Unit of Work 模式

```
Session 是一个工作单元，跟踪所有变更：

1. 添加对象：session.add(obj) → obj 进入 pending 状态
2. 修改对象：obj.name = "new" → obj 进入 dirty 状态
3. 删除对象：session.delete(obj) → obj 进入 deleted 状态
4. 提交变更：session.commit() → 一次性提交所有变更

关键特性：
- 累积变更：所有操作都在内存中累积
- 统一提交：commit() 一次性提交所有变更
- 事务边界：每次 commit() 是一个完整的数据库事务
```

### Scoped Session 的作用域

```
Scoped Session 基于作用域函数返回同一个 session：

1. 同一个请求 ID → 同一个 session 实例
2. 不同请求 ID → 不同 session 实例
3. 请求结束时 → 调用 session_scope.remove() 清理

关键代码（DatabaseManager.init 中）：
self._session_scope = scoped_session(self._session_maker, scopefunc=self._get_request_id)
```

### 提交行为总结

```
在事务之外：

1. save(commit=False)：只添加到 session，不提交
2. save(commit=True)：添加到 session 并提交所有变更
3. session.commit()：提交 session 中的所有待处理变更

关键点：
- 一次 commit() 提交所有变更
- 多次 commit() 会产生多个数据库事务
- 使用事务管理器可以避免部分提交的风险
```

---

## 十一、最终答案

### 你的问题

```python
user.save()        # commit=False
order.save(True)   # commit=True
```

### 答案

- ✅ **提交 1 次**（在 `order.save(True)` 时）
- ✅ **user 和 order 都会被提交**（因为它们在同一个 session 中）
- 🎯 SQLAlchemy 的 `session.commit()` 会提交 session 中的**所有待处理变更**

### 原理

这就是 SQLAlchemy 的 **Unit of Work** 模式：
- Session 是一个工作单元，跟踪所有变更
- `commit()` 一次性提交所有变更
- 不管调用多少次 `add()`，只要调用一次 `commit()`，所有变更都会被提交

---

**文档生成时间**: 2026-01-21
**分析范围**: yweb-core ORM 框架事务外提交行为
**分析方法**: 代码追踪 + SQLAlchemy 原理分析
