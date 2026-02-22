# 10. 历史记录

## 概述

YWeb ORM 支持通过 `sqlalchemy-history` 库实现版本历史记录功能，可以：

- 记录每次数据变更
- 查看历史版本
- 比较版本差异
- 恢复到指定版本

> **注意**：历史记录功能是可选的，需要安装 `sqlalchemy-history` 库。

## 安装

```bash
pip install sqlalchemy-history
```

## 初始化

### 启用版本化

> **重要说明**：
> - `init_versioning()` 使用**全局单例模式**，整个应用只能初始化一次
> - 重复调用会被自动忽略，只有第一次调用的配置生效
> - 所有启用 `enable_history=True` 的模型共享同一个版本化配置
> - **必须在应用入口统一调用**，不要在每个模型文件中分别调用

### 两种初始化方式

#### 方式1：在模块 `__init__.py` 中初始化（推荐）

**适用场景**：大型项目，数据库相关代码集中管理

**项目结构**：
```
project/
├── database/
│   ├── __init__.py      # ← 在这里初始化
│   └── models/
│       ├── __init__.py
│       ├── user.py
│       └── article.py
└── app.py
```

**核心代码**：

```python
# database/__init__.py
from yweb.orm import init_versioning
from yweb.orm.history import CurrentUserPlugin

# 初始化版本化（模块导入时自动执行）
init_versioning(plugins=[CurrentUserPlugin()])

# 导入所有模型
from .models import User, Article

__all__ = ['User', 'Article']
```

```python
# database/models/article.py
from yweb.orm import CoreModel

class Article(CoreModel):
    __tablename__ = 'articles'
    enable_history = True  # ← 自动配置历史记录
    # ...
```

```python
# app.py
from database import User, Article  # ← 导入时自动初始化
```

**说明**：
- 在 `database/__init__.py` 中调用 `init_versioning()`
- 导入 `database` 模块时自动执行初始化
- 模型可以分散在多个文件中
- 符合模块化设计原则
- **关键**：先初始化启动监听器，再导入模型时自动注册并配置

#### 方式2：在应用入口 `app.py` 中初始化

**适用场景**：小型项目，启动流程一目了然

**项目结构**：
```
project/
├── database/
│   ├── __init__.py
│   └── models/
│       └── ...
└── app.py               # ← 在这里初始化
```

**核心代码**：

```python
# app.py
from yweb.orm import init_versioning
from yweb.orm.history import CurrentUserPlugin

# 1. 先初始化版本化
init_versioning(plugins=[CurrentUserPlugin()])

# 2. 再导入模型
from database import User, Article

# 3. 创建应用
app = FastAPI()
```

**说明**：
- 在应用入口文件中调用 `init_versioning()`
- 必须在导入模型之前初始化
- 启动流程集中在一个文件中
- 适合快速开发和小型项目
- **关键**：先初始化启动监听器，再导入模型时自动注册并配置

### 两种方式对比

| 特性 | 方式1（`__init__.py`） | 方式2（`app.py`） |
|------|----------------------|------------------|
| **初始化位置** | `database/__init__.py` | `app.py` |
| **执行时机** | 导入模块时自动执行 | 应用启动时执行 |
| **适用场景** | 大型项目、模块化管理 | 小型项目、快速开发 |
| **优点** | 模块化清晰、关注点分离 | 流程直观、集中管理 |
| **推荐度** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |

**核心原则**：
- `init_versioning()` 只能调用一次
- 必须在应用入口统一调用
- 不要在每个模型文件中分别调用
- 模型可以分散在多个文件中，监听器会自动配置
- **顺序很重要**：先初始化（启动监听器），再导入模型（自动注册并配置）

### 错误示例

❌ **不要在每个模型文件中分别调用**：

```python
# models/user.py
init_versioning(plugins=[CurrentUserPlugin()])  # 第一次调用

# models/article.py
init_versioning(plugins=[CurrentUserPlugin()])  # 被忽略！不会生效
```

### 检查是否已初始化

```python
from yweb.orm import is_versioning_initialized

if is_versioning_initialized():
    print("版本化已启用")
```
```

### 默认行为说明

当调用 `init_versioning()` 而不传入 `user_cls` 参数时，框架会自动发现项目中的 `User` 类：

```python
# ✅ 推荐：不传入 user_cls，让框架自动发现 User 类
init_versioning()

