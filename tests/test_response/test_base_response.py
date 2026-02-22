"""BaseResponse 模块测试

测试标准化响应的功能
"""

import pytest
import json
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.response import (
    ResponseStatus,
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
    BaseResponse,
    SuccessResponse,
    ClientErrorResponse,
    ServerErrorResponse,
    ExtendedResponse,
    create_item_model,
    create_page_model,
    create_response_model,
)


def get_response_content(response) -> dict:
    """从 JSONResponse 中获取内容"""
    return json.loads(response.body.decode())


class TestResponseStatus:
    """ResponseStatus 枚举测试"""
    
    def test_status_values(self):
        """测试枚举值"""
        assert ResponseStatus.SUCCESS.value == "success"
        assert ResponseStatus.ERROR.value == "error"
        assert ResponseStatus.WARNING.value == "warning"
        assert ResponseStatus.INFO.value == "info"
    
    def test_status_is_string(self):
        """测试枚举继承自 str"""
        assert isinstance(ResponseStatus.SUCCESS, str)
        assert ResponseStatus.SUCCESS == "success"
    
    def test_status_comparison(self):
        """测试枚举值比较"""
        response = OK()
        content = get_response_content(response)
        
        # 可以直接与字符串比较
        assert content["status"] == ResponseStatus.SUCCESS
        assert content["status"] == "success"
    
    def test_all_status_types(self):
        """测试所有状态类型"""
        # Success
        ok_response = get_response_content(OK())
        assert ok_response["status"] == ResponseStatus.SUCCESS
        
        # Error
        error_response = get_response_content(BadRequest())
        assert error_response["status"] == ResponseStatus.ERROR
        
        # Warning
        warning_response = get_response_content(Warning())
        assert warning_response["status"] == ResponseStatus.WARNING
        
        # Info
        info_response = get_response_content(Info())
        assert info_response["status"] == ResponseStatus.INFO


class TestOKResponse:
    """OK 响应测试"""
    
    def test_ok_with_data(self):
        """测试带数据的成功响应"""
        response = OK(data={"id": 1, "name": "test"})
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "success"
        assert content["message"] == "请求成功"
        assert content["data"]["id"] == 1
        assert content["data"]["name"] == "test"
    
    def test_ok_with_message(self):
        """测试带自定义消息的成功响应"""
        response = OK(message="操作完成")
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "success"
        assert content["message"] == "操作完成"
    
    def test_ok_with_list_data(self):
        """测试带列表数据的成功响应"""
        data = [{"id": 1}, {"id": 2}]
        response = OK(data=data)
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "success"
        assert len(content["data"]) == 2
    
    def test_ok_empty_data(self):
        """测试空数据的成功响应"""
        response = OK()
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "success"
        assert content["data"] == {}
    
    def test_ok_with_none_data(self):
        """测试 None 数据的成功响应"""
        response = OK(data=None)
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["data"] == {}


class TestBadRequestResponse:
    """BadRequest 响应测试"""
    
    def test_bad_request_basic(self):
        """测试基本的错误请求响应"""
        response = BadRequest()
        content = get_response_content(response)
        
        assert response.status_code == 400
        assert content["status"] == "error"
        assert content["message"] == "请求参数错误"
    
    def test_bad_request_custom_message(self):
        """测试自定义消息的错误请求响应"""
        response = BadRequest(message="用户名不能为空")
        content = get_response_content(response)
        
        assert response.status_code == 400
        assert content["status"] == "error"
        assert content["message"] == "用户名不能为空"
    
    def test_bad_request_with_details(self):
        """测试带详情的错误请求响应"""
        response = BadRequest(
            message="验证失败",
            msg_details=["用户名不能为空", "密码长度不足"]
        )
        content = get_response_content(response)
        
        assert response.status_code == 400
        assert content["status"] == "error"
        assert len(content["msg_details"]) == 2


class TestUnauthorizedResponse:
    """Unauthorized 响应测试"""
    
    def test_unauthorized_default(self):
        """测试默认的未授权响应"""
        response = Unauthorized()
        content = get_response_content(response)
        
        assert response.status_code == 401
        assert content["status"] == "error"
        assert content["message"] == "未授权访问"
    
    def test_unauthorized_custom_message(self):
        """测试自定义消息的未授权响应"""
        response = Unauthorized(message="Token已过期")
        content = get_response_content(response)
        
        assert response.status_code == 401
        assert content["status"] == "error"
        assert content["message"] == "Token已过期"


class TestForbiddenResponse:
    """Forbidden 响应测试"""
    
    def test_forbidden_default(self):
        """测试默认的禁止访问响应"""
        response = Forbidden()
        content = get_response_content(response)
        
        assert response.status_code == 403
        assert content["status"] == "error"
        assert content["message"] == "禁止访问"
    
    def test_forbidden_custom_message(self):
        """测试自定义消息的禁止访问响应"""
        response = Forbidden(message="您没有权限执行此操作")
        content = get_response_content(response)
        
        assert response.status_code == 403
        assert content["message"] == "您没有权限执行此操作"


class TestNotFoundResponse:
    """NotFound 响应测试"""
    
    def test_not_found_default(self):
        """测试默认的资源不存在响应"""
        response = NotFound()
        content = get_response_content(response)
        
        assert response.status_code == 404
        assert content["status"] == "error"
        assert content["message"] == "资源不存在"
    
    def test_not_found_custom_message(self):
        """测试自定义消息的资源不存在响应"""
        response = NotFound(message="用户不存在")
        content = get_response_content(response)
        
        assert response.status_code == 404
        assert content["message"] == "用户不存在"


class TestInternalServerErrorResponse:
    """InternalServerError 响应测试"""
    
    def test_internal_error_default(self):
        """测试默认的服务器错误响应"""
        response = InternalServerError()
        content = get_response_content(response)
        
        assert response.status_code == 500
        assert content["status"] == "error"
        assert content["message"] == "服务器内部错误"
    
    def test_internal_error_custom_message(self):
        """测试自定义消息的服务器错误响应"""
        response = InternalServerError(message="数据库连接失败")
        content = get_response_content(response)
        
        assert response.status_code == 500
        assert content["message"] == "数据库连接失败"


class TestConflictResponse:
    """Conflict 响应测试"""
    
    def test_conflict_default(self):
        """测试默认的资源冲突响应"""
        response = Conflict()
        content = get_response_content(response)
        
        assert response.status_code == 409
        assert content["status"] == "error"
        assert content["message"] == "资源冲突"
    
    def test_conflict_custom_message(self):
        """测试自定义消息的资源冲突响应"""
        response = Conflict(message="用户名已存在")
        content = get_response_content(response)
        
        assert response.status_code == 409
        assert content["message"] == "用户名已存在"


class TestTooManyRequestsResponse:
    """TooManyRequests 响应测试"""
    
    def test_too_many_requests_default(self):
        """测试默认的请求过于频繁响应"""
        response = TooManyRequests()
        content = get_response_content(response)
        
        assert response.status_code == 429
        assert content["status"] == "error"
        assert content["message"] == "请求过于频繁"
    
    def test_too_many_requests_custom_message(self):
        """测试自定义消息的请求过于频繁响应"""
        response = TooManyRequests(message="请稍后再试")
        content = get_response_content(response)
        
        assert response.status_code == 429
        assert content["message"] == "请稍后再试"


class TestWarningResponse:
    """Warning 响应测试"""
    
    def test_warning_default(self):
        """测试默认的警告响应"""
        response = Warning()
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "warning"
        assert content["message"] == "操作成功，但有警告"
    
    def test_warning_with_data(self):
        """测试带数据的警告响应"""
        response = Warning(
            message="部分数据导入失败",
            data={"success": 10, "failed": 2},
            msg_details=["第3行格式错误", "第7行数据重复"]
        )
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "warning"
        assert content["data"]["success"] == 10
        assert len(content["msg_details"]) == 2


class TestInfoResponse:
    """Info 响应测试"""
    
    def test_info_default(self):
        """测试默认的信息响应"""
        response = Info()
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "info"
        assert content["message"] == "信息提示"
    
    def test_info_with_data(self):
        """测试带数据的信息响应"""
        response = Info(
            message="系统状态",
            data={"version": "1.0.0", "uptime": "24h"}
        )
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "info"
        assert content["data"]["version"] == "1.0.0"


class TestResponseModels:
    """响应模型生成测试"""
    
    def test_create_page_model(self):
        """测试创建分页模型"""
        from pydantic import BaseModel
        
        class UserItem(BaseModel):
            id: int
            name: str
        
        UserPageData = create_page_model(UserItem)
        
        # 验证模型有正确的字段
        assert "rows" in UserPageData.model_fields
        assert "total_records" in UserPageData.model_fields
        assert "page" in UserPageData.model_fields
        assert "page_size" in UserPageData.model_fields
        assert "total_pages" in UserPageData.model_fields
        assert "has_prev" in UserPageData.model_fields
        assert "has_next" in UserPageData.model_fields
    
    def test_create_item_model_from_sqlalchemy(self, memory_engine):
        """测试从 SQLAlchemy 模型创建 Item 模型"""
        from sqlalchemy import Column, Integer, String
        from yweb.orm import BaseModel as ORMBaseModel
        
        class TestUser(ORMBaseModel):
            __tablename__ = "test_response_users"
            __table_args__ = {'extend_existing': True}
            username = Column(String(50), comment="用户名")
            email = Column(String(100), comment="邮箱")
        
        ORMBaseModel.metadata.create_all(bind=memory_engine)
        
        UserItemModel = create_item_model(TestUser)
        
        # 验证模型有 ORM 模型的字段
        assert "id" in UserItemModel.model_fields
        assert "username" in UserItemModel.model_fields
        assert "email" in UserItemModel.model_fields
    
    def test_create_response_model_from_sqlalchemy(self, memory_engine):
        """测试从 SQLAlchemy 模型创建完整响应模型"""
        from sqlalchemy import Column, Integer, String
        from yweb.orm import BaseModel as ORMBaseModel
        
        class TestProduct(ORMBaseModel):
            __tablename__ = "test_response_products"
            __table_args__ = {'extend_existing': True}
            product_name = Column(String(100), comment="产品名称")
            price = Column(Integer, comment="价格")
        
        ORMBaseModel.metadata.create_all(bind=memory_engine)
        
        ProductResponse = create_response_model(TestProduct)
        
        # 验证响应模型有正确的字段
        assert "status" in ProductResponse.model_fields
        assert "message" in ProductResponse.model_fields
        assert "msg_details" in ProductResponse.model_fields
        assert "data" in ProductResponse.model_fields


class TestBaseResponseSerialization:
    """BaseResponse 序列化测试"""
    
    def test_serialize_dict(self):
        """测试序列化字典"""
        data = {"id": 1, "name": "test"}
        result = BaseResponse._serialize_data(data)
        
        assert result == {"id": 1, "name": "test"}
    
    def test_serialize_list(self):
        """测试序列化列表"""
        data = [{"id": 1}, {"id": 2}]
        result = BaseResponse._serialize_data(data)
        
        assert len(result) == 2
        assert result[0]["id"] == 1
    
    def test_serialize_none(self):
        """测试序列化 None"""
        result = BaseResponse._serialize_data(None)
        
        assert result == {}
    
    def test_serialize_datetime(self):
        """测试序列化 datetime"""
        from datetime import datetime
        
        dt = datetime(2024, 1, 15, 10, 30, 45)
        result = BaseResponse._serialize_data(dt)
        
        assert result == "2024-01-15 10:30:45"
    
    def test_serialize_nested_dict(self):
        """测试序列化嵌套字典"""
        data = {
            "user": {
                "id": 1,
                "profile": {
                    "name": "test"
                }
            }
        }
        result = BaseResponse._serialize_data(data)
        
        assert result["user"]["profile"]["name"] == "test"

    def test_serialize_none_semantics_top_level_vs_nested(self):
        """测试顶层 None 与嵌套 None 的序列化语义"""
        # 顶层 None -> {}
        assert BaseResponse._serialize_data(None) == {}
        # 嵌套 None -> 保留 None（避免语义丢失）
        nested = BaseResponse._serialize_data({"a": None, "b": {"c": None}})
        assert nested["a"] is None
        assert nested["b"]["c"] is None

    def test_serialize_dto_object(self):
        """测试带 to_dict 的 DTO 对象会被递归序列化"""
        class UserDTO:
            def to_dict(self):
                return {
                    "id": 1,
                    "created_at": __import__("datetime").datetime(2024, 1, 1, 8, 0, 0),
                }

        result = BaseResponse._serialize_data(UserDTO())
        assert result["id"] == 1
        assert result["created_at"] == "2024-01-01 08:00:00"


