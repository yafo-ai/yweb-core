# ResourceController 路由迁移评估与结论

> 记录将 yweb-core 各模块 API 从「函数式路由工厂」迁移到 `ResourceController` 类视图的范围、决策、难点与影响评估，供后续模块开发/迁移直接对照。
>
> 最后更新：2026-06-05

---

## 0. 背景

目标 API 风格：**资源树 + 自定义动作**（`模块/api/类名/方法名`，只用 GET/POST，方法名自定义）。
落地手段：`ResourceController` 类视图（方法名即路由路径，默认 POST，`@get` 标 GET）。

核心约束（决定一个模块能否干净迁移）：

> `ResourceController` 的 `router` 在**类定义 / import 时**由 `__init_subclass__ → _register_actions()` **一次性构建**。
> 因此「哪些端点存在」必须在 import 时就确定。
> 对于「端点集合固定，但 model/service/scheduler 需要在工厂调用时传入」的场景，已通过 `ResourceController.create_router(**attrs)` 生成独立 router 解决。
> 对于「运行时决定是否注册某些端点」的场景，仍然与当前类视图模型冲突，应保持函数式路由。

**选用判据**：

- ✅ 适合直接类视图：**无条件全量注册** + **无运行时依赖** + 方法名能映射路径。
- ✅ 适合类视图工厂：**无条件全量注册** + **运行时绑定固定依赖**（model/service/scheduler）+ 方法名能映射路径。
- ❌ 不适合类视图（保持函数式路由）：**运行时条件注册** / **大量运行时定制回调** / **协议路径必须严格保持原形**。

---

## 1. 已改（迁移为 ResourceController）

### 1.1 ResourceController 框架增强（基础设施）

| 文件 | 改动 |
|------|------|
| `yweb/controller/decorators.py` | `@get/@post` 支持裸用 + 带参；新增 `@route`；支持 `response_model / status_code / dependencies / summary` 等元数据；新增 `path=` 路径覆盖 |
| `yweb/controller/base.py` | 读取并应用上述元数据；**同步方法生成同步端点**（FastAPI 自动放线程池，修复同步 ORM 在事件循环触发 async-safety 的问题）；支持 `path=` 覆盖默认 `/方法名`；新增 `create_router(**attrs)` 用于绑定运行时依赖并生成独立 router |

> `path=` 的引入是为了表达方法名无法表达的路径（如连字符 `/reset-password`）。

### 1.2 业务模块迁移（均为**路径不变 + 工厂签名不变**，对外零行为变化）

| 模块 | 改动 | 验证 |
|------|------|------|
| `yweb/cache/api.py` | → `CacheController` + `CacheInvalidatorController`，保留 `create_cache_router()` | test_cache 全绿（113），测试零修改 |
| `yweb/scheduler/api/`（job/stats/execution） | → `JobController` / `StatsController` / `ExecutionController`，保留 `create_*_router` / `setup_scheduler_api` | test_scheduler 全绿，测试零修改 |
| `yweb/auth/api/user_api.py` | → `UserController`（`/reset-password` 用 `path=` 保留），保留 `create_user_router` | test_auth + test_controller 477 全绿 |
| `yweb/auth/api/login_record_api.py` | → `LoginRecordController`，保留 `create_login_record_router` | 同上 |
| `yweb/acl/api/`（rules/resources/permission） | → `AclRuleController` / `AclResourceController` / `AclPermissionController`，保留 `create_acl_router` 并新增子路由工厂 | test_acl + test_controller 全绿 |

实现要点：DTO 从工厂闭包提到模块级；运行时模型/依赖通过 `ResourceController.create_router(...)` 绑定到独立 router，避免模块级注入状态；方法保持同步 `def`（配合同步端点修复，DB 走线程池）。

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

### 方案 B：轻量增强 ResourceController 支持「运行时依赖绑定」（已采纳）
- **影响**：不改变「哪些端点存在由类定义决定」的核心模型，只新增 `Controller.create_router(**attrs)`，为每次工厂调用生成独立 router。
- **范围**：`controller/base.py` + controller 隔离性测试；auth / scheduler / acl 已按该模式落地。
- **难度**：低到中。适合解决「路由集合固定，但依赖需要在工厂调用时传入」的问题。
- **限制**：不能解决「运行时条件注册端点」，例如缺模型时端点根本不存在、按配置开关裁剪 OAuth2/auth 端点等。

### 方案 C（推荐，已采纳）：复杂动态模块保持函数式路由
- **影响**：零。这三类本就属于「特殊 / 可配置 / 多模型」端点，函数式路由是更合适的归属（与 `15_controller_guide.md` 选用建议一致）。
- **范围 / 难度**：无。

---

## 3.1 未来可选增强：Blueprint + `build(deps)`（动态构建）

本节是后续如果确实要把 organization / rbac / auth_api 这类「运行时条件注册」模块也迁入类视图时的可选设计，不属于当前已采纳规范。

这类模块的三个障碍是同一根因的三种表现：

> `__init_subclass__` 在 **import 时**就把 `cls.router` 一次性建好（`base.py`），导致「注册哪些方法、绑定哪套模型/回调」都必须在 import 时定死。

解法：把 **「路由声明（import 时）」与「路由绑定（调用时）」分离**，router 改为按调用参数动态构建。把 `ResourceController` 从「类 = 单例 router」升级为「类 = 路由蓝图，`build(deps)` = 生成一个绑定了依赖的 router 实例」。

### 三个机制 ↔ 三个障碍

**① 条件注册 → 装饰器加 `when=` 谓词（build 时对 deps 求值）**

