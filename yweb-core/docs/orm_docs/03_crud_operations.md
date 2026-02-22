# 03. CRUD 操作

## 概述

YWeb ORM 提供了完整的 CRUD（Create, Read, Update, Delete）操作方法，支持事务控制和自动提交。

> **注意**：
>
> - 所有查询方法使用 `Model.query`，这是通过 `init_database()` 自动设置的
> - 主键 `id` 的类型可能是 `int` 或 `str`，取决于主键策略配置（auto_increment/snowflake/uuid/short_uuid/custom）
> - 在事务上下文中，`commit=True` 可能会被事务管理器抑制，由事务管理器统一控制提交

## 创建（Create）

### save() 方法（推荐）

智能保存：将对象添加到会话中。`save()` 方法对新建对象和已存在对象都是幂等的，SQLAlchemy 会自动追踪对象变化。

```python
# 新对象 - 添加到会话
user = User(username="tom", email="tom@example.com")
user.save()  # 添加到会话，不提交
user.save(True)  # 添加到会话并提交

# 已存在对象 - 修改后保存
user = User.get(1)
user.email = "new@example.com"
user.save(True)  # SQLAlchemy 会自动检测变化并更新

# save() 是幂等的，可以安全地多次调用
user.save()
user.save()  # 不会重复添加
```

> **工作原理**：
>
> - `save()` 内部调用 `session.add(self)`
> - `session.add()` 是幂等的，对已在会话中的对象调用是安全的
> - SQLAlchemy 会自动追踪 persistent 对象的变化，在 flush/commit 时执行实际的 SQL 操作
> - 不需要手动判断是新增还是更新，SQLAlchemy 会根据对象状态自动处理

### add() 方法（已废弃）

> ⚠️ **已废弃**：建议使用 `save()` 方法，`add()` 将在未来版本中移除。`save()` 语义更清晰，表示"保存对象（新增或更新）"。

```python
# 已废弃的用法
user = User(username="tom", email="tom@example.com")
user.add()  # 内部调用 save()

# 推荐用法
user.save()
```

### save_all() 批量保存（推荐）

批量保存对象（新增或更新）：

```python
users = [
    User(username="user1", email="user1@example.com"),
    User(username="user2", email="user2@example.com"),
    User(username="user3", email="user3@example.com"),
]

# 批量保存（不提交，默认 commit=False）
User.save_all(users)

# 批量保存并提交
User.save_all(users, commit=True)

# 所有对象都有 ID（提交后）
for user in users:
    print(user.id)  # 类型可能是 int 或 str，取决于主键策略

# 也可以保存已存在的对象
existing_users = User.query.filter(User.is_active == True).all()
for user in existing_users:
    user.status = "verified"
User.save_all(existing_users, commit=True)
```

> **注意**：`save_all()` 的 `commit` 参数默认为 `False`，需要显式传入 `commit=True` 才会立即提交。

### add_all() 批量添加（已废弃）

> ⚠️ **已废弃**：建议使用 `save_all()` 方法，`add_all()` 将在未来版本中移除。

```python
# 已废弃的用法
User.add_all(users, commit=True)

# 推荐用法
User.save_all(users, commit=True)
```

## 查询（Read）

### get() 根据 ID 获取

```python
# 获取单个对象
# 注意：id 的类型可能是 int 或 str，取决于主键策略
user = User.get(1)  # 整数主键
# 或
user = User.get("abc123")  # 字符串主键（UUID/短UUID）

if user:
    print(user.username)
else:
    print("用户不存在")

# get() 找不到时返回 None，不会抛出异常
# 但如果找到多条数据（主键不唯一），会抛出 ValueError 异常
```

### get_all() 获取所有

```python
# 获取所有记录
users = User.get_all()

for user in users:
    print(user.username)
```

### get_list_by_conditions() 条件查询

```python
# 单条件查询
active_users = User.get_list_by_conditions({"is_active": True})

# 多条件查询（AND）
users = User.get_list_by_conditions({
    "is_active": True,
    "department_id": 1
})
```

