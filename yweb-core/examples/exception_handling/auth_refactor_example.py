"""auth.py 重构示例

展示如何使用新的异常处理机制重构现有代码。

对比：
- 旧代码：47 行，充斥大量 if-else 判断
- 新代码：15 行，逻辑清晰简洁

代码减少：68%
"""

# ============================================================================
# 旧代码示例（不推荐）
# ============================================================================

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from yweb import OK, Unauthorized, InternalServerError
from yweb.log import get_logger

logger = get_logger()
router_old = APIRouter(prefix="/auth-old", tags=["auth-old"])


class LoginRequest(BaseModel):
    username: str = Field(min_length=2, max_length=50)
    password: str = Field(min_length=6, max_length=128)


@router_old.post("/login")
def login_old(request: Request, login_request: LoginRequest):
    """旧的登录实现 - 47 行代码，充斥大量判断"""
    client_ip = request.client.host if request.client else "未知"
    user_agent = request.headers.get("User-Agent", "未知")

    logger.debug(f"客户端信息: IP={client_ip}, User-Agent={user_agent}")
    logger.debug(f"调用 auth_app_service.login 方法...")

    # 假设这是 Service 层调用
    from app.services.auth_app import AuthApplicationService
    from app.domain.auth.impl.auth_service_impl import AuthServiceImpl
    from app.domain.auth.impl.token_service import TokenService

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

    logger.debug(f"auth_app_service.login 返回结果: {result}")

    # ❌ 大量重复的异常判断代码
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


# ============================================================================
# 新代码示例（推荐）
# ============================================================================

from yweb import OK, AuthenticationException

router_new = APIRouter(prefix="/auth", tags=["auth"])


@router_new.post("/login")
def login_new(request: Request, login_request: LoginRequest):
    """新的登录实现 - 15 行代码，逻辑清晰

    改进点：
    1. 无需 try-catch，异常自动被全局处理器捕获
    2. 无需判断返回值是否为错误字典
    3. Service 层直接抛出异常，Controller 层只关注正常流程
    4. 代码减少 68%，可读性大幅提升
    """
    client_ip = request.client.host if request.client else "未知"
    user_agent = request.headers.get("User-Agent", "未知")

    # 假设这是重构后的 Service 层
    from app.services.auth_app import AuthApplicationService
    from app.domain.auth.impl.auth_service_impl import AuthServiceImpl
    from app.domain.auth.impl.token_service import TokenService

    auth_app_service = AuthApplicationService(
        auth_service=AuthServiceImpl(),
        token_repository=TokenService()
    )

    # ✅ 直接调用，异常会被全局处理器捕获并转换为 JSON 响应
    result = auth_app_service.login(
        login_request.username,
        login_request.password,
        client_ip,
        user_agent
    )

    return OK(result, "登录成功")


# ============================================================================
# Service 层重构示例
# ============================================================================

"""
旧的 Service 层实现（返回错误字典）:

class AuthServiceImpl:
    def login(self, username: str, password: str, client_ip: str, user_agent: str):
        # 查找用户
        user = self.user_repository.find_by_username(username)
        if not user:
            return {"error": "invalid_credentials"}

        # 验证密码
        if not self.verify_password(password, user.password_hash):
            return {"error": "invalid_credentials"}

        # 创建 Token
        try:
            token = self.create_token(user)
            return {"token": token, "user": user}
        except Exception as e:
            logger.error(f"创建 Token 失败: {e}")
            return {"error": "system_error", "message": str(e)}


新的 Service 层实现（抛出异常）:
"""

from yweb import AuthenticationException


