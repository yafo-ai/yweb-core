"""全局异常处理器

提供 FastAPI 全局异常处理器，自动将异常转换为统一的 JSON 响应格式。
"""

from fastapi import Request, status
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from typing import Dict, Callable, Optional
import traceback
import sys
import os

from yweb.log import get_logger
from yweb.response import ResponseStatus, ValidationErrorResponse
from .exceptions import BusinessException

# 创建日志记录器
logger = get_logger()


# ==================== 验证错误翻译器 ====================

class ValidationErrorTranslator:
    """验证错误翻译器
    
    提供优雅的扩展机制，让应用可以轻松添加自定义错误翻译。
    
    使用示例:
        # 方式1: 添加静态错误映射
        ValidationErrorTranslator.add_messages({
            "value_error.phone": "手机号格式不正确",
            "value_error.id_card": "身份证号格式不正确",
        })
        
        # 方式2: 注册动态翻译函数（需要访问上下文）
        @ValidationErrorTranslator.translator("value_error.custom")
        def translate_custom(ctx: dict) -> str:
            return f"自定义错误，期望: {ctx.get('expected')}"
        
        # 方式3: 批量注册（适合从配置文件加载）
        ValidationErrorTranslator.configure({
            "messages": {"value_error.xxx": "xxx错误"},
            "fallback_translations": {
                "must be": "必须是",
                "invalid": "无效的",
            }
        })
    """
    
    # 自定义错误消息映射（静态）
    _custom_messages: Dict[str, str] = {}
    
    # 动态翻译函数映射
    _translators: Dict[str, Callable[[dict], str]] = {}
    
    # 回退翻译（英文短语 -> 中文）
    _fallback_translations: Dict[str, str] = {
        "Field required": "此字段为必填项",
        "Input should be": "输入值应该是",
        "String should have at least": "字符串长度不能少于",
        "String should have at most": "字符串长度不能超过",
        "characters": "个字符",
        "Value error,": "值错误:",
        "Invalid": "无效的",
        "is not a valid": "不是有效的",
        "greater than or equal to": "大于或等于",
        "less than or equal to": "小于或等于",
        "greater than": "大于",
        "less than": "小于",
    }
    
    # 框架内置错误消息（Pydantic v2）
    _builtin_messages: Dict[str, str] = {
        # ==================== 必填/缺失 ====================
        "missing": "此字段为必填项",
        "value_error.missing": "此字段为必填项",
        
        # ==================== 类型错误 ====================
        "int_type": "必须是整数",
        "float_type": "必须是数字",
        "bool_type": "必须是布尔值",
        "str_type": "必须是字符串",
        "list_type": "必须是列表",
        "dict_type": "必须是对象",
        "type_error.integer": "必须是整数",
        "type_error.float": "必须是数字",
        "type_error.string": "必须是字符串",
        "type_error.bool": "必须是布尔值",
        "type_error.list": "必须是列表",
        "type_error.dict": "必须是对象",
        "type_error.none.not_allowed": "不能为空",
        
        # ==================== 字符串验证 ====================
        "string_pattern_mismatch": "格式不正确",
        "value_error.str.regex": "格式不正确",
        
        # ==================== 格式验证 ====================
        "value_error.email": "邮箱格式不正确",
        "value_error.url": "URL 格式不正确",
        "value_error.url.scheme": "URL 格式不正确",
        "value_error.url.host": "URL 格式不正确",
        "url_parsing": "URL 格式不正确",
        "url_scheme": "URL 协议不正确",
        
        # ==================== 日期时间验证 ====================
        "datetime_parsing": "日期时间格式不正确",
        "date_parsing": "日期格式不正确",
        "time_parsing": "时间格式不正确",
        "datetime_from_date_parsing": "日期时间格式不正确",
        "date_from_datetime_parsing": "日期格式不正确",
        "time_delta_parsing": "时间间隔格式不正确",
        "timezone_naive": "需要包含时区信息",
        "timezone_aware": "不能包含时区信息",
        
        # ==================== UUID 验证 ====================
        "uuid_parsing": "UUID 格式不正确",
        "uuid_type": "必须是有效的 UUID",
        
        # ==================== JSON 验证 ====================
        "json_invalid": "JSON 格式不正确",
        "json_type": "必须是有效的 JSON",
        
        # ==================== 字节验证 ====================
        "bytes_type": "必须是字节类型",
        
        # ==================== 其他常见错误 ====================
        "value_error": "值无效",
        "assertion_error": "断言验证失败",
        "frozen_field": "此字段不可修改",
        "frozen_instance": "此对象不可修改",
        "extra_forbidden": "不允许额外的字段",
        "model_type": "必须是有效的对象",
        "model_attributes_type": "对象属性格式不正确",
        "dataclass_type": "必须是有效的数据类",
        "union_tag_invalid": "类型标签无效",
        "union_tag_not_found": "缺少类型标签",
    }
    
    @classmethod
    def add_messages(cls, messages: Dict[str, str]) -> None:
        """添加自定义错误消息映射
        
        Args:
            messages: 错误类型 -> 中文消息 的映射字典
            
        Example:
            ValidationErrorTranslator.add_messages({
                "value_error.phone": "手机号格式不正确",
                "value_error.id_card": "身份证号格式不正确",
            })
        """
        cls._custom_messages.update(messages)
    
    @classmethod
    def translator(cls, error_type: str):
        """装饰器：注册动态翻译函数
        
        Args:
            error_type: 要处理的错误类型
            
        Example:
            @ValidationErrorTranslator.translator("value_error.custom")
            def translate_custom(ctx: dict) -> str:
                return f"值必须在 {ctx.get('min')} 到 {ctx.get('max')} 之间"
        """
        def decorator(func: Callable[[dict], str]):
            cls._translators[error_type] = func
            return func
        return decorator
    
    @classmethod
    def add_fallback_translations(cls, translations: Dict[str, str]) -> None:
        """添加回退翻译（英文短语 -> 中文）
        
        Args:
            translations: 英文短语 -> 中文 的映射
            
        Example:
            ValidationErrorTranslator.add_fallback_translations({
                "must be positive": "必须为正数",
                "cannot be empty": "不能为空",
            })
        """
        cls._fallback_translations.update(translations)
    
    @classmethod
    def configure(cls, config: dict) -> None:
        """批量配置（适合从配置文件加载）
        
        Args:
            config: 配置字典，支持以下键：
                - messages: 静态错误消息映射
                - fallback_translations: 回退翻译映射
                
        Example:
            ValidationErrorTranslator.configure({
                "messages": {
                    "value_error.phone": "手机号格式不正确",
                },
                "fallback_translations": {
                    "invalid format": "格式无效",
                }
            })
        """
        if "messages" in config:
            cls.add_messages(config["messages"])
        if "fallback_translations" in config:
            cls.add_fallback_translations(config["fallback_translations"])
    
    # 需要上下文的错误类型模板
    _context_message_templates: Dict[str, str] = {
        "string_too_short": "长度不能少于 {min_length} 个字符",
        "string_too_long": "长度不能超过 {max_length} 个字符",
        "greater_than": "必须大于 {gt}",
        "greater_than_equal": "必须大于或等于 {ge}",
        "less_than": "必须小于 {lt}",
        "less_than_equal": "必须小于或等于 {le}",
        "multiple_of": "必须是 {multiple_of} 的倍数",
        "too_short": "元素数量不能少于 {min_length} 个",
        "too_long": "元素数量不能超过 {max_length} 个",
        "uuid_version": "UUID 版本必须是 {expected_version}",
        "bytes_too_short": "字节长度不能少于 {min_length}",
        "bytes_too_long": "字节长度不能超过 {max_length}",
        "value_error.any_str.min_length": "长度不能少于 {limit_value} 个字符",
        "value_error.any_str.max_length": "长度不能超过 {limit_value} 个字符",
        "value_error.number.not_gt": "必须大于 {limit_value}",
        "value_error.number.not_ge": "必须大于或等于 {limit_value}",
        "value_error.number.not_lt": "必须小于 {limit_value}",
        "value_error.number.not_le": "必须小于或等于 {limit_value}",
    }
    
    @classmethod
    def _format_context_message(cls, template: str, ctx: dict) -> str:
        """格式化带上下文的消息模板"""
        # 使用安全的格式化，缺失的键用 '?' 代替
        try:
            return template.format_map({k: ctx.get(k, '?') for k in ctx} | 
                                       {k: '?' for k in ['min_length', 'max_length', 'gt', 'ge', 'lt', 'le', 
                                                         'multiple_of', 'expected_version', 'limit_value']})
        except (KeyError, ValueError):
            return template
    
    @classmethod
    def translate(cls, error_type: str, error: dict) -> Optional[str]:
        """翻译验证错误
        
        翻译优先级：
        1. 自定义消息映射
        2. 动态翻译函数
        3. 内置消息映射（需要上下文的）
        4. 内置消息映射（静态的）
        
        Args:
            error_type: Pydantic 错误类型
            error: 完整的错误信息字典
            
        Returns:
            翻译后的中文消息，如果无法翻译则返回 None
        """
        ctx = error.get("ctx", {})
        
        # 1. 优先使用自定义消息
        if error_type in cls._custom_messages:
            return cls._custom_messages[error_type]
        
        # 2. 尝试动态翻译函数
        if error_type in cls._translators:
            return cls._translators[error_type](ctx)
        
        # 3. 处理需要上下文的内置错误类型
        if error_type in cls._context_message_templates:
            template = cls._context_message_templates[error_type]
            return cls._format_context_message(template, ctx)
        
        # 特殊处理：enum 和 literal_error 需要拼接列表
        if error_type in ("enum", "literal_error"):
            expected = ctx.get("expected", [])
            return f"值必须是以下之一: {', '.join(str(v) for v in expected)}"
        
        # 4. 使用内置静态消息
        if error_type in cls._builtin_messages:
            return cls._builtin_messages[error_type]
        
        return None
    
    @classmethod
    def fallback_translate(cls, msg: str) -> str:
        """回退翻译：替换英文短语为中文
        
        Args:
            msg: 原始英文消息
            
        Returns:
            部分翻译后的消息
        """
        for en, zh in cls._fallback_translations.items():
            msg = msg.replace(en, zh)
        return msg


