# 认证流程详解

本文档详细说明 YWeb 的 JWT 认证流程，包括缓存优化和自动失效机制。

## 目录

- [整体流程概览](#整体流程概览)
- [核心组件](#核心组件)
- [认证流程详解](#认证流程详解)
- [缓存优化](#缓存优化)
- [FastAPI 依赖注入机制](#fastapi-依赖注入机制)
- [Token 验证详情](#token-验证详情)
- [auto_error 参数说明](#auto_error-参数说明)
- [完整时序图](#完整时序图)
- [代码实现参考](#代码实现参考)

---

## 整体流程概览

```
客户端请求                              服务器处理
   │                                       │
   │  Authorization: Bearer <token>        │
   ├──────────────────────────────────────►│
   │                                       │
   │                            ┌──────────▼──────────┐
   │                            │ 1. OAuth2PasswordBearer │
   │                            │    提取 Header 中的 Token │
   │                            └──────────┬──────────┘
   │                                       │
   │                            ┌──────────▼──────────┐
   │                            │ 2. jwt_manager.verify_token │
   │                            │    验证 Token 签名和有效期 │
   │                            └──────────┬──────────┘
   │                                       │
   │                            ┌──────────▼──────────┐
   │                            │ 3. 检查 token_type == "access" │
   │                            └──────────┬──────────┘
   │                                       │
   │                            ┌──────────▼──────────┐
   │                            │ 4. user_getter(user_id)    │
   │                            │    查缓存 → 未命中则查数据库 │
   │                            └──────────┬──────────┘
   │                                       │
   │                            ┌──────────▼──────────┐
   │                            │ 5. 返回 User 对象          │
   │                            │    注入到路由函数参数       │
   │                            └──────────┬──────────┘
   │                                       │
   │◄──────────────────────────────────────┤
   │            响应数据                    │
```

### 简化流程

```
请求 → 提取Token → 验证签名 → 检查类型 → 查询用户 → 注入参数 → 执行业务
         ↓           ↓           ↓           ↓
       失败?       失败?       失败?       失败?
         ↓           ↓           ↓           ↓
      返回401     返回401     返回401     返回401
```

---

## 核心组件

| 组件 | 作用 | 位置 |
|------|------|------|
| **`setup_auth()`** | **一站式认证设置（推荐）** | **`yweb.auth`** |
| `OAuth2PasswordBearer` | 从请求头提取 Token | FastAPI 内置 |
| `JWTManager` | 验证 Token 签名和有效期 | `yweb.auth` |
| `create_auth_dependency` | 创建认证依赖的工厂函数（底层） | `yweb.auth` |
| `@cached` | 缓存用户查询结果 | `yweb.cache` |
| `cache_invalidator` | 自动失效缓存 | `yweb.cache` |
| `user_getter` | 业务层提供的获取用户函数 | 业务代码 |

> **推荐**：大多数项目使用 `setup_auth()` 一行完成认证配置，自动处理 JWTManager 创建、用户缓存、缓存失效注册。详见 [认证指南 - 一站式认证设置](../06_auth_guide.md#一站式认证设置-setup_auth推荐)。以下内容帮助理解底层原理。

---

## 认证流程详解

### 第 1 层：OAuth2PasswordBearer（Token 提取器）

```python
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)
```

**作用：** FastAPI 内置的安全组件，负责：

| 功能 | 说明 |
|------|------|
| 提取 Token | 从 `Authorization: Bearer xxx` 头中提取 `xxx` |
| Swagger 集成 | 在 API 文档中自动生成「登录」按钮 |
| `tokenUrl` | 告诉 Swagger 登录接口在哪里 |
| `auto_error=False` | Token 不存在时返回 None，而不是直接报错 |

**工作原理：**
```
请求头: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
                              └──────────────────────────────────────┘
                                      OAuth2PasswordBearer 提取这部分
```

### 第 2 层：create_auth_dependency（依赖工厂）

> `setup_auth()` 内部自动调用此函数，通常无需手动使用。以下展示内部实现原理。

```python
def dependency(token: Optional[str] = Depends(oauth2_scheme)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭证",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    # 步骤 1: 检查 Token 是否存在
    if not token:
        if auto_error:
            raise credentials_exception
        return None
    
    # 步骤 2: 验证 Token（签名、过期时间等）
    token_data = jwt_manager.verify_token(token)
    if not token_data or not token_data.user_id:
        if auto_error:
            raise credentials_exception
        return None
    
    # 步骤 3: 检查 Token 类型必须是 access（不能用 refresh token 访问接口）
    if token_data.token_type != "access":
        if auto_error:
            raise credentials_exception
        return None
    
    # 步骤 4: 调用业务层函数获取用户（带缓存）
    user = user_getter(token_data.user_id)
    if not user:
        if auto_error:
            raise credentials_exception
        return None
    
    # 步骤 5: 返回用户对象
    return user
```

**每个步骤的意义：**

| 步骤 | 检查内容 | 失败原因示例 |
|------|----------|-------------|
| 1 | Token 是否存在 | 请求头没带 Authorization |
| 2 | Token 是否有效 | 签名错误、已过期、格式错误 |
| 3 | Token 类型检查 | 误用了 refresh_token |
| 4 | 用户是否存在 | 用户被删除、被禁用 |

### 第 3 层：user_getter（业务层策略）

```python
@cached(ttl=60, key_prefix="user:auth")
def get_user_by_id(user_id: int) -> Optional[User]:
    """通过用户 ID 获取用户（带缓存）"""
    user = User.get_by_id(user_id)
    if user and user.is_active:
        return user
    return None

# 注册自动缓存失效
cache_invalidator.register(User, get_user_by_id)
```

**这是业务层提供的「策略函数」，职责是：**
1. 根据 `user_id` 查缓存（命中则直接返回）
2. 缓存未命中则查数据库
3. 检查用户是否激活（`is_active`）
4. 返回用户对象或 None

### 模型兼容性说明

`cache_invalidator` 的自动失效功能对模型有一定要求：

| 场景 | 是否可用 | 需要做什么 |
|------|---------|-----------|
| 继承 CoreModel，主键是 `id` | ✅ 直接用 | 无需额外配置 |
| 继承 CoreModel，主键不是 `id` | ✅ 可用 | 自定义 `key_extractor` |
| 不继承 CoreModel 的 SQLAlchemy 模型 | ✅ 可用 | 自定义 `key_extractor` |
| 非 SQLAlchemy 模型 | ⚠️ 部分可用 | `@cached` 可用，自动失效不可用 |

**说明：**
- `@cached` 装饰器本身不依赖任何模型，可以缓存任意函数
- `cache_invalidator` 依赖 SQLAlchemy 事件机制，需要是 SQLAlchemy 模型
- 默认使用 `obj.id` 作为缓存键，如果主键不是 `id`，需要自定义 `key_extractor`

```python
# 主键不是 id 的情况
cache_invalidator.register(
    Product,
    get_product,
    key_extractor=lambda obj: obj.product_id  # 自定义键提取
)
```

---

## 缓存优化

### 无缓存时的问题

```
每次 API 请求：
  验证 JWT (内存计算，微秒级) → 查询数据库 (IO，毫秒级) → 执行业务
                                     ↑
                               高并发时成为瓶颈
```

### 加缓存后的流程

```
┌─────────────────────────────────────────────────────────────────┐
│                    认证流程（带缓存）                            │
└─────────────────────────────────────────────────────────────────┘

  请求到达
      │
      ▼
  JWT 验证 → 提取 user_id
      │
      ▼
  ┌─────────────────────────────────────┐
  │         user_getter(user_id)        │
  │  ┌────────────────────────────────┐ │
  │  │  1. 查询缓存                    │ │
  │  │     cache.get("user:auth:123") │ │
  │  └──────────────┬─────────────────┘ │
  │                 │                   │
  │      ┌──────────┴──────────┐        │
  │      │                     │        │
  │  命中 ▼                未命中 ▼       │
  │  ┌─────────┐         ┌─────────┐    │
  │  │ 返回    │         │ 查数据库 │    │
  │  │ 缓存值  │         │         │    │
  │  └─────────┘         └────┬────┘    │
  │                           │         │
  │                           ▼         │
  │                      写入缓存       │
  │                      TTL=60s        │
  │                           │         │
  │                           ▼         │
  │                       返回用户      │
  └─────────────────────────────────────┘
      │
      ▼
  注入到路由函数
      │
      ▼
  执行业务逻辑
```

### 自动缓存失效

```
┌─────────────────────────────────────────────────────────────┐
│                    自动缓存失效流程                          │
└─────────────────────────────────────────────────────────────┘

  业务代码                   SQLAlchemy                  缓存
      │                          │                        │
      │ user.name = "新名字"     │                        │
      │ user.update()            │                        │
      │─────────────────────────►│                        │
      │                          │                        │
      │                          │ 触发 after_update      │
      │                          │────────────────────────►
      │                          │                        │
      │                          │         自动调用        │
      │                          │  get_user_by_id.invalidate(user.id)
      │                          │                        │
      │                          │        缓存已删除       │
      │                          │                        │
      │   下次请求重新从数据库获取  │                        │
```

**自动失效触发点：**
- `after_update`: 用户信息更新后
- `after_delete`: 用户删除后

---

## FastAPI 依赖注入机制

当你这样写路由时：

```python
from yweb.response import Resp

@app.get("/me")
def get_me(user: User = Depends(get_current_user)):
    return Resp.OK({"id": user.id, "name": user.name})
```

**FastAPI 会自动执行：**

```
1. 收到 GET /me 请求
        │
        ▼
2. 发现参数 user 有 Depends(get_current_user)
        │
        ▼
3. 调用 get_current_user 函数
        │
        ├─► get_current_user 内部有 Depends(oauth2_scheme)
        │           │
        │           ▼
        │   从请求头提取 Token
        │           │
        │           ▼
        │   验证 Token → 获取 user_id
        │           │
        │           ▼
        │   调用 user_getter(user_id)
        │           │
        │           ├─► 查缓存（命中则返回）
        │           │
        │           ├─► 缓存未命中 → 查数据库
        │           │
        │           ▼
        │   返回 User 对象
        │
        ▼
4. 将 User 对象注入到路由函数的 user 参数
        │
        ▼
5. 执行路由函数逻辑
```

---

## Token 验证详情

### Token 结构（JWT）

```
eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTYiLCJ0eXBlIjoiYWNjZXNzIiwiZXhwIjoxNzA2MjAwMDAwfQ.签名
└─────────────────┘ └──────────────────────────────────────────────────────────────┘ └──┘
      Header                              Payload                                   Signature
```

### Payload 解码后

```json
{
  "sub": "123456",        // user_id
  "type": "access",       // token 类型
  "exp": 1706200000,      // 过期时间戳
  "roles": ["admin"]      // 可选：用户角色
}
```

### verify_token 的检查项

| 检查项 | 说明 |
|--------|------|
| ✅ 签名验证 | 防止篡改 |
| ✅ 过期检查 | `exp` 字段 |
| ✅ 黑名单检查 | 如果实现了登出功能 |

---

## auto_error 参数说明

| auto_error | Token 无效时的行为 | 使用场景 |
|------------|-------------------|----------|
| `True` | 抛出 401 HTTPException | 必须登录的接口 |
| `False` | 返回 `None` | 可选登录的接口 |

**代码对比：**

```python
from yweb.response import Resp

# 必须登录 - 未登录会报 401
@app.get("/profile")
def profile(user: User = Depends(get_current_user)):  # auto_error=True
    return Resp.OK(user)

# 可选登录 - 未登录返回 None
@app.get("/home")
def home(user: Optional[User] = Depends(get_current_user_optional)):  # auto_error=False
    if user:
        return Resp.OK({"greeting": f"欢迎, {user.name}"})
    return Resp.OK({"greeting": "欢迎, 游客"})
```

---

## 完整时序图

```
┌──────────┐    ┌────────────────┐    ┌─────────────┐    ┌──────────┐    ┌────────┐    ┌────────┐
│  Client  │    │ OAuth2Scheme   │    │ dependency  │    │ JWT验证   │    │  缓存   │    │ 数据库  │
└────┬─────┘    └───────┬────────┘    └──────┬──────┘    └────┬─────┘    └───┬────┘    └───┬────┘
     │                  │                    │                │              │              │
     │ GET /me          │                    │                │              │              │
     │ Authorization:   │                    │                │              │              │
     │ Bearer xxx       │                    │                │              │              │
     │─────────────────►│                    │                │              │              │
     │                  │                    │                │              │              │
     │                  │ token="xxx"        │                │              │              │
     │                  │───────────────────►│                │              │              │
     │                  │                    │                │              │              │
     │                  │                    │ verify(token)  │              │              │
     │                  │                    │───────────────►│              │              │
     │                  │                    │                │              │              │
     │                  │                    │ TokenData      │              │              │
     │                  │                    │ {user_id: 123} │              │              │
     │                  │                    │◄───────────────│              │              │
     │                  │                    │                │              │              │
     │                  │                    │ get_user(123)  │              │              │
     │                  │                    │────────────────────────────►  │              │
     │                  │                    │                │              │              │
     │                  │                    │           缓存命中?            │              │
     │                  │                    │                │              │              │
     │                  │                    │  ┌─── 命中 ───►│ 返回用户     │              │
     │                  │                    │  │             │              │              │
     │                  │                    │  │             │              │              │
     │                  │                    │  └─── 未命中 ──────────────────────────────► │
     │                  │                    │                │              │              │
     │                  │                    │                │              │ User 对象    │
     │                  │                    │◄───────────────────────────────────────────  │
     │                  │                    │                │              │              │
     │                  │                    │           写入缓存            │              │
     │                  │                    │────────────────────────────►  │              │
     │                  │                    │                │              │              │
     │                  │ User 对象          │                │              │              │
     │                  │◄───────────────────│                │              │              │
     │                  │                    │                │              │              │
     │ 响应数据          │                    │                │              │              │
     │◄─────────────────│                    │                │              │              │
     │                  │                    │                │              │              │
```

---

## 代码实现参考

### 完整的 dependencies.py（推荐方式：setup_auth）

```python
"""
API 依赖模块

使用 yweb.auth.setup_auth 一站式设置认证依赖，
自动完成 JWT 管理器创建、用户查询缓存、缓存失效注册。

使用方式：
    from app.api.dependencies import auth
    
    # 路由级别认证
    router = APIRouter(dependencies=[Depends(auth.get_current_user)])
"""

from fastapi import Depends, HTTPException, status

from app.domain.auth.model.user import User  # 继承自 AbstractUser 的项目用户模型
from app.config import settings
from yweb.auth import setup_auth

# ==================== 一站式认证设置 ====================

auth = setup_auth(User, jwt_settings=settings.jwt, token_url="/api/v1/auth/token")


# ==================== 角色检查器 ====================

def require_admin(user: User = Depends(auth.get_current_user)) -> User:
    """要求管理员角色"""
    if not user.has_role("admin"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限"
        )
    return user


def require_roles(*roles: str):
    """要求指定角色之一"""
    def checker(user: User = Depends(auth.get_current_user)) -> User:
        if not any(user.has_role(role) for role in roles):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"需要以下角色之一: {', '.join(roles)}"
            )
        return user
    return checker
```

<details>
<summary>手动方式（需要完全自定义时）</summary>

```python
"""
API 依赖模块（手动方式）

使用 yweb.auth 提供认证依赖，结合 yweb.cache 提供缓存和自动失效。
仅在需要完全自定义认证逻辑时使用此方式。
"""

from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer

from app.domain.auth.model.user import User
from app.services.jwt_service import jwt_manager
from yweb.auth import create_auth_dependency
from yweb.cache import cached, cache_invalidator


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/token")


@cached(ttl=60, key_prefix="user:auth")
def get_user_by_id(user_id: int) -> Optional[User]:
    user = User.get_by_id(user_id)
    if user and user.is_active:
        return user
    return None


cache_invalidator.register(User, get_user_by_id)


get_current_user = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=True,
)

get_current_user_optional = create_auth_dependency(
    jwt_manager=jwt_manager,
    user_getter=get_user_by_id,
    auto_error=False,
)
```
</details>

### 路由中使用

```python
from fastapi import APIRouter, Depends
from typing import Optional
from app.api.dependencies import auth, require_admin
from app.domain.auth.model.user import User
from yweb.response import Resp

router = APIRouter()

@router.get("/me")
def get_me(user: User = Depends(auth.get_current_user)):
    """获取当前用户信息（必须登录）"""
    return Resp.OK({"id": user.id, "name": user.name})


@router.get("/home")
def home(user: Optional[User] = Depends(auth.get_current_user_optional)):
    """首页（可选登录）"""
    if user:
        return Resp.OK({"greeting": f"欢迎回来, {user.name}"})
    return Resp.OK({"greeting": "欢迎, 游客"})


@router.get("/admin/dashboard")
def admin_dashboard(user: User = Depends(require_admin)):
    """管理后台（需要管理员权限）"""
    return Resp.OK(message="Welcome to admin dashboard")
```

---

## 总结

整个认证过程是一条**责任链**：

```
请求 → 提取Token → 验证签名 → 检查类型 → 查询用户(带缓存) → 注入参数 → 执行业务
                                              │
                                              ├─ 缓存命中：微秒级返回
                                              └─ 缓存未命中：查数据库，写缓存
```

**设计优点：**

| 特性 | 说明 |
|------|------|
| 分层清晰 | yweb 处理通用逻辑，业务层只提供「如何获取用户」 |
| 高性能 | 缓存减少数据库查询，高并发下优势明显 |
| 自动一致 | `cache_invalidator` 保证数据变更时缓存自动失效 |
| 低侵入 | 业务代码无需关心缓存失效，ORM 操作自动触发 |
| 可扩展 | 支持内存缓存和 Redis 缓存，多实例部署友好 |
