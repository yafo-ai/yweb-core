"""ResourceController 单元测试

测试覆盖：
- 基础路由生成（方法名 → 路径映射）
- @get 装饰器（标记的方法注册为 GET）
- 下划线方法过滤（_helper 不注册）
- OpenAPI schema 正确性（请求体/参数展示）
- 类级 dependencies（Router 级依赖生效）
- 方法级 Depends（FastAPI 原生 DI 正常工作）
- 多控制器组合（模块路由嵌套）
- prefix 为空字符串的场景
"""

import pytest
from fastapi import FastAPI, Depends, Query
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yweb.controller import ResourceController, get


# ==================== 测试用 Schema ====================

class CreateItemRequest(BaseModel):
    name: str
    value: int = 0


class UpdateItemRequest(BaseModel):
    id: int
    name: str


# ==================== 基础路由生成测试 ====================

class TestBasicRouteGeneration:
    """验证方法名正确映射为路由路径，HTTP 方法正确分配"""

    def setup_method(self):
        class ItemController(ResourceController):
            prefix = "/item"
            tags = ["测试"]

            @get
            async def list(self, page: int = 1):
                """获取列表"""
                return {"items": [], "page": page}

            @get
            async def detail(self, item_id: int = Query(...)):
                """获取详情"""
                return {"id": item_id}

            async def create(self, body: CreateItemRequest):
                """创建项目"""
                return {"name": body.name, "value": body.value}

            async def update(self, body: UpdateItemRequest):
                """更新项目"""
                return {"id": body.id, "name": body.name}

            async def delete(self, item_id: int = Query(...)):
                """删除项目"""
                return {"deleted": item_id}

        self.app = FastAPI()
        self.app.include_router(ItemController.router, prefix="/api/v1")
        self.client = TestClient(self.app)

    def test_get_methods_registered_as_get(self):
        """@get 标记的方法注册为 GET"""
        resp = self.client.get("/api/v1/item/list", params={"page": 2})
        assert resp.status_code == 200
        assert resp.json() == {"items": [], "page": 2}

    def test_get_method_with_query_param(self):
        """GET 方法支持 Query 参数"""
        resp = self.client.get("/api/v1/item/detail", params={"item_id": 42})
        assert resp.status_code == 200
        assert resp.json() == {"id": 42}

    def test_post_methods_registered_as_post(self):
        """未标记的方法默认注册为 POST"""
        resp = self.client.post(
            "/api/v1/item/create",
            json={"name": "test", "value": 10},
        )
        assert resp.status_code == 200
        assert resp.json() == {"name": "test", "value": 10}

    def test_post_method_with_body(self):
        """POST 方法正确接收请求体"""
        resp = self.client.post(
            "/api/v1/item/update",
            json={"id": 1, "name": "updated"},
        )
        assert resp.status_code == 200
        assert resp.json() == {"id": 1, "name": "updated"}

    def test_post_method_with_query(self):
        """POST 方法也可以有 Query 参数"""
        resp = self.client.post(
            "/api/v1/item/delete",
            params={"item_id": 99},
        )
        assert resp.status_code == 200
        assert resp.json() == {"deleted": 99}

    def test_get_on_post_endpoint_returns_405(self):
        """GET 请求 POST 端点返回 405"""
        resp = self.client.get("/api/v1/item/create")
        assert resp.status_code == 405

    def test_post_on_get_endpoint_returns_405(self):
        """POST 请求 GET 端点返回 405"""
        resp = self.client.post("/api/v1/item/list")
        assert resp.status_code == 405


# ==================== 下划线方法过滤测试 ====================

