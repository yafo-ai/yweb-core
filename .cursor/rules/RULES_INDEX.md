# Cursor Rules Index

本文件用于快速索引项目内的 Cursor 规则。  
规则文件位于 `.cursor/rules/`，按“全局通用 / 后端 / 前端 / 环境”分类。

## 全局通用

- `file-modification-policy.mdc`
  - 修改文件前先确认用户意图；若用户要求“先分析”，只分析不改代码。
- `terminal-emoji.mdc`
  - 终端 emoji 显示异常可忽略，不要为此做修复。
- `powershell-environment.mdc`
  - PowerShell 环境下命令串联使用 `;`，不要使用 `&&`。

## 后端（YWeb / Python）

- `yweb-framework.mdc`
  - yweb 框架总规范入口；提供 DDD、异常、事务、响应等总览。
- `yweb-ddd-architecture.mdc`
  - DDD 分层职责边界（API/Service/Domain）；瘦 API 原则。
- `yweb-orm.mdc`
  - ORM 模型定义、字段 comment、SQLAlchemy 2.0 风格、事务边界。
- `yweb-auth.mdc`
  - 认证授权、权限管理相关规范。
- `yweb-infra.mdc`
  - 基础设施（缓存、异常、日志、配置、存储、定时任务）规范。
- `yweb-testing.mdc`
  - 测试编写与组织规范。
- `yweb-webapi-response.mdc`（新增）
  - WebAPI 响应规范：必须声明 `response_model`，DTO/Resp 统一写法，避免 `/docs` 出现 `string`。

## 前端（Vue / API 封装）

- `frontend-api-conventions.mdc`（新增）
  - `frontend/src/api` 下 API 封装规范：参数放 `params`、命名统一、调用风格统一、只做请求封装。

## 测试命名专项

- `how-to-add-pytest-class-unit-test.mdc`
  - pytest 中非测试辅助类不能以 `Test` 开头，避免被误识别。

## 推荐使用顺序

1. 先看 `yweb-framework.mdc`（总览）
2. 再按改动类型进入专项规则：
   - API 路由：`yweb-ddd-architecture.mdc` + `yweb-webapi-response.mdc`
   - ORM 模型：`yweb-orm.mdc`
   - 前端 API：`frontend-api-conventions.mdc`
3. 涉及测试时补看 `yweb-testing.mdc` 与 pytest 命名规则。

## 维护约定

- 新增规则时，请同步更新本索引。
- 若规则有交叉，专项规则优先于总览规则。