```

**自动发现机制**：
- SQLAlchemy-History 会在项目中查找名为 `User` 的类
- 如果找到，会自动将其用作版本记录的操作者模型
- 如果找不到，版本记录仍会正常工作，但不会记录操作者信息

#### 具体行为

1. 默认值为 "User" ：如果不指定，系统会默认查找名为 User 的类

2. 可以是类名或类对象 ：支持字符串形式（延迟评估）或直接传入类对象

3. 建立关系 ：系统会在 Transaction 类和指定的用户类之间创建数据库关系

4. 设置为 None 可禁用 ：如果不需要用户关联功能：init_versioning(user_cls=None)

## 当前用户追踪（审计功能）

YWeb ORM 提供了自动追踪操作者的功能，可以在历史记录中自动记录是谁执行了操作。

### 快速开始

只需在应用启动时启用 `CurrentUserPlugin` 并添加中间件，即可实现用户追踪：

```python
from fastapi import FastAPI
from yweb.orm import init_versioning, CurrentUserPlugin
from yweb.auth import JWTManager
from yweb.middleware import CurrentUserMiddleware

app = FastAPI()

# 1. 初始化版本化（显式启用 CurrentUserPlugin）
init_versioning(plugins=[CurrentUserPlugin()])

# 2. 配置 JWT 管理器
jwt_manager = JWTManager(secret_key="your-secret-key")

# 3. 添加中间件（一次配置，全局生效）
app.add_middleware(
    CurrentUserMiddleware,
    jwt_manager=jwt_manager,
    skip_paths=["/login", "/register", "/docs"]
)
```

之后，在 API 代码中需要手动桥接 user_id：

```python
from yweb.middleware import get_current_user_id
from yweb.orm.history import set_user

@app.post("/articles")
def create_article(title: str, content: str, session: Session = Depends(get_db)):
    # 手动桥接：从 ContextVar 获取 user_id 并设置到 session
    user_id = get_current_user_id()
    if user_id:
        set_user(session, user_id)
    
    # 执行业务操作
    article = Article(title=title, content=content)
    article.add(commit=True)
    return {"id": article.id}
```

> **重要说明**：
>
> - `CurrentUserMiddleware` 会将 user_id 存入 ContextVar（中间件层）
> - `sqlalchemy-history` 的 `CurrentUserPlugin` 从 `session.info` 读取 user_id（ORM 层）
> - 需要手动调用 `set_user(session, user_id)` 将 ContextVar 中的 user_id 桥接到 session.info
> - 这是因为 ContextVar 和 session.info 是两个独立的存储机制，需要手动桥接

### 工作原理

```
HTTP 请求 → CurrentUserMiddleware 解析 JWT → user_id 存入 ContextVar
                                                    ↓
业务代码执行 article.add() → sqlalchemy-history 触发 → CurrentUserPlugin 读取 ContextVar
                                                    ↓
                                          Transaction 表写入 user_id
```

### 中间件配置

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `jwt_manager` | JWTManager | 必填 | JWT 管理器实例 |
| `skip_paths` | List[str] | ["/docs", "/redoc", ...] | 跳过追踪的路径列表 |
| `user_id_extractor` | Callable | lambda data: data.user_id | 自定义 user_id 提取函数 |

```python
# 完整配置示例
app.add_middleware(
    CurrentUserMiddleware,
    jwt_manager=jwt_manager,
    skip_paths=["/login", "/register", "/health", "/docs", "/openapi.json"],
    user_id_extractor=lambda data: data.sub  # 从 sub 字段提取
)
```

### 手动设置（后台任务场景）

在后台任务、定时任务等无 HTTP 请求的场景，可以手动设置 user_id。

#### 方式一：ContextVar 方式（推荐用于 Web 请求上下文）

```python
from yweb.middleware import set_current_user_id, clear_current_user_id

def background_task():
    # 设置系统用户 ID
    set_current_user_id(system_user_id)
    
    try:
        # 执行操作
        article.status = "published"
        article.save(commit=True)  # 记录为 system_user_id 的操作
    finally:
        # 清理
        clear_current_user_id()
```

#### 方式二：Session 方式（推荐用于直接操作 Session）

```python
from yweb.orm.history import set_user, get_user_id, clear_user

def batch_operation(session):
    # 设置当前用户（支持用户对象或用户ID）
    set_user(session, user)        # 传入用户对象
    set_user(session, user_id)     # 或传入用户ID
    
    try:
        # 执行操作
        article.title = "新标题"
        session.commit()  # 记录为 user_id 的操作
    finally:
        # 清理
        clear_user(session)
