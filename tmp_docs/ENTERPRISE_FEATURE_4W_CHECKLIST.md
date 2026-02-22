# YWeb 企业能力 4 周实施清单（MVP）

> 目标：在不破坏“极简 API + 开箱即用”理念下，优先补齐企业落地最关键能力。  
> 范围：`throttle`、`audit`、`metrics/tracing`、`multitenant(v1)`。

## 实施原则

- [ ] 一行启用：每个模块都提供默认配置和快速接入函数
- [ ] 默认安全：默认值可直接用于生产基础场景
- [ ] 可观测：关键路径必须有日志、指标、错误信息
- [ ] 可回退：新能力可通过配置关闭，不影响历史项目
- [ ] 先 MVP 再增强：先做 80% 通用场景，复杂能力后置

## 扩展机制改造清单（插件注册 + 生命周期钩子 + 配置驱动启停）

> 目标：保留当前“工厂函数 + 一站式 setup”体验，同时给使用者稳定扩展点。  
> 设计建议：先统一“轻量事件总线 + 钩子协议”，再逐模块接入。

### A) 先新增的核心扩展底座（建议第 0 周并行）

- [ ] 新建 `yweb/extensions/registry.py`（插件注册中心）
- [ ] 新建 `yweb/extensions/hooks.py`（统一生命周期事件定义）
- [ ] 新建 `yweb/extensions/plugin.py`（`YWebPlugin` 协议/基类）
- [ ] 新建 `yweb/extensions/bootstrap.py`（从配置加载并启停插件）
- [ ] 在 `yweb/__init__.py` 导出 `setup_extensions()` 与核心类型

### B) 配置驱动启停（建议改 `yweb/config/settings.py`）

- [ ] 新增 `ExtensionsSettings`（全局开关、插件列表、每插件配置）
- [ ] 在 `AppSettings` 增加 `extensions` 段（默认关闭或最小开启）
- [ ] 支持按插件配置：`enabled`、`order`、`module`、`config`
- [ ] 支持按模块总开关：`throttle` / `audit` / `observability` / `multitenant`

### C) 优先改造模块（按价值排序）

#### 1) 调度器（`yweb/scheduler/scheduler.py`）—— 最容易先打样
- [ ] 复用现有 `on_job_executed/on_job_error/on_job_retry/on_job_missed`，统一接入插件事件总线
- [ ] 新增生命周期钩子：`before_scheduler_start`、`after_scheduler_start`、`before_scheduler_shutdown`
- [ ] 允许插件拦截任务执行上下文（只读）并附加元数据（如租户、trace）

#### 2) 认证模块（`yweb/auth/setup.py`、`yweb/auth/service.py`）—— 业务扩展高频
- [ ] 增加钩子：`before_authenticate`、`after_authenticate`、`on_login_success`、`on_login_failed`、`on_token_issued`
- [ ] 在 `setup_auth()` / `mount_routes()` 中注入插件上下文
- [ ] 支持插件做二次风控（IP、设备、地理位置）和自定义 claim 注入

#### 3) 权限模块（`yweb/permission/factory.py`、`yweb/permission/dependencies.py`）
- [ ] 增加钩子：`before_permission_check`、`after_permission_check`、`on_role_changed`
- [ ] 支持插件扩展 Subject 解析与权限决策（ABAC/策略中心）
- [ ] 缓存失效时触发权限变更事件，供审计和同步系统消费

#### 4) 组织模块（`yweb/organization/factory.py`、`yweb/organization/services/*.py`）
- [ ] 将现有 `*_customizer` 能力标准化为生命周期事件（模型创建前/后、关系绑定前/后）
- [ ] 增加事件：`on_employee_created/updated/status_changed`
- [ ] 对外提供观察者接口，方便同步到第三方系统（企微/飞书/钉钉）

#### 5) 缓存模块（`yweb/cache/invalidation.py`）—— 事件化失效
- [ ] 失效动作发布标准事件：`cache_invalidated`
- [ ] 支持插件订阅失效事件做二级处理（预热、联动删除、统计）
- [ ] 增加可选的 tag 事件，为后续标签失效做铺垫

#### 6) 日志模块（`yweb/log/filter_hooks.py`）—— 已有钩子，建议并轨
- [ ] 保留 `LogFilterHookManager`，并作为扩展系统内置插件之一
- [ ] 增加阶段钩子：`before_log_write`、`after_log_write`
- [ ] 允许插件按路由/租户/用户动态添加脱敏规则

#### 7) 中间件与异常（`yweb/middleware/*.py`、`yweb/exceptions/handlers.py`）
- [ ] 增加请求生命周期钩子：`before_request`、`after_request`、`on_request_error`
- [ ] 异常处理增加 `on_exception_handled` 钩子，支持统一告警与审计
- [ ] 为审计和 tracing 插件预留上下文透传字段

### D) 插件接口最小规范（MVP）

- [ ] 统一插件基类接口：`setup(app, settings)`、`start()`、`stop()`
- [ ] 统一事件订阅接口：`subscribe(event_name, handler)`
- [ ] 插件执行顺序支持 `order`（数字越小越先执行）
- [ ] 插件异常隔离：单插件失败不影响主流程（可配置 fail_fast）

### E) 验收标准（扩展机制）

- [ ] 不改业务代码，仅通过配置即可启用/停用插件
- [ ] 现有 `setup_auth/setup_permission/setup_organization/setup_scheduler` 向后兼容
- [ ] 至少 3 个内置插件接入（建议：审计、指标、限流）
- [ ] 插件崩溃时主链路可继续，并有明确日志定位

