"""scan_controllers 自动扫描测试

测试覆盖：
- 扫描指定包下的所有 ResourceController 子类
- 自动 include_router 到 app
- prefix 正确拼接
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.controller import scan_controllers


class TestScanControllers:
    """验证 scan_controllers 自动发现并挂载控制器"""

    def test_scan_package(self):
        """扫描测试 fixtures 包下的控制器"""
        app = FastAPI()
        scan_controllers(
            app,
            package="tests.test_controller._fixtures",
            prefix="/api",
        )
        client = TestClient(app)

        resp = client.get("/api/sample/list")
        assert resp.status_code == 200
        assert resp.json() == {"items": []}

        resp = client.post("/api/sample/create")
        assert resp.status_code == 200
        assert resp.json() == {"created": True}
