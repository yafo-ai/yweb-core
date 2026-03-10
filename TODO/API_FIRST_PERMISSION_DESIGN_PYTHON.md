# API First 权限方案设计（Python 版）

## 1. 目标与背景

本文设计一套以 **Web API 为唯一权限源** 的权限方案，目标是解决以下问题：

- 前端不再为每个按钮手写权限码。
- 前端不再为每个按钮维护 `actionKey`。
- 不再围绕“页面有哪些按钮”做前后端反复沟通。
- 权限只挂在后端 API 上，前端通过 API 元数据自动判断按钮是否可见、可点击。
- 后端仍然保留真正的安全边界，前端只负责体验层的显示控制。

这套方案尤其适合：

- Python 后端
- 前后端分离项目
- 有 OpenAPI / Swagger 文档能力的系统
- 中后台系统、运营后台、管理台

## 2. 核心思想

传统按钮权限方案一般是这样的：

- 后端接口定义权限码
- 前端按钮手写同一个权限码
- 数据库再维护一份页面/按钮/权限关系

问题在于：

- 权限信息被维护了多份
- 前后端必须围绕页面细节反复沟通
- 页面越多、按钮越多，维护成本越高

本方案改成：

1. **后端接口是唯一权限源**
2. **权限声明只写在后端接口上**
3. **后端把 API 的权限元数据暴露到 OpenAPI**
4. **前端 API 客户端自动生成，并携带权限元数据**
5. **前端按钮只绑定 API 函数，不再手写权限码**
6. **前端根据 API 元数据自动判断当前用户是否可调用该 API**

一句话概括：

**权限不再围绕按钮建模，而是围绕 API 能力建模；按钮权限只是 API 权限的自动投影。**

## 3. 总体架构

### 3.1 数据流

```text
后端路由定义
  -> 声明权限（permission）
  -> 生成 OpenAPI，附带 x-permission / x-resource / x-action
  -> 前端根据 OpenAPI 生成 API Client
  -> 每个 API 方法自带权限元数据
  -> 登录后拿到当前用户 permission 集合
  -> 按钮绑定 API 方法
  -> 通用组件自动判断是否允许调用
```

### 3.2 职责边界

后端负责：

- 定义 API
- 定义权限
- 校验权限
- 产出权限元数据

前端负责：

- 按 API 使用，不关心具体权限码细节
- 根据 API 元数据做显示控制
- 不承担真正安全职责

数据库负责：

- 只维护角色、用户、权限关系
- 不强制维护页面按钮表
- 如果有菜单系统，菜单只管理导航，不再作为按钮权限源

## 4. 方案设计原则

### 4.1 单一权限源

权限只在后端接口侧声明一次，避免：

- 前端重复写权限码
- 数据库重复存页面按钮权限
- 文档重复描述权限

### 4.2 前端不猜，只读取元数据

前端不去分析 `onClick`、不解析页面逻辑、不做静态推导。  
前端只使用一个可靠事实：

- 这个按钮绑定的是哪个 API 方法
- 这个 API 方法的权限是什么

### 4.3 后端是真正边界

无论前端是否隐藏按钮，后端都必须继续做权限拦截。  
前端自动鉴权只是提升体验，不是安全边界。

### 4.4 权限粒度以 API 为主

推荐按 API 动作定义权限，例如：

- `user:list`
- `user:read`
- `user:create`
- `user:update`
- `user:delete`
- `user:export`

而不是按页面、按钮名称定义权限，例如：

- `page-user-add-button`
- `btn_user_create`

因为页面和按钮是 UI 概念，API 才是业务能力概念。

## 5. Python 后端设计

## 5.1 推荐技术路线

如果你使用 Python，我推荐优先采用：

- **FastAPI**：天然支持 OpenAPI，最适合这个方案

也可以兼容：

- Flask + `apispec` / `flask-smorest`
- Django + `drf-spectacular`
- Django Ninja

其中 FastAPI 成本最低，因为：

