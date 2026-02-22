"""department_api 深度补充分支测试（新文件）"""

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.orm import Page
from yweb.organization.api.department_api import create_department_crud_router


class ExprField:
    def __init__(self, name: str):
        self.name = name

    def in_(self, value):
        return (self.name, "in", value)

    def is_(self, value):
        return (self.name, "is", value)

    def __eq__(self, other):
        return (self.name, "eq", other)


class QueryChain:
    def __init__(self, rows=None, first_item=None):
        self._rows = list(rows or [])
        self._first = first_item

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
        if self._first is not None:
            return self._first
        return self._rows[0] if self._rows else None

    def paginate(self, page=1, page_size=20):
        return Page(
            rows=list(self._rows),
            total_records=len(self._rows),
            page=page,
            page_size=page_size,
            total_pages=1 if self._rows else 0,
        )


class FakeUserModel:
    is_active = ExprField("is_active")
    query = QueryChain(rows=[SimpleNamespace(id=7)])


class FakeEmployeeModel:
    id = ExprField("id")
    user_id = ExprField("user_id")
    query = QueryChain(rows=[])
    # 模拟 relationship.property.mapper.class_ 链路
    user = SimpleNamespace(property=SimpleNamespace(mapper=SimpleNamespace(class_=FakeUserModel)))


class FakeDeptModel:
    org_id = ExprField("org_id")
    is_active = ExprField("is_active")
    level = ExprField("level")
    sort_order = ExprField("sort_order")
    _dept = SimpleNamespace(id=101, org_id=1)

    @classmethod
    def get(cls, dept_id):
        return cls._dept if dept_id == 101 else None


class FakeEmpDeptRelModel:
    dept_id = ExprField("dept_id")
    employee_id = ExprField("employee_id")
    query = QueryChain(rows=[SimpleNamespace(employee_id=1)])


class FakeEmpOrgRelModel:
    employee_id = ExprField("employee_id")
    org_id = ExprField("org_id")
    status = ExprField("status")
    query = QueryChain(
        rows=[SimpleNamespace(employee_id=1)],
        first_item=SimpleNamespace(emp_no="EMP001", position="SE", status=3),
    )


class FakeEmployeeRow:
    def __init__(self):
        self.id = 1
        self.user_id = 7
        self.user = SimpleNamespace(is_active=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": "张三",
            "mobile": "13800138000",
            "email": "a@b.com",
            "gender": 1,
            "avatar": None,
            "is_senior": False,
            "primary_org_id": 1,
            "primary_dept_id": 101,
            "created_at": None,
            "updated_at": None,
        }


class FakeOrgModel:
    @classmethod
    def get(cls, org_id):
        return SimpleNamespace(id=org_id)


class FakeOrgService:
    pass


class TestDepartmentApiExtraDeep:
    def test_get_dept_employees_status_filters_and_enrichment(self):
        # 准备员工查询返回
        FakeEmployeeModel.query = QueryChain(rows=[FakeEmployeeRow()])
        app = FastAPI()
        router = create_department_crud_router(
            dept_model=FakeDeptModel,
            org_model=FakeOrgModel,
            employee_model=FakeEmployeeModel,
            emp_org_rel_model=FakeEmpOrgRelModel,
            emp_dept_rel_model=FakeEmpDeptRelModel,
            dept_leader_model=None,
            org_service=FakeOrgService(),
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)

        resp = client.get("/dept/employees?dept_id=101&emp_status=3&account_status=1&page=1&page_size=10")
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "success"
        assert body["data"]["total_records"] == 1
        row = body["data"]["rows"][0]
        assert row["emp_no"] == "EMP001"
        assert row["position"] == "SE"
        assert row["status"] == 3
        assert row["account_status"] == 1

    def test_get_dept_employees_dept_not_found(self):
        app = FastAPI()
        router = create_department_crud_router(
            dept_model=FakeDeptModel,
            org_model=FakeOrgModel,
            employee_model=FakeEmployeeModel,
            emp_org_rel_model=FakeEmpOrgRelModel,
            emp_dept_rel_model=FakeEmpDeptRelModel,
            dept_leader_model=None,
            org_service=FakeOrgService(),
        )
        app.include_router(router, prefix="/dept")
        client = TestClient(app)
        resp = client.get("/dept/employees?dept_id=999")
        assert resp.status_code == 404
