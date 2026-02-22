# ORM 框架提交抑制机制 (Commit Suppression) 详解

## 一、核心设计思想

### 问题场景

```python
with tm.transaction() as tx:
    user.save(commit=True)  # ⚠️ 如果这里真的提交了
    profile.save(commit=True)  # ⚠️ 这里又提交了
    # 如果后面出错，前面的提交无法回滚！
```

### 解决方案

在事务上下文中，自动忽略所有 `commit=True` 参数，由事务管理器统一控制提交时机。

---

## 二、实现机制的完整调用链

### 调用链路图

```
用户代码
  ↓
user.save(commit=True)
  ↓
CoreModel.__is_commit(commit=True)  [core_model.py:999-1009]
  ↓
self._should_suppress_commit()  [core_model.py:1023-1035]
  ↓
get_current_transaction()  [manager.py:39-51]
  ↓
_current_transaction.get()  [ContextVar 获取当前事务]
  ↓
tx.should_suppress_commit()  [context.py:415-420]
  ↓
检查: self.is_active and self.suppress_commit
  ↓
返回 True → commit 被抑制 ✅
返回 False → 正常执行 commit
```

---

## 三、关键代码分析

### 第 1 层：模型层拦截

**文件**: `yweb/orm/core_model.py`

```python
def __is_commit(self, commit=False):
    """实例方法：根据参数决定是否提交

    当在事务上下文中且启用了提交抑制时，commit=True 会被忽略，
    但会自动执行 flush 以获取自动生成的字段（id, created_at 等）。
    """
    if commit:
        # 🔑 关键：先检查是否应该抑制
        if self._should_suppress_commit():
            # 🔑 被抑制时，自动 flush 以获取自动生成字段
            self.session.flush()
            self.session.refresh(self)
            return  # 不执行 commit，由事务管理器统一控制
        self.session.commit()  # 只有不抑制时才真正提交
```

**作用**：
- 所有模型的 CRUD 方法 (`save()`, `add()`, `delete()`, `update()`) 都会调用这个方法
- 在真正执行 `session.commit()` 之前，先检查是否应该抑制
- **新增**：当 commit 被抑制时，会自动执行 `flush()` + `refresh()` 以获取自动生成的字段

**调用位置**：
```python
def save(self, commit: bool = False):
    self.session.add(self)
    self.__is_commit(commit)  # 🔑 在这里调用
    return self

def delete(self, commit: bool = False):
    self.session.delete(self)
    self.__is_commit(commit)  # 🔑 在这里调用
```

**为什么需要自动 flush？**

在事务中创建新对象后，通常需要立即访问自动生成的字段（如 `id`、`created_at`）：

```python
@tm.transactional()
def create_user(data):
    user = User(**data)
    user.save(True)  # commit 被抑制
    
    # 问题：如果不 flush，user.id 仍然是 None
    # 解决：__is_commit 在抑制 commit 时自动 flush
    print(user.id)  # ✅ 现在有值了
    return user
```

---

### 第 2 层：抑制检查逻辑

**文件**: `yweb/orm/core_model.py:1023-1035`

```python
def _should_suppress_commit(self) -> bool:
    """检查是否应该抑制提交（实例方法）"""
    try:
        from .transaction import get_current_transaction
        tx = get_current_transaction()  # 🔑 获取当前事务上下文
        if tx is not None and tx.should_suppress_commit():
            from yweb.log import get_logger
            logger = get_logger("orm.transaction")
            logger.debug("commit=True 被事务上下文抑制")
            return True  # ✅ 应该抑制
    except ImportError:
        pass  # 如果事务模块未导入，不抑制
    return False  # ❌ 不抑制
```

**关键点**：
1. **动态导入**：使用 `from .transaction import get_current_transaction` 避免循环依赖
2. **获取当前事务**：通过 `get_current_transaction()` 获取当前线程/协程的事务上下文
3. **委托判断**：调用事务上下文的 `should_suppress_commit()` 方法
4. **日志记录**：当抑制发生时，输出 debug 日志

**类方法版本** (`core_model.py:1037-1050`):
```python
@classmethod
def _cls_should_suppress_commit(cls) -> bool:
    """检查是否应该抑制提交（类方法）"""
    try:
        from .transaction import get_current_transaction
        tx = get_current_transaction()
        if tx is not None and tx.should_suppress_commit():
            from yweb.log import get_logger
            logger = get_logger("orm.transaction")
            logger.debug("commit=True 被事务上下文抑制")
            return True
    except ImportError:
        pass
    return False
```

