# YWeb 异常处理完全指南

本指南介绍如何使用 YWeb 框架的异常处理机制，实现友好的错误提示和完整的异常堆栈记录。

---

## 目录

- [快速开始](#快速开始)
- [核心特性](#核心特性)
- [错误代码枚举](#错误代码枚举)
- [Err 快捷类（推荐）](#err-快捷类推荐) ⭐ 新增
- [业务异常类（高级用法）](#业务异常类高级用法)
- [模块专用异常（基础设施层）](#模块专用异常基础设施层)
- [异常类速查表](#异常类速查表)
- [使用示例](#使用示例)
- [常用代码片段](#常用代码片段)
- [最佳实践](#最佳实践)
- [内部异常外部传播](#内部异常外部传播)
- [响应格式](#响应格式)
- [日志记录](#日志记录)
- [调试技巧](#调试技巧)
- [测试示例](#测试示例)
- [从旧代码迁移](#从旧代码迁移)
- [常见问题](#常见问题)
- [验证错误翻译器](#验证错误翻译器)
- [验证约束模块（类似 .NET MVC 特性）](#验证约束模块类似-net-mvc-特性)
- [总结](#总结)

---

## 快速开始

### 1️⃣ 注册全局异常处理器

在 FastAPI 应用启动时注册异常处理器：

```python
from fastapi import FastAPI
from yweb import register_exception_handlers

app = FastAPI()

# 注册全局异常处理器（必须在路由注册之前）
register_exception_handlers(app)
```

### 2️⃣ 在业务代码中抛出异常（推荐使用 Err）

```python
from fastapi import APIRouter
from yweb import OK, Err

router = APIRouter()

@router.post("/login")
def login(username: str, password: str):
    """用户登录 - 无需 try-catch"""
    user = authenticate(username, password)

    if not user:
        # 直接抛出异常，全局处理器会自动转换为 JSON 响应
        raise Err.auth("用户名或密码错误")

    token = create_token(user)
    return OK(token, "登录成功")
```

> **推荐使用 `Err` 快捷类**：只需导入一个类，IDE 自动补全所有异常方法，无需记忆多个异常类名。

### 4️⃣ 自动获得统一的错误响应

```json
{
    "status": "error",
    "message": "用户名或密码错误",
    "msg_details": [],
    "data": {},
    "error_code": "AUTHENTICATION_FAILED"
}
```

---

## 核心特性

| 功能 | 说明 |
|------|------|
| **全局异常处理** | 自动捕获所有异常，转换为统一 JSON 响应 |
| **完整堆栈记录** | 日志中记录完整的异常堆栈信息 |
| **业务逻辑清晰** | 无需 try-catch，代码简洁易读 |
| **友好错误提示** | 用户看到友好的错误消息 |
| **详细开发信息** | 开发人员获得完整的调试信息 |
| **统一响应格式** | 所有错误响应格式一致 |
| **参数验证优化** | Pydantic 验证错误自动转换为友好消息 |

---

## 错误代码枚举

YWeb 提供了 `ErrorCode` 枚举类，用于定义标准化的错误代码，支持 IDE 补全和拼写检查。

### 基本用法

```python
from yweb import ErrorCode, AuthorizationException

# ✅ 使用枚举（推荐）- 有 IDE 补全，防止拼写错误
raise AuthorizationException(
    "需要管理员权限",
    code=ErrorCode.ADMIN_REQUIRED
)

# ✅ 枚举值可以直接比较
if error_code == ErrorCode.TOKEN_EXPIRED:
    refresh_token()
```

### 内置错误代码

| 分类 | 错误代码 | 说明 |
|------|---------|------|
| **通用** | `BUSINESS_ERROR` | 通用业务错误 |
| | `OPERATION_FAILED` | 操作失败 |
| | `INTERNAL_SERVER_ERROR` | 服务器内部错误 |
| **认证 (401)** | `AUTHENTICATION_FAILED` | 认证失败 |
| | `INVALID_CREDENTIALS` | 凭证无效 |
| | `INVALID_TOKEN` | Token 无效 |
| | `TOKEN_EXPIRED` | Token 已过期 |
| | `TOKEN_REVOKED` | Token 已撤销 |
| **授权 (403)** | `AUTHORIZATION_FAILED` | 授权失败 |
| | `PERMISSION_DENIED` | 权限不足 |
| | `ADMIN_REQUIRED` | 需要管理员权限 |
| | `ROLE_REQUIRED` | 需要特定角色 |
| **资源 (404)** | `RESOURCE_NOT_FOUND` | 资源不存在 |
| | `USER_NOT_FOUND` | 用户不存在 |
| | `ORDER_NOT_FOUND` | 订单不存在 |
| **冲突 (409)** | `RESOURCE_CONFLICT` | 资源冲突 |
| | `DUPLICATE_ENTRY` | 重复记录 |
| | `VERSION_CONFLICT` | 版本冲突 |
| | `USERNAME_EXISTS` | 用户名已存在 |
| | `EMAIL_EXISTS` | 邮箱已存在 |
| **验证 (422)** | `VALIDATION_ERROR` | 验证错误 |
| | `INVALID_FORMAT` | 格式无效 |
| | `INVALID_PARAMETER` | 参数无效 |
| **服务 (503)** | `SERVICE_UNAVAILABLE` | 服务不可用 |
| | `DATABASE_ERROR` | 数据库错误 |
| | `EXTERNAL_SERVICE_ERROR` | 外部服务错误 |
| **业务** | `INSUFFICIENT_BALANCE` | 余额不足 |
| | `PAYMENT_FAILED` | 支付失败 |
| | `ORDER_CREATE_FAILED` | 订单创建失败 |
| | `RATE_LIMIT_EXCEEDED` | 超出速率限制 |

### 扩展自定义错误代码

应用层可以通过以下方式扩展自定义错误代码：

**方式 1: 定义应用层枚举（推荐）**

```python
from enum import Enum
from yweb import BusinessException

class AppErrorCode(str, Enum):
    """应用自定义错误代码"""
    ORDER_EXPIRED = "ORDER_EXPIRED"
    INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
    PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
    COUPON_INVALID = "COUPON_INVALID"
    COUPON_EXPIRED = "COUPON_EXPIRED"

# 使用自定义错误代码
raise BusinessException(
    "订单已过期",
    code=AppErrorCode.ORDER_EXPIRED
)
```

**方式 2: 直接使用字符串（简单场景）**

```python
# 对于一次性使用的错误代码，可以直接使用字符串
raise BusinessException(
    "自定义错误",
    code="MY_CUSTOM_ERROR"
)
```

### 为什么使用枚举？

| 对比 | 硬编码字符串 | ErrorCode 枚举 |
|------|------------|----------------|
| IDE 补全 | ❌ 无 | ✅ 有 |
| 拼写检查 | ❌ 无 | ✅ 编译时检查 |
| 统一管理 | ❌ 分散各处 | ✅ 集中定义 |
| 重构支持 | ❌ 难 | ✅ 易 |

---

## Err 快捷类（推荐）

`Err` 是异常快捷创建类，只需导入一个类，即可通过 IDE 自动补全发现所有可用的异常类型。

### 基本用法

```python
from yweb import Err

# 认证失败 (401)
raise Err.auth("用户名或密码错误")

# 权限不足 (403)
raise Err.forbidden("需要管理员权限")

# 资源不存在 (404)
raise Err.not_found("用户不存在", resource_type="User", resource_id=123)

# 资源冲突 (409)
raise Err.conflict("用户名已被使用", field="username", value="admin")

# 数据验证失败 (422)
raise Err.invalid("数据验证失败", details=["用户名长度必须在3-20个字符之间"])

# 服务不可用 (503)
raise Err.unavailable("数据库连接失败")

# 通用业务异常 (400)
raise Err.fail("操作失败")
```

### Err 方法速查表

| 方法 | HTTP 状态码 | 使用场景 |
|------|------------|---------|
| `Err.auth()` | 401 | 登录失败、Token 无效/过期 |
| `Err.forbidden()` | 403 | 权限不足、需要更高角色 |
| `Err.not_found()` | 404 | 资源不存在 |
| `Err.conflict()` | 409 | 资源已存在、版本冲突 |
| `Err.invalid()` | 422 | 数据验证失败 |
| `Err.unavailable()` | 503 | 服务不可用 |
| `Err.fail()` | 400 | 通用业务异常 |

### 支持自定义错误码

```python
from yweb import Err, ErrorCode

# 使用预定义的错误码
raise Err.auth("Token已过期", code=ErrorCode.TOKEN_EXPIRED)

# 使用自定义错误码
raise Err.fail("订单已过期", code="ORDER_EXPIRED")
```

### 为什么推荐使用 Err？

| 对比 | 传统方式 | Err 快捷类 |
|------|---------|-----------|
| 导入 | 需要导入多个异常类 | 只需 `from yweb import Err` |
| 记忆 | 需要记住类名 | IDE 自动补全 |
| 代码量 | 较长 | 简洁 |
| 可读性 | 一般 | 更直观 |

---

## 业务异常类（高级用法）

> 以下异常类主要用于：类型检查、自定义异常继承、单元测试。日常使用推荐 `Err` 快捷类。

### 异常类层次结构

```
BusinessException (基类)
├── AuthenticationException (认证异常)
├── AuthorizationException (授权异常)
├── ResourceNotFoundException (资源不存在)
├── ResourceConflictException (资源冲突)
├── ValidationException (数据验证失败)
└── ServiceUnavailableException (服务不可用)
```

### 1. BusinessException (业务异常基类)

所有业务异常的基类，可以直接使用或继承。

```python
from yweb import BusinessException

# 基本使用
raise BusinessException("操作失败")

# 带错误代码
raise BusinessException("操作失败", code="OPERATION_FAILED")

# 带详细信息
raise BusinessException(
    message="数据验证失败",
    code="VALIDATION_ERROR",
    details=["字段1不能为空", "字段2格式错误"]
)

# 带额外上下文
raise BusinessException(
    message="订单创建失败",
    code="ORDER_CREATE_FAILED",
    extra={"order_id": 12345, "reason": "库存不足"}
)
```

**参数说明:**
- `message`: 错误消息（面向用户）
- `code`: 错误代码（用于程序判断，默认 "BUSINESS_ERROR"）
- `status_code`: HTTP 状态码（默认 400）
- `details`: 详细错误信息列表
- `**extra`: 额外的上下文信息（调试模式下会返回给前端）

### 2. AuthenticationException (认证异常)

用户认证失败时使用，HTTP 状态码 401。

```python
from yweb import AuthenticationException

# 登录失败
raise AuthenticationException("用户名或密码错误")

# Token 无效
raise AuthenticationException("无效的访问令牌", code="INVALID_TOKEN")

# Token 过期
raise AuthenticationException("访问令牌已过期", code="TOKEN_EXPIRED")
```

### 3. AuthorizationException (授权异常)

用户权限不足时使用，HTTP 状态码 403。

```python
from yweb import AuthorizationException

# 权限不足
raise AuthorizationException("您没有权限执行此操作")

# 角色不匹配
raise AuthorizationException(
    "需要管理员权限",
    code="ADMIN_REQUIRED",
    details=["当前角色: user", "需要角色: admin"]
)
```

### 4. ResourceNotFoundException (资源不存在)

请求的资源不存在时使用，HTTP 状态码 404。

```python
from yweb import ResourceNotFoundException

# 用户不存在
raise ResourceNotFoundException(
    "用户不存在",
    resource_type="User",
    resource_id=123
)

# 订单不存在
raise ResourceNotFoundException(
    "订单不存在",
    code="ORDER_NOT_FOUND",
    resource_type="Order",
    resource_id="ORD123456"
)
```

### 5. ResourceConflictException (资源冲突)

资源已存在或发生冲突时使用，HTTP 状态码 409。

```python
from yweb import ResourceConflictException

# 用户名已存在
raise ResourceConflictException(
    "用户名已被使用",
    field="username",
    value="admin"
)

# 数据版本冲突
raise ResourceConflictException(
    "数据已被其他用户修改",
    code="VERSION_CONFLICT",
    details=["请刷新后重试"]
)
```

### 6. ValidationException (数据验证异常)

数据验证失败时使用，HTTP 状态码 422。

```python
from yweb import ValidationException

# 单个字段验证失败
raise ValidationException("手机号格式不正确", field="phone")

# 多个字段验证失败
raise ValidationException(
    "数据验证失败",
    details=[
        "用户名长度必须在3-20个字符之间",
        "密码必须包含字母和数字"
    ]
)
```

### 7. ServiceUnavailableException (服务不可用)

依赖的服务不可用时使用，HTTP 状态码 503。

```python
from yweb import ServiceUnavailableException

# 数据库连接失败
raise ServiceUnavailableException("数据库连接失败", service="database")

# 第三方API不可用
raise ServiceUnavailableException(
    "支付服务暂时不可用",
    code="PAYMENT_SERVICE_DOWN",
    service="payment_gateway"
)
```

---

## 模块专用异常（基础设施层）

框架中各基础设施模块有独立的异常基类，**不继承 BusinessException**：

| 模块 | 基类 | 典型异常 | 说明 |
|------|------|---------|------|
| 存储模块 | `StorageError` | `FileTooLarge`, `InvalidFileType` | 文件上传、存储配额、文件验证等 |
| 事务模块 | `TransactionError` | `TransactionNotActiveError`, `SavepointError` | 事务状态、保存点、传播行为等 |
| 状态机模块 | `StateMachineError` | `InvalidTransitionError`, `TransitionGuardError` | 状态转换、守卫条件等 |
| 权限模块 | `PermissionException` | `PermissionDeniedException`, `RoleNotFoundException` | 继承自 BusinessException |

### 设计说明

**为什么存储/事务/状态机异常不继承 BusinessException？**

1. **职责分离** - 这些是**基础设施层**的技术异常，不应直接暴露给用户
2. **模块解耦** - 基础设施模块不强制依赖核心异常体系
3. **转换原则** - 应在服务层捕获并转换为业务异常或 ValueError

### 处理方式

```python
# 服务层捕获技术异常并转换为业务异常
from yweb.storage.exceptions import FileTooLarge, InvalidFileType

def upload_avatar(self, file):
    try:
        return storage.save(file)
    except FileTooLarge as e:
        raise ValueError(f"文件过大，最大允许 {e.details['max_size']} 字节")
    except InvalidFileType as e:
        raise ValueError(f"不支持的文件类型: {e.details.get('actual_type')}")
```

### 全局异常处理器行为

| 异常类型 | 处理方式 |
|---------|---------|
| `BusinessException` 及其子类 | 按异常定义的 `status_code` 返回 |
| `ValueError` | 返回 400 BadRequest |
| 其他未捕获异常（包括模块专用异常） | 返回 500 Internal Server Error |

> **注意**：未在服务层转换的模块专用异常会被全局处理器捕获并返回 500，同时记录完整的错误日志便于排查。

---

## 异常类速查表

| 异常类 | 状态码 | 使用场景 | 示例 |
|--------|--------|---------|------|
| `AuthenticationException` | 401 | 登录失败、Token无效 | `raise AuthenticationException("用户名或密码错误")` |
| `AuthorizationException` | 403 | 权限不足 | `raise AuthorizationException("需要管理员权限")` |
| `ResourceNotFoundException` | 404 | 资源不存在 | `raise ResourceNotFoundException("用户不存在")` |
| `ResourceConflictException` | 409 | 资源已存在、冲突 | `raise ResourceConflictException("用户名已被使用")` |
| `ValidationException` | 422 | 数据验证失败 | `raise ValidationException("邮箱格式不正确")` |
| `ServiceUnavailableException` | 503 | 服务不可用 | `raise ServiceUnavailableException("数据库连接失败")` |
| `BusinessException` | 400 | 其他业务错误 | `raise BusinessException("操作失败")` |

---

## 使用示例

### 示例 1: 用户登录（认证）

**❌ 改进前（47 行代码）- 过时写法，不推荐：**

> ⚠️ 以下是**旧的、过时的写法**，仅用于对比展示。新项目请使用"改进后"的写法。

```python
@router.post("/login")
def login(request: Request, login_request: LoginRequest):
    client_ip = request.client.host if request.client else "未知"
    user_agent = request.headers.get("User-Agent", "未知")

    logger.debug(f"客户端信息: IP={client_ip}, User-Agent={user_agent}")

    auth_app_service = AuthApplicationService(
        auth_service=AuthServiceImpl(),
        token_repository=TokenService()
    )
    result = auth_app_service.login(
        login_request.username,
        login_request.password,
        client_ip,
        user_agent
    )

    # ❌ 问题：在 API 层手动检查错误并返回响应
    # ❌ 问题：需要手动记录日志
    # ❌ 问题：代码冗长，充斥着错误处理逻辑
    if isinstance(result, dict) and "error" in result:
        error_type = result["error"]
        if error_type == "invalid_credentials":
            logger.warning("登录失败: 用户名或密码错误")
            return Unauthorized("用户名或密码错误")
        elif error_type == "system_error":
            logger.error(f"系统登录接口错误: {result.get('message', '未知系统错误')}")
            return InternalServerError("系统登录接口错误")
        else:
            logger.error(f"未知错误类型: {error_type}")
            return InternalServerError("登录过程中发生未知错误")

    if not result:
        logger.warning("登录失败: 用户名或密码错误")
        return Unauthorized("用户名或密码错误")

    logger.debug("登录成功，返回结果")
    return OK(result, "登录成功")
```

**✅ 改进后（15 行代码）- 推荐写法：**

```python
from yweb import OK, AuthenticationException

@router.post("/login")
def login(request: Request, login_request: LoginRequest):
    """用户登录 - 简洁清晰"""
    client_ip = request.client.host if request.client else "未知"
    user_agent = request.headers.get("User-Agent", "未知")

    auth_service = AuthServiceImpl()

    # 直接调用，异常会被全局处理器捕获
    # 常会被自动记录到日志
    user = auth_service.authenticate(
        login_request.username,
        login_request.password
    )

    if not user:
        # 抛出异常，自动转换为 JSON 响应
        raise AuthenticationException("用户名或密码错误")

    token = auth_service.create_token(user, client_ip, user_agent)
    return OK(token, "登录成功")
```

**代码减少了 68%，逻辑更清晰！**

### 示例 2: 获取用户信息（资源查询）

```python
from yweb import OK, ResourceNotFoundException

@router.get("/users/{user_id}")
def get_user(user_id: int):
    """获取用户信息"""
    user = User.get_by_id(user_id)

    if not user:
        raise ResourceNotFoundException(
            "用户不存在",
            resource_type="User",
            resource_id=user_id
        )

    return OK(user, "获取成功")
```

### 示例 3: 创建用户（资源冲突）

```python
from yweb import OK, ResourceConflictException, ValidationException

@router.post("/users")
def create_user(user_data: UserCreateRequest):
    """创建用户"""
    # 检查用户名是否已存在
    existing_user = User.get_by_username(user_data.username)
    if existing_user:
        raise ResourceConflictException(
            "用户名已被使用",
            field="username",
            value=user_data.username
        )

    # 检查邮箱格式
    if not is_valid_email(user_data.email):
        raise ValidationException(
            "邮箱格式不正确",
            field="email",
            value=user_data.email
        )

    # 创建用户
    user = User.create(**user_data.dict())
    return OK(user, "创建成功")
```

### 示例 4: 权限检查（授权）

```python
from yweb import OK, AuthorizationException

@router.delete("/users/{user_id}")
def delete_user(user_id: int, current_user: User = Depends(get_current_user)):
    """删除用户 - 需要管理员权限"""
    if not current_user.is_admin:
        raise AuthorizationException(
            "需要管理员权限",
            code="ADMIN_REQUIRED",
            details=[
                f"当前角色: {current_user.role}",
                "需要角色: admin"
            ]
        )

    user = User.get_by_id(user_id)
    if not user:
        raise ResourceNotFoundException("用户不存在")

    user.delete()
    return OK(message="删除成功")
```

### 示例 5: Service 层异常处理

**❌ 改进前（使用字典返回错误）- 过时写法，不推荐：**

> ⚠️ 以下是**旧的、过时的写法**，仅用于对比展示。

```python
class AuthService:
    def login(self, username: str, password: str):
        """登录 - 返回字典表示错误"""
        user = self.user_repository.find_by_username(username)
        if not user:
            return {"error": "invalid_credentials"}  # ❌ 返回错误字典

        if not self.verify_password(password, user.password_hash):
            return {"error": "invalid_credentials"}  # ❌ 返回错误字典

        try:
            token = self.create_token(user)
            return {"token": token, "user": user}
        except Exception as e:
            return {"error": "system_error", "message": str(e)}  # ❌ 吞掉异常
```

**✅ 改进后（使用异常）- 推荐写法：**

```python
from yweb import AuthenticationException

class AuthService:
    def login(self, username: str, password: str):
        """登录 - 抛出异常"""
        user = self.user_repository.find_by_username(username)
        if not user:
            raise AuthenticationException("用户名或密码错误")

        if not self.verify_password(password, user.password_hash):
            raise AuthenticationException("用户名或密码错误")

        # 不需要 try-catch，异常会自动向上传播
        token = self.create_token(user)
        return {"token": token, "user": user}
```

---

## 常用代码片段

> 推荐使用 `Err` 快捷类，代码更简洁。

### 认证失败

```python
# 推荐方式
if not user or not verify_password(password, user.password_hash):
    raise Err.auth("用户名或密码错误")

# 传统方式
raise AuthenticationException("用户名或密码错误")
```

### 权限检查

```python
# 推荐方式
if not current_user.is_admin:
    raise Err.forbidden("需要管理员权限")

# 传统方式
raise AuthorizationException("需要管理员权限", code="ADMIN_REQUIRED")
```

### 资源不存在

```python
# 推荐方式
user = User.get_by_id(user_id)
if not user:
    raise Err.not_found("用户不存在", resource_type="User", resource_id=user_id)

# 传统方式
raise ResourceNotFoundException("用户不存在", resource_type="User", resource_id=user_id)
```

### 资源冲突

```python
# 推荐方式
if User.get_by_username(username):
    raise Err.conflict("用户名已被使用", field="username", value=username)

# 传统方式
raise ResourceConflictException("用户名已被使用", field="username", value=username)
```

### 数据验证

```python
# 推荐方式
if not is_valid_email(email):
    raise Err.invalid("邮箱格式不正确", field="email")

# 带详细信息
raise Err.invalid("数据验证失败", details=[
    "用户名长度必须在3-20个字符之间",
    "密码必须包含字母和数字"
])
```

### 服务不可用

```python
# 推荐方式
raise Err.unavailable("数据库连接失败", service="database")
```

### 通用业务异常

```python
# 推荐方式
raise Err.fail("操作失败", order_id=12345, reason="库存不足")

# 传统方式
raise BusinessException("操作失败", code="ORDER_CREATE_FAILED", order_id=12345)
```

### 带自定义错误码

```python
from yweb import Err, ErrorCode

# 使用预定义错误码
raise Err.auth("访问令牌已过期", code=ErrorCode.TOKEN_EXPIRED)

# 使用自定义错误码
raise Err.fail("订单已过期", code="ORDER_EXPIRED")
```

---

## 最佳实践

### 1. 异常分层原则

```
Controller 层: 只捕获需要特殊处理的异常，其他交给全局处理器
Service 层: 抛出业务异常，不返回错误字典
Repository 层: 抛出数据访问异常
```

### 2. 选择合适的异常类型

| 场景 | 使用的异常 | HTTP 状态码 |
|------|-----------|------------|
| 登录失败 | AuthenticationException | 401 |
| 权限不足 | AuthorizationException | 403 |
| 资源不存在 | ResourceNotFoundException | 404 |
| 资源已存在 | ResourceConflictException | 409 |
| 参数验证失败 | ValidationException | 422 |
| 服务不可用 | ServiceUnavailableException | 503 |
| 其他业务错误 | BusinessException | 400 |

### 3. 提供详细的错误信息

```python
# ❌ 不好 - 信息不够详细
raise ValidationException("验证失败")

# ✅ 好 - 提供详细信息
raise ValidationException(
    "数据验证失败",
    details=[
        "用户名长度必须在3-20个字符之间",
        "密码必须包含字母和数字",
        "邮箱格式不正确"
    ]
)
```

### 4. 使用错误代码便于程序判断

```python
# ✅ 使用错误代码
raise AuthenticationException(
    "访问令牌已过期",
    code="TOKEN_EXPIRED"
)

# 前端可以根据 error_code 做特殊处理
if (response.error_code === "TOKEN_EXPIRED") {
    // 自动刷新 token
    refreshToken();
}
```

### 5. 不要过度捕获异常

```python
# ❌ 不要这样做 - 吞掉所有异常
try:
    result = some_function()
except Exception:
    pass  # 什么都不做

# ✅ 应该这样做 - 让异常向上传播
def some_function():
    # 不需要 try-catch
    user = User.get_by_id(user_id)
    if not user:
        raise ResourceNotFoundException("用户不存在")
    return user
```

### 6. 推荐做法 vs 不推荐做法

**✅ 推荐做法**

```python
# ✅ 直接抛出异常
def login(username, password):
    if not user:
        raise AuthenticationException("用户名或密码错误")
    return user

# ✅ 无需 try-catch
@router.post("/login")
def login_endpoint(username: str, password: str):
    user = login(username, password)
    return OK(user)

# ✅ 提供详细信息
raise ValidationException(
    "数据验证失败",
    details=["字段1错误", "字段2错误"]
)

# ✅ 使用错误代码
raise AuthenticationException(
    "令牌已过期",
    code="TOKEN_EXPIRED"
)
```

**❌ 不推荐做法**

```python
# ❌ 返回错误字典
def login(username, password):
    if not user:
        return {"error": "invalid_credentials"}
    return user

# ❌ 过度使用 try-catch
@router.post("/login")
def login_endpoint(username: str, password: str):
    try:
        user = login(username, password)
        return OK(user)
    except Exception as e:
        return InternalServerError(str(e))

# ❌ 吞掉异常
try:
    result = some_function()
except Exception:
    pass  # 什么都不做

# ❌ 信息不够详细
raise ValidationException("验证失败")
```

---

## 内部异常外部传播

### 问题定义

**内部异常外部传播**指的是：当内部系统（数据库、第三方API、文件系统等）发生异常时，如何安全、规范地将异常信息传播到外部（用户/前端），同时满足：

1. **对用户友好** - 隐藏技术细节和敏感信息
2. **对开发有用** - 保留完整的调试信息
3. **安全可控** - 不泄露系统内部结构

### 常见问题

#### 问题 1: 直接暴露内部异常

```python
# ❌ 问题代码 - 直接重新抛出原始异常
try:
    user = User.get_by_id(user_id)
except Exception as e:
    raise e  # 直接抛出，可能暴露敏感信息
```

当数据库连接失败时，用户会看到：

```json
{
    "status": "error",
    "message": "FATAL: password authentication failed for user \"postgres\"",
    "error_code": "INTERNAL_SERVER_ERROR"
}
```

**暴露的问题：**
- ❌ 暴露了数据库用户名 `postgres`
- ❌ 暴露了使用的数据库类型
- ❌ 暴露了认证失败的技术细节
- ❌ 用户无法理解这个错误

#### 问题 2: 吞掉异常，返回 None

```python
# ❌ 问题代码 - 吞掉所有异常
def get_user_by_username(username: str):
    try:
        user = User.get_by_username(username)
        return user
    except Exception:
        return None  # 吞掉异常，丢失错误信息
```

**问题分析：**
- ❌ 无法区分"用户不存在"和"数据库连接失败"
- ❌ 调用者无法知道发生了什么错误
- ❌ 日志中没有记录异常信息
- ❌ 问题难以排查

#### 问题 3: 使用通用的 HTTPException

```python
# ❌ 问题代码 - 使用通用异常
from fastapi import HTTPException

try:
    result = database.query(sql)
except Exception as e:
    raise HTTPException(
        status_code=500,
        detail=str(e)  # 直接暴露原始错误消息
    )
```

#### 问题 4: 异常链丢失

```python
# ❌ 问题代码 - 丢失异常链
try:
    result = third_party_api.call()
except RequestException as e:
    # 创建新异常，但没有保留原始异常
    raise BusinessException("API调用失败")
```

### 解决方案

#### 方案 1: 异常转换与包装

```python
from yweb import ServiceUnavailableException
from sqlalchemy.exc import OperationalError, IntegrityError
import requests

class UserRepository:
    """用户仓储层 - 负责异常转换"""

    def get_by_id(self, user_id: int):
        """获取用户

        Raises:
            ResourceNotFoundException: 用户不存在
            ServiceUnavailableException: 数据库连接失败
        """
        try:
            user = self.session.query(User).filter_by(id=user_id).first()
            if not user:
                raise ResourceNotFoundException(
                    "用户不存在",
                    resource_type="User",
                    resource_id=user_id
                )
            return user

        except OperationalError as e:
            # ✅ 转换为业务异常，隐藏技术细节
            logger.error(f"数据库连接失败: {e}", exc_info=True)
            raise ServiceUnavailableException(
                "数据库服务暂时不可用，请稍后重试",
                service="database",
                original_error=type(e).__name__  # 只记录异常类型
            ) from e  # 保留异常链

        except IntegrityError as e:
            # ✅ 转换为资源冲突异常
            logger.warning(f"数据完整性错误: {e}")
            raise ResourceConflictException(
                "数据冲突，请检查输入",
                details=["可能存在重复的数据"]
            ) from e


class PaymentService:
    """支付服务 - 处理第三方API异常"""

    def process_payment(self, amount: float):
        """处理支付

        Raises:
            ServiceUnavailableException: 支付服务不可用
            BusinessException: 支付失败
        """
        try:
            response = requests.post(
                "https://payment-api.com/charge",
                json={"amount": amount},
                timeout=10
            )
            response.raise_for_status()
            return response.json()

        except requests.Timeout as e:
            # ✅ 超时异常转换
            logger.error(f"支付API超时: {e}")
            raise ServiceUnavailableException(
                "支付服务响应超时，请稍后重试",
                service="payment_gateway",
                timeout=10
            ) from e

        except requests.ConnectionError as e:
            # ✅ 连接异常转换
            logger.error(f"支付API连接失败: {e}")
            raise ServiceUnavailableException(
                "无法连接到支付服务",
                service="payment_gateway"
            ) from e

        except requests.HTTPError as e:
            # ✅ HTTP错误转换
            status_code = e.response.status_code
            if status_code == 402:
                raise BusinessException(
                    "余额不足",
                    code="INSUFFICIENT_BALANCE"
                ) from e
            elif status_code >= 500:
                raise ServiceUnavailableException(
                    "支付服务暂时不可用",
                    service="payment_gateway"
                ) from e
            else:
                raise BusinessException(
                    "支付失败",
                    code="PAYMENT_FAILED"
                ) from e
```

#### 方案 2: 异常映射表

```python
from typing import Dict, Type, Tuple
from sqlalchemy.exc import (
    OperationalError,
    IntegrityError,
    DataError,
    ProgrammingError
)
import requests

# 数据库异常映射
DATABASE_EXCEPTION_MAP: Dict[Type[Exception], Tuple[Type[BusinessException], str]] = {
    OperationalError: (
        ServiceUnavailableException,
        "数据库服务暂时不可用"
    ),
    IntegrityError: (
        ResourceConflictException,
        "数据冲突，请检查输入"
    ),
    DataError: (
        ValidationException,
        "数据格式错误"
    ),
    ProgrammingError: (
        BusinessException,
        "系统错误，请联系管理员"
    ),
}

# HTTP异常映射
HTTP_EXCEPTION_MAP: Dict[int, Tuple[Type[BusinessException], str]] = {
    400: (ValidationException, "请求参数错误"),
    401: (AuthenticationException, "认证失败"),
    403: (AuthorizationException, "权限不足"),
    404: (ResourceNotFoundException, "资源不存在"),
    409: (ResourceConflictException, "资源冲突"),
    429: (BusinessException, "请求过于频繁"),
    500: (ServiceUnavailableException, "服务暂时不可用"),
    502: (ServiceUnavailableException, "网关错误"),
    503: (ServiceUnavailableException, "服务不可用"),
    504: (ServiceUnavailableException, "网关超时"),
}


def convert_database_exception(e: Exception) -> BusinessException:
    """转换数据库异常为业务异常"""
    for exc_type, (business_exc, message) in DATABASE_EXCEPTION_MAP.items():
        if isinstance(e, exc_type):
            logger.error(f"数据库异常: {type(e).__name__}: {e}")
            return business_exc(
                message,
                original_error=type(e).__name__
            )

    # 未知异常
    logger.error(f"未知数据库异常: {e}", exc_info=True)
    return ServiceUnavailableException(
        "数据库服务异常",
        service="database"
    )


def convert_http_exception(e: requests.HTTPError) -> BusinessException:
    """转换HTTP异常为业务异常"""
    status_code = e.response.status_code
    exc_class, message = HTTP_EXCEPTION_MAP.get(
        status_code,
        (BusinessException, "请求失败")
    )

    logger.warning(f"HTTP异常: {status_code} - {e}")
    return exc_class(
        message,
        code=f"HTTP_{status_code}",
        status_code=status_code
    )


# 使用示例
class UserRepository:
    def get_by_id(self, user_id: int):
        try:
            user = self.session.query(User).filter_by(id=user_id).first()
            if not user:
                raise ResourceNotFoundException("用户不存在")
            return user
        except Exception as e:
            # ✅ 使用映射表转换异常
            raise convert_database_exception(e) from e
```

#### 方案 3: 异常装饰器

```python
from functools import wraps
from typing import Type, Callable

def handle_database_exceptions(func):
    """数据库异常处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            raise convert_database_exception(e) from e
    return wrapper


def handle_http_exceptions(func):
    """HTTP异常处理装饰器"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except requests.HTTPError as e:
            raise convert_http_exception(e) from e
        except requests.Timeout as e:
            logger.error(f"HTTP超时: {e}")
            raise ServiceUnavailableException(
                "服务响应超时",
                timeout=True
            ) from e
        except requests.ConnectionError as e:
            logger.error(f"连接失败: {e}")
            raise ServiceUnavailableException(
                "无法连接到服务",
                connection_error=True
            ) from e
    return wrapper


# 使用示例
class UserRepository:
    @handle_database_exceptions
    def get_by_id(self, user_id: int):
        """获取用户 - 自动处理数据库异常"""
        user = self.session.query(User).filter_by(id=user_id).first()
        if not user:
            raise ResourceNotFoundException("用户不存在")
        return user

    @handle_database_exceptions
    def create(self, user_data: dict):
        """创建用户 - 自动处理数据库异常"""
        user = User(**user_data)
        self.session.add(user)
        self.session.commit()
        return user


class PaymentService:
    @handle_http_exceptions
    def process_payment(self, amount: float):
        """处理支付 - 自动处理HTTP异常"""
        response = requests.post(
            "https://payment-api.com/charge",
            json={"amount": amount},
            timeout=10
        )
        response.raise_for_status()
        return response.json()
```

### 异常转换原则

```python
# ✅ 好的做法
try:
    # 内部操作
    result = database.query()
except TechnicalException as e:
    # 转换为业务异常
    logger.error(f"技术异常: {e}", exc_info=True)
    raise BusinessException("用户友好的消息") from e

# ❌ 不好的做法
try:
    result = database.query()
except Exception as e:
    raise e  # 直接抛出
```

### 日志记录原则

```python
# ✅ 记录完整信息到日志
logger.error(
    f"数据库连接失败: {e}",
    exc_info=True,  # 记录完整堆栈
    extra={
        "user_id": user_id,
        "operation": "get_user"
    }
)

# ✅ 返回友好消息给用户
raise ServiceUnavailableException(
    "数据库服务暂时不可用，请稍后重试"
)
```

### 使用 `from e` 保留异常链

```python
# ✅ 保留异常链
try:
    result = operation()
except OriginalException as e:
    raise BusinessException("业务消息") from e

# ❌ 丢失异常链
try:
    result = operation()
except OriginalException as e:
    raise BusinessException("业务消息")
```

### 完整的 Repository 层实现示例

```python
from yweb import (
    ResourceNotFoundException,
    ResourceConflictException,
    ServiceUnavailableException,
    ValidationException
)
from sqlalchemy.exc import OperationalError, IntegrityError
from yweb.log import get_logger

logger = get_logger()


class UserRepository:
    """用户仓储层 - 规范的异常处理"""

    def __init__(self, session):
        self.session = session

    def get_by_id(self, user_id: int):
        """根据ID获取用户

        Args:
            user_id: 用户ID

        Returns:
            User对象

        Raises:
            ResourceNotFoundException: 用户不存在
            ServiceUnavailableException: 数据库连接失败
        """
        try:
            user = self.session.query(User).filter_by(id=user_id).first()
            if not user:
                raise ResourceNotFoundException(
                    "用户不存在",
                    resource_type="User",
                    resource_id=user_id
                )
            return user

        except OperationalError as e:
            logger.error(
                f"数据库连接失败: {e}",
                exc_info=True,
                extra={"user_id": user_id}
            )
            raise ServiceUnavailableException(
                "数据库服务暂时不可用，请稍后重试",
                service="database"
            ) from e

    def create(self, user_data: dict):
        """创建用户

        Raises:
            ResourceConflictException: 用户名已存在
            ValidationException: 数据格式错误
            ServiceUnavailableException: 数据库连接失败
        """
        try:
            user = User(**user_data)
            self.session.add(user)
            self.session.commit()
            return user

        except IntegrityError as e:
            logger.warning(f"数据完整性错误: {e}")
            self.session.rollback()

            # 判断具体的完整性错误
            if "unique constraint" in str(e).lower():
                raise ResourceConflictException(
                    "用户名已被使用",
                    field="username",
                    value=user_data.get("username")
                ) from e
            else:
                raise ValidationException(
                    "数据验证失败",
                    details=["数据格式不正确"]
                ) from e

        except OperationalError as e:
            logger.error(f"数据库连接失败: {e}", exc_info=True)
            self.session.rollback()
            raise ServiceUnavailableException(
                "数据库服务暂时不可用",
                service="database"
            ) from e
```

---

## 响应格式

### 成功响应

```json
{
    "status": "success",
    "message": "登录成功",
    "msg_details": [],
    "data": {"user": {...}}
}
```

### 错误响应

```json
{
    "status": "error",
    "message": "用户名或密码错误",
    "msg_details": [],
    "data": {},
    "error_code": "AUTHENTICATION_FAILED"
}
```

### 验证错误响应

```json
{
    "status": "error",
    "message": "请求参数验证失败",
    "msg_details": [
        "username: 字符串长度必须至少为 2 个字符",
        "password: 字符串长度必须至少为 6 个字符"
    ],
    "data": {},
    "error_code": "VALIDATION_ERROR"
}
```

### 调试模式响应

设置环境变量 `DEBUG=true`，异常响应会包含更多调试信息：

```json
{
    "status": "error",
    "message": "服务器内部错误",
    "msg_details": [
        "异常类型: ValueError",
        "异常消息: invalid literal for int()"
    ],
    "data": {},
    "error_code": "INTERNAL_SERVER_ERROR",
    "debug_info": {
        "exception_type": "ValueError",
        "exception_message": "invalid literal for int()",
        "traceback": ["...", "...", "..."]
    }
}
```

---

## 日志记录

### 自动记录的信息

全局异常处理器会自动记录以下信息：

1. **业务异常** (WARNING 级别):
   - 请求 ID
   - 请求路径和方法
   - 错误代码和消息
   - 详细信息和额外上下文

2. **系统异常** (ERROR 级别):
   - 请求 ID
   - 请求路径和方法
   - 异常类型和消息
   - **完整的异常堆栈**

### 日志示例

```
2026-01-18 10:30:45 WARNING [yweb.exceptions.handlers] Business exception occurred: AUTHENTICATION_FAILED - 用户名或密码错误
    request_id: a1b2c3d4
    path: /api/v1/auth/login
    method: POST
    error_code: AUTHENTICATION_FAILED
    status_code: 401

2026-01-18 10:31:20 ERROR [yweb.exceptions.handlers] Unhandled exception: ValueError: invalid literal for int()
    request_id: e5f6g7h8
    path: /api/v1/users/abc
    method: GET
    exception_type: ValueError
    exception_message: invalid literal for int() with base 10: 'abc'
    traceback:
        Traceback (most recent call last):
          File "/app/api/v1/users.py", line 25, in get_user
            user_id = int(user_id_str)
        ValueError: invalid literal for int() with base 10: 'abc'
```

---

## 调试技巧

### 开启调试模式

```bash
export DEBUG=true
```

调试模式下，错误响应会包含：
- 异常类型
- 异常消息
- 堆栈跟踪（最后5行）

### 查看日志

```bash
# 查看错误日志
tail -f logs/error.log

# 搜索特定异常
grep "AuthenticationException" logs/error.log

# 查看完整堆栈
grep -A 20 "Traceback" logs/error.log
```

---

## 测试示例

### 测试异常抛出

```python
import pytest
from yweb import AuthenticationException

def test_login_with_invalid_credentials():
    """测试登录失败"""
    with pytest.raises(AuthenticationException) as exc_info:
        auth_service.login("invalid_user", "wrong_password")

    assert exc_info.value.code == "AUTHENTICATION_FAILED"
    assert "用户名或密码错误" in str(exc_info.value)
```

### 测试 API 响应

```python
def test_login_api_error(client):
    response = client.post("/auth/login", json={
        "username": "invalid",
        "password": "wrong"
    })

    assert response.status_code == 401
    assert response.json()["status"] == "error"
    assert response.json()["error_code"] == "AUTHENTICATION_FAILED"
```

---

## 从旧代码迁移

### 步骤 1: 注册全局异常处理器

在 `main.py` 中添加：

```python
from yweb import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)  # 添加这一行
```

### 步骤 2: 逐步替换旧代码

**旧代码模式 1: 返回错误响应**

```python
# ❌ 旧代码（过时）
@router.post("/login")
def login(username: str, password: str):
    user = authenticate(username, password)
    if not user:
        return Unauthorized("用户名或密码错误")  # ❌ 返回响应
    return OK(user)
```

```python
# ✅ 新代码（推荐）
from yweb import OK, AuthenticationException

@router.post("/login")
def login(username: str, password: str):
    user = authenticate(username, password)
    if not user:
        raise AuthenticationException("用户名或密码错误")  # ✅ 抛出异常
    return OK(user)
```

**旧代码模式 2: Service 层返回字典**

```python
# ❌ 旧代码（过时）- API 层需要手动处理错误字典
result = auth_service.login(username, password)
if isinstance(result, dict) and "error" in result:
    if result["error"] == "invalid_credentials":
        return Unauthorized("用户名或密码错误")
    return InternalServerError("系统错误")
return OK(result)
```

```python
# ✅ 新代码（推荐）- Service 层抛出异常，API 层代码极简
# 异常由全局处理器自动捕获并转换为 JSON 响应
result = auth_service.login(username, password)
return OK(result, "登录成功")
```

### 步骤 3: 修改 Service 层

```python
# ❌ 旧代码（过时）
class AuthService:
    def login(self, username, password):
        if not user:
            return {"error": "invalid_credentials"}  # ❌ 返回错误字典
        return user_data
```

```python
# ✅ 新代码（推荐）- 全局处理器会自动记录日志并返回统一响应
from yweb import AuthenticationException

class AuthService:
    def login(self, username, password):
        if not user:
            raise AuthenticationException("用户名或密码错误")  # ✅ 抛出异常
        return user_data
```

---

## 常见问题

### Q1: 如何自定义异常类？

继承 `BusinessException` 并设置默认参数：

```python
from yweb import BusinessException
from fastapi import status

class PaymentException(BusinessException):
    """支付异常"""
    def __init__(self, message: str = "支付失败", **kwargs):
        super().__init__(
            message=message,
            code="PAYMENT_FAILED",
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            **kwargs
        )

# 使用
raise PaymentException("余额不足", balance=100, required=200)
```

### Q2: 如何在异常响应中添加自定义字段？

使用 `extra` 参数：

```python
raise BusinessException(
    "订单创建失败",
    code="ORDER_CREATE_FAILED",
    order_id=12345,
    reason="库存不足",
    available_stock=5
)
```

调试模式下，这些信息会出现在 `debug_info` 中。

### Q3: 如何处理第三方库的异常？

在 Service 层捕获并转换为业务异常：

```python
from yweb import ServiceUnavailableException
import requests

class PaymentService:
    def process_payment(self, amount: float):
        try:
            response = requests.post(
                "https://payment-api.com/charge",
                json={"amount": amount}
            )
            response.raise_for_status()
            return response.json()
        except requests.RequestException as e:
            # 转换为业务异常
            raise ServiceUnavailableException(
                "支付服务暂时不可用",
                service="payment_gateway",
                original_error=str(e)
            )
```

### Q4: 如何在测试中验证异常？

```python
import pytest
from yweb import AuthenticationException

def test_login_with_invalid_credentials():
    """测试登录失败"""
    with pytest.raises(AuthenticationException) as exc_info:
        auth_service.login("invalid_user", "wrong_password")

    assert exc_info.value.code == "AUTHENTICATION_FAILED"
    assert "用户名或密码错误" in str(exc_info.value)
```

---

## 验证错误翻译器

YWeb 提供了 `ValidationErrorTranslator` 类，用于将 Pydantic 验证错误自动翻译为友好的中文提示，并支持应用层扩展。

### 基本用法

框架已内置常见的验证错误翻译，无需额外配置即可获得中文提示：

```python
from fastapi import FastAPI
from yweb import register_exception_handlers

app = FastAPI()
register_exception_handlers(app)

# 验证失败时自动返回中文提示
# {
#     "status": "error",
#     "message": "请求参数验证失败",
#     "msg_details": [
#         "username: 长度不能少于 3 个字符",
#         "email: 邮箱格式不正确"
#     ],
#     "error_code": "VALIDATION_ERROR"
# }
```

### 扩展自定义错误翻译

应用可以轻松扩展自定义的验证错误翻译：

```python
from yweb import ValidationErrorTranslator

# 方式1: 添加静态错误映射（最常用）
ValidationErrorTranslator.add_messages({
    "value_error.phone": "手机号格式不正确，请输入11位有效手机号",
    "value_error.id_card": "身份证号格式不正确",
    "value_error.org_code": "组织编码格式不正确",
})
```

```python
# 方式2: 注册动态翻译函数（需要访问上下文）
@ValidationErrorTranslator.translator("value_error.custom_range")
def translate_custom_range(ctx: dict) -> str:
    return f"值必须在 {ctx.get('min')} 到 {ctx.get('max')} 之间"
```

```python
# 方式3: 添加回退翻译（英文短语 -> 中文）
ValidationErrorTranslator.add_fallback_translations({
    "must be positive": "必须为正数",
    "cannot be empty": "不能为空",
})
```

```python
# 方式4: 批量配置（适合从配置文件加载）
ValidationErrorTranslator.configure({
    "messages": {
        "value_error.phone": "手机号格式不正确",
    },
    "fallback_translations": {
        "invalid format": "格式无效",
    }
})
```

### 内置支持的验证类型

| Pydantic 错误类型 | 中文提示 |
|------------------|---------|
| `missing` | 此字段为必填项 |
| `string_too_short` | 长度不能少于 X 个字符 |
| `string_too_long` | 长度不能超过 X 个字符 |
| `greater_than_equal` | 必须大于或等于 X |
| `less_than_equal` | 必须小于或等于 X |
| `int_type` | 必须是整数 |
| `str_type` | 必须是字符串 |
| `value_error.email` | 邮箱格式不正确 |
| `url_parsing` | URL 格式不正确 |
| `datetime_parsing` | 日期时间格式不正确 |
| `enum` | 值必须是以下之一: ... |

---

## 验证约束模块（类似 .NET MVC 特性）

YWeb 提供了类似 .NET MVC 特性验证风格的约束模块，让你可以用声明式的方式定义字段验证规则。

### 推荐方式：使用 Typed 快捷类

只需导入一个类，IDE 自动补全所有验证类型：

```python
from pydantic import BaseModel
from yweb import Typed

class UserCreate(BaseModel):
    phone: Typed.Phone          # 必填手机号
    email: Typed.Email          # 必填邮箱
    website: Typed.Url | None = None  # 可选 URL
    id_card: Typed.IdCard       # 身份证

class UserUpdate(BaseModel):
    # 可选类型（允许 None 或空字符串）
    phone: Typed.OptionalPhone = None
    email: Typed.OptionalEmail = None
```

### Typed 类型速查表

| 类型 | 说明 | 示例 |
|------|------|------|
| `Typed.Phone` | 手机号（中国大陆11位） | `phone: Typed.Phone` |
| `Typed.Email` | 邮箱地址 | `email: Typed.Email` |
| `Typed.Url` | URL（http/https） | `website: Typed.Url` |
| `Typed.IdCard` | 身份证号（18位，含校验） | `id_card: Typed.IdCard` |
| `Typed.CreditCard` | 信用卡号（Luhn算法校验） | `card: Typed.CreditCard` |
| `Typed.OptionalPhone` | 可选手机号 | `phone: Typed.OptionalPhone = None` |
| `Typed.OptionalEmail` | 可选邮箱 | `email: Typed.OptionalEmail = None` |
| `Typed.OptionalUrl` | 可选URL | `url: Typed.OptionalUrl = None` |
| `Typed.OptionalIdCard` | 可选身份证号 | `id: Typed.OptionalIdCard = None` |

### 传统方式：使用 Annotated

如果需要更细粒度的控制（如字符串长度、正则等），使用 Annotated 方式：

```python
from typing import Annotated
from pydantic import BaseModel
from yweb import StringLength, RegularExpression, Range, Phone

class UserCreate(BaseModel):
    # 字符串长度约束
    username: Annotated[str, StringLength(min_length=3, max_length=20)]
    
    # 正则表达式约束
    password: Annotated[str, RegularExpression(r"^[a-zA-Z0-9_]{8,30}$")]
    
    # 数值范围约束
    age: Annotated[int, Range(ge=1, le=150)]
    
    # 格式验证
    phone: Annotated[str, Phone]
```

### .NET vs Python 对照表

| .NET 写法 | Python 写法（Typed） | Python 写法（Annotated） |
|-----------|---------------------|-------------------------|
| `[Phone]` | `Typed.Phone` | `Annotated[str, Phone]` |
| `[EmailAddress]` | `Typed.Email` | `Annotated[str, Email]` |
| `[Url]` | `Typed.Url` | `Annotated[str, Url]` |
| `[CreditCard]` | `Typed.CreditCard` | `Annotated[str, CreditCard]` |
| `[StringLength(3, 20)]` | - | `StringLength(min_length=3, max_length=20)` |
| `[Range(1, 100)]` | - | `Range(ge=1, le=100)` |
| `[RegularExpression(...)]` | - | `RegularExpression(r"...")` |

### 组合多个约束

```python
# [Required] [MinLength(8)] [MaxLength(32)] [RegularExpression]
password: Annotated[str, 
    StringLength(min_length=8, max_length=32),
    RegularExpression(r"^(?=.*[A-Z])(?=.*[a-z])(?=.*\d).+$")
]
```

### 验证失败响应示例

```json
{
    "status": "error",
    "message": "请求参数验证失败",
    "msg_details": [
        "username: 长度不能少于 3 个字符",
        "phone: 手机号格式不正确，请输入11位有效手机号",
        "email: 邮箱格式不正确",
        "age: 必须大于或等于 1"
    ],
    "data": {},
    "error_code": "VALIDATION_ERROR"
}
```

### 内置验证类型说明

| 类型 | 说明 | 错误提示 |
|------|------|---------|
| `Phone` | 中国大陆手机号（11位） | 手机号格式不正确，请输入11位有效手机号 |
| `Email` | 邮箱格式 | 邮箱格式不正确 |
| `Url` | URL 格式（http/https） | URL 格式不正确，需要以 http:// 或 https:// 开头 |
| `IdCard` | 中国大陆身份证（18位，含校验码验证） | 身份证号格式不正确 |
| `CreditCard` | 信用卡号（Luhn 算法校验） | 信用卡号格式不正确 |

### 自定义验证类型

你可以创建自己的验证类型：

```python
from typing import Annotated
from pydantic.functional_validators import BeforeValidator
from pydantic_core import PydanticCustomError
import re

def _validate_org_code(v: str) -> str:
    """验证组织编码"""
    if not re.match(r"^[A-Z]{3}-\d{4}$", v):
        raise PydanticCustomError(
            "value_error.org_code",  # 错误类型
            "组织编码格式不正确（格式如 ABC-1234）"  # 错误消息
        )
    return v

# 定义验证类型
OrgCode = BeforeValidator(_validate_org_code)

# 使用
class OrgCreate(BaseModel):
    code: Annotated[str, OrgCode]
```

---

## 总结

使用 YWeb 异常处理机制的优势：

1. ✅ **代码更简洁** - 减少 60-70% 的异常处理代码
2. ✅ **逻辑更清晰** - 业务逻辑与异常处理分离
3. ✅ **维护更容易** - 统一的异常处理逻辑
4. ✅ **调试更方便** - 完整的异常堆栈信息
5. ✅ **用户体验更好** - 友好的错误提示
6. ✅ **响应格式统一** - 所有错误响应格式一致
7. ✅ **安全可控** - 隐藏技术细节，不泄露敏感信息

### 核心要点

1. **总是注册全局异常处理器** - `register_exception_handlers(app)`
2. **直接抛出异常，不返回错误字典** - `raise` 而非 `return {"error": ...}`
3. **无需 try-catch** - 让全局处理器处理
4. **选择合适的异常类型** - 401/403/404/409/422/503
5. **提供详细信息** - 使用 `details` 参数
6. **使用错误代码** - 便于前端判断
7. **开发环境开启 DEBUG** - 查看详细信息
8. **使用 `from e` 保留异常链** - 方便调试

开始使用吧！🚀

---

**版本:** v1.5.0 | **更新日期:** 2026-01-21

**更新记录:**
- v1.5.0 (2026-01-21): 新增 `Resp` 响应快捷类，只需导入一个类即可使用所有响应方法（Resp.OK, Resp.NotFound 等）
- v1.4.0 (2026-01-21): 新增 `Typed` 验证类型快捷类，只需导入一个类即可使用所有验证类型（Typed.Phone, Typed.Email 等）
- v1.3.0 (2026-01-21): 新增 `Err` 异常快捷创建类，只需导入一个类即可创建所有类型的异常，IDE 自动补全
- v1.2.0 (2026-01-20): 新增 ErrorCode 错误代码枚举，支持 IDE 补全和拼写检查，支持应用层扩展自定义错误代码
- v1.1.1 (2026-01-20): 优化文档示例，明确标注"改进前"代码为过时写法，避免误导
- v1.1.0 (2026-01-19): 新增验证错误翻译器（ValidationErrorTranslator）、验证约束模块（类似 .NET MVC 特性）
- v1.0.0 (2026-01-18): 初始版本