```

### user_cls 配置场景

| 场景 | 配置方式 | 说明 |
|------|---------|------|
| 默认 User 类 | `init_versioning()` | 自动查找名为 "User" 的类 |
| 自定义类名 | `init_versioning(user_cls="MyUser")` | 指定用户模型类名 |
| 启用用户追踪 | `init_versioning(plugins=[CurrentUserPlugin()])` | 启用操作者追踪 |
| 自定义列名 | `init_versioning(plugins=[CurrentUserPlugin(user_column_name="operator_id")])` | Transaction 表列名 |

### 便捷函数

YWeb 提供两套 API 来管理当前用户，适用于不同场景：

#### ContextVar 方式（中间件层，用于 Web 请求）

从 `yweb.middleware` 导入，基于 Python `ContextVar`，适用于 FastAPI 中间件自动追踪：

| 函数 | 说明 |
|------|------|
| `set_current_user_id(user_id)` | 设置当前用户 ID（存入 ContextVar） |
| `get_current_user_id()` | 获取当前用户 ID |
| `clear_current_user_id()` | 清除当前用户 ID |

```python
from yweb.middleware import set_current_user_id, get_current_user_id, clear_current_user_id
```

#### Session 方式（ORM 层，用于直接操作 Session）

从 `yweb.orm.history` 导入，基于 `session.info` 字典，适用于后台任务、脚本等直接操作 Session 的场景：

| 函数 | 说明 |
|------|------|
| `set_user(session, user)` | 设置当前用户（支持用户对象或用户ID） |
| `get_user_id(session)` | 获取当前用户 ID |
| `clear_user(session)` | 清除当前用户 |

```python
from yweb.orm.history import set_user, get_user_id, clear_user

# 使用示例
set_user(session, user)      # 传入用户对象（自动提取主键）
set_user(session, 123)       # 传入整数 ID
set_user(session, "uuid-xx") # 传入字符串 ID
```

> **注意**：`set_user` 支持传入 SQLAlchemy 模型对象或普通 Python 对象（需有 `id` 属性），会自动提取主键值。

### 高级配置

> **全局配置说明**：以下所有参数都是全局配置，影响整个应用的所有版本化模型。

`init_versioning` 函数支持以下参数：

| 参数                | 类型 | 说明                                    |
| ------------------- | ---- | --------------------------------------- |
| `user_cls`        | Type | 用户模型类，用于记录变更操作者          |
| `transaction_cls` | Type | 自定义 Transaction 类，用于自定义事务表 |
| `options`         | dict | 配置字典，支持多种选项                  |
| `unit_of_work_cls` | Type | 可选的工作单元类，用于处理版本化生命周期操作 |
| `plugins`         | List | 插件列表，如需用户追踪请传入 `[CurrentUserPlugin()]` |
| `builder`         | Any  | 可选的构建器对象，用于处理版本化模型和架构的构建 |
| `manager`         | Any  | 可选的 VersioningManager 实例，如果提供，将直接使用此 manager（提供最大灵活性） |

#### options 配置选项

| 选项                            | 默认值                   | 说明                                  |
| ------------------------------- | ------------------------ | ------------------------------------- |
| `table_name`                  | `'%s_version'`         | 历史表名模板，`%s` 会被替换为原表名 |
| `transaction_column_name`     | `'transaction_id'`     | 事务ID列名                            |
| `end_transaction_column_name` | `'end_transaction_id'` | 结束事务ID列名                        |
| `operation_type_column_name`  | `'operation_type'`     | 操作类型列名                          |

### 自定义历史表名

```python
# 将历史表名从 xxx_version 改为 xxx_history
init_versioning(options={'table_name': '%s_history'})
```

### 自定义 Transaction 表（推荐方式）

默认情况下，sqlalchemy-history 会创建一个名为 `transaction` 的表来记录事务信息。

> **重要限制**：由于 `sqlalchemy-history` 的设计限制，所有版本化模型共享同一个 Transaction 表。无法为不同的模型使用不同的 Transaction 表。如需分离，考虑使用不同的数据库或 schema。

如果需要自定义 Transaction 表（表名、字段等），**推荐使用 `IdModel`** 作为基类：

```python
from yweb.orm import init_versioning, IdModel, configure_primary_key, IdType
from sqlalchemy_history.transaction import TransactionBase
from sqlalchemy_history.manager import VersioningManager
from sqlalchemy.orm import mapped_column
from sqlalchemy import String

# 1. 先配置全局主键策略（可选，Transaction 表会自动使用此配置）
configure_primary_key(strategy=IdType.SNOWFLAKE)

# 2. 创建自定义 Transaction 类（继承 IdModel）
class AuditLog(IdModel, TransactionBase):
    """自定义审计日志表 - 替代默认的 transaction 表"""
    __tablename__ = "audit_log"  # 自定义表名
    
    # id 会自动根据 IdModel 的全局配置生成（无需手动定义）
    
    # 可以添加自定义字段
    remote_addr = mapped_column(String(50), comment="客户端IP")
    request_id = mapped_column(String(64), comment="请求ID")
    operation_reason = mapped_column(String(500), comment="操作原因")

# 3. 创建自定义 manager
custom_manager = VersioningManager(transaction_cls=AuditLog)

# 4. 初始化版本化
init_versioning(manager=custom_manager)
```

#### 为什么使用 IdModel？

`IdModel` 是专门为主键管理设计的轻量级基类：

| 特性 | 说明 |
|------|------|
| 自动主键类型 | 根据全局配置自动选择主键类型（自增、雪花ID、UUID等） |
| 统一主键策略 | 确保 Transaction 表与业务模型使用相同的主键策略 |
| 无额外字段 | 不包含 `created_at`、`updated_at` 等字段，避免与 `TransactionBase` 冲突 |

#### 注意事项

⚠️ **不要手动定义 id 字段**：`IdModel` 会自动根据全局配置生成主键，手动定义可能导致类型冲突。

```python
# ❌ 错误：手动定义 id 会与 IdModel 冲突
class AuditLog(IdModel, TransactionBase):
    __tablename__ = "audit_log"
    id = Column(BigInteger, primary_key=True)  # 不要这样做！

# ✅ 正确：让 IdModel 自动处理
class AuditLog(IdModel, TransactionBase):
    __tablename__ = "audit_log"
    # id 自动生成，无需定义
    remote_addr = mapped_column(String(50))
```

### 使用 manager 参数（高级用法）

如果需要完全自定义 VersioningManager，可以直接传入 `manager` 参数：

```python
from yweb.orm import init_versioning, IdModel, configure_primary_key, IdType
from sqlalchemy_history.manager import VersioningManager
from sqlalchemy_history.transaction import TransactionBase
from sqlalchemy.orm import mapped_column
from sqlalchemy import String

# 配置主键策略
configure_primary_key(strategy=IdType.UUID)

# 定义自定义 Transaction 类
class AuditLog(IdModel, TransactionBase):
    __tablename__ = "audit_log"
    # id 自动使用 UUID 类型
    
    remote_addr = mapped_column(String(50), comment="客户端IP")
    user_agent = mapped_column(String(200), comment="用户代理")

# 创建自定义 manager
custom_manager = VersioningManager(
    transaction_cls=AuditLog,
    user_cls=User,  # 可选：记录操作用户
    plugins=[MyCustomPlugin()],  # 可选：自定义插件
    options={'table_name': '%s_history'}  # 可选：历史表名模板
)

# 使用自定义 manager 初始化
init_versioning(manager=custom_manager)
```

> **注意**：如果提供了 `manager` 参数，其他参数（除 `options` 外）将被忽略。

### IdModel vs CoreModel

| 基类 | 包含字段 | 适用场景 |
|------|----------|----------|
| `IdModel` | 仅主键 `id` | 自定义 Transaction 表（推荐） |
| `CoreModel` | `id` + `created_at` + `updated_at` + `deleted_at` + `ver` | 业务模型 |
| `BaseModel` | CoreModel 字段 + `name` + `code` + `note` + `caption` | 带常用业务字段的模型 |

对于 Transaction 表，`IdModel` 是最佳选择，因为它：
- 只提供必要的主键功能
- 不会与 `TransactionBase` 的 `issued_at` 等字段冲突
- 自动与全局主键策略保持一致

### 配置主键策略（重要）

⚠️ **重要**：如需使用自定义主键策略（如 short_uuid、snowflake 等），必须在调用 `init_versioning()` **之前**先调用 `configure_primary_key()`，因为 Transaction 表的主键类型在此时确定。

```python
from yweb.orm import configure_primary_key, init_versioning

# ✅ 正确顺序：先配置主键策略，再初始化版本化
configure_primary_key(strategy="short_uuid", short_uuid_length=10)
init_versioning()

# ❌ 错误顺序：这会导致 Transaction 表使用默认的整数主键
# init_versioning()
# configure_primary_key(strategy="short_uuid")  # 太晚了！
```

### 完整配置示例

```python
from yweb.orm import init_versioning

# 组合多个配置
init_versioning(
    user_cls=User,  # 记录操作用户
    options={
        'table_name': '%s_history',  # 历史表名模板
    }
)
```

### 定义版本化模型

#### 方式一：使用 enable_history（推荐）

最简单的方式，只需在模型类中设置 `enable_history = True`：

```python
from yweb.orm import BaseModel, CoreModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers

# 使用 BaseModel（推荐，包含 name/code 等常用字段）
class Article(BaseModel):
    __tablename__ = "article"
    
    enable_history = True  # 启用历史版本记录
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(2000))

# 或者使用 CoreModel（更轻量，只包含基础字段）
class Document(CoreModel):
    __tablename__ = "document"
    
    enable_history = True  # 启用历史版本记录
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(2000))

# 配置 mappers（必须）
configure_mappers()
```

#### 方式二：使用 __versioned__（高级配置）

如果需要更多自定义配置，可以直接使用 `__versioned__`：

```python
from yweb.orm import BaseModel
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers

class Article(BaseModel):
    __tablename__ = "article"
    
    # 使用 __versioned__ 进行高级配置
    __versioned__ = {
        'table_name': 'article_%s_history',  # 自定义历史表名前缀
        'exclude': ['updated_at', 'view_count']  # 排除的字段
    }
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(2000))

# 配置 mappers（必须）
configure_mappers()
```

#### BaseModel vs CoreModel

- **CoreModel**：基础模型类，包含 id、created_at、updated_at 等基础字段
- **BaseModel**：继承自 CoreModel，额外包含 name、code、note、caption 等常用业务字段

两者都支持 `enable_history`，根据实际需求选择即可。

## 基本使用

### 自动记录历史

```python
# 创建记录
article = Article(title="原始标题", content="原始内容")
session.add(article)
session.commit()  # 记录版本 1（transaction_id = 1）

# 更新记录
article.title = "修改后的标题"
session.commit()  # 记录版本 2（transaction_id = 2）

# 再次更新
article.content = "修改后的内容"
session.commit()  # 记录版本 3（transaction_id = 3）
```

> **注意**：版本号就是 `transaction_id`，可以通过历史记录的 `transaction_id` 字段访问。

### 查看历史记录

#### 使用函数方式

```python
from yweb.orm import get_history

# 获取所有历史记录
# 注意：参数名是 instance_id
history = get_history(Article, instance_id=article.id, session=session)

for record in history:
    print(f"版本: {record['transaction_id']}")
    print(f"标题: {record['title']}")
    print(f"操作: {record['operation_type']}")
```

#### 使用实例方法（推荐）

```python
# 获取实例后直接调用方法
article = Article.query.filter_by(id=1).first()

# 获取所有历史记录
history = article.get_history()

# 或者使用便捷属性
for record in article.history:
    print(f"版本: {record['transaction_id']}")
    print(f"标题: {record['title']}")
    print(f"操作: {record['operation_type']}")
```

#### 使用类方法

```python
# 不需要先获取实例，直接通过 ID 查询
history = Article.get_history_by_id(instance_id=1, session=session)
```

### 获取历史数量

#### 使用函数方式

```python
from yweb.orm import get_history_count

count = get_history_count(Article, instance_id=article.id, session=session)
print(f"共有 {count} 个历史版本")
```

#### 使用实例属性（推荐）

```python
article = Article.query.filter_by(id=1).first()
print(f"共有 {article.history_count} 个历史版本")
```

#### 使用类方法

```python
count = Article.get_history_count_by_id(instance_id=1, session=session)
print(f"共有 {count} 个历史版本")
```

### 限制返回数量

#### 使用函数方式

```python
# 只获取最近 5 条历史
history = get_history(Article, instance_id=article.id, limit=5, session=session)
```

#### 使用实例方法

```python
article = Article.query.filter_by(id=1).first()
# 只获取最近 5 条历史
history = article.get_history(limit=5)
```

#### 只获取特定字段

```python
# 只获取 title 和 content 字段
history = article.get_history(field_names=['title', 'content', 'transaction_id'])
```

## 版本比较

### 获取版本差异

#### 使用函数方式

```python
from yweb.orm import get_history_diff

# 比较两个版本的差异
diff = get_history_diff(
    Article,
    instance_id=article.id,
    from_version=1,
    to_version=3,
    session=session,
    exclude_fields={'updated_at'}  # 可选：排除的字段
)

if diff:
    for field, changes in diff.items():
        print(f"{field}: {changes['from']} -> {changes['to']}")
```

#### 使用实例方法（推荐）

```python
article = Article.query.filter_by(id=1).first()

# 比较两个版本的差异
diff = article.get_history_diff(
    from_version=1,
    to_version=3,
    exclude_fields={'updated_at'}  # 可选：排除的字段
)

if diff:
    for field, changes in diff.items():
        print(f"{field}: {changes['from']} -> {changes['to']}")
```

### 差异格式

```python
# 返回格式
{
    "title": {
        "from": "原始标题",
        "to": "修改后的标题"
    },
    "content": {
        "from": "原始内容",
        "to": "修改后的内容"
    }
}
```

## 文本细节差异

对于长文本字段（如文章内容），除了知道"哪个字段变了"，通常还需要知道"具体哪里变了"。`get_field_text_diff` 函数使用 Python 内置的 `difflib` 库提供精确到行/字符级别的差异对比。

### 获取文本细节差异

#### 使用函数方式

```python
from yweb.orm import get_field_text_diff

# 获取文章内容字段的详细差异
detail = get_field_text_diff(
    Article,
    instance_id=article.id,
    field_name="content",
    from_version=1,
    to_version=3,
    session=session
)

if detail:
    print(f"字段: {detail['field']}")
    print(f"变更统计: +{detail['stats']['added']} -{detail['stats']['removed']}")
    print(detail["diff"])
```

#### 使用实例方法（推荐）

```python
article = Article.query.filter_by(id=1).first()

