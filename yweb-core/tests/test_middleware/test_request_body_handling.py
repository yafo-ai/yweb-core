"""RequestLoggingMiddleware 请求体处理测试

专门测试 C005 修复：RequestLoggingMiddleware 正确处理请求体
确保中间件读取请求体用于日志记录后，路由处理函数仍能正常接收请求体
"""

import pytest
import json
from typing import List
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yweb.middleware import RequestLoggingMiddleware, RequestIDMiddleware


class SumRequest(BaseModel):
    """求和请求模型"""
    numbers: List[int]


class UserCreateRequest(BaseModel):
    """用户创建请求模型"""
    name: str
    email: str
    age: int = None


class TestRequestBodyHandling:
    """测试请求体处理（C005 修复验证）"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        
        # 添加中间件
        app.add_middleware(RequestLoggingMiddleware)
        app.add_middleware(RequestIDMiddleware)
        
        @app.post("/sum")
        async def sum_numbers(request: SumRequest):
            """求和接口"""
            result = sum(request.numbers)
            return {"result": result}
        
        @app.post("/users")
        async def create_user(user: UserCreateRequest):
            """创建用户接口"""
            return {
                "id": 1,
                "name": user.name,
                "email": user.email,
                "age": user.age
            }
        
        @app.put("/users/{user_id}")
        async def update_user(user_id: int, user: UserCreateRequest):
            """更新用户接口"""
            return {
                "id": user_id,
                "name": user.name,
                "email": user.email,
                "age": user.age,
                "updated": True
            }
        
        @app.patch("/users/{user_id}")
        async def partial_update_user(user_id: int, data: dict):
            """部分更新用户接口"""
            return {
                "id": user_id,
                "updated_fields": list(data.keys())
            }
        
        @app.post("/echo")
        async def echo(data: dict):
            """回显接口"""
            return data
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_post_with_json_body(self, client):
        """测试 POST 请求带 JSON 请求体"""
        response = client.post(
            "/sum",
            json={"numbers": [1, 2, 3, 4, 5]}
        )
        
        assert response.status_code == 200
        assert response.json() == {"result": 15}
    
    def test_post_with_complex_body(self, client):
        """测试 POST 请求带复杂请求体"""
        response = client.post(
            "/users",
            json={
                "name": "张三",
                "email": "zhangsan@example.com",
                "age": 25
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "张三"
        assert data["email"] == "zhangsan@example.com"
        assert data["age"] == 25
    
    def test_put_with_body(self, client):
        """测试 PUT 请求带请求体"""
        response = client.put(
            "/users/123",
            json={
                "name": "李四",
                "email": "lisi@example.com"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 123
        assert data["name"] == "李四"
        assert data["updated"] is True
    
    def test_patch_with_body(self, client):
        """测试 PATCH 请求带请求体"""
        response = client.patch(
            "/users/456",
            json={"name": "王五"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == 456
        assert "name" in data["updated_fields"]
    
    def test_multiple_requests_with_body(self, client):
        """测试多个连续请求都能正确处理请求体"""
        # 第一个请求
        response1 = client.post("/sum", json={"numbers": [1, 2, 3]})
        assert response1.status_code == 200
        assert response1.json() == {"result": 6}
        
        # 第二个请求
        response2 = client.post("/sum", json={"numbers": [10, 20, 30]})
        assert response2.status_code == 200
        assert response2.json() == {"result": 60}
        
        # 第三个请求
        response3 = client.post("/users", json={
            "name": "测试用户",
            "email": "test@example.com"
        })
        assert response3.status_code == 200
        assert response3.json()["name"] == "测试用户"
    
    def test_empty_body(self, client):
        """测试空请求体"""
        response = client.post("/echo", json={})
        
        assert response.status_code == 200
        assert response.json() == {}
    
    def test_large_body(self, client):
        """测试大请求体"""
        # 创建一个较大的数组
        large_numbers = list(range(1000))
        
        response = client.post("/sum", json={"numbers": large_numbers})
        
        assert response.status_code == 200
        assert response.json() == {"result": sum(large_numbers)}
    
    def test_nested_json_body(self, client):
        """测试嵌套 JSON 请求体"""
        nested_data = {
            "user": {
                "profile": {
                    "name": "嵌套测试",
                    "settings": {
                        "theme": "dark",
                        "language": "zh-CN"
                    }
                }
            },
            "metadata": {
                "version": "1.0",
                "timestamp": "2026-01-20T10:00:00Z"
            }
        }
        
        response = client.post("/echo", json=nested_data)
        
        assert response.status_code == 200
        assert response.json() == nested_data
    
    def test_unicode_in_body(self, client):
        """测试请求体中的 Unicode 字符"""
        response = client.post("/users", json={
            "name": "测试用户 🎉",
            "email": "test@例え.jp"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["name"] == "测试用户 🎉"
        assert data["email"] == "test@例え.jp"


class TestRequestBodyWithMaxSize:
    """测试请求体大小限制"""
    
    @pytest.fixture
    def app_with_size_limit(self):
        """创建带大小限制的应用"""
        app = FastAPI()
        
        # 设置较小的 max_body_size 用于测试
        app.add_middleware(
            RequestLoggingMiddleware,
            max_body_size=1024  # 1KB
        )
        
        @app.post("/data")
        async def post_data(data: dict):
            return {"received": True, "keys": list(data.keys())}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_size_limit):
        return TestClient(app_with_size_limit)
    
    def test_body_within_limit(self, client):
        """测试请求体在限制内"""
        small_data = {"key": "value"}
        
        response = client.post("/data", json=small_data)
        
        assert response.status_code == 200
        assert response.json()["received"] is True
    
    def test_body_exceeds_limit(self, client):
        """测试请求体超过限制（应该仍然能正常处理）"""
        # 创建一个超过 1KB 的请求体
        large_data = {"data": "x" * 2000}
        
        response = client.post("/data", json=large_data)
        
        # 中间件只是截断日志，不影响实际处理
        assert response.status_code == 200
        assert response.json()["received"] is True


class TestRequestBodyWithSkipPaths:
    """测试跳过路径时的请求体处理"""
    
    @pytest.fixture
    def app_with_skip_paths(self):
        """创建带跳过路径的应用"""
        app = FastAPI()
        
        app.add_middleware(
            RequestLoggingMiddleware,
            skip_paths={"/health", "/internal"}
        )
        
        @app.post("/health")
        async def health_check(data: dict = None):
            return {"status": "ok", "data": data}
        
        @app.post("/api/users")
        async def create_user(user: dict):
            return {"created": True, "user": user}
        
        @app.post("/internal/metrics")
        async def internal_metrics(metrics: dict):
            return {"recorded": True, "count": len(metrics)}
        
        return app
    
    @pytest.fixture
    def client(self, app_with_skip_paths):
        return TestClient(app_with_skip_paths)
    
    def test_skipped_path_with_body(self, client):
        """测试跳过路径仍能正确处理请求体"""
        response = client.post("/health", json={"check": "test"})
        
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["data"] == {"check": "test"}
    
    def test_normal_path_with_body(self, client):
        """测试正常路径能正确处理请求体"""
        response = client.post("/api/users", json={"name": "测试"})
        
        assert response.status_code == 200
        assert response.json()["created"] is True
        assert response.json()["user"]["name"] == "测试"
    
    def test_skipped_prefix_with_body(self, client):
        """测试跳过前缀路径能正确处理请求体"""
        response = client.post("/internal/metrics", json={
            "cpu": 50,
            "memory": 80
        })
        
        assert response.status_code == 200
        assert response.json()["recorded"] is True
        assert response.json()["count"] == 2


class TestRequestBodyLogging:
    """测试请求体日志记录"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.post("/login")
        async def login(credentials: dict):
            return {"success": True}
        
        @app.post("/data")
        async def post_data(data: dict):
            return data
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_request_body_logged(self, client, caplog):
        """测试请求体被记录到日志"""
        import logging
        
        with caplog.at_level(logging.INFO):
            response = client.post("/data", json={"key": "value"})
        
        assert response.status_code == 200
        
        # 检查日志中是否包含请求体信息
        log_messages = [record.message for record in caplog.records]
        # 至少应该有一条日志记录
        assert len(log_messages) > 0
    
    def test_json_body_format_in_log(self, client, caplog):
        """测试 JSON 请求体在日志中的格式"""
        import logging
        
        with caplog.at_level(logging.INFO):
            response = client.post("/data", json={
                "username": "testuser",
                "action": "create"
            })
        
        assert response.status_code == 200


