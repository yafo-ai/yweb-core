"""测试业务异常类

测试所有业务异常类的基本功能。
"""

import pytest
from fastapi import status

from yweb.exceptions import (
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    ServiceUnavailableException,
)


class TestBusinessException:
    """测试 BusinessException 基类"""

    def test_basic_exception(self):
        """测试基本异常创建"""
        exc = BusinessException("测试错误")

        assert str(exc) == "测试错误"
        assert exc.message == "测试错误"
        assert exc.code == "BUSINESS_ERROR"
        assert exc.status_code == status.HTTP_400_BAD_REQUEST
        assert exc.details == []
        assert exc.extra == {}

    def test_exception_with_code(self):
        """测试带错误代码的异常"""
        exc = BusinessException("测试错误", code="CUSTOM_ERROR")

        assert exc.code == "CUSTOM_ERROR"

    def test_exception_with_details(self):
        """测试带详细信息的异常"""
        details = ["错误1", "错误2"]
        exc = BusinessException("测试错误", details=details)

        assert exc.details == details

    def test_exception_with_extra(self):
        """测试带额外上下文的异常"""
        exc = BusinessException(
            "测试错误",
            user_id=123,
            operation="test"
        )

        assert exc.extra["user_id"] == 123
        assert exc.extra["operation"] == "test"

    def test_exception_to_dict(self):
        """测试异常转换为字典"""
        exc = BusinessException(
            "测试错误",
            code="TEST_ERROR",
            details=["详细信息"],
            user_id=123
        )

        result = exc.to_dict()

        assert result["message"] == "测试错误"
        assert result["code"] == "TEST_ERROR"
        assert result["status_code"] == 400
        assert result["details"] == ["详细信息"]
        assert result["extra"]["user_id"] == 123

    def test_exception_repr(self):
        """测试异常的字符串表示"""
        exc = BusinessException("测试错误", code="TEST_ERROR")

        repr_str = repr(exc)

        assert "BusinessException" in repr_str
        assert "message='测试错误'" in repr_str
        assert "code='TEST_ERROR'" in repr_str

    def test_mutable_defaults_are_isolated_between_instances(self):
        """测试 details/extra 在实例间不会共享（防止可变默认值污染）"""
        exc1 = BusinessException("错误1")
        exc2 = BusinessException("错误2")

        exc1.details.append("d1")
        exc1.extra["request_id"] = "rid-1"

        assert exc2.details == []
        assert exc2.extra == {}

    def test_to_dict_does_not_share_mutable_references(self):
        """测试 to_dict 返回值与异常内部状态解耦"""
        exc = BusinessException("测试错误", details=["原始"], trace_id="rid")

        data = exc.to_dict()
        data["details"].append("外部修改")
        data["extra"]["trace_id"] = "mutated"

        assert exc.details == ["原始"]
        assert exc.extra["trace_id"] == "rid"


class TestAuthenticationException:
    """测试 AuthenticationException"""

    def test_default_authentication_exception(self):
        """测试默认认证异常"""
        exc = AuthenticationException()

        assert exc.message == "认证失败"
        assert exc.code == "AUTHENTICATION_FAILED"
        assert exc.status_code == status.HTTP_401_UNAUTHORIZED

    def test_custom_authentication_exception(self):
        """测试自定义认证异常"""
        exc = AuthenticationException(
            "用户名或密码错误",
            code="INVALID_CREDENTIALS"
        )

        assert exc.message == "用户名或密码错误"
        assert exc.code == "INVALID_CREDENTIALS"
        assert exc.status_code == 401

    def test_authentication_exception_with_details(self):
        """测试带详细信息的认证异常"""
        exc = AuthenticationException(
            "Token已过期",
            code="TOKEN_EXPIRED",
            details=["请重新登录"]
        )

        assert exc.details == ["请重新登录"]


class TestAuthorizationException:
    """测试 AuthorizationException"""

    def test_default_authorization_exception(self):
        """测试默认授权异常"""
        exc = AuthorizationException()

        assert exc.message == "权限不足"
        assert exc.code == "AUTHORIZATION_FAILED"
        assert exc.status_code == status.HTTP_403_FORBIDDEN

    def test_custom_authorization_exception(self):
        """测试自定义授权异常"""
        exc = AuthorizationException(
            "需要管理员权限",
            code="ADMIN_REQUIRED",
            details=["当前角色: user", "需要角色: admin"]
        )

        assert exc.message == "需要管理员权限"
        assert exc.code == "ADMIN_REQUIRED"
        assert len(exc.details) == 2