```python
class DepartmentController(ResourceController):
    prefix = "/dept"

    @get  # 无条件，恒注册
    def list(self, org_id: int = Query(...)):
        return Resp.OK(self.deps.dept_model.query...)

    @get(when=lambda d: d.employee_model and d.emp_dept_rel_model)
    def employees(self, dept_id: int = Query(...)):
        ...

    @post(when=lambda d: d.dept_leader_model and d.employee_model and d.emp_dept_rel_model)
    def add_leader(self, data: DeptLeaderCreate):
        ...
```

`build(deps)` 时对每个方法的 `when(deps)` 求值，False 就不注册 → 完整复刻「缺模型 → 404」契约（现有测试不用改）。

**② 6 模型 + 多套并存 → `build(deps)` 每次返回独立 router，依赖随 deps 走，不用模块级全局**

```python
@dataclass
class OrgDeps:
    dept_model: type
    org_model: type
    employee_model: type | None = None
    emp_org_rel_model: type | None = None
    emp_dept_rel_model: type | None = None
    dept_leader_model: type | None = None
    org_service: Any = None
    tree_node_builder: Callable | None = None
    employee_response_builder: Callable | None = None
```

每次 `build(deps_A)` / `build(deps_B)` 各自闭包捕获自己的 `deps`，同进程多套模型互不干扰（这是 cache/scheduler 那种「模块级全局注入」做不到的）。

**③ 自定义回调 + 闭包 helper → 方法通过 `self.deps` 访问，helper 变私有实例方法**

```python
    def _build_tree(self, depts, parent_id=None, opts=None):   # _ 开头不注册为路由
        builder = self.deps.tree_node_builder
        ...
```

回调（`tree_node_builder` 等）、`org_service`、递归 helper 全部走 `self.deps`，不再依赖闭包捕获。

### 工厂层几乎不变（向后兼容）

```python
def create_department_crud_router(dept_model, org_model, employee_model=None, ...):
    deps = OrgDeps(dept_model=dept_model, org_model=org_model, employee_model=employee_model, ...)
    return DepartmentController.build(deps)
```

签名、路径、行为全不变，「缺模型返回 404」的断言照样通过。

### base.py 需要的改造（要点）

1. `__init_subclass__` 不再立即注册，而是把每个方法的 **route spec**（`http_method / path / route_kwargs / when`）收集到 `cls._route_specs`。
2. 新增 `classmethod build(cls, deps=None) -> APIRouter`：建新 `APIRouter`，遍历 specs，`when is None or when(deps)` 才注册；endpoint 闭包绑定 `deps`，每请求 `instance = cls(); instance.deps = deps`。
3. **向后兼容桥**：保留 `cls.router`（等价 `build(None)`），让 cache/scheduler/auth/acl 这些无 `when`、不用 `self.deps` 的控制器完全不受影响；`scan_controllers` 走 `cls.router` 也不变。
4. `decorators.py` 加 `when=` 参数（与 `path=` 同样单独存放，不混入 FastAPI 路由元数据）。

### 一并解决 rbac / auth_api

同一套机制天然覆盖另外两个「重」模块：

| 模块 | 现障碍 | 用该方案怎么解 |
|------|--------|---------------|
| organization | 条件注册 + 6 模型多套 + 回调 | `when` + `build(deps)` + `self.deps` |
| rbac | 多套动态模型 + `api_resource` 可选 | `build(deps)` + `when=lambda d: d.api_resource_model` |
| auth_api | `enable_oauth2_token / json_login / refresh / logout / kick` 开关 | `when=lambda d: d.enable_kick` 等 |

### 对 ResourceController 的影响评估

| 维度 | 评估 |
|------|------|
| 改动面 | 中等，集中在 `base.py`（注册逻辑由「立即」改「收集 spec + build 时注册」）+ `decorators.py`（加 `when=`） |
| 兼容面 | **可做到现有模块零感知**：① 不用 `when` → 谓词 None → 恒注册；② 不用 `self.deps` → 构造不变；③ 仍走 `cls.router = build(None)` → `include_router` / `scan_controllers` 照旧 |
| 主要风险 | 框架核心改动，必须靠全套 controller + 已迁模块测试回归全绿背书；`cls.router = build(None)` 兼容桥须保证 `deps=None` 下行为逐字节一致（路径/OpenAPI/依赖/同步异步端点） |
| 语义微调 | 实例新增 `self.deps`（构建期绑定），文档「无状态」表述需补充说明 |
| scan 限制 | 用 deps 的控制器不能走自动扫描（扫描不知道 deps），需经工厂手动挂载——org/rbac/auth 本来就是这样 |

### 推荐推进路径

1. **先做框架原型**：只动 `base.py` / `decorators.py` + 加针对性测试（`when` 跳过、多次 build 隔离、deps 绑定），保证现有控制器全绿（兼容桥成立）。
2. 原型通过后再迁 organization（含改写其测试为「恒定注册 / 动态依赖」语义），rbac / auth_api 视需要跟进。

这样框架增强与业务迁移解耦，风险可控、可随时回退。

---

## 4. 难易梯度

```
易 ──────────────────────────────────────────────── 难
cache < scheduler < acl < auth(user/login_record) < auth_api ≈ rbac < organization
   ↑————————————— 已迁移 —————————————↑      ↑————— 保持函数式路由 —————↑
```

---

## 5. 相关文档

- `15_controller_guide.md` —— ResourceController 用法（已含 `@post/@route`、`response_model/status_code/dependencies`、`path=`、`create_router(**attrs)`、选用建议）。
- `webapi_development_standards/api_layer_design_guide.md` —— 瘦 API 原则、运行时依赖绑定规范与类视图/函数式选用。
- `scheduler_design.md` —— 调度器管理 API（已对齐动词风格真实端点）。