- 路由定义天然结构化
- OpenAPI 自动生成能力成熟
- 扩展自定义元数据相对清晰

下文以 **FastAPI** 为主进行设计，其他框架可以套同样的思想。

## 5.2 API 权限声明方式

推荐给每个路由增加统一的权限声明字段，例如：

```python
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/users", tags=["users"])


@router.post(
    "",
    summary="创建用户",
    openapi_extra={
        "x-permission": "user:create",
        "x-resource": "user",
        "x-action": "create",
    },
)
async def create_user(
    payload: UserCreateIn,
    current_user=Depends(require_permission("user:create")),
):
    ...
```

这个设计里有两层：

1. `require_permission("user:create")`
   - 真正做后端鉴权
2. `openapi_extra["x-permission"]`
   - 暴露给前端生成 API 元数据

它们必须使用同一个权限值，避免漂移。

## 5.3 避免重复声明：封装统一装饰器

为了避免同时写两次权限码，建议封装一个统一路由注册器。

示意代码：

```python
from typing import Any, Callable


def api_permission(permission: str, resource: str | None = None, action: str | None = None):
    def decorator(route_kwargs: dict[str, Any]) -> dict[str, Any]:
        extra = route_kwargs.setdefault("openapi_extra", {})
        extra["x-permission"] = permission
        if resource:
            extra["x-resource"] = resource
        if action:
            extra["x-action"] = action
        route_kwargs["dependencies"] = route_kwargs.get("dependencies", []) + [
            Depends(require_permission(permission))
        ]
        return route_kwargs
    return decorator
```

或者更直接一点，封装自己的 `route` 方法：

```python
def register_api(
    router: APIRouter,
    method: str,
    path: str,
    *,
    permission: str,
    resource: str | None = None,
    action: str | None = None,
    **kwargs,
):
    extra = kwargs.setdefault("openapi_extra", {})
    extra["x-permission"] = permission
    if resource:
        extra["x-resource"] = resource
    if action:
        extra["x-action"] = action

    dependencies = kwargs.setdefault("dependencies", [])
    dependencies.append(Depends(require_permission(permission)))

    def wrapper(func):
        router.add_api_route(path, func, methods=[method], **kwargs)
        return func

    return wrapper
```

使用时：

```python
@register_api(
    router,
    "POST",
    "",
    permission="user:create",
    resource="user",
    action="create",
    summary="创建用户",
)
async def create_user(payload: UserCreateIn):
    ...
```

这样，权限码只写一次。

## 5.4 权限校验模型

推荐后端采用 RBAC 基础模型：

- `users`
- `roles`
- `permissions`
- `user_roles`
- `role_permissions`

如果你已有用户角色体系，不一定要重建，只要最终能得到：

```python
current_user.permissions: set[str]
```

即可。

校验函数示意：

```python
from fastapi import HTTPException, status


def require_permission(permission: str):
    async def checker(current_user=Depends(get_current_user)):
        if current_user.is_superuser:
            return current_user
        if permission not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"missing permission: {permission}",
            )
        return current_user

    return checker
```

如果你想支持通配权限，也可以扩展成：

- `user:*`
- `report:*`
- `*:*`

但建议前后端统一匹配规则，避免后端允许、前端不显示，或前端显示、后端拒绝。

## 5.5 登录后返回什么

登录成功或获取当前用户信息时，建议返回：

```json
{
  "user": {
    "id": 1,
    "username": "alice"
  },
  "roles": ["admin"],
  "permissions": [
    "user:list",
    "user:read",
    "user:create",
    "user:update"
  ]
}
```

其中前端最关键的是：

- `permissions`

这是运行时快速判断按钮显示状态的本地依据。

## 5.6 OpenAPI 扩展格式约定

建议所有需要鉴权的接口都输出以下扩展字段：

```json
{
  "x-permission": "user:create",
  "x-resource": "user",
  "x-action": "create",
  "x-auth-required": true
}
```

