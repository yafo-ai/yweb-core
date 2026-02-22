"""业务异常类定义

定义框架使用的业务异常类体系。
"""

import copy
from typing import Optional, List, Any, Dict, Union
from fastapi import status
from enum import Enum


class ErrorCode(str, Enum):
    """错误代码枚举
    
    提供常用的错误代码，支持 IDE 补全和拼写检查。
    继承自 str，可以直接作为字符串使用。
    
    使用示例:
        from yweb import ErrorCode, AuthorizationException
        
        # 使用枚举（推荐）
        raise AuthorizationException(
            "需要管理员权限",
            code=ErrorCode.ADMIN_REQUIRED
        )
        
        # 枚举值可以直接比较
        if error_code == ErrorCode.TOKEN_EXPIRED:
            refresh_token()
    
    扩展自定义错误代码:
        # 方式1: 定义应用层枚举（推荐）
        from enum import Enum
        
        class AppErrorCode(str, Enum):
            '''应用自定义错误代码'''
            ORDER_EXPIRED = "ORDER_EXPIRED"
            INSUFFICIENT_STOCK = "INSUFFICIENT_STOCK"
            PAYMENT_TIMEOUT = "PAYMENT_TIMEOUT"
        
        # 使用自定义错误代码
        raise BusinessException("订单已过期", code=AppErrorCode.ORDER_EXPIRED)
        
        # 方式2: 直接使用字符串（简单场景）
        raise BusinessException("自定义错误", code="MY_CUSTOM_ERROR")
    """
    
    # ==================== 通用错误 ====================
    BUSINESS_ERROR = "BUSINESS_ERROR"
    OPERATION_FAILED = "OPERATION_FAILED"
    INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"
    
    # ==================== 认证相关 (401) ====================
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    INVALID_CREDENTIALS = "INVALID_CREDENTIALS"
    INVALID_TOKEN = "INVALID_TOKEN"
    TOKEN_EXPIRED = "TOKEN_EXPIRED"
    TOKEN_REVOKED = "TOKEN_REVOKED"
    
    # ==================== 授权相关 (403) ====================
    AUTHORIZATION_FAILED = "AUTHORIZATION_FAILED"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    ADMIN_REQUIRED = "ADMIN_REQUIRED"
    ROLE_REQUIRED = "ROLE_REQUIRED"
    
    # ==================== 资源相关 (404) ====================
    RESOURCE_NOT_FOUND = "RESOURCE_NOT_FOUND"
    USER_NOT_FOUND = "USER_NOT_FOUND"
    ORDER_NOT_FOUND = "ORDER_NOT_FOUND"
    
    # ==================== 冲突相关 (409) ====================
    RESOURCE_CONFLICT = "RESOURCE_CONFLICT"
    DUPLICATE_ENTRY = "DUPLICATE_ENTRY"
    VERSION_CONFLICT = "VERSION_CONFLICT"
    USERNAME_EXISTS = "USERNAME_EXISTS"
    EMAIL_EXISTS = "EMAIL_EXISTS"
    
    # ==================== 验证相关 (422) ====================
    VALIDATION_ERROR = "VALIDATION_ERROR"
    INVALID_FORMAT = "INVALID_FORMAT"
    INVALID_PARAMETER = "INVALID_PARAMETER"
    
    # ==================== 服务相关 (503) ====================
    SERVICE_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    DATABASE_ERROR = "DATABASE_ERROR"
    EXTERNAL_SERVICE_ERROR = "EXTERNAL_SERVICE_ERROR"
    
    # ==================== 业务相关 ====================
    INSUFFICIENT_BALANCE = "INSUFFICIENT_BALANCE"
    PAYMENT_FAILED = "PAYMENT_FAILED"
    ORDER_CREATE_FAILED = "ORDER_CREATE_FAILED"
    RATE_LIMIT_EXCEEDED = "RATE_LIMIT_EXCEEDED"


# 类型别名，支持枚举和字符串
ErrorCodeType = Union[str, ErrorCode]


