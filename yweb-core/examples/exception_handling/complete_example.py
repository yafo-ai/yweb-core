"""完整的 FastAPI 应用示例

展示如何在实际项目中使用 YWeb 异常处理机制。
"""

from fastapi import FastAPI, Request, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from typing import Optional
import uvicorn

# 导入 YWeb 异常处理模块
from yweb import (
    # 响应函数
    OK,
    # 异常类
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    # 异常处理器注册函数
    register_exception_handlers,
    # 日志
    get_logger
)

# 创建日志记录器
logger = get_logger()

# 创建 FastAPI 应用
app = FastAPI(
    title="YWeb 异常处理示例",
    description="展示如何使用 YWeb 异常处理机制",
    version="1.0.0"
)

# ============================================================================
# 1. 注册全局异常处理器（必须在路由注册之前）
# ============================================================================

register_exception_handlers(app)
logger.info("全局异常处理器已注册")


# ============================================================================
# 2. 定义数据模型
# ============================================================================

class User(BaseModel):
    """用户模型"""
    id: int
    username: str
    email: str
    role: str = "user"

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


class LoginRequest(BaseModel):
    """登录请求"""
    username: str = Field(min_length=2, max_length=50, description="用户名")
    password: str = Field(min_length=6, max_length=128, description="密码")


class UserCreateRequest(BaseModel):
    """创建用户请求"""
    username: str = Field(min_length=2, max_length=50)
    email: str = Field(min_length=5, max_length=100)
    password: str = Field(min_length=6, max_length=128)


# ============================================================================
# 3. 模拟数据库
# ============================================================================

# 模拟用户数据库
USERS_DB = {
    1: User(id=1, username="admin", email="admin@example.com", role="admin"),
    2: User(id=2, username="user1", email="user1@example.com", role="user"),
}

# 模拟密码数据库（实际应该加密存储）
PASSWORDS_DB = {
    "admin": "admin123",
    "user1": "password123",
}


# ============================================================================
# 4. 业务逻辑层（Service）
# ============================================================================

class AuthService:
    """认证服务 - 展示如何在 Service 层抛出异常"""

    def authenticate(self, username: str, password: str) -> User:
        """认证用户

        Args:
            username: 用户名
            password: 密码

        Returns:
            用户对象

        Raises:
            AuthenticationException: 认证失败
        """
        # 检查用户是否存在
        user = self.find_user_by_username(username)
        if not user:
            # ✅ 直接抛出异常，不返回错误字典
            raise AuthenticationException("用户名或密码错误")

        # 验证密码
        if not self.verify_password(username, password):
            raise AuthenticationException("用户名或密码错误")

        logger.info(f"用户 {username} 认证成功")
        return user

    def find_user_by_username(self, username: str) -> Optional[User]:
        """根据用户名查找用户"""
        for user in USERS_DB.values():
            if user.username == username:
                return user
        return None

    def verify_password(self, username: str, password: str) -> bool:
        """验证密码"""
        return PASSWORDS_DB.get(username) == password


