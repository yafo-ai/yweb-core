from fastapi import status
from fastapi.responses import JSONResponse
from typing import Any, Optional, Dict, List, Type, TypeVar, Generic
from datetime import datetime
from enum import Enum
from pydantic import BaseModel, Field, create_model


# 泛型类型变量
T = TypeVar('T')


class ResponseStatus(str, Enum):
    """响应状态枚举
    
    用于标识响应的业务状态，与 HTTP 状态码独立。
    
    使用示例:
        from yweb.response import ResponseStatus
        
        # 判断响应状态
        if response_data["status"] == ResponseStatus.SUCCESS:
            ...
        
        # 在自定义响应中使用
        content = {"status": ResponseStatus.WARNING, ...}
    """
    SUCCESS = "success"   # 请求成功
    ERROR = "error"       # 请求失败（客户端或服务端错误）
    WARNING = "warning"   # 操作成功但有警告
    INFO = "info"         # 信息性响应


# ========== 泛型响应模型 ==========

class PageData(BaseModel, Generic[T]):
    """泛型分页数据模型
    
    使用示例:
        from yweb.response import PageData
        
        class UserItem(BaseModel):
            id: int
            username: str
        
        class UserPageData(PageData[UserItem]):
            pass
    """
    rows: List[T] = Field(description="数据列表")
    total_records: int = Field(description="总记录数")
    page: int = Field(description="当前页码")
    page_size: int = Field(description="每页数量")
    total_pages: int = Field(description="总页数")
    has_prev: bool = Field(description="是否有上一页")
    has_next: bool = Field(description="是否有下一页")


class PageResponse(BaseModel, Generic[T]):
    """泛型分页响应模型
    
    使用示例:
        from yweb.response import PageResponse
        
        class UserItem(BaseModel):
            id: int
            username: str
        
        # 方式1：直接使用泛型
        @router.get("", response_model=PageResponse[UserItem])
        def get_users():
            ...
        
        # 方式2：创建具体类型
        class UserResponse(PageResponse[UserItem]):
            pass
        
        @router.get("", response_model=UserResponse)
        def get_users():
            ...
    """
    status: str = Field(default="success", description="响应状态")
    message: str = Field(default="请求成功", description="响应消息")
    msg_details: List[str] = Field(default=[], description="详细信息")
    data: PageData[T] = Field(description="分页数据")


class ItemResponse(BaseModel, Generic[T]):
    """泛型单项响应模型
    
    使用示例:
        from yweb.response import ItemResponse
        
        class UserItem(BaseModel):
            id: int
            username: str
        
        @router.get("/{id}", response_model=ItemResponse[UserItem])
        def get_user(id: int):
            ...
    """
    status: str = Field(default="success", description="响应状态")
    message: str = Field(default="请求成功", description="响应消息")
    msg_details: List[str] = Field(default=[], description="详细信息")
    data: T = Field(description="数据")


class ValidationErrorResponse(BaseModel):
    """验证错误响应模型（422）
    
    描述 Pydantic 参数校验失败时的实际响应格式，
    用于覆盖 FastAPI 默认的 422 OpenAPI Schema。
    
    使用示例:
        # 通常不需要手动使用，由 register_exception_handlers 自动注册
        app.router.responses[422] = {
            "description": "请求参数验证失败",
            "model": ValidationErrorResponse,
        }
    """
    status: str = Field(default="error", description="响应状态")
    message: str = Field(default="请求参数验证失败", description="错误消息")
    msg_details: List[str] = Field(default=[], description="各字段验证错误详情")
    data: dict = Field(default={}, description="空数据")
    error_code: str = Field(default="VALIDATION_ERROR", description="错误码")


class OkResponse(BaseModel):
    """通用操作响应模型（删除、移除、设置等简单操作）
    
    适用于返回简单 dict 的操作接口，如 delete、remove、set-primary 等。
    
    使用示例:
        from yweb.response import OkResponse
        
        @router.post("/delete", response_model=OkResponse)
        def delete_item(id: int):
            ...
            return Resp.OK(data={"id": id}, message="删除成功")
    """
    status: str = Field(default="success", description="响应状态")
    message: str = Field(default="请求成功", description="响应消息")
    msg_details: List[str] = Field(default=[], description="详细信息")
    data: dict = Field(default={}, description="操作结果")