# 获取文章内容字段的详细差异
detail = article.get_field_text_diff(
    field_name="content",
    from_version=1,
    to_version=3,
    output_format="unified",  # 或 "html", "inline", "opcodes"
    context_lines=3
)

if detail:
    print(f"字段: {detail['field']}")
    print(f"变更统计: +{detail['stats']['added']} -{detail['stats']['removed']}")
    print(detail["diff"])
```

### 输出格式

`get_field_text_diff` 支持 4 种输出格式：

| 格式        | 说明                     | 适用场景           |
| ----------- | ------------------------ | ------------------ |
| `unified` | 类似 git diff 的统一格式 | 开发调试、日志记录 |
| `inline`  | 结构化列表格式           | 前端自定义渲染     |
| `html`    | HTML 表格格式            | 直接在浏览器展示   |
| `opcodes` | 操作码格式               | 程序化处理         |

#### unified 格式（默认）

```python
detail = get_field_text_diff(
    Article, article.id, "content", 1, 3,
    output_format="unified",
    context_lines=3,  # 上下文行数
    session=session
)

print(detail["diff"])
# 输出类似 git diff：
# --- v1
# +++ v3
# @@ -1,3 +1,3 @@
#  这是第一段。
# -这是被删除的句子。
# +这是新增的句子。
#  这是第三段。
```

#### inline 格式

```python
detail = get_field_text_diff(
    Article, article.id, "content", 1, 3,
    output_format="inline",
    session=session
)

# 返回结构化列表，便于前端渲染
for item in detail["diff"]:
    if item["type"] == "delete":
        print(f"- {item['text']}")  # 删除的行
    elif item["type"] == "insert":
        print(f"+ {item['text']}")  # 新增的行
    else:
        print(f"  {item['text']}")  # 未变化的行
```

#### html 格式

```python
detail = get_field_text_diff(
    Article, article.id, "content", 1, 3,
    output_format="html",
    session=session
)

# detail["diff"] 是完整的 HTML 表格，可直接渲染
html_content = detail["diff"]
```

#### opcodes 格式

```python
detail = get_field_text_diff(
    Article, article.id, "content", 1, 3,
    output_format="opcodes",
    session=session
)

# 返回字符级别的操作指令
for op in detail["diff"]:
    if op["operation"] == "replace":
        print(f"替换: '{op['from_text']}' -> '{op['to_text']}'")
    elif op["operation"] == "insert":
        print(f"新增: '{op['to_text']}'")
    elif op["operation"] == "delete":
        print(f"删除: '{op['from_text']}'")
```

### 返回格式

```python
{
    "field": "content",           # 字段名
    "from_version": 1,            # 起始版本
    "to_version": 3,              # 目标版本
    "from_value": "原始文本...",   # 原始值
    "to_value": "修改后文本...",   # 新值
    "diff": ...,                  # 差异（格式取决于 output_format）
    "stats": {                    # 行级统计
        "added": 2,               # 新增行数
        "removed": 1,             # 删除行数
        "changed": 0              # 修改行数
    }
}
```

### 结合 get_history_diff 使用

推荐的工作流：先用 `get_history_diff` 找出哪些字段变了，再对感兴趣的字段使用 `get_field_text_diff` 获取细节。

#### 使用函数方式

```python
from yweb.orm import get_history_diff, get_field_text_diff

# 1. 找出哪些字段变了
diff = get_history_diff(Article, instance_id=article.id, from_version=1, to_version=3, session=session)

if diff:
    print(f"变更的字段: {list(diff.keys())}")
  
    # 2. 对文本字段获取细节差异
    if "content" in diff:
        detail = get_field_text_diff(
            Article, instance_id=article.id, field_name="content", 
            from_version=1, to_version=3,
            output_format="unified",
            session=session
        )
        print("内容变更详情:")
        print(detail["diff"])
```

#### 使用实例方法（推荐）

```python
article = Article.query.filter_by(id=1).first()

# 1. 找出哪些字段变了
diff = article.get_history_diff(from_version=1, to_version=3)

if diff:
    print(f"变更的字段: {list(diff.keys())}")
  
    # 2. 对文本字段获取细节差异
    if "content" in diff:
        detail = article.get_field_text_diff(
            field_name="content",
            from_version=1,
            to_version=3,
            output_format="unified"
        )
        print("内容变更详情:")
        print(detail["diff"])
```

## 版本恢复

### 恢复到指定版本

#### 使用函数方式

```python
from yweb.orm import restore_to_version

# 恢复到版本 1
restored = restore_to_version(
    Article,
    instance_id=article.id,
    version=1,
    session=session,
    exclude_fields={'id', 'created_at'}  # 可选：恢复时要排除的字段
)

if restored:
    print(f"已恢复到版本 1: {restored.title}")
    session.commit()
```

#### 使用实例方法（推荐）

```python
article = Article.query.filter_by(id=1).first()