class UserService:
    """用户服务 - 展示各种异常场景"""

    def get_user_by_id(self, user_id: int) -> User:
        """根据ID获取用户

        Raises:
            ResourceNotFoundException: 用户不存在
        """
        user = USERS_DB.get(user_id)
        if not user:
            raise ResourceNotFoundException(
                "用户不存在",
                resource_type="User",
                resource_id=user_id
            )
        return user

    def create_user(self, username: str, email: str, password: str) -> User:
        """创建用户

        Raises:
            ResourceConflictException: 用户名已存在
            ValidationException: 数据验证失败
        """
        # 检查用户名是否已存在
        if self.username_exists(username):
            raise ResourceConflictException(
                "用户名已被使用",
                field="username",
                value=username
            )

        # 验证邮箱格式
        if not self.is_valid_email(email):
            raise ValidationException(
                "邮箱格式不正确",
                field="email",
                value=email
            )

        # 创建用户
        new_id = max(USERS_DB.keys()) + 1
        new_user = User(id=new_id, username=username, email=email)
        USERS_DB[new_id] = new_user
        PASSWORDS_DB[username] = password

        logger.info(f"创建用户成功: {username}")
        return new_user

    def delete_user(self, user_id: int, current_user: User) -> None:
        """删除用户

        Raises:
            AuthorizationException: 权限不足
            ResourceNotFoundException: 用户不存在
        """
        # 检查权限
        if not current_user.is_admin:
            raise AuthorizationException(
                "需要管理员权限",
                code="ADMIN_REQUIRED",
                details=[
                    f"当前角色: {current_user.role}",
                    "需要角色: admin"
                ]
            )

        # 检查用户是否存在
        if user_id not in USERS_DB:
            raise ResourceNotFoundException("用户不存在")

        # 删除用户
        del USERS_DB[user_id]
        logger.info(f"删除用户成功: {user_id}")

    def username_exists(self, username: str) -> bool:
        """检查用户名是否存在"""
        return any(u.username == username for u in USERS_DB.values())

    def is_valid_email(self, email: str) -> bool:
        """验证邮箱格式"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(pattern, email) is not None


# 创建服务实例
auth_service = AuthService()
user_service = UserService()


# ============================================================================
# 5. 依赖注入（模拟获取当前用户）
# ============================================================================

def get_current_user(request: Request) -> User:
    """获取当前用户（简化版，实际应该从 Token 中解析）

    Raises:
        AuthenticationException: 未认证
    """
    # 从请求头获取用户ID（实际应该从 JWT Token 中解析）
    user_id = request.headers.get("X-User-ID")
    if not user_id:
        raise AuthenticationException("未提供认证信息")

    try:
        return user_service.get_user_by_id(int(user_id))
    except ValueError:
        raise AuthenticationException("无效的用户ID")


# ============================================================================
# 6. API 路由
# ============================================================================

@app.get("/")
def root():
    """根路径"""
    return {
        "message": "YWeb 异常处理示例 API",
        "docs": "/docs",
        "examples": {
            "login": "POST /auth/login",
            "get_user": "GET /users/{user_id}",
            "create_user": "POST /users",
            "delete_user": "DELETE /users/{user_id}"
        }
    }


@app.post("/auth/login")
def login(login_request: LoginRequest):
    """用户登录

    示例：
        POST /auth/login
        {
            "username": "admin",
            "password": "admin123"
        }

    成功响应：
        {
            "status": "success",
            "message": "登录成功",
            "data": {"user": {...}}
        }

    失败响应：
        {
            "status": "error",
            "message": "用户名或密码错误",
            "error_code": "AUTHENTICATION_FAILED"
        }
    """
    # ✅ 无需 try-catch，异常会被全局处理器捕获
    user = auth_service.authenticate(
        login_request.username,
        login_request.password
    )

    return OK(
        data={"user": user.dict()},
        message="登录成功"
    )


@app.get("/users/{user_id}")
def get_user(user_id: int):
    """获取用户信息

    示例：
        GET /users/1

    成功响应：
        {
            "status": "success",
            "message": "获取成功",
            "data": {"id": 1, "username": "admin", ...}
        }

    失败响应（用户不存在）：
        {
            "status": "error",
            "message": "用户不存在",
            "error_code": "RESOURCE_NOT_FOUND"
        }
    """
    user = user_service.get_user_by_id(user_id)
    return OK(data=user.dict(), message="获取成功")


@app.post("/users")
def create_user(user_data: UserCreateRequest):
    """创建用户

    示例：
        POST /users
        {
            "username": "newuser",
            "email": "newuser@example.com",
            "password": "password123"
        }

    成功响应：
        {
            "status": "success",
            "message": "创建成功",
            "data": {"id": 3, "username": "newuser", ...}
        }

    失败响应（用户名已存在）：
        {
            "status": "error",
            "message": "用户名已被使用",
            "error_code": "RESOURCE_CONFLICT"
        }

    失败响应（参数验证失败）：
        {
            "status": "error",
            "message": "请求参数验证失败",
            "msg_details": ["username: 字符串长度必须至少为 2 个字符"],
            "error_code": "VALIDATION_ERROR"
        }
    """
    user = user_service.create_user(
        username=user_data.username,
        email=user_data.email,
        password=user_data.password
    )
    return OK(data=user.dict(), message="创建成功")


@app.delete("/users/{user_id}")
def delete_user(
    user_id: int,
    current_user: User = Depends(get_current_user)
):
    """删除用户（需要管理员权限）

    示例：
        DELETE /users/2
        Headers:
            X-User-ID: 1  # 管理员用户

    成功响应：
        {
            "status": "success",
            "message": "删除成功",
            "data": {}
        }

    失败响应（权限不足）：
        {
            "status": "error",
            "message": "需要管理员权限",
            "msg_details": ["当前角色: user", "需要角色: admin"],
            "error_code": "ADMIN_REQUIRED"
        }
    """
    user_service.delete_user(user_id, current_user)
    return OK(message="删除成功")


@app.get("/test/business-error")
def test_business_error():
    """测试通用业务异常"""
    raise BusinessException(
        "这是一个业务异常示例",
        code="CUSTOM_ERROR",
        details=["详细信息1", "详细信息2"]
    )


@app.get("/test/system-error")
def test_system_error():
    """测试系统异常（会记录完整堆栈）"""
    # 故意触发一个系统异常
    result = 1 / 0  # ZeroDivisionError
    return {"result": result}


# ============================================================================
# 7. 启动应用
# ============================================================================

if __name__ == "__main__":
    print("=" * 80)
    print("YWeb 异常处理示例 API")
    print("=" * 80)
    print("\n📚 API 文档: http://localhost:8000/docs")
    print("\n🧪 测试示例:")
    print("\n1. 测试登录成功:")
    print('   curl -X POST "http://localhost:8000/auth/login" \\')
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"username": "admin", "password": "admin123"}\'')
    print("\n2. 测试登录失败:")
    print('   curl -X POST "http://localhost:8000/auth/login" \\')
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"username": "admin", "password": "wrong"}\'')
    print("\n3. 测试获取用户:")
    print('   curl "http://localhost:8000/users/1"')
    print("\n4. 测试用户不存在:")
    print('   curl "http://localhost:8000/users/999"')
    print("\n5. 测试创建用户:")
    print('   curl -X POST "http://localhost:8000/users" \\')
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"username": "test", "email": "test@example.com", "password": "test123"}\'')
    print("\n6. 测试参数验证失败:")
    print('   curl -X POST "http://localhost:8000/users" \\')
    print('        -H "Content-Type: application/json" \\')
    print('        -d \'{"username": "a", "email": "invalid", "password": "123"}\'')
    print("\n7. 测试权限不足:")
    print('   curl -X DELETE "http://localhost:8000/users/2" \\')
    print('        -H "X-User-ID: 2"')
    print("\n8. 测试系统异常:")
    print('   curl "http://localhost:8000/test/system-error"')
    print("\n" + "=" * 80)
    print()

    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
