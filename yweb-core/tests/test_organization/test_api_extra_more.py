"""组织模块 API 补充分支测试（新文件）"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import scoped_session, sessionmaker

from yweb.orm import BaseModel, CoreModel, Page
from yweb.organization.api import create_org_router
from yweb.organization.api.department_api import create_department_crud_router
from yweb.organization.api.employee_api import create_employee_crud_router

from tests.test_organization.test_api import (
    SampleOrganization,
    SampleDepartment,
    SampleEmployee,
    SampleEmployeeOrgRel,
    SampleEmployeeDeptRel,
    SampleDeptLeader,
    SampleOrgService,
)


class QueryEmptyStub:
    def __init__(self):
        self._rows = []

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def filter_by(self, **kwargs):
        _ = kwargs
        return self

    def order_by(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return None

    def paginate(self, page=1, page_size=20):
        return Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)


class TestOrganizationApiExtraMore:
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        BaseModel.metadata.create_all(bind=memory_engine)
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(session_local)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()

    def test_create_org_router_mounts_child_routers(self):
        app = FastAPI()
        router = create_org_router(
            org_model=SampleOrganization,
            dept_model=SampleDepartment,
            employee_model=SampleEmployee,
            emp_org_rel_model=SampleEmployeeOrgRel,
            emp_dept_rel_model=SampleEmployeeDeptRel,
            dept_leader_model=SampleDeptLeader,
            org_service=SampleOrgService(),
            prefix="/orgx",
        )
        app.include_router(router, prefix="/api")
        client = TestClient(app)
        assert client.get("/api/orgx/list").status_code in (200, 422)
        assert client.get("/api/orgx/dept/tree?org_id=1").status_code in (200, 404)
        assert client.get("/api/orgx/employee/list").status_code == 200

    def test_department_router_optional_routes_absent_without_models(self):
        app = FastAPI()
        router = create_department_crud_router(
            dept_model=SampleDepartment,
            org_model=SampleOrganization,
            employee_model=None,
            emp_org_rel_model=None,
            emp_dept_rel_model=None,
            dept_leader_model=None,
            org_service=SampleOrgService(),
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)
        assert client.get("/dept/employees?dept_id=1").status_code == 404
        assert client.post("/dept/add-leader", json={"dept_id": 1, "employee_id": 1}).status_code == 404
        assert client.post("/dept/remove-leader?dept_id=1&employee_id=1").status_code == 404

    def test_department_get_tree_and_get_detail_not_found(self):
        app = FastAPI()
        router = create_department_crud_router(
            dept_model=SampleDepartment,
            org_model=SampleOrganization,
            org_service=SampleOrgService(),
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)

        tree_resp = client.get("/dept/tree?org_id=999999")
        assert tree_resp.status_code == 404
        assert tree_resp.json()["status"] == "error"

        get_resp = client.get("/dept/get?dept_id=999999")
        assert get_resp.status_code == 404
        assert get_resp.json()["status"] == "error"

    def test_department_write_endpoints_bad_request(self, monkeypatch):
        svc = SampleOrgService()

        def raise_value_error(*args, **kwargs):
            _ = (args, kwargs)
            raise ValueError("bad request from service")

        monkeypatch.setattr(svc, "create_dept", raise_value_error)
        monkeypatch.setattr(svc, "update_dept", raise_value_error)
        monkeypatch.setattr(svc, "move_dept", raise_value_error)
        monkeypatch.setattr(svc, "delete_dept", raise_value_error)

        app = FastAPI()
        router = create_department_crud_router(
            dept_model=SampleDepartment,
            org_model=SampleOrganization,
            org_service=svc,
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)

        assert client.post("/dept/create", json={"org_id": 1, "name": "A"}).status_code == 400
        assert client.post("/dept/update?dept_id=1", json={"name": "B"}).status_code == 400
        assert client.post("/dept/move?dept_id=1&new_parent_id=2").status_code == 400
        assert client.post("/dept/delete?dept_id=1&force=true").status_code == 400

    def test_department_employees_empty_page_branch(self, monkeypatch):
        svc = SampleOrgService()
        app = FastAPI()
        router = create_department_crud_router(
            dept_model=SampleDepartment,
            org_model=SampleOrganization,
            employee_model=SampleEmployee,
            emp_org_rel_model=SampleEmployeeOrgRel,
            emp_dept_rel_model=SampleEmployeeDeptRel,
            dept_leader_model=SampleDeptLeader,
            org_service=svc,
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)

        # 创建组织和部门，确保部门存在
        org = SampleOrganization(name="O", code="O1")
        org.add(commit=True)
        dept = SampleDepartment(org_id=org.id, name="D")
        dept.add(commit=True)
        dept.update_path_and_level()
        dept.save(commit=True)

        # 强制部门关联查询为空，命中空分页分支
        monkeypatch.setattr(SampleEmployeeDeptRel, "query", QueryEmptyStub())
        resp = client.get(f"/dept/employees?dept_id={dept.id}&page=1&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["total_records"] == 0

    def test_employee_router_response_builder_and_bad_requests(self, monkeypatch):
        svc = SampleOrgService()

        def builder(emp, base_data):
            base_data["display_name"] = f"{base_data.get('name', '')}-X"
            return base_data

        app = FastAPI()
        router = create_employee_crud_router(
            employee_model=SampleEmployee,
            org_model=SampleOrganization,
            dept_model=SampleDepartment,
            emp_org_rel_model=SampleEmployeeOrgRel,
            emp_dept_rel_model=SampleEmployeeDeptRel,
            dept_leader_model=SampleDeptLeader,
            org_service=svc,
            response_builder=builder,
        )
        app.include_router(router, prefix="/emp")
        client = TestClient(app)

        # list 命中 response_builder 分支
        created = client.post("/emp/create", json={"name": "U1", "mobile": "13800138000"})
        assert created.status_code == 200
        list_resp = client.get("/emp/list")
        assert list_resp.status_code == 200
        rows = list_resp.json()["data"]["rows"]
        assert rows and "display_name" in rows[0]

        # 写接口 ValueError -> 400
        def raise_value_error(*args, **kwargs):
            _ = (args, kwargs)
            raise ValueError("x")

        monkeypatch.setattr(svc, "update_employee", raise_value_error)
        monkeypatch.setattr(svc, "delete_employee", raise_value_error)
        monkeypatch.setattr(svc, "add_employee_to_org", raise_value_error)
        monkeypatch.setattr(svc, "remove_employee_from_org", raise_value_error)
        monkeypatch.setattr(svc, "set_primary_org", raise_value_error)
        monkeypatch.setattr(svc, "add_employee_to_dept", raise_value_error)
        monkeypatch.setattr(svc, "remove_employee_from_dept", raise_value_error)
        monkeypatch.setattr(svc, "set_primary_dept", raise_value_error)
        monkeypatch.setattr(svc, "update_emp_org_status", raise_value_error)
        monkeypatch.setattr(svc, "update_account_status", raise_value_error)

        assert client.post("/emp/update?employee_id=1", json={"name": "x"}).status_code == 400
        assert client.post("/emp/delete?employee_id=1").status_code == 400
        assert client.post("/emp/add-to-org", json={"employee_id": 1, "org_id": 1}).status_code == 400
        assert client.post("/emp/remove-from-org?employee_id=1&org_id=1").status_code == 400
        assert client.post("/emp/set-primary-org?employee_id=1&org_id=1").status_code == 400
        assert client.post("/emp/add-to-dept", json={"employee_id": 1, "dept_id": 1}).status_code == 400
        assert client.post("/emp/remove-from-dept?employee_id=1&dept_id=1").status_code == 400
        assert client.post("/emp/set-primary-dept?employee_id=1&dept_id=1").status_code == 400
        assert client.post("/emp/update-org-status?employee_id=1&org_id=1&status=3").status_code == 400
        assert client.post("/emp/update-account-status?employee_id=1&account_status=1").status_code == 400