建议约定如下：

- `x-permission`：最终权限码，前后端判断主依据
- `x-resource`：资源名，可用于统计、分组、生成菜单
- `x-action`：动作名，可用于通用按钮、审计、页面能力映射
- `x-auth-required`：是否要求登录

其中真正必须的是：

- `x-permission`

其他字段主要用于增强可读性和后续扩展。

## 6. 前端设计

## 6.1 前端不要再手写权限码

旧方式：

```vue
<el-button v-hasPermi="['user:create']">新增</el-button>
```

新方式：

```vue
<PermButton :api="createUserApi" @click="handleCreate">
  新增
</PermButton>
```

此时按钮组件只接收一个事实：

- 它关联的 API 方法是 `createUserApi`

它不再接收：

- 权限码
- actionKey
- 页面按钮 ID

## 6.2 API Client 自动生成目标

前端应当根据 OpenAPI 生成如下结果：

```ts
export const createUserApi = defineApi({
  operationId: "create_user",
  method: "POST",
  path: "/users",
  permission: "user:create",
  resource: "user",
  action: "create",
  request: (data) => http.post("/users", data),
})
```

这样前端按钮只认 API 对象。

## 6.3 `defineApi` 统一结构

建议所有 API 方法都包装成统一结构：

```ts
export type ApiDefinition<TArgs = any, TResult = any> = {
  operationId: string
  method: string
  path: string
  permission?: string
  resource?: string
  action?: string
  request: (args: TArgs) => Promise<TResult>
}

export function defineApi<TArgs, TResult>(api: ApiDefinition<TArgs, TResult>) {
  return api
}
```

这样前端任意组件都可以通过 `api.permission` 直接判断。

## 6.4 权限判断函数

```ts
export function hasPermission(
  userPermissions: Set<string>,
  permission?: string
): boolean {
  if (!permission) {
    return true
  }
  if (userPermissions.has("*:*") || userPermissions.has("*")) {
    return true
  }
  if (userPermissions.has(permission)) {
    return true
  }

  const [resource, action] = permission.split(":")
  if (userPermissions.has(`${resource}:*`)) {
    return true
  }

  return false
}
```

注意：

- 前后端最好统一通配匹配规则
- 否则 UI 表现会和后端结果不一致

## 6.5 通用按钮组件 `PermButton`

示意实现：

```tsx
type PermButtonProps = {
  api: ApiDefinition<any, any>
  disabled?: boolean
  hiddenMode?: "remove" | "disable"
  onClick?: () => void
  children: React.ReactNode
}

function PermButton(props: PermButtonProps) {
  const permissions = useCurrentUserPermissions()
  const allowed = hasPermission(permissions, props.api.permission)

  if (!allowed && props.hiddenMode !== "disable") {
    return null
  }

  return (
    <button
      disabled={props.disabled || !allowed}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  )
}
```

如果你是 Vue，也同理：

```ts
const props = defineProps<{
  api: ApiDefinition
  disabled?: boolean
  mode?: "remove" | "disable"
}>()

const permissions = usePermissionStore()
const allowed = computed(() => hasPermission(permissions.set, props.api.permission))
```

核心点不在于框架，而在于：

- 组件只接收 API
- 组件自动从 API 读取权限元数据

## 6.6 页面如何使用

标准 CRUD 页面示例：

```ts
import { listUserApi, createUserApi, updateUserApi, deleteUserApi } from "@/apis/user"
```

```vue
<PermButton :api="createUserApi" @click="openCreateDialog">新增</PermButton>
<PermButton :api="updateUserApi" @click="openEditDialog">编辑</PermButton>
<PermButton :api="deleteUserApi" @click="handleDelete">删除</PermButton>
```

这样页面开发者不再需要知道权限码是什么。  
他只需要知道：

- 这个按钮关联哪个 API

## 6.7 特殊情况处理

### 一个按钮可能调用多个 API

例如“保存”按钮，可能：