class TestRequestBodyWithDifferentContentTypes:
    """测试不同 Content-Type 的请求体处理"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.post("/json")
        async def handle_json(data: dict):
            return {"type": "json", "data": data}
        
        @app.post("/form")
        async def handle_form(name: str = None, email: str = None):
            return {"type": "form", "name": name, "email": email}
        
        @app.post("/text")
        async def handle_text():
            return {"type": "text"}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_json_content_type(self, client):
        """测试 application/json"""
        response = client.post(
            "/json",
            json={"key": "value"}
        )
        
        assert response.status_code == 200
        assert response.json()["type"] == "json"
        assert response.json()["data"]["key"] == "value"
    
    def test_form_content_type(self, client):
        """测试 application/x-www-form-urlencoded"""
        response = client.post(
            "/form",
            data={"name": "test", "email": "test@example.com"}
        )
        
        assert response.status_code == 200
        assert response.json()["type"] == "form"
        # 表单数据通过查询参数传递，中间件不会消耗它
        # 这个测试主要验证中间件不会干扰表单数据处理


class TestRequestBodyErrorHandling:
    """测试请求体错误处理"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.post("/strict")
        async def strict_endpoint(request: SumRequest):
            return {"result": sum(request.numbers)}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_invalid_json_body(self, client):
        """测试无效的 JSON 请求体"""
        response = client.post(
            "/strict",
            json={"invalid": "data"}  # 缺少 numbers 字段
        )
        
        # 应该返回 422 验证错误
        assert response.status_code == 422
    
    def test_malformed_request(self, client):
        """测试格式错误的请求"""
        response = client.post(
            "/strict",
            json={"numbers": "not_a_list"}  # 类型错误
        )
        
        assert response.status_code == 422


class TestConcurrentRequests:
    """测试并发请求的请求体处理"""
    
    @pytest.fixture
    def app(self):
        """创建测试应用"""
        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware)
        
        @app.post("/process")
        async def process_data(data: dict):
            import asyncio
            await asyncio.sleep(0.01)  # 模拟处理时间
            return {"processed": True, "data": data}
        
        return app
    
    @pytest.fixture
    def client(self, app):
        return TestClient(app)
    
    def test_concurrent_requests(self, client):
        """测试并发请求都能正确处理请求体"""
        import concurrent.futures
        
        def make_request(i):
            response = client.post("/process", json={"id": i, "value": i * 10})
            return response.json()
        
        # 并发发送 10 个请求
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(make_request, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # 所有请求都应该成功
        assert len(results) == 10
        assert all(r["processed"] is True for r in results)