---

### 第 3 层：获取当前事务

**文件**: `yweb/orm/transaction/manager.py:33-51`

```python
# 全局 ContextVar，线程/协程安全
_current_transaction: ContextVar[Optional[TransactionContext]] = ContextVar(
    '_current_transaction', default=None
)

def get_current_transaction() -> Optional[TransactionContext]:
    """获取当前事务上下文

    Returns:
        当前的事务上下文，如果不在事务中则返回 None

    使用示例:
        tx = get_current_transaction()
        if tx and tx.is_active:
            # 在事务中
            pass
    """
    return _current_transaction.get()  # 🔑 从 ContextVar 获取
```

**关键技术**：
- **ContextVar**：Python 3.7+ 的上下文变量，线程和协程隔离
- **每个请求/协程独立**：不同请求的事务互不干扰
- **默认值 None**：如果没有事务，返回 None

---

### 第 4 层：事务上下文判断

**文件**: `yweb/orm/transaction/context.py:415-420`

```python
def should_suppress_commit(self) -> bool:
    """检查是否应该抑制提交

    用于 CoreModel 中判断 commit=True 是否应该被忽略
    """
    return self.is_active and self.suppress_commit
    #      ↑ 事务是否活跃    ↑ 是否启用抑制
```

**判断条件**：
1. `self.is_active`：事务必须处于 ACTIVE 状态
2. `self.suppress_commit`：抑制标志必须为 True

**is_active 属性** (`context.py:205-207`):
```python
@property
def is_active(self) -> bool:
    """事务是否活跃"""
    return self._state == TransactionState.ACTIVE
```

---

### 第 5 层：suppress_commit 属性

**文件**: `yweb/orm/transaction/context.py:219-225`

```python
@property
def suppress_commit(self) -> bool:
    """是否抑制内部的 commit=True 调用

    只有当 _suppress_commit 为 True 且没有通过 allow_commit() 临时允许时才抑制
    """
    return self._suppress_commit and self._allow_commit_depth == 0
    #      ↑ 初始化时设置        ↑ 临时允许计数器
```

**两个控制点**：
1. **`_suppress_commit`**：在创建事务时设置（默认 True）
2. **`_allow_commit_depth`**：临时允许提交的嵌套深度计数器

**初始化** (`context.py:153-175`):
```python
def __init__(
    self,
    session: Session,
    auto_commit: bool = True,
    propagation: TransactionPropagation = None,
    suppress_commit: bool = True  # 🔑 默认启用抑制
):
    self._session = session
    self._auto_commit = auto_commit
    self._propagation = propagation or TransactionPropagation.REQUIRED
    self._suppress_commit = suppress_commit  # 🔑 保存抑制标志
    self._state = TransactionState.INACTIVE

    # 提交抑制控制
    self._allow_commit_depth = 0  # 🔑 初始化为 0

    # ... 其他初始化
```

---

## 四、完整执行流程示例

### 示例 1：正常抑制场景（自动 flush）

```python
from yweb.orm import transaction_manager as tm

with tm.transaction() as tx:  # 1️⃣ 创建事务上下文
    # _current_transaction.set(tx)
    # tx._suppress_commit = True
    # tx._state = ACTIVE

    user = User(name="tom")
    user.save(commit=True)  # 2️⃣ 调用 save(commit=True)

    # 执行流程：
    # __is_commit(commit=True)
    #   → _should_suppress_commit()
    #     → get_current_transaction() 返回 tx
    #       → tx.should_suppress_commit() 返回 True
    #         → 执行 session.flush() + session.refresh(user)
    #         → return，不执行 session.commit()

    # ✅ user.id 已有值（因为自动 flush 了）
    profile = Profile(user_id=user.id)
    profile.save(commit=True)  # 3️⃣ 同样被抑制，但自动 flush

# 4️⃣ 退出上下文，__exit__ 统一提交
# tx.commit() → session.commit()
```

**结果**：
- ✅ 所有 `commit=True` 的实际提交被忽略
- ✅ 自动 flush，可以立即访问自动生成的字段（id, created_at 等）
- ✅ 事务在 `__exit__` 时统一提交
- ✅ 如果中间出错，整个事务回滚

**日志输出**：
```
DEBUG:orm.transaction:commit=True 被事务上下文抑制
DEBUG:orm.transaction:commit=True 被事务上下文抑制
DEBUG:yweb.orm.transaction:事务提交成功
```

