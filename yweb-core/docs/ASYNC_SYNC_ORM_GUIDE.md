# FastAPI 异步与同步 ORM 使用指南

## 概述

本文档详细解释 FastAPI 中使用同步 ORM（如 SQLAlchemy）时的常见问题和解决方案。

## 目录

1. [核心概念：sync / async / await](#核心概念sync--async--await)
2. [FastAPI vs Flask 架构差异](#fastapi-vs-flask-架构差异)
3. [问题：async def 中使用同步 ORM](#问题async-def-中使用同步-orm)
4. [解决方案](#解决方案)
5. [Session 隔离问题](#session-隔离问题)
6. [使用指南](#使用指南)
7. [错误检测与警告](#错误检测与警告)

---

## 核心概念：sync / async / await

### sync（同步）

**同步 = 排队，一个一个来**

```python
def make_coffee():
    grind_beans()      # 磨豆子，等 30 秒
    boil_water()       # 烧水，等 60 秒
    brew()             # 冲泡，等 30 秒
    return coffee      # 总共等了 120 秒
```

```
执行流程：
[磨豆子 30s][     烧水 60s     ][冲泡 30s] = 120s

（干等着，什么都不能做）
```

### async（异步）

**异步 = 可以同时做多件事**

```python
async def make_coffee():
    task1 = grind_beans()   # 后台开始运行：开始磨豆子
    task2 = boil_water()    # 后台开始运行：同时开始烧水
    await task1             # 前台等待：等磨完
    await task2             # 前台等待：等水开
    brew()                  # 冲泡
    return coffee           # 总共约 60 秒（烧水最久）
```

```
执行流程：
[磨豆子 30s]
[        烧水 60s        ][冲泡 30s] = 90s

（磨豆子和烧水同时进行）
```

### await（等待）

**await = "等这件事做完再继续，但等待期间让别人先做事"**

```python
# 【异步函数】- 用 async def 定义
async def fetch_data():
    return await some_api()
async def main():
    result = await fetch_data()  # 等网络请求完成
    print(result)                # 拿到结果后继续
```

**执行流程**：

1. `fetch_data()` 被调用，返回一个"协程对象"（还没执行！）
2. `await` 告诉事件循环：
  - "帮我执行这个协程"
  - "执行完把结果给我"
  - "期间你可以去忙别的"
3. 事件循环执行 `fetch_data`，期间可以处理其他请求
4. `fetch_data` 完成，结果赋值给 `result`
5. 继续执行 `print(result)`

### 不 await 会怎样？

```python
# 【异步函数】- 用 async def 定义
async def fetch_data():
    return await some_api()
async def main():
    result = fetch_data()  # 没有 await！
    print(result)
```

**输出**：

```
<coroutine object fetch_data at 0x7f...>
```

`fetch_data` 根本没执行！`result` 只是一个"协程对象"，不是真正的结果。

### 如何同时开始多个任务？

```python
async def main():
    # ❌ 这样是串行的（一个等完再等下一个）
    result1 = await task1()  # 等 task1 完成
    result2 = await task2()  # 再等 task2 完成
    # 总时间 = task1 + task2

    # ✅ 这样是并行的
    t1 = asyncio.create_task(task1())  # 立刻开始 task1
    t2 = asyncio.create_task(task2())  # 立刻开始 task2（同时！）
    
    result1 = await t1  # 等 t1 完成
    result2 = await t2  # 等 t2 完成（可能已经完成了）
    # 总时间 = max(task1, task2)
```

```
串行 (await 一个再 await 下一个):
task1: ████████████
task2:             ████████████
                              总时间 ──▶

并行 (create_task 同时开始):
task1: ████████████
task2: ████████████
              总时间 ──▶
```

### 生活类比


| 概念            | 类比                |
| ------------- | ----------------- |
| **sync（同步）**  | 你去银行排队，前面的人办完你才能办 |
| **async（异步）** | 你取号后去喝咖啡，叫号了再回来办  |
| **await（等待）** | "等叫我的号"这个动作       |


---

## 事件循环 vs 进程 vs 线程

### 概念区分

```
┌─────────────────────────────────────────────────────────┐
│                      服务器                              │
├─────────────────────────────────────────────────────────┤
│  进程 1                    进程 2                        │
│  ┌───────────────────┐    ┌───────────────────┐         │
│  │ 事件循环（1个线程）│    │ 事件循环（1个线程）│         │
│  │  ├─ 协程A         │    │  ├─ 协程E         │         │
│  │  ├─ 协程B         │    │  ├─ 协程F         │         │
│  │  ├─ 协程C         │    │  └─ 协程G         │         │
│  │  └─ 协程D         │    │                   │         │
│  └───────────────────┘    └───────────────────┘         │
└─────────────────────────────────────────────────────────┘
```


| 概念       | 说明               |
| -------- | ---------------- |
| **进程**   | 独立的内存空间，互不干扰     |
| **线程**   | 进程内的执行单元，共享内存    |
| **事件循环** | 单线程内调度多个协程的机制    |
| **协程**   | 轻量级的"任务"，由事件循环调度 |


### 部署方式对比

#### 单进程（开发环境）

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

```
1个进程 → 1个事件循环 → 所有请求共享这个循环
```

#### 多进程（生产环境）

```bash
uvicorn app:app --workers 4    # 4个进程
# 或
gunicorn app:app -w 4 -k uvicorn.workers.UvicornWorker
```

```
4个进程 → 每个进程1个事件循环 → 请求分散到不同进程
         ↓
         每个进程内的请求共享该进程的事件循环
```

### "所有请求共享一个事件循环"的含义

- **同一个进程内**的所有请求共享一个事件循环 ✅
- 如果部署了多进程，**不同进程**有各自的事件循环，互不影响
- **阻塞问题仍然存在**：即使多进程，每个进程内阻塞还是会影响该进程的其他请求

---

## FastAPI vs Flask 架构差异

### 架构对比


| 框架          | 协议   | 请求处理方式           | 并发模型      |
| ----------- | ---- | ---------------- | --------- |
| **Flask**   | WSGI | 每个请求独占一个**线程**   | 多线程       |
| **FastAPI** | ASGI | 所有请求共享一个**事件循环** | 协程 + 事件循环 |


### Flask（WSGI）

```
Flask 部署（Gunicorn: -w 4 --threads 4）

进程1 ──┬── 线程1 → 处理请求A
        ├── 线程2 → 处理请求B
        ├── 线程3 → 处理请求C
        └── 线程4 → 处理请求D

进程2 ──┬── 线程1 → 处理请求E
        ...

每个请求独立线程，互不影响
```

**特点**：

- 每个请求在独立线程中执行
- 同步代码阻塞只影响当前线程
- 其他线程正常处理其他请求
- Flask 2.0+ 支持 `async def`，但内部用 `asyncio.run()` 执行，本质还是同步模型

### FastAPI（ASGI）

```
FastAPI 部署（Uvicorn）

事件循环（单线程）
    │
    ├── 协程1: 处理请求A
    ├── 协程2: 处理请求B
    ├── 协程3: 处理请求C
    └── 协程4: 处理请求D

所有协程在同一个事件循环中调度
```

**特点**：

- 所有请求共享一个事件循环
- `async def` 中的同步阻塞会卡住整个事件循环
- `def`（同步函数）会自动放到线程池执行，不阻塞事件循环

---

## 问题：async def 中使用同步 ORM

### 错误示例

```python
# ❌ 错误：async def + 同步 ORM
@app.get("/users")
async def list_users():
    users = User.query.all()  # 同步操作，没有 await，，因为User.query.all()定义的是同步 def 函数 不是 async def 
    return users              # 会阻塞整个事件循环！
```

### 在 Flask 中 ✅ 没问题

```
Flask (WSGI)
    │
    ├── 线程1 处理请求A → User.query.all() 阻塞 100ms → 返回
    ├── 线程2 处理请求B → User.query.all() 阻塞 100ms → 返回
    ├── 线程3 处理请求C → ...
    └── ...
    
每个请求独立的线程，互不影响
```

### 在 FastAPI 中 ❌ 会阻断所有请求

```
FastAPI (ASGI)
    │
    └── 事件循环（单线程）
            │
            ├── 请求A: User.query.all() 阻塞 100ms...
            │         ↑
            │         整个事件循环卡住！
            │         
            ├── 请求B: 等着... 😢
            ├── 请求C: 等着... 😢
            └── 请求D: 等着... 😢
            
所有请求都在等请求A的 ORM 操作完成
```

---

## 解决方案

> **最终方案选择**：采用 `sync_to_async` 装饰器和 `run_sync` 函数，在框架层面提供工具，让开发者可以在 `async def` 中安全使用同步 ORM。

### 完整实现代码

```python
import asyncio
import contextvars
from concurrent.futures import ThreadPoolExecutor
from functools import wraps
from typing import TypeVar, Callable, Any, Coroutine

T = TypeVar('T')

# 全局线程池
executor = ThreadPoolExecutor(max_workers=40, thread_name_prefix="yweb_sync_")


async def run_sync(func: Callable[..., T], *args, **kwargs) -> T:
    """在线程池中执行同步函数，返回 awaitable
    
    自动传递 ContextVar 上下文（如 request_id），确保 ORM session 隔离正确。
    """
    loop = asyncio.get_running_loop()
    
    # 关键：复制当前协程的上下文（包含 request_id）
    ctx = contextvars.copy_context()
    
    # 在复制的上下文中执行
    def _run_in_context():
        return ctx.run(func, *args, **kwargs)
    
    return await loop.run_in_executor(executor, _run_in_context)


def sync_to_async(func: Callable[..., T]) -> Callable[..., Coroutine[Any, Any, T]]:
    """装饰器：将同步函数转换为异步函数
    
    自动传递 ContextVar 上下文（如 request_id），确保 ORM session 隔离正确。
    """
    @wraps(func)
    async def wrapper(*args, **kwargs) -> T:
        return await run_sync(func, *args, **kwargs)
    
    return wrapper
```

**关键点**：
1. `contextvars.copy_context()` - 复制当前协程的上下文，包含 `request_id`
2. `ctx.run(func, ...)` - 在复制的上下文中执行函数，确保 session 隔离正确
3. `run_in_executor` - 将同步函数放到线程池执行，不阻塞事件循环

---

### 方案1：使用同步端点（推荐）

**最简单有效的方案**：把 API 端点改为同步函数 `def`，而不是 `async def`。

```python
# ✅ 推荐：同步 def + 同步 ORM
@app.get("/users")
def list_users():
    users = User.query.filter(User.is_active == True).all()
    return OK(users)
```

**为什么这样做不会浪费资源？**

FastAPI 会自动将同步函数放到 **线程池（ThreadPoolExecutor）** 中执行：

- 不会阻塞事件循环
- 多个请求可以并发处理
- 链式调用正常工作

### 方案2：使用 run_sync 工具函数

如果你的 API 中既有 ORM 操作，又有真正的异步操作（如调用外部 HTTP API），可以使用 `run_sync`：

```python
from yweb.utils import run_sync

@app.get("/users")
async def list_users():
    # 同步 ORM 操作 → 用 run_sync 包装
    users = await run_sync(lambda: User.query.filter(User.is_active == True).all())
    
    # 异步操作 → 正常 await
    await send_notification("查询完成")
    
    return OK(users)
```

### 方案3：使用 @sync_to_async 装饰器

```python
from yweb.utils import sync_to_async

@sync_to_async
def query_active_users():
    return User.query.filter(User.is_active == True).all()

@app.get("/users")
async def list_users():
    users = await query_active_users()
    return OK(users)
```

### 方案选择指南


| 你的代码有什么                  | 用什么                                    |
| ------------------------ | -------------------------------------- |
| 只有同步操作（ORM、文件等）          | `def`（方案1）                             |
| 只有异步操作（httpx、aioredis 等） | `async def`                            |
| 两者都有                     | `async def` + `run_sync` 包装同步部分（方案2/3） |


---

## Session 隔离问题

### 问题背景

YWeb ORM 使用 `ContextVar` 存储 `request_id`，`scoped_session` 根据 `request_id` 返回对应的 session：

```python
# yweb 用 ContextVar 存储 request_id
_request_id_var: ContextVar[str] = ContextVar('request_id')

# scoped_session 根据 request_id 返回对应的 session
scoped_session(session_maker, scopefunc=get_request_id)
```

### 问题：run_in_executor 的上下文丢失

如果简单地使用 `run_in_executor`，线程池中的代码可能无法访问正确的 `request_id`：

```python
# ❌ 简单实现，会有问题
async def run_sync_bad(func):
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(executor, func)
    # 线程池中的 request_id 是空的或错误的！
```

```
请求 A (request_id = "aaa")
    │
    ├──▶ 线程池线程1：request_id = ???  ← 拿不到 "aaa"！
    │    可能拿到空值或其他请求的 ID
    │
请求 B (request_id = "bbb") 
    │
    ├──▶ 线程池线程1：可能混用了 A 的 session！
```

### 解决方案：复制 ContextVar 上下文

`yweb.utils` 提供的 `run_sync` 和 `sync_to_async` 使用 `contextvars.copy_context()` 确保上下文正确传递：

```python
# ✅ 正确实现
async def run_sync(func, *args, **kwargs):
    loop = asyncio.get_event_loop()
    
    # 关键：复制当前协程的上下文（包含 request_id）
    ctx = contextvars.copy_context()
    
    # 在复制的上下文中执行
    return await loop.run_in_executor(
        executor,
        lambda: ctx.run(func, *args, **kwargs)  # ctx.run 确保上下文正确
    )
```

这样 `request_id` 就能正确传递到线程池，session 不会混乱。

---

## 使用指南

### 安装与导入

```python
from yweb.utils import run_sync, sync_to_async
```

### run_sync 函数

将同步函数放到线程池执行，返回 awaitable。

```python
from yweb.utils import run_sync

# 方式1：使用 lambda
@app.get("/users")
async def list_users():
    users = await run_sync(lambda: User.query.all())
    return OK(users)

# 方式2：使用已定义的函数
def query_users():
    return User.query.filter(User.is_active == True).paginate(page=1, page_size=10)

@app.get("/users")
async def list_users():
    page_result = await run_sync(query_users)
    return OK(page_result)

# 方式3：带参数
@app.get("/users/{user_id}")
async def get_user(user_id: int):
    user = await run_sync(User.get, user_id)
    return OK(user)
```

### sync_to_async 装饰器

将同步函数转换为异步函数。

```python
from yweb.utils import sync_to_async

@sync_to_async
def query_active_users():
    return User.query.filter(User.is_active == True).all()

@sync_to_async
def create_user(name: str, email: str):
    user = User(name=name, email=email)
    user.save(commit=True)
    return user

# 使用
@app.get("/users")
async def list_users():
    users = await query_active_users()
    return OK(users)

@app.post("/users")
async def create_user_endpoint(data: UserCreate):
    user = await create_user(data.name, data.email)
    return OK(user)
```

---

## 错误检测与警告

### 问题场景

开发者可能不小心在 `async def` 中直接使用同步 ORM 操作：

```python
@app.get("/users")
async def list_users():
    users = User.query.all()  # ❌ 忘记用 run_sync 包装
    return users
```

这种错误很隐蔽——代码能正常运行、结果也正确，但会阻塞事件循环。需要一种机制在**运行时自动检测**并发出警告。

### 实现原理

核心思路：**包装 SQLAlchemy Query 的终结方法**（`all()`, `first()`, `count()` 等），在每次查询执行前检测是否处于异步上下文中。

```
开发者调用              检测 Hook                      结果
    │                     │                            │
    ▼                     ▼                            ▼
User.query.all() → 是否在 async 上下文？→ 是 → 发出警告
                                        → 否 → 正常执行
```

### 完整实现代码

```python
import asyncio
import functools
import warnings
import logging
import traceback

_logger = logging.getLogger("yweb.utils.async")


class AsyncORMWarning(UserWarning):
    """在异步上下文中使用同步 ORM 操作的警告"""
    pass


# ==================== 警告配置 ====================

_warning_config = {
    'enabled': False,
    'raise_error': False,
    'log_level': 'WARNING',
}


def configure_async_orm_warning(
    enabled: bool = True,
    raise_error: bool = False,
    log_level: str = "WARNING"
) -> None:
    """配置异步 ORM 警告

    Args:
        enabled: 是否启用警告检测
        raise_error: 是否抛出异常（CI 环境建议 True，直接中断）
        log_level: 日志级别（DEBUG/INFO/WARNING/ERROR）
    """
    _warning_config['enabled'] = enabled
    _warning_config['raise_error'] = raise_error
    _warning_config['log_level'] = log_level


def enable_async_orm_warning(raise_error: bool = False) -> None:
    """启用异步 ORM 警告

    Args:
        raise_error: 是否抛出异常而不是仅警告
    """
    configure_async_orm_warning(enabled=True, raise_error=raise_error)
    _install_orm_warning_hook()


# ==================== 异步上下文检测 ====================

def is_in_async_context() -> bool:
    """检测当前是否在异步上下文中（即事件循环正在运行）"""
    try:
        asyncio.get_running_loop()
        return True
    except RuntimeError:
        return False


def _get_caller_info(depth: int = 3) -> str:
    """获取调用者的文件、行号、函数名"""
    stack = traceback.extract_stack()
    if len(stack) > depth:
        frame = stack[-(depth + 1)]
        return f"{frame.filename}:{frame.lineno} in {frame.name}"
    return "unknown"


def _emit_async_orm_warning(operation: str) -> None:
    """检测并发出警告"""
    if not _warning_config['enabled']:
        return

    if not is_in_async_context():
        return

    caller = _get_caller_info(depth=4)
    message = (
        f"在异步上下文中使用了同步 ORM 操作 '{operation}'，"
        f"这会阻塞事件循环。请使用以下方式之一：\n"
        f"1. 将端点改为 def（推荐）\n"
        f"2. 使用 await run_sync(lambda: {operation})\n"
        f"位置：{caller}"
    )

    if _warning_config['raise_error']:
        raise AsyncORMWarning(message)

    log_level = getattr(logging, _warning_config['log_level'].upper(), logging.WARNING)
    _logger.log(log_level, f"⚠️ AsyncORMWarning: {message}")
    warnings.warn(message, AsyncORMWarning, stacklevel=5)


# ==================== ORM Hook 安装 ====================

_orm_warning_installed = False


def _install_orm_warning_hook() -> None:
    """包装 SQLAlchemy Query 的终结方法，注入异步检测"""
    global _orm_warning_installed
    if _orm_warning_installed:
        return

    try:
        from sqlalchemy.orm import Query

        # 要包装的终结方法（这些方法会真正执行 SQL）
        methods_to_wrap = ['all', 'first', 'one', 'one_or_none', 'count']
        if hasattr(Query, 'scalar'):
            methods_to_wrap.append('scalar')

        for method_name in methods_to_wrap:
            original = getattr(Query, method_name)

            def _make_wrapper(orig_method, name):
                @functools.wraps(orig_method)
                def wrapper(self, *args, **kwargs):
                    # 尝试获取模型名，用于更友好的警告信息
                    try:
                        model_name = self.column_descriptions[0]['entity'].__name__
                        operation = f"{model_name}.query.{name}()"
                    except Exception:
                        operation = f"Query.{name}()"

                    _emit_async_orm_warning(operation)
                    return orig_method(self, *args, **kwargs)
                return wrapper

            setattr(Query, method_name, _make_wrapper(original, method_name))

        _orm_warning_installed = True
        _logger.debug("ORM 异步警告 hook 已安装")

    except ImportError:
        _logger.warning("无法安装 ORM 警告 hook：sqlalchemy 未找到")
    except Exception as e:
        _logger.warning(f"安装 ORM 警告 hook 失败：{e}")


def _uninstall_orm_warning_hook() -> None:
    """卸载 ORM 警告 hook（用于测试）"""
    global _orm_warning_installed
    _orm_warning_installed = False
    _warning_config['enabled'] = False
```

### 工作流程详解

**检测流程**：

```
1. 应用启动 → enable_async_orm_warning()
   │
   ▼
2. _install_orm_warning_hook() 包装 Query.all / Query.first / ...
   │
   ▼
3. 某处调用 User.query.all()
   │
   ├── 检查 _warning_config['enabled'] → 未启用 → 正常执行
   │
   ├── 调用 is_in_async_context()
   │   │
   │   ├── asyncio.get_running_loop() 成功 → 在异步上下文中 → 发出警告
   │   │
   │   └── asyncio.get_running_loop() 抛 RuntimeError → 在同步上下文中 → 正常执行
   │
   └── 执行原始的 Query.all()
```

**`is_in_async_context()` 的原理**：

```python
def is_in_async_context() -> bool:
    try:
        asyncio.get_running_loop()  # 如果有正在运行的事件循环，说明在 async 上下文中
        return True
    except RuntimeError:            # 没有事件循环，说明在普通同步代码中
        return False
```

- `def list_users()` → FastAPI 放到线程池 → 线程中没有事件循环 → `is_in_async_context()` 返回 `False` → 不警告 ✅
- `async def list_users()` → 在事件循环中执行 → `is_in_async_context()` 返回 `True` → 发出警告 ⚠️
- `async def` + `run_sync(lambda: ...)` → ORM 代码在线程池中执行 → 线程中没有事件循环 → 不警告 ✅

### 自动启用（默认行为）

警告检测在 `init_database()` 中**自动启用**，用户无需额外配置，也不提供关闭选项：

- 如果全部使用 `def` 端点，`is_in_async_context()` 永远返回 `False`，不会触发任何警告，没有性能影响
- 只有真正在 `async def` 中错误使用了同步 ORM 才会触发

```python
# 用户代码 —— 无需任何额外配置，警告自动生效
init_database("sqlite:///./app.db")
```

#### init_database 内部实现

```python
def init_database(database_url: str = None, ...):
    # ... 原有初始化逻辑 ...
    
    # 自动设置 ORM query 属性
    if auto_setup_query:
        CoreModel.query = self._session_scope.query_property()
    
    # 自动启用异步 ORM 警告（在 query 属性设置之后）
    from yweb.utils.async_utils import _install_orm_warning_hook
    _install_orm_warning_hook()
```

#### CI 环境：升级为抛出异常

```python
from yweb.utils import configure_async_orm_warning

# 默认只是警告，CI 环境可以升级为抛出异常，让测试直接失败
configure_async_orm_warning(raise_error=True)
```

#### 自定义配置

```python
from yweb.utils import configure_async_orm_warning

configure_async_orm_warning(
    enabled=True,           # 是否启用
    raise_error=False,      # 是否抛出异常
    log_level="WARNING",    # 日志级别
)
```

### 警告输出示例

```
⚠️ AsyncORMWarning: 在异步上下文中使用了同步 ORM 操作 'User.query.all()'，
这会阻塞事件循环。请使用以下方式之一：
1. 将端点改为 def（推荐）
2. 使用 await run_sync(lambda: User.query.all())
位置：app/api/user.py:25 in list_users
```

### 三种场景的检测结果

```python
# 场景1：def + 同步 ORM → 不警告 ✅
@app.get("/users")
def list_users():
    return User.query.all()  # 在线程池中执行，无事件循环 → 不触发警告

# 场景2：async def + 同步 ORM → 警告 ⚠️
@app.get("/users")
async def list_users():
    return User.query.all()  # 在事件循环中执行 → 触发警告

# 场景3：async def + run_sync → 不警告 ✅
@app.get("/users")
async def list_users():
    return await run_sync(lambda: User.query.all())  # ORM 在线程池中执行 → 不触发警告
```

---

## 总结

### 核心要点

1. **Flask 不需要担心这个问题**：它是每个请求一个线程的模型
2. **FastAPI 中 async def + 同步代码会阻塞事件循环**：影响所有请求
3. **最简单的解决方案**：ORM 操作的端点用 `def`，不用 `async def`
4. **如果必须用 async def**：使用 `run_sync` 或 `@sync_to_async` 包装同步代码
5. **Session 隔离**：`run_sync` 使用 `contextvars.copy_context()` 确保上下文正确传递

### 快速参考

```python
# ✅ 场景1：只有 ORM 操作 → 用 def
@app.get("/users")
def list_users():
    return User.query.all()

# ✅ 场景2：ORM + 异步操作 → async def + run_sync
@app.get("/users")
async def list_users():
    users = await run_sync(lambda: User.query.all())
    await send_notification()
    return users

# ❌ 错误：async def + 直接使用同步 ORM
@app.get("/users")
async def list_users():
    return User.query.all()  # 阻塞事件循环！
```

---

## 相关文档

- [ORM 基础指南](../yweb-core/docs/03_orm_guide.md)
- [FastAPI 集成](../yweb-core/docs/orm_docs/15_fastapi_integration.md)
- [数据库会话管理](../yweb-core/docs/orm_docs/12_db_session.md)