### query 属性查询

```python
# 使用 query 属性进行复杂查询
users = User.query.filter(
    User.is_active == True
).all()

# 链式调用
users = User.query.filter(
    User.is_active == True
).filter(
    User.age >= 18
).order_by(
    User.created_at.desc()
).all()

# 获取第一条
user = User.query.filter(User.username == "tom").first()

# 获取数量
count = User.query.filter(User.is_active == True).count()
```

### 复杂条件查询

```python
from sqlalchemy import and_, or_, not_

# AND 条件
users = User.query.filter(
    and_(
        User.is_active == True,
        User.age >= 18
    )
).all()

# OR 条件
users = User.query.filter(
    or_(
        User.username == "admin",
        User.email.like("%@admin.com")
    )
).all()

# NOT 条件
users = User.query.filter(
    not_(User.is_active == False)
).all()

# 组合条件
users = User.query.filter(
    and_(
        User.is_active == True,
        or_(
            User.role == "admin",
            User.role == "manager"
        )
    )
).all()
```

### 模糊查询

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
# IN 查询
users = User.query.filter(User.id.in_([1, 2, 3])).all()

# NOT IN 查询
users = User.query.filter(User.id.not_in([1, 2, 3])).all()
```

### 排序

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
```

### 限制和偏移

```python
# 限制数量
users = User.query.limit(10).all()

# 偏移
users = User.query.offset(20).limit(10).all()

# 等同于分页
users = User.query.offset((page - 1) * page_size).limit(page_size).all()
```

### 只返回指定字段查询

当只需要查询部分字段时，可以使用以下方法优化性能：

#### 方法1：使用 with_entities()（推荐）

```python
# 只查询指定字段，返回元组
results = User.query.with_entities(
    User.id,
    User.username,
    User.email
).filter(User.is_active == True).all()

# 返回的是元组，不是模型对象
for row in results:
    user_id, username, email = row
    print(f"{user_id}: {username} - {email}")
```

#### 方法2：使用 load_only()（返回模型对象）

```python
from sqlalchemy.orm import load_only

# 只加载指定字段，返回模型对象（但只有指定字段有值）
users = User.query.options(
    load_only(User.id, User.username, User.email)
).filter(User.is_active == True).all()

# 返回的是模型对象，但只有指定字段有值
for user in users:
    print(f"{user.id}: {user.username} - {user.email}")
    # user.note 等未加载的字段访问时会触发延迟加载
```

#### 方法3：使用 defer() 排除字段

```python
from sqlalchemy.orm import defer

# 排除大字段，只加载其他字段
users = User.query.options(
    defer(User.avatar),      # 排除头像（大字段）
    defer(User.bio),         # 排除简介（大字段）
    defer(User.extra_data)  # 排除额外数据
).filter(User.is_active == True).all()

# 返回的是模型对象，排除的字段访问时会触发延迟加载
```

> **性能建议**：
>
> - 如果只需要少量字段，使用 `with_entities()` 性能最好（不加载完整对象）
> - 如果需要模型对象但想排除大字段，使用 `defer()` 或 `load_only()`
> - 对于列表查询，优先使用 `with_entities()` 减少内存占用

## 更新（Update）

### update() 方法

`update()` 方法支持两种使用方式：

**方式一：先修改属性，再调用 update()**

```python
# 获取对象
user = User.get(1)

# 修改属性
user.email = "new@example.com"
user.is_active = False

# 更新并提交
user.update(commit=True)
```

**方式二：通过 kwargs 直接更新属性（推荐）**

```python
user = User.get(1)

# 直接传入要更新的属性
user.update(email="new@example.com", is_active=False, commit=True)

# 支持链式调用
user.update(name="Tom").update(age=25, commit=True)
```

