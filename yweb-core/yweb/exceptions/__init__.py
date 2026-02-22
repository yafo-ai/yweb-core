"""异常处理模块

提供业务异常类、全局异常处理器等功能。

使用示例:
    from yweb import Err, register_exception_handlers

    # 在 FastAPI 应用中注册异常处理器
    app = FastAPI()
    register_exception_handlers(app)

    # 在业务代码中抛出异常（推荐使用 Err）
    @router.post("/login")
    def login(username: str, password: str):
        user = authenticate(username, password)
        if not user:
            raise Err.auth("用户名或密码错误")
        return OK(user)
"""

from .exceptions import (
    # ===== 推荐使用 =====
    Err,                            # 异常快捷创建类
    ErrorCode,                      # 错误代码枚举
    ErrorCodeType,
    
    # ===== 高级用法 =====
    # 以下类主要用于：类型检查、自定义异常继承、单元测试
    BusinessException,              # 业务异常基类
    AuthenticationException,        # 401
    AuthorizationException,         # 403
    ResourceNotFoundException,      # 404
    ResourceConflictException,      # 409
    ValidationException,            # 422
    ServiceUnavailableException,    # 503
)

from .handlers import (
    # 异常处理器注册函数
    register_exception_handlers,

    # 单独的处理器（高级用法）
    business_exception_handler,
    validation_exception_handler,
    http_exception_handler,
    general_exception_handler,
    
    # 验证错误翻译器（扩展用）
    ValidationErrorTranslator,
)

__all__ = [
    # ===== 推荐使用 =====
    "Err",                          # 异常快捷创建：Err.auth(), Err.not_found() 等
    "ErrorCode",                    # 错误代码枚举
    "register_exception_handlers",  # 注册全局异常处理器
    
    # ===== 高级用法 =====
    # 以下导出主要用于：类型检查、自定义异常继承、单元测试
    "ErrorCodeType",
    "BusinessException",
    "AuthenticationException",
    "AuthorizationException",
    "ResourceNotFoundException",
    "ResourceConflictException",
    "ValidationException",
    "ServiceUnavailableException",
    "business_exception_handler",
    "validation_exception_handler",
    "http_exception_handler",
    "general_exception_handler",
    "ValidationErrorTranslator",
]
