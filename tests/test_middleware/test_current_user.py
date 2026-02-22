"""当前用户中间件测试

测试 CurrentUserMiddleware 和 SimpleCurrentUserMiddleware 的功能

测试覆盖：
- ContextVar 操作：set_current_user_id, get_current_user_id, clear_current_user_id
- CurrentUserMiddleware 中间件
- SimpleCurrentUserMiddleware 中间件
- 路径跳过逻辑
- JWT Token 解析
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from starlette.responses import JSONResponse

from yweb.middleware.current_user import (
    CurrentUserMiddleware,
    SimpleCurrentUserMiddleware,
    set_current_user_id,
    get_current_user_id,
    clear_current_user_id,
)


# ==================== ContextVar 操作测试 ====================

class TestContextVarOperations:
    """ContextVar 操作测试"""
    
    def test_set_and_get_integer_user_id(self):
        """测试设置和获取整数 user_id"""
        clear_current_user_id()
        
        set_current_user_id(123)
        assert get_current_user_id() == 123
        
        clear_current_user_id()
        assert get_current_user_id() is None
    
    def test_set_and_get_string_user_id(self):
        """测试设置和获取字符串 user_id"""
        clear_current_user_id()
        
        set_current_user_id("user_abc_123")
        assert get_current_user_id() == "user_abc_123"
        
        clear_current_user_id()
    
    def test_set_none_clears_user_id(self):
        """测试设置 None"""
        set_current_user_id(100)
        assert get_current_user_id() == 100
        
        set_current_user_id(None)
        assert get_current_user_id() is None
    
    def test_clear_current_user_id(self):
        """测试 clear_current_user_id"""
        set_current_user_id(999)
        assert get_current_user_id() == 999
        
        clear_current_user_id()
        assert get_current_user_id() is None
    
    def test_default_value_is_none(self):
        """测试默认值为 None"""
        clear_current_user_id()
        assert get_current_user_id() is None
    
    def test_overwrite_user_id(self):
        """测试覆盖 user_id"""
        set_current_user_id(1)
        assert get_current_user_id() == 1
        
        set_current_user_id(2)
        assert get_current_user_id() == 2
        
        clear_current_user_id()


# ==================== CurrentUserMiddleware 测试 ====================

class TestCurrentUserMiddleware:
    """CurrentUserMiddleware 中间件测试"""
    
    @pytest.fixture
    def mock_jwt_manager(self):
        """创建 mock JWTManager"""
        manager = Mock()
        return manager
    
    @pytest.fixture
    def app_with_middleware(self, mock_jwt_manager):
        """创建带中间件的测试应用"""
        app = FastAPI()
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager,
            skip_paths=["/login", "/public"]
        )
        
        @app.get("/test")
        def test_endpoint():
            user_id = get_current_user_id()
            return {"user_id": user_id}
        
        @app.get("/login")
        def login_endpoint():
            return {"message": "login"}
        
        @app.get("/public")
        def public_endpoint():
            return {"message": "public"}
        
        @app.get("/docs")
        def docs_endpoint():
            return {"message": "docs"}
        
        return app, mock_jwt_manager
    
    def test_middleware_extracts_user_id_from_token(self, app_with_middleware):
        """测试中间件从 Token 提取 user_id"""
        app, mock_jwt_manager = app_with_middleware
        
        # Mock token 验证返回包含 user_id 的对象
        token_data = Mock()
        token_data.user_id = 42
        mock_jwt_manager.verify_token.return_value = token_data
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer valid_token"})
        
        assert response.status_code == 200
        assert response.json()["user_id"] == 42
    
    def test_middleware_clears_user_id_after_request(self, app_with_middleware):
        """测试请求结束后清理 user_id"""
        app, mock_jwt_manager = app_with_middleware
        
        token_data = Mock()
        token_data.user_id = 42
        mock_jwt_manager.verify_token.return_value = token_data
        
        client = TestClient(app)
        
        # 第一个请求
        response1 = client.get("/test", headers={"Authorization": "Bearer valid_token"})
        assert response1.json()["user_id"] == 42
        
        # 请求结束后 ContextVar 应该被清理
        # 第二个请求不带 token
        response2 = client.get("/test")
        assert response2.json()["user_id"] is None
    
    def test_middleware_skips_login_path(self, app_with_middleware):
        """测试跳过登录路径"""
        app, mock_jwt_manager = app_with_middleware
        
        client = TestClient(app)
        response = client.get("/login")
        
        assert response.status_code == 200
        # jwt_manager 不应该被调用
        mock_jwt_manager.verify_token.assert_not_called()
    
    def test_middleware_skips_default_paths(self, app_with_middleware):
        """测试跳过默认路径（如 /docs）"""
        app, mock_jwt_manager = app_with_middleware
        
        client = TestClient(app)
        response = client.get("/docs")
        
        assert response.status_code == 200
        mock_jwt_manager.verify_token.assert_not_called()
    
    def test_middleware_handles_invalid_token(self, app_with_middleware):
        """测试处理无效 Token"""
        app, mock_jwt_manager = app_with_middleware
        
        # Mock token 验证抛出异常
        mock_jwt_manager.verify_token.side_effect = Exception("Invalid token")
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer invalid_token"})
        
        assert response.status_code == 200
        assert response.json()["user_id"] is None
    
    def test_middleware_handles_missing_token(self, app_with_middleware):
        """测试处理缺失 Token"""
        app, mock_jwt_manager = app_with_middleware
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json()["user_id"] is None
    
    def test_middleware_handles_malformed_authorization_header(self, app_with_middleware):
        """测试处理格式错误的 Authorization 头"""
        app, mock_jwt_manager = app_with_middleware
        
        client = TestClient(app)
        
        # 缺少 Bearer 前缀
        response1 = client.get("/test", headers={"Authorization": "token_only"})
        assert response1.json()["user_id"] is None
        
        # 错误的前缀
        response2 = client.get("/test", headers={"Authorization": "Basic abc123"})
        assert response2.json()["user_id"] is None
    
    def test_middleware_without_jwt_manager(self):
        """测试不提供 jwt_manager 的情况"""
        app = FastAPI()
        
        app.add_middleware(CurrentUserMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer token"})
        
        assert response.status_code == 200
        assert response.json()["user_id"] is None


# ==================== CurrentUserMiddleware 初始化测试 ====================

class TestCurrentUserMiddlewareInit:
    """CurrentUserMiddleware 初始化测试"""
    
    def test_default_skip_paths(self):
        """测试默认跳过路径"""
        app = FastAPI()
        middleware = CurrentUserMiddleware(app)
        
        assert "/docs" in middleware.skip_paths
        assert "/redoc" in middleware.skip_paths
        assert "/openapi.json" in middleware.skip_paths
        assert "/health" in middleware.skip_paths
        assert "/ping" in middleware.skip_paths
    
    def test_custom_skip_paths_merged(self):
        """测试自定义跳过路径与默认路径合并"""
        app = FastAPI()
        middleware = CurrentUserMiddleware(
            app,
            skip_paths=["/login", "/register"]
        )
        
        # 应该包含默认路径
        assert "/docs" in middleware.skip_paths
        # 应该包含自定义路径
        assert "/login" in middleware.skip_paths
        assert "/register" in middleware.skip_paths
    
    def test_custom_user_id_extractor(self):
        """测试自定义 user_id 提取函数"""
        app = FastAPI()
        
        def custom_extractor(token_data):
            return token_data.sub  # 从 sub 字段提取
        
        middleware = CurrentUserMiddleware(
            app,
            user_id_extractor=custom_extractor
        )
        
        # 测试自定义提取函数
        token_data = Mock()
        token_data.sub = "custom_user_123"
        
        result = middleware.user_id_extractor(token_data)
        assert result == "custom_user_123"


# ==================== 路径匹配测试 ====================

class TestPathMatching:
    """路径匹配测试（通过端到端测试验证行为）"""
    
    def test_exact_path_match(self):
        """测试精确路径匹配"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager,
            skip_paths=["/api/auth"]
        )
        
        @app.get("/api/auth")
        def auth_endpoint():
            return {"ok": True}
        
        @app.get("/api/auth2")
        def auth2_endpoint():
            return {"ok": True}
        
        client = TestClient(app)
        
        # 访问跳过路径（带 token）
        client.get("/api/auth", headers={"Authorization": "Bearer test_token"})
        # jwt_manager 不应该被调用
        mock_jwt_manager.verify_token.assert_not_called()
        
        # 重置 mock
        mock_jwt_manager.reset_mock()
        
        # 访问非跳过路径（带 token）
        client.get("/api/auth2", headers={"Authorization": "Bearer test_token"})
        # jwt_manager 应该被调用
        mock_jwt_manager.verify_token.assert_called()
    
    def test_prefix_path_match(self):
        """测试前缀路径匹配"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager,
            skip_paths=["/docs"]
        )
        
        @app.get("/docs")
        def docs_endpoint():
            return {"ok": True}
        
        @app.get("/docs/swagger")
        def docs_swagger_endpoint():
            return {"ok": True}
        
        @app.get("/documents")
        def documents_endpoint():
            return {"ok": True}
        
        client = TestClient(app)
        
        # 访问 /docs - 应该跳过（带 token）
        client.get("/docs", headers={"Authorization": "Bearer test_token"})
        mock_jwt_manager.verify_token.assert_not_called()
        
        mock_jwt_manager.reset_mock()
        
        # 访问 /docs/swagger - 应该跳过（前缀匹配，带 token）
        client.get("/docs/swagger", headers={"Authorization": "Bearer test_token"})
        mock_jwt_manager.verify_token.assert_not_called()
        
        mock_jwt_manager.reset_mock()
        
        # 访问 /documents - 不应该跳过（带 token）
        client.get("/documents", headers={"Authorization": "Bearer test_token"})
        mock_jwt_manager.verify_token.assert_called()


# ==================== Token 解析测试 ====================

class TestTokenParsing:
    """Token 解析测试（通过端到端测试验证行为）"""
    
    def test_get_token_from_valid_header(self):
        """测试从有效头部获取 Token"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        # Mock token 验证返回包含 user_id 的对象
        token_data = Mock()
        token_data.user_id = 999
        mock_jwt_manager.verify_token.return_value = token_data
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer my_jwt_token"})
        
        # 验证 token 被正确解析并传递给 jwt_manager
        mock_jwt_manager.verify_token.assert_called_once_with("my_jwt_token")
        assert response.json()["user_id"] == 999
    
    def test_get_token_from_missing_header(self):
        """测试缺少 Authorization 头部"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test")
        
        # jwt_manager 不应该被调用
        mock_jwt_manager.verify_token.assert_not_called()
        assert response.json()["user_id"] is None
    
    def test_get_token_from_invalid_format(self):
        """测试无效格式的 Authorization 头部"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        
        # 缺少 Bearer
        response1 = client.get("/test", headers={"Authorization": "my_token"})
        assert response1.json()["user_id"] is None
        
        # 错误前缀
        response2 = client.get("/test", headers={"Authorization": "Basic my_token"})
        assert response2.json()["user_id"] is None
        
        # 多余部分
        response3 = client.get("/test", headers={"Authorization": "Bearer token extra"})
        assert response3.json()["user_id"] is None
        
        # jwt_manager 不应该被调用
        mock_jwt_manager.verify_token.assert_not_called()
    
    def test_bearer_case_insensitive(self):
        """测试 Bearer 大小写不敏感"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        token_data = Mock()
        token_data.user_id = 888
        mock_jwt_manager.verify_token.return_value = token_data
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        
        # 小写 bearer
        response1 = client.get("/test", headers={"Authorization": "bearer my_token"})
        assert response1.json()["user_id"] == 888
        
        mock_jwt_manager.reset_mock()
        
        # 大写 BEARER
        response2 = client.get("/test", headers={"Authorization": "BEARER my_token"})
        assert response2.json()["user_id"] == 888


# ==================== SimpleCurrentUserMiddleware 测试 ====================

class TestSimpleCurrentUserMiddleware:
    """SimpleCurrentUserMiddleware 中间件测试"""
    
    @pytest.fixture
    def app_with_simple_middleware(self):
        """创建带简化中间件的测试应用"""
        app = FastAPI()
        
        def get_user_id_from_header(request: Request):
            user_id = request.headers.get("X-User-ID")
            return int(user_id) if user_id else None
        
        app.add_middleware(
            SimpleCurrentUserMiddleware,
            user_id_getter=get_user_id_from_header,
            skip_paths=["/public"]
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        @app.get("/public")
        def public_endpoint():
            return {"message": "public"}
        
        return app
    
    def test_simple_middleware_extracts_user_id(self, app_with_simple_middleware):
        """测试简化中间件提取 user_id"""
        client = TestClient(app_with_simple_middleware)
        
        response = client.get("/test", headers={"X-User-ID": "123"})
        
        assert response.status_code == 200
        assert response.json()["user_id"] == 123
    
    def test_simple_middleware_handles_missing_header(self, app_with_simple_middleware):
        """测试简化中间件处理缺失头部"""
        client = TestClient(app_with_simple_middleware)
        
        response = client.get("/test")
        
        assert response.status_code == 200
        assert response.json()["user_id"] is None
    
    def test_simple_middleware_skips_path(self, app_with_simple_middleware):
        """测试简化中间件跳过路径"""
        client = TestClient(app_with_simple_middleware)
        
        response = client.get("/public")
        
        assert response.status_code == 200
        assert response.json()["message"] == "public"
    
    def test_simple_middleware_clears_user_id_after_request(self, app_with_simple_middleware):
        """测试请求结束后清理 user_id"""
        client = TestClient(app_with_simple_middleware)
        
        # 带 user_id 的请求
        response1 = client.get("/test", headers={"X-User-ID": "456"})
        assert response1.json()["user_id"] == 456
        
        # 不带 user_id 的请求
        response2 = client.get("/test")
        assert response2.json()["user_id"] is None
    
    def test_simple_middleware_handles_getter_exception(self):
        """测试简化中间件处理 getter 异常"""
        app = FastAPI()
        
        def bad_getter(request: Request):
            raise ValueError("Error getting user")
        
        app.add_middleware(
            SimpleCurrentUserMiddleware,
            user_id_getter=bad_getter
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test")
        
        # 应该正常返回，user_id 为 None
        assert response.status_code == 200
        assert response.json()["user_id"] is None


# ==================== 默认 user_id 提取器测试 ====================

class TestDefaultUserIdExtractor:
    """默认 user_id 提取器测试（通过端到端测试验证行为）"""
    
    def test_extract_user_id_attribute(self):
        """测试从 user_id 属性提取"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        # Mock token 验证返回包含 user_id 的对象
        token_data = Mock()
        token_data.user_id = 123
        mock_jwt_manager.verify_token.return_value = token_data
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer valid_token"})
        
        assert response.json()["user_id"] == 123
    
    def test_extract_returns_none_for_none_token(self):
        """测试 token_data 为 None 时返回 None"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        # Mock token 验证返回 None
        mock_jwt_manager.verify_token.return_value = None
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer valid_token"})
        
        assert response.json()["user_id"] is None
    
    def test_extract_returns_none_for_missing_attribute(self):
        """测试缺少 user_id 属性时返回 None"""
        app = FastAPI()
        mock_jwt_manager = Mock()
        
        # Mock token 验证返回没有 user_id 属性的对象
        token_data = Mock(spec=[])  # 没有任何属性
        mock_jwt_manager.verify_token.return_value = token_data
        
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=mock_jwt_manager
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        response = client.get("/test", headers={"Authorization": "Bearer valid_token"})
        
        assert response.json()["user_id"] is None


# ==================== 并发安全测试 ====================

class TestConcurrencySafety:
    """并发安全测试"""
    
    def test_context_var_isolation_between_requests(self):
        """测试请求之间的 ContextVar 隔离"""
        app = FastAPI()
        
        def get_user_from_header(request: Request):
            return request.headers.get("X-User-ID")
        
        app.add_middleware(
            SimpleCurrentUserMiddleware,
            user_id_getter=get_user_from_header
        )
        
        @app.get("/test")
        def test_endpoint():
            return {"user_id": get_current_user_id()}
        
        client = TestClient(app)
        
        # 模拟多个请求
        response1 = client.get("/test", headers={"X-User-ID": "user_1"})
        response2 = client.get("/test", headers={"X-User-ID": "user_2"})
        response3 = client.get("/test")
        
        assert response1.json()["user_id"] == "user_1"
        assert response2.json()["user_id"] == "user_2"
        assert response3.json()["user_id"] is None