# 简化别名，方便内部使用
_translate = ValidationErrorTranslator.translate


async def business_exception_handler(
    request: Request,
    exc: BusinessException
) -> JSONResponse:
    """业务异常处理器

    处理所有继承自 BusinessException 的异常，转换为统一的 JSON 响应。

    Args:
        request: FastAPI 请求对象
        exc: 业务异常实例

    Returns:
        JSON 响应
    """
    # 获取请求ID（如果有）
    request_id = getattr(request.state, "request_id", "unknown")

    # 记录警告日志
    logger.warning(
        f"Business exception occurred: {exc.code} - {exc.message}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_code": exc.code,
            "status_code": exc.status_code,
            "details": exc.details,
            "extra": exc.extra
        }
    )

    # 构造响应内容
    content = {
        "status": ResponseStatus.ERROR.value,
        "message": exc.message,
        "msg_details": exc.details,
        "data": {}
    }

    # 如果有错误代码，添加到响应中
    if exc.code:
        content["error_code"] = exc.code

    # 如果有额外信息且在调试模式，添加到响应中
    is_debug = os.getenv("DEBUG", "false").lower() == "true"
    if is_debug and exc.extra:
        content["debug_info"] = exc.extra

    return JSONResponse(
        status_code=exc.status_code,
        content=content
    )


