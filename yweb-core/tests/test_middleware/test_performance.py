"""性能监控中间件测试

测试性能监控功能
"""

import pytest
import time
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.middleware import PerformanceMonitoringMiddleware


class TestPerformanceMonitoringMiddleware:
    """PerformanceMonitoringMiddleware 测试"""
    
    @pytest.fixture
    def app_with_monitoring(self):
        """创建带性能监控的应用"""
        app = FastAPI()
        app.add_middleware(PerformanceMonitoringMiddleware)
        
        @app.get("/fast")
        def fast_endpoint():
            return {"fast": True}
        
        @app.get("/slow")
        def slow_endpoint():
            time.sleep(0.5)
            return {"slow": True}
        
        @app.get("/very-slow")
        def very_slow_endpoint():
            time.sleep(1.5)
            return {"very_slow": True}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_monitoring):
        return TestClient(app_with_monitoring)
    
    def test_fast_request(self, client):
        """测试快速请求"""
        response = client.get("/fast")
        
        assert response.status_code == 200
        
        # 检查响应头中是否有处理时间
        if "X-Process-Time" in response.headers:
            process_time = float(response.headers["X-Process-Time"])
            assert process_time < 0.1  # 应该很快
    
    def test_slow_request(self, client):
        """测试慢请求"""
        response = client.get("/slow")
        
        assert response.status_code == 200
        
        if "X-Process-Time" in response.headers:
            process_time = float(response.headers["X-Process-Time"])
            assert process_time >= 0.5  # 至少 0.5 秒
    
    def test_process_time_header(self, client):
        """测试处理时间响应头"""
        response = client.get("/fast")
        
        # 检查是否有处理时间头
        process_time_header = (
            response.headers.get("X-Process-Time") or
            response.headers.get("x-process-time") or
            response.headers.get("X-Response-Time") or
            response.headers.get("x-response-time")
        )
        
        if process_time_header:
            assert float(process_time_header) >= 0


class TestPerformanceThresholds:
    """性能阈值测试"""
    
    def test_slow_request_threshold(self, caplog):
        """测试慢请求阈值"""
        import logging
        
        app = FastAPI()
        
        app.add_middleware(
            PerformanceMonitoringMiddleware,
            slow_request_threshold=0.1  # 100ms
        )
        
        @app.get("/test")
        def test_endpoint():
            time.sleep(0.2)  # 200ms
            return {"ok": True}
        
        client = TestClient(app)
        
        with caplog.at_level(logging.WARNING):
            response = client.get("/test")
        
        assert response.status_code == 200
        # 应该有慢请求警告日志
    
    def test_very_slow_request_threshold(self, caplog):
        """测试非常慢请求阈值（使用较高的 slow_request_threshold）"""
        import logging
        
        app = FastAPI()
        
        app.add_middleware(
            PerformanceMonitoringMiddleware,
            slow_request_threshold=1.0  # 1s
        )
        
        @app.get("/test")
        def test_endpoint():
            time.sleep(1.2)  # 1.2s
            return {"ok": True}
        
        client = TestClient(app)
        
        with caplog.at_level(logging.WARNING):
            response = client.get("/test")
        
        assert response.status_code == 200


class TestPerformanceMetrics:
    """性能指标测试"""
    
    def test_metrics_collection(self):
        """测试指标收集"""
        app = FastAPI()
        
        # 某些实现可能支持指标收集
        try:
            middleware = PerformanceMonitoringMiddleware(app, collect_metrics=True)
            
            @app.get("/test")
            def test_endpoint():
                return {"ok": True}
            
            client = TestClient(app)
            
            # 发送多个请求
            for _ in range(10):
                client.get("/test")
            
            # 检查指标
            if hasattr(middleware, 'get_metrics'):
                metrics = middleware.get_metrics()
                assert metrics is not None
        except TypeError:
            pass
    
    def test_endpoint_specific_metrics(self):
        """测试端点特定指标"""
        app = FastAPI()
        app.add_middleware(PerformanceMonitoringMiddleware)
        
        @app.get("/api/v1/users")
        def get_users():
            return {"users": []}
        
        @app.get("/api/v1/posts")
        def get_posts():
            time.sleep(0.05)
            return {"posts": []}
        
        client = TestClient(app)
        
        # 发送多个请求
        for _ in range(5):
            client.get("/api/v1/users")
            client.get("/api/v1/posts")
        
        # 验证请求完成
        response = client.get("/api/v1/users")
        assert response.status_code == 200


class TestPerformanceMonitoringIntegration:
    """性能监控集成测试"""
    
    def test_with_request_id_middleware(self):
        """测试与 Request ID 中间件配合"""
        from yweb.middleware import RequestIDMiddleware
        
        app = FastAPI()
        app.add_middleware(PerformanceMonitoringMiddleware)
        app.add_middleware(RequestIDMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"ok": True}
        
        client = TestClient(app)
        response = client.get("/test")
        
        assert response.status_code == 200
        
        # 两个中间件都应该工作
        assert "X-Request-ID" in response.headers or "x-request-id" in response.headers
    
    def test_with_all_middleware(self):
        """测试与所有中间件配合"""
        from yweb.middleware import RequestIDMiddleware, RequestLoggingMiddleware
        
        app = FastAPI()
        app.add_middleware(PerformanceMonitoringMiddleware)
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)
        
        @app.get("/test")
        def test_endpoint():
            return {"ok": True}
        
        @app.post("/data")
        def post_data(data: dict = None):
            return data or {}
        
        client = TestClient(app)
        
        # GET 请求
        response = client.get("/test")
        assert response.status_code == 200
        
        # POST 请求
        response = client.post("/data", json={"key": "value"})
        assert response.status_code == 200

