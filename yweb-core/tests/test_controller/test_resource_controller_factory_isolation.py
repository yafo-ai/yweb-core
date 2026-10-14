from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.controller import ResourceController, get
from yweb.acl.api import create_acl_router
from yweb.scheduler.api.job_api import create_job_router


class FakeScheduler:
    def __init__(self, code: str):
        self.code = code

    def get_jobs(self):
        return [{
            "code": self.code,
            "name": self.code,
            "run_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "is_paused": False,
        }]

    def get_job(self, code):
        return None

    def run_job(self, code):
        return None

    def pause_job(self, code):
        return False

    def resume_job(self, code):
        return False

    def remove_job(self, code):
        return False


class FakeAclService:
    def __init__(self, marker: str):
        self.marker = marker

    def get_resource_tree(self, resource_type=None):
        return [{"marker": self.marker, "resource_type": resource_type}]


def test_scheduler_router_factory_binds_independent_scheduler_instances():
    app = FastAPI()
    app.include_router(create_job_router(FakeScheduler("first")), prefix="/first")
    app.include_router(create_job_router(FakeScheduler("second")), prefix="/second")

    client = TestClient(app)

    first = client.get("/first/jobs/list").json()
    second = client.get("/second/jobs/list").json()

    assert first["data"][0]["code"] == "first"
    assert second["data"][0]["code"] == "second"


def test_acl_router_factory_binds_independent_service_instances():
    app = FastAPI()
    app.include_router(create_acl_router(FakeAclService("first")), prefix="/first")
    app.include_router(create_acl_router(FakeAclService("second")), prefix="/second")

    client = TestClient(app)

    first = client.get("/first/resources/tree").json()
    second = client.get("/second/resources/tree").json()

    assert first["data"][0]["marker"] == "first"
    assert second["data"][0]["marker"] == "second"


def test_resource_controller_create_router_binds_runtime_attrs_independently():
    class MarkerController(ResourceController):
        prefix = "/marker"
        marker = ""

        @get
        def value(self):
            return {"marker": self.marker}

    app = FastAPI()
    app.include_router(MarkerController.create_router(marker="first"), prefix="/first")
    app.include_router(MarkerController.create_router(marker="second"), prefix="/second")

    client = TestClient(app)

    assert client.get("/first/marker/value").json() == {"marker": "first"}
    assert client.get("/second/marker/value").json() == {"marker": "second"}