# ========== 文档模型生成工具 ==========

# SQLAlchemy 类型到 Python 类型的映射
_TYPE_MAP = {
    'INTEGER': int,
    'BIGINT': int,
    'SMALLINT': int,
    'VARCHAR': str,
    'TEXT': str,
    'STRING': str,
    'BOOLEAN': bool,
    'DATETIME': str,  # 序列化后是字符串
    'DATE': str,
    'FLOAT': float,
    'NUMERIC': float,
}


def _get_python_type(sa_type) -> Type:
    """从 SQLAlchemy 列类型获取 Python 类型"""
    type_name = type(sa_type).__name__.upper()
    return _TYPE_MAP.get(type_name, Any)


def create_item_model(model_class, name: str = None, include_fields: List[str] = None) -> Type[BaseModel]:
    """从 SQLAlchemy 模型自动创建 Pydantic 文档模型
    
    Args:
        model_class: SQLAlchemy 模型类
        name: 生成的模型名称，默认为 "{模型名}Item"
        include_fields: 要包含的字段列表，默认为 None 表示所有字段
    
    Returns:
        动态生成的 Pydantic 模型类
    """
    if name is None:
        name = f"{model_class.__name__}Item"
    
    fields = {}
    for column in model_class.__table__.columns:
        # 如果指定了字段列表，只包含指定的字段
        if include_fields is not None and column.name not in include_fields:
            continue
            
        python_type = _get_python_type(column.type)
        # 处理可空字段
        if column.nullable:
            python_type = Optional[python_type]
        # 获取字段注释作为描述
        description = column.comment or column.name
        fields[column.name] = (python_type, Field(description=description))
    
    return create_model(name, **fields)


def create_page_model(item_model: Type[BaseModel], name: str = None) -> Type[BaseModel]:
    """创建分页数据模型
    
    Args:
        item_model: 数据项的 Pydantic 模型
        name: 生成的模型名称
    """
    if name is None:
        name = f"{item_model.__name__.replace('Item', '')}PageData"
    
    return create_model(
        name,
        rows=(List[item_model], Field(description="数据列表")),
        total_records=(int, Field(description="总记录数")),
        page=(int, Field(description="当前页码")),
        page_size=(int, Field(description="每页数量")),
        total_pages=(int, Field(description="总页数")),
        has_prev=(bool, Field(description="是否有上一页")),
        has_next=(bool, Field(description="是否有下一页")),
    )


def create_response_model(model_class, name: str = None, include_fields: List[str] = None) -> Type[BaseModel]:
    """从 SQLAlchemy 模型自动创建完整的 BaseResponse 格式文档模型（分页）
    
    Args:
        model_class: SQLAlchemy 模型类
        name: 生成的响应模型名称
        include_fields: 要包含的字段列表，默认为 None 表示所有字段
    
    Returns:
        完整的响应模型，包含 message, msg_details, data(分页格式)
        
    Usage:
        from yweb.response import create_response_model
        from your_app.models import YourModel
        
        # 返回所有字段
        YourModelResponse = create_response_model(YourModel)
        
        # 只返回指定字段
        YourModelResponse = create_response_model(
            YourModel, 
            include_fields=['id', 'name', 'created_at']
        )
        
        @router.get("", response_model=YourModelResponse)
        def get_records():
            ...
    """
    if name is None:
        name = f"{model_class.__name__}Response"
    
    item_model = create_item_model(model_class, include_fields=include_fields)
    page_model = create_page_model(item_model)
    
    return create_model(
        name,
        status=(str, Field(default=ResponseStatus.SUCCESS.value, description="响应状态")),
        message=(str, Field(default="请求成功", description="响应消息")),
        msg_details=(List[str], Field(default=[], description="详细信息")),
        data=(page_model, Field(description="分页数据")),
    )

