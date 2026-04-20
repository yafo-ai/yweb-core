# YWeb 限流指南

本指南介绍 YWeb 提供的 API 限流集成模块，帮助你快速为应用添加请求频率限制，防止接口被滥用。

## 目录

- [设计背景](#设计背景)
- [快速开始](#快速开始)
- [配置](#配置)
- [路由限流](#路由限流)
- [身份识别](#身份识别)
- [429 响应格式](#429-响应格式)
- [事件订阅](#事件订阅)
- [最佳实践](#最佳实践)
- [API 参考](#api-参考)

---

## 设计背景

### 问题场景

Web 应用常面临以下攻击和滥用：

- **暴力破解**：高频尝试登录接口
- **爬虫滥用**：无限制爬取数据接口
- **DDoS 缓解**：突发大量请求压垮服务

### 解决方案

基于 [slowapi](https://github.com/laurentS/slowapi) 做轻度封装，提供一站式初始化，集成 yweb 的配置体系、认证身份识别和统一响应格式：

```python
from yweb.ratelimit import setup_ratelimit

app = FastAPI()
limiter = setup_ratelimit(app, default_limits=["100/minute"])
```

**设计原则：薄封装**——不重新造限流算法，只做配置桥接、身份识别、响应格式统一。路由中直接使用 slowapi 原生装饰器，零额外学习成本。

---

## 快速开始

### 安装

```bash
pip install yweb[ratelimit]
```

### 最小示例

```python
from fastapi import FastAPI
from starlette.requests import Request
from starlette.responses import Response

from yweb.ratelimit import setup_ratelimit

app = FastAPI()
limiter = setup_ratelimit(app, default_limits=["100/minute"])

@app.get("/api/v1/data")
@limiter.limit("10/minute")
async def get_data(request: Request, response: Response):
    return {"data": "hello"}

@app.get("/health")
@limiter.exempt
async def health(request: Request, response: Response):
    return {"status": "ok"}
```

> **注意**：使用 `@limiter.limit()` 的端点必须接受 `request: Request` 和 `response: Response` 参数。

---

## 配置

### 参数方式

```python
limiter = setup_ratelimit(
    app,
    default_limits=["100/minute", "5/second"],
    storage_uri="redis://localhost:6379/1",
    headers_enabled=True,
    key_prefix="myapp_rl",
    enabled=True,
)
```

### RateLimitSettings 方式

```python
from yweb.config import AppSettings, load_yaml_config

class Settings(AppSettings):
    app_name: str = "My App"

settings = load_yaml_config("config/settings.yaml", Settings)
limiter = setup_ratelimit(app, settings=settings.ratelimit)
```

对应的 YAML 配置：

```yaml
ratelimit:
  enabled: true
  default_limits: ["100/minute", "5/second"]
  storage_uri: "redis://localhost:6379/1"
  headers_enabled: true
  key_prefix: "myapp_rl"
```

也可通过环境变量覆盖（前缀 `YWEB_RL_`）：

```bash
YWEB_RL_DEFAULT_LIMITS='["50/minute"]'
YWEB_RL_STORAGE_URI=redis://redis:6379/1
YWEB_RL_ENABLED=false
```

### 参数说明

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `default_limits` | `List[str]` | `["60/minute"]` | 全局默认限流规则 |
| `storage_uri` | `str` | `""` (内存) | 存储后端，`redis://...` 用 Redis |
| `headers_enabled` | `bool` | `True` | 响应中包含 `X-RateLimit-*` headers |
| `key_prefix` | `str` | `"yweb_rl"` | 限流计数器 key 前缀 |
| `enabled` | `bool` | `True` | 是否启用限流 |
| `on_limited` | `Callable / List` | `None` | 限流触发时的事件回调 |

### 限流规则语法

格式为 `"次数/周期"`，支持：

```
"5/second"      # 每秒 5 次
"100/minute"    # 每分钟 100 次
"1000/hour"     # 每小时 1000 次
"10000/day"     # 每天 10000 次
```

可同时指定多个规则（全部满足才放行）：

```python
default_limits=["100/minute", "5/second"]
```

---

## 路由限流

### 基本用法

```python
@app.get("/api/v1/users")
@limiter.limit("30/minute")
async def list_users(request: Request, response: Response):
    ...
```

### 豁免限流

```python
@app.get("/health")
@limiter.exempt
async def health(request: Request, response: Response):
    ...
```

### 共享限流（多个路由共用配额）

```python
@app.get("/api/v1/search")
@limiter.shared_limit("50/minute", scope="search_api")
async def search(request: Request, response: Response):
    ...

@app.get("/api/v1/suggest")
@limiter.shared_limit("50/minute", scope="search_api")
async def suggest(request: Request, response: Response):
    ...
```

### 在 APIRouter 上使用

```python
from fastapi import APIRouter

router = APIRouter()

@router.get("/items")
@limiter.limit("20/minute")
async def list_items(request: Request, response: Response):
    ...

app.include_router(router, prefix="/api/v1")
```

---

## 身份识别

### 默认策略：get_user_or_ip

`setup_ratelimit()` 默认使用 `get_user_or_ip` 作为 key 函数：

1. 尝试从 `Authorization: Bearer <token>` 解析 JWT，提取 `sub` 或 `user_id`
2. 解析失败（无 token / 匿名） → fallback 到客户端 IP

这意味着已登录用户按用户 ID 限流，匿名用户按 IP 限流。

### 纯 IP 限流

```python
from yweb.ratelimit import setup_ratelimit, get_remote_address

limiter = setup_ratelimit(app, key_func=get_remote_address)
```

### 自定义 key 函数

```python
def key_by_api_key(request: Request) -> str:
    return request.headers.get("X-API-Key", "anonymous")

limiter = setup_ratelimit(app, key_func=key_by_api_key)
```

### 路由级别覆盖 key 函数

```python
@app.post("/api/v1/login")
@limiter.limit("5/minute", key_func=get_remote_address)
async def login(request: Request, response: Response):
    ...
```

---

## 429 响应格式

超限时自动返回 yweb 统一格式：

```json
{
  "status": "error",
  "message": "请求过于频繁，请稍后再试（限制: 5 per 1 minute）",
  "data": null
}
```

响应头包含（当 `headers_enabled=True`）：

```
X-RateLimit-Limit: 5
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1711459200
Retry-After: 52
```

---

## 事件订阅

限流模块提供事件总线，当请求被限流时自动广播 `RateLimitedEvent`，你可以订阅此事件实现自定义处理（如记录到数据库、发送告警）。

### 订阅方式一：直接使用事件总线

```python
from yweb.ratelimit import rate_limit_event_bus, RateLimitedEvent

def save_to_db(event: RateLimitedEvent):
    RateLimitLog(
        client_id=event.client_id,
        path=event.path,
        method=event.method,
        limit=event.limit,
        created_at=event.timestamp,
    ).add(commit=True)

rate_limit_event_bus.subscribe(save_to_db)
```

### 订阅方式二：初始化时传入

```python
limiter = setup_ratelimit(
    app,
    default_limits=["100/minute"],
    on_limited=save_to_db,
)

# 或多个回调
limiter = setup_ratelimit(
    app,
    default_limits=["100/minute"],
    on_limited=[save_to_db, send_alert],
)
```

### RateLimitedEvent 字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `client_id` | `str` | 限流标识，如 `"user:123"` 或 `"ip:10.0.0.1"` |
| `path` | `str` | 请求路径 |
| `method` | `str` | HTTP 方法 |
| `limit` | `str` | 触发的限流规则，如 `"5 per 1 minute"` |
| `timestamp` | `datetime` | 触发时间（UTC） |
| `headers` | `dict` | 请求头摘要（仅安全字段，不含 Authorization） |

### 注意事项

- 事件在 429 响应返回前同步触发
- 单个订阅者异常只记 warning，不影响其他订阅者和响应
- 如果需要做耗时操作（写数据库、发告警），建议在订阅者中将任务丢到后台队列

---

## 最佳实践

### 1. 按场景设置不同限制

```python
# 登录接口：严格限流，防暴力破解
@app.post("/api/v1/login")
@limiter.limit("5/minute", key_func=get_remote_address)
async def login(request: Request, response: Response):
    ...

# 数据查询接口：适度限流
@app.get("/api/v1/users")
@limiter.limit("60/minute")
async def list_users(request: Request, response: Response):
    ...

# 健康检查：不限流
@app.get("/health")
@limiter.exempt
async def health(request: Request, response: Response):
    ...
```

### 2. 生产环境使用 Redis 后端

内存后端仅适合单进程开发环境。生产环境多进程/多实例部署时必须使用 Redis：

```yaml
ratelimit:
  storage_uri: "redis://redis:6379/1"
```

### 3. 登录接口用 IP 限流

登录接口应按 IP 而非用户身份限流（因为此时用户尚未认证）：

```python
@limiter.limit("5/minute", key_func=get_remote_address)
```

### 4. 灰度/测试时可禁用

```yaml
ratelimit:
  enabled: false
```

或通过环境变量：`YWEB_RL_ENABLED=false`

---

## API 参考

### setup_ratelimit()

```python
def setup_ratelimit(
    app: FastAPI,
    *,
    default_limits: Optional[List[str]] = None,
    storage_uri: Optional[str] = None,
    key_func: Optional[Callable] = None,
    headers_enabled: bool = True,
    key_prefix: str = "yweb_rl",
    enabled: bool = True,
    settings: Optional[RateLimitSettings] = None,
    on_limited: Optional[Union[Callable, List[Callable]]] = None,
) -> Limiter
```

### RateLimitSettings

```python
class RateLimitSettings(BaseSettings):
    enabled: bool = True
    default_limits: List[str] = ["60/minute"]
    storage_uri: str = ""
    headers_enabled: bool = True
    key_prefix: str = "yweb_rl"

    class Config:
        env_prefix = "YWEB_RL_"
```

### Key 函数

| 函数 | 说明 |
|------|------|
| `get_user_or_ip(request)` | JWT user_id 优先，fallback IP（默认） |
| `get_remote_address(request)` | 纯 IP，支持 X-Forwarded-For |

### 事件总线

```python
rate_limit_event_bus.subscribe(callback)    # 订阅
rate_limit_event_bus.unsubscribe(callback)  # 取消订阅
rate_limit_event_bus.subscriber_count       # 当前订阅者数量
rate_limit_event_bus.clear()                # 清空所有订阅
```
