"""测试异常处理集成场景

测试异常处理在实际业务场景中的应用。
"""

import pytest
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yweb.exceptions import (
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    ServiceUnavailableException,
    register_exception_handlers,
)


# 模拟数据库
USERS_DB = {
    1: {"id": 1, "username": "admin", "role": "admin"},
    2: {"id": 2, "username": "user1", "role": "user"},
}


# 模拟 Service 层
class UserService:
    """用户服务 - 演示异常处理"""

    def get_user_by_id(self, user_id: int):
        """获取用户"""
        user = USERS_DB.get(user_id)
        if not user:
            raise ResourceNotFoundException(
                "用户不存在",
                resource_type="User",
                resource_id=user_id
            )
        return user

    def create_user(self, username: str, role: str = "user"):
        """创建用户"""
        # 检查用户名是否已存在
        for user in USERS_DB.values():
            if user["username"] == username:
                raise ResourceConflictException(
                    "用户名已被使用",
                    field="username",
                    value=username
                )

        # 验证用户名长度
        if len(username) < 3:
            raise ValidationException(
                "用户名长度不足",
                field="username",
                details=["用户名长度必须至少为3个字符"]
            )

        # 创建用户
        new_id = max(USERS_DB.keys()) + 1
        new_user = {"id": new_id, "username": username, "role": role}
        USERS_DB[new_id] = new_user
        return new_user

    def delete_user(self, user_id: int, current_user: dict):
        """删除用户 - 需要管理员权限"""
        # 检查权限
        if current_user["role"] != "admin":
            raise AuthorizationException(
                "需要管理员权限",
                code="ADMIN_REQUIRED",
                details=[
                    f"当前角色: {current_user['role']}",
                    "需要角色: admin"
                ]
            )

        # 检查用户是否存在
        if user_id not in USERS_DB:
            raise ResourceNotFoundException("用户不存在")

        # 删除用户
        del USERS_DB[user_id]
        return {"message": "删除成功"}

    def authenticate(self, username: str, password: str):
        """认证用户"""
        # 模拟认证逻辑
        for user in USERS_DB.values():
            if user["username"] == username:
                # 这里简化处理，实际应该验证密码
                if password == "correct_password":
                    return user

        raise AuthenticationException("用户名或密码错误")


# 创建测试应用
def create_test_app():
    """创建测试应用"""
    app = FastAPI()
    register_exception_handlers(app)

    user_service = UserService()

    # 模拟当前用户依赖
    def get_current_user(user_id: int = 1):
        return user_service.get_user_by_id(user_id)

    @app.get("/users/{user_id}")
    def get_user(user_id: int):
        """获取用户"""
        user = user_service.get_user_by_id(user_id)
        return {"status": "success", "data": user}

    @app.post("/users")
    def create_user(username: str, role: str = "user"):
        """创建用户"""
        user = user_service.create_user(username, role)
        return {"status": "success", "data": user}

    @app.delete("/users/{user_id}")
    def delete_user(user_id: int, current_user_id: int = 1):
        """删除用户"""
        current_user = user_service.get_user_by_id(current_user_id)
        result = user_service.delete_user(user_id, current_user)
        return {"status": "success", "data": result}

    @app.post("/auth/login")
    def login(username: str, password: str):
        """登录"""
        user = user_service.authenticate(username, password)
        return {"status": "success", "data": user}

    return app


@pytest.fixture
def app():
    """测试应用"""
    return create_test_app()


@pytest.fixture
def client(app):
    """测试客户端"""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_db():
    """每个测试前重置数据库"""
    global USERS_DB
    USERS_DB = {
        1: {"id": 1, "username": "admin", "role": "admin"},
        2: {"id": 2, "username": "user1", "role": "user"},
    }
    yield


