---
name: yweb-infra
description: YWeb 基础设施模块规范。在使用缓存（@cached）、异常处理（Err/register_exception_handlers）、日志（get_logger）、配置（AppSettings/YAML）、文件存储（本地/OSS/S3）、定时任务（Scheduler）、限流（setup_ratelimit）时使用。
---

# YWeb 基础设施模块规范

## 缓存

- 使用 `@cached(ttl=秒数)` 装饰器缓存函数返回值
- **缓存 ORM 对象**：使用 `@cached(ttl=60, orm_model=Model)` 自动将 detached 对象 merge 回当前 Session（`load=False`，零查询）
- **缓存键前缀**：默认自动使用 `module.qualname` 全限定名，避免同名函数在 Redis 后端下的键冲突；也可手动指定 `key_prefix="xxx"`
- **自动缓存失效（双路径）**：`cache_invalidator.register(Model, func)` 监听 ORM `after_update`/`after_delete` 事件
  - **路径 1 — key_extractor**：实体变更时用 `key_extractor(entity)` 精确失效，适合 `get_user(user_id)` 等单实体查询
  - **路径 2 — 依赖追踪**：缓存写入时自动扫描结果中的实体建立反向索引，实体变更时按索引精确失效，适合列表/组合查询
- **M2M 关系变更失效**：`watch_relationships` 参数默认 `True`，自动监听 ManyToMany 集合的 `append`/`remove` 事件触发失效
- 支持 Memory 和 Redis 两种后端
- 详细规范：**`yweb-core/docs/11_cache_guide.md`**

## 异常处理

- 使用 `register_exception_handlers(app)` 注册全局异常处理器
- 推荐使用 `Err` 快捷类抛出业务异常
- 业务规则违反使用标准 `ValueError`，不定义自定义异常类
- 支持验证约束模块（类似 .NET MVC 特性）
- 详细规范：**`yweb-core/docs/05_exception_handling.md`**

## 日志

- 使用 `get_logger()` 获取日志记录器（自动推断模块名）
- 支持时间+大小双重轮转
- 支持敏感数据过滤
- 详细规范：**`yweb-core/docs/04_log_guide.md`**

## 配置管理

- 使用 `AppSettings` 基础配置类
- 支持 YAML 文件 + 环境变量混合配置
- 使用配置加载器和配置管理器
- 详细规范：**`yweb-core/docs/02_config_guide.md`**

## 文件存储

- 支持本地存储、阿里云 OSS、AWS S3 / MinIO
- 支持文件验证
- 详细规范：**`yweb-core/docs/10_storage_guide.md`**

## 定时任务

- 基于 APScheduler 封装
- 支持 Builder 模式链式配置
- 支持失败重试、HTTP 任务、持久化
- 详细规范：**`yweb-core/docs/09_scheduler_guide.md`**

## 限流

- 基于 slowapi 轻度封装，使用 `setup_ratelimit(app)` 一站式初始化
- 路由中使用 slowapi 原生 `@limiter.limit("10/minute")` 装饰器
- 默认按 JWT user_id 限流，匿名时按 IP 限流（`get_user_or_ip`）
- 超限返回 yweb 统一 429 格式（`Resp.TooManyRequests()`）
- 支持事件订阅：`rate_limit_event_bus.subscribe(callback)` 可将限流事件记录到数据库
- 配置集成：`AppSettings.ratelimit`（`RateLimitSettings`），环境变量前缀 `YWEB_RL_`
- 支持 Memory 和 Redis 两种存储后端
- 可选依赖：`pip install yweb[ratelimit]`
- 详细规范：**`yweb-core/docs/14_ratelimit_guide.md`**

## 快速开始

- 框架安装与基础示例：**`yweb-core/docs/01_quickstart.md`**

## 工作流程

1. 使用任何基础设施模块前，**先阅读对应文档**
2. 缓存使用：阅读 `11_cache_guide.md`，重点关注 TTL 设置和失效策略
3. 异常处理：阅读 `05_exception_handling.md`，了解 Err 快捷类和验证约束
4. 日志使用：阅读 `04_log_guide.md`，使用 `get_logger()` 而非 `logging.getLogger()`
5. 配置相关：阅读 `02_config_guide.md`，了解 YAML + 环境变量的优先级
6. 限流使用：阅读 `14_ratelimit_guide.md`，了解 setup_ratelimit 初始化和事件订阅
