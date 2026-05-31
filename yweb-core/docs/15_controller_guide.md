# ResourceController 类视图指南

以「一个类 = 一个资源」的方式组织 API，方法名即路由动作，零装饰器、约定优于配置。

---

## 目录

1. [为什么用 ResourceController](#1-为什么用-resourcecontroller)
2. [基础用法](#2-基础用法)
3. [HTTP 方法约定](#3-http-方法约定)
4. [路径分层组合](#4-路径分层组合)
5. [依赖注入](#5-依赖注入)
6. [自动扫描注册](#6-自动扫描注册)
7. [与函数式路由共存](#7-与函数式路由共存)
8. [完整项目示例](#8-完整项目示例)
9. [注意事项](#9-注意事项)

---

## 1. 为什么用 ResourceController

### 现状：函数式路由

```python
connector_router = APIRouter(prefix="/api/v1/connector")

@connector_router.get("/list")
async def list_connectors(): ...

@connector_router.post("/create")
async def create_connector(body: CreateRequest): ...

@connector_router.post("/delete")
async def delete_connector(body: DeleteRequest): ...
```

问题：每个方法都要重复 `@router.method("/action")` 装饰器，同一资源的端点散落各处，无法在类层面共享依赖。

### ResourceController 方式

```python
from yweb.controller import ResourceController, get

class ConnectorController(ResourceController):
    prefix = "/connector"
    tags = ["连接器"]

    @get
    async def list(self, page: int = 1):
        return Resp.OK(ConnectorService.list(page))

    async def create(self, body: CreateRequest):
        return Resp.OK(ConnectorService.create(body))

    async def delete(self, body: DeleteRequest):
        ConnectorService.delete(body.id)
        return Resp.OK()
```

- 方法名即路由路径（`create` → `/create`）
- 默认 POST，`@get` 标记 GET
- 类定义完成时自动生成 `APIRouter`

---

## 2. 基础用法

### 最小示例

```python
from yweb.controller import ResourceController, get

class ItemController(ResourceController):
    prefix = "/item"
    tags = ["项目管理"]

    @get
    async def list(self, page: int = 1, size: int = 10):
        """获取项目列表"""
        items = ItemModel.paginate(page=page, per_page=size)
        return Resp.OK(ItemDTO.from_page(items))

    @get
    async def get(self, item_id: int):
        """获取项目详情"""
        item = ItemModel.get_or_404(item_id)
        return Resp.OK(ItemDTO.from_entity(item))

    async def create(self, body: CreateItemRequest):
        """创建项目"""
        item = ItemService.create(body)
        return Resp.OK(ItemDTO.from_entity(item))

    async def update(self, body: UpdateItemRequest):
        """更新项目"""
        item = ItemService.update(body)
        return Resp.OK(ItemDTO.from_entity(item))

    async def delete(self, body: DeleteRequest):
        """删除项目"""
        ItemService.delete(body.id)
        return Resp.OK()
```

### 挂载到应用

```python
from fastapi import FastAPI

app = FastAPI()
app.include_router(ItemController.router, prefix="/api/v1")
# → GET  /api/v1/item/list
# → GET  /api/v1/item/get
# → POST /api/v1/item/create
# → POST /api/v1/item/update
# → POST /api/v1/item/delete
```

---

## 3. HTTP 方法约定

| 规则 | 说明 |
|------|------|
| 默认 POST | 所有 public 方法默认注册为 POST |
| `@get` 标记 | 需要 GET 的方法用 `@get` 装饰器 |
| `_` 开头 = 私有 | 下划线开头的方法不注册为路由 |

```python
class MyController(ResourceController):
    prefix = "/my"

    @get
    async def list(self): ...        # → GET /my/list

    async def create(self): ...      # → POST /my/create（默认）

    def _helper(self): ...           # → 不注册，私有辅助方法
```

**为什么默认 POST**：实际业务中 80% 以上的接口是写操作（create、update、delete、submit、approve...），只有少量读操作需要 GET。默认 POST 让大多数方法零配置。

---

## 4. 路径分层组合

ResourceController 利用 FastAPI 原生的 `include_router(prefix=...)` 嵌套机制分层组合路径。**目录层级与 URL 路径一一对应**：

```
拼接公式（与目录层级一一对应）：

目录层级:    app / api / v1  / workflow / template.py → create()
               │        │         │           │            │
URL 路径:      │   /api/v1    /workflow    /template     /create
               │   ─────┬─   ────┬────   ─────┬────   ───┬───
               │   全局前缀    模块前缀     prefix       方法名
               │
               └── 最终: POST /api/v1/workflow/template/create
```

### 推荐目录结构

```
app/
├── main.py
└── api/
    └── v1/                              ← 全局前缀 "/api/v1"，目录体现版本
        ├── __init__.py                  ← v1_router, API_PREFIX = "/api/v1"
        ├── workflow/                     ← 模块前缀 "/workflow"
        │   ├── __init__.py              ← workflow_router = APIRouter(prefix="/workflow")
        │   ├── template.py              ← prefix = "/template"
        │   ├── template_form.py         ← prefix = "/template/form"
        │   ├── template_node.py         ← prefix = "/template/node"
        │   └── instance.py              ← prefix = "/instance"
        ├── acl/                          ← 模块前缀 "/acl"
        │   ├── __init__.py              ← acl_router = APIRouter(prefix="/acl")
        │   ├── rules.py                 ← prefix = "/rules"
        │   └── resources.py             ← prefix = "/resources/inheritance"
        ├── connector/                    ← 模块前缀 "/connector"
        │   ├── __init__.py              ← connector_router = APIRouter(prefix="/connector")
        │   └── connector.py             ← prefix = ""（无额外前缀）
        ├── org/                          ← 模块前缀 "/org"
        │   ├── __init__.py              ← org_router = APIRouter(prefix="/org")
        │   ├── user.py                  ← prefix = "/user"
        │   └── department.py            ← prefix = "/department"
        └── ai/                           ← 模块前缀 "/ai"
            ├── __init__.py              ← ai_router = APIRouter(prefix="/ai")
            └── chat.py                  ← prefix = ""
```

### 模块级路由组织

```python
# app/api/v1/workflow/__init__.py
from fastapi import APIRouter

workflow_router = APIRouter(prefix="/workflow", tags=["工作流"])
workflow_router.include_router(TemplateController.router)
workflow_router.include_router(InstanceController.router)
```

### 应用级挂载

```python
# app/main.py
app.include_router(workflow_router, prefix="/api/v1")
app.include_router(connector_router, prefix="/api/v1")
```

### 嵌套资源

```python
class TemplateController(ResourceController):
    prefix = "/template"
    async def create(self): ...           # → POST /api/v1/workflow/template/create

class TemplateNodeController(ResourceController):
    prefix = "/template/node"
    async def create(self): ...           # → POST /api/v1/workflow/template/node/create
```

### 空 prefix（模块本身就是资源）

```python
class ConnectorController(ResourceController):
    prefix = ""                           # 无额外前缀
    async def list(self): ...             # → GET /api/v1/connector/list
```

---

## 5. 依赖注入

### 类级 dependencies（Router 级）

所有方法共享的前置守卫通过 `dependencies` 类属性声明：

```python
from yweb.auth import setup_auth

auth = setup_auth(User)

class ProtectedController(ResourceController):
    prefix = "/admin"
    dependencies = [auth.get_current_user]  # 所有方法都需要登录

    async def dashboard(self): ...
    async def settings(self): ...
```

### 方法级 Depends（FastAPI 原生）

特定方法的额外依赖直接写在参数中：

```python
from fastapi import Depends

class OrderController(ResourceController):
    prefix = "/order"

    async def create(self, body: CreateOrderRequest, user=Depends(auth.get_current_user)):
        order = OrderService.create(body, operator=user)
        return Resp.OK(OrderDTO.from_entity(order))

    @get
    async def list(self, page: int = 1):
        # 这个方法不需要登录
        return Resp.OK(OrderService.list(page))
```

---

## 6. 自动扫描注册

对于约定式项目结构，可以用 `scan_controllers` 一行完成所有控制器的注册：

```python
from yweb.controller import scan_controllers

app = FastAPI()
scan_controllers(app, package="app.api.v1", prefix="/api/v1")
```

`scan_controllers` 会递归扫描指定包下所有 `ResourceController` 子类，自动调用 `app.include_router(controller.router, prefix=prefix)`。

适合项目目录结构已经与 URL 路径对应的场景。

---

## 7. 与函数式路由共存

ResourceController 和函数式路由可以在同一项目中共存。两者都是标准的 `APIRouter`：

```python
# 类视图
class UserController(ResourceController):
    prefix = "/user"
    async def create(self, body: CreateUserRequest): ...

# 函数式（特殊端点）
special_router = APIRouter()

@special_router.post("/webhook/github")
async def github_webhook(request: Request): ...

# 统一挂载
app.include_router(UserController.router, prefix="/api/v1")
app.include_router(special_router, prefix="/api/v1")
```

**选择建议**：

| 场景 | 推荐方式 |
|------|---------|
| 标准 CRUD 资源（大多数业务接口） | ResourceController |
| 特殊协议端点（webhook、OAuth callback） | 函数式路由 |
| 需要细粒度 response_model 控制 | 函数式路由 |
| 新项目、从零开始 | ResourceController |

---

## 8. 完整项目示例

### 目录结构

```
app/
├── main.py
└── api/
    └── v1/
        ├── __init__.py              # v1_router
        ├── workflow/
        │   ├── __init__.py          # workflow_router = APIRouter(prefix="/workflow")
        │   ├── template.py          # TemplateController, prefix="/template"
        │   └── instance.py          # InstanceController, prefix="/instance"
        ├── connector/
        │   ├── __init__.py          # connector_router = APIRouter(prefix="/connector")
        │   └── connector.py         # ConnectorController, prefix=""
        └── org/
            ├── __init__.py          # org_router = APIRouter(prefix="/org")
            ├── user.py              # UserController, prefix="/user"
            └── department.py        # DepartmentController, prefix="/department"
```

### 控制器代码

```python
# app/api/v1/connector/connector.py

from yweb import Resp
from yweb.controller import ResourceController, get
from fastapi import Depends, Query

from app.services.connector import ConnectorService
from app.schemas.connector import CreateConnectorRequest, ConnectorDTO


class ConnectorController(ResourceController):
    prefix = ""
    tags = ["连接器"]

    @get
    async def list(self, page: int = 1, size: int = 10):
        """获取连接器列表"""
        result = ConnectorService.list(page, size)
        return Resp.OK(ConnectorDTO.from_page(result))

    @get
    async def get(self, connector_id: int = Query(...)):
        """获取连接器详情"""
        connector = ConnectorService.get(connector_id)
        return Resp.OK(ConnectorDTO.from_entity(connector))

    async def create(self, body: CreateConnectorRequest):
        """创建连接器"""
        connector = ConnectorService.create(body)
        return Resp.OK(ConnectorDTO.from_entity(connector))

    async def test(self, body: TestConnectorRequest):
        """测试连接器连通性"""
        result = ConnectorService.test(body)
        return Resp.OK(result)
```

### 模块路由组织

```python
# app/api/v1/connector/__init__.py

from fastapi import APIRouter
from .connector import ConnectorController

connector_router = APIRouter(prefix="/connector", tags=["连接器"])
connector_router.include_router(ConnectorController.router)
```

### 应用入口

```python
# app/main.py

from fastapi import FastAPI
from app.api.v1.connector import connector_router
from app.api.v1.workflow import workflow_router
from app.api.v1.org import org_router

app = FastAPI()

API_PREFIX = "/api/v1"
app.include_router(connector_router, prefix=API_PREFIX)
app.include_router(workflow_router, prefix=API_PREFIX)
app.include_router(org_router, prefix=API_PREFIX)
```

---

## 9. 注意事项

### OpenAPI 文档

- 方法的 docstring 第一行自动成为 Swagger 的 `summary`
- 参数的 type hints 自动生成请求体/查询参数的 Schema
- `tags` 类属性控制 Swagger 分组

### 私有方法

下划线开头的方法不参与路由注册，可作为辅助逻辑：

```python
class MyController(ResourceController):
    prefix = "/my"

    async def create(self, body: CreateRequest):
        validated = self._validate(body)
        return Resp.OK(Service.create(validated))

    def _validate(self, body):
        # 私有辅助，不会变成路由
        ...
```

### 同步方法

支持同步和异步方法，两者都能正常工作：

```python
class MyController(ResourceController):
    prefix = "/my"

    async def async_action(self): ...   # 异步，推荐
    def sync_action(self): ...          # 同步，也支持
```

### 每次请求创建新实例

ResourceController 是无状态的——每次请求创建一个新的类实例。不要在实例上存储跨请求状态。
