---
name: yweb-infra
description: YWeb 基础设施模块规范。在使用缓存（@cached）、异常处理（Err/register_exception_handlers）、日志（get_logger）、配置（AppSettings/YAML）、文件存储（本地/OSS/S3）、定时任务（Scheduler）时使用。
---

# YWeb 基础设施模块规范

## 缓存

- 使用 `@cached(ttl=秒数)` 装饰器缓存函数返回值
- 支持自动缓存失效和手动失效
- 认证场景中常用于缓存用户信息，减少数据库查询
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

## 快速开始

- 框架安装与基础示例：**`yweb-core/docs/01_quickstart.md`**

## 工作流程

1. 使用任何基础设施模块前，**先阅读对应文档**
2. 缓存使用：阅读 `11_cache_guide.md`，重点关注 TTL 设置和失效策略
3. 异常处理：阅读 `05_exception_handling.md`，了解 Err 快捷类和验证约束
4. 日志使用：阅读 `04_log_guide.md`，使用 `get_logger()` 而非 `logging.getLogger()`
5. 配置相关：阅读 `02_config_guide.md`，了解 YAML + 环境变量的优先级