class TestUnderscoreFiltering:
    """验证下划线开头的方法不注册为路由"""

    def setup_method(self):
        class HelperController(ResourceController):
            prefix = "/helper"

            async def public_action(self):
                return {"ok": True}

            def _private_helper(self):
                return "should not be a route"

            async def _async_private(self):
                return "also not a route"

        self.app = FastAPI()
        self.app.include_router(HelperController.router)
        self.client = TestClient(self.app)

    def test_public_method_is_registered(self):
        """非下划线方法注册为路由"""
        resp = self.client.post("/helper/public_action")
        assert resp.status_code == 200

    def test_private_method_not_registered(self):
        """下划线方法不注册为路由"""
        resp = self.client.post("/helper/_private_helper")
        assert resp.status_code in (404, 405)

    def test_async_private_not_registered(self):
        """异步下划线方法也不注册"""
        resp = self.client.post("/helper/_async_private")
        assert resp.status_code in (404, 405)


# ==================== OpenAPI Schema 测试 ====================

class TestOpenAPISchema:
    """验证 Swagger/OpenAPI 文档正确生成"""

    def setup_method(self):
        class SchemaController(ResourceController):
            prefix = "/schema"
            tags = ["Schema测试"]

            @get
            async def list(self, page: int = 1, size: int = 10):
                """获取分页列表"""
                return []

            async def create(self, body: CreateItemRequest):
                """创建新项目"""
                return body.model_dump()

        self.app = FastAPI()
        self.app.include_router(SchemaController.router, prefix="/api")
        self.client = TestClient(self.app)

    def test_openapi_schema_generated(self):
        """OpenAPI schema 可正常生成"""
        resp = self.client.get("/openapi.json")
        assert resp.status_code == 200
        schema = resp.json()
        assert "paths" in schema

    def test_get_endpoint_has_query_params(self):
        """GET 端点的查询参数在 schema 中展示"""
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/api/schema/list"]
        assert "get" in path
        params = path["get"]["parameters"]
        param_names = {p["name"] for p in params}
        assert "page" in param_names
        assert "size" in param_names

    def test_post_endpoint_has_request_body(self):
        """POST 端点的请求体在 schema 中展示"""
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/api/schema/create"]
        assert "post" in path
        assert "requestBody" in path["post"]

    def test_tags_applied(self):
        """tags 正确应用到路由"""
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/api/schema/list"]
        assert "Schema测试" in path["get"]["tags"]

    def test_summary_from_docstring(self):
        """docstring 第一行作为 summary"""
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/api/schema/create"]
        assert path["post"]["summary"] == "创建新项目"

    def test_self_not_in_params(self):
        """self 参数不出现在 OpenAPI schema 中"""
        resp = self.client.get("/openapi.json")
        schema = resp.json()
        path = schema["paths"]["/api/schema/list"]
        params = path["get"]["parameters"]
        param_names = {p["name"] for p in params}
        assert "self" not in param_names


# ==================== 依赖注入测试 ====================

class TestDependencyInjection:
    """验证类级 dependencies 和方法级 Depends 正常工作"""

    def setup_method(self):
        auth_called = []

        async def mock_auth():
            auth_called.append(True)
            return {"user_id": 1}

        class ProtectedController(ResourceController):
            prefix = "/protected"
            dependencies = [mock_auth]

            @get
            async def info(self):
                return {"status": "ok"}

            async def action(self):
                return {"done": True}

        class MixedController(ResourceController):
            prefix = "/mixed"

            @get
            async def public(self):
                return {"public": True}

            async def private(self, user=Depends(mock_auth)):
                return {"user": user}

        self.app = FastAPI()
        self.app.include_router(ProtectedController.router)
        self.app.include_router(MixedController.router)
        self.client = TestClient(self.app)
        self.auth_called = auth_called

    def test_class_level_dependency_called_on_get(self):
        """类级 dependencies 在 GET 请求时执行"""
        resp = self.client.get("/protected/info")
        assert resp.status_code == 200
        assert len(self.auth_called) > 0

    def test_class_level_dependency_called_on_post(self):
        """类级 dependencies 在 POST 请求时执行"""
        self.auth_called.clear()
        resp = self.client.post("/protected/action")
        assert resp.status_code == 200
        assert len(self.auth_called) > 0

    def test_method_level_depends(self):
        """方法级 Depends 正常注入"""
        resp = self.client.post("/mixed/private")
        assert resp.status_code == 200
        assert resp.json() == {"user": {"user_id": 1}}

    def test_no_dependency_on_public(self):
        """无 dependencies 的控制器方法正常访问"""
        resp = self.client.get("/mixed/public")
        assert resp.status_code == 200
        assert resp.json() == {"public": True}