- 新增时调用 `create`
- 编辑时调用 `update`

此时建议显式使用一个动态 API 引用：

```ts
const submitApi = computed(() => isEdit.value ? updateUserApi : createUserApi)
```

```vue
<PermButton :api="submitApi" @click="handleSubmit">保存</PermButton>
```

或者组件支持数组：

```vue
<PermButton :apis="[createUserApi, updateUserApi]" mode="disable">保存</PermButton>
```

规则可以定义为：

- `or`：有任一权限即可显示
- `and`：必须全部拥有才显示

标准场景建议默认 `or`。

### 一个按钮只打开弹窗，不直接调 API

仍然建议给它绑定“最终提交 API”。  
因为用户真正关心的是：

- 是否有资格进入这个操作流程

而不是当前点击时是否立刻发请求。

### 按钮触发的是导入/导出/下载

也应该当作 API 能力处理，例如：

- `report:export`
- `user:import`

不要因为它是下载链接就绕开权限元数据模型。

## 7. OpenAPI 到前端 API Client 的生成方案

## 7.1 生成目标

建议生成两部分产物：

1. API 请求方法
2. API 元数据描述

例如生成：

```ts
export const createUserApi = defineApi({
  operationId: "createUser",
  method: "POST",
  path: "/users",
  permission: "user:create",
  resource: "user",
  action: "create",
  request: (data) => http.post("/users", data),
})
```

## 7.2 最小生成规则

从 OpenAPI 中读取：

- `operationId`
- `method`
- `path`
- `x-permission`
- `x-resource`
- `x-action`

映射到前端。

## 7.3 不建议的做法

不建议前端自己去扫描源码推断：

- 某个按钮会不会调用某个 API
- 某个 `handleSubmit` 最终会不会触发哪个请求

因为这会导致：

- 推断不稳定
- 重构时易失效
- 很难覆盖动态逻辑

正确做法是：

- 后端输出元数据
- 前端生成 API 客户端
- 页面绑定 API 客户端

## 8. 数据库设计建议

## 8.1 仍然保留 RBAC

推荐最小表结构：

- `user`
- `role`
- `permission`
- `user_role`
- `role_permission`

可选：

- `permission_group`
- `resource`

## 8.2 `permission` 表建议

示意字段：

| 字段 | 含义 |
| --- | --- |
| `id` | 主键 |
| `code` | 权限码，如 `user:create` |
| `name` | 权限名称，如“创建用户” |
| `resource` | 资源名，如 `user` |
| `action` | 动作名，如 `create` |
| `description` | 说明 |
| `status` | 状态 |

你可以让权限表来自：

- 手工维护
- 代码扫描同步
- OpenAPI 自动导入

## 8.3 推荐做法：以代码为源，同步到数据库

最推荐的是：

1. 后端代码里声明权限
2. 启动时或 CI 中扫描 OpenAPI
3. 自动把权限同步到数据库 `permission` 表
4. 管理后台只负责“角色绑定权限”，不负责手工创建每个按钮权限

这样可以避免：

- 前端先建按钮
- 后端再补权限
- 数据库再录一遍

而是改成：

- 后端新增 API
- 权限自动注册
- 运营侧只需给角色分配权限

## 9. 推荐的权限命名规范

建议采用：

```text
<resource>:<action>
```

例如：

- `user:list`
- `user:read`
- `user:create`
- `user:update`
- `user:delete`
- `user:import`
- `user:export`
- `order:audit`
- `order:cancel`

不建议：

- 把页面名混进权限码
- 把按钮文案混进权限码
- 使用过长、不可预测的名称

推荐动作集合：

- `list`
- `read`
- `create`
- `update`
- `delete`
- `import`
- `export`
- `audit`
- `approve`
- `reject`
- `publish`
- `execute`

## 10. 后端框架落地建议（FastAPI）

## 10.1 基础约定

统一要求：

- 每个受保护接口必须声明权限
- 每个受保护接口必须输出 `x-permission`
- 所有前端 API 都必须从 OpenAPI 生成，不允许手写裸请求作为主路径