# 基础响应模型
class BaseResponse:
    """基础响应类"""
    
    @staticmethod
    def _serialize_data(data: Any, _is_top_level: bool = True) -> Any:
        """递归序列化数据，处理DTO对象、SQLAlchemy模型和列表
        
        Args:
            data: 要序列化的数据
            _is_top_level: 是否为顶层调用，顶层 None 转为 {}，嵌套 None 保持为 None
        """
        if data is None:
            return {} if _is_top_level else None
        
        # 处理 datetime 对象
        if isinstance(data, datetime):
            return data.strftime('%Y-%m-%d %H:%M:%S')
        
        # 处理 SQLAlchemy Row 对象（with_entities 查询返回的结果）
        if hasattr(data, '_mapping'):
            return {k: BaseResponse._serialize_data(v, False) for k, v in data._mapping.items()}
        
        # 如果是 SQLAlchemy 模型对象（有 __table__ 属性），转换为字典
        if hasattr(data, '__table__'):
            result = {}
            for column in data.__table__.columns:
                value = getattr(data, column.name, None)
                result[column.name] = BaseResponse._serialize_data(value, False)
            return result
        
        # 如果是DTO对象，调用to_dict后继续递归处理
        if hasattr(data, 'to_dict') and callable(getattr(data, 'to_dict')):
            return BaseResponse._serialize_data(data.to_dict(), False)
        
        # 如果是列表，递归处理每个元素
        if isinstance(data, list):
            return [BaseResponse._serialize_data(item, False) for item in data]
        
        # 如果是字典，递归处理每个值
        if isinstance(data, dict):
            return {k: BaseResponse._serialize_data(v, False) for k, v in data.items()}
        
        # 其他类型直接返回
        return data
    
    @staticmethod
    def _create_response(
        message: str,
        data: Any = None,
        msg_details: Optional[List[str]] = None,
        status_code: int = status.HTTP_200_OK,
        response_status: ResponseStatus = ResponseStatus.SUCCESS
    ) -> JSONResponse:
        """创建标准化响应"""
        # 自动处理DTO对象序列化（支持单个对象、列表、嵌套结构）
        serialized_data = BaseResponse._serialize_data(data)
        
        content = {
            "status": response_status.value,
            "message": message,
            "msg_details": msg_details if msg_details is not None else [],
            "data": serialized_data
        }
            
        return JSONResponse(
            status_code=status_code,
            content=content
        )

# 成功响应 (2xx)
class SuccessResponse(BaseResponse):
    """成功响应类"""
    
    @staticmethod
    def OK(data: Any = None, message: str = "请求成功") -> JSONResponse:
        """200 OK - 请求成功"""
        return BaseResponse._create_response(
            data=data,
            message=message,
            status_code=status.HTTP_200_OK,
            response_status=ResponseStatus.SUCCESS
        )

# 扩展响应方法
class ExtendedResponse(BaseResponse):
    """扩展响应类 - 用于复杂的业务状态，但仍遵循统一的JSON格式"""
    
    @staticmethod
    def Warning(message: str = "操作成功，但有警告", data: Any = None, msg_details: Optional[List[str]] = None) -> JSONResponse:
        """警告响应 - 操作成功但有警告信息"""
        return BaseResponse._create_response(
            message=message,
            data=data,
            msg_details=msg_details,
            status_code=status.HTTP_200_OK,
            response_status=ResponseStatus.WARNING
        )
    
    @staticmethod
    def Info(message: str = "信息提示", data: Any = None) -> JSONResponse:
        """信息响应 - 纯信息性响应"""
        return BaseResponse._create_response(
            message=message,
            data=data,
            status_code=status.HTTP_200_OK,
            response_status=ResponseStatus.INFO
        )    


# 客户端错误响应 (4xx)
class ClientErrorResponse(BaseResponse):
    """客户端错误响应类"""
    
    @staticmethod
    def BadRequest(message: str = "请求参数错误", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """400 Bad Request - 请求参数错误"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_400_BAD_REQUEST,
            response_status=ResponseStatus.ERROR
        )
    
    @staticmethod
    def Unauthorized(message: str = "未授权访问", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """401 Unauthorized - 未授权"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_401_UNAUTHORIZED,
            response_status=ResponseStatus.ERROR
        )
    
    @staticmethod
    def Forbidden(message: str = "禁止访问", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """403 Forbidden - 禁止访问"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_403_FORBIDDEN,
            response_status=ResponseStatus.ERROR
        )
    
    @staticmethod
    def NotFound(message: str = "资源不存在", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """404 Not Found - 资源不存在"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_404_NOT_FOUND,
            response_status=ResponseStatus.ERROR
        )
    
    @staticmethod
    def Conflict(message: str = "资源冲突", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """409 Conflict - 资源冲突"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_409_CONFLICT,
            response_status=ResponseStatus.ERROR
        )
    
    @staticmethod
    def TooManyRequests(message: str = "请求过于频繁", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """429 Too Many Requests - 请求过于频繁"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            response_status=ResponseStatus.ERROR
        )