> **说明**：
>
> - `update(**kwargs)` 会遍历 kwargs，对存在的属性进行 `setattr`
> - 不存在的属性会被忽略，不会抛出异常
> - SQLAlchemy 会自动追踪对象属性的变化，标记对象为 "dirty"
> - 实际的 SQL UPDATE 语句在 `session.flush()` 或 `session.commit()` 时执行

### update_all() 批量更新

`update_all()` 类方法支持两种使用方式：

**方式一：对象已修改属性，只需触发提交**

```python
users = User.query.filter(User.is_active == True).all()

# 修改每个对象的属性
for user in users:
    user.status = "verified"

# 批量提交
User.update_all(users, commit=True)
```

**方式二：通过 kwargs 批量设置相同属性（推荐）**

```python
users = User.query.filter(User.department_id == 1).all()

# 批量设置所有对象的相同属性
User.update_all(users, status="active", level=2, commit=True)
```

> **注意**：kwargs 方式会将所有对象设置为相同的值，适用于批量状态变更等场景。

### update_properties() 方法（已废弃）

> ⚠️ **已废弃**：建议使用 `update(**kwargs)` 方法，`update_properties()` 将在未来版本中移除。`update()` 方法功能更完整，支持同时更新属性和提交。

```python
# 已废弃的用法
user.update_properties(email="new@example.com", is_active=False)
user.save(True)

# 推荐用法
user.update(email="new@example.com", is_active=False, commit=True)
```

### save() 方法更新

```python
user = User.get(1)
user.email = "new@example.com"
user.save(True)  # SQLAlchemy 会自动检测变化并更新
```

### update_with_foreign_key_none() 方法

当需要将外键字段设置为 `None` 时，使用此方法可以防止在事件监听中被误认为是软删除：

```python
user = User.get(1)

# 设置外键为 None
user.department_id = None
user.update_with_foreign_key_none()  # 标记，防止误判为软删除

# 或直接提交
user.update_with_foreign_key_none(commit=True)
```

> **使用场景**：当模型有外键字段，且软删除功能通过监听 `session.delete()` 实现时，设置外键为 `None` 可能会被误判为软删除操作。使用此方法可以明确标识这是正常的外键更新，而非软删除。

## 删除（Delete）

### delete() 方法

**CoreModel 和 BaseModel 的 delete() 行为不同：**

- **CoreModel**：`delete()` 是物理删除（`session.delete(self)`），会直接从数据库删除记录
- **BaseModel**：`delete()` 是软删除，通过 SimpleSoftDeleteMixin 的钩子拦截 `session.delete()`，转换为设置 `deleted_at` 字段

#### BaseModel 软删除（推荐）

```python
# BaseModel 继承 SimpleSoftDeleteMixin，delete() 是软删除
user = User.get(1)

# 软删除（不提交）
user.delete()  # 设置 deleted_at = datetime.now()

# 软删除并提交
user.delete(True)

# 软删除后，正常查询不会返回该记录
user = User.get(1)  # 返回 None（被软删除过滤）
```

#### CoreModel 物理删除

```python
# CoreModel 的 delete() 是物理删除
class LogEntry(CoreModel):
    __tablename__ = "log_entry"
    message: Mapped[str] = mapped_column(String(500))

log = LogEntry.get(1)
log.delete(True)  # 物理删除，记录直接从数据库删除
```

### 查询已删除的记录

```python
# 包含已删除的记录
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()

# 只查询已删除的记录
deleted_users = User.query.execution_options(include_deleted=True).filter(
    User.deleted_at.isnot(None)
).all()
```

### 恢复软删除的记录

```python
# 获取已删除的记录
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()

# 恢复软删除（SimpleSoftDeleteMixin 提供的方法）
if user and user.is_deleted:  # is_deleted 是 SimpleSoftDeleteMixin 提供的属性
    user.undelete()  # 设置 deleted_at = None
    user.save(True)  # 提交更改

# 检查是否已删除（SimpleSoftDeleteMixin 提供的属性）
if user.is_deleted:  # 等同于 user.deleted_at is not None
    print("该记录已被软删除")
```