class TestResourceNotFoundException:
    """测试 ResourceNotFoundException"""

    def test_default_resource_not_found(self):
        """测试默认资源不存在异常"""
        exc = ResourceNotFoundException()

        assert exc.message == "资源不存在"
        assert exc.code == "RESOURCE_NOT_FOUND"
        assert exc.status_code == status.HTTP_404_NOT_FOUND

    def test_resource_not_found_with_context(self):
        """测试带上下文的资源不存在异常"""
        exc = ResourceNotFoundException(
            "用户不存在",
            resource_type="User",
            resource_id=123
        )

        assert exc.message == "用户不存在"
        assert exc.extra["resource_type"] == "User"
        assert exc.extra["resource_id"] == 123


class TestResourceConflictException:
    """测试 ResourceConflictException"""

    def test_default_resource_conflict(self):
        """测试默认资源冲突异常"""
        exc = ResourceConflictException()

        assert exc.message == "资源冲突"
        assert exc.code == "RESOURCE_CONFLICT"
        assert exc.status_code == status.HTTP_409_CONFLICT

    def test_resource_conflict_with_field(self):
        """测试带字段信息的资源冲突异常"""
        exc = ResourceConflictException(
            "用户名已被使用",
            field="username",
            value="admin"
        )

        assert exc.message == "用户名已被使用"
        assert exc.extra["field"] == "username"
        assert exc.extra["value"] == "admin"


class TestValidationException:
    """测试 ValidationException"""

    def test_default_validation_exception(self):
        """测试默认验证异常"""
        exc = ValidationException()

        assert exc.message == "数据验证失败"
        assert exc.code == "VALIDATION_ERROR"
        assert exc.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY

    def test_validation_exception_with_details(self):
        """测试带详细信息的验证异常"""
        details = [
            "用户名长度必须在3-20个字符之间",
            "密码必须包含字母和数字"
        ]
        exc = ValidationException(
            "数据验证失败",
            details=details
        )

        assert exc.details == details

    def test_validation_exception_with_field(self):
        """测试带字段信息的验证异常"""
        exc = ValidationException(
            "邮箱格式不正确",
            field="email",
            value="invalid-email"
        )

        assert exc.extra["field"] == "email"
        assert exc.extra["value"] == "invalid-email"


class TestServiceUnavailableException:
    """测试 ServiceUnavailableException"""

    def test_default_service_unavailable(self):
        """测试默认服务不可用异常"""
        exc = ServiceUnavailableException()

        assert exc.message == "服务暂时不可用"
        assert exc.code == "SERVICE_UNAVAILABLE"
        assert exc.status_code == status.HTTP_503_SERVICE_UNAVAILABLE

    def test_service_unavailable_with_service_name(self):
        """测试带服务名称的服务不可用异常"""
        exc = ServiceUnavailableException(
            "数据库连接失败",
            service="database"
        )

        assert exc.message == "数据库连接失败"
        assert exc.extra["service"] == "database"

    def test_service_unavailable_with_multiple_context(self):
        """测试带多个上下文的服务不可用异常"""
        exc = ServiceUnavailableException(
            "支付服务暂时不可用",
            service="payment_gateway",
            timeout=10,
            retry_after=60
        )

        assert exc.extra["service"] == "payment_gateway"
        assert exc.extra["timeout"] == 10
        assert exc.extra["retry_after"] == 60


class TestExceptionChaining:
    """测试异常链"""

    def test_exception_chaining_with_from(self):
        """测试使用 from 保留异常链"""
        original_error = ValueError("原始错误")

        try:
            raise BusinessException("业务错误") from original_error
        except BusinessException as e:
            assert e.__cause__ is original_error
            assert isinstance(e.__cause__, ValueError)

    def test_exception_chaining_preserves_traceback(self):
        """测试异常链保留堆栈信息"""
        def inner_function():
            raise ValueError("内部错误")

        def outer_function():
            try:
                inner_function()
            except ValueError as e:
                raise BusinessException("外部错误") from e

        with pytest.raises(BusinessException) as exc_info:
            outer_function()

        # 验证异常链存在
        assert exc_info.value.__cause__ is not None
        assert isinstance(exc_info.value.__cause__, ValueError)


class TestCustomExceptionSubclass:
    """测试自定义异常子类"""

    def test_create_custom_exception(self):
        """测试创建自定义异常类"""
        class PaymentException(BusinessException):
            def __init__(self, message: str = "支付失败", **kwargs):
                super().__init__(
                    message=message,
                    code="PAYMENT_FAILED",
                    status_code=402,
                    **kwargs
                )

        exc = PaymentException("余额不足", balance=100, required=200)

        assert exc.message == "余额不足"
        assert exc.code == "PAYMENT_FAILED"
        assert exc.status_code == 402
        assert exc.extra["balance"] == 100
        assert exc.extra["required"] == 200


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