async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError
) -> JSONResponse:
    """Pydantic 验证异常处理器

    处理 FastAPI 的请求参数验证异常，转换为友好的中文错误消息。
    
    支持的验证类型（类似 .NET MVC 特性）：
    - Required: 必填验证
    - MinLength/MaxLength: 长度验证  
    - Range (ge/le/gt/lt): 范围验证
    - EmailAddress: 邮箱验证
    - URL: URL 验证
    - RegularExpression: 正则验证
    - 类型验证: 整数、字符串、布尔等

    Args:
        request: FastAPI 请求对象
        exc: Pydantic 验证异常

    Returns:
        JSON 响应
    """
    # 获取请求ID
    request_id = getattr(request.state, "request_id", "unknown")

    # 提取验证错误信息
    errors = []
    for error in exc.errors():
        # 获取字段路径（排除 body/query/path 等前缀）
        loc_parts = [str(loc) for loc in error["loc"] if loc not in ("body", "query", "path", "header", "cookie")]
        field = ".".join(loc_parts) if loc_parts else "请求体"
        
        # 获取错误类型和原始消息
        error_type = error["type"]
        original_msg = error["msg"]
        
        # 尝试翻译为中文
        translated_msg = _translate(error_type, error)
        
        if translated_msg:
            errors.append(f"{field}: {translated_msg}")
        else:
            # 未匹配的错误类型，使用回退翻译
            msg = ValidationErrorTranslator.fallback_translate(original_msg)
            errors.append(f"{field}: {msg}")

    # 记录警告日志
    logger.warning(
        f"Validation error: {len(errors)} field(s) failed validation",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "errors": errors
        }
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "status": ResponseStatus.ERROR.value,
            "message": "请求参数验证失败",
            "msg_details": errors,
            "data": {},
            "error_code": "VALIDATION_ERROR"
        }
    )


