"""认证依赖模块测试

测试 FastAPI 认证依赖的各种场景。
"""

from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, HTTPException
from fastapi.testclient import TestClient

from yweb.auth import (
    JWTManager,
    TokenPayload,
    AuthDependency,
    create_auth_dependency,
    oauth2_scheme,
    RoleChecker,
    get_token_from_header,
)


class TestCreateAuthDependency:
    """create_auth_dependency 函数测试"""
    
    @pytest.fixture
    def auth_app(self, jwt_manager, user_getter):
        """创建带认证的测试应用"""
        app = FastAPI()
        
        get_current_user = create_auth_dependency(
            jwt_manager=jwt_manager,
            user_getter=user_getter,
            auto_error=True
        )
        
        get_current_user_optional = create_auth_dependency(
            jwt_manager=jwt_manager,
            user_getter=user_getter,
            auto_error=False
        )
        
        @app.get("/me")
        def get_me(user=Depends(get_current_user)):
            return {"id": user.id, "username": user.username}
        
        @app.get("/me-optional")
        def get_me_optional(user=Depends(get_current_user_optional)):
            if user:
                return {"id": user.id, "username": user.username}
            return {"user": None}
        
        return app
    
    @pytest.fixture
    def auth_client(self, auth_app):
        return TestClient(auth_app)
    
    def test_authenticated_request(self, auth_client, jwt_manager):
        """测试认证成功的请求"""
        payload = TokenPayload(
            sub="user1",
            user_id=1,
            username="user1"
        )
        token = jwt_manager.create_access_token(payload)
        
        response = auth_client.get(
            "/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1
        assert data["username"] == "user1"
    
    def test_unauthenticated_request(self, auth_client):
        """测试未认证的请求"""
        response = auth_client.get("/me")
        
        assert response.status_code == 401
        assert response.json()["detail"] == "无法验证凭证"
    
    def test_invalid_token(self, auth_client):
        """测试无效令牌"""
        response = auth_client.get(
            "/me",
            headers={"Authorization": "Bearer invalid.token.here"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "无法验证凭证"
    
    def test_user_not_found(self, auth_client, jwt_manager):
        """测试用户不存在"""
        payload = TokenPayload(
            sub="nonexistent",
            user_id=999,  # 不存在的用户ID
            username="nonexistent"
        )
        token = jwt_manager.create_access_token(payload)
        
        response = auth_client.get(
            "/me",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 401
        assert response.json()["detail"] == "无法验证凭证"
    
    def test_optional_auth_without_token(self, auth_client):
        """测试可选认证-无令牌"""
        response = auth_client.get("/me-optional")
        
        assert response.status_code == 200
        data = response.json()
        assert data["user"] is None
    
    def test_optional_auth_with_token(self, auth_client, jwt_manager):
        """测试可选认证-有令牌"""
        payload = TokenPayload(
            sub="user1",
            user_id=1,
            username="user1"
        )
        token = jwt_manager.create_access_token(payload)
        
        response = auth_client.get(
            "/me-optional",
            headers={"Authorization": f"Bearer {token}"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 1

    def test_optional_auth_with_invalid_token_returns_none(self, auth_client):
        """测试可选认证下无效令牌返回匿名用户。"""
        response = auth_client.get(
            "/me-optional",
            headers={"Authorization": "Bearer invalid.token.here"},
        )
        assert response.status_code == 200
        assert response.json() == {"user": None}
    
    def test_refresh_token_not_accepted(self, auth_client, jwt_manager):
        """测试刷新令牌不能用于访问接口"""
        payload = TokenPayload(
            sub="user1",
            user_id=1,
            username="user1"
        )
        # 使用刷新令牌
        refresh_token = jwt_manager.create_refresh_token(payload)
        
        response = auth_client.get(
            "/me",
            headers={"Authorization": f"Bearer {refresh_token}"}
        )
        
        # 刷新令牌应该被拒绝
        assert response.status_code == 401


class TestAuthDependencyClass:
    """AuthDependency 类测试"""
    
    def test_auth_dependency_implementation(self, jwt_manager, mock_user):
        """测试 AuthDependency 实现"""
        class MyAuthDependency(AuthDependency):
            def get_user(self, user_id: int):
                if user_id == 1:
                    return mock_user(id=1, username="testuser")
                return None
        
        auth = MyAuthDependency(jwt_manager)
        
        # 创建测试应用
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint(user=Depends(auth.get_current_user)):
            return {"username": user.username}
        
        client = TestClient(app)
        
        # 创建令牌
        payload = TokenPayload(sub="testuser", user_id=1, username="testuser")
        token = jwt_manager.create_access_token(payload)
        
        response = client.get("/test", headers={"Authorization": f"Bearer {token}"})
        
        assert response.status_code == 200
        assert response.json()["username"] == "testuser"

    def test_get_current_user_optional_returns_none_when_missing_token(self, jwt_manager, mock_user):
        """测试基类可选认证在缺少令牌时返回 None。"""
        class MyAuthDependency(AuthDependency):
            def get_user(self, user_id: int):
                if user_id == 1:
                    return mock_user(id=1, username="testuser")
                return None

        auth = MyAuthDependency(jwt_manager)
        assert auth.get_current_user_optional(token=None) is None


class TestGetTokenFromHeader:
    """get_token_from_header 函数测试"""
    
    def test_get_token_from_valid_header(self):
        """测试从有效头部获取令牌"""
        from starlette.requests import Request
        from starlette.testclient import TestClient
        
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint(request: Request):
            token = get_token_from_header(request)
            return {"token": token}
        
        client = TestClient(app)
        response = client.get(
            "/test",
            headers={"Authorization": "Bearer test-token-123"}
        )
        
        assert response.json()["token"] == "test-token-123"
    
    def test_get_token_without_header(self):
        """测试无 Authorization 头部"""
        from starlette.requests import Request
        
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint(request: Request):
            token = get_token_from_header(request)
            return {"token": token}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.json()["token"] is None
    
    def test_get_token_with_invalid_format(self):
        """测试无效格式的 Authorization 头部"""
        from starlette.requests import Request
        
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint(request: Request):
            token = get_token_from_header(request)
            return {"token": token}
        
        client = TestClient(app)
        
        # 测试缺少 Bearer 前缀
        response = client.get(
            "/test",
            headers={"Authorization": "test-token"}
        )
        assert response.json()["token"] is None
        
        # 测试错误的认证类型
        response = client.get(
            "/test",
            headers={"Authorization": "Basic test-token"}
        )
        assert response.json()["token"] is None


class TestRoleChecker:
    """RoleChecker 类测试"""
    
    def test_role_checker_creation(self):
        """测试创建角色检查器"""
        checker = RoleChecker(["admin", "manager"])
        
        assert checker.allowed_roles == ["admin", "manager"]

    def test_role_checker_raises_401_without_token(self):
        """测试缺少令牌时返回 401。"""
        checker = RoleChecker(["admin"])
        with pytest.raises(HTTPException) as exc_info:
            checker(token=None, jwt_manager=object())
        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == "未提供认证信息"

    def test_role_checker_raises_401_without_jwt_manager(self):
        """测试缺少 jwt_manager 时返回 401。"""
        checker = RoleChecker(["admin"])
        with pytest.raises(HTTPException) as exc_info:
            checker(token="token", jwt_manager=None)
        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == "未提供认证信息"

    def test_role_checker_raises_401_with_invalid_token(self):
        """测试无效令牌时返回 401。"""
        checker = RoleChecker(["admin"])

        class FakeJWTManager:
            @staticmethod
            def verify_token(token):
                return None

        with pytest.raises(HTTPException) as exc_info:
            checker(token="bad", jwt_manager=FakeJWTManager())
        exc = exc_info.value
        assert exc.status_code == 401
        assert exc.detail == "无效的令牌"

    def test_role_checker_raises_403_when_role_not_allowed(self):
        """测试角色不满足时返回 403。"""
        checker = RoleChecker(["admin"])

        class FakeJWTManager:
            @staticmethod
            def verify_token(token):
                return SimpleNamespace(roles=["user"])

        with pytest.raises(HTTPException) as exc_info:
            checker(token="good", jwt_manager=FakeJWTManager())
        exc = exc_info.value
        assert exc.status_code == 403
        assert exc.detail == "权限不足"

    def test_role_checker_returns_true_when_role_allowed(self):
        """测试角色满足时返回 True。"""
        checker = RoleChecker(["admin"])

        class FakeJWTManager:
            @staticmethod
            def verify_token(token):
                return SimpleNamespace(roles=["admin", "user"])

        assert checker(token="good", jwt_manager=FakeJWTManager()) is True


class TestOAuth2Scheme:
    """OAuth2 Scheme 测试"""
    
    def test_oauth2_scheme_exists(self):
        """测试 OAuth2 Scheme 存在"""
        assert oauth2_scheme is not None
    
    def test_oauth2_scheme_auto_error_false(self):
        """测试 OAuth2 Scheme auto_error 为 False"""
        # oauth2_scheme 设置了 auto_error=False
        # 这意味着缺少令牌时不会自动抛出异常
        assert oauth2_scheme.auto_error == False

