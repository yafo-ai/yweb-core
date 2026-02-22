"""
缓存模块 - 通用缓存管理 API 测试

测试 create_cache_router 提供的缓存管理端点，包括：
1. 列出所有缓存函数
2. 获取缓存统计（汇总/单函数）
3. 清空缓存（全部/单函数）
4. 查看自动失效注册
5. 切换自动失效开关
"""

import pytest
from typing import Optional
from dataclasses import dataclass

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.cache import (
    cached,
    cache_registry,
    cache_invalidator,
    create_cache_router,
    CacheRegistry,
)


# ==================== 辅助类定义 ====================
# 注意：类名不以 Test 开头，避免 pytest 误认为是测试类

@dataclass
class SampleUser:
    """模拟用户实体"""
    id: int
    name: str


# 模拟数据库
_fake_db = {
    1: SampleUser(id=1, name="Alice"),
    2: SampleUser(id=2, name="Bob"),
    3: SampleUser(id=3, name="Charlie"),
}


# ==================== 测试类 ====================


class TestCacheRegistryUnit:
    """测试 CacheRegistry 注册表（单元测试）"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前创建独立的注册表，测试后清理"""
        self.registry = CacheRegistry()
        yield
    
    def test_register_and_list(self):
        """测试注册缓存函数后可以列出"""
        @cached(ttl=60)
        def sample_func(key: str):
            return key
        
        self.registry.register(sample_func)
        
        functions = self.registry.list_functions()
        assert len(functions) == 1
        assert functions[0]["name"] == "sample_func"
        assert functions[0]["ttl"] == 60
        assert functions[0]["backend"] == "memory"
    
    def test_get_function(self):
        """测试获取指定缓存函数"""
        @cached(ttl=120)
        def another_func(x: int):
            return x * 2
        
        self.registry.register(another_func)
        
        func = self.registry.get("another_func")
        assert func is not None
        assert func.__name__ == "another_func"
        
        # 不存在的函数返回 None
        assert self.registry.get("nonexistent") is None
    
    def test_unregister(self):
        """测试取消注册"""
        @cached(ttl=60)
        def temp_func(key: str):
            return key
        
        self.registry.register(temp_func)
        assert self.registry.size == 1
        
        result = self.registry.unregister("temp_func")
        assert result is True
        assert self.registry.size == 0
        
        # 取消不存在的函数返回 False
        assert self.registry.unregister("nonexistent") is False
    
    def test_get_all_stats(self):
        """测试汇总统计"""
        @cached(ttl=60)
        def stats_func_a(key: str):
            return _fake_db.get(int(key))
        
        @cached(ttl=120)
        def stats_func_b(key: str):
            return key
        
        self.registry.register(stats_func_a)
        self.registry.register(stats_func_b)
        
        # 产生一些缓存命中/未命中
        stats_func_a("1")  # miss
        stats_func_a("1")  # hit
        stats_func_b("x")  # miss
        
        all_stats = self.registry.get_all_stats()
        assert all_stats["total_functions"] == 2
        assert all_stats["total_hits"] == 1
        assert all_stats["total_misses"] == 2
        assert "functions" in all_stats
    
    def test_clear_function(self):
        """测试清空指定函数的缓存"""
        call_count = 0
        
        @cached(ttl=60)
        def clearable_func(key: str):
            nonlocal call_count
            call_count += 1
            return key
        
        self.registry.register(clearable_func)
        
        clearable_func("a")
        clearable_func("a")  # hit
        assert call_count == 1
        
        result = self.registry.clear_function("clearable_func")
        assert result is True
        
        clearable_func("a")  # miss after clear
        assert call_count == 2
        
        # 清空不存在的函数返回 False
        assert self.registry.clear_function("nonexistent") is False
    
    def test_clear_all(self):
        """测试清空所有缓存"""
        count_a = 0
        count_b = 0
        
        @cached(ttl=60)
        def func_clear_a(key: str):
            nonlocal count_a
            count_a += 1
            return key
        
        @cached(ttl=60)
        def func_clear_b(key: str):
            nonlocal count_b
            count_b += 1
            return key
        
        self.registry.register(func_clear_a)
        self.registry.register(func_clear_b)
        
        func_clear_a("x")
        func_clear_b("y")
        assert count_a == 1
        assert count_b == 1
        
        cleared = self.registry.clear_all()
        assert cleared == 2
        
        func_clear_a("x")
        func_clear_b("y")
        assert count_a == 2
        assert count_b == 2
    
    def test_size_property(self):
        """测试 size 属性"""
        assert self.registry.size == 0
        
        @cached(ttl=60)
        def sized_func(x: int):
            return x
        
        self.registry.register(sized_func)
        assert self.registry.size == 1