## 10.2 统一注册器

建议你封装一个项目级工具，例如：

```python
def secure_route(
    router: APIRouter,
    method: str,
    path: str,
    *,
    permission: str,
    summary: str,
    resource: str | None = None,
    action: str | None = None,
    **kwargs,
):
    extra = kwargs.setdefault("openapi_extra", {})
    extra["x-auth-required"] = True
    extra["x-permission"] = permission
    extra["x-resource"] = resource or permission.split(":")[0]
    extra["x-action"] = action or permission.split(":")[1]

    dependencies = kwargs.setdefault("dependencies", [])
    dependencies.append(Depends(require_permission(permission)))

    def wrapper(func):
        router.add_api_route(path, func, methods=[method], summary=summary, **kwargs)
        return func

    return wrapper
```

这样以后新增接口时，开发者只关注：

- 路径
- 方法
- 权限码
- 业务逻辑

## 10.3 OpenAPI 清洗与导出

建议增加一个脚本，导出简化版权限清单，例如：

```json
[
  {
    "operationId": "createUser",
    "method": "POST",
    "path": "/users",
    "permission": "user:create",
    "resource": "user",
    "action": "create"
  }
]
```

用途包括：

- 前端代码生成
- 权限同步数据库
- 审计与对账
- 生成管理台说明

## 11. 前端落地建议

## 11.1 统一使用生成 API

不要再鼓励这种写法：

```ts
http.post("/users", payload)
```

应该统一通过：

```ts
createUserApi.request(payload)
```

原因是裸请求丢失了：

- 权限元数据
- 资源元数据
- 操作名元数据

而你的整个自动权限方案，恰恰就依赖这些元数据。

## 11.2 提供 Hook / Composable

例如：

```ts
function useApiPermission(api: ApiDefinition | Ref<ApiDefinition>) {
  const permissions = usePermissionStore()
  return computed(() => {
    const target = unref(api)
    return hasPermission(permissions.set, target.permission)
  })
}
```

这样页面和组件都可以复用。

## 11.3 对表格操作列的支持

封装：

```vue
<ApiAction :api="updateUserApi" @click="edit(row)">编辑</ApiAction>
<ApiAction :api="deleteUserApi" @click="remove(row)">删除</ApiAction>
```

这样业务页面不会再出现散落的权限判断逻辑。

## 12. 菜单系统如何处理

如果你仍然需要菜单导航，建议做如下切分：

- **菜单系统**：只负责导航、分组、页面入口
- **API 权限系统**：只负责业务能力控制

也就是说：

- 菜单可以存在数据库
- 但按钮权限不再依赖菜单表去维护
- 页面是否显示某个按钮，由按钮绑定的 API 决定

这样可以避免原来那种：

- 页面按钮
- 菜单按钮
- 接口权限

三套东西来回对齐。

## 13. 迁移方案

## 13.1 现状假设

你当前可能类似这样：

- 后端接口有权限装饰器
- 前端按钮有权限指令
- 菜单/按钮权限在数据库中维护

## 13.2 迁移目标

迁移后变成：

- 后端接口继续有权限装饰器
- OpenAPI 输出权限扩展元数据
- 前端按钮改为绑定 API
- 前端不再手写权限码
- 按钮权限不再由菜单表维护

## 13.3 分阶段迁移

### 第一阶段：保留旧模型，补齐 OpenAPI 元数据

先不动前端，只做：

- 后端所有权限接口增加 `x-permission`
- 确保 OpenAPI 可以导出完整权限清单

验收标准：

- 所有需要鉴权的 API 都能在 OpenAPI 中看到权限码

### 第二阶段：生成 API Client

建立统一 API 生成产物：

- 请求函数
- 权限元数据

验收标准：

- 前端新页面优先使用生成 API，而非裸请求

### 第三阶段：引入 `PermButton`

先在新页面使用：

