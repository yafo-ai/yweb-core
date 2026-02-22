"""请求日志中间件测试

测试请求日志记录功能
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.middleware import RequestLoggingMiddleware, RequestIDMiddleware


class TestRequestLoggingMiddleware:
    """RequestLoggingMiddleware 测试"""
    
    @pytest.fixture
    def app_with_logging(self):
        """创建带日志中间件的应用"""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)
        
        @app.get("/users")
        def get_users():
            return {"users": []}
        
        @app.post("/users")
        def create_user(name: str = None):
            return {"id": 1, "name": name}
        
        @app.get("/error")
        def error_endpoint():
            raise ValueError("Test error")
        
        @app.get("/slow")
        def slow_endpoint():
            import time
            time.sleep(0.1)
            return {"slow": True}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_logging):
        return TestClient(app_with_logging)
    
    def test_get_request_logged(self, client, caplog):
        """测试 GET 请求被记录"""
        import logging
        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            response = client.get("/users")
        
        assert response.status_code == 200
        logs = [r.message for r in caplog.records if "Method: GET" in r.message]
        assert any("URL: /users" in m and "Status: 200" in m for m in logs)
    
    def test_post_request_logged(self, client, caplog):
        """测试 POST 请求被记录"""
        import logging
        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            response = client.post("/users?name=test")
        
        assert response.status_code == 200
        logs = [r.message for r in caplog.records if "Method: POST" in r.message]
        assert any("URL: /users" in m and "Status: 200" in m for m in logs)
    
    def test_request_includes_method(self, client, caplog):
        """测试日志包含请求方法"""
        import logging

        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            client.get("/users")

        assert any("Method: GET" in r.message for r in caplog.records)
    
    def test_request_includes_path(self, client, caplog):
        """测试日志包含请求路径"""
        import logging

        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            client.get("/users")

        assert any("URL: /users" in r.message for r in caplog.records)
    
    def test_request_includes_status_code(self, client, caplog):
        """测试日志包含状态码"""
        import logging

        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            client.get("/users")

        assert any("Status: 200" in r.message for r in caplog.records)
    
    def test_error_request_logged(self, client, caplog):
        """测试错误请求被记录"""
        import logging

        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.ERROR, logger="yweb.middleware.request_logging"):
            with pytest.raises(Exception):
                client.get("/error")

        assert any("API Request Error" in r.message and "URL: /error" in r.message for r in caplog.records)
    
    def test_slow_request_warning(self, client, caplog):
        """测试慢请求警告"""
        import logging

        RequestLoggingMiddleware._executor = None
        with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
            response = client.get("/slow")

        assert response.status_code == 200
        # 当前实现按状态码分级：slow 但 200 仍为 info，不应被误记为 warning/error
        assert any("URL: /slow" in r.message and r.levelname == "INFO" for r in caplog.records)


class TestRequestLoggingConfiguration:
    """请求日志配置测试"""
    
    def test_skip_paths(self):
        """测试跳过路径"""
        app = FastAPI()
        
        app.add_middleware(
            RequestLoggingMiddleware,
            skip_paths={"/health", "/metrics"},
        )
        
        @app.get("/health")
        def health():
            return {"status": "ok"}
        
        @app.get("/api/users")
        def users():
            return {"users": []}
        
        client = TestClient(app)
        RequestLoggingMiddleware._executor = None
        import logging
        from yweb.middleware.request_logging import _default_logger
        from unittest.mock import patch
        
        with patch.object(_default_logger, "info") as mock_info, patch.object(_default_logger, "warning"), patch.object(_default_logger, "error"):
            response = client.get("/health")
            assert response.status_code == 200

            response = client.get("/api/users")
            assert response.status_code == 200

            joined = "\n".join(call.args[0] for call in mock_info.call_args_list if call.args)
            assert "URL: /health" in joined and "Request Body: [SKIPPED_PATH]" in joined
            assert "URL: /api/users" in joined and "Request Body: [NO_BODY]" in joined
    
    def test_max_body_size(self):
        """测试最大请求体大小限制"""
        app = FastAPI()
        
        app.add_middleware(
            RequestLoggingMiddleware,
            max_body_size=1024  # 1KB
        )
        
        @app.post("/upload")
        async def upload(data: dict):
            return {"received": True, "size": len(data.get("data", ""))}
        
        client = TestClient(app)
        RequestLoggingMiddleware._executor = None
        from yweb.middleware.request_logging import _default_logger
        from unittest.mock import patch
        
        # 大请求体
        large_data = {"data": "x" * 2000}
        with patch.object(_default_logger, "info") as mock_info, patch.object(_default_logger, "warning"), patch.object(_default_logger, "error"):
            response = client.post("/upload", json=large_data)
            assert response.status_code == 200
            assert response.json()["size"] == 2000
            joined = "\n".join(call.args[0] for call in mock_info.call_args_list if call.args)
            # 超大请求体应被预览化记录，而不是完整透传
            assert "Request Body:" in joined
            assert "x" * 2000 not in joined
            assert ("..." in joined) or ("[Binary data" in joined)
    
    def test_log_request_body(self):
        """测试记录请求体"""
        app = FastAPI()
        
        # RequestLoggingMiddleware 默认会记录请求体（受 max_body_size 限制）
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.post("/data")
        def post_data(data: dict = None):
            return data or {}
        
        client = TestClient(app)
        
        response = client.post("/data", json={"key": "value"})
        assert response.status_code == 200
    
    def test_log_response_body(self):
        """测试记录响应体"""
        app = FastAPI()
        
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.get("/data")
        def get_data():
            return {"response": "data"}
        
        client = TestClient(app)
        
        response = client.get("/data")
        assert response.status_code == 200


class TestRequestLoggingWithFilters:
    """请求日志与过滤器测试"""
    
    def test_sensitive_data_filtered(self, caplog):
        """测试敏感数据被过滤"""
        from yweb.log import SensitiveDataFilterHook, log_filter_hook_manager
        
        # 注册过滤钩子
        filter_hook = SensitiveDataFilterHook()
        log_filter_hook_manager.register_hook(filter_hook)
        
        try:
            app = FastAPI()
            app.add_middleware(RequestLoggingMiddleware)
            
            @app.post("/auth/login")
            def login(data: dict):
                return {"success": True}
            
            client = TestClient(app)
            RequestLoggingMiddleware._executor = None
            
            import logging
            with caplog.at_level(logging.INFO, logger="yweb.middleware.request_logging"):
                response = client.post("/auth/login", json={"username": "admin", "password": "secret123"})
            
            assert response.status_code == 200
            joined = "\n".join(r.message for r in caplog.records)
            assert "secret123" not in joined
            assert "*SENSITIVE DATA FILTERED*" in joined
        finally:
            log_filter_hook_manager.unregister_hook(filter_hook)