> **注意**：
>
> - `undelete()` 和 `is_deleted` 是 `SimpleSoftDeleteMixin` 提供的方法和属性
> - 只有继承 `SimpleSoftDeleteMixin` 的模型（如 BaseModel）才有这些功能
> - CoreModel 没有软删除功能，因此没有 `undelete()` 方法

### 物理删除

如果确实需要物理删除（BaseModel 的软删除记录）：

```python
from sqlalchemy import delete
from yweb.orm import db_manager

session = db_manager.get_session()

# 方法1：使用 delete 语句（推荐）
stmt = delete(User).where(User.id == 1)
session.execute(stmt)
session.commit()

# 方法2：先查询再删除（需要包含已删除记录）
user = User.query.execution_options(include_deleted=True).filter_by(id=1).first()
if user:
    session.delete(user)  # 物理删除
    session.commit()
```

> **警告**：物理删除会永久删除数据，无法恢复。请谨慎使用!

### delete_all() 批量删除

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
> - 对于 BaseModel 会触发软删除，对于 CoreModel 是物理删除
> - 详细说明请参考 [06_批量操作](06_bulk_operations.md) 文档

## 刷新对象（Refresh）

### refresh() 方法

从数据库重新加载对象状态。用于在 commit 后需要继续操作对象的**特殊场景**。

> ⚠️ **重要：优先使用单次提交模式**
>
> 大多数场景下，应该将所有相关操作放在同一个事务中一次性提交，而不是多次 commit 后再 refresh。
> refresh 会产生额外的数据库查询，仅在特殊场景下使用。

```python
# 基本用法
user.save(commit=True)
user.refresh()  # 从数据库重新加载

# 链式调用
user.save(True).refresh()

# 只刷新特定属性
user.refresh(['name', 'updated_at'])
```

**典型使用场景**（需要 refresh 的特殊情况）：

```python
# 场景1：需要获取数据库触发器/默认值生成的字段
user.save(commit=True)
user.refresh()  # 获取数据库生成的字段

# 场景2：commit 后需要继续操作对象的关系属性
role.save(commit=True)
role.refresh()  # 刷新后才能正常操作关系
user.roles.append(role)
```

### refresh_all() 批量刷新

批量从数据库重新加载对象状态。

> ⚠️ **性能警告**：此方法会对每个对象执行一次 SELECT 查询。
> 例如 `refresh_all(100个对象)` = 100 次数据库查询。批量操作时请谨慎使用。

```python
# 批量刷新
roles = [role1, role2, role3]
Role.save_all(roles, commit=True)
Role.refresh_all(roles)  # 批量刷新

# 只刷新特定属性
Role.refresh_all(roles, ['name', 'permissions'])
```

### 推荐：单次提交模式（避免 refresh）

在大多数场景下，使用单次提交模式可以避免使用 refresh：

```python
# ✅ 推荐：单次提交模式（不需要 refresh）
role = Role(name="admin")
user = User(name="test")
user.roles.append(role)  # 都是新对象，直接关联
session.add_all([role, user])
session.commit()  # 一次性提交

# ❌ 不推荐：多次提交后再关联（需要 refresh）
role.save(commit=True)
role.refresh()  # 需要额外刷新
user.roles.append(role)
user.save(commit=True)
```

## 事务控制

### commit 参数

所有修改方法都支持 `commit` 参数：

```python
# commit=False（默认）：只添加到会话，不提交
user.save()
user.update()
user.delete()

# commit=True：添加到会话并立即提交
user.save(True)
user.update(name="new_name", commit=True)
user.delete(True)
```

> **重要**：在事务上下文中，`commit=True` 的行为会被事务管理器调整：
>
> - 如果当前在事务管理器（TransactionManager）的上下文中
> - 且事务管理器启用了提交抑制（`should_suppress_commit()` 返回 `True`）
> - 则 `commit=True` 的实际提交会被忽略，由事务管理器统一控制提交
> - **但会自动执行 `flush()` + `refresh()`**，以便立即访问自动生成的字段（id, created_at 等）
> - 这是为了支持嵌套事务和事务传播行为，同时保证新对象的 id 可用