# 服务端错误响应 (5xx)
class ServerErrorResponse(BaseResponse):
    """服务端错误响应类"""
    
    @staticmethod
    def InternalServerError(message: str = "服务器内部错误", msg_details: Optional[List[str]] = None) -> JSONResponse:
        """500 Internal Server Error - 服务器内部错误"""
        return BaseResponse._create_response(
            message=message,
            msg_details=msg_details,
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            response_status=ResponseStatus.ERROR
        )


# 简化别名（最常用的）
OK = SuccessResponse.OK
BadRequest = ClientErrorResponse.BadRequest
Unauthorized = ClientErrorResponse.Unauthorized
Forbidden = ClientErrorResponse.Forbidden
NotFound = ClientErrorResponse.NotFound
InternalServerError = ServerErrorResponse.InternalServerError
Conflict = ClientErrorResponse.Conflict
TooManyRequests = ClientErrorResponse.TooManyRequests

# 扩展响应别名（简化命名）
Warning = ExtendedResponse.Warning
Info = ExtendedResponse.Info


# ==================== 响应快捷类（推荐） ====================

class Resp:
    """响应快捷类
    
    只需导入一个类，IDE 自动补全所有响应方法。
    
    使用示例:
        from yweb import Resp
        
        # 成功响应
        return Resp.OK(data=result)
        return Resp.OK(data={"user": user}, message="获取成功")
        
        # 错误响应
        return Resp.NotFound(message="用户不存在")
        return Resp.BadRequest(message="参数错误", msg_details=["name 不能为空"])
        return Resp.Unauthorized(message="请先登录")
        
        # 扩展响应
        return Resp.Warning(message="操作成功，但有警告", data=result)
    """
    
    # ===== 成功响应 =====
    OK = OK
    """200 OK - 请求成功
    
    参数:
        data: 响应数据
        message: 响应消息，默认 "请求成功"
    """
    
    # ===== 扩展响应 =====
    Warning = Warning
    """警告响应 - 操作成功但有警告信息
    
    参数:
        message: 警告消息
        data: 响应数据（可选）
        msg_details: 详细信息列表（可选）
    """
    
    Info = Info
    """信息响应 - 附带额外提示信息
    
    参数:
        message: 提示消息
        data: 响应数据（可选）
        msg_details: 详细信息列表（可选）
    """
    
    # ===== 客户端错误 (4xx) =====
    BadRequest = BadRequest
    """400 Bad Request - 请求参数错误
    
    参数:
        message: 错误消息，默认 "请求参数错误"
        msg_details: 详细错误列表（可选）
    """
    
    Unauthorized = Unauthorized
    """401 Unauthorized - 未授权访问
    
    参数:
        message: 错误消息，默认 "未授权访问"
        msg_details: 详细信息列表（可选）
    """
    
    Forbidden = Forbidden
    """403 Forbidden - 禁止访问
    
    参数:
        message: 错误消息，默认 "禁止访问"
        msg_details: 详细信息列表（可选）
    """
    
    NotFound = NotFound
    """404 Not Found - 资源不存在
    
    参数:
        message: 错误消息，默认 "资源不存在"
        msg_details: 详细信息列表（可选）
    """
    
    Conflict = Conflict
    """409 Conflict - 资源冲突
    
    参数:
        message: 错误消息，默认 "资源冲突"
        msg_details: 详细信息列表（可选）
    """
    
    TooManyRequests = TooManyRequests
    """429 Too Many Requests - 请求过于频繁
    
    参数:
        message: 错误消息，默认 "请求过于频繁"
        msg_details: 详细信息列表（可选）
    """
    
    # ===== 服务端错误 (5xx) =====
    ServerError = InternalServerError
    """500 Internal Server Error - 服务器内部错误
    
    参数:
        message: 错误消息，默认 "服务器内部错误"
        msg_details: 详细信息列表（可选）
    """
