"""组织模块 API 补充分支测试（新文件）"""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import scoped_session, sessionmaker

from yweb.orm import BaseModel, CoreModel, Page
from yweb.organization.api import create_org_router
from yweb.organization.api.organization_api import create_organization_crud_router
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


class TestOrganizationApiFieldRoundtrip:
    """测试新增请求字段的创建与更新回传"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(session_local)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()

    @pytest.fixture
    def org_service(self):
        """创建测试用组织服务"""
        return SampleOrgService()

    @pytest.fixture
    def org_client(self, org_service):
        """组织 API 测试客户端"""
        app = FastAPI()
        router = create_organization_crud_router(
            org_model=SampleOrganization,
            org_service=org_service,
        )
        app.include_router(router, prefix="/org")
        return TestClient(app)

    @pytest.fixture
    def dept_client(self, org_service):
        """部门 API 测试客户端"""
        app = FastAPI()
        app.include_router(
            create_organization_crud_router(
                org_model=SampleOrganization,
                org_service=org_service,
            ),
            prefix="/org",
        )
        app.include_router(
            create_department_crud_router(
                dept_model=SampleDepartment,
                org_model=SampleOrganization,
                employee_model=SampleEmployee,
                emp_org_rel_model=SampleEmployeeOrgRel,
                emp_dept_rel_model=SampleEmployeeDeptRel,
                dept_leader_model=SampleDeptLeader,
                org_service=org_service,
            ),
            prefix="/dept",
        )
        return TestClient(app)

    @pytest.fixture
    def emp_client(self, org_service):
        """员工 API 测试客户端"""
        app = FastAPI()
        app.include_router(
            create_employee_crud_router(
                employee_model=SampleEmployee,
                org_model=SampleOrganization,
                dept_model=SampleDepartment,
                emp_org_rel_model=SampleEmployeeOrgRel,
                emp_dept_rel_model=SampleEmployeeDeptRel,
                dept_leader_model=SampleDeptLeader,
                org_service=org_service,
            ),
            prefix="/emp",
        )
        return TestClient(app)

    def test_organization_create_and_update_accept_new_fields(self, org_client):
        """测试组织创建和更新支持新增字段"""
        create_resp = org_client.post("/org/create", json={
            "name": "外部组织",
            "code": "ORG_EXT_001",
            "external_source": "feishu",
            "external_corp_id": "corp-001",
            "external_config": '{"tenant_key":"tk-001"}',
            "is_active": False,
        })

        assert create_resp.status_code == 200
        create_data = create_resp.json()["data"]
        assert create_data["external_source"] == "feishu"
        assert create_data["external_corp_id"] == "corp-001"
        assert create_data["external_config"] == '{"tenant_key":"tk-001"}'
        assert create_data["is_active"] is False

        org_id = create_data["id"]
        update_resp = org_client.post(f"/org/update?org_id={org_id}", json={
            "external_source": "dingtalk",
            "external_corp_id": "corp-002",
            "external_config": '{"corp_id":"ding-002"}',
            "is_active": True,
        })

        assert update_resp.status_code == 200
        update_data = update_resp.json()["data"]
        assert update_data["external_source"] == "dingtalk"
        assert update_data["external_corp_id"] == "corp-002"
        assert update_data["external_config"] == '{"corp_id":"ding-002"}'
        assert update_data["is_active"] is True

    def test_department_create_update_and_tree_return_new_fields(self, dept_client):
        """测试部门创建更新及树接口返回新增字段"""
        org_resp = dept_client.post("/org/create", json={
            "name": "部门字段组织",
            "code": "DEPT_FIELD_ORG",
        })
        org_id = org_resp.json()["data"]["id"]

        create_resp = dept_client.post("/dept/create", json={
            "org_id": org_id,
            "name": "技术平台部",
            "caption": "平台能力建设部门",
            "external_dept_id": "ext-dept-1",
            "external_parent_id": "ext-parent-root",
            "is_active": False,
        })

        assert create_resp.status_code == 200
        create_data = create_resp.json()["data"]
        assert create_data["caption"] == "平台能力建设部门"
        assert create_data["external_dept_id"] == "ext-dept-1"
        assert create_data["external_parent_id"] == "ext-parent-root"
        assert create_data["is_active"] is False

        dept_id = create_data["id"]
        update_resp = dept_client.post(f"/dept/update?dept_id={dept_id}", json={
            "caption": "更新后的部门介绍",
            "external_dept_id": "ext-dept-2",
            "external_parent_id": "ext-parent-2",
            "is_active": True,
        })

        assert update_resp.status_code == 200
        update_data = update_resp.json()["data"]
        assert update_data["caption"] == "更新后的部门介绍"
        assert update_data["external_dept_id"] == "ext-dept-2"
        assert update_data["external_parent_id"] == "ext-parent-2"
        assert update_data["is_active"] is True

        tree_resp = dept_client.get(f"/dept/tree?org_id={org_id}")
        assert tree_resp.status_code == 200
        tree_nodes = tree_resp.json()["data"]
        assert tree_nodes[0]["caption"] == "更新后的部门介绍"
        assert tree_nodes[0]["external_dept_id"] == "ext-dept-2"
        assert tree_nodes[0]["external_parent_id"] == "ext-parent-2"
        assert tree_nodes[0]["is_active"] is True

    def test_employee_create_and_update_accept_new_fields(self, emp_client):
        """测试员工创建和更新支持新增字段"""
        create_resp = emp_client.post("/emp/create", json={
            "name": "王五",
            "code": "EMP-001",
            "mobile": "13800138111",
            "note": "来自测试请求",
            "caption": "核心骨干员工",
        })

        assert create_resp.status_code == 200
        create_data = create_resp.json()["data"]
        assert create_data["code"] == "EMP-001"
        assert create_data["note"] == "来自测试请求"
        assert create_data["caption"] == "核心骨干员工"

        emp_id = create_data["id"]
        update_resp = emp_client.post(f"/emp/update?employee_id={emp_id}", json={
            "code": "EMP-002",
            "note": "更新后的备注",
            "caption": "更新后的介绍",
        })

        assert update_resp.status_code == 200
        update_data = update_resp.json()["data"]
        assert update_data["code"] == "EMP-002"
        assert update_data["note"] == "更新后的备注"
        assert update_data["caption"] == "更新后的介绍"