class BusinessException(Exception):
    """业务异常基类

    所有业务异常都应该继承此类。

    属性:
        message: 错误消息（面向用户）
        code: 错误代码（用于程序判断，支持 ErrorCode 枚举或字符串）
        status_code: HTTP 状态码
        details: 详细错误信息列表
        extra: 额外的上下文信息

    使用示例:
        # 使用枚举（推荐，有 IDE 补全）
        raise BusinessException("操作失败", code=ErrorCode.OPERATION_FAILED)

        # 抛出带详细信息的异常
        raise BusinessException(
            message="数据验证失败",
            code=ErrorCode.VALIDATION_ERROR,
            details=["字段1不能为空", "字段2格式错误"]
        )

        # 抛出带额外上下文的异常
        raise BusinessException(
            message="订单创建失败",
            code=ErrorCode.ORDER_CREATE_FAILED,
            extra={"order_id": 12345, "reason": "库存不足"}
        )
        
        # 使用自定义错误代码（字符串）
        raise BusinessException("自定义错误", code="MY_CUSTOM_ERROR")
    """

    def __init__(
        self,
        message: str,
        code: ErrorCodeType = ErrorCode.BUSINESS_ERROR,
        status_code: int = status.HTTP_400_BAD_REQUEST,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        """初始化业务异常

        Args:
            message: 错误消息
            code: 错误代码
            status_code: HTTP 状态码
            details: 详细错误信息列表
            **extra: 额外的上下文信息
        """
        self.message = message
        self.code = code
        self.status_code = status_code
        self.details = details or []
        self.extra = extra
        super().__init__(message)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典格式

        Returns:
            包含异常信息的字典
        """
        return {
            "message": self.message,
            "code": self.code,
            "status_code": self.status_code,
            # 返回深拷贝，避免调用方修改返回值反向污染异常对象内部状态
            "details": copy.deepcopy(self.details),
            "extra": copy.deepcopy(self.extra)
        }

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}("
            f"message={self.message!r}, "
            f"code={self.code!r}, "
            f"status_code={self.status_code})"
        )


class AuthenticationException(BusinessException):
    """认证异常

    当用户认证失败时抛出此异常。

    使用示例:
        # 登录失败（使用默认错误代码）
        raise AuthenticationException("用户名或密码错误")

        # Token 无效（使用枚举，推荐）
        raise AuthenticationException("无效的访问令牌", code=ErrorCode.INVALID_TOKEN)

        # Token 过期
        raise AuthenticationException("访问令牌已过期", code=ErrorCode.TOKEN_EXPIRED)
    """

    def __init__(
        self,
        message: str = "认证失败",
        code: ErrorCodeType = ErrorCode.AUTHENTICATION_FAILED,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_401_UNAUTHORIZED,
            details=details,
            **extra
        )


class AuthorizationException(BusinessException):
    """授权异常

    当用户权限不足时抛出此异常。

    使用示例:
        # 权限不足（使用默认错误代码）
        raise AuthorizationException("您没有权限执行此操作")

        # 需要管理员权限（使用枚举，推荐）
        raise AuthorizationException(
            "需要管理员权限",
            code=ErrorCode.ADMIN_REQUIRED,
            details=["当前角色: user", "需要角色: admin"]
        )
    """

    def __init__(
        self,
        message: str = "权限不足",
        code: ErrorCodeType = ErrorCode.AUTHORIZATION_FAILED,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_403_FORBIDDEN,
            details=details,
            **extra
        )


class ResourceNotFoundException(BusinessException):
    """资源不存在异常

    当请求的资源不存在时抛出此异常。

    使用示例:
        # 用户不存在（使用默认错误代码）
        raise ResourceNotFoundException("用户不存在", resource_type="User", resource_id=123)

        # 订单不存在（使用枚举，推荐）
        raise ResourceNotFoundException(
            "订单不存在",
            code=ErrorCode.ORDER_NOT_FOUND,
            resource_type="Order",
            resource_id="ORD123456"
        )
    """

    def __init__(
        self,
        message: str = "资源不存在",
        code: ErrorCodeType = ErrorCode.RESOURCE_NOT_FOUND,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_404_NOT_FOUND,
            details=details,
            **extra
        )


class ResourceConflictException(BusinessException):
    """资源冲突异常

    当资源已存在或发生冲突时抛出此异常。

    使用示例:
        # 用户名已存在（使用默认错误代码）
        raise ResourceConflictException("用户名已被使用", field="username", value="admin")

        # 数据版本冲突（使用枚举，推荐）
        raise ResourceConflictException(
            "数据已被其他用户修改",
            code=ErrorCode.VERSION_CONFLICT,
            details=["请刷新后重试"]
        )
    """

    def __init__(
        self,
        message: str = "资源冲突",
        code: ErrorCodeType = ErrorCode.RESOURCE_CONFLICT,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_409_CONFLICT,
            details=details,
            **extra
        )


class ValidationException(BusinessException):
    """数据验证异常

    当数据验证失败时抛出此异常。

    使用示例:
        # 单个字段验证失败（使用默认错误代码）
        raise ValidationException("手机号格式不正确", field="phone")

        # 多个字段验证失败
        raise ValidationException(
            "数据验证失败",
            code=ErrorCode.VALIDATION_ERROR,
            details=[
                "用户名长度必须在3-20个字符之间",
                "密码必须包含字母和数字"
            ]
        )
    """

    def __init__(
        self,
        message: str = "数据验证失败",
        code: ErrorCodeType = ErrorCode.VALIDATION_ERROR,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            details=details,
            **extra
        )


class ServiceUnavailableException(BusinessException):
    """服务不可用异常

    当依赖的服务不可用时抛出此异常。

    使用示例:
        # 数据库连接失败（使用默认错误代码）
        raise ServiceUnavailableException("数据库连接失败", service="database")

        # 第三方API不可用（使用枚举，推荐）
        raise ServiceUnavailableException(
            "支付服务暂时不可用",
            code=ErrorCode.EXTERNAL_SERVICE_ERROR,
            service="payment_gateway"
        )
    """

    def __init__(
        self,
        message: str = "服务暂时不可用",
        code: ErrorCodeType = ErrorCode.SERVICE_UNAVAILABLE,
        details: Optional[List[str]] = None,
        **extra: Any
    ):
        super().__init__(
            message=message,
            code=code,
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            details=details,
            **extra
        )


class Err:
    """异常快捷创建类
    
    提供统一入口，通过 IDE 自动补全发现所有可用的异常类型。
    只需导入一个类，即可创建所有类型的业务异常。
    
    使用示例:
        from yweb import Err
        
        # 认证失败 (401)
        raise Err.auth("用户名或密码错误")
        
        # 权限不足 (403)
        raise Err.forbidden("需要管理员权限")
        
        # 资源不存在 (404)
        raise Err.not_found("用户不存在", resource_type="User", resource_id=123)
        
        # 资源冲突 (409)
        raise Err.conflict("用户名已存在", field="username")
        
        # 数据验证失败 (422)
        raise Err.invalid("数据验证失败", details=["用户名不能为空"])
        
        # 服务不可用 (503)
        raise Err.unavailable("数据库连接失败")
        
        # 通用业务异常 (400)
        raise Err.fail("操作失败")
        
        # 支持自定义错误码
        raise Err.auth("Token已过期", code=ErrorCode.TOKEN_EXPIRED)
    """
    
    @staticmethod
    def auth(message: str = "认证失败", **kwargs) -> AuthenticationException:
        """认证失败 (401)
        
        适用场景: 登录失败、Token 无效、Token 过期等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details 等）
        """
        return AuthenticationException(message, **kwargs)
    
    @staticmethod
    def forbidden(message: str = "权限不足", **kwargs) -> AuthorizationException:
        """权限不足 (403)
        
        适用场景: 无权访问、需要更高权限等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details 等）
        """
        return AuthorizationException(message, **kwargs)
    
    @staticmethod
    def not_found(message: str = "资源不存在", **kwargs) -> ResourceNotFoundException:
        """资源不存在 (404)
        
        适用场景: 用户不存在、订单不存在、数据未找到等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details, resource_type, resource_id 等）
        """
        return ResourceNotFoundException(message, **kwargs)
    
    @staticmethod
    def conflict(message: str = "资源冲突", **kwargs) -> ResourceConflictException:
        """资源冲突 (409)
        
        适用场景: 用户名已存在、数据版本冲突、重复操作等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details, field, value 等）
        """
        return ResourceConflictException(message, **kwargs)
    
    @staticmethod
    def invalid(message: str = "数据验证失败", **kwargs) -> ValidationException:
        """数据验证失败 (422)
        
        适用场景: 参数格式错误、数据校验不通过等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details 等）
        """
        return ValidationException(message, **kwargs)
    
    @staticmethod
    def unavailable(message: str = "服务暂时不可用", **kwargs) -> ServiceUnavailableException:
        """服务不可用 (503)
        
        适用场景: 数据库连接失败、第三方服务不可用等
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details, service 等）
        """
        return ServiceUnavailableException(message, **kwargs)
    
    @staticmethod
    def fail(message: str = "操作失败", **kwargs) -> BusinessException:
        """通用业务异常 (400)
        
        适用场景: 其他业务逻辑错误
        
        Args:
            message: 错误消息
            **kwargs: 额外参数（code, details 等）
        """
        return BusinessException(message, **kwargs)