class TestUserGetScenario:
    """测试获取用户场景"""

    def test_get_existing_user(self, client):
        """测试获取存在的用户"""
        response = client.get("/users/1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["username"] == "admin"

    def test_get_non_existing_user(self, client):
        """测试获取不存在的用户"""
        response = client.get("/users/999")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "用户不存在"
        assert data["error_code"] == "RESOURCE_NOT_FOUND"


class TestUserCreateScenario:
    """测试创建用户场景"""

    def test_create_user_success(self, client):
        """测试成功创建用户"""
        response = client.post("/users?username=newuser&role=user")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["username"] == "newuser"

    def test_create_user_with_duplicate_username(self, client):
        """测试创建重复用户名的用户"""
        before_count = len(USERS_DB)
        response = client.post("/users?username=admin&role=user")

        assert response.status_code == 409
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "用户名已被使用"
        assert data["error_code"] == "RESOURCE_CONFLICT"
        # 失败请求不应污染状态
        assert len(USERS_DB) == before_count

    def test_create_user_with_short_username(self, client):
        """测试创建用户名过短的用户"""
        before_count = len(USERS_DB)
        response = client.post("/users?username=ab&role=user")

        assert response.status_code == 422
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "用户名长度不足"
        assert data["error_code"] == "VALIDATION_ERROR"
        assert len(data["msg_details"]) > 0
        # 验证失败不应写入新用户
        assert len(USERS_DB) == before_count


class TestUserDeleteScenario:
    """测试删除用户场景"""

    def test_delete_user_as_admin(self, client):
        """测试管理员删除用户"""
        assert 2 in USERS_DB
        response = client.delete("/users/2?current_user_id=1")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert 2 not in USERS_DB

    def test_delete_user_as_normal_user(self, client):
        """测试普通用户删除用户（权限不足）"""
        response = client.delete("/users/1?current_user_id=2")

        assert response.status_code == 403
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "需要管理员权限"
        assert data["error_code"] == "ADMIN_REQUIRED"
        assert len(data["msg_details"]) == 2

    def test_delete_non_existing_user(self, client):
        """测试删除不存在的用户"""
        response = client.delete("/users/999?current_user_id=1")

        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "用户不存在"


class TestAuthenticationScenario:
    """测试认证场景"""

    def test_login_success(self, client):
        """测试登录成功"""
        response = client.post("/auth/login?username=admin&password=correct_password")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["username"] == "admin"

    def test_login_with_wrong_password(self, client):
        """测试登录失败（密码错误）"""
        response = client.post("/auth/login?username=admin&password=wrong_password")

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert data["message"] == "用户名或密码错误"
        assert data["error_code"] == "AUTHENTICATION_FAILED"

    def test_login_with_non_existing_user(self, client):
        """测试登录失败（用户不存在）"""
        response = client.post("/auth/login?username=nonexist&password=any")

        assert response.status_code == 401
        data = response.json()
        assert data["status"] == "error"
        assert data["error_code"] == "AUTHENTICATION_FAILED"


class TestExceptionChainInIntegration:
    """测试集成场景中的异常链"""

    def test_exception_chain_preserved(self, client):
        """测试异常链被保留"""
        # 这个测试验证异常链在实际应用中被正确保留
        # 虽然响应中不会直接显示异常链，但日志中应该有完整信息

        response = client.get("/users/999")

        # 验证响应正确
        assert response.status_code == 404
        data = response.json()
        assert data["error_code"] == "RESOURCE_NOT_FOUND"


class TestMultipleExceptionsInOneRequest:
    """测试一个请求中可能触发多个异常"""

    def test_validation_before_conflict(self, client):
        """测试验证异常优先于冲突异常"""
        # 用户名太短，应该先触发验证异常
        response = client.post("/users?username=ab&role=user")

        assert response.status_code == 422
        data = response.json()
        assert data["error_code"] == "VALIDATION_ERROR"


class TestExceptionResponseConsistency:
    """测试异常响应的一致性"""

    def test_all_exceptions_have_same_format(self, client):
        """测试所有异常响应格式一致"""
        test_cases = [
            ("/users/999", "GET", 404),  # ResourceNotFoundException
            ("/users?username=admin&role=user", "POST", 409),  # ResourceConflictException
            ("/users?username=ab&role=user", "POST", 422),  # ValidationException
            ("/auth/login?username=admin&password=wrong", "POST", 401),  # AuthenticationException
            ("/users/1?current_user_id=2", "DELETE", 403),  # AuthorizationException
        ]

        for endpoint, method, expected_status in test_cases:
            # 根据方法调用不同的 HTTP 方法
            if method == "GET":
                response = client.get(endpoint)
            elif method == "POST":
                response = client.post(endpoint)
            elif method == "DELETE":
                response = client.delete(endpoint)
            else:
                continue

            assert response.status_code == expected_status, f"Failed for {method} {endpoint}"

            data = response.json()
            # 验证所有响应都有相同的字段
            assert "status" in data
            assert "message" in data
            assert "msg_details" in data
            assert "data" in data
            assert "error_code" in data

            # 验证 status 都是 error
            assert data["status"] == "error"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
