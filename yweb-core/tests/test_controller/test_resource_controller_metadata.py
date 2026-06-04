"""ResourceController 路由元数据增强测试

覆盖 @get/@post/@route 对以下能力的支持：
- response_model（OpenAPI 文档体现）
- status_code（自定义响应状态码）
- 方法级 dependencies（可调用对象自动包装 Depends，或直接传 Depends 实例）
- @post 裸用 / 带参数用法
- @route 通用装饰器
"""

from typing import List

from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from pydantic import BaseModel

from yweb.controller import ResourceController, get, post, route


class ItemOut(BaseModel):
    id: int
    name: str


class ItemListOut(BaseModel):
    items: List[ItemOut]
    total: int


class CreateItem(BaseModel):
    name: str


class TestResponseModel:
    def setup_method(self):
        class C(ResourceController):
            prefix = "/c"

            @get(response_model=ItemListOut)
            async def list(self):
                return {"items": [{"id": 1, "name": "a"}], "total": 1}

            @post(response_model=ItemOut, status_code=201)
            async def create(self, body: CreateItem):
                return {"id": 1, "name": body.name}

        self.app = FastAPI()
        self.app.include_router(C.router, prefix="/api")
        self.client = TestClient(self.app)

    def test_get_response_model_in_openapi(self):
        schema = self.client.get("/openapi.json").json()
        op = schema["paths"]["/api/c/list"]["get"]
        ref = op["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ItemListOut")

    def test_post_response_model_and_status_code_in_openapi(self):
        schema = self.client.get("/openapi.json").json()
        op = schema["paths"]["/api/c/create"]["post"]
        # 自定义 status_code=201 -> 文档里成功响应在 201
        assert "201" in op["responses"]
        ref = op["responses"]["201"]["content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ItemOut")

    def test_status_code_applied_at_runtime(self):
        resp = self.client.post("/api/c/create", json={"name": "x"})
        assert resp.status_code == 201
        assert resp.json() == {"id": 1, "name": "x"}

    def test_get_runtime_ok(self):
        resp = self.client.get("/api/c/list")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1


class TestMethodLevelDependencies:
    def setup_method(self):
        calls = {"dep": 0}

        def dep_callable():
            calls["dep"] += 1
            return {"user": "u1"}

        forbidden = {"flag": False}

        def maybe_forbid():
            if forbidden["flag"]:
                from fastapi import HTTPException
                raise HTTPException(status_code=403, detail="no")

        class C(ResourceController):
            prefix = "/c"

            # 可调用对象，自动包装为 Depends
            @post(dependencies=[dep_callable])
            async def action(self):
                return {"ok": True}

            # 直接传 Depends 实例
            @get(dependencies=[Depends(maybe_forbid)])
            async def info(self):
                return {"info": True}

        self.app = FastAPI()
        self.app.include_router(C.router)
        self.client = TestClient(self.app)
        self.calls = calls
        self.forbidden = forbidden

    def test_callable_dependency_wrapped_and_invoked(self):
        resp = self.client.post("/c/action")
        assert resp.status_code == 200
        assert self.calls["dep"] == 1

    def test_depends_instance_dependency(self):
        assert self.client.get("/c/info").status_code == 200
        self.forbidden["flag"] = True
        assert self.client.get("/c/info").status_code == 403


class TestPostAndRouteDecorators:
    def setup_method(self):
        class C(ResourceController):
            prefix = "/c"

            @post
            async def bare_post(self):
                return {"m": "post"}

            @route("GET", response_model=ItemOut)
            async def via_route(self):
                return {"id": 9, "name": "r"}

        self.app = FastAPI()
        self.app.include_router(C.router)
        self.client = TestClient(self.app)

    def test_bare_post(self):
        assert self.client.post("/c/bare_post").status_code == 200
        assert self.client.get("/c/bare_post").status_code == 405

    def test_route_get(self):
        resp = self.client.get("/c/via_route")
        assert resp.status_code == 200
        assert resp.json() == {"id": 9, "name": "r"}


class TestPathOverride:
    """path= 覆盖默认的 /方法名 路径（如连字符路径）。"""

    def setup_method(self):
        class C(ResourceController):
            prefix = "/c"

            @post(path="/reset-password")
            async def reset_password(self):
                return {"ok": True}

            @get(path="/items/active", response_model=ItemOut)
            async def active_items(self):
                return {"id": 1, "name": "a"}

        self.app = FastAPI()
        self.app.include_router(C.router)
        self.client = TestClient(self.app)

    def test_post_hyphen_path(self):
        assert self.client.post("/c/reset-password").json() == {"ok": True}
        # 默认的 /方法名 路径不应存在
        assert self.client.post("/c/reset_password").status_code == 404

    def test_get_custom_path_and_openapi(self):
        assert self.client.get("/c/items/active").json() == {"id": 1, "name": "a"}
        schema = self.client.get("/openapi.json").json()
        assert "/c/items/active" in schema["paths"]
        ref = schema["paths"]["/c/items/active"]["get"]["responses"]["200"][
            "content"
        ]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/ItemOut")
