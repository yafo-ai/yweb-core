# YWeb 认证指南

本指南介绍 YWeb 提供的多种认证方式，帮助你快速为应用添加用户认证功能。

## 目录

- [认证方式概览](#认证方式概览)
- [一站式认证设置 setup_auth（推荐）](#一站式认证设置-setup_auth推荐)
- [BaseAuthService 认证服务](#baseauthservice-认证服务)
- [角色管理 AbstractSimpleRole + RoleMixin](#角色管理-abstractsimplerole--rolemixin)
- [输入验证器](#输入验证器)
- [JWT 认证](#jwt-认证)
- [Refresh Token 滑动过期](#refresh-token-滑动过期)
- [Token 撤销/黑名单](#token-撤销黑名单)
- [API Key 认证](#api-key-认证)
- [Session 认证](#session-认证)
- [OAuth 2.0](#oauth-20)
- [OpenID Connect (OIDC)](#openid-connect-oidc)
- [多因素认证 (MFA)](#多因素认证-mfa)
- [LDAP/AD 认证](#ldapad-认证)
- [登录审计](#登录审计)
- [登录防护策略](#登录防护策略)
- [用户安全 Mixins](#用户安全-mixins)
- [密码工具 PasswordHelper](#passwordhelper---密码工具类)
- [统一认证管理](#统一认证管理)

---

## 认证方式概览

| 认证方式 | 适用场景 | 特点 |
|---------|---------|------|
| JWT | API 认证、移动应用 | 无状态、可扩展 |
| API Key | 服务间调用、第三方集成 | 简单直接 |
| Session | 传统 Web 应用 | 服务端状态管理 |
| OAuth 2.0 | 第三方授权、SSO | 标准协议 |
| OIDC | 身份认证、社会化登录 | 基于 OAuth 2.0 |
| MFA | 高安全场景 | 二次验证 |
| LDAP | 企业内部系统 | 目录服务集成 |

---

## 一站式认证设置 setup_auth（推荐）

对于大多数项目，推荐使用 `setup_auth()` 一行完成 JWT 认证的全部配置，自动处理：

1. 从 `settings.jwt` 创建 JWTManager
2. （可选）创建角色模型 + User.roles 关系 + RoleMixin 方法注入
3. 创建带缓存的用户获取函数（支持自动失效）
4. 创建 `get_current_user` 和 `get_current_user_optional` 两个 FastAPI 依赖
5. （可选）提供 `app` 时，自动挂载用户管理和登录记录路由

### 快速开始

**一站式最简用法（推荐）：**

传入 `app` 时，框架自动完成认证配置 + 角色创建 + 路由挂载，与 `setup_organization()` 风格一致：

```python
from fastapi import FastAPI
from yweb.auth import setup_auth, AbstractUser

app = FastAPI()

class User(AbstractUser):
    __tablename__ = "sys_user"

# 一行完成：认证 + 角色 + 用户管理路由 + 登录记录路由
auth = setup_auth(app=app, user_model=User, jwt_settings=settings.jwt)

# 框架自动完成以下工作：
# 1. 创建 JWTManager
# 2. 创建 Role 模型 + User.roles + RoleMixin（role_model 默认 True）
# 3. 创建 LoginRecord 模型（login_record_model 默认 True）
# 4. 挂载用户管理路由 → /api/v1/users
# 5. 挂载登录记录路由 → /api/v1/login-records
# 6. 自动推导 token_url → /api/v1/auth/token
```

**不挂载路由（仅认证配置）：**

```python
from yweb.auth import setup_auth, AbstractUser

class User(AbstractUser):
    __tablename__ = "sys_user"

auth = setup_auth(User)  # 不传 app，不挂载路由
```

**需要角色但不挂载路由：**

```python
auth = setup_auth(User, role_model=True)

# 框架自动完成以下工作：
# 1. 创建 Role 模型（table=sys_role，自动推导前缀）
# 2. 设置 User.roles = ManyToMany(Role, UNLINK)（table=sys_user_role）
# 3. 注入 RoleMixin 方法（has_role, role_codes 等）

Role = auth.role_model
Role.create_role(name="管理员", code="admin")
```

> **表名前缀自动推导**：从 `User.__tablename__` 提取前缀。例如 `sys_user` → 前缀 `sys_`，自动生成 `sys_role` 和 `sys_user_role`；`user` → 无前缀，生成 `role` 和 `user_role`。也可通过 `role_table_name` / `role_assoc_table_name` 显式覆盖。

> **关于用户模型**：推荐继承 `AbstractUser`，内置 `username`、`password_hash`、`email`、`phone`、`is_active`、`last_login_at` 等字段和 `get_by_username()` 等查询方法。也可使用任何继承 `BaseModel`（提供 `.get(id)`）且含 `is_active` 字段的自定义模型。

在路由中使用：

```python
from fastapi import Depends
from app.api.dependencies import auth

@app.get("/me")
def get_me(user=Depends(auth.get_current_user)):
    return Resp.OK({"user_id": user.id, "name": user.name})
```

### 自定义参数

```python
from app.config import settings

auth = setup_auth(
    User,
    jwt_settings=settings.jwt,                 # 显式传入 JWT 配置（默认自动从 app.config.settings.jwt 读取）
    token_url="/api/v1/auth/token",            # Swagger UI 登录地址（默认 "token"，提供 app 时自动推导）
    cache_ttl=120,                             # 用户缓存秒数（默认 60，设为 0 禁用缓存）
    active_field="is_active",                  # 活跃状态字段（默认 "is_active"，设为 None 不检查）
    role_model=True,                           # 角色模型（True=自动创建 / AbstractSimpleRole子类=自定义 / None=不启用）
    role_table_name="sys_role",                # 角色表名（仅 role_model=True 时生效，默认自动推导）
    role_assoc_table_name="sys_user_role",     # 关联表名（默认自动推导）
    # 路由挂载参数（提供 app 时生效）
    app=app,                                   # FastAPI 实例（可选，提供时自动挂载路由）
    login_record_model=True,                   # 登录记录（True=自动创建 / AbstractLoginRecord子类=自定义）
    login_record_table_name="sys_login_record",# 登录记录表名（仅 login_record_model=True 时生效）
    api_prefix="/api/v1",                      # API 基础前缀（默认 "/api/v1"）
    user_prefix="/users",                      # 用户路由子前缀（默认 "/users"）
    login_record_prefix="/login-records",      # 登录记录路由子前缀（默认 "/login-records"）
    # 登录防护策略
    ip_max_attempts=10,                        # 同一 IP 最大失败次数（默认 10，0 禁用）
    ip_block_minutes=15,                       # IP 封锁时长（默认 15 分钟）
    max_login_attempts=20,                     # 账户级别最大失败次数（默认 20，需 LockableMixin）
    lock_duration_minutes=30,                  # 账户锁定时长（默认 30 分钟）
)
```

#### role_model 参数说明

| 值 | 说明 |
|---|---|
| `None`（默认） | 不传 `app` 时不启用；传 `app` 时默认 `True`（一站式模式自动启用） |
| `False` | 明确不启用角色管理 |
| `True` | 自动创建 Role 模型 + 设置 User.roles + 注入 RoleMixin |
| `AbstractSimpleRole` 子类 | 使用自定义 Role + 自动设置 User.roles + 注入 RoleMixin |

#### login_record_model 参数说明

| 值 | 说明 |
|---|---|
| `None`（默认） | 不传 `app` 时不启用；传 `app` 时默认 `True`（一站式模式自动启用） |
| `False` | 明确不启用登录记录路由 |
| `True` | 自动创建 LoginRecord 模型（表名从 user_model 推导前缀） |
| `AbstractLoginRecord` 子类 | 使用自定义 LoginRecord（需要额外字段时，如 ForeignKey、自定义索引） |

**自定义 Role 模型示例：**

```python
from yweb.auth import AbstractSimpleRole, AbstractUser, setup_auth
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class MyRole(AbstractSimpleRole):
    __tablename__ = "sys_role"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class User(AbstractUser):
    __tablename__ = "sys_user"

auth = setup_auth(User, role_model=MyRole)
# 自动设置 User.roles = ManyToMany(MyRole, UNLINK)
# 自动注入 RoleMixin（has_role, role_codes 等）
```

### AuthSetup 返回对象

`setup_auth()` 返回 `AuthSetup` 对象，包含以下属性和方法：

| 属性/方法 | 说明 |
|----------|------|
| `auth.get_current_user` | 必须认证的 FastAPI 依赖（未登录抛 401） |
| `auth.get_current_user_optional` | 可选认证的 FastAPI 依赖（未登录返回 None） |
| `auth.jwt_manager` | JWTManager 实例（用于 token 创建/验证/刷新） |
| `auth.user_getter` | 用户获取函数（带缓存） |
| `auth.role_model` | 角色模型类（启用角色时可用，否则为 None） |
| `auth.login_record_model` | 登录记录模型类（启用登录记录时可用，否则为 None） |
| `auth.user_router` | 用户管理路由（挂载路由后可用） |
| `auth.login_record_router` | 登录记录路由（挂载路由后可用） |
| `auth.create_auth_service(...)` | 便捷创建 BaseAuthService 实例（详见 [BaseAuthService](#baseauthservice-认证服务)） |
| `auth.mount_routes(app, ...)` | 手动挂载路由（不传 `app` 给 `setup_auth` 时使用） |
| `auth.invalidate_user_cache(user_id)` | 手动失效单个用户缓存 |
| `auth.invalidate_users_cache(user_ids)` | 批量失效用户缓存 |
| `auth.get_user_cache_stats()` | 获取缓存统计信息 |

### jwt_settings 参数说明

`jwt_settings` 支持多种类型：

| 类型 | 说明 |
|------|------|
| `None`（默认） | 自动从 `app.config.settings.jwt` 读取 |
| `JWTSettings` 实例 | 直接使用（推荐显式传入） |
| `dict` | 作为 `JWTManager` 构造参数 |

### 完整项目示例

```python
# app/domain/auth/model/user.py — 只需定义项目特有字段

from yweb.auth import AbstractUser, LockableMixin
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

class User(LockableMixin, AbstractUser):
    __tablename__ = "user"
    wechat_user_id: Mapped[str] = mapped_column(String(100), nullable=True)
```

```python
# app/main.py — 一站式设置（推荐，与 setup_organization 风格一致）

from fastapi import FastAPI, Depends
from yweb.auth import setup_auth
from app.domain.auth.model.user import User
from app.config import settings

app = FastAPI()

# ==================== 一站式认证设置（app 创建后统一配置） ====================

auth = setup_auth(
    app=app,
    user_model=User,
    jwt_settings=settings.jwt,
    api_prefix="/api/v1",
    # role_model 默认 True：自动创建 Role + User.roles + RoleMixin
    # login_record_model 默认 True：自动创建 LoginRecord + 挂载路由
    # token_url 自动推导为 "/api/v1/auth/token"
)

# 自动挂载以下路由：
# - /api/v1/users（用户管理 CRUD）
# - /api/v1/login-records（登录记录查询）
```

如果有自定义的 LoginRecord（需要额外字段）：

```python
from app.domain.auth.model.login_record import LoginRecord

auth = setup_auth(
    app=app,
    user_model=User,
    login_record_model=LoginRecord,  # 使用自定义模型
    jwt_settings=settings.jwt,
    api_prefix="/api/v1",
)
```

不需要路由挂载时（向后兼容写法）：

```python
# app/api/dependencies.py — 仅设置认证，不挂载路由

from fastapi import Depends, HTTPException, status
from app.domain.auth.model.user import User
from app.config import settings
from yweb.auth import setup_auth

auth = setup_auth(
    User,
    jwt_settings=settings.jwt,
    token_url="/api/v1/auth/token",
    role_model=True,
)

# 后续可手动挂载路由：
# auth.mount_routes(app, login_record_model=True)


# ==================== 角色检查器 ====================

def require_admin(user: User = Depends(auth.get_current_user)) -> User:
    if not user.has_role("admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="需要管理员权限")
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(auth.get_current_user)) -> User:
        if not any(user.has_role(role) for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要以下角色之一: {', '.join(roles)}"
            )
        return user
    return checker
```

使用时通过 `auth` 对象访问所有组件：

```python
from app.api.dependencies import auth

# 认证依赖
Depends(auth.get_current_user)          # 必须登录
Depends(auth.get_current_user_optional) # 可选登录

# JWT 管理器
auth.jwt_manager.create_access_token(payload)

# 角色模型（role_model=True 时可用）
Role = auth.role_model
Role.create_role(name="管理员", code="admin")

# 用户获取（带缓存）
user = auth.user_getter(user_id)

# 缓存管理
auth.invalidate_user_cache(user_id)
auth.get_user_cache_stats()
```

> **与 `create_auth_dependency` 的关系**：`setup_auth()` 是更高层的封装，内部自动完成 JWTManager 创建、用户缓存、缓存失效注册等工作。如需完全自定义认证逻辑（如自定义 Token 格式、非标准用户查询等），仍可使用底层的 `create_auth_dependency()`，详见下方 [JWT 认证](#jwt-认证) 章节。

---

## BaseAuthService 认证服务

`BaseAuthService` 提供认证流程的默认实现，覆盖 80% 项目的常见需求——认证、令牌管理、登出、用户锁定/解锁等，避免每个项目重复编写认证逻辑。

### 内置功能

- **登录记录**：传入 `login_record_model` 后，自动记录每次登录成功/失败，包含具体失败原因（密码错误、用户不存在、账户已禁用、账户已锁定、系统异常等）
- **IP 频率限制**（一级防线）：同一 IP 连续失败 N 次 → 封锁该 IP，不影响合法用户。错误提示包含剩余尝试次数
- **账户锁定**（二级防线）：自动检测 `LockableMixin`，同一账户从多个 IP 累计失败 N 次 → 锁定账户，防御分布式攻击
- **系统异常捕获**：认证过程中的系统异常（数据库错误等）会被正确记录，而非笼统地标记为"用户名或密码错误"

### 快速创建

通过 `setup_auth()` 返回的 `AuthSetup` 对象，一行便捷创建：

```python
from yweb.auth import setup_auth
from app.domain.auth.model.user import User

auth = setup_auth(User)
auth_service = auth.create_auth_service()

# 认证用户
user = auth_service.authenticate("admin", "password123")

# 创建令牌
access_token = auth_service.create_access_token(user)
refresh_token = auth_service.create_refresh_token(user)

# 登出（撤销令牌）
auth_service.logout(user.id)
```

带 Token 黑名单和审计日志：

```python
from yweb.auth import configure_token_blacklist, LoginAuditService
from app.domain.auth.model.login_record import LoginRecord

blacklist = configure_token_blacklist(jwt_manager=auth.jwt_manager)
audit = LoginAuditService(LoginRecord)

auth_service = auth.create_auth_service(
    token_blacklist=blacklist,
    audit_service=audit,
)
```

### 独立构造

不使用 `setup_auth()` 时，也可直接构造：

```python
from yweb.auth import BaseAuthService, JWTManager, TokenBlacklist

auth_service = BaseAuthService(
    user_model=User,
    jwt_manager=jwt_manager,
    token_blacklist=token_blacklist,  # 可选
    audit_service=audit_service,      # 可选
    roles_getter=lambda user: [r.code for r in user.roles],  # 可选
)
```

### AbstractAuthService 接口

`BaseAuthService` 实现了 `AbstractAuthService` 定义的标准接口：

| 方法 | 说明 |
|------|------|
| `authenticate(username, password)` | 认证用户，成功返回用户对象，失败返回 `None`。自动检测 LockableMixin（解锁过期 + 锁定检查） |
| `get_failure_reason(username)` | 判断认证失败的具体原因（用户不存在/密码错误/账户已禁用/账户已锁定），仅内部记录 |
| `create_access_token(user)` | 创建访问令牌（自动提取角色） |
| `create_refresh_token(user)` | 创建刷新令牌 |
| `verify_token(token)` | 验证令牌（自动检查黑名单） |
| `refresh_token(refresh_token)` | 刷新访问令牌 |
| `logout(user_id)` | 登出，撤销用户的所有令牌 |
| `lock_user(user_id)` | 锁定用户（设 `is_active=False` 并撤销令牌） |
| `unlock_user(user_id)` | 解锁用户（设 `is_active=True`） |
| `update_last_login(user_id, **kwargs)` | 更新最后登录时间 + 自动创建登录成功记录（需 `login_record_model`） |

### 继承自定义

框架默认实现已覆盖大部分场景（登录记录、失败累计、自动锁定、成功重置），项目只需在有额外需求时覆写：

```python
from yweb.auth import BaseAuthService

class MyAuthService(BaseAuthService):
    """项目自定义认证服务 — 仅覆写需要额外处理的部分"""
    
    def get_user_roles(self, user) -> list:
        """自定义角色提取逻辑"""
        return [r.code for r in user.custom_roles]
    
    def on_authenticate_failure(self, username, **kwargs):
        """认证失败后：框架默认行为 + 额外告警"""
        super().on_authenticate_failure(username, **kwargs)
        # 额外逻辑：连续失败多次时发送告警
        reason = kwargs.get('reason', '')
        if '账户已锁定' in reason:
            send_alert(f"账户 {username} 已被自动锁定: {reason}")
```

> **注意**：覆写钩子方法时，务必调用 `super()` 以保留框架的默认行为（登录记录创建、失败计数等）。

### 可覆写的钩子方法

| 方法 | 默认行为 | 典型覆写场景 |
|------|---------|-------------|
| `get_user_roles(user)` | 从 `user.roles` 提取 `code` | 自定义角色关系 |
| `get_failure_reason(username)` | 判断具体原因（不存在/密码错误/已禁用/已锁定） | 自定义失败原因（如密码过期） |
| `update_last_login(user_id, **kwargs)` | 更新 `last_login_at` + 创建登录成功记录 | 额外的业务处理 |
| `on_authenticate_success(user, **kwargs)` | 重置失败计数（需 LockableMixin） | 发送通知、额外统计 |
| `on_authenticate_failure(username, **kwargs)` | 累计失败次数 + 自动锁定 + 创建登录失败记录 | 发送告警、IP 封禁 |

---

## 角色管理 AbstractSimpleRole + RoleMixin

提供轻量级的角色管理，适用于只需"用户属于哪些角色"的简单场景。

`yweb.permission.AbstractRole` 继承自 `AbstractSimpleRole`，如需升级到完整 RBAC（树形角色继承 + 权限管理），只需更换 Role 基类，`User.has_role()` / `User.role_codes` 等 API 保持不变。

### 推荐方式：setup_auth(role_model=True)

最简单的角色管理——零配置，只需一个参数：

```python
from yweb.auth import setup_auth, AbstractUser

class User(AbstractUser):
    __tablename__ = "sys_user"

auth = setup_auth(User, role_model=True)
```

框架自动完成：
- 创建 `Role` 模型（继承 `AbstractSimpleRole`，表名自动推导）
- 设置 `User.roles = ManyToMany(Role, on_delete=UNLINK)`（中间表名自动推导）
- 注入 `RoleMixin` 方法到 `User`（`has_role()`、`role_codes` 等）

> **表名自动推导**：从 `User.__tablename__` 提取前缀。`sys_user` → `sys_role` + `sys_user_role`，`user` → `role` + `user_role`。可通过 `role_table_name` / `role_assoc_table_name` 显式覆盖。

使用角色：

```python
Role = auth.role_model

# 创建角色
Role.create_role(name="管理员", code="admin")
Role.create_role(name="普通用户", code="user")

# 查询角色
admin_role = Role.get_by_code("admin")
all_roles = Role.list_all()

# 用户角色操作（RoleMixin 自动注入）
user = User.get(1)
user.add_role(admin_role)
user.has_role("admin")            # True
user.role_codes                   # {"admin"}
user.remove_role(admin_role)
```

### 自定义 Role 模型

需要额外字段时，传入自定义 `AbstractSimpleRole` 子类：

```python
from yweb.auth import AbstractSimpleRole, AbstractUser, setup_auth
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import Integer

class MyRole(AbstractSimpleRole):
    __tablename__ = "sys_role"
    sort_order: Mapped[int] = mapped_column(Integer, default=0)

class User(AbstractUser):
    __tablename__ = "sys_user"

auth = setup_auth(User, role_model=MyRole)
# 自动设置 User.roles + RoleMixin，无需手动配置
```

### AbstractSimpleRole 内置功能

继承自 `BaseModel`，自动拥有 `id`、`name`（角色名称）、`code`（角色代码，唯一标识）、`created_at`、`updated_at` 等字段。

额外字段：`description`（角色描述，Text 类型）。

| 方法 | 说明 |
|------|------|
| `Role.get_by_code("admin")` | 根据角色代码查询 |
| `Role.list_all()` | 获取所有角色 |
| `Role.create_role(name, code, description)` | 创建角色 |

### RoleMixin 方法

通过 `setup_auth(role_model=...)` 自动注入到 User，无需手动混入：

```python
user = User.get(1)

user.has_role("admin")            # 检查是否拥有某角色
user.has_any_role("admin", "mgr") # 拥有任一角色即返回 True
user.has_all_roles("admin", "mgr")# 必须同时拥有所有角色

user.role_codes                   # 获取角色代码集合: {"admin", "user"}

user.add_role(admin_role)         # 添加角色
user.remove_role(admin_role)      # 移除角色
```

> **也可手动使用**：如果不使用 `setup_auth` 管理角色，可以手动继承 `RoleMixin` 并定义 `roles` 关系：
> ```python
> from yweb.auth import RoleMixin, AbstractUser
> from yweb.orm import fields
> 
> class User(RoleMixin, AbstractUser):
>     roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)
> ```

### 路由角色检查

```python
from fastapi import Depends, HTTPException, status

def require_roles(*roles: str):
    """角色检查依赖"""
    def checker(user=Depends(auth.get_current_user)):
        if not any(user.has_role(r) for r in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要以下角色之一: {', '.join(roles)}"
            )
        return user
    return checker

# 使用
@app.get("/admin/dashboard")
def admin_dashboard(user=Depends(require_roles("admin"))):
    return {"message": "Welcome admin"}
```

---

## 输入验证器

`yweb.auth.validators` 提供认证场景专用的验证器。邮箱/手机号验证请使用通用模块 `yweb.validators`。

### PasswordValidator 密码强度验证

采用「强度等级 + 长度」两个维度组合，简单直观。与 `PasswordHelper`（负责哈希/验证）互补，本类只负责检查密码格式和强度。

#### 强度等级

| 等级 | 枚举值 | 字符要求 |
|------|--------|---------|
| 基础 | `PasswordStrength.BASIC` | 字母 + 数字 |
| 中等 | `PasswordStrength.MEDIUM` | 大写字母 + 小写字母 + 数字 |
| 强 | `PasswordStrength.STRONG` | 大写字母 + 小写字母 + 数字 + 特殊字符 |

长度（`min_length` / `max_length`）独立于强度等级，可自由组合。

#### 基本用法

```python
from yweb.auth import PasswordValidator, PasswordStrength

# 类方法 — 使用全局默认规则（默认 STRONG + 8-128）
PasswordValidator.validate("MyP@ss123")       # True
PasswordValidator.validate("weak")            # False
PasswordValidator.validate_or_raise("weak")   # 抛出 ValidationError
```

#### 工厂方法 — 指定等级 + 长度

```python
# BASIC：字母+数字，最少 6 位
v = PasswordValidator.of(PasswordStrength.BASIC, min_length=6)
v.validate_instance("abc123")   # True
v.validate_instance("abcdef")   # False（缺少数字）

# MEDIUM：大小写+数字，最少 8 位
v = PasswordValidator.of(PasswordStrength.MEDIUM, min_length=8)
v.validate_instance("Abcdefg1") # True

# STRONG：大小写+数字+特殊字符，最少 10 位
v = PasswordValidator.of(PasswordStrength.STRONG, min_length=10)
v.validate_instance("MyP@ssw0rd!")  # True
```

#### 修改全局默认

```python
# 降低为基础强度，最少 6 位（影响类方法 validate / validate_or_raise）
PasswordValidator.configure(
    strength=PasswordStrength.BASIC,
    min_length=6,
)

PasswordValidator.validate("abc123")  # True
```

#### 获取详细错误信息

```python
v = PasswordValidator.of(PasswordStrength.STRONG, min_length=8)
errors = v.get_errors("abc")
# ['密码长度不能少于 8 个字符', '密码必须包含大写字母', '密码必须包含数字', '密码必须包含特殊字符']
```

### UsernameValidator 用户名验证

默认规则：长度 1-20，允许中文、英文字母、数字、下划线。

```python
from yweb.auth import UsernameValidator

# 类方法 — 使用默认规则
UsernameValidator.validate("admin")       # True
UsernameValidator.validate("管理员")       # True
UsernameValidator.validate("user@name")   # False（含非法字符）
UsernameValidator.validate_or_raise("")   # 抛出 ValidationError

# 自定义规则
v = UsernameValidator(min_length=3, max_length=16, allow_chinese=False)
v.validate_instance("ab")                # False（太短）
v.validate_instance("admin")             # True

# 修改全局默认
UsernameValidator.configure(min_length=3, allow_chinese=False)
```

### 与 yweb.validators 的关系

| 场景 | 使用 | 说明 |
|------|------|------|
| 密码强度 | `yweb.auth.validators.PasswordValidator` | 认证专用 |
| 用户名格式 | `yweb.auth.validators.UsernameValidator` | 认证专用 |
| 邮箱验证（DTO） | `yweb.validators.Email` | Pydantic 约束 |
| 手机号验证（DTO） | `yweb.validators.Phone` | Pydantic 约束 |
| 邮箱验证（Service） | `yweb.validators.is_valid_email()` | 纯函数 |
| 手机号验证（Service） | `yweb.validators.is_valid_phone()` | 纯函数 |

---

## JWT 认证

JWT 是最常用的 API 认证方式，适合前后端分离应用。

> **推荐**：大多数场景使用 [setup_auth()](#一站式认证设置-setup_auth推荐) 即可，无需手动创建以下组件。以下内容适用于需要完全自定义认证逻辑的高级场景。

### 基础使用

```python
from fastapi import FastAPI, Depends
from yweb.auth import JWTManager, TokenPayload, create_auth_dependency
from yweb.response import Resp

app = FastAPI()

# 1. 创建 JWT 管理器
jwt_manager = JWTManager(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,
    refresh_token_expire_days=7,
)

# 2. 模拟获取用户函数
def get_user_by_id(user_id: int):
    # 实际应用中从数据库查询
    return {"id": user_id, "username": "admin"}

# 3. 创建认证依赖
get_current_user = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
)

# 4. 登录接口 - 生成 Token
@app.post("/login")
def login(username: str, password: str):
    # 验证用户名密码（省略）
    user_id = 1
    
    payload = TokenPayload(
        sub=username,
        user_id=user_id,
        username=username,
        roles=["admin"],
    )
    
    return Resp.OK({
        "access_token": jwt_manager.create_access_token(payload),
        "refresh_token": jwt_manager.create_refresh_token(payload),
        "token_type": "bearer",
    }, message="登录成功")

# 5. 受保护的接口
@app.get("/me")
def get_me(user=Depends(get_current_user)):
    return Resp.OK({"user": user})
```

### 刷新 Token

```python
@app.post("/refresh")
def refresh_token(refresh_token: str):
    # 使用便捷方法刷新（推荐）
    new_access_token = jwt_manager.refresh_from_refresh_token(
        refresh_token,
        user_getter=get_user_by_id  # 可选：获取最新用户信息
    )
    
    if not new_access_token:
        return Resp.Unauthorized(message="无效的刷新令牌")
    
    return Resp.OK({
        "access_token": new_access_token,
        "token_type": "bearer",
    }, message="刷新成功")
```

---

## Refresh Token 滑动过期

实现活跃用户"永不过期"的体验：当用户使用 Refresh Token 换取新 Access Token 时，如果 Refresh Token 即将过期，自动返回新的 Refresh Token。

### 设计理念

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        双 Token 机制                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│   Access Token (默认30分钟)                                                      │
│   ├── 功能：API 请求认证                                                     │
│   ├── 特点：短有效期，减少泄露风险                                           │
│   └── 过期后：用 Refresh Token 换取新的                                      │
│                                                                             │
│   Refresh Token (默认7天)                                                        │
│   ├── 功能：换取新的 Access Token                                            │
│   ├── 特点：长有效期，只在刷新接口使用                                        │
│   └── 滑动过期：默认剩余 2 天时自动续期                                           │
│                                                                             │
│   效果：只要用户 2 天内活跃过一次，就永远不会被登出                            │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

流程图

用户登录（第1天）
    │
    ├── Access Token  (过期时间: 第1天 + 30分钟)
    └── Refresh Token (过期时间: 第8天)  ← 客户端保存
    
第3天，Access Token 过期，用 Refresh Token 刷新
    │
    │   剩余 5 天 > 2 天阈值
    │
    ├── 新 Access Token (过期时间: 第3天 + 30分钟)
    └── Refresh Token: 不续期，还是原来那个
    
第6天，再次刷新
    │
    │   剩余 2 天 ≤ 2 天阈值 → 触发续期！
    │
    ├── 新 Access Token (过期时间: 第6天 + 30分钟)
    └── 新 Refresh Token (过期时间: 第13天)  ← 客户端替换保存！
        │
        └── 旧 Token 虽然还有效，但客户端已不再使用
```

### 配置说明

```yaml
jwt:
  secret_key: "your-secret-key"
  access_token_expire_minutes: 30      # Access Token 有效期（分钟）
  refresh_token_expire_days: 7         # Refresh Token 基础有效期（天）
  refresh_token_sliding_days: 2        # 滑动过期阈值（天），剩余时间少于此值时自动续期
```

### 服务端实现

```python
from yweb.auth import JWTManager, TokenPayload
from yweb.response import Resp

# 1. 创建 JWT 管理器
jwt_manager = JWTManager(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,       # Access Token 30 分钟
    refresh_token_expire_days=7,          # Refresh Token 7 天
    refresh_token_sliding_days=2,         # 剩余 2 天时自动续期
)

# 2. 刷新接口
@router.post("/auth/refresh")
def refresh_token(refresh_token: str):
    """使用 Refresh Token 换取新 Token"""
    
    # refresh_tokens() 返回格式：
    # {
    #     "access_token": "new_access_token",
    #     "refresh_token": "new_refresh_token",  # 字段始终存在，值为 None 表示不需要续期
    #     "token_type": "bearer",
    #     "refresh_token_renewed": True | False,  # True 表示已续期，False 表示未续期
    # }
    result = jwt_manager.refresh_tokens(
        refresh_token,
        user_getter=lambda uid: User.get_by_id(uid)  # 可选：验证用户状态
    )
    
    if not result:
        return Resp.Unauthorized(message="无效的刷新令牌")
    
    return Resp.OK({
        "access_token": result["access_token"],
        "refresh_token": result["refresh_token"],  # 可能为 None（表示不需要续期）
        "token_type": result["token_type"],
    }, message="刷新成功")
```

### 前端配合

后端所有认证错误统一返回 BaseResponse 格式（含 `error_code`），前端通过 `error_code` 做逻辑判断，通过 `message` 做 UI 展示。

**关键 error_code**：

| error_code | 含义 | 前端处理 |
|-----------|------|---------|
| `TOKEN_EXPIRED` | Access Token 过期 | 自动刷新，用户无感知 |
| `INVALID_TOKEN` | Token 无效 | 跳转登录页 |
| `AUTHENTICATION_FAILED` | 登录失败/其他认证失败 | 展示 message |

```javascript
// ========== 登录成功后保存 Token ==========
function handleLoginSuccess(response) {
  // response 已被拦截器解包为 BaseResponse
  const { access_token, refresh_token } = response.data;
  localStorage.setItem('access_token', access_token);
  localStorage.setItem('refresh_token', refresh_token);
}

// ========== Axios 响应拦截器（核心） ==========
api.interceptors.response.use(
  response => response.data,  // 成功时返回 BaseResponse
  async error => {
    if (error.response?.status !== 401) {
      return Promise.reject(error);
    }

    const { error_code, message } = error.response.data || {};
    const originalRequest = error.config;

    // 登录/刷新请求的 401 → 直接展示后端消息
    if (originalRequest.url.includes('/auth/login') ||
        originalRequest.url.includes('/auth/refresh')) {
      return Promise.reject(new Error(message || '认证失败'));
    }

    // ★ 核心：只有 TOKEN_EXPIRED 才自动刷新
    if (error_code === 'TOKEN_EXPIRED' && !originalRequest._retry) {
      originalRequest._retry = true;
      const refreshed = await refreshAccessToken();
      if (refreshed) {
        originalRequest.headers['Authorization'] =
          `Bearer ${localStorage.getItem('access_token')}`;
        return api(originalRequest);
      }
    }

    // 其他 401 → 跳转登录页
    redirectToLogin();
    return Promise.reject(new Error(message || '认证失败'));
  }
);

// ========== 刷新 Token（请求体传递） ==========
async function refreshAccessToken() {
  const refreshToken = localStorage.getItem('refresh_token');
  if (!refreshToken) return false;

  try {
    // ★ 通过请求体传递 refresh_token（非 query 参数）
    const response = await api.post('/auth/refresh', {
      refresh_token: refreshToken
    });

    const { access_token, refresh_token: newRefreshToken } = response.data;
    if (!access_token) return false;

    localStorage.setItem('access_token', access_token);

    // 滑动过期续期
    if (newRefreshToken) {
      localStorage.setItem('refresh_token', newRefreshToken);
    }

    return true;
  } catch (error) {
    redirectToLogin();
    return false;
  }
}
```

### JWTManager 方法

```python
# 获取 Token 剩余秒数
remaining_seconds = jwt_manager.get_remaining_seconds(token)

# 获取 Token 剩余天数
remaining_days = jwt_manager.get_remaining_days(token)

# 判断 Refresh Token 是否需要续期
if jwt_manager.should_renew_refresh_token(refresh_token):
    print("Refresh Token 即将过期，需要续期")

# 使用 Refresh Token 换取新 Token（推荐方式）
result = jwt_manager.refresh_tokens(refresh_token, user_getter=get_user)
# result["access_token"] - 新的 Access Token
# result["refresh_token"] - 新的 Refresh Token（如果续期了）
# result["refresh_token_renewed"] - 是否续期了 Refresh Token

# 兼容旧 API：仅获取新 Access Token
new_access_token = jwt_manager.refresh_from_refresh_token(refresh_token)
```

### 参数校验

```python
# refresh_token_sliding_days 必须小于 refresh_token_expire_days
jwt_manager = JWTManager(
    secret_key="test",
    refresh_token_expire_days=7,
    refresh_token_sliding_days=7,  # ❌ 错误：等于有效期
)
# ValueError: refresh_token_sliding_days (7) 必须小于 refresh_token_expire_days (7)

# 设置为 0 可禁用滑动过期
jwt_manager = JWTManager(
    secret_key="test",
    refresh_token_sliding_days=0,  # ✅ 禁用滑动过期
)
```

---

## Token 撤销/黑名单

实现 Token 撤销功能，支持单个 Token 撤销和用户级别的全部撤销。

### 基础使用

```python
from yweb.auth import (
    TokenBlacklist, 
    InMemoryTokenStore,
    configure_token_blacklist,
)

# 1. 创建存储后端（内存存储，适合单实例）
store = InMemoryTokenStore()

# 2. 创建黑名单管理器
blacklist = TokenBlacklist(store, jwt_manager)

# 3. 撤销单个 Token（登出时）
blacklist.revoke_token(token, reason="user_logout")

# 4. 撤销用户所有 Token（修改密码、账户被锁定时）
blacklist.revoke_all_user_tokens(user_id=1)

# 5. 检查 Token 是否被撤销
if blacklist.is_revoked(token):
    raise HTTPException(status_code=401, detail="Token 已被撤销")
```

### Redis 存储（多实例部署）

```python
import redis
from yweb.auth import RedisTokenStore, TokenBlacklist

# 使用 Redis 存储（适合多实例部署）
redis_client = redis.Redis(host='localhost', port=6379, db=0)
store = RedisTokenStore(
    redis_client,
    prefix="token_blacklist:",
    default_ttl_seconds=86400 * 7,  # 记录保留 7 天
)

blacklist = TokenBlacklist(store, jwt_manager)
```

### 全局配置

```python
from yweb.auth import configure_token_blacklist, get_token_blacklist

# 在应用启动时配置
configure_token_blacklist(
    store=InMemoryTokenStore(),  # 或 RedisTokenStore
    jwt_manager=jwt_manager,
)

# 在任何地方使用
blacklist = get_token_blacklist()
blacklist.revoke_token(token)
```

### 在认证依赖中集成

**方式1：手动集成黑名单检查**

```python
from yweb.auth import get_token_blacklist
from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer

oauth2_scheme = HTTPBearer()

def get_current_user_with_blacklist(
    token: str = Depends(oauth2_scheme)
):
    # 1. 检查黑名单
    blacklist = get_token_blacklist()
    if blacklist and blacklist.is_revoked(token.credentials):
        raise HTTPException(401, "Token 已被撤销")
    
    # 2. 正常验证
    token_data = jwt_manager.verify_token(token.credentials)
    if not token_data:
        raise HTTPException(401, "无效的 Token")
    
    # 3. 获取用户
    user = get_user_by_id(token_data.user_id)
    if not user:
        raise HTTPException(401, "用户不存在")
    
    return user

# 使用
@app.get("/protected")
def protected_route(user = Depends(get_current_user_with_blacklist)):
    return {"user_id": user.id}
```

**方式2：基于 setup_auth 添加黑名单检查**

```python
from yweb.auth import get_token_blacklist
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer
from app.api.dependencies import auth

oauth2_scheme = HTTPBearer()

# 包装添加黑名单检查
def get_current_user_with_blacklist(
    user = Depends(auth.get_current_user),
    token = Depends(oauth2_scheme)
):
    blacklist = get_token_blacklist()
    if blacklist and blacklist.is_revoked(token.credentials):
        raise HTTPException(401, "Token 已被撤销")
    return user

# 使用
@app.get("/protected")
def protected_route(user = Depends(get_current_user_with_blacklist)):
    return {"user_id": user.id}
```

> 也可以使用底层的 `create_auth_dependency()` 代替 `setup_auth()`，效果相同。

**完整示例：登出接口**

```python
@app.post("/auth/logout")
def logout(
    token: str = Depends(oauth2_scheme),
    user = Depends(get_current_user_with_blacklist)
):
    """登出接口：撤销当前 Token"""
    blacklist = get_token_blacklist()
    blacklist.revoke_token(token.credentials, reason="user_logout")
    return Resp.OK(message="登出成功")

@app.post("/auth/logout-all")
def logout_all(user = Depends(get_current_user_with_blacklist)):
    """撤销用户所有 Token（如修改密码后）"""
    blacklist = get_token_blacklist()
    blacklist.revoke_all_user_tokens(user_id=user.id)
    return Resp.OK(message="已撤销所有登录会话")
```

---

## API Key 认证

适合服务间调用和第三方 API 集成。

### 基础使用

```python
from yweb.auth import APIKeyManager
from yweb.response import Resp

# 1. 创建管理器
api_key_manager = APIKeyManager(
    secret_key="your-secret-key",
    prefix="myapp",  # Key 前缀
)

# 2. 设置存储（生产环境使用数据库）
# 注意：getter 可以接收 key_hash 或 key_id 作为参数
api_keys_db = {}

api_key_manager.set_key_store(
    # getter: 根据 key_hash 查询 API Key 数据
    # 参数可以是 key_hash（字符串）或 key_id（整数）
    getter=lambda key_hash: api_keys_db.get(key_hash),
    
    # saver: 保存 API Key 数据
    # data 是 APIKeyData 对象，包含 key_hash, user_id, scopes 等字段
    saver=lambda data: api_keys_db.update({data.key_hash: data}) or True,
)

# 生产环境示例：使用数据库存储
# def get_api_key_from_db(key_hash: str):
#     """从数据库查询 API Key"""
#     api_key = APIKey.query.filter_by(key_hash=key_hash).first()
#     if not api_key:
#         return None
#     return APIKeyData(
#         key_hash=api_key.key_hash,
#         user_id=api_key.user_id,
#         scopes=api_key.scopes.split(",") if api_key.scopes else [],
#         expires_at=api_key.expires_at,
#     )
#
# def save_api_key_to_db(data: APIKeyData) -> bool:
#     """保存 API Key 到数据库"""
#     api_key = APIKey(
#         key_hash=data.key_hash,
#         user_id=data.user_id,
#         scopes=",".join(data.scopes),
#         expires_at=data.expires_at,
#     )
#     api_key.save(commit=True)
#     return True
#
# api_key_manager.set_key_store(
#     getter=get_api_key_from_db,
#     saver=save_api_key_to_db,
# )

# 3. 生成 API Key
key_data = api_key_manager.generate_key(
    user_id=1,
    name="Production API Key",
    scopes=["read", "write"],
    expires_days=365,
)
print(f"API Key: {key_data.key}")  # myapp_xxxx_xxxxxxxxxx
# 注意：完整的 key 只在创建时返回一次，请妥善保存！

# 4. 创建 FastAPI 依赖
get_api_user = api_key_manager.create_dependency(
    user_getter=get_user_by_id,
    header_name="X-API-Key",  # 从 Header 获取
)

# 5. 使用
@app.get("/api/data")
def get_data(user=Depends(get_api_user)):
    return Resp.OK({"data": "secret", "user": user})
```

### 调用方式

```bash
# 通过 Header
curl -H "X-API-Key: myapp_xxxx_xxxxxxxxxx" http://localhost:8000/api/data

# 通过 Query 参数
curl "http://localhost:8000/api/data?api_key=myapp_xxxx_xxxxxxxxxx"
```

---

## Session 认证

适合传统 Web 应用，使用 Cookie 管理会话。

### 基础使用

```python
from fastapi import Response, Request, Depends
from yweb.auth import SessionManager, set_session_cookie, clear_session_cookie
from yweb.response import Resp

# 1. 创建管理器
session_manager = SessionManager(
    secret_key="your-secret-key",
    expire_minutes=30,
    max_sessions_per_user=5,  # 限制每用户最多 5 个会话
)

# 2. 登录
@app.post("/login")
def login(response: Response, username: str, password: str):
    # 验证用户（省略）
    user_id = 1
    
    # 创建会话
    session = session_manager.create_session(
        user_id=user_id,
        ip_address="127.0.0.1",
    )
    
    # 设置 Cookie
    set_session_cookie(response, session)
    
    return Resp.OK(message="登录成功")

# 3. 创建认证依赖
get_session_user = session_manager.create_dependency(
    user_getter=get_user_by_id,
)

# 4. 受保护的接口
@app.get("/dashboard")
def dashboard(user=Depends(get_session_user)):
    return Resp.OK({"user": user})

# 5. 登出
@app.post("/logout")
def logout(response: Response, request: Request):
    session_id = request.cookies.get("session_id")
    if session_id:
        session_manager.destroy_session(session_id)
    clear_session_cookie(response)
    return Resp.OK(message="已登出")
```

---

## OAuth 2.0

提供标准的 OAuth 2.0 授权服务。

### 快速集成

```python
from yweb.auth.oauth2 import OAuth2Manager
from yweb.auth.api import create_oauth2_router

# 1. 创建管理器
oauth2_manager = OAuth2Manager(
    secret_key="your-secret-key",
    access_token_expire_minutes=30,
)

# 2. 注册客户端
client = oauth2_manager.create_client(
    name="My Web App",
    redirect_uris=["http://localhost:3000/callback"],
    allowed_grant_types=["authorization_code", "refresh_token"],
    allowed_scopes=["openid", "profile", "email"],
)
print(f"Client ID: {client.client_id}")
print(f"Client Secret: {client.client_secret}")

# 3. 添加路由
router = create_oauth2_router(oauth2_manager)
app.include_router(router, prefix="/oauth2")
```

### 配置参数说明

**OAuth2Manager 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `secret_key` | str | 必填 | 用于签名 Token 的密钥 |
| `access_token_expire_minutes` | int | 30 | Access Token 过期时间（分钟） |
| `refresh_token_expire_days` | int | 30 | Refresh Token 过期时间（天） |
| `authorization_code_expire_minutes` | int | 10 | 授权码过期时间（分钟） |
| `algorithm` | str | "HS256" | JWT 签名算法 |

**create_client 参数**：

| 参数 | 类型 | 说明 |
|------|------|------|
| `name` | str | 客户端名称 |
| `redirect_uris` | List[str] | 允许的回调地址列表 |
| `allowed_grant_types` | List[str] | 允许的授权类型（authorization_code, client_credentials, refresh_token 等） |
| `allowed_scopes` | List[str] | 允许的权限范围 |
| `client_id` | str | 可选，不传则自动生成 |
| `client_secret` | str | 可选，不传则自动生成 |

> **详细文档**：更多 OAuth 2.0 配置和使用方式，请参考独立的 OAuth 2.0 指南文档

### 可用端点

| 端点 | 说明 |
|------|------|
| `GET /oauth2/authorize` | 授权页面 |
| `POST /oauth2/token` | 获取 Token |
| `POST /oauth2/revoke` | 撤销 Token |
| `POST /oauth2/introspect` | Token 内省 |
| `POST /oauth2/device/code` | 设备码授权 |

### 客户端凭证模式

适合服务间调用：

```python
# 获取 Token
success, token = oauth2_manager.client_credentials_token(
    client_id="your-client-id",
    client_secret="your-client-secret",
    scope="api.read api.write",
)

if success:
    print(f"Access Token: {token.access_token}")
```

---

## OpenID Connect (OIDC)

基于 OAuth 2.0 的身份认证层，提供标准化的用户身份信息。

### 基础使用

```python
from yweb.auth.oidc import OIDCManager
from yweb.auth.api import create_oidc_router

# 1. 创建管理器
oidc_manager = OIDCManager(
    issuer="https://sso.example.com",
    secret_key="your-secret-key",
)

# 2. 设置用户信息获取函数
def get_user_claims(user_id):
    """返回用户的 OIDC 声明"""
    return {
        "sub": str(user_id),
        "name": "张三",
        "email": "zhangsan@example.com",
        "email_verified": True,
    }

oidc_manager.set_user_claims_getter(get_user_claims)

# 3. 创建 ID Token
id_token = oidc_manager.create_id_token(
    user_id=1,
    client_id="my-app",
    scope="openid profile email",
)

# 4. 验证 ID Token
claims = oidc_manager.verify_id_token(id_token, client_id="my-app")
print(claims)  # {"sub": "1", "name": "张三", ...}

# 5. 添加路由
router = create_oidc_router(oidc_manager, oauth2_manager)
app.include_router(router)
```

### 配置参数说明

**OIDCManager 参数**：

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `issuer` | str | 必填 | OIDC 发行者标识（通常是服务器 URL） |
| `secret_key` | str | 必填 | 用于签名 ID Token 的密钥 |
| `id_token_expire_minutes` | int | 60 | ID Token 过期时间（分钟） |
| `algorithm` | str | "HS256" | JWT 签名算法 |

**支持的标准声明（Claims）**：

| 声明 | 说明 |
|------|------|
| `sub` | 用户唯一标识（必填） |
| `name` | 用户全名 |
| `email` | 用户邮箱 |
| `email_verified` | 邮箱是否已验证 |
| `phone_number` | 电话号码 |
| `phone_number_verified` | 电话是否已验证 |
| `picture` | 用户头像 URL |
| `preferred_username` | 首选用户名 |

> **详细文档**：更多 OIDC 配置和使用方式，请参考独立的 OIDC 指南文档

### Discovery 端点

访问 `/.well-known/openid-configuration` 获取 OIDC 配置信息。

---

## 多因素认证 (MFA)

为高安全场景提供二次验证。

### TOTP (Google Authenticator)

```python
from yweb.auth.mfa import TOTPProvider

# 1. 创建提供者
totp = TOTPProvider(issuer="MyApp")

# 2. 为用户启用 TOTP
setup_data = totp.setup(
    user_id=1,
    username="zhangsan",
    email="zhangsan@example.com",
)

print(f"密钥: {setup_data.secret}")
print(f"二维码 URI: {setup_data.uri}")
# 用户使用 Authenticator App 扫描 URI 生成的二维码

# 3. 验证 TOTP 代码
result = totp.verify(user_id=1, code="123456")
if result.success:
    print("验证成功")
else:
    print(f"验证失败: {result.message}")
```

### 短信/邮件验证码

```python
from yweb.auth.mfa import SMSProvider, EmailProvider

# 短信验证码
sms = SMSProvider(
    code_length=6,
    expire_minutes=5,
)

# 设置发送函数
sms.set_sms_sender(lambda phone, code: send_sms(phone, f"验证码: {code}"))

# 发送验证码
success, msg = sms.send_code(user_id=1, phone="+8613800138000")

# 验证
result = sms.verify(user_id=1, code="123456")
```

### 恢复码

```python
from yweb.auth.mfa import RecoveryCodeProvider

# 生成恢复码
recovery = RecoveryCodeProvider(code_count=10)
setup_data = recovery.setup(user_id=1)

print("请保存以下恢复码:")
for code in setup_data.recovery_codes:
    print(f"  - {code}")

# 使用恢复码（每个只能用一次）
result = recovery.verify(user_id=1, code="ABCD-1234")
```

### MFA 管理器

统一管理多种 MFA 方式：

```python
from yweb.auth.mfa import MFAManager, TOTPProvider, RecoveryCodeProvider

mfa_manager = MFAManager()
mfa_manager.register_provider("totp", TOTPProvider(issuer="MyApp"))
mfa_manager.register_provider("recovery", RecoveryCodeProvider())

# 为用户启用 TOTP
setup_data = mfa_manager.setup(user_id=1, provider_name="totp", username="zhangsan")

# 验证（指定方式）
result = mfa_manager.verify(user_id=1, provider_name="totp", code="123456")

# 验证（自动尝试所有已启用的方式）
result = mfa_manager.verify_any(user_id=1, code="123456")
```

---

## LDAP/AD 认证

与企业目录服务集成。

### OpenLDAP

```python
from yweb.auth import LDAPManager

ldap = LDAPManager(
    server="ldap://ldap.example.com:389",
    base_dn="dc=example,dc=com",
    bind_dn="cn=admin,dc=example,dc=com",
    bind_password="admin_password",
)

# 测试连接
success, msg = ldap.test_connection()
print(msg)

# 验证用户
success, user = ldap.authenticate("zhangsan", "user_password")
if success:
    print(f"用户: {user.username}")
    print(f"邮箱: {user.email}")
    print(f"所属组: {user.groups}")
```

### Active Directory

```python
from yweb.auth import LDAPManager, create_active_directory_config

# 使用便捷函数创建配置
config = create_active_directory_config(
    server="ldaps://ad.corp.example.com:636",
    base_dn="dc=corp,dc=example,dc=com",
    bind_dn="admin@corp.example.com",
    bind_password="admin_password",
    use_ssl=True,
)

ldap = LDAPManager(config=config)

# 验证用户
success, user = ldap.authenticate("zhangsan", "password")
```

### 角色映射

```python
from yweb.auth import LDAPAuthProvider

provider = LDAPAuthProvider(
    ldap_manager=ldap,
    role_mapping={
        "Domain Admins": ["admin", "superuser"],
        "Developers": ["developer"],
        "Users": ["user"],
    },
)

result = provider.authenticate({
    "username": "zhangsan",
    "password": "password",
})

if result.success:
    print(f"角色: {result.identity.roles}")
```

> **注意**: LDAP 功能需要安装 `ldap3` 库：`pip install ldap3`

---

## 登录审计

记录用户登录历史，支持安全分析和合规审计。

### 定义登录记录模型

**方式1：自动创建（推荐，无需额外定义）**

使用 `setup_auth(app=app, ...)` 时，`login_record_model` 默认为 `True`，框架自动创建 `LoginRecord` 模型，表名从 `user_model` 推导前缀（如 `sys_user` → `sys_login_record`，`user` → `login_record`）。

**方式2：自定义模型（需要额外字段时）**

```python
from yweb.auth import AbstractLoginRecord
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy import String

class LoginRecord(AbstractLoginRecord):
    """登录记录模型"""
    __tablename__ = "login_record"
    
    # 可以添加额外字段
    device_type: Mapped[str] = mapped_column(String(50), nullable=True)
```

然后传入 `setup_auth`：

```python
auth = setup_auth(app=app, user_model=User, login_record_model=LoginRecord)
```

#### AbstractLoginRecord 内置功能

继承后自动获得标准字段和便捷查询方法：

**内置字段：** `user_id`、`username`、`ip_address`、`user_agent`、`status`、`failure_reason`、`login_at`、`location`、`device_info`

**内置查询方法：**

| 方法 | 说明 |
|------|------|
| `LoginRecord.create_record(record)` | 创建并保存登录记录 |
| `LoginRecord.get_recent_logins(limit=10)` | 获取最近登录记录（按时间倒序） |
| `LoginRecord.get_user_logins(user_id, limit=10)` | 获取指定用户的登录记录 |
| `LoginRecord.count_records()` | 获取登录记录总数 |

> 这些是模型层的简单直查方法。更复杂的查询（按状态过滤、IP 历史、失败次数统计等）请使用 `LoginAuditService`。

### 使用审计服务

```python
from yweb.auth import LoginAuditService, LoginStatus, LoginFailureReason

# 创建审计服务
audit_service = LoginAuditService(LoginRecord)

# 记录成功登录
audit_service.record_success(
    user_id=1,
    username="zhangsan",
    ip_address="192.168.1.100",
    user_agent="Mozilla/5.0...",
    location="北京",
)

# 记录失败登录
audit_service.record_failure(
    username="zhangsan",
    ip_address="192.168.1.100",
    failure_reason=LoginFailureReason.INVALID_PASSWORD,
)

# 查询用户登录历史
records = audit_service.get_user_login_history(
    user_id=1, 
    limit=10,
    status="success"  # 可选：只查成功/失败
)

# 获取最近失败次数（用于登录限制）
failures = audit_service.get_recent_failures(
    username="zhangsan",
    minutes=30,  # 最近 30 分钟
    ip_address="192.168.1.100",  # 可选：限制特定 IP
)

if failures >= 5:
    raise HTTPException(429, "登录失败次数过多，请稍后重试")

# 获取最后一次成功登录
last_login = audit_service.get_last_successful_login(user_id=1)
print(f"上次登录: {last_login.login_at} from {last_login.ip_address}")

# 统计登录情况
stats = audit_service.count_logins_by_status(user_id=1, days=30)
print(f"成功: {stats.get('success', 0)}, 失败: {stats.get('failed', 0)}")

# 清理旧记录
deleted = audit_service.cleanup_old_records(days=90, keep_failures=True)
```

### 登录状态枚举

```python
from yweb.auth import LoginStatus, LoginFailureReason

# 登录状态
LoginStatus.SUCCESS      # 成功
LoginStatus.FAILED       # 失败
LoginStatus.LOCKED       # 账户被锁定
LoginStatus.DISABLED     # 账户被禁用
LoginStatus.MFA_REQUIRED # 需要 MFA

# 失败原因
LoginFailureReason.INVALID_USERNAME   # 用户名不存在
LoginFailureReason.INVALID_PASSWORD   # 密码错误
LoginFailureReason.ACCOUNT_LOCKED     # 账户被锁定
LoginFailureReason.TOO_MANY_ATTEMPTS  # 尝试次数过多
LoginFailureReason.MFA_FAILED         # MFA 验证失败
```

---

## 登录防护策略

框架内置两层防护，开箱即用，无需手动编码：

```
┌─────────────────────────────────────────────────────────────────────┐
│                        两层登录防护                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  第一层：IP 频率限制（LoginRateLimiter）← 主力防线                    │
│  ├── 同一 IP 连续失败 10 次 → 封锁该 IP 15 分钟                      │
│  ├── 不影响合法用户（只封攻击者的 IP）                                │
│  ├── 自动过期解封                                                    │
│  └── 错误提示包含剩余尝试次数                                        │
│                                                                     │
│  第二层：账户锁定（LockableMixin）← 安全网                           │
│  ├── 同一账户累计失败 20 次（跨 IP）→ 锁定账户 30 分钟               │
│  ├── 防御分布式攻击（攻击者换 IP 继续攻击同一账户）                   │
│  └── 到期自动解锁                                                    │
│                                                                     │
│  登录成功 → 同时重置 IP 计数和账户失败计数                            │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### 用户看到的提示

| 场景 | 返回消息 |
|------|---------|
| 密码错误（前几次） | `"用户名或密码错误，还可尝试7次"` |
| 同一 IP 达到阈值 | `"登录尝试次数过多，请15分钟后重试"` |
| 封锁期间再次尝试 | `"登录尝试次数过多，请X分钟后重试"` |
| 账户被锁定（分布式攻击触发） | `"用户名或密码错误"` + 内部记录 "账户已锁定" |
| 登录成功 | IP 计数归零，账户失败计数归零 |

### 配置

```python
auth = setup_auth(
    app=app,
    user_model=User,
    jwt_settings=settings.jwt,
    # IP 频率限制（一级防线）
    ip_max_attempts=10,         # 同一 IP 最多失败 10 次（默认 10，设 0 禁用）
    ip_block_minutes=15,        # 封锁 15 分钟（默认 15）
    # 账户锁定（二级防线，需 LockableMixin）
    max_login_attempts=20,      # 账户级别 20 次（默认 20）
    lock_duration_minutes=30,   # 锁定 30 分钟（默认 30）
)
```

### 为什么不只锁用户？

单纯锁定用户账户会被恶意利用：攻击者故意用错误密码尝试目标账户，导致合法用户被锁定，形成拒绝服务（DoS）。

IP 限制 + 账户锁定的组合策略：
- **单 IP 暴力破解**：第一层拦截，封锁 IP，用户完全不受影响
- **分布式攻击（多 IP 攻击同一账户）**：第二层拦截，账户临时锁定（阈值更高，正常用户不会触发）
- **密码喷射（同 IP 尝试多个账户）**：第一层拦截，IP 失败计数不区分用户名

### LoginRateLimiter 独立使用

也可以脱离 `setup_auth`，独立使用 IP 限制器：

```python
from yweb.auth import LoginRateLimiter

limiter = LoginRateLimiter(max_attempts=10, block_minutes=15)

# 检查 IP 是否被封锁
if limiter.is_blocked("192.168.1.100"):
    print("IP 已被封锁")

# 记录失败并获取剩余次数
was_blocked, remaining = limiter.record_failure("192.168.1.100")
print(f"剩余尝试次数: {remaining}")

# 登录成功时重置
limiter.reset("192.168.1.100")

# 手动解封（管理员操作）
limiter.unblock("192.168.1.100")

# 查看所有被封锁的 IP
blocked_ips = limiter.get_blocked_ips()
```

> **多实例部署**：默认使用内存存储，适合单实例。多实例部署可继承 `LoginRateLimiter`，用 Redis 替换存储。

---

## 用户安全 Mixins

提供账户锁定、密码管理等功能，可以直接混入用户模型。

### LockableMixin - 账户锁定

混入后，`BaseAuthService` 会**自动检测并启用**完整的锁定策略：

| 场景 | 自动行为 |
|------|---------|
| 密码错误（第 1~N-1 次） | 失败计数 +1，记录 "密码错误" |
| 密码错误达到阈值（第 N 次） | 自动锁定，记录 "账户已锁定（连续失败N次）" |
| 锁定期间再次登录 | 直接拒绝（不验密码），记录 "账户已锁定" |
| 锁定到期后登录 | 自动解锁，正常验证 |
| 登录成功 | 失败计数归零 |

> 作为二级防线，默认阈值为 20 次（比 IP 限制的 10 次更高），可通过 `setup_auth(max_login_attempts=20, lock_duration_minutes=30)` 配置。一般场景下，IP 频率限制已足够拦截暴力破解，账户锁定仅在分布式攻击时触发。

```python
from yweb.auth import LockableMixin, AbstractUser

class User(LockableMixin, AbstractUser):
    __tablename__ = "user"

# 获取用户
user = User.get(1)

# 手动锁定账户
user.lock(reason="可疑活动", duration_minutes=30)  # 锁定 30 分钟
user.lock(reason="违规操作")  # 永久锁定（需管理员解锁）

# 解锁账户
user.unlock()

# 检查账户状态
if not user.can_login:
    print("账户不可用")

if user.is_locked:
    print(f"锁定原因: {user.lock_reason}")
    print(f"锁定到: {user.locked_until}")

# 记录登录失败（超过阈值自动锁定）
is_locked = user.record_failed_login(
    max_attempts=5,           # 最多失败 5 次
    lock_duration_minutes=30  # 锁定 30 分钟
)

if is_locked:
    print("账户已被自动锁定")

# 登录成功时重置失败计数
user.reset_failed_attempts()

# 禁用/启用账户（与锁定不同）
user.disable()
user.enable()
```

### PasswordMixin - 密码管理

```python
from yweb.auth import PasswordMixin
from yweb.orm import BaseModel

class User(PasswordMixin, BaseModel):
    __tablename__ = "user"
    username = Column(String(255), unique=True)

user = User()

# 设置密码（默认使用 pbkdf2_sha256）
user.set_password("my_password")

# 验证密码
if user.verify_password("my_password"):
    print("密码正确")

# 检查密码是否需要升级（从旧算法升级到新算法）
if user.needs_password_rehash():
    user.rehash_password_if_needed("my_password")

# 检查密码是否过期
user.password_expires_days = 90  # 90 天过期
if user.is_password_expired:
    print("密码已过期，请修改")

# 要求用户修改密码
user.require_password_change()
if user.must_change_password:
    print("请修改密码")
```

### LastLoginMixin - 最后登录信息

```python
from yweb.auth import LastLoginMixin
from yweb.orm import BaseModel

class User(LastLoginMixin, BaseModel):
    __tablename__ = "user"
    username = Column(String(255), unique=True)

user = User.get(1)

# 更新最后登录信息
user.update_last_login(ip_address="192.168.1.100")

print(f"最后登录: {user.last_login_at}")
print(f"登录 IP: {user.last_login_ip}")
```

### FullUserMixin - 组合所有功能

```python
from yweb.auth import FullUserMixin
from yweb.orm import BaseModel

# FullUserMixin = LockableMixin + PasswordMixin + LastLoginMixin
class User(FullUserMixin, BaseModel):
    __tablename__ = "user"
    username = Column(String(255), unique=True)
    email = Column(String(255))

# 完整的登录流程
def login(username: str, password: str, ip_address: str):
    user = User.query.filter_by(username=username).first()
    
    if not user:
        audit_service.record_failure(username, ip_address, LoginFailureReason.INVALID_USERNAME)
        return None
    
    # 检查账户状态
    if not user.can_login:
        if user.is_locked:
            audit_service.record_failure(username, ip_address, LoginFailureReason.ACCOUNT_LOCKED)
        return None
    
    # 验证密码
    if not user.verify_password(password):
        is_locked = user.record_failed_login(max_attempts=5)
        audit_service.record_failure(username, ip_address, LoginFailureReason.INVALID_PASSWORD)
        return None
    
    # 登录成功
    user.reset_failed_attempts()
    user.update_last_login(ip_address=ip_address)
    audit_service.record_success(user.id, username, ip_address)
    
    return user
```

### RoleMixin - 角色管理

为用户模型提供角色相关的便捷方法。

**推荐**：使用 `setup_auth(User, role_model=True)` 自动注入，无需手动继承。

```python
# setup_auth 自动注入后即可使用：
user = User.get(1)

user.has_role("admin")              # 检查单个角色
user.has_any_role("admin", "mgr")   # 任一角色
user.has_all_roles("admin", "mgr")  # 所有角色

user.role_codes                     # {"admin", "user"}

user.add_role(admin_role)
user.remove_role(admin_role)
```

> 详细的角色模型定义和路由角色检查示例，请参阅 [角色管理 AbstractSimpleRole + RoleMixin](#角色管理-abstractsimplerole--rolemixin)。

### PasswordHelper - 密码工具类

`PasswordHelper` 是一个独立的密码工具类，不依赖 ORM，可在任何地方使用。

```python
from yweb.auth import PasswordHelper, PasswordTooShortError, PasswordTooLongError

# 配置（可选，通常在应用启动时配置一次）
# 如果不配置，将使用默认值
PasswordHelper.configure(
    min_length=6,      # 密码最小长度（默认 6）
    max_length=128,    # 密码最大长度（默认 128）
    md5_salt="..."     # 兼容旧 MD5 格式的盐值（默认 None，仅在需要兼容旧系统时设置）
)

# 哈希密码
hashed = PasswordHelper.hash("my_password")  # 使用 pbkdf2_sha256

# 验证密码（自动识别格式：pbkdf2、MD5、SHA256）
if PasswordHelper.verify("my_password", hashed):
    print("密码正确")

# 检查是否需要升级
if PasswordHelper.needs_rehash(old_hash):
    new_hash = PasswordHelper.hash(password)

# 密码长度验证
try:
    PasswordHelper.hash("abc")  # 太短，会抛异常
except PasswordTooShortError as e:
    print(e)  # "密码长度不能少于 6 个字符，当前 3 个字符"

try:
    PasswordHelper.hash("a" * 200)  # 太长，会抛异常
except PasswordTooLongError as e:
    print(e)  # "密码长度不能超过 128 个字符，当前 200 个字符"

# 跳过长度验证（特殊场景）
hashed = PasswordHelper.hash("abc", validate=False)
```

> **配置说明**：
> - `configure()` 方法是可选的，不调用时使用默认值（min_length=6, max_length=128, md5_salt=None）
> - `md5_salt` 参数仅在需要兼容旧系统的 MD5 密码时设置，新系统不需要
> - 配置后的参数会全局生效，建议在应用启动时配置一次

**便捷函数**（等价于调用 `PasswordHelper` 的方法）：

```python
from yweb.auth import hash_password, verify_password, needs_rehash

hashed = hash_password("password123")
is_valid = verify_password("password123", hashed)
need_upgrade = needs_rehash(old_hash)
```

---

## 统一认证管理

使用 `AuthManager` 统一管理多种认证方式：

```python
from yweb.auth import AuthManager, AuthType

# 创建管理器
auth_manager = AuthManager()

# 注册认证提供者
auth_manager.register_provider("jwt", jwt_auth_provider, is_default=True)
auth_manager.register_provider("api_key", api_key_provider)
auth_manager.register_provider("ldap", ldap_provider)

# 使用指定方式认证
result = auth_manager.authenticate("jwt", {
    "username": "admin",
    "password": "123456",
})

# 使用默认方式认证
result = auth_manager.authenticate_default(credentials)

# 验证 Token（自动尝试所有提供者）
result = auth_manager.validate_token(token)

if result.success:
    identity = result.identity
    print(f"用户: {identity.username}")
    print(f"角色: {identity.roles}")
    print(f"认证方式: {identity.auth_type}")
```

---

## 最佳实践

### 1. 密钥管理

```python
import os

# 从环境变量获取密钥
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

# 生产环境检查
if os.environ.get("ENV") == "production":
    assert SECRET_KEY != "dev-secret-key", "请设置生产环境密钥"
```

### 2. Token 过期与刷新配置

```python
# 推荐配置
jwt_manager = JWTManager(
    secret_key=SECRET_KEY,
    access_token_expire_minutes=30,       # 访问令牌：30分钟
    refresh_token_expire_days=7,          # 刷新令牌：7天
    refresh_token_sliding_days=2,         # Refresh Token 剩余 2 天时自动续期
)
```

### 3. Token 撤销策略

```python
# 生产环境使用 Redis 存储
if os.environ.get("ENV") == "production":
    import redis
    redis_client = redis.Redis.from_url(os.environ["REDIS_URL"])
    store = RedisTokenStore(redis_client)
else:
    store = InMemoryTokenStore()

configure_token_blacklist(store=store, jwt_manager=jwt_manager)

# 关键操作时撤销 Token
def change_password(user_id: int, new_password: str):
    # ... 修改密码逻辑
    
    # 撤销所有旧 Token，强制重新登录
    blacklist = get_token_blacklist()
    blacklist.revoke_all_user_tokens(user_id)
```

### 4. 安全 Cookie 设置

```python
set_session_cookie(
    response,
    session,
    httponly=True,   # 禁止 JS 访问
    secure=True,     # 仅 HTTPS
    samesite="lax",  # 防止 CSRF
)
```

### 5. 登录安全

```python
# 框架自动启用两层防护，只需配置参数
auth = setup_auth(
    app=app,
    user_model=User,                # User 已混入 LockableMixin
    # IP 频率限制（一级防线，防暴力破解，不影响合法用户）
    ip_max_attempts=10,             # 同一 IP 10 次失败后封锁（默认 10）
    ip_block_minutes=15,            # 封锁 15 分钟（默认 15）
    # 账户锁定（二级防线，防分布式攻击，阈值更高）
    max_login_attempts=20,          # 账户级别 20 次失败后锁定（默认 20）
    lock_duration_minutes=30,       # 锁定 30 分钟（默认 30）
)

# 密码错误时用户会看到：
# "用户名或密码错误，还可尝试7次"
# IP 被封锁时：
# "登录尝试次数过多，请15分钟后重试"
```

### 6. MFA 恢复码

- 为启用 MFA 的用户生成恢复码
- 提醒用户安全保存恢复码
- 恢复码使用后自动失效

### 7. YAML 配置示例

```yaml
# config/settings.yaml
jwt:
  secret_key: "${SECRET_KEY:dev-secret-key}"
  algorithm: "HS256"
  access_token_expire_minutes: 30
  refresh_token_expire_days: 7
  refresh_token_sliding_days: 2  # Refresh Token 滑动过期阈值
```

---

## 功能速查表

| 功能 | 类/函数 | 说明 |
|------|---------|------|
| **一站式认证设置** | **`setup_auth()`** | **一行完成认证配置 + 角色 + 路由挂载（推荐）** |
| 用户管理路由工厂 | `create_user_router()` | 生成用户 CRUD 路由（列表/创建/启用/禁用/重置密码等） |
| 登录记录路由工厂 | `create_login_record_router()` | 生成登录记录查询路由 |
| 认证服务 | `BaseAuthService` | 认证流程默认实现（认证/令牌/登出） |
| 认证服务接口 | `AbstractAuthService` | 认证服务抽象接口（完全自定义时实现） |
| 用户抽象模型 | `AbstractUser` | 用户基类，内置认证字段和 `create_user()`、`search()` 类方法 |
| 角色抽象模型 | `AbstractSimpleRole` | 轻量级角色管理基类 |
| 角色 Mixin | `RoleMixin` | 用户模型角色管理便捷方法 |
| 密码强度验证 | `PasswordValidator` | 支持 BASIC / MEDIUM / STRONG 三级 |
| 密码强度等级 | `PasswordStrength` | 枚举：BASIC / MEDIUM / STRONG |
| 用户名验证 | `UsernameValidator` | 用户名格式验证 |
| 密码工具 | `PasswordHelper` | 密码哈希/验证（独立于 ORM） |
| JWT 创建/验证 | `JWTManager` | Token 管理核心类 |
| 创建认证依赖 | `create_auth_dependency()` | 底层依赖工厂（需自定义时使用） |
| Refresh Token 滑动过期 | `jwt_manager.refresh_tokens()` | 换取 Token 时自动续期 |
| Token 撤销 | `TokenBlacklist` | 支持单个/用户级撤销 |
| 内存存储 | `InMemoryTokenStore` | 单实例部署 |
| Redis 存储 | `RedisTokenStore` | 多实例部署 |
| 登录审计 | `LoginAuditService` | 记录登录历史 |
| 登录记录模型 | `AbstractLoginRecord` | 登录审计记录基类 |
| **IP 频率限制** | **`LoginRateLimiter`** | **IP 封锁防暴力破解（一级防线）** |
| 账户锁定 | `LockableMixin` | 自动锁定/解锁（二级防线） |
| 密码管理 | `PasswordMixin` | 密码哈希/过期检查 |
| API Key | `APIKeyManager` | 服务间认证 |
| Session | `SessionManager` | Cookie 会话 |
| OAuth 2.0 | `OAuth2Manager` | 标准授权协议 |
| OIDC | `OIDCManager` | 身份认证 |
| MFA | `MFAManager` | 多因素认证 |
| LDAP | `LDAPManager` | 目录服务集成 |

---

## 下一步

- 查看 [OAuth 2.0 详细文档](oauth2_guide.md)
- 查看 [MFA 配置指南](mfa_guide.md)
- 查看 [完整示例](../examples/auth/)
- 查看 [权限控制指南](07_organization_guide.md)