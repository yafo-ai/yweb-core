"""测试全局异常处理器

测试 FastAPI 全局异常处理器的功能。
"""

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from yweb.exceptions import (
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    ServiceUnavailableException,
    register_exception_handlers,
)


# 创建测试应用
def create_test_app():
    """创建测试用的 FastAPI 应用"""
    app = FastAPI()

    # 注册全局异常处理器
    register_exception_handlers(app)

    # 定义测试路由
    @app.get("/test/business-error")
    def test_business_error():
        raise BusinessException("业务错误", code="TEST_ERROR")

    @app.get("/test/authentication-error")
    def test_authentication_error():
        raise AuthenticationException("认证失败")

    @app.get("/test/authorization-error")
    def test_authorization_error():
        raise AuthorizationException("权限不足")

    @app.get("/test/not-found-error")
    def test_not_found_error():
        raise ResourceNotFoundException("资源不存在")

    @app.get("/test/conflict-error")
    def test_conflict_error():
        raise ResourceConflictException("资源冲突")

    @app.get("/test/validation-error")
    def test_validation_error():
        raise ValidationException("验证失败", details=["字段1错误", "字段2错误"])

    @app.get("/test/service-unavailable")
    def test_service_unavailable():
        raise ServiceUnavailableException("服务不可用")

    @app.get("/test/system-error")
    def test_system_error():
        # 触发系统异常
        result = 1 / 0
        return {"result": result}

    @app.get("/test/exception-with-details")
    def test_exception_with_details():
        raise BusinessException(
            "详细错误",
            code="DETAILED_ERROR",
            details=["详细信息1", "详细信息2"]
        )

    # 测试 Pydantic 验证
    class TestModel(BaseModel):
        username: str = Field(min_length=3, max_length=20)
        age: int = Field(ge=0, le=150)

    @app.post("/test/pydantic-validation")
    def test_pydantic_validation(data: TestModel):
        return {"message": "success"}

    return app


@pytest.fixture
def app():
    """测试应用 fixture"""
    return create_test_app()


@pytest.fixture
def client(app):
    """测试客户端 fixture"""
    return TestClient(app)


class TestBusinessExceptionHandler:
    """测试业务异常处理器"""

    def test_business_exception_response(self, client):
        """测试业务异常响应格式"""
        response = client.get("/test/business-error")

        assert response.status_code == 400
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "业务错误"
        assert data["error_code"] == "TEST_ERROR"
        assert data["msg_details"] == []
        assert data["data"] == {}

    def test_authentication_exception_response(self, client):
        """测试认证异常响应"""
        response = client.get("/test/authentication-error")

        assert response.status_code == 401
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "认证失败"
        assert data["error_code"] == "AUTHENTICATION_FAILED"

    def test_authorization_exception_response(self, client):
        """测试授权异常响应"""
        response = client.get("/test/authorization-error")

        assert response.status_code == 403
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "权限不足"
        assert data["error_code"] == "AUTHORIZATION_FAILED"

    def test_not_found_exception_response(self, client):
        """测试资源不存在异常响应"""
        response = client.get("/test/not-found-error")

        assert response.status_code == 404
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "资源不存在"
        assert data["error_code"] == "RESOURCE_NOT_FOUND"

    def test_conflict_exception_response(self, client):
        """测试资源冲突异常响应"""
        response = client.get("/test/conflict-error")

        assert response.status_code == 409
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "资源冲突"
        assert data["error_code"] == "RESOURCE_CONFLICT"

    def test_validation_exception_response(self, client):
        """测试验证异常响应"""
        response = client.get("/test/validation-error")

        assert response.status_code == 422
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "验证失败"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert len(data["msg_details"]) == 2
        assert "字段1错误" in data["msg_details"]

    def test_service_unavailable_response(self, client):
        """测试服务不可用异常响应"""
        response = client.get("/test/service-unavailable")

        assert response.status_code == 503
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "服务不可用"
        assert data["error_code"] == "SERVICE_UNAVAILABLE"

    def test_exception_with_details(self, client):
        """测试带详细信息的异常响应"""
        response = client.get("/test/exception-with-details")

        assert response.status_code == 400
        data = response.json()

        assert data["error_code"] == "DETAILED_ERROR"
        assert len(data["msg_details"]) == 2


