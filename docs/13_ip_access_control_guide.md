# YWeb IP 访问控制指南

本指南介绍 YWeb 提供的 IP 访问控制能力，帮助你按 IP 地址限制 Web API 的访问范围。

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [三种控制粒度](#三种控制粒度)
  - [装饰器 — 单个端点](#1-装饰器--单个端点推荐)
  - [依赖注入 — Router 级别](#2-依赖注入--router-级别)
  - [中间件 — 全局路径规则](#3-中间件--全局路径规则)
- [IP 匹配格式](#ip-匹配格式)
- [代理环境下的真实 IP 提取](#代理环境下的真实-ip-提取)
- [匹配规则详解](#匹配规则详解)
- [配置文件驱动](#配置文件驱动)
- [IP 工具函数](#ip-工具函数)
- [常见场景](#常见场景)
- [注意事项](#注意事项)
- [API 参考](#api-参考)

---

## 概述

YWeb 的 IP 访问控制提供三种粒度，可以按需选择或组合使用：

| 粒度 | 方式 | 适用场景 |
|------|------|---------|
| 单个端点 | `@ip_allow` / `@ip_deny` 装饰器 | 某个 API 仅内网访问 |
| 整个 Router | `Depends(IPAllow(...))` 依赖注入 | 管理模块统一限制 |
| 全局路径规则 | `IPAccessMiddleware` 中间件 | 通过 YAML 配置批量管理 |

支持的 IP 格式：单 IP、CIDR 网段、`*` 通配符，同时支持 IPv4 和 IPv6。

---

## 快速开始

### 30 秒上手：给一个 API 加白名单

```python
from yweb.middleware.ip_access import ip_allow

@app.post("/admin/sync")
@ip_allow(["192.168.0.0/16", "10.0.0.0/8"])
async def sync_data():
    return {"synced": True}
```

效果：只有内网 IP（`192.168.x.x` 和 `10.x.x.x`）能访问这个端点，其他 IP 返回 403。

---

## 三种控制粒度

### 1. 装饰器 — 单个端点（推荐）

最简洁的方式，直接标注在路由函数上：

```python
from yweb.middleware.ip_access import ip_allow, ip_deny

# 白名单：仅允许指定 IP
@app.post("/admin/sync")
@ip_allow(["10.0.0.0/8", "192.168.0.0/16"])
async def sync_data():
    ...

# 黑名单：拒绝指定 IP
@app.get("/api/data")
@ip_deny(["1.2.3.4", "5.6.7.0/24"])
async def get_data():
    ...

# 黑名单 + 白名单豁免：拒绝所有，仅允许本机
@app.get("/debug")
@ip_deny(["0.0.0.0/0"], allow=["127.0.0.1", "::1"])
async def debug_info():
    ...
```

**特点：**

- 不破坏 FastAPI 的参数注入（Path、Query、Body、Depends 全部正常）
- `request` 参数不出现在 OpenAPI 文档中
- 支持同步和异步函数
- 支持多个装饰器叠加

**装饰器与已有 request 参数兼容：**

```python
@app.get("/info")
@ip_allow(["*"])
async def info(request: Request):
    # request 参数正常可用
    return {"client_ip": request.client.host}
```

**自定义拒绝响应：**

```python
@app.post("/webhook")
@ip_allow(
    ["203.0.113.0/24"],
    status_code=451,
    message="此端点仅允许合作方 IP 访问",
)
async def webhook():
    ...
```

### 2. 依赖注入 — Router 级别

适合对整个 Router 下的所有路由统一限制：

```python
from fastapi import APIRouter, Depends
from yweb.middleware.ip_access import IPAllow, IPDeny

# 整个 admin Router 仅内网可访问
admin_router = APIRouter(
    prefix="/api/v1/admin",
    dependencies=[Depends(IPAllow(["192.168.0.0/16", "10.0.0.0/8"]))],
)

@admin_router.get("/users")
async def list_users():
    ...

@admin_router.post("/settings")
async def update_settings():
    ...
```

也可以用在单个路由上（语法比装饰器稍长）：

```python
@app.post(
    "/webhook",
    dependencies=[Depends(IPAllow(["203.0.113.0/24"]))],
)
async def webhook():
    ...
```

### 3. 中间件 — 全局路径规则

适合通过配置文件集中管理，在 `main.py` 中一次性注册：

```python
from yweb.middleware.ip_access import IPAccessMiddleware, IPAccessRule

app.add_middleware(
    IPAccessMiddleware,
    rules=[
        IPAccessRule(
            paths=["/api/v1/admin/*"],
            allow_ips=["192.168.0.0/16", "10.0.0.0/8"],
            description="管理后台仅内网",
        ),
        IPAccessRule(
            paths=["/api/v1/oauth2/*"],
            allow_ips=["*"],
            description="OAuth2 端点对外开放",
        ),
    ],
    default_policy="allow",
    trusted_proxies=["127.0.0.1"],
)
```

**推荐使用配置文件驱动**（见 [配置文件驱动](#配置文件驱动) 章节）。

---

## IP 匹配格式

所有 `allow_ips`、`deny_ips`、`trusted_proxies` 参数都支持以下格式：

| 格式 | 示例 | 说明 |
|------|------|------|
| 单 IP | `"192.168.1.100"` | 精确匹配一个 IP |
| CIDR 网段 | `"192.168.0.0/16"` | 匹配整个子网 |
| 通配符 | `"*"` | 匹配所有 IP |
| IPv6 | `"::1"` | 支持 IPv6 地址 |
| IPv6 CIDR | `"fe80::/10"` | 支持 IPv6 网段 |

**常用内网网段：**

```python
PRIVATE_NETWORKS = [
    "10.0.0.0/8",       # A 类私有
    "172.16.0.0/12",     # B 类私有
    "192.168.0.0/16",    # C 类私有
    "127.0.0.0/8",       # 环回
    "::1",               # IPv6 环回
]
```

---

## 代理环境下的真实 IP 提取

当应用部署在 Nginx / 负载均衡器后面时，`request.client.host` 返回的是代理的 IP，而非客户端真实 IP。通过配置 `trusted_proxies` 解决：

```python
# 装饰器
@ip_allow(["10.0.0.0/8"], trusted_proxies=["127.0.0.1"])

# 中间件
app.add_middleware(
    IPAccessMiddleware,
    trusted_proxies=["127.0.0.1", "10.0.0.0/8"],
    rules=[...],
)
```

**提取逻辑（按优先级）：**

1. 如果直连 IP 是受信代理 → 从 `X-Forwarded-For` 第一个 IP 获取
2. 如果直连 IP 是受信代理 → 从 `X-Real-IP` 获取
3. 直接使用连接 IP（`request.client.host`）

**安全提示：** 只有直连 IP 在 `trusted_proxies` 列表中时，才会信任代理头。这防止了客户端伪造 `X-Forwarded-For` 来绕过 IP 限制。

**Nginx 配置示例：**

```nginx
location / {
    proxy_pass http://127.0.0.1:8000;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Real-IP $remote_addr;
}
```

---

## 匹配规则详解

### 中间件规则匹配逻辑

`IPAccessMiddleware` 按**规则顺序**遍历，**第一个路径匹配的规则生效**：

```
请求 /api/v1/admin/users
  → 规则1: paths=["/api/v1/admin/*"] → 路径匹配 ✓ → 执行 IP 检查
  → 规则2: paths=["/api/v1/*"]       → 不会执行（规则1已匹配）
```

单条规则内的 IP 检查优先级：

```
1. deny_ips 不为空 且 IP 命中 → 拒绝
2. allow_ips 不为空 且 IP 命中 → 放行
3. allow_ips 不为空 且 IP 未命中 → 拒绝
4. 仅有 deny_ips 且 IP 未命中 → 放行
5. 没有匹配到任何规则 → 使用 default_policy
```

### 路径通配符

中间件的 `paths` 支持 `fnmatch` 通配符：

| 模式 | 匹配 | 不匹配 |
|------|------|--------|
| `"/api/v1/admin/*"` | `/api/v1/admin/users` | `/api/v1/admin/users/1` |
| `"/api/v1/admin*"` | `/api/v1/admin`, `/api/v1/admin/users` | `/api/v1/other` |
| `"/api/*/admin/*"` | `/api/v1/admin/users`, `/api/v2/admin/settings` | `/api/users` |
| `"/api/v1/users"` | `/api/v1/users`（精确） | `/api/v1/users/1` |

---

## 配置文件驱动

推荐在生产环境中使用 YAML 配置管理 IP 规则，修改配置后重启即可生效，无需改代码。

### settings.yaml

```yaml
ip_access:
  enabled: true                      # 是否启用（开发环境设为 false）
  default_policy: allow              # 默认策略：allow / deny
  trusted_proxies:                   # 受信代理列表
    - "127.0.0.1"
  # deny_status_code: 403           # 自定义拒绝状态码
  # deny_message: "IP 访问被拒绝"    # 自定义拒绝消息
  rules:
    - paths: ["/api/v1/admin/*", "/api/v1/users/*", "/api/v1/roles/*"]
      allow_ips: ["192.168.0.0/16", "10.0.0.0/8"]
      description: "管理后台仅允许内网访问"
    - paths: ["/api/v1/oauth2/*"]
      allow_ips: ["*"]
      description: "OAuth2 端点对外开放"
```

### main.py 注册

```python
from yweb.middleware.ip_access import IPAccessMiddleware

# 从配置加载并注册（条件加载，无规则时不注册中间件）
ip_access_config = getattr(settings, 'ip_access', None)
if ip_access_config:
    mw_kwargs = IPAccessMiddleware.from_settings(ip_access_config)
    if mw_kwargs.get("rules"):
        app.add_middleware(IPAccessMiddleware, **mw_kwargs)
```

### 多环境配置

```yaml
# config/settings.yaml（开发环境）
ip_access:
  enabled: false    # 开发环境关闭

# config/settings.prod.yaml（生产环境）
ip_access:
  enabled: true
  default_policy: allow
  trusted_proxies: ["10.0.0.1"]
  rules:
    - paths: ["/api/v1/admin/*"]
      allow_ips: ["192.168.0.0/16"]
      description: "管理后台仅内网"
```

---

## IP 工具函数

`yweb.utils.ip` 模块提供独立的 IP 工具函数，可在任何地方使用（不限于访问控制）：

### get_client_ip

从 Request 对象提取客户端真实 IP：

```python
from yweb.utils.ip import get_client_ip

@app.get("/whoami")
async def whoami(request: Request):
    ip = get_client_ip(request, trusted_proxies=["127.0.0.1"])
    return {"your_ip": ip}
```

### ip_in_list

检查 IP 是否匹配列表：

```python
from yweb.utils.ip import ip_in_list

# 单 IP
ip_in_list("192.168.1.100", ["192.168.1.100"])  # True

# CIDR
ip_in_list("192.168.1.100", ["192.168.0.0/16"])  # True

# 通配符
ip_in_list("任意IP", ["*"])  # True

# 多规则
ip_in_list("10.1.2.3", ["192.168.0.0/16", "10.0.0.0/8"])  # True

# 不匹配
ip_in_list("8.8.8.8", ["192.168.0.0/16", "10.0.0.0/8"])  # False
```

---

## 常见场景

### 场景一：管理后台仅内网访问

```python
# 方式 A：装饰器（少量端点）
@app.get("/admin/dashboard")
@ip_allow(["192.168.0.0/16", "10.0.0.0/8"])
async def dashboard():
    ...

# 方式 B：Router 级别（整个模块）
admin_router = APIRouter(
    prefix="/admin",
    dependencies=[Depends(IPAllow(["192.168.0.0/16", "10.0.0.0/8"]))],
)

# 方式 C：中间件 + 配置文件（全局管理）
# → 见「配置文件驱动」章节
```

### 场景二：Webhook 仅允许合作方 IP

```python
@app.post("/webhook/github")
@ip_allow(
    ["140.82.112.0/20", "185.199.108.0/22"],
    message="仅允许 GitHub IP 访问",
)
async def github_webhook(payload: dict):
    ...
```

### 场景三：调试端点仅允许本机

```python
@app.get("/debug/routes")
@ip_deny(["0.0.0.0/0"], allow=["127.0.0.1", "::1"])
async def debug_routes():
    ...
```

### 场景四：配合认证使用

IP 控制和认证是独立的，可以组合使用：

```python
@app.delete("/admin/users/{user_id}")
@ip_allow(["192.168.0.0/16"])                    # 先检查 IP
async def delete_user(
    user_id: int,
    user=Depends(auth.get_current_user),          # 再检查认证
):
    ...
```

### 场景五：装饰器叠加

多个 IP 装饰器可以叠加，从外到内依次检查：

```python
@app.post("/sensitive")
@ip_allow(["10.0.0.0/8"])     # 外层：必须是内网
@ip_deny(["10.0.0.99"])       # 内层：但排除特定 IP
async def sensitive_operation():
    ...
```

---

## 注意事项

### 1. 中间件执行顺序

FastAPI 中间件执行顺序是**最后添加的最先执行**。IP 访问控制中间件应在最外层（最后添加），这样被拒绝的请求不会进入日志、认证等后续中间件：

```python
# 推荐的添加顺序
app.add_middleware(RequestLoggingMiddleware, ...)    # 第1个添加（最后执行）
app.add_middleware(PerformanceMonitoringMiddleware)   # 第2个添加
app.add_middleware(RequestIDMiddleware)               # 第3个添加
app.add_middleware(IPAccessMiddleware, ...)           # 第4个添加（最先执行）
```

### 2. 装饰器顺序

`@ip_allow` / `@ip_deny` 必须在 `@app.get()` / `@app.post()` **之后**：

```python
# 正确
@app.post("/admin/sync")
@ip_allow(["10.0.0.0/8"])
async def sync_data():
    ...

# 错误（装饰器在路由注册之前，不会生效）
@ip_allow(["10.0.0.0/8"])
@app.post("/admin/sync")
async def sync_data():
    ...
```

### 3. 性能

- IP 匹配使用 Python 标准库 `ipaddress`，单次匹配耗时微秒级
- 无缓存层设计，规则数量少（几十条以内）时无需担心性能
- 中间件在 ASGI 层直接拒绝，被拦截的请求不会进入 FastAPI 路由层

### 4. 日志

所有拒绝事件会记录 WARNING 级别日志，包含：
- 客户端 IP
- 请求路径
- 拒绝原因（命中的规则描述）

```
WARNING yweb.middleware.ip_access: IP 访问被拒绝: ip=203.0.113.50, path=/api/v1/admin/users, reason=不在白名单中: 管理后台仅内网
```

---

## API 参考

### 装饰器

| 装饰器 | 说明 |
|--------|------|
| `@ip_allow(allow_ips, trusted_proxies=None, status_code=403, message="IP 访问被拒绝")` | 白名单装饰器，仅允许列表中的 IP |
| `@ip_deny(deny_ips, allow=None, trusted_proxies=None, status_code=403, message="IP 访问被拒绝")` | 黑名单装饰器，拒绝列表中的 IP（可选白名单豁免） |

### 依赖注入类

| 类 | 说明 |
|----|------|
| `IPAllow(allow_ips, trusted_proxies=None, deny_status_code=403, deny_message="...")` | 白名单依赖，用于 `Depends()` |
| `IPDeny(deny_ips, allow_ips=None, trusted_proxies=None, deny_status_code=403, deny_message="...")` | 黑名单依赖，用于 `Depends()` |

### 中间件

| 类 | 说明 |
|----|------|
| `IPAccessMiddleware(app, rules, default_policy="allow", trusted_proxies=None, deny_status_code=403, deny_message="...")` | 全局 IP 访问控制中间件 |
| `IPAccessRule(paths, allow_ips=[], deny_ips=[], description="")` | 中间件规则数据类 |
| `IPAccessMiddleware.from_settings(config)` | 从 YAML 配置字典解析中间件参数 |

### 工具函数

| 函数 | 说明 |
|------|------|
| `get_client_ip(request, trusted_proxies=None) -> str` | 从 Request 提取真实客户端 IP |
| `get_client_ip_from_scope(scope, trusted_proxies=None) -> str` | 从 ASGI scope 提取真实客户端 IP |
| `ip_in_list(ip, ip_list) -> bool` | 检查 IP 是否匹配列表（支持单 IP、CIDR、`*`） |

### 导入路径

```python
# 装饰器 + 依赖注入 + 中间件
from yweb.middleware.ip_access import (
    ip_allow, ip_deny,              # 装饰器
    IPAllow, IPDeny,                # 依赖注入
    IPAccessMiddleware, IPAccessRule, # 中间件
)

# 或从 yweb.middleware 统一导入
from yweb.middleware import ip_allow, ip_deny, IPAllow, IPDeny, IPAccessMiddleware

# IP 工具函数
from yweb.utils.ip import get_client_ip, ip_in_list
```