# 恢复到版本 1
restored = article.restore_to_version(
    version=1,
    exclude_fields={'id', 'created_at'}  # 可选：恢复时要排除的字段
)

if restored:
    print(f"已恢复到版本 1: {restored.title}")
    session.commit()
```

## 获取版本类

```python
from yweb.orm import get_version_class

# 获取历史模型类
ArticleVersion = get_version_class(Article)

# 直接查询历史表
versions = session.query(ArticleVersion).filter(
    ArticleVersion.id == article.id
).all()
```

## 实例方法和属性

所有继承 `CoreModel` 或 `BaseModel` 并启用 `enable_history = True` 的模型，都会自动获得以下实例方法和属性：

### 实例方法

#### `get_history(version=None, limit=100, field_names=None)`

获取当前实例的历史记录。

```python
article = Article.query.filter_by(id=1).first()

# 获取所有历史记录
history = article.get_history()

# 获取特定版本
history = article.get_history(version=5)

# 只获取特定字段
history = article.get_history(field_names=['title', 'content', 'transaction_id'])

# 限制返回数量
history = article.get_history(limit=10)
```

#### `get_history_diff(from_version, to_version, exclude_fields=None)`

比较两个版本之间的差异。

```python
article = Article.query.filter_by(id=1).first()

diff = article.get_history_diff(
    from_version=1,
    to_version=3,
    exclude_fields={'updated_at'}  # 可选：排除的字段
)

if diff:
    for field, changes in diff.items():
        print(f"{field}: {changes['from']} -> {changes['to']}")
```

#### `get_field_text_diff(field_name, from_version, to_version, output_format="unified", context_lines=3)`

获取单个字段的文本细节差异。

```python
article = Article.query.filter_by(id=1).first()

# 获取 unified diff（类似 git diff）
detail = article.get_field_text_diff(
    field_name="content",
    from_version=1,
    to_version=3,
    output_format="unified",
    context_lines=3
)

# 获取 HTML 格式
detail = article.get_field_text_diff(
    field_name="content",
    from_version=1,
    to_version=3,
    output_format="html"
)
```

#### `restore_to_version(version, exclude_fields=None)`

恢复当前实例到指定版本。

```python
article = Article.query.filter_by(id=1).first()

# 恢复到版本 2
restored = article.restore_to_version(
    version=2,
    exclude_fields={'id', 'created_at'}  # 可选：排除的字段
)

if restored:
    session.commit()
```

### 实例属性

#### `history`

便捷属性，获取所有历史记录（等同于 `get_history()`）。

```python
article = Article.query.filter_by(id=1).first()

for record in article.history:
    print(f"版本 {record['transaction_id']}: {record['title']}")
```

#### `history_count`

便捷属性，获取历史记录数量（等同于 `get_history_count()`）。

```python
article = Article.query.filter_by(id=1).first()
print(f"共有 {article.history_count} 个历史版本")
```

### 类方法

#### `get_history_by_id(instance_id, version=None, limit=100, session=None, field_names=None)`

根据 ID 获取历史记录，不需要先获取实例。

```python
# 不需要先查询实例
history = Article.get_history_by_id(instance_id=1, session=session)

# 获取特定版本
history = Article.get_history_by_id(instance_id=1, version=5, session=session)
```

#### `get_history_count_by_id(instance_id, session=None)`

根据 ID 获取历史记录数量，不需要先获取实例。

```python
count = Article.get_history_count_by_id(instance_id=1, session=session)
print(f"共有 {count} 个历史版本")
```

## __versioned__ 配置选项

如果使用 `__versioned__` 进行高级配置，支持以下选项：

```python
class Article(BaseModel):
    __tablename__ = "article"
    
    __versioned__ = {
        'table_name': 'article_%s_history',  # 自定义历史表名前缀
        'exclude': ['updated_at', 'view_count']  # 排除的字段
    }
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(String(2000))
```

## 与软删除配合

### 软删除后保留历史

```python
from yweb.orm import BaseModel, SimpleSoftDeleteMixin

class Article(BaseModel, SimpleSoftDeleteMixin):
    __tablename__ = "article"
    enable_history = True  # 启用历史版本记录

    title: Mapped[str] = mapped_column(String(200))

# 软删除不会删除历史记录
article.delete(True)

# 历史记录仍然可以查询
history = article.get_history()
# 或使用函数方式
from yweb.orm import get_history
history = get_history(Article, instance_id=article.id, session=session)
```

### 历史记录不受软删除影响

```python
# 软删除主记录
article.delete(True)

# 历史表中的数据物理存在
ArticleVersion = get_version_class(Article)
versions = session.query(ArticleVersion).filter(
    ArticleVersion.id == article.id
).all()
print(f"历史记录数: {len(versions)}")  # 不受影响
```

## 在 FastAPI 中使用

### 查看历史 API

```python
from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from yweb.orm import get_db, get_history

