"""Request ID 中间件测试

测试请求 ID 生成和传递功能
"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.middleware import RequestIDMiddleware, get_request_id


class TestRequestIDMiddleware:
    """RequestIDMiddleware 测试"""
    
    @pytest.fixture
    def app_with_middleware(self):
        """创建带中间件的应用"""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"request_id": get_request_id()}
        
        @app.get("/nested")
        def nested_endpoint():
            # 模拟嵌套调用
            inner_id = get_request_id()
            return {"inner_request_id": inner_id}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_middleware):
        return TestClient(app_with_middleware)
    
    def test_request_id_generated(self, client):
        """测试请求 ID 自动生成"""
        response = client.get("/test")
        
        assert response.status_code == 200
        data = response.json()
        assert "request_id" in data
        assert data["request_id"] is not None
        assert len(data["request_id"]) > 0
    
    def test_request_id_in_response_header(self, client):
        """测试请求 ID 在响应头中"""
        response = client.get("/test")
        
        # 响应头中应该有 X-Request-ID
        assert "X-Request-ID" in response.headers or "x-request-id" in response.headers
    
    def test_request_id_unique(self, client):
        """测试请求 ID 唯一"""
        ids = set()
        for _ in range(10):
            response = client.get("/test")
            data = response.json()
            ids.add(data["request_id"])
        
        # 所有 ID 应该唯一
        assert len(ids) == 10
    

    
    def test_request_id_consistent_within_request(self, client):
        """测试同一请求内 ID 一致"""
        response = client.get("/test")
        
        data = response.json()
        header_id = response.headers.get("X-Request-ID") or response.headers.get("x-request-id")
        
        # 响应体和响应头中的 ID 应该一致
        assert data["request_id"] == header_id
    
    def test_request_id_format(self, client):
        """测试请求 ID 格式"""
        response = client.get("/test")
        data = response.json()
        request_id = data["request_id"]
        
        # 通常是 UUID 格式或自定义格式
        # 至少应该是非空字符串
        assert isinstance(request_id, str)
        assert len(request_id) >= 8  # 最短也应该有一定长度


class TestGetRequestId:
    """get_request_id 函数测试"""
    

    
    def test_get_request_id_in_request(self):
        """测试在请求中获取 ID"""
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
        
        captured_id = None
        
        @app.get("/capture")
        def capture():
            nonlocal captured_id
            captured_id = get_request_id()
            return {"ok": True}
        
        client = TestClient(app)
        client.get("/capture")
        
        assert captured_id is not None
        assert len(captured_id) > 0


class TestRequestIDMiddlewareConfiguration:
    """RequestIDMiddleware 配置测试"""
    
    def test_custom_header_name(self):
        """测试当前实现不支持自定义头名称参数"""
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        app.add_middleware(
            RequestIDMiddleware,
            header_name="X-Trace-ID"
        )
        # Starlette 会在应用启动/首个请求时实例化中间件
        with pytest.raises(TypeError):
            with TestClient(app) as client:
                client.get("/test")
    
    def test_generator_function(self):
        """测试当前实现不支持自定义生成器参数"""
        app = FastAPI()
        
        @app.get("/test")
        def test_endpoint():
            return {"ok": True}

        def custom_generator():
            return "req-00001"

        app.add_middleware(
            RequestIDMiddleware,
            generator=custom_generator
        )
        with pytest.raises(TypeError):
            with TestClient(app) as client:
                client.get("/test")

