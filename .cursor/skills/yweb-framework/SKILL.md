---
name: yweb-framework
description: YWeb 框架编码总规范。基于 FastAPI + SQLAlchemy 的 Web 框架，采用 Active Record + DDD 分层架构。在编写任何基于 yweb 框架的代码时使用此技能，包括 API 开发、ORM 操作、认证授权、缓存、异常处理等场景。
---

# YWeb 框架编码规范（主索引）

本技能是 YWeb 框架所有编码规范的**总入口**。具体规范细节请查阅对应文档，不要凭猜测编码。

> **重要原则**：所有编码规范的详细要求均以 `yweb-core/docs/` 下的文档为准。遇到不确定的用法时，必须先阅读对应文档再编码。

## 框架概述

YWeb 是基于 **FastAPI + SQLAlchemy** 的 Python Web 框架，核心特点：

- **Active Record 模式**：领域模型继承 ORM 基类，直接具备数据访问能力
- **DDD 分层思想**：API 层 → Service 层 → Domain 层，职责清晰分离
- **富领域模型**：模型不仅包含数据，还封装业务行为和验证逻辑
- **不引入 Repository 层**：保持简单，避免过度设计

## 核心原则速查

1. **瘦 API 原则**：API 层只做参数验证、DTO 转换、异常捕获、调用服务层
2. **业务逻辑归属**：单聚合内的业务规则 → 领域模型方法；跨聚合操作 → Service 层
3. **异常处理**：使用 `ValueError` 表达业务规则违反，不定义自定义异常类
4. **Model 字段**：所有字段必须有 `comment` 参数
5. **响应格式**：使用 `Resp.OK()` / `Resp.NotFound()` 等统一响应；响应模型使用 `DTO` 类
6. **请求模型**：使用 Pydantic `BaseModel`（不是 DTO）
7. **缓存**：使用 `@cached` 装饰器，注意 TTL 设置和失效策略
8. **事务管理**：Service 层负责事务边界，使用 `@transactional` 装饰器

## 规范文档索引

### 架构与项目设计

| 主题 | 文档路径 | 说明 |
|------|---------|------|
| DDD 分层架构 | `yweb-core/docs/webapi_development_standards/ddd-layered-architecture-guide.md` | 分层架构、各层职责、服务层拆分原则 |
| API 层设计 | `yweb-core/docs/webapi_development_standards/api_layer_design_guide.md` | 瘦 API 原则、Schema 设计、响应返回规范 |
| Model 与 Service 设计 | `yweb-core/docs/webapi_development_standards/model_and_service_design_guide.md` | Model 字段规范、Service 层设计规范 |
| DTO 与响应处理 | `yweb-core/docs/webapi_development_standards/dto_response_guide.md` | DTO 基础、字段映射、响应格式规范 |
| API 与 Service 开发规范 | `yweb-core/docs/webapi_development_standards/development_guide.md` | 项目结构、导入规范、完整开发示例 |

### ORM 与数据层

| 主题 | 文档路径 | 说明 |
|------|---------|------|
| ORM 基础指南 | `yweb-core/docs/03_orm_guide.md` | 数据库初始化、模型定义、CRUD、分页、软删除 |
| ORM 详细功能文档 | `yweb-core/docs/orm_docs/README.md` | 完整 ORM 功能索引（20+ 篇详细文档） |
| ORM 事务提交行为 | `yweb-core/docs/orm_commit_behavior_outside_transaction.md` | 事务外提交行为说明 |
| ORM 提交抑制机制 | `yweb-core/docs/orm_commit_suppression_mechanism.md` | 提交抑制机制说明 |

### 认证与权限

| 主题 | 文档路径 | 说明 |
|------|---------|------|
| 认证模块指南 | `yweb-core/docs/06_auth_guide.md` | JWT、Session、OAuth、API Key 等认证方式 |
| 认证流程详解 | `yweb-core/docs/webapi_development_standards/auth_flow_guide.md` | JWT 认证流程、缓存优化、自动失效 |
| JWT Token 规范 | `yweb-core/docs/webapi_development_standards/jwt_auth_guide.md` | 双 Token 机制、前后端规范 |
| 权限管理 | `yweb-core/docs/08_permission_guide.md` | RBAC 框架、角色/权限管理 |
| 组织管理 | `yweb-core/docs/07_organization_guide.md` | 组织架构管理模块 |

### 基础设施

| 主题 | 文档路径 | 说明 |
|------|---------|------|
| 缓存 | `yweb-core/docs/11_cache_guide.md` | `@cached` 装饰器、缓存后端、失效策略 |
| 异常处理 | `yweb-core/docs/05_exception_handling.md` | 全局异常处理器、Err 快捷类、验证约束 |
| 配置管理 | `yweb-core/docs/02_config_guide.md` | YAML + 环境变量配置、AppSettings |
| 日志 | `yweb-core/docs/04_log_guide.md` | get_logger、日志轮转、敏感数据过滤 |
| 文件存储 | `yweb-core/docs/10_storage_guide.md` | 本地/OSS/S3 存储、文件验证 |
| 定时任务 | `yweb-core/docs/09_scheduler_guide.md` | APScheduler 封装、Builder 模式、持久化 |
| 快速开始 | `yweb-core/docs/01_quickstart.md` | 框架安装与基础示例 |

## 使用指南

当需要编写或修改 yweb 相关代码时：

1. **先确定涉及的领域**（架构设计 / ORM / 认证 / 基础设施）
2. **阅读对应的规范文档**，了解框架要求的编码方式
3. **严格按照文档中的规范编码**，不要使用文档未提及的模式
4. 如果涉及 ORM 高级功能（如树形结构、状态机、排序混入等），查阅 `yweb-core/docs/orm_docs/` 下的专题文档