---

### 示例 2：临时允许提交 (allow_commit)

```python
with tm.transaction() as tx:
    user.save(commit=True)  # ❌ 被抑制

    with tx.allow_commit():  # 🔓 临时允许
        # _allow_commit_depth += 1

        critical_log.save(commit=True)  # ✅ 真正提交！

        # _allow_commit_depth -= 1

    profile.save(commit=True)  # ❌ 又被抑制
```

**allow_commit 实现** (`context.py:389-401`):
```python
@contextmanager
def allow_commit(self):
    """临时允许 commit=True 生效

    使用示例:
        with tx.allow_commit():
            critical_log.save(commit=True)  # 正常提交
    """
    self._allow_commit_depth += 1  # 增加计数器
    try:
        yield
    finally:
        self._allow_commit_depth -= 1  # 恢复计数器
```

**判断逻辑**：
```python
@property
def suppress_commit(self) -> bool:
    return self._suppress_commit and self._allow_commit_depth == 0
    #                                 ↑ 当 > 0 时，返回 False，不抑制
```

**执行流程**：
```
1. user.save(commit=True)
   → _allow_commit_depth = 0
   → suppress_commit = True and 0 == 0 = True
   → 抑制 ✅

2. with tx.allow_commit():
   → _allow_commit_depth = 1

3. critical_log.save(commit=True)
   → _allow_commit_depth = 1
   → suppress_commit = True and 1 == 0 = False
   → 不抑制，真正提交 ✅

4. 退出 allow_commit
   → _allow_commit_depth = 0

5. profile.save(commit=True)
   → _allow_commit_depth = 0
   → suppress_commit = True and 0 == 0 = True
   → 抑制 ✅
```

---

### 示例 3：非事务场景

```python
# 没有事务上下文
user = User(name="tom")
user.save(commit=True)  # ✅ 正常提交

# 执行流程：
# __is_commit(commit=True)
#   → _should_suppress_commit()
#     → get_current_transaction() 返回 None
#       → 返回 False（不抑制）
#         → 执行 session.commit()
```

**详细流程**：
```python
def _should_suppress_commit(self) -> bool:
    try:
        from .transaction import get_current_transaction
        tx = get_current_transaction()  # 返回 None
        if tx is not None and tx.should_suppress_commit():
            # ❌ tx 是 None，不进入
            return True
    except ImportError:
        pass
    return False  # ✅ 返回 False
```

---

## 五、ContextVar 的作用

### 为什么使用 ContextVar？

```python
_current_transaction: ContextVar[Optional[TransactionContext]] = ContextVar(
    '_current_transaction', default=None
)
```

**优势**：
1. **线程安全**：每个线程有独立的值
2. **协程安全**：每个协程有独立的值
3. **自动传播**：在异步调用链中自动传递

**对比其他方案**：

| 方案 | 线程安全 | 协程安全 | 传播性 | 说明 |
|------|---------|---------|--------|------|
| 全局变量 | ❌ | ❌ | ❌ | 多线程/协程会互相覆盖 |
| threading.local | ✅ | ❌ | ❌ | 只支持线程，不支持协程 |
| ContextVar | ✅ | ✅ | ✅ | Python 3.7+ 推荐方案 |

**示例：多请求隔离**：
```python
# 请求 1
async def request_1():
    with tm.transaction() as tx1:
        # _current_transaction.get() 返回 tx1
        user.save(commit=True)  # 被 tx1 抑制

# 请求 2（同时进行）
async def request_2():
    with tm.transaction() as tx2:
        # _current_transaction.get() 返回 tx2
        order.save(commit=True)  # 被 tx2 抑制

# tx1 和 tx2 互不干扰！
```

---

## 六、事务上下文的设置与清理

### 设置事务上下文

**文件**: `yweb/orm/transaction/manager.py:315-320`

```python
@contextmanager
def transaction(
    self,
    session: Session = None,
    propagation: TransactionPropagation = TransactionPropagation.REQUIRED,
    auto_commit: bool = True,
    read_only: bool = False,
    suppress_commit: bool = None
) -> Generator[TransactionContext, None, None]:
    """创建事务上下文"""

    if session is None:
        session = self.get_session()

    if suppress_commit is None:
        suppress_commit = self._default_suppress_commit  # 默认 True

    # ... 处理事务传播 ...

    # 创建事务上下文
    ctx = TransactionContext(
        session=session,
        auto_commit=auto_commit,
        propagation=propagation,
        suppress_commit=suppress_commit  # 🔑 传入抑制标志
    )

    # 注册全局钩子
    self._apply_global_hooks(ctx)

    # 🔑 设置到 ContextVar
    token = _current_transaction.set(ctx)
    try:
        with ctx:
            yield ctx
    finally:
        # 🔑 清理 ContextVar
        _current_transaction.reset(token)
```