### 获取主键 ID

无论使用哪种主键策略（自增、UUID、雪花算法等），所有主键都是在 `flush` 时生成的：
- **自增主键**：数据库在 INSERT 时生成，flush 后通过 RETURNING 或 LAST_INSERT_ID 获取
- **非自增主键**：在 SQLAlchemy 的 `before_insert` 事件中生成（flush 过程的一部分）

框架会在访问 `id` 属性时**自动检测并 flush**，无需手动处理：

```python
# ✅ 直接使用，访问 id 时自动 flush
with tm.transaction():
    user = User(name="张三")
    user.save()
    print(user.id)  # 访问时自动 flush，主键立即可用！

# 同样适用于 @transactional 装饰器
@tm.transactional()
def create_user_with_profile(data):
    user = User(**data)
    user.save()
    
    # user.id 访问时自动 flush，可直接使用
    profile = Profile(user_id=user.id)
    profile.save()
    return user
```

**原理**：框架在 `CoreModel.__getattribute__` 中拦截 `id` 属性访问，
当 id 为 None 且对象处于 pending 状态时，自动触发 `session.flush()`。

> **注意**：如果需要显式控制 flush 时机，仍可使用 `save(commit=True)` 或手动 `session.flush()`。

#### 手动指定主键的行为差异

如果手动指定了 `id` 值，访问 `id` 时**不会触发自动 flush**：

```python
# 手动指定 id
user = User(name="张三")
user.id = "my_custom_id"  # 手动指定
user.save()

# 此时访问 user.id 不会触发 flush（因为 id 不是 None）
print(user.id)  # 返回 "my_custom_id"，但对象可能还未写入数据库
```

| 场景 | 访问 id 时 | 冲突检测时机 | 重试机制 |
|-----|-----------|-------------|---------|
| 框架自动生成 id | 自动 flush | 立即（flush 时） | ✅ `generate_with_retry` 生效 |
| 手动指定 id | 不触发 flush | 延迟（commit 时） | ❌ 不生效，直接报错 |

> ⚠️ **风险**：手动指定的 id 如果与数据库已有记录冲突，会在 commit 时抛出 `IntegrityError`，
> 且 `generate_with_retry` 重试机制不会工作。建议让框架自动生成主键，除非 id 来源可靠唯一。

### 手动事务控制

**推荐方式：使用 `db_session_scope` 上下文管理器**

```python
from yweb.orm import db_session_scope

with db_session_scope() as session:
    # 多个操作
    user1 = User(username="user1")
    user1.add()  # 添加到会话，不提交

    user2 = User(username="user2")
    user2.add()  # 添加到会话，不提交

    # 自动提交（两个操作在同一事务中）
# 自动清理 session
```

> **注意**：
>
> - `db_session_scope()` 自动管理 session 生命周期，包括提交、回滚和清理
> - 在 FastAPI 等框架中，通常使用 `get_db()` 依赖注入获取 session
> - 所有模型实例的 `session` 属性会自动获取当前 session，通常不需要手动传递

### Service 层事务模式

**推荐方式：使用 `@transactional` 装饰器**

```python
from yweb.orm import transaction_manager as tm

class UserService:
    @tm.transactional()
    def create_user_with_profile(self, user_data: dict, profile_data: dict):
        """创建用户和档案（事务）"""
        # 创建用户
        user = User(**user_data)
        user.save(True)  # commit 被抑制，但自动 flush，user.id 可用

        # 创建档案（直接使用 user.id）
        profile = UserProfile(user_id=user.id, **profile_data)
        profile.save(True)

        # 函数结束时由事务管理器统一提交
        return user
```