# ==================== 多控制器组合测试 ====================

class TestMultipleControllers:
    """验证多控制器通过模块路由嵌套组合"""

    def setup_method(self):
        from fastapi import APIRouter

        class TemplateController(ResourceController):
            prefix = "/template"

            async def create(self):
                return {"resource": "template"}

            async def publish(self):
                return {"action": "publish"}

        class NodeController(ResourceController):
            prefix = "/template/node"

            async def create(self):
                return {"resource": "node"}

        workflow_router = APIRouter(prefix="/workflow")
        workflow_router.include_router(TemplateController.router)
        workflow_router.include_router(NodeController.router)

        self.app = FastAPI()
        self.app.include_router(workflow_router, prefix="/api/v1")
        self.client = TestClient(self.app)

    def test_first_controller_routes(self):
        """第一个控制器路由正确"""
        resp = self.client.post("/api/v1/workflow/template/create")
        assert resp.status_code == 200
        assert resp.json() == {"resource": "template"}

    def test_second_action_on_first_controller(self):
        """第一个控制器的第二个方法"""
        resp = self.client.post("/api/v1/workflow/template/publish")
        assert resp.status_code == 200
        assert resp.json() == {"action": "publish"}

    def test_nested_controller_routes(self):
        """嵌套资源控制器路由正确"""
        resp = self.client.post("/api/v1/workflow/template/node/create")
        assert resp.status_code == 200
        assert resp.json() == {"resource": "node"}


# ==================== 空 prefix 测试 ====================

class TestEmptyPrefix:
    """验证 prefix 为空字符串时路由正确"""

    def setup_method(self):
        class RootController(ResourceController):
            prefix = ""

            @get
            async def status(self):
                return {"up": True}

            async def action(self):
                return {"done": True}

        module_router = FastAPI().router
        self.app = FastAPI()
        self.app.include_router(RootController.router, prefix="/api/v1/connector")
        self.client = TestClient(self.app)

    def test_empty_prefix_get(self):
        """空 prefix 下 GET 路由直接挂载"""
        resp = self.client.get("/api/v1/connector/status")
        assert resp.status_code == 200
        assert resp.json() == {"up": True}

    def test_empty_prefix_post(self):
        """空 prefix 下 POST 路由直接挂载"""
        resp = self.client.post("/api/v1/connector/action")
        assert resp.status_code == 200
        assert resp.json() == {"done": True}


# ==================== 同步方法支持测试 ====================

class TestSyncMethods:
    """验证同步方法（非 async）也能正常工作"""

    def setup_method(self):
        class SyncController(ResourceController):
            prefix = "/sync"

            @get
            def info(self):
                """同步 GET"""
                return {"sync": True}

            def action(self, body: CreateItemRequest):
                """同步 POST"""
                return {"name": body.name}

        self.app = FastAPI()
        self.app.include_router(SyncController.router)
        self.client = TestClient(self.app)

    def test_sync_get(self):
        """同步 GET 方法正常工作"""
        resp = self.client.get("/sync/info")
        assert resp.status_code == 200
        assert resp.json() == {"sync": True}

    def test_sync_post(self):
        """同步 POST 方法正常工作"""
        resp = self.client.post("/sync/action", json={"name": "hello"})
        assert resp.status_code == 200
        assert resp.json() == {"name": "hello"}