class TestPydanticValidationHandler:
    """测试 Pydantic 验证异常处理器"""

    def test_pydantic_validation_error(self, client):
        """测试 Pydantic 验证错误"""
        response = client.post("/test/pydantic-validation", json={
            "username": "ab",  # 太短
            "age": 200  # 超出范围
        })

        assert response.status_code == 422
        data = response.json()

        assert data["status"] == "error"
        assert data["message"] == "请求参数验证失败"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert len(data["msg_details"]) > 0

    def test_pydantic_missing_field(self, client):
        """测试 Pydantic 缺少必填字段"""
        response = client.post("/test/pydantic-validation", json={
            "username": "test"
            # 缺少 age 字段
        })

        assert response.status_code == 422
        data = response.json()

        assert "age" in str(data["msg_details"])

    def test_pydantic_type_error(self, client):
        """测试 Pydantic 类型错误"""
        response = client.post("/test/pydantic-validation", json={
            "username": "test",
            "age": "not_a_number"  # 类型错误
        })

        assert response.status_code == 422
        data = response.json()

        assert data["error_code"] == "VALIDATION_ERROR"


class TestGeneralExceptionHandler:
    """测试通用异常处理器"""

    def test_system_exception_logged(self, client, caplog):
        """测试系统异常是否被正确记录到日志"""
        import pytest

        # 在测试环境中，TestClient 会重新抛出异常
        # 但我们可以验证日志是否正确记录
        with pytest.raises(ZeroDivisionError):
            response = client.get("/test/system-error")

        # 验证日志中记录了异常信息
        assert "Unhandled exception" in caplog.text
        assert "ZeroDivisionError" in caplog.text

    def test_business_exception_not_raised_in_test(self, client):
        """测试业务异常在测试环境中被正确处理"""
        # 业务异常应该被正确转换为响应，不会重新抛出
        response = client.get("/test/business-error")

        assert response.status_code == 400
        data = response.json()
        assert data["status"] == "error"

    def test_system_exception_returns_standard_error_response(self, app):
        """测试系统异常可返回统一错误语义（非重新抛出模式）"""
        client_no_raise = TestClient(app, raise_server_exceptions=False)

        response = client_no_raise.get("/test/system-error")
        assert response.status_code == 500
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "INTERNAL_SERVER_ERROR"
        assert isinstance(data["message"], str)
        assert data["message"] != ""
        assert data["data"] == {}


class TestResponseFormat:
    """测试响应格式"""

    def test_response_has_required_fields(self, client):
        """测试响应包含必需字段"""
        response = client.get("/test/business-error")
        data = response.json()

        # 验证必需字段
        assert "status" in data
        assert "message" in data
        assert "msg_details" in data
        assert "data" in data
        assert "error_code" in data

    def test_response_status_is_error(self, client):
        """测试错误响应的 status 字段"""
        response = client.get("/test/business-error")
        data = response.json()

        assert data["status"] == "error"

    def test_response_data_is_empty_dict(self, client):
        """测试错误响应的 data 字段为空字典"""
        response = client.get("/test/business-error")
        data = response.json()

        assert data["data"] == {}

    def test_response_msg_details_is_list(self, client):
        """测试 msg_details 字段为列表"""
        response = client.get("/test/business-error")
        data = response.json()

        assert isinstance(data["msg_details"], list)


class TestExceptionHandlerIntegration:
    """测试异常处理器集成"""

    def test_multiple_exception_types(self, client):
        """测试多种异常类型"""
        test_cases = [
            ("/test/business-error", 400, "TEST_ERROR"),
            ("/test/authentication-error", 401, "AUTHENTICATION_FAILED"),
            ("/test/authorization-error", 403, "AUTHORIZATION_FAILED"),
            ("/test/not-found-error", 404, "RESOURCE_NOT_FOUND"),
            ("/test/conflict-error", 409, "RESOURCE_CONFLICT"),
            ("/test/validation-error", 422, "VALIDATION_ERROR"),
            ("/test/service-unavailable", 503, "SERVICE_UNAVAILABLE"),
        ]

        for endpoint, expected_status, expected_error_code in test_cases:
            response = client.get(endpoint)
            assert response.status_code == expected_status

            data = response.json()
            assert data["status"] == "error"
            assert data["error_code"] == expected_error_code

    def test_exception_handler_does_not_affect_normal_response(self, client):
        """测试异常处理器不影响正常响应"""
        # 添加一个正常的路由
        @client.app.get("/test/normal")
        def normal_endpoint():
            return {"message": "success"}

        response = client.get("/test/normal")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "success"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