> **性能警告**：在 `@transactional` 中循环调用 `save(True)` 会导致性能问题！
>
> ```python
> # ❌ 糟糕：每次 save(True) 都会 flush，1000 次网络往返
> @tm.transactional()
> def batch_import(users_data):
>     for data in users_data:  # 1000 条
>         user = User(**data)
>         user.save(True)  # 每次都 flush！
>
> # ✅ 好：批量场景使用 save()，最后统一处理
> @tm.transactional()
> def batch_import(users_data):
>     for data in users_data:
>         user = User(**data)
>         user.save()  # 只 add，不 flush
>     # 事务结束时自动 commit
> ```

**传统方式（手动事务控制）**

```python
from yweb.orm import db_manager

class UserService:
    def __init__(self, session=None):
        self.session = session or db_manager.get_session()

    def create_user_with_profile(self, user_data: dict, profile_data: dict):
        """创建用户和档案（事务）"""
        try:
            # 创建用户
            user = User(**user_data)
            user.add()
          
            # flush() 的作用：
            # - 将 pending 的对象刷新到数据库（执行 INSERT）
            # - 获取主键 ID（自增由数据库生成，其他在 before_insert 事件中生成）
            # - 但不提交事务，可以继续在同一事务中执行其他操作
            self.session.flush()  # 获取 user.id，但不提交

            # 创建档案（使用刚获取的 user.id）
            profile = UserProfile(user_id=user.id, **profile_data)
            profile.add()

            # 统一提交（两个操作在同一事务中）
            self.session.commit()
            return user
        except Exception as e:
            self.session.rollback()
            raise
```

> **flush() 与 commit() 的区别**：
>
> - `flush()`：将 SQL 语句发送到数据库执行，但不提交事务。可以获取自动生成的主键，但事务未结束，可以回滚
> - `commit()`：提交事务，所有更改永久保存到数据库。提交后无法回滚
> - 在同一事务中需要先获取主键再创建关联记录时，使用 `flush()` 获取 ID，最后统一 `commit()`

## 版本控制（乐观锁）

CoreModel 和 BaseModel 的 `ver` 字段用于乐观锁，通过 `__mapper_args__ = {"version_id_col": ver}` 配置：

```python
# 获取用户
user = User.get(1)
print(user.ver)  # 1

# 修改属性
user.name = "New Name"
user.update()  # 或 user.save()，只是标记为 dirty

# 版本号在 commit 时自动递增，不是在 update 时
user.session.commit()  # 或 user.update(True)
print(user.ver)  # 2（commit 后自动递增）

# 并发冲突检测
from sqlalchemy.orm.exc import StaleDataError

user1 = User.get(1)  # ver = 1
user2 = User.get(1)  # ver = 1（另一个会话获取同一记录）

user1.name = "Name1"
user1.update(True)  # commit 后 ver = 2

user2.name = "Name2"
try:
    user2.update(True)  # 失败，版本号已变（期望 ver=1，但实际是 ver=2）
except StaleDataError:
    print("并发冲突，请刷新后重试")
    # 需要重新获取最新数据
    user2 = User.get(1)  # 重新获取，ver = 2
    user2.name = "Name2"
    user2.update(True)  # 成功
```

> **工作原理**：
>
> - 每次 `commit()` 时，SQLAlchemy 会自动检查 `ver` 字段
> - 如果检测到版本号不匹配（其他事务已更新），会抛出 `StaleDataError` 异常
> - 版本号在 `commit()` 时自动递增，不是在 `update()` 时
> - 通过 `__mapper_args__ = {"version_id_col": ver}` 配置启用乐观锁

## 最佳实践

### 1. 方法选择指南

| 场景 | 推荐方法 | 说明 |
|------|---------|------|
| 新增对象 | `save()` | 将对象添加到会话 |
| 更新属性 | `update(**kwargs)` | 直接传入要更新的属性 |
| 批量保存 | `save_all()` | 批量添加或更新对象 |
| 批量更新 | `update_all()` | 批量更新对象属性 |
| 删除对象 | `delete()` | 软删除（BaseModel）或物理删除（CoreModel） |
| 批量删除 | `delete_all()` | 批量删除对象 |
| 刷新对象 | `refresh()` | commit 后刷新对象状态（特殊场景） |
| 批量刷新 | `refresh_all()` | 批量刷新对象状态（特殊场景） |