class TestCacheAPIEndpoints:
    """测试缓存管理 HTTP API 端点"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前清理全局注册表，测试后恢复"""
        # 保存原有注册
        original_functions = dict(cache_registry._functions)
        cache_registry._functions.clear()
        
        # 确保 invalidator 是启用状态
        cache_invalidator.enable()
        
        yield
        
        # 恢复原有注册
        cache_registry._functions.clear()
        cache_registry._functions.update(original_functions)
    
    @pytest.fixture
    def cache_app(self):
        """创建包含缓存管理 API 的测试应用"""
        app = FastAPI()
        router = create_cache_router()
        app.include_router(router, prefix="/api/cache")
        return app
    
    @pytest.fixture
    def cache_client(self, cache_app):
        """缓存 API 测试客户端"""
        return TestClient(cache_app)

    def test_openapi_response_schema_is_not_string(self, cache_app):
        """测试 OpenAPI 成功响应已声明 response_model（非 string）"""
        openapi = cache_app.openapi()

        paths_to_check = [
            ("/api/cache/functions", "get"),
            ("/api/cache/stats", "get"),
            ("/api/cache/entries", "get"),
            ("/api/cache/entry", "get"),
            ("/api/cache/clear", "post"),
            ("/api/cache/invalidator/registrations", "get"),
            ("/api/cache/invalidator/toggle", "post"),
        ]

        for path, method in paths_to_check:
            schema = (
                openapi["paths"][path][method]["responses"]["200"]["content"]["application/json"]["schema"]
            )
            assert schema.get("type") != "string"
            assert "$ref" in schema or "allOf" in schema or "anyOf" in schema
    
    def _register_sample_functions(self):
        """注册示例缓存函数用于测试"""
        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[SampleUser]:
            return _fake_db.get(user_id)
        
        @cached(ttl=300)
        def get_config(key: str) -> str:
            return f"value_{key}"
        
        return get_user, get_config
    
    # ---------- GET /functions ----------
    
    def test_list_functions_empty(self, cache_client):
        """测试列出缓存函数（无注册）"""
        response = cache_client.get("/api/cache/functions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["total"] == 0
        assert data["data"]["functions"] == []
    
    def test_list_functions_with_registrations(self, cache_client):
        """测试列出缓存函数（有注册）"""
        self._register_sample_functions()
        
        response = cache_client.get("/api/cache/functions")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total"] == 2
        
        func_names = [f["name"] for f in data["data"]["functions"]]
        assert "get_user" in func_names
        assert "get_config" in func_names
        
        # 验证函数详情
        for func_info in data["data"]["functions"]:
            if func_info["name"] == "get_user":
                assert func_info["ttl"] == 60
                assert func_info["backend"] == "memory"
            elif func_info["name"] == "get_config":
                assert func_info["ttl"] == 300
    
    # ---------- GET /stats ----------
    
    def test_get_stats_all(self, cache_client):
        """测试获取汇总统计"""
        get_user, get_config = self._register_sample_functions()
        
        # 产生缓存数据
        get_user(1)   # miss
        get_user(1)   # hit
        get_config("a")  # miss
        
        response = cache_client.get("/api/cache/stats")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["total_functions"] == 2
        assert data["data"]["total_hits"] == 1
        assert data["data"]["total_misses"] == 2
        assert "functions" in data["data"]
    
    def test_get_stats_single_function(self, cache_client):
        """测试获取单个函数统计"""
        get_user, _ = self._register_sample_functions()
        
        get_user(1)
        get_user(1)
        get_user(2)
        
        response = cache_client.get("/api/cache/stats?function_name=get_user")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["hits"] == 1
        assert data["data"]["misses"] == 2
        assert data["data"]["function"] == "get_user"
    
    def test_get_stats_nonexistent_function(self, cache_client):
        """测试获取不存在函数的统计"""
        response = cache_client.get("/api/cache/stats?function_name=nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
    
    # ---------- GET /entries ----------
    
    def test_list_entries_for_function(self, cache_client):
        """测试查看指定函数缓存条目列表"""
        get_user, _ = self._register_sample_functions()
        get_user(1)
        get_user(2)
        
        response = cache_client.get("/api/cache/entries?function_name=get_user&limit=10")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["function"] == "get_user"
        assert data["data"]["total"] >= 2
        assert len(data["data"]["entries"]) >= 2
        assert "key" in data["data"]["entries"][0]
        assert "value_preview" in data["data"]["entries"][0]
    
    def test_list_entries_nonexistent_function(self, cache_client):
        """测试查看不存在函数的条目列表"""
        response = cache_client.get("/api/cache/entries?function_name=nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
    
    # ---------- GET /entry ----------
    
    def test_get_single_entry(self, cache_client):
        """测试查看单个缓存条目"""
        get_user, _ = self._register_sample_functions()
        get_user(1)
        
        key = get_user._build_key((1,), {})
        response = cache_client.get(f"/api/cache/entry?function_name=get_user&key={key}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["key"] == key
        assert data["data"]["value_type"] == "SampleUser"
    
    def test_get_single_entry_not_found(self, cache_client):
        """测试查看不存在的单个缓存条目"""
        self._register_sample_functions()
        
        response = cache_client.get("/api/cache/entry?function_name=get_user&key=missing:key")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
    
    # ---------- POST /clear ----------
    
    def test_clear_all_cache(self, cache_client):
        """测试清空所有缓存"""
        user_calls = 0
        config_calls = 0

        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[SampleUser]:
            nonlocal user_calls
            user_calls += 1
            return _fake_db.get(user_id)

        @cached(ttl=300)
        def get_config(key: str) -> str:
            nonlocal config_calls
            config_calls += 1
            return f"value_{key}"

        # 先命中缓存
        get_user(1)
        get_user(1)
        get_config("a")
        get_config("a")
        assert user_calls == 1
        assert config_calls == 1
        
        response = cache_client.post("/api/cache/clear")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["cleared_count"] == 2

        # 清空后再次调用应重新计算，证明不是“只返回成功”
        get_user(1)
        get_config("a")
        assert user_calls == 2
        assert config_calls == 2
    
    def test_clear_single_function_cache(self, cache_client):
        """测试清空指定函数的缓存"""
        user_calls = 0
        config_calls = 0

        @cached(ttl=60)
        def get_user(user_id: int) -> Optional[SampleUser]:
            nonlocal user_calls
            user_calls += 1
            return _fake_db.get(user_id)

        @cached(ttl=300)
        def get_config(key: str) -> str:
            nonlocal config_calls
            config_calls += 1
            return f"value_{key}"

        # 预热缓存
        get_user(1)
        get_user(1)
        get_config("a")
        get_config("a")
        assert user_calls == 1
        assert config_calls == 1
        
        response = cache_client.post("/api/cache/clear?function_name=get_user")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["function"] == "get_user"

        # get_user 缓存被清，get_config 缓存保留
        get_user(1)
        get_config("a")
        assert user_calls == 2
        assert config_calls == 1
    
    def test_clear_nonexistent_function(self, cache_client):
        """测试清空不存在函数的缓存"""
        response = cache_client.post("/api/cache/clear?function_name=nonexistent")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"
    
    # ---------- GET /invalidator/registrations ----------
    
    def test_get_invalidator_registrations_empty(self, cache_client):
        """测试查看自动失效注册（无注册）"""
        response = cache_client.get("/api/cache/invalidator/registrations")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["enabled"] is True
        assert isinstance(data["data"]["registrations"], dict)
    
    # ---------- POST /invalidator/toggle ----------
    
    def test_toggle_invalidator_disable(self, cache_client):
        """测试禁用自动失效"""
        response = cache_client.post("/api/cache/invalidator/toggle?enabled=false")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["enabled"] is False
        
        # 确认状态
        assert cache_invalidator.is_enabled is False
    
    def test_toggle_invalidator_enable(self, cache_client):
        """测试启用自动失效"""
        # 先禁用
        cache_invalidator.disable()
        
        response = cache_client.post("/api/cache/invalidator/toggle?enabled=true")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["enabled"] is True
        assert cache_invalidator.is_enabled is True


class TestCacheAPIIntegration:
    """缓存管理 API 集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup_registry(self):
        """每个测试前清理全局注册表"""
        original_functions = dict(cache_registry._functions)
        cache_registry._functions.clear()
        yield
        cache_registry._functions.clear()
        cache_registry._functions.update(original_functions)
    
    @pytest.fixture
    def cache_app(self):
        """创建测试应用"""
        app = FastAPI()
        router = create_cache_router()
        app.include_router(router, prefix="/api/cache")
        return app
    
    @pytest.fixture
    def cache_client(self, cache_app):
        """测试客户端"""
        return TestClient(cache_app)
    
    def test_cache_lifecycle(self, cache_client):
        """测试缓存完整生命周期：注册 -> 使用 -> 统计 -> 清空"""
        call_count = 0
        
        @cached(ttl=60)
        def get_item(item_id: int) -> str:
            nonlocal call_count
            call_count += 1
            return f"item_{item_id}"
        
        # 1. 确认注册成功
        response = cache_client.get("/api/cache/functions")
        assert response.json()["data"]["total"] == 1
        
        # 2. 使用缓存产生数据
        get_item(1)   # miss
        get_item(1)   # hit
        get_item(2)   # miss
        get_item(2)   # hit
        get_item(2)   # hit
        assert call_count == 2
        
        # 3. 查看统计
        response = cache_client.get("/api/cache/stats?function_name=get_item")
        stats = response.json()["data"]
        assert stats["hits"] == 3
        assert stats["misses"] == 2
        
        # 4. 清空缓存
        response = cache_client.post("/api/cache/clear?function_name=get_item")
        assert response.json()["status"] == "success"
        
        # 5. 清空后再次调用应重新查询
        get_item(1)
        assert call_count == 3
    
    def test_multiple_functions_management(self, cache_client):
        """测试多函数管理场景"""
        @cached(ttl=60)
        def func_alpha(x: int) -> int:
            return x * 2
        
        @cached(ttl=120)
        def func_beta(x: int) -> int:
            return x * 3
        
        # 使用
        func_alpha(1)
        func_beta(1)
        
        # 列出所有
        response = cache_client.get("/api/cache/functions")
        assert response.json()["data"]["total"] == 2
        
        # 只清空 alpha
        cache_client.post("/api/cache/clear?function_name=func_alpha")
        
        # 验证 beta 的统计不受影响
        response = cache_client.get("/api/cache/stats?function_name=func_beta")
        assert response.json()["data"]["misses"] == 1
    
    def test_entry_preview_masks_sensitive_fields(self, cache_client):
        """测试条目预览会脱敏敏感字段"""
        @cached(ttl=60)
        def get_secret_payload(user_id: int):
            return {
                "user_id": user_id,
                "password": "plain-text-password",
                "access_token": "very-secret-token",
                "profile": {"nickname": "alice"},
            }
        
        get_secret_payload(1)
        key = get_secret_payload._build_key((1,), {})
        
        response = cache_client.get(
            f"/api/cache/entry?function_name=get_secret_payload&key={key}"
        )
        assert response.status_code == 200
        preview = response.json()["data"]["value_preview"]
        assert preview["password"] == "***"
        assert preview["access_token"] == "***"
        assert preview["profile"]["nickname"] == "alice"
