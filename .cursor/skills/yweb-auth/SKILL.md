---
name: yweb-auth
description: YWeb 认证授权与权限管理规范。在实现用户登录、JWT Token 处理、权限校验、角色管理、组织架构、OAuth 集成等功能时使用。
---

# YWeb 认证授权与权限管理规范

## 核心要点

YWeb 提供完整的认证授权体系：

- **双 Token 机制**：Access Token（短期）+ Refresh Token（长期）
- **认证服务基类**：继承 `BaseAuthService` 实现自定义认证
- **一站式认证设置**：`setup_auth()` 快速启用
- **RBAC 权限框架**：基于角色的访问控制，支持树形角色继承
- **缓存优化**：认证结果使用 `@cached` 缓存，减少数据库查询
- **组织架构管理**：`setup_organization()` 快速启用组织管理功能

## 关键编码规范

1. **认证依赖注入**：使用 `get_current_user` 作为 FastAPI 依赖
2. **权限检查**：使用权限装饰器或依赖注入，不在 API 层手动检查
3. **Token 处理**：后端使用 `jwt_manager`，前端实现自动刷新机制
4. **用户模型**：认证相关模型遵循框架约定（RoleMixin 等）

## 详细规范文档

| 主题 | 文档路径 |
|------|---------|
| 认证模块完整指南 | `yweb-core/docs/06_auth_guide.md` |
| 认证流程详解（含缓存优化） | `yweb-core/docs/webapi_development_standards/auth_flow_guide.md` |
| JWT Token 前后端规范 | `yweb-core/docs/webapi_development_standards/jwt_auth_guide.md` |
| 权限管理模块（RBAC） | `yweb-core/docs/08_permission_guide.md` |
| 组织架构管理 | `yweb-core/docs/07_organization_guide.md` |

## 工作流程

1. 初次接入认证功能，阅读 `06_auth_guide.md` 了解支持的认证方式
2. 实现 JWT 相关逻辑前，阅读 `jwt_auth_guide.md` 了解双 Token 机制
3. 理解认证流程和缓存策略，阅读 `auth_flow_guide.md`
4. 实现权限控制前，阅读 `08_permission_guide.md`
5. 涉及组织架构管理时，阅读 `07_organization_guide.md`
