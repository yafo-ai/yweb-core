---
name: yweb-ddd-architecture
description: YWeb DDD 分层架构与 API 设计规范。在创建或修改 API 路由、Service 层、领域模型、DTO 时使用。涵盖瘦 API 原则、服务层拆分、Model 设计、DTO 转换、响应格式等。
---

# YWeb DDD 分层架构与 API 设计规范

## 核心架构要点

YWeb 采用 **Active Record + DDD 分层思想**，三层架构：

```
API 层 (路由) → Service 层 (业务编排) → Domain 层 (领域模型)
```

**关键原则**：
- 不引入 Repository 层，领域模型直接继承 ORM 基类
- API 层保持"瘦"，只做参数验证、DTO 转换、异常捕获、调用 Service
- 业务规则封装在领域模型的 `validate_xxx()` 方法中
- 跨聚合操作通过 Service 层协调
- 简单的纯查询（无业务逻辑）可由 API 层直接调用领域模型

## 各层职责速查

| 层 | 职责 | 禁止 |
|----|------|------|
| API 层 | 参数验证、DTO 转换、异常→HTTP 响应、调用 Service | 业务逻辑、事务管理、数据库操作 |
| Service 层 | 跨聚合协调、事务管理、权限检查 | HTTP 感知、直接返回 Response |
| Domain 层 | 单聚合业务规则、数据验证、状态变更 | 调用其他聚合、HTTP 感知 |

## DTO 使用要点

- **响应模型**：继承 `DTO`（来自 `yweb`），使用 `from_entity()` / `from_page()` 转换
- **请求模型**：使用 Pydantic `BaseModel`
- DTO 继承自 Pydantic BaseModel，**不要**对 DTO 使用 `@dataclass` 装饰器
- 使用 `_field_mapping` 进行字段映射，使用 `_value_processors` 进行值处理（字段类型应与处理器转换后的类型一致）

## 响应格式要点

- 统一使用 `Resp.OK()` / `Resp.Fail()` / `Resp.NotFound()` 等
- 分页响应使用 `PageResponse`
- 异常统一捕获 `ValueError`，转为 `Resp.Fail()`

## 详细规范文档

编码前**必须阅读**对应文档以获取完整规范和示例：

| 主题 | 文档路径 |
|------|---------|
| DDD 分层架构全貌 | `yweb-core/docs/webapi_development_standards/ddd-layered-architecture-guide.md` |
| API 层设计规范（瘦 API 原则） | `yweb-core/docs/webapi_development_standards/api_layer_design_guide.md` |
| Model 与 Service 层设计规范 | `yweb-core/docs/webapi_development_standards/model_and_service_design_guide.md` |
| DTO 与响应处理规范 | `yweb-core/docs/webapi_development_standards/dto_response_guide.md` |
| API 与 Service 开发综合规范 | `yweb-core/docs/webapi_development_standards/development_guide.md` |

## 工作流程

1. 新建功能时，先阅读 `ddd-layered-architecture-guide.md` 确定分层
2. 编写 API 路由前，阅读 `api_layer_design_guide.md`
3. 编写 Model / Service 前，阅读 `model_and_service_design_guide.md`
4. 定义 DTO 和响应格式前，阅读 `dto_response_guide.md`
5. 综合参考 `development_guide.md` 中的完整示例