**关键点**：
1. **`set(ctx)`**：将事务上下文设置到 ContextVar，返回 token
2. **`reset(token)`**：在 finally 中恢复之前的值（支持嵌套事务）
3. **token 机制**：允许嵌套事务正确恢复外层事务

**嵌套事务示例**：
```python
with tm.transaction() as tx1:
    # token1 = _current_transaction.set(tx1)
    # get_current_transaction() 返回 tx1

    with tm.transaction() as tx2:
        # token2 = _current_transaction.set(tx2)
        # get_current_transaction() 返回 tx2
        pass
    # _current_transaction.reset(token2)
    # get_current_transaction() 恢复为 tx1

# _current_transaction.reset(token1)
# get_current_transaction() 恢复为 None
```

---

## 七、配置选项

### 全局配置

**文件**: `yweb/orm/transaction/manager.py:184-198`

```python
def configure(
    self,
    suppress_commit_in_transaction: bool = None,
    log_suppressed_commit: bool = None
) -> None:
    """配置事务管理器

    Args:
        suppress_commit_in_transaction: 是否在事务中抑制 commit=True
        log_suppressed_commit: 抑制 commit 时是否输出日志
    """
    if suppress_commit_in_transaction is not None:
        self._default_suppress_commit = suppress_commit_in_transaction
    if log_suppressed_commit is not None:
        self._log_suppressed_commit = log_suppressed_commit
```

**使用示例**：
```python
from yweb.orm import transaction_manager as tm

# 全局禁用提交抑制
tm.configure(suppress_commit_in_transaction=False)

# 现在所有事务都不会抑制 commit=True
with tm.transaction() as tx:
    user.save(commit=True)  # ✅ 真正提交（不推荐）
```

### 单次事务配置

```python
# 方式 1：上下文管理器
with tm.transaction(suppress_commit=False) as tx:
    # 这个事务不抑制 commit=True
    user.save(commit=True)  # ✅ 真正提交

# 方式 2：装饰器
@tm.transactional(suppress_commit=False)
def create_user(data):
    user = User(**data)
    user.save(commit=True)  # ✅ 真正提交
    return user
```

---

## 八、设计优势

### 1. 防止意外提交

```python
with tm.transaction() as tx:
    user.save(commit=True)  # 不会真正提交
    # 如果这里出错，user 不会被提交
    profile.save()
```

**传统方式的问题**：
```python
# 没有抑制机制
user.save(commit=True)  # ✅ 已提交
# 如果这里出错...
profile.save()  # ❌ 未执行
# 结果：user 已入库，profile 未入库，数据不一致！
```

### 2. 统一事务边界

```python
@tm.transactional()
def create_order(data):
    order.save(commit=True)  # 被抑制
    items.save_all(commit=True)  # 被抑制
    inventory.update(commit=True)  # 被抑制
    # 函数结束时统一提交
```

**优势**：
- ✅ 所有操作在一个事务中
- ✅ 要么全成功，要么全失败
- ✅ 不需要修改现有代码

### 3. 支持嵌套事务

```python
with tm.transaction() as tx1:
    user.save(commit=True)  # 被抑制

    with tm.transaction() as tx2:  # 嵌套事务
        profile.save(commit=True)  # 被抑制

    # tx2 退出时不提交（nesting_level > 1）
# tx1 退出时统一提交
```

### 4. 灵活的控制

```python
with tm.transaction() as tx:
    user.save(commit=True)  # 被抑制

    with tx.allow_commit():
        audit_log.save(commit=True)  # ✅ 允许提交

    profile.save(commit=True)  # 又被抑制
```

---

## 九、潜在问题与注意事项

### 问题 1：开发者困惑

```python
user.save(commit=True)  # 为什么没提交？
# 因为在事务上下文中被抑制了
```

**解决方案**：
1. 文档说明
2. 日志提示：`logger.debug("commit=True 被事务上下文抑制")`
3. 代码注释

### 问题 2：批量操作的性能问题

在 `@transactional` 中循环调用 `save(True)` 会导致严重性能问题：