app = FastAPI()

@app.get("/articles/{article_id}/history")
def get_article_history(
    article_id: int,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    # 使用函数方式
    history = get_history(Article, instance_id=article_id, limit=limit, session=db)
    if history is None:
        return {"error": "文章不存在"}
    return {"history": history}
    
    # 或使用类方法
    # history = Article.get_history_by_id(instance_id=article_id, limit=limit, session=db)
```

### 版本比较 API

```python
@app.get("/articles/{article_id}/diff")
def get_article_diff(
    article_id: int,
    from_version: int,
    to_version: int,
    db: Session = Depends(get_db)
):
    diff = get_history_diff(
        Article, 
        instance_id=article_id,
        from_version=from_version,
        to_version=to_version,
        session=db,
        exclude_fields={'updated_at'}  # 可选：排除的字段
    )
    if diff is None:
        return {"error": "版本不存在"}
    return {"diff": diff}
```

### 恢复版本 API

```python
@app.post("/articles/{article_id}/restore/{version}")
def restore_article_version(
    article_id: int,
    version: int,
    db: Session = Depends(get_db)
):
    restored = restore_to_version(
        Article, 
        instance_id=article_id,
        version=version,
        session=db,
        exclude_fields={'id', 'created_at'}  # 可选：排除的字段
    )
    if restored is None:
        return {"error": "恢复失败"}

    db.commit()
    return {"message": "恢复成功", "article": restored.to_dict()}
```

### 文本细节差异 API

```python
from yweb.orm import get_field_text_diff
from typing import Literal

@app.get("/articles/{article_id}/text-diff")
def get_article_text_diff(
    article_id: int,
    field: str,
    from_version: int,
    to_version: int,
    format: Literal["unified", "inline", "html", "opcodes"] = "unified",
    db: Session = Depends(get_db)
):
    detail = get_field_text_diff(
        Article, 
        instance_id=article_id,
        field_name=field,
        from_version=from_version,
        to_version=to_version,
        output_format=format,
        session=db
    )
    if detail is None:
        return {"error": "版本不存在"}
    return detail
```

## 最佳实践

### 1. 在应用启动时初始化

```python
# main.py
from yweb.orm import init_versioning

# 在导入模型之前初始化
init_versioning()

# 然后导入模型
from models import Article
```

### 2. 排除不需要记录的字段

```python
class Article(BaseModel):
    __tablename__ = "article"
    enable_history = True
    
    __versioned__ = {
        'exclude': ['updated_at', 'view_count']  # 排除的字段
    }
    
    title: Mapped[str] = mapped_column(String(200))
```

### 3. 定期清理历史数据

```python
from datetime import datetime, timedelta

def cleanup_old_history(days: int = 90):
    """清理 N 天前的历史记录"""
    cutoff = datetime.now() - timedelta(days=days)

    ArticleVersion = get_version_class(Article)
    session.query(ArticleVersion).filter(
        ArticleVersion.transaction.has(
            Transaction.issued_at < cutoff
        )
    ).delete(synchronize_session=False)

    session.commit()
```

## 常见问题

### Q1: 历史记录表在哪里？

历史记录存储在自动生成的表中，表名通常是 `{原表名}_version`。可以通过 `options={'table_name': '%s_history'}` 自定义。

### Q2: Transaction 表是什么？

`transaction` 表是 sqlalchemy-history 自动创建的事务日志表，用于：

- 记录每次数据库提交的时间点
- 为历史记录提供 `transaction_id` 关联（版本号就是 `transaction_id`）
- 追踪同一事务中的多个变更

**重要限制**：由于 `sqlalchemy-history` 的设计限制，所有版本化模型共享同一个 Transaction 表。无法为不同的模型使用不同的 Transaction 表。如需分离，考虑使用不同的数据库或 schema。

如需自定义表名，参考上方 "自定义 Transaction 表名" 章节。

### Q3: 如何禁用某个模型的版本化？

不设置 `enable_history = True` 或不定义 `__versioned__` 即可：

```python
class LogEntry(BaseModel):  # 不设置 enable_history
    __tablename__ = "log_entry"
    # enable_history = False  # 默认就是 False，可以不写
```

### Q4: 版本号是如何生成的？

版本号就是 `transaction_id`，每次 commit 都会生成新的 transaction，`transaction_id` 就是版本号。可以通过 `record['transaction_id']` 访问。

### Q5: 历史记录会影响性能吗？

会有一定影响，因为每次更新都会写入历史表。对于高频更新的表，建议：

- 排除不重要的字段
- 定期清理历史数据
- 考虑是否真的需要历史记录

## 下一步

- [09_版本控制](09_version_control.md) - 了解乐观锁机制
- [07_软删除](07_soft_delete.md) - 学习软删除功能
