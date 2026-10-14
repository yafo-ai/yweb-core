"""测试用控制器 — 供 scan_controllers 测试使用"""

from yweb.controller import ResourceController, get


class SampleController(ResourceController):
    prefix = "/sample"

    @get
    async def list(self):
        return {"items": []}

    async def create(self):
        return {"created": True}