### 2. 使用 save() 保存对象

```python
# 推荐：使用 save()，SQLAlchemy 自动处理
user = User(username="tom")
user.save(True)  # 新对象，自动添加

user.email = "new@example.com"
user.save(True)  # 已存在对象，自动检测变化并更新
```

> **注意**：`save()` 内部调用 `session.add()`，SQLAlchemy 会自动判断对象状态，不需要手动区分新增和更新。

### 3. 使用 update() 更新属性

```python
# 推荐：使用 update() 直接传入要更新的属性
user = User.get(1)
user.update(email="new@example.com", is_active=False, commit=True)

# 不推荐：分开调用
user.email = "new@example.com"
user.is_active = False
user.update(commit=True)
```

### 4. 批量操作使用 save_all() / update_all()

```python
# 推荐：批量保存
users = [User(username=f"user{i}") for i in range(100)]
User.save_all(users, commit=True)

# 推荐：批量更新（设置相同值）
users = User.query.filter(User.department_id == 1).all()
User.update_all(users, status="active", commit=True)

# 不推荐：循环单个操作
for user in users:
    user.save(True)  # 每次都提交，性能差
```

### 3. 查询时使用 query 属性

```python
# 推荐：使用 query 属性
users = User.query.filter(User.is_active == True).all()

# 不推荐：使用 session.query
users = session.query(User).filter(User.is_active == True).all()
```

### 4. 合理使用事务

```python
from yweb.orm import db_manager

session = db_manager.get_session()

# 推荐：相关操作放在同一事务
user = User(username="tom")
user.add()

# 如果需要获取 user.id，先 flush
session.flush()  # 获取 user.id，但不提交

profile = UserProfile(user_id=user.id)
profile.add()

session.commit()  # 统一提交

# 不推荐：每个操作单独提交
user = User(username="tom")
user.add(True)  # 提交

profile = UserProfile(user_id=user.id)
profile.add(True)  # 再次提交
```

### 5. 关系操作使用单次提交模式

> ⚠️ **重要**：操作关系属性（如多对多）时，**必须使用单次提交模式**，否则可能导致关联失败。

```python
# ✅ 正确：单次提交模式
role1 = Role(name="admin")
role2 = Role(name="editor")
user = User(username="tom")

# 先建立关联（此时都是新对象）
user.roles.append(role1)
user.roles.append(role2)

# 一次性提交所有对象
session.add_all([role1, role2, user])
session.commit()

# ❌ 错误：先提交再关联
role1 = Role(name="admin")
role1.save(commit=True)  # 先提交角色

user = User(username="tom")
user.roles.append(role1)  # ⚠️ 可能失败！role1 状态已变化
user.save(commit=True)

# ⚠️ 如果必须先提交再关联，需要使用 refresh()
role1 = Role(name="admin")
role1.save(commit=True)
role1.refresh()  # 刷新对象状态

user = User(username="tom")
user.roles.append(role1)  # 现在可以正常工作
user.save(commit=True)
```

**为什么先提交再关联会失败？**

SQLAlchemy 默认配置 `expire_on_commit=True`，commit 后对象状态会过期。
当尝试将过期对象添加到关系集合时，可能会被 SQLAlchemy 跳过，导致关联不生效。

### 6. 服务层事务管理（重要）

> ⚠️ **重要**：服务层推荐使用 `@transactional` 装饰器自动管理事务，这是框架的首选方式。

#### 方式一：使用 @transactional 装饰器（推荐）