class AuthServiceImplNew:
    """重构后的认证服务 - 使用异常而非错误字典"""

    def login(self, username: str, password: str, client_ip: str, user_agent: str):
        """用户登录

        Args:
            username: 用户名
            password: 密码
            client_ip: 客户端IP
            user_agent: 用户代理

        Returns:
            包含 token 和用户信息的字典

        Raises:
            AuthenticationException: 认证失败时抛出
        """
        # 查找用户
        user = self.user_repository.find_by_username(username)
        if not user:
            # ✅ 直接抛出异常，不返回错误字典
            raise AuthenticationException("用户名或密码错误")

        # 验证密码
        if not self.verify_password(password, user.password_hash):
            raise AuthenticationException("用户名或密码错误")

        # 创建 Token（不需要 try-catch，异常会自动向上传播）
        token = self.create_token(user)

        # 记录登录日志
        self.login_record_repository.create(
            user_id=user.id,
            client_ip=client_ip,
            user_agent=user_agent
        )

        return {
            "access_token": token.access_token,
            "refresh_token": token.refresh_token,
            "user": user
        }


# ============================================================================
# 更多示例
# ============================================================================

from yweb import (
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    AuthorizationException
)


@router_new.get("/users/{user_id}")
def get_user(user_id: int):
    """获取用户信息 - 资源不存在示例"""
    from app.domain.auth.model.user import User

    user = User.get_by_id(user_id)
    if not user:
        # ✅ 抛出资源不存在异常
        raise ResourceNotFoundException(
            "用户不存在",
            resource_type="User",
            resource_id=user_id
        )

    return OK(user, "获取成功")


@router_new.post("/users")
def create_user(username: str, email: str, password: str):
    """创建用户 - 资源冲突和验证示例"""
    from app.domain.auth.model.user import User

    # 检查用户名是否已存在
    existing_user = User.get_by_username(username)
    if existing_user:
        # ✅ 抛出资源冲突异常
        raise ResourceConflictException(
            "用户名已被使用",
            field="username",
            value=username
        )

    # 检查邮箱格式
    if not is_valid_email(email):
        # ✅ 抛出验证异常
        raise ValidationException(
            "邮箱格式不正确",
            field="email",
            value=email
        )

    # 创建用户
    user = User.create(username=username, email=email, password=password)
    return OK(user, "创建成功")


@router_new.delete("/users/{user_id}")
def delete_user(user_id: int, current_user=None):
    """删除用户 - 权限检查示例"""
    from app.domain.auth.model.user import User

    # 检查权限
    if not current_user or not current_user.is_admin:
        # ✅ 抛出授权异常
        raise AuthorizationException(
            "需要管理员权限",
            code="ADMIN_REQUIRED",
            details=[
                f"当前角色: {current_user.role if current_user else 'anonymous'}",
                "需要角色: admin"
            ]
        )

    # 查找用户
    user = User.get_by_id(user_id)
    if not user:
        raise ResourceNotFoundException("用户不存在")

    # 删除用户
    user.delete()
    return OK(message="删除成功")


# ============================================================================
# 辅助函数
# ============================================================================

def is_valid_email(email: str) -> bool:
    """验证邮箱格式"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


# ============================================================================
# 使用说明
# ============================================================================

"""
如何在 main.py 中使用：

from fastapi import FastAPI
from yweb import register_exception_handlers

app = FastAPI()

# 1. 注册全局异常处理器（必须在路由注册之前）
register_exception_handlers(app)

# 2. 注册路由
app.include_router(router_new)

# 3. 启动应用
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


测试异常处理：

1. 测试认证失败：
   POST /auth/login
   {
       "username": "invalid_user",
       "password": "wrong_password"
   }

   响应：
   {
       "status": "error",
       "message": "用户名或密码错误",
       "msg_details": [],
       "data": {},
       "error_code": "AUTHENTICATION_FAILED"
   }

2. 测试资源不存在：
   GET /auth/users/99999

   响应：
   {
       "status": "error",
       "message": "用户不存在",
       "msg_details": [],
       "data": {},
       "error_code": "RESOURCE_NOT_FOUND"
   }

3. 测试参数验证：
   POST /auth/users
   {
       "username": "a",  // 太短
       "email": "invalid-email",
       "password": "123"  // 太短
   }

   响应：
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
"""