async def http_exception_handler(
    request: Request,
    exc: StarletteHTTPException
) -> JSONResponse:
    """HTTP 异常处理器

    处理 FastAPI/Starlette 的 HTTPException。

    Args:
        request: FastAPI 请求对象
        exc: HTTP 异常

    Returns:
        JSON 响应
    """
    # 获取请求ID
    request_id = getattr(request.state, "request_id", "unknown")

    # 记录日志
    log_level = "warning" if exc.status_code < 500 else "error"
    getattr(logger, log_level)(
        f"HTTP exception: {exc.status_code} - {exc.detail}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code
        }
    )

    return JSONResponse(
        status_code=exc.status_code,
        content={
            "status": ResponseStatus.ERROR.value,
            "message": str(exc.detail),
            "msg_details": [],
            "data": {},
            "error_code": f"HTTP_{exc.status_code}"
        }
    )


async def general_exception_handler(
    request: Request,
    exc: Exception
) -> JSONResponse:
    """通用异常处理器

    捕获所有未被其他处理器处理的异常，记录完整堆栈信息。
    这是最后一道防线，确保不会向用户暴露原始异常。

    Args:
        request: FastAPI 请求对象
        exc: 异常实例

    Returns:
        JSON 响应
    """
    # 获取请求ID
    request_id = getattr(request.state, "request_id", "unknown")

    # 获取完整的异常堆栈信息
    exc_type, exc_value, exc_traceback = sys.exc_info()
    tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
    full_traceback = "".join(tb_lines)

    # 记录详细的错误日志（包含完整堆栈）
    logger.error(
        f"Unhandled exception: {type(exc).__name__}: {str(exc)}",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": full_traceback
        }
    )

    # 判断是否为调试模式
    is_debug = os.getenv("DEBUG", "false").lower() == "true"

    # 构造响应内容
    content = {
        "status": ResponseStatus.ERROR.value,
        "message": "服务器内部错误",
        "msg_details": [],
        "data": {},
        "error_code": "INTERNAL_SERVER_ERROR"
    }

    # 调试模式下返回详细错误信息
    if is_debug:
        content["msg_details"] = [
            f"异常类型: {type(exc).__name__}",
            f"异常消息: {str(exc)}"
        ]
        content["debug_info"] = {
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": tb_lines[-5:]  # 只返回最后5行堆栈
        }

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content
    )


def register_exception_handlers(app) -> None:
    """注册所有异常处理器到 FastAPI 应用

    这个函数会注册以下异常处理器：
    1. BusinessException - 业务异常处理器
    2. RequestValidationError - 参数验证异常处理器
    3. HTTPException - HTTP 异常处理器
    4. Exception - 通用异常处理器（兜底）

    使用示例:
        from fastapi import FastAPI
        from yweb.exceptions import register_exception_handlers

        app = FastAPI()
        register_exception_handlers(app)

    Args:
        app: FastAPI 应用实例
    """
    # 注册业务异常处理器
    app.add_exception_handler(BusinessException, business_exception_handler)

    # 注册参数验证异常处理器
    app.add_exception_handler(RequestValidationError, validation_exception_handler)

    # 注册 HTTP 异常处理器
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    # 注册通用异常处理器（必须放在最后）
    app.add_exception_handler(Exception, general_exception_handler)

    # 覆盖 OpenAPI 默认的 422 响应 Schema，与实际验证错误处理器一致
    app.router.responses[422] = {
        "description": "请求参数验证失败",
        "model": ValidationErrorResponse,
    }

    logger.info("Exception handlers registered successfully")
