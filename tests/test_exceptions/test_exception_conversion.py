"""测试内部异常转换

测试将内部技术异常转换为业务异常的功能。
"""

import pytest
from sqlalchemy.exc import OperationalError, IntegrityError
import requests

from yweb.exceptions import (
    BusinessException,
    ResourceConflictException,
    ServiceUnavailableException,
    ValidationException,
)


class TestDatabaseExceptionConversion:
    """测试数据库异常转换"""

    def test_convert_operational_error(self):
        """测试转换数据库连接错误"""
        def database_operation():
            try:
                # 模拟数据库连接失败
                raise OperationalError(
                    "connection failed",
                    None,
                    None
                )
            except OperationalError as e:
                # 转换为业务异常
                raise ServiceUnavailableException(
                    "数据库服务暂时不可用",
                    service="database"
                ) from e

        with pytest.raises(ServiceUnavailableException) as exc_info:
            database_operation()

        # 验证异常信息
        assert exc_info.value.message == "数据库服务暂时不可用"
        assert exc_info.value.extra["service"] == "database"

        # 验证异常链被保留
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, OperationalError)

    def test_convert_integrity_error(self):
        """测试转换数据完整性错误"""
        def database_operation():
            try:
                # 模拟唯一约束冲突
                raise IntegrityError(
                    "duplicate key value violates unique constraint",
                    None,
                    None
                )
            except IntegrityError as e:
                # 转换为资源冲突异常
                raise ResourceConflictException(
                    "用户名已被使用",
                    field="username"
                ) from e

        with pytest.raises(ResourceConflictException) as exc_info:
            database_operation()

        # 验证异常信息
        assert exc_info.value.message == "用户名已被使用"
        assert exc_info.value.extra["field"] == "username"

        # 验证异常链
        assert isinstance(exc_info.value.__cause__, IntegrityError)


class TestHTTPExceptionConversion:
    """测试 HTTP 异常转换"""

    def test_convert_connection_error(self):
        """测试转换连接错误"""
        def api_call():
            try:
                # 模拟连接失败
                raise requests.ConnectionError("Connection refused")
            except requests.ConnectionError as e:
                # 转换为服务不可用异常
                raise ServiceUnavailableException(
                    "无法连接到支付服务",
                    service="payment_gateway"
                ) from e

        with pytest.raises(ServiceUnavailableException) as exc_info:
            api_call()

        assert exc_info.value.message == "无法连接到支付服务"
        assert exc_info.value.extra["service"] == "payment_gateway"
        assert isinstance(exc_info.value.__cause__, requests.ConnectionError)

    def test_convert_timeout_error(self):
        """测试转换超时错误"""
        def api_call():
            try:
                # 模拟超时
                raise requests.Timeout("Request timeout")
            except requests.Timeout as e:
                # 转换为服务不可用异常
                raise ServiceUnavailableException(
                    "服务响应超时",
                    service="payment_gateway",
                    timeout=10
                ) from e

        with pytest.raises(ServiceUnavailableException) as exc_info:
            api_call()

        assert exc_info.value.extra["timeout"] == 10
        assert isinstance(exc_info.value.__cause__, requests.Timeout)


class TestExceptionConversionBestPractices:
    """测试异常转换最佳实践"""

    def test_preserve_exception_chain(self):
        """测试保留异常链"""
        def inner_function():
            raise ValueError("原始错误")

        def outer_function():
            try:
                inner_function()
            except ValueError as e:
                raise BusinessException("转换后的错误") from e

        with pytest.raises(BusinessException) as exc_info:
            outer_function()

        # 验证异常链
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)
        assert str(exc_info.value.__cause__) == "原始错误"

    def test_hide_sensitive_information(self):
        """测试隐藏敏感信息"""
        def database_operation():
            try:
                # 模拟包含敏感信息的错误
                raise OperationalError(
                    "FATAL: password authentication failed for user 'postgres'",
                    None,
                    None
                )
            except OperationalError as e:
                # 转换时隐藏敏感信息
                raise ServiceUnavailableException(
                    "数据库服务暂时不可用",  # 不包含敏感信息
                    service="database"
                ) from e

        with pytest.raises(ServiceUnavailableException) as exc_info:
            database_operation()

        # 验证用户看到的消息不包含敏感信息
        assert "postgres" not in exc_info.value.message
        assert "password" not in exc_info.value.message

        # 但原始异常仍然被保留（用于日志）
        assert "postgres" in str(exc_info.value.__cause__)

    def test_add_context_information(self):
        """测试添加上下文信息"""
        def database_operation(user_id: int):
            try:
                raise OperationalError("connection failed", None, None)
            except OperationalError as e:
                # 添加上下文信息
                raise ServiceUnavailableException(
                    "数据库服务暂时不可用",
                    service="database",
                    operation="get_user",
                    user_id=user_id
                ) from e

        with pytest.raises(ServiceUnavailableException) as exc_info:
            database_operation(user_id=123)

        # 验证上下文信息被添加
        assert exc_info.value.extra["operation"] == "get_user"
        assert exc_info.value.extra["user_id"] == 123


class TestExceptionConversionPatterns:
    """测试异常转换模式"""

    def test_repository_layer_exception_conversion(self):
        """测试 Repository 层异常转换模式"""
        class UserRepository:
            def get_by_id(self, user_id: int):
                try:
                    # 模拟数据库查询
                    if user_id == 999:
                        raise OperationalError("connection failed", None, None)
                    return {"id": user_id, "username": "test"}
                except OperationalError as e:
                    raise ServiceUnavailableException(
                        "数据库服务暂时不可用",
                        service="database"
                    ) from e

        repo = UserRepository()

        # 正常情况
        user = repo.get_by_id(1)
        assert user["id"] == 1

        # 异常情况
        with pytest.raises(ServiceUnavailableException):
            repo.get_by_id(999)

    def test_service_layer_exception_handling(self):
        """测试 Service 层异常处理模式"""
        class UserService:
            def __init__(self, repository):
                self.repository = repository

            def get_user(self, user_id: int):
                # Service 层不需要转换异常，直接让异常向上传播
                return self.repository.get_by_id(user_id)

        class MockRepository:
            def get_by_id(self, user_id: int):
                if user_id == 999:
                    raise ServiceUnavailableException(
                        "数据库服务暂时不可用"
                    )
                return {"id": user_id}

        service = UserService(MockRepository())

        # 异常会自动向上传播
        with pytest.raises(ServiceUnavailableException):
            service.get_user(999)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