```python
from yweb.orm import transaction_manager as tm

class EmployeeService:
    @tm.transactional()
    def remove_from_dept(self, employee_id: int, dept_id: int):
        """从部门中移除员工（自动事务管理）"""
        employee = self.employee_model.get(employee_id)
        if employee is None:
            raise ValueError(f"员工不存在: {employee_id}")
        
        # 批量删除操作
        self.emp_dept_rel_model.query.filter(
            self.emp_dept_rel_model.employee_id == employee_id,
            self.emp_dept_rel_model.dept_id == dept_id
        ).delete()
        
        # 更新员工状态
        if employee.primary_dept_id == dept_id:
            employee.primary_dept_id = None
        
        employee.save()  # 不需要 commit=True，事务管理器自动提交
```

**优势**：
- 自动提交：方法正常返回时自动提交
- 自动回滚：方法抛出异常时自动回滚
- 嵌套事务：支持 Savepoint，内层失败不影响外层
- 提交抑制：嵌套调用时，内层的 `save(commit=True)` 会被自动抑制

#### 方式二：手动 save(commit=True)（简单场景）

对于不使用 `@transactional` 的简单方法，通过模型实例提交：

```python
class EmployeeService:
    def update_employee(self, employee_id: int, **kwargs):
        """更新员工（简单场景）"""
        employee = self.employee_model.get(employee_id)
        employee.update(**kwargs)
        employee.save(commit=True)  # 手动提交
```

#### 不推荐的方式

```python
# ❌ 不推荐：直接调用 session.commit()
from yweb.orm import db_manager
db_manager.get_session().commit()

# ❌ 不推荐：使用 query.session.commit()
self.model.query.session.commit()
```

**原因**：
- 与 `@transactional` 装饰器不兼容
- 测试时需要初始化 `db_manager`
- 脱离了 Active Record 模式

#### 内部辅助方法规范

内部方法（以 `_` 开头）不应自行提交，由调用方或事务管理器统一处理：

```python
def _validate_employee(self, employee_id: int):
    """内部方法：只做校验，不提交"""
    employee = self.employee_model.get(employee_id)
    if not employee:
        raise ValueError("员工不存在")
    return employee

@tm.transactional()
def update_employee(self, employee_id: int, data: dict):
    """更新员工"""
    employee = self._validate_employee(employee_id)
    employee.update(**data)  # 事务管理器自动提交
```

#### 删除操作与级联软删除

当模型使用 `fields.*` API 定义关系并配置了 `on_delete` 参数时，框架会自动处理关联数据的级联删除，**无需手动清理**：

```python
@tm.transactional()
def delete_employee(self, employee_id: int):
    """删除员工 - 框架自动级联删除关联数据"""
    employee = self.employee_model.get(employee_id)
    if not employee:
        raise ValueError("员工不存在")
    # 直接删除即可，关联的 emp_org_rel、emp_dept_rel 等会自动处理
    employee.delete()  # 事务管理器自动提交
```

> **注意**：如果模型的关系配置了 `on_delete=PROTECT`，删除时会自动检查并阻止存在关联数据的删除操作。

### 7. 使用批量操作方法

对于大量数据的更新和删除，使用批量操作方法性能更好：

```python
# 批量更新
# 更新所有活跃用户的状态
count = User.bulk_update(
    filters={"is_active": True},
    values={"status": "active"},
    commit=True
)
print(f"更新了 {count} 条记录")

# 根据 ID 批量更新
count = User.bulk_update_by_ids(
    ids=[1, 2, 3],
    values={"is_active": False},
    commit=True
)

# 批量软删除（BaseModel）
count = User.bulk_soft_delete(
    filters={"status": "inactive"},
    commit=True
)

# 批量物理删除（CoreModel）
count = LogEntry.bulk_delete(
    filters={"created_at < ": "2024-01-01"},
    commit=True
)
```

详细说明请参考 [06_批量操作](06_bulk_operations.md) 文档。

## 下一步

- [04_查询与过滤](04_query_and_filter.md) - 深入学习查询
- [05_分页查询](05_pagination.md) - 学习分页功能
- [06_批量操作](06_bulk_operations.md) - 学习批量操作