```python
# ❌ 糟糕：每次 save(True) 都会 flush，1000 次网络往返
@tm.transactional()
def batch_import(users_data):
    for data in users_data:  # 1000 条
        user = User(**data)
        user.save(True)  # 每次都 flush！

# ✅ 好：批量场景使用 save()
@tm.transactional()
def batch_import(users_data):
    for data in users_data:
        user = User(**data)
        user.save()  # 只 add，不 flush
    # 事务结束时自动 commit
```

**性能对比**（1000 条数据）：

| 方式 | flush 次数 | 耗时 |
|-----|-----------|------|
| 循环 `save(True)` | 1000 次 | ~5-10 秒 |
| 循环 `save()` | 0 次 | ~0.1-0.5 秒 |

**原则**：
- 普通 API（1-2 条数据）：`save(True)` 没问题
- 批量操作：用 `save()` 代替 `save(True)`

### 问题 3：ContextVar 访问开销

每次 `commit=True` 都要：
1. 调用 `get_current_transaction()`
2. 检查事务状态
3. 判断是否抑制

**影响**：微小，可忽略（ContextVar 访问非常快）

### 问题 4：与第三方库冲突

如果第三方库直接调用 `session.commit()`，无法被抑制。

**解决方案**：
```python
with tm.transaction() as tx:
    # 第三方库
    third_party_lib.save(session)  # 内部调用 session.commit()
    # ⚠️ 无法被抑制
```

**建议**：在事务中避免使用直接操作 session 的第三方库

### 问题 5：allow_commit 的滥用

```python
with tm.transaction() as tx:
    with tx.allow_commit():
        user.save(commit=True)  # 真正提交
    # 如果这里出错，user 已提交，无法回滚
```

**建议**：只在必要时使用 `allow_commit()`，如审计日志

---

## 十、最佳实践

### 推荐做法

```python
# ✅ 推荐：创建新对象后需要访问 id 时，使用 commit=True
@tm.transactional()
def create_user_with_profile(data):
    user = User(**data)
    user.save(True)  # commit 被抑制，但自动 flush，user.id 可用
    
    profile = Profile(user_id=user.id)  # ✅ user.id 有值
    profile.save(True)
    
    return user

# ✅ 推荐：使用装饰器
@tm.transactional()
def create_user(data):
    user = User(**data)
    user.save(True)  # 自动 flush，可以立即访问 user.id
    return user

# ✅ 推荐：不需要 id 时，可以不传 commit 参数
with tm.transaction() as tx:
    user.save()  # 不传 commit 参数
    profile.save()
    # 统一提交
```

### 不推荐做法

```python
# ❌ 不推荐：禁用抑制
with tm.transaction(suppress_commit=False) as tx:
    user.save(commit=True)  # 破坏了事务的原子性
```

---

## 十一、总结

### 核心机制

1. **ContextVar 存储当前事务**：线程/协程安全
2. **模型层拦截 commit**：在执行前检查是否应该抑制
3. **自动 flush**：commit 被抑制时，自动执行 flush + refresh 以获取自动生成字段
4. **事务上下文控制**：通过 `suppress_commit` 标志控制
5. **统一提交时机**：在事务 `__exit__` 时统一提交

### 调用链总结

```
user.save(commit=True)
  ↓
__is_commit(commit=True)
  ↓
_should_suppress_commit()
  ↓
get_current_transaction() → ContextVar.get()
  ↓
tx.should_suppress_commit()
  ↓
return self.is_active and self.suppress_commit
  ↓
如果 True：执行 flush + refresh，然后 return（抑制 commit，但可访问自动生成字段）
如果 False：执行 session.commit()
```

### 设计亮点

- ✅ 优雅的 AOP 设计（面向切面编程）
- ✅ 零侵入性（不改变用户代码）
- ✅ 线程/协程安全
- ✅ 支持嵌套和临时允许
- ✅ 可配置（全局 + 单次）
- ✅ **自动 flush**：抑制 commit 时仍可访问自动生成的字段（id, created_at 等）

### 关键文件

| 文件 | 作用 |
|------|------|
| `yweb/orm/core_model.py` | 模型层拦截 commit |
| `yweb/orm/transaction/manager.py` | 事务管理器，ContextVar 管理 |
| `yweb/orm/transaction/context.py` | 事务上下文，抑制逻辑 |

---

**文档生成时间**: 2026-01-21
**分析范围**: yweb-core ORM 框架提交抑制机制
**分析方法**: 代码追踪 + 执行流程分析