class TestResponseInFastAPI:
    """FastAPI 集成测试"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        
        @app.get("/ok")
        def get_ok():
            return OK(data={"message": "hello"})
        
        @app.get("/error")
        def get_error():
            return BadRequest(message="Invalid request")
        
        @app.get("/not-found")
        def get_not_found():
            return NotFound(message="Item not found")
        
        return app
    
    @pytest.fixture
    def client(self, app):
        """创建测试客户端"""
        return TestClient(app)
    
    def test_ok_response_in_api(self, client):
        """测试 API 中的 OK 响应"""
        response = client.get("/ok")
        data = response.json()
        
        assert response.status_code == 200
        assert data["status"] == "success"
        assert data["data"]["message"] == "hello"
        # 统一响应契约：始终包含 msg_details 列表
        assert isinstance(data["msg_details"], list)
    
    def test_error_response_in_api(self, client):
        """测试 API 中的错误响应"""
        response = client.get("/error")
        data = response.json()
        
        # 错误响应返回对应的 HTTP 状态码
        assert response.status_code == 400
        assert data["status"] == "error"
        assert data["message"] == "Invalid request"
    
    def test_not_found_response_in_api(self, client):
        """测试 API 中的 NotFound 响应"""
        response = client.get("/not-found")
        data = response.json()
        
        assert response.status_code == 404
        assert data["status"] == "error"
        assert data["message"] == "Item not found"


class TestResponseClasses:
    """响应类测试"""
    
    def test_success_response_class(self):
        """测试 SuccessResponse 类"""
        response = SuccessResponse.OK(data={"test": True})
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "success"
        assert content["data"]["test"] is True
    
    def test_client_error_response_class(self):
        """测试 ClientErrorResponse 类"""
        response = ClientErrorResponse.BadRequest()
        content = get_response_content(response)
        
        assert response.status_code == 400
        assert content["status"] == "error"
        assert content["message"] == "请求参数错误"
    
    def test_server_error_response_class(self):
        """测试 ServerErrorResponse 类"""
        response = ServerErrorResponse.InternalServerError()
        content = get_response_content(response)
        
        assert response.status_code == 500
        assert content["status"] == "error"
        assert content["message"] == "服务器内部错误"
    
    def test_extended_response_class(self):
        """测试 ExtendedResponse 类"""
        response = ExtendedResponse.Warning(message="Warning message")
        content = get_response_content(response)
        
        assert response.status_code == 200
        assert content["status"] == "warning"
        assert content["message"] == "Warning message"

    def test_alias_functions_match_class_methods(self):
        """测试顶层别名函数与类方法行为一致"""
        alias_resp = get_response_content(OK(data={"x": 1}, message="ok"))
        class_resp = get_response_content(SuccessResponse.OK(data={"x": 1}, message="ok"))
        assert alias_resp == class_resp

        alias_err = BadRequest(message="bad", msg_details=["d1"])
        class_err = ClientErrorResponse.BadRequest(message="bad", msg_details=["d1"])
        assert alias_err.status_code == class_err.status_code
        assert get_response_content(alias_err) == get_response_content(class_err)