- 按钮绑定 API
- 不再手写权限码

验收标准：

- 新页面无 `v-hasPermi`
- 页面仍具备完整按钮权限控制

### 第四阶段：逐步废弃按钮权限表

保留菜单表，但停止把按钮权限当成菜单项维护。  
角色权限改为直接绑定权限码。

验收标准：

- 角色权限源与 API 权限清单一致
- 页面按钮权限不再依赖菜单按钮项

## 14. 风险与对策

## 14.1 风险：前端仍然绕过生成 API，直接写裸请求

后果：

- 自动权限失效

对策：

- 统一封装请求层
- ESLint/代码审查限制业务层直接调用裸 `http`

## 14.2 风险：后端权限注解与 OpenAPI 元数据不一致

后果：

- 前端显示和后端真实放行不一致

对策：

- 使用统一装饰器/统一注册器
- 不允许手写两份权限码

## 14.3 风险：一个按钮关联多个 API

后果：

- 自动判断模型复杂化

对策：

- 允许按钮绑定单个动态 API
- 或支持 `apis` 数组 + `or/and` 规则

## 14.4 风险：复杂业务动作不属于标准 CRUD

后果：

- 页面开发者不确定按钮该绑定哪个 API

对策：

- 明确约定：按钮绑定“最终业务动作 API”
- 不绑定局部校验 API、预检查 API

## 15. 推荐的最小落地版本

如果你想尽快开始，不必一次做完所有能力。  
建议先落最小版本：

1. 后端所有受保护接口统一声明 `permission`
2. OpenAPI 暴露 `x-permission`
3. 前端生成 API Client，带 `permission`
4. 登录后拿到当前用户 `permissions`
5. 提供 `hasPermission()` 与 `PermButton`
6. 新页面全部通过 `:api="xxxApi"` 控制按钮显示

这样你已经能解决 80% 的痛点：

- 不手写按钮权限码
- 不手写 `actionKey`
- 不需要围绕页面按钮反复沟通

## 16. 与你当前诉求的对应关系

你的核心诉求是：

- 不想写按钮名称
- 不想写 `actionKey`
- 不想为页面按钮和后端权限做大量人工对齐
- 希望直接围绕 Web API 建权限

这套方案对你的回答是：

- **可以不写按钮名称作为权限依据**
- **可以不写 `actionKey`**
- **可以不按页面/按钮存库**
- **可以直接以 Web API 为权限中心**

但仍然保留一个必要约束：

- **按钮必须绑定某个 API 定义**

这不是额外负担，而是最小且可靠的“语义锚点”。  
没有这个锚点，前端无法稳定知道这个按钮对应什么业务能力。

## 17. 最终结论

对于 Python 项目，最推荐的实现方式是：

- 以后端 API 权限注解为唯一权限源
- 通过 OpenAPI 扩展字段把权限元数据暴露出来
- 前端自动生成带权限元数据的 API Client
- 页面按钮只绑定 API，不再绑定权限码
- 菜单系统与 API 权限系统解耦

最终效果是：

- 后端新增一个 API，并声明权限
- 权限自动进入 OpenAPI
- 前端自动获得该 API 的权限元数据
- 按钮只要绑定这个 API，就能自动判断显示权限

这就是一套真正可落地的 **API First 权限方案**。

## 18. 后续可继续扩展的内容

如果后面要继续深化，这套方案还可以继续扩展：

- OpenAPI -> 权限表自动同步脚本
- 前端 API Client 自动生成器
- `PermButton` / `ApiAction` 组件库
- 资源能力模型（`resource + action`）的进一步收敛
- 审计日志中自动记录 `operationId / permission`
- 管理后台自动展示“角色可调用 API 列表”

---

如果要进入实施阶段，建议优先完成三件事：

1. Python 后端统一权限装饰器与 OpenAPI 扩展输出
2. 前端 API Client 生成格式定型
3. 通用 `PermButton` 能力落地

这样整套方案就能跑起来了。
