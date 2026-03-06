# YWeb 缓存指南

本指南介绍 YWeb 提供的通用缓存装饰器，帮助你快速为应用添加函数级缓存功能，提升性能。

## 目录

- [设计背景](#设计背景)
- [核心概念](#核心概念)
- [快速开始](#快速开始)
- [缓存装饰器](#缓存装饰器)
- [缓存管理](#缓存管理)
- [自动缓存失效](#自动缓存失效)
- [缓存后端](#缓存后端)
- [缓存管理 API](#缓存管理-api)
- [认证缓存实践](#认证缓存实践)
- [最佳实践](#最佳实践)
- [API 参考](#api-参考)

---

## 设计背景

### 问题场景

在典型的 Web 应用中，每次 API 请求都需要进行用户认证：

```
请求 → 提取 Token → 验证签名 → 查询数据库获取用户 → 执行业务逻辑
                                    ↑
                              这里是性能瓶颈
```

每次请求都查询数据库会带来：
- 数据库连接池压力
- 网络往返开销
- 高并发时延迟累积

### 解决方案

使用 `@cached` 装饰器缓存函数调用结果：

```python
from yweb.cache import cached

@cached(ttl=60)  # 缓存 60 秒
def get_user_by_id(user_id: int) -> Optional[User]:
    return User.get_by_id(user_id)
```

**效果：**
- 第一次调用：查询数据库，结果存入缓存
- 后续调用：直接返回缓存，不查数据库
- 60 秒后：缓存过期，重新查询

---

## 核心概念

### 设计原则

| 原则 | 说明 |
|------|------|
| **类型无关** | 缓存的是「函数调用结果」，不关心返回什么类型 |
| **非侵入式** | 不需要修改原有代码，加个装饰器即可 |
| **可插拔后端** | 支持内存缓存和 Redis 缓存，通过参数切换 |
| **自动失效** | 通过 `cache_invalidator` 监听 ORM 事件，模型变更时自动失效 |
| **手动失效** | 也提供 `.invalidate()` 方法，支持特殊场景手动控制 |

### 缓存流程

```
┌──────────────────────────────────────────────────────────────┐
│                       @cached 装饰器流程                      │
└──────────────────────────────────────────────────────────────┘

     调用 get_user(123)
            │
            ▼
    ┌───────────────────┐
    │  生成缓存键        │
    │  "get_user:123"   │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐     命中      ┌───────────────────┐
    │  查询缓存          │ ───────────► │  直接返回缓存值    │
    └─────────┬─────────┘              └───────────────────┘
              │ 未命中
              ▼
    ┌───────────────────┐
    │  调用原函数        │
    │  User.get_by_id() │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │  结果写入缓存      │
    │  TTL = 60 秒      │
    └─────────┬─────────┘
              │
              ▼
    ┌───────────────────┐
    │  返回结果          │
    └───────────────────┘
```

---

## 快速开始

### 安装依赖

```bash
pip install cachetools  # 内存缓存依赖
pip install redis       # Redis 缓存依赖（可选）
```

### 基本用法

```python
from yweb.cache import cached
from typing import Optional

# 1. 添加缓存装饰器
@cached(ttl=60)
def get_user_by_id(user_id: int) -> Optional[User]:
    """获取用户（带缓存）"""
    return User.get_by_id(user_id)

# 2. 正常调用函数
user = get_user_by_id(123)  # 第一次：查数据库
user = get_user_by_id(123)  # 第二次：返回缓存

# 3. 数据变更时失效缓存
def update_user(user_id: int, data: dict):
    user = User.get_by_id(user_id)
    user.update(**data)
    
    # 失效缓存，下次查询会重新从数据库获取
    get_user_by_id.invalidate(user_id)
```

---

## 缓存装饰器

### @cached - 通用缓存(推荐)

```python
from yweb.cache import cached

@cached(
    ttl=60,              # 缓存过期时间（秒），默认 300
    maxsize=1000,        # 最大缓存条目数，默认 1000
    backend="memory",    # 后端类型："memory" 或 "redis"
    redis=None,          # Redis 客户端（backend="redis" 时必须）
    key_prefix=None,     # 缓存键前缀，默认使用函数名
    key_builder=None,    # 自定义缓存键生成函数（高级用法）
    enable_stats=True,   # 是否启用统计
)
def my_function(arg1, arg2):
    ...
```

**高级参数说明：**

- `key_builder`: 自定义缓存键生成函数，接收 `(func, args, kwargs)` 参数，返回字符串作为缓存键。默认使用函数名和参数生成键。

**使用示例：**

```python
# 自定义缓存键生成逻辑
def custom_key_builder(func, args, kwargs):
    # 只使用第一个参数作为键
    return f"{func.__name__}:{args[0]}"

@cached(ttl=60, key_builder=custom_key_builder)
def get_user_info(user_id: int, include_details: bool = False):
    # 无论 include_details 是什么值，都使用相同的缓存键
    return User.get_by_id(user_id)
```
```

### @memory_cache - 内存缓存（简写）

```python
from yweb.cache import memory_cache

@memory_cache(ttl=60, maxsize=1000)
def get_config(key: str) -> dict:
    return Config.get_by_key(key)
```

### @redis_cache - Redis 缓存（简写）

```python
from yweb.cache import redis_cache
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

@redis_cache(redis=redis_client, ttl=300)
def get_user(user_id: int) -> Optional[User]:
    return User.get_by_id(user_id)
```

### 内存 vs Redis 对比

| 特性 | 内存缓存 | Redis 缓存 |
|------|---------|-----------|
| 速度 | 微秒级 | 毫秒级 |
| 容量 | 受内存限制 | 可扩展 |
| 多实例共享 | ❌ | ✅ |
| 持久化 | ❌ | ✅ |
| 序列化 | 无（直接存 Python 对象引用） | pickle（默认，支持 ORM 模型） |
| 适用场景 | 单实例、热点数据 | 分布式、大规模 |

---

## 缓存管理

装饰后的函数会自动获得以下管理方法：

### invalidate() - 失效单个

```python
@cached(ttl=60)
def get_user(user_id: int):
    return User.get_by_id(user_id)

# 失效特定参数的缓存
get_user.invalidate(123)              # 位置参数
get_user.invalidate(user_id=123)      # 关键字参数
```

### invalidate_many() - 批量失效

```python
# 批量失效多个用户的缓存
get_user.invalidate_many([123, 456, 789])
```

### refresh() - 强制刷新

```python
# 先失效缓存，再重新调用函数获取最新值
user = get_user.refresh(123)
```

### clear() - 清空所有

```python
# 清空此函数的所有缓存
get_user.clear()
```

### stats() - 查看统计

```python
stats = get_user.stats()
print(stats)
# {
#     'backend': 'memory',
#     'function': 'get_user',
#     'ttl': 60,
#     'size': 150,
#     'maxsize': 1000,
#     'hits': 1000,
#     'misses': 150,
#     'hit_rate': '86.96%',
#     'invalidations': 10
# }
```

---

## 自动缓存失效

手动调用 `invalidate()` 容易遗漏，yweb 提供了自动缓存失效功能，监听 SQLAlchemy 模型事件，实现自动失效。

### 推荐用法：装饰器声明（invalidate_on）

最简单的方式是在 `@cached` 装饰器中直接声明依赖的模型：

```python
from yweb import cached

# 单模型自动失效 —— User 变更时自动清除缓存
@cached(ttl=60, invalidate_on=User)
def get_user(user_id: int):
    return User.get(user_id)

# 多模型自动失效
@cached(ttl=60, invalidate_on=[User, Department])
def get_user_with_dept(user_id: int):
    user = User.get(user_id)
    dept = Department.get(user.dept_id)
    return {"user": user, "dept": dept}

# 自定义 key 提取器（关联模型场景）
@cached(ttl=60, invalidate_on={
    User: lambda user: user.id,
    Department: lambda dept: [e.user_id for e in dept.employees]  # 返回列表，批量失效
})
def get_user_with_dept(user_id: int):
    ...
```

**`invalidate_on` 参数支持三种形式：**

| 形式 | 示例 | 说明 |
|------|------|------|
| 单模型 | `invalidate_on=User` | User 变更时失效，默认用 `obj.id` 作为 key |
| 模型列表 | `invalidate_on=[User, Dept]` | 任一模型变更时失效 |
| 字典（自定义 key） | `invalidate_on={User: lambda u: u.id}` | 自定义从模型提取缓存 key |

### 工作原理

自动缓存失效采用**双路径**机制，同时覆盖单实体查询和列表查询：

#### 路径 1：key_extractor 精确失效（单实体查询）

适用于 `get_user(user_id)` 等参数就是实体 ID 的场景：

1. ORM 模型变更时触发 SQLAlchemy 事件
2. `key_extractor` 从实例提取 ID → 调用 `func.invalidate(id)`

#### 路径 2：依赖追踪失效（列表查询）

适用于 `get_orders(user_id, page)` 等参数不是实体 ID 的场景：

1. **缓存写入时**：自动扫描结果中的实体实例，建立反向索引 `(Model, entity_id) → {cache_keys}`
2. **实体变更时**：查反向索引，精确失效包含该实体的缓存条目

```
┌──────────────────────────────────────────────────────────────┐
│                  自动缓存失效（双路径）                         │
└──────────────────────────────────────────────────────────────┘

  路径 1（单实体）:
      user.update()  → after_update → key_extractor(user) → get_user.invalidate(123)

  路径 2（列表查询）:
      缓存写入时: get_orders(1, 1) → [Order(1), Order(2)] → 反向索引:
                  (Order, 1) → {"get_orders:1:1"}
                  (Order, 2) → {"get_orders:1:1"}

      Order(2) 变更时: 查反向索引 → 精确删除 "get_orders:1:1"
```

**两条路径自动生效，用户只需写 `invalidate_on=Model`，无需区分查询类型。**

### 手动注册方式（备选）

如果不使用 `invalidate_on` 参数，也可以手动调用 `cache_invalidator.register()` 注册：

```python
from yweb.cache import cached, cache_invalidator
from app.domain.auth.model.user import User

# 1. 定义带缓存的函数
@cached(ttl=60, key_prefix="user:auth")
def get_user_by_id(user_id: int) -> Optional[User]:
    user = User.get_by_id(user_id)
    if user and user.is_active:
        return user
    return None

# 2. 手动注册自动失效
cache_invalidator.register(User, get_user_by_id)

# 3. 之后 User 的任何 update/delete 都会自动失效缓存
# 不需要手动调用 invalidate！
```

### 自定义 Key 提取器

默认从模型提取 `id` 作为缓存键，可以自定义：

```python
# 按用户名缓存
@cached(ttl=60)
def get_user_by_username(username: str) -> Optional[User]:
    return User.query.filter_by(username=username).first()

# 注册时指定 key 提取器
cache_invalidator.register(
    User,
    get_user_by_username,
    key_extractor=lambda user: user.username  # 从 user 对象提取 username
)
```

### 监听特定事件

默认监听 `after_update` 和 `after_delete`，可以自定义：

```python
# 只在更新时失效（删除时不失效）
cache_invalidator.register(
    User,
    get_user_by_id,
    events=("after_update",)
)

# 也监听插入事件
cache_invalidator.register(
    User,
    get_user_list,
    events=("after_update", "after_delete", "after_insert")
)
```

### 注册多个缓存函数

一个模型可以关联多个缓存函数：

```python
cache_invalidator.register(User, get_user_by_id)
cache_invalidator.register(User, get_user_by_username, 
                           key_extractor=lambda u: u.username)
cache_invalidator.register(User, get_user_by_email,
                           key_extractor=lambda u: u.email)

# User 变更时，三个缓存都会自动失效
```

### 链式注册

```python
cache_invalidator \
    .register(User, get_user_by_id) \
    .register(Organization, get_org_by_id) \
    .register(Department, get_dept_by_id)
```

### 临时禁用自动失效

批量操作时可能需要临时禁用，避免频繁失效：

```python
from yweb.cache import no_auto_invalidation

# 批量导入时禁用自动失效
with no_auto_invalidation():
    for data in bulk_data:
        User.create(data)

# 导入完成后手动清空缓存
get_user_by_id.clear()
```

### 查看注册信息

```python
# 查看所有注册
print(cache_invalidator.get_registrations())
# {
#     'User': [
#         {'func': 'get_user_by_id', 'events': ('after_update', 'after_delete')},
#         {'func': 'get_user_by_username', 'events': ('after_update', 'after_delete')}
#     ],
#     'Organization': [...]
# }

# 查看特定模型
print(cache_invalidator.get_registrations(User))
```

### 取消注册

```python
# 取消特定函数的注册
cache_invalidator.unregister(User, get_user_by_id)

# 取消模型的所有注册
cache_invalidator.unregister(User)

# 清空所有注册
cache_invalidator.clear()
```

**使用场景示例：**

```python
# 场景1: 动态启用/禁用缓存
def enable_user_cache():
    """启用用户缓存"""
    cache_invalidator.register(User, get_user_by_id)

def disable_user_cache():
    """禁用用户缓存（用于调试或特殊场景）"""
    cache_invalidator.unregister(User, get_user_by_id)
    get_user_by_id.clear()  # 同时清空现有缓存

# 场景2: 测试环境清理
def teardown_test():
    """测试结束后清理所有缓存注册"""
    cache_invalidator.clear()
    # 清空所有缓存函数的缓存
    get_user_by_id.clear()
    get_org_by_id.clear()

# 场景3: 模块卸载时清理
def cleanup_module():
    """模块卸载时取消注册"""
    cache_invalidator.unregister(User)
    cache_invalidator.unregister(Organization)
```

### 模型兼容性说明

`cache_invalidator` 的自动失效功能对模型有一定要求：

| 场景 | 是否可用 | 需要做什么 |
|------|---------|-----------|
| 继承 CoreModel，主键是 `id` | ✅ 直接用 | 无需额外配置 |
| 继承 CoreModel，主键不是 `id` | ✅ 可用 | 自定义 `key_extractor` |
| 不继承 CoreModel 的 SQLAlchemy 模型 | ✅ 可用 | 自定义 `key_extractor` |
| 非 SQLAlchemy 模型 | ⚠️ 部分可用 | `@cached` 可用，自动失效不可用 |

**说明：**
- `@cached` 装饰器本身不依赖任何模型，可以缓存任意函数
- `cache_invalidator` 依赖 SQLAlchemy 的事件机制监听模型变更
- 默认 `key_extractor` 使用 `lambda obj: obj.id`，如果主键不是 `id`，需要自定义

```python
# 主键不是 id 的模型
class Product(Base):
    __tablename__ = 'product'
    product_id = Column(Integer, primary_key=True)  # 主键叫 product_id
    name = Column(String)

# 自定义 key_extractor
cache_invalidator.register(
    Product,
    get_product_by_id,
    key_extractor=lambda obj: obj.product_id  # 使用 product_id
)
```

### 列表查询与多实体缓存

`invalidate_on` 同时支持单实体查询和列表查询，**无需额外配置**：

```python
# 单实体查询 — key_extractor 路径自动命中
@cached(ttl=60, invalidate_on=Order)
def get_order(order_id: int):
    return Order.get(order_id)

# 列表查询 — 依赖追踪路径自动命中
@cached(ttl=60, invalidate_on=Order)
def get_orders(user_id: int, page: int):
    return Order.query.filter_by(user_id=user_id).paginate(page)

# 多模型组合查询
@cached(ttl=300, invalidate_on=[User, Department])
def get_user_with_dept(user_id: int):
    user = User.get(user_id)
    dept = Department.get(user.dept_id)
    return {"user": user, "dept": dept}
```

**列表查询示例**：`get_orders(1, 1)` 返回 `[Order(1), Order(2), Order(3)]` 时，框架自动建立反向索引。当 `Order(2)` 被更新，只有包含 `Order(2)` 的缓存条目被精确失效，其他用户的列表缓存不受影响。

#### 支持的结果类型

| 结果类型 | 示例 | 扫描行为 |
|---------|------|---------|
| 单对象 | `Order(id=1)` | 直接提取 |
| 列表/元组 | `[Order(1), Order(2)]` | 遍历每个元素 |
| 分页对象 | `Page(items=[...])` | 遍历 `items` 属性 |
| 非实体类型 | `dict`, `str`, `int` | 跳过（不追踪） |

---

## 缓存后端

### MemoryBackend

基于 `cachetools.TTLCache` 实现的本地内存缓存，支持 per-key TTL。

```python
from yweb.cache import MemoryBackend

backend = MemoryBackend(
    maxsize=1000,       # 最大条目数
    ttl=300,            # 默认 TTL
    enable_stats=True,  # 启用统计
)

# 直接操作
backend.set("key", "value")              # 使用默认 TTL（300 秒）
backend.set("key2", "value2", ttl=10)    # 自定义 TTL（10 秒后过期）
value = backend.get("key")
backend.delete("key")
backend.clear()
```

> **per-key TTL 说明：** 自定义 TTL 小于默认值时精确控制过期；大于默认值时以默认值为上限（TTLCache 会先行淘汰）。通过 `@cached` 使用时无需关心此细节，TTL 在装饰器参数中统一设置。

### RedisBackend

基于 Redis 的分布式缓存，默认使用 pickle 序列化，**支持缓存任意 Python 对象（包括 ORM 模型实例）**。

```python
from yweb.cache import RedisBackend
import redis

redis_client = redis.Redis(host='localhost', port=6379, db=0)

backend = RedisBackend(
    redis_client=redis_client,
    prefix="myapp:cache:",  # 键前缀
    ttl=300,
    enable_stats=True,
)
```

#### 序列化

RedisBackend 默认使用 `PickleSerializer`，可以正确序列化 SQLAlchemy ORM 模型等复杂 Python 对象。如需 JSON 格式（仅支持简单类型，但 Redis 中数据可读），可传入 `JsonSerializer`：

```python
from yweb.cache import RedisBackend, JsonSerializer

# 使用 JSON 序列化（仅适用于 dict/list/str/int 等简单类型）
backend = RedisBackend(
    redis_client=redis_client,
    serializer=JsonSerializer(),
)
```

| 序列化器 | 支持类型 | Redis 可读性 | 适用场景 |
|---------|---------|-------------|---------|
| `PickleSerializer`（默认） | 任意 Python 对象 | 二进制不可读 | ORM 模型、用户认证等 |
| `JsonSerializer` | JSON 基础类型 | JSON 可读 | 缓存配置、字典等简单数据 |
```

### 自定义后端

可以继承 `CacheBackend` 实现自定义后端：

```python
from yweb.cache import CacheBackend

class MyCustomBackend(CacheBackend):
    def get(self, key: str):
        ...
    
    def set(self, key: str, value, ttl=None):
        ...
    
    def delete(self, key: str) -> bool:
        ...
    
    def clear(self):
        ...
    
    def get_stats(self) -> dict:
        ...
```

---

## 缓存管理 API

`yweb.cache` 提供了通用的 HTTP 管理接口，可以挂载到任何 FastAPI 应用上，用于运行时查看和管理所有 `@cached` 函数的缓存状态。

### 快速接入

```python
from fastapi import FastAPI
from yweb.cache import create_cache_router

app = FastAPI()

# 挂载缓存管理路由
app.include_router(
    create_cache_router(),
    prefix="/api/cache",
    tags=["缓存管理"],
)
```

### 端点列表

| 方法 | 路径 | 说明 |
|------|------|------|
| `GET` | `/functions` | 列出所有 `@cached` 装饰的函数及其配置 |
| `GET` | `/stats` | 获取缓存统计（汇总或指定函数） |
| `GET` | `/entries` | 查看指定函数的缓存条目列表（脱敏预览） |
| `GET` | `/entry` | 查看指定函数的单个缓存条目（脱敏预览） |
| `POST` | `/clear` | 清空缓存（全部或指定函数） |
| `GET` | `/invalidator/registrations` | 查看自动失效注册信息 |
| `POST` | `/invalidator/toggle` | 启用/禁用 ORM 自动失效 |

### 端点详解

#### GET /functions

列出所有通过 `@cached` 装饰的函数及其配置信息：

```json
// GET /api/cache/functions
{
    "status": "success",
    "data": {
        "total": 2,
        "functions": [
            {
                "name": "get_user_by_id",
                "module": "app.api.dependencies",
                "ttl": 60,
                "backend": "memory",
                "key_prefix": "user:auth"
            },
            {
                "name": "get_config",
                "module": "app.domain.config.entities",
                "ttl": 300,
                "backend": "memory",
                "key_prefix": "sys_config"
            }
        ]
    }
}
```

#### GET /stats

获取缓存统计。不传 `function_name` 返回汇总统计，传参返回单函数统计：

```json
// GET /api/cache/stats
{
    "status": "success",
    "data": {
        "total_functions": 2,
        "total_hits": 1523,
        "total_misses": 210,
        "total_hit_rate": 87.88,
        "functions": {
            "get_user_by_id": {
                "backend": "memory",
                "function": "get_user_by_id",
                "ttl": 60,
                "hits": 1200,
                "misses": 150,
                "hit_rate": "88.89%"
            },
            "get_config": { ... }
        }
    }
}
```

#### GET /entries

查看指定函数的缓存条目列表（仅返回元信息和脱敏预览）：

```json
// GET /api/cache/entries?function_name=get_user_by_id&limit=20
{
    "status": "success",
    "data": {
        "function": "get_user_by_id",
        "total": 2,
        "entries": [
            {
                "key": "123",
                "ttl_remaining": 48,
                "value_type": "User",
                "value_size": 312,
                "value_preview": {
                    "__type__": "User",
                    "fields": {
                        "id": 123,
                        "username": "tom",
                        "access_token": "***"
                    }
                }
            }
        ]
    }
}
```

#### GET /entry

查看指定函数的单条缓存记录（用于定位某个 key 的缓存内容）：

```json
// GET /api/cache/entry?function_name=get_user_by_id&key=123
{
    "status": "success",
    "data": {
        "key": "123",
        "ttl_remaining": 48,
        "value_type": "User",
        "value_size": 312,
        "value_preview": {
            "__type__": "User",
            "fields": {
                "id": 123,
                "username": "tom",
                "password_hash": "***"
            }
        }
    }
}
```

```json
// GET /api/cache/stats?function_name=get_user_by_id
{
    "status": "success",
    "data": {
        "backend": "memory",
        "function": "get_user_by_id",
        "ttl": 60,
        "hits": 1200,
        "misses": 150,
        "hit_rate": "88.89%"
    }
}
```

#### POST /clear

清空缓存。不传 `function_name` 清空所有，传参清空指定函数：

```json
// POST /api/cache/clear
{
    "status": "success",
    "data": { "cleared_count": 2 },
    "message": "已清空 2 个函数的缓存"
}

// POST /api/cache/clear?function_name=get_user_by_id
{
    "status": "success",
    "data": { "function": "get_user_by_id" },
    "message": "缓存已清空: get_user_by_id"
}
```

#### GET /invalidator/registrations

查看 `cache_invalidator` 中所有模型与缓存函数的关联注册：

```json
// GET /api/cache/invalidator/registrations
{
    "status": "success",
    "data": {
        "enabled": true,
        "models_count": 2,
        "registrations": {
            "User": [
                { "func": "get_user_by_id", "events": ["after_update", "after_delete"] }
            ],
            "SystemConfig": [
                { "func": "_cached_get_value", "events": ["after_update", "after_delete", "after_insert"] }
            ]
        }
    }
}
```

#### POST /invalidator/toggle

启用或禁用 ORM 事件驱动的缓存自动失效：

```json
// POST /api/cache/invalidator/toggle?enabled=false
{
    "status": "success",
    "data": { "enabled": false },
    "message": "自动失效已禁用"
}
```

### 全局缓存注册表（代码级 API）

所有 `@cached` 函数在创建时自动注册到全局 `cache_registry`，也可在代码中直接使用：

```python
from yweb.cache import cache_registry

# 列出所有缓存函数
cache_registry.list_functions()

# 获取汇总统计
cache_registry.get_all_stats()

# 获取指定缓存函数
func = cache_registry.get("get_user_by_id")

# 清空指定函数的缓存
cache_registry.clear_function("get_user_by_id")

# 清空所有缓存
cache_registry.clear_all()
```

### 安全建议

缓存管理 API 提供了清空缓存、开关自动失效等操作能力，**建议在生产环境中限制访问**：

```python
from fastapi import Depends
from yweb.auth import require_admin  # 示例：要求管理员权限

app.include_router(
    create_cache_router(),
    prefix="/api/cache",
    tags=["缓存管理"],
    dependencies=[Depends(require_admin)],  # 添加权限保护
)
```

#### 缓存值查看安全说明

- `GET /entries` 与 `GET /entry` 默认只返回 `value_preview`，不会返回 raw 原始值
- 常见敏感字段（如 `password`、`secret`、`token`、`access_token`、`refresh_token`）会自动脱敏为 `***`
- 建议仅在管理员角色下开放此能力，并记录操作审计日志（谁在何时查看了哪个函数/键）
- 建议线上环境限制 `limit`（如最大 100）并配合访问频率控制

---

## 认证缓存实践

### 场景：用户认证缓存

每次 API 请求都需要验证用户身份，频繁查询数据库。

### 实现方案（推荐：setup_auth 一站式）

> **推荐使用 `setup_auth()`**：自动完成 缓存 + 自动失效 + 黑名单检查 + Session 安全。详见 [认证指南 - 一站式认证设置](06_auth_guide.md#一站式认证设置-setup_auth推荐)。

```python
# app/api/dependencies.py — 推荐方式

from yweb.auth import setup_auth
from app.domain.auth.model.user import User  # 继承自 AbstractUser 的项目用户模型

auth = setup_auth(User, cache_ttl=60)  # 自动完成缓存 + 失效注册

# 路由中使用: Depends(auth.get_current_user)
# 手动失效（特殊场景）: auth.invalidate_user_cache(user_id=123)
# 缓存统计: auth.get_user_cache_stats()
```

**`setup_auth` 自动处理的缓存问题：**

| 问题 | 自动解决方案 |
|------|------------|
| 频繁查库 | `@cached` 缓存用户对象，默认 60s TTL |
| 缓存脏数据（模型本身） | `cache_invalidator` 监听 User 的 ORM 事件自动失效 |
| 缓存脏数据（M2M 关系） | `cache_invalidator` 默认监听 ManyToMany 集合变更（如 `user.roles.append(role)`）自动失效 |
| 缓存对象 Session 脱离 | `@cached(orm_model=User)` 缓存命中时自动 `session.merge(load=False)` |
| 角色等关系加载 | 首次查询自动 `selectinload` 所有 ManyToMany 关系，缓存对象包含完整数据 |
| 黑名单检查 | 配置 `token_blacklist=True` 后自动在 JWT 校验前检查 |

### 手动实现方案（需要完全自定义时）

如果需要自定义缓存逻辑（如自定义 key、复杂的活跃判断等），可手动组装：

```python
# app/api/dependencies.py

from typing import Optional
from sqlalchemy.orm import selectinload
from yweb.cache import cached, cache_invalidator
from yweb.auth import create_auth_dependency
from app.services.jwt_service import jwt_manager
from app.domain.auth.model.user import User


# orm_model=User：缓存命中时自动 merge 回当前 Session，解决 DetachedInstanceError
@cached(ttl=60, key_prefix="user:auth", orm_model=User)
def get_user_by_id(user_id: int) -> Optional[User]:
    """通过用户 ID 获取用户（带缓存）"""
    user = User.query.options(
        selectinload(User.roles)    # 调用方决定预加载什么关系
    ).filter_by(id=user_id).first()
    if user and user.is_active:
        return user
    return None


# 默认自动监听 M2M 集合变更（user.roles 增删时也触发缓存失效）
cache_invalidator.register(User, get_user_by_id)


# 无需手动包装 session merge，orm_model 已处理
get_current_user = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=True,
)

get_current_user_optional = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=False,
)
```

### 业务代码无需关心缓存

```python
# app/services/user_service.py

class UserService:
    
    def update_password(self, user_id: int, new_password: str):
        """修改密码"""
        user = User.get_by_id(user_id)
        user.password_hash = hash_password(new_password)
        user.update()
        # 无需手动失效！cache_invalidator 自动处理
    
    def disable_user(self, user_id: int):
        """禁用用户"""
        user = User.get_by_id(user_id)
        user.is_active = False
        user.update()
        # 无需手动失效！cache_invalidator 自动处理
    
    def update_roles(self, user_id: int, role_ids: List[int]):
        """更新用户角色"""
        # ... 更新角色逻辑 ...
        # 无需手动失效！cache_invalidator 自动处理
```

### 特殊场景：手动失效

仅在以下特殊场景需要手动失效：

```python
# 1. 通过原生 SQL 更新（绕过 ORM 事件）
db.execute("UPDATE user SET is_active = 0 WHERE id = :id", {"id": user_id})
get_user_by_id.invalidate(user_id)  # 需要手动失效

# 2. 从外部系统同步数据
def sync_users_from_ldap():
    # ... 同步逻辑 ...
    get_user_by_id.clear()  # 清空所有缓存

# 3. 批量导入后
with no_auto_invalidation():
    for data in bulk_data:
        User.create(data)
get_user_by_id.clear()  # 导入完成后清空
```

### 认证流程图（带缓存）

```
┌─────────────────────────────────────────────────────────────────┐
│                    API 请求认证流程（带缓存）                     │
└─────────────────────────────────────────────────────────────────┘

  客户端                 认证中间件                   缓存              数据库
     │                      │                        │                  │
     │  GET /api/me         │                        │                  │
     │  Authorization:      │                        │                  │
     │  Bearer xxx          │                        │                  │
     │─────────────────────►│                        │                  │
     │                      │                        │                  │
     │                      │ 验证 JWT 签名          │                  │
     │                      │ 提取 user_id=123       │                  │
     │                      │                        │                  │
     │                      │ get_user(123)          │                  │
     │                      │───────────────────────►│                  │
     │                      │                        │                  │
     │                      │        缓存命中        │                  │
     │                      │◄─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─│                  │
     │                      │        返回 User       │                  │
     │                      │                        │                  │
     │◄─────────────────────│                        │                  │
     │      响应数据         │                        │                  │


  首次请求（缓存未命中）:
     │                      │ get_user(123)          │                  │
     │                      │───────────────────────►│                  │
     │                      │                        │ 缓存未命中       │
     │                      │                        │─────────────────►│
     │                      │                        │                  │
     │                      │                        │◄─────────────────│
     │                      │                        │   User 对象      │
     │                      │                        │                  │
     │                      │                        │ 写入缓存         │
     │                      │◄───────────────────────│ TTL=60s         │
     │                      │       返回 User        │                  │
```

---

## 最佳实践

### 1. TTL 设置建议

| 场景 | TTL | 说明 |
|------|-----|------|
| 高安全（用户认证） | 30-60 秒 | 用户状态变更快速生效 |
| 平衡（一般业务） | 5 分钟 | 推荐默认值 |
| 高性能（配置、字典） | 10-30 分钟 | 减少数据库压力 |

### 2. 缓存键设计

```python
# 默认：使用函数名 + 参数
@cached(ttl=60)
def get_user(user_id: int):  # 键: "get_user:123"
    ...

# 自定义前缀：更清晰的键命名
@cached(ttl=60, key_prefix="user:auth")
def get_user(user_id: int):  # 键: "user:auth:123"
    ...
```

### 3. None 值不缓存

`@cached` 默认不缓存 `None` 结果，这是有意为之：

```python
@cached(ttl=60)
def get_user(user_id: int) -> Optional[User]:
    return User.get_by_id(user_id)

# 查询不存在的用户
user = get_user(999)  # None，不缓存
user = get_user(999)  # 再次查询数据库
```

这避免了「缓存穿透」问题，但如果需要缓存 None，可以返回特殊标记值。

### 4. 失效时机

确保在以下场景失效缓存：

| 操作 | 失效调用 |
|------|---------|
| 创建 | 通常不需要（新 ID 无缓存） |
| 更新 | `func.invalidate(id)` |
| 删除 | `func.invalidate(id)` |
| 批量操作 | `func.invalidate_many([...])` |

### 5. 监控与调优

```python
# 定期检查命中率
stats = get_user.stats()
if stats['hit_rate'] < 0.8:
    # 命中率低于 80%，考虑：
    # - 增加 TTL
    # - 增加 maxsize
    # - 检查是否有大量不同参数调用
    pass
```

### 6. 缓存 ORM 对象的正确姿势

缓存 SQLAlchemy ORM 对象时，内存缓存（MemoryBackend）存储的是**对象引用**。请求结束后 Session 关闭，缓存对象变为 detached，后续请求访问 lazy 关系会抛 `DetachedInstanceError`。

**解决方案：使用 `orm_model` + `watch_relationships`**

```python
from yweb.cache import cached, cache_invalidator
from sqlalchemy.orm import selectinload

# 1. orm_model=Product：缓存命中时自动 merge 回 Session
@cached(ttl=300, orm_model=Product)
def get_product(product_id: int):
    return Product.query.options(
        selectinload(Product.categories)   # 调用方决定预加载什么
    ).filter_by(id=product_id).first()

# 2. 注册自动失效（默认监听 M2M 集合变更）
cache_invalidator.register(Product, get_product)
```

| 参数 | 作用 | 解决的问题 |
|------|------|-----------|
| `orm_model` | 缓存命中时自动 `session.merge(load=False)` | DetachedInstanceError |
| `watch_relationships` | 监听 M2M 集合 append/remove 事件 | M2M 变更后缓存脏数据 |
| `selectinload(...)` | 预加载关系数据进缓存 | 每次命中都额外查询关系 |

> **职责分离**：`orm_model` 和 `watch_relationships` 是缓存层的通用能力；预加载什么关系是业务层的决策。

### 7. 多实例部署注意事项

使用内存缓存时，多实例之间缓存不共享：

```
┌─────────────────────────────────────────────────────────────┐
│                      多实例部署                              │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│   实例 A              实例 B              实例 C            │
│   ┌─────┐            ┌─────┐            ┌─────┐            │
│   │Cache│            │Cache│            │Cache│            │
│   │user1│            │user2│            │user3│            │
│   └─────┘            └─────┘            └─────┘            │
│      │                  │                  │               │
│      └──────────────────┼──────────────────┘               │
│                         │                                   │
│                    ┌─────────┐                              │
│                    │ 数据库  │                              │
│                    └─────────┘                              │
│                                                             │
│   问题：实例 A 更新用户后，只失效了自己的缓存                  │
│   解决：使用 Redis 缓存，或通过消息队列广播失效               │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

解决方案：

```python
# 方案 1：使用 Redis 缓存（推荐）
@cached(ttl=60, backend="redis", redis=redis_client)
def get_user(user_id: int):
    ...

# 方案 2：缩短 TTL
@cached(ttl=10)  # 最多 10 秒不一致
def get_user(user_id: int):
    ...
```

---

## API 参考

### 装饰器

| 装饰器 | 说明 |
|--------|------|
| `@cached(ttl, maxsize, backend, redis, ...)` | 通用缓存装饰器 |
| `@memory_cache(ttl, maxsize)` | 内存缓存装饰器（简写） |
| `@redis_cache(redis, ttl)` | Redis 缓存装饰器（简写） |

**`@cached` 关键参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `ttl` | int | 缓存过期时间（秒），默认 300 |
| `invalidate_on` | Model/list/dict | 自动失效配置，ORM 模型变更时清除缓存 |
| `orm_model` | Model class | 指定后，缓存命中时自动将 detached ORM 对象 merge 回当前 Session |

### CachedFunction 方法

| 方法 | 说明 |
|------|------|
| `__call__(*args, **kwargs)` | 调用函数（优先返回缓存） |
| `invalidate(*args, **kwargs)` | 失效特定参数的缓存 |
| `invalidate_many(keys)` | 批量失效缓存 |
| `refresh(*args, **kwargs)` | 强制刷新（先失效再调用） |
| `clear()` | 清空此函数的所有缓存 |
| `stats()` | 获取缓存统计信息 |
| `backend` | 获取缓存后端实例 |

### 自动失效 (cache_invalidator)

| 方法 | 说明 |
|------|------|
| `register(model, func, key_extractor, events, watch_relationships)` | 注册模型与缓存函数的关联 |
| `unregister(model, func)` | 取消注册 |
| `track_dependencies(func, cache_key, result)` | 扫描结果建立反向索引（`@cached` 内部自动调用） |

**`register` 关键参数：**

| 参数 | 类型 | 说明 |
|------|------|------|
| `watch_relationships` | bool | 默认 True。自动监听模型上所有 ManyToMany 集合的 append/remove 事件，集合变更时触发缓存失效。模型无 M2M 关系时零开销 |

**失效机制（双路径，自动选择）：**

| 路径 | 触发条件 | 适用场景 |
|------|---------|---------|
| key_extractor 精确失效 | 实体变更时，用 `key_extractor(entity)` 作为参数调用 `func.invalidate()` | `get_user(user_id)` 等参数即 ID 的函数 |
| 依赖追踪失效 | 缓存写入时扫描结果中的实体，建立反向索引；实体变更时按索引精确失效 | `get_orders(user_id, page)` 等列表/组合查询 |

| 其他方法 | 说明 |
|------|------|
| `get_registrations(model)` | 获取注册信息 |
| `enable()` | 启用自动失效 |
| `disable()` | 禁用自动失效 |
| `clear()` | 清空所有注册 |

### 上下文管理

| 函数 | 说明 |
|------|------|
| `no_auto_invalidation()` | 临时禁用自动失效的上下文管理器 |

### 缓存注册表 (cache_registry)

| 方法/属性 | 说明 |
|-----------|------|
| `register(func)` | 注册缓存函数（`@cached` 自动调用） |
| `unregister(name)` | 取消注册 |
| `get(name)` | 获取指定缓存函数 |
| `list_functions()` | 列出所有已注册的缓存函数信息 |
| `get_all_stats()` | 获取所有缓存函数的汇总统计 |
| `list_entries(name, limit)` | 获取指定函数缓存条目列表（脱敏预览） |
| `get_entry(name, key)` | 获取指定函数单条缓存记录（脱敏预览） |
| `clear_function(name)` | 清空指定函数的缓存 |
| `clear_all()` | 清空所有缓存 |
| `size` | 已注册的缓存函数数量 |

### 缓存管理路由

| 函数 | 说明 |
|------|------|
| `create_cache_router()` | 创建通用缓存管理 API 路由（FastAPI APIRouter） |

### 缓存后端

| 类 | 说明 |
|----|------|
| `CacheBackend` | 缓存后端抽象基类 |
| `MemoryBackend` | 内存缓存后端（支持 per-key TTL） |
| `RedisBackend` | Redis 缓存后端（默认 pickle 序列化） |
| `CacheStats` | 缓存统计信息类 |
| `CacheInvalidator` | 缓存自动失效管理器 |

### 序列化器

| 类 | 说明 |
|----|------|
| `PickleSerializer` | pickle 序列化器（RedisBackend 默认），支持任意 Python 对象 |
| `JsonSerializer` | JSON 序列化器，仅支持基础类型，Redis 中数据可读 |

---

## 完整示例

### 推荐方式：setup_auth 一站式（自动缓存 + 自动失效 + Session 安全）

`setup_auth()` 内部自动完成 `@cached` + `cache_invalidator.register()` + `create_auth_dependency()` + 黑名单检查 + Session 安全 merge，无需手动编写：

```python
# app/api/dependencies.py — 推荐

from yweb.auth import setup_auth
from app.domain.auth.model.user import User
from app.config import settings

auth = setup_auth(User, jwt_settings=settings.jwt, token_url="/api/v1/auth/token")

# 路由中使用: Depends(auth.get_current_user)
# JWT 管理器: auth.jwt_manager
# 用户获取（带缓存 + Session 安全）: auth.user_getter
# 手动失效: auth.invalidate_user_cache(user_id)
# 缓存统计: auth.get_user_cache_stats()
```

**框架自动处理的内部细节（用户无需关心）：**

1. 首次查询时自动 `selectinload` 所有 ManyToMany 关系（roles/permissions 等）
2. `@cached(orm_model=User)` 缓存命中时自动 `session.merge(load=False)`
3. `cache_invalidator` 默认监听 M2M 集合变更（如 `user.roles.append(role)`）自动失效
4. 配置 `token_blacklist=True` 时，自动在 JWT 校验前检查黑名单

### 手动方式：完全自定义（自动失效）

如需自定义缓存逻辑，可手动组装各组件：

```python
# app/api/dependencies.py — 手动方式

from typing import Optional
from sqlalchemy.orm import selectinload
from yweb.cache import cached, cache_invalidator
from yweb.auth import create_auth_dependency
from app.services.jwt_service import jwt_manager
from app.domain.auth.model.user import User


# orm_model=User：缓存命中时自动 merge 回 Session
@cached(ttl=60, key_prefix="user:auth", orm_model=User)
def get_user_by_id(user_id: int) -> Optional[User]:
    """通过用户 ID 获取用户（带缓存）"""
    user = User.query.options(
        selectinload(User.roles)
    ).filter_by(id=user_id).first()
    if user and user.is_active:
        return user
    return None


# 默认监听 M2M 集合变更（user.roles 增删时也失效）
cache_invalidator.register(User, get_user_by_id)


# 无需手动 session merge 包装
get_current_user = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=True,
)

get_current_user_optional = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=False,
)


def invalidate_user_cache(user_id: int) -> bool:
    """手动失效用户缓存（特殊场景使用）
    
    通常不需要调用，User 模型变更时会自动失效。
    仅在绕过 ORM 或外部同步时使用。
    """
    return get_user_by_id.invalidate(user_id)


def get_user_cache_stats() -> dict:
    """获取缓存统计（供监控使用）"""
    return get_user_by_id.stats()
```

```python
# app/services/user_service.py

# 业务代码无需关心缓存失效！

class UserService:
    
    def update_user(self, user_id: int, data: dict):
        user = User.get_by_id(user_id)
        for key, value in data.items():
            setattr(user, key, value)
        user.update()
        
        # 无需手动调用 invalidate！
        # cache_invalidator 监听 after_update 事件，自动失效缓存
        
        return user
    
    def disable_user(self, user_id: int):
        user = User.get_by_id(user_id)
        user.is_active = False
        user.update()
        # 自动失效，无需手动处理
    
    def delete_user(self, user_id: int):
        user = User.get_by_id(user_id)
        user.delete()
        # 自动失效，无需手动处理
```

### 对比：手动 vs 自动

| 方式 | 代码量 | 遗漏风险 | 推荐度 |
|------|--------|---------|--------|
| 手动调用 `invalidate()` | 多（每处变更都要写） | 高 | ⭐⭐ |
| 自动失效 `cache_invalidator` | 少（一行注册） | 低 | ⭐⭐⭐ |

```python
# 手动方式（容易遗漏）
def update_user(...):
    user.update()
    invalidate_user_cache(user_id)  # 每次都要记得写

# 自动方式（推荐）
cache_invalidator.register(User, get_user_by_id)  # 一次注册，永久生效
def update_user(...):
    user.update()  # 自动触发失效，无需额外代码
```