---

## 第 1 周：通用限流（`yweb/throttle`）

### 1) 模块与接口
- [ ] 新建 `yweb/throttle/rates.py`（令牌桶或滑动窗口实现）
- [ ] 新建 `yweb/throttle/storage.py`（内存 + Redis 后端）
- [ ] 新建 `yweb/throttle/middleware.py`（全局限流中间件）
- [ ] 新建 `yweb/throttle/decorators.py`（`@RateLimit(...)`）
- [ ] 在 `yweb/throttle/__init__.py` 导出核心 API

### 2) 默认行为（开箱即用）
- [ ] 默认 key：优先用户 ID，回退客户端 IP
- [ ] 默认限额：如 `60/minute`（可配置）
- [ ] 触发限流时返回统一错误码和 `Retry-After` 响应头

### 3) 验收标准
- [ ] 同一用户超过阈值可稳定触发 429
- [ ] 多实例部署下 Redis 限流结果一致
- [ ] 文档包含 1 行启用示例与常见配置示例

---

## 第 2 周：操作审计（`yweb/audit`）

### 1) 模块与接口
- [ ] 新建 `yweb/audit/models.py`（`AuditLog`）
- [ ] 新建 `yweb/audit/decorators.py`（`@audit_log(...)`）
- [ ] 新建 `yweb/audit/middleware.py`（请求审计上下文）
- [ ] 新建 `yweb/audit/service.py`（记录写入与查询）
- [ ] 在 `yweb/audit/__init__.py` 导出核心 API

### 2) 审计字段（MVP）
- [ ] 操作者（user_id / subject）
- [ ] 动作（action）
- [ ] 目标对象（resource_type / resource_id）
- [ ] 请求上下文（request_id、IP、UA）
- [ ] 变更摘要（before/after 可选）
- [ ] 时间戳、结果状态（success/failed）

### 3) 验收标准
- [ ] 关键操作（删除、授权、配置修改）可自动留痕
- [ ] 审计查询支持按时间、操作者、动作过滤
- [ ] 异常流程也会落审计日志

---

## 第 3 周：统一可观测性（`yweb/observability`）

### 1) 模块与接口
- [ ] 新建 `yweb/observability/metrics.py`（HTTP 指标采集）
- [ ] 新建 `yweb/observability/tracing.py`（OpenTelemetry 集成）
- [ ] 新建 `yweb/observability/middleware.py`（请求级注入）
- [ ] 暴露 `/metrics`（Prometheus）

### 2) 指标最小集（MVP）
- [ ] 请求总数（按路由、状态码）
- [ ] 请求时延（P50/P95/P99）
- [ ] 异常总数
- [ ] DB 慢查询计数（阈值可配）

### 3) 链路追踪（MVP）
- [ ] 自动生成/透传 trace_id、span_id
- [ ] 与 request_id 关联，日志可检索
- [ ] 支持 Jaeger/OTLP exporter 基础配置

### 4) 验收标准
- [ ] 单请求可串联日志、trace、指标
- [ ] 压测下指标采集开销可控
- [ ] 默认关闭 tracing exporter 时不影响主流程

---

## 第 4 周：多租户 v1（`yweb/multitenant`）

### 1) 模块与接口
- [ ] 新建 `yweb/multitenant/context.py`（`current_tenant`）
- [ ] 新建 `yweb/multitenant/middleware.py`（域名/请求头识别租户）
- [ ] 新建 `yweb/multitenant/models.py`（`TenantModel` 基类）
- [ ] 新建 `yweb/multitenant/isolation.py`（隔离策略枚举，先支持共享库）
- [ ] 新建 `yweb/multitenant/manager.py`（租户解析与校验）
- [ ] 在 `yweb/multitenant/__init__.py` 导出核心 API

### 2) v1 范围（明确边界）
- [ ] 仅支持“共享库 + tenant_id 列”模式
- [ ] `TenantModel` 自动注入 `tenant_id`
- [ ] 查询默认按当前租户过滤（可显式禁用）
- [ ] 后台任务支持手动传入租户上下文

### 3) 验收标准
- [ ] 未识别租户时按配置拒绝请求或回退默认租户
- [ ] 跨租户数据不可见（含分页与关联查询）
- [ ] 管理端可显式切换“忽略租户过滤”用于运维场景

---

## 横向任务（每周都要做）

- [ ] 单元测试：核心分支、边界条件、异常路径
- [ ] 集成测试：中间件 + ORM + 认证组合场景
- [ ] 文档补齐：快速开始、配置项、错误码、最佳实践
- [ ] 示例工程：每个模块至少 1 个最小可运行示例
- [ ] 向后兼容：老项目升级无破坏（提供迁移说明）

---

## 发布门禁（Go/No-Go）

- [ ] 测试通过率 100%，关键模块覆盖率达标
- [ ] 压测无明显回归（吞吐/时延）
- [ ] 新增配置项均有默认值和文档
- [ ] 关键错误有可定位日志（含 request_id/trace_id）
- [ ] 发布说明包含升级步骤与回滚方案

---

## 下一阶段（4 周后）

- [ ] `throttle`：补齐配额管理（按租户/套餐）
- [ ] `audit`：补齐合规导出与保留策略
- [ ] `observability`：补齐 dashboard 与告警模板
- [ ] `multitenant`：评估独立 schema / 独立库演进路径

