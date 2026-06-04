# ResourceController 路由迁移评估与结论

> 记录将 yweb-core 各模块 API 从「函数式路由工厂」迁移到 `ResourceController` 类视图的范围、决策、难点与影响评估，供后续模块开发/迁移直接对照。
>
> 最后更新：2026-06-04

---

## 0. 背景

目标 API 风格：**资源树 + 自定义动作**（`模块/api/类名/方法名`，只用 GET/POST，方法名自定义）。
落地手段：`ResourceController` 类视图（方法名即路由路径，默认 POST，`@get` 标 GET）。

核心约束（决定一个模块能否干净迁移）：

> `ResourceController` 的 `router` 在**类定义 / import 时**由 `__init_subclass__ → _register_actions()` **一次性构建**。
> 因此「哪些端点存在」「绑定哪套模型/依赖」必须在 import 时就确定——
> 任何**运行时（工厂被调用时）才决定**注册与否、绑定哪套模型的写法，都与类视图模型根本冲突。

**选用判据**：

- ✅ 适合类视图：**无条件全量注册** + **单一/固定依赖**（单例或单模型）+ 方法名能映射路径。
- ❌ 不适合类视图（保持函数式路由）：**运行时条件注册** / **多套模型并存** / **大量运行时定制回调**。

---

## 1. 已改（迁移为 ResourceController）

### 1.1 ResourceController 框架增强（基础设施）

| 文件 | 改动 |
|------|------|
| `yweb/controller/decorators.py` | `@get/@post` 支持裸用 + 带参；新增 `@route`；支持 `response_model / status_code / dependencies / summary` 等元数据；新增 `path=` 路径覆盖 |
| `yweb/controller/base.py` | 读取并应用上述元数据；**同步方法生成同步端点**（FastAPI 自动放线程池，修复同步 ORM 在事件循环触发 async-safety 的问题）；支持 `path=` 覆盖默认 `/方法名` |

> `path=` 的引入是为了表达方法名无法表达的路径（如连字符 `/reset-password`）。

### 1.2 业务模块迁移（均为**路径不变 + 工厂签名不变**，对外零行为变化）

| 模块 | 改动 | 验证 |
|------|------|------|
| `yweb/cache/api.py` | → `CacheController` + `CacheInvalidatorController`，保留 `create_cache_router()` | test_cache 全绿（113），测试零修改 |
| `yweb/scheduler/api/`（job/stats/execution） | → `JobController` / `StatsController` / `ExecutionController`，保留 `create_*_router` / `setup_scheduler_api` | test_scheduler 全绿，测试零修改 |
| `yweb/auth/api/user_api.py` | → `UserController`（`/reset-password` 用 `path=` 保留），保留 `create_user_router` | test_auth + test_controller 477 全绿 |
| `yweb/auth/api/login_record_api.py` | → `LoginRecordController`，保留 `create_login_record_router` | 同上 |

实现要点：DTO 从工厂闭包提到模块级；模型/依赖走模块级注入（`init_*_controller`）；`create_*_router` 改为薄装配（注入后 `include_router(XxxController.router)`）；方法保持同步 `def`（配合同步端点修复，DB 走线程池）。

---

## 2. 未改（保持函数式路由）及原因

| 模块 | 未改原因 | 难点根因 | 难度 |
|------|---------|---------|------|
| **rbac**（permission/role/subject/api_resource/cache 共 5 工厂） | 与 organization 同源冲突，且 **API 层零测试**（仅 service/model/types/decorators/cache/exceptions 有测试） | 运行时多模型注入（`create_rbac_models` 用 uuid 动态生成、闭包捕获、支持多套并存）+ `api_resource_model` 可选条件挂载 | 高 |
| **auth/auth_api.py** | 运行时按开关裁剪端点 | `enable_oauth2_token / json_login / refresh / logout / kick` **运行时条件注册**；外加闭包 DTO、`auth_service/jwt_manager/...` 运行时定制注入 | 高 |
| **auth/oauth2_api.py、oidc_api.py** | 标准协议端点 | OAuth2 / OIDC 固定路径（`/token`、`/authorize`、`/.well-known/...`），不能改名/改形 | 不适用 |
| **organization**（org/dept/employee） | 三重冲突叠加，全模块最重 | ① 运行时条件注册：`if employee_model and emp_dept_rel_model` 决定 `/employees`，`if dept_leader_model and ...` 决定 `/add-leader`、`/remove-leader` ② 6 模型 + 多套并存 ③ 自定义回调（`tree_node_builder` / `employee_response_builder` / 可选 `org_service`）+ 闭包递归 helper | 最高 |

> 这三类的共性正是判据里的「运行时条件注册 / 多模型并存 / 定制回调」，与「import 时定死路由」的类视图模型直接冲突。

---

## 3. 如果硬改：影响、范围、难度

### 方案 A：砍掉条件注册 / 多模型能力，改用全量注册 + 模块级注入
- **影响**：破坏性变更——项目无法再关闭 `/kick`、无法多套 RBAC/组织模型并存、自定义回调路径受限。
- **范围**：rbac 5 文件 + auth_api + organization 3 文件；其中 rbac **无测试网**，风险最高；organization/auth 有测试且多处断言「缺模型时路由不存在」，会直接失败。
- **难度**：中（改代码）+ 高（风险，尤其 rbac）。

### 方案 B：增强 ResourceController 支持「运行时动态建路由」（如 `build(enabled=..., models=...)`）
- **影响**：改动框架核心模型（从「类即路由单例」变「按参数生成路由实例」），波及**所有已迁模块**（cache/scheduler/auth/acl…）。
- **范围**：`controller/base.py` + `scanner.py` + 全部现有控制器 + 全套控制器测试都需回归。
- **难度**：高（架构级），收益主要是让这 3 个「重」模块也能用类视图，性价比存疑。

### 方案 C（推荐，已采纳）：保持函数式路由
- **影响**：零。这三类本就属于「特殊 / 可配置 / 多模型」端点，函数式路由是更合适的归属（与 `15_controller_guide.md` 选用建议一致）。
- **范围 / 难度**：无。

---

## 4. 难易梯度

```
易 ──────────────────────────────────────────────── 难
cache < scheduler < auth(user/login_record) < auth_api ≈ rbac < organization
   ↑————————— 已迁移 —————————↑      ↑————— 保持函数式路由 —————↑
```

---

## 5. 相关文档

- `15_controller_guide.md` —— ResourceController 用法（已含 `@post/@route`、`response_model/status_code/dependencies`、`path=`、选用建议）。
- `webapi_development_standards/api_layer_design_guide.md` —— 瘦 API 原则与类视图/函数式选用。
- `scheduler_design.md` —— 调度器管理 API（已对齐动词风格真实端点）。
