"""响应模块

推荐使用示例（Resp 快捷类）:
    from yweb import Resp
    
    return Resp.OK(data=result)
    return Resp.NotFound(message="用户不存在")
    return Resp.BadRequest(message="参数错误")

传统使用示例（单独导入）:
    from yweb import OK, NotFound, BadRequest
    
    return OK(data=result)
    return NotFound(message="用户不存在")
"""

from .base_response import (
    # ===== 推荐使用 =====
    Resp,                       # 响应快捷类
    
    # 响应状态枚举
    ResponseStatus,
    
    # 泛型响应模型
    PageData,
    PageResponse,
    ItemResponse,
    OkResponse,
    ValidationErrorResponse,
    
    # 基础响应类（高级用法）
    BaseResponse,
    SuccessResponse,
    ExtendedResponse,
    ClientErrorResponse,
    ServerErrorResponse,
    
    # 简化别名（高级用法）
    OK,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    InternalServerError,
    Conflict,
    TooManyRequests,
    Warning,
    Info,
    
    # 文档模型生成工具
    create_item_model,
    create_page_model,
    create_response_model,
)

__all__ = [
    # ===== 推荐使用 =====
    "Resp",                     # 响应快捷类：Resp.OK, Resp.NotFound 等
    
    # 响应状态枚举
    "ResponseStatus",
    
    # 泛型响应模型
    "PageData",
    "PageResponse",
    "ItemResponse",
    "OkResponse",
    "ValidationErrorResponse",
    
    # 基础响应类（高级用法）
    "BaseResponse",
    "SuccessResponse",
    "ExtendedResponse",
    "ClientErrorResponse",
    "ServerErrorResponse",
    
    # 简化别名（高级用法）
    "OK",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "InternalServerError",
    "Conflict",
    "TooManyRequests",
    "Warning",
    "Info",
    
    # 文档模型生成工具
    "create_item_model",
    "create_page_model",
    "create_response_model",
]
