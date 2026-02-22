"""sync_service 深度补充分支测试（新文件）"""

from datetime import datetime
from types import SimpleNamespace

from yweb.organization.enums import ExternalSource
from yweb.organization.services.sync_service import BaseSyncService, SyncResult


class QueryStub:
    def __init__(self, rows=None, count_value=0):
        self._rows = list(rows or [])
        self._count = count_value
        self.deleted_calls = 0

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def all(self):
        return list(self._rows)

    def count(self):
        return self._count

    def delete(self):
        self.deleted_calls += 1
        return 1


class ExprField:
    def __init__(self, name: str):
        self.name = name

    def in_(self, value):
        return (self.name, "in", value)

    def __eq__(self, other):
        return (self.name, "eq", other)


class DeptObj:
    def __init__(self, ext_id, org_id=1):
        self.id = int(ext_id)
        self.org_id = org_id
        self.external_dept_id = str(ext_id)
        self.external_parent_id = None
        self.parent_id = None
        self.name = f"D{ext_id}"
        self.sort_order = 0
        self.deleted_at = None
        self.saved = 0

    def update_path_and_level(self):
        return None

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class EmployeeObj:
    def __init__(self, eid=1):
        self.id = eid
        self.name = "E"
        self.mobile = None
        self.email = None
        self.avatar = None
        self.gender = 0
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class EmpOrgRelObj:
    def __init__(self, employee_id=1, org_id=1, ext_uid="u1"):
        self.employee_id = employee_id
        self.org_id = org_id
        self.external_user_id = ext_uid
        self.external_union_id = None
        self.emp_no = None
        self.position = None
        self.status = 3
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class EmpDeptRelObj:
    def __init__(self, employee_id=1, dept_id=1, external_dept_id=None):
        self.employee_id = employee_id
        self.dept_id = dept_id
        self.external_dept_id = external_dept_id
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class OrgModelStub:
    query = QueryStub()

    @classmethod
    def get(cls, org_id):
        return SimpleNamespace(
            id=org_id,
            external_source=ExternalSource.WECHAT_WORK.value,
            name="Org",
            code="O1",
            save=lambda commit=True: None,
        )


class DeptModelStub:
    org_id = "org_id_col"
    query = QueryStub()

    def __call__(self, **kwargs):
        d = DeptObj(kwargs.get("external_dept_id", "9"), kwargs.get("org_id", 1))
        d.name = kwargs.get("name", d.name)
        d.external_parent_id = kwargs.get("external_parent_id")
        d.sort_order = kwargs.get("sort_order", 0)
        return d


class EmployeeModelStub:
    query = QueryStub()

    _map = {1: EmployeeObj(1)}

    @classmethod
    def get(cls, employee_id):
        return cls._map.get(employee_id)

    def __call__(self, **kwargs):
        e = EmployeeObj(99)
        for k, v in kwargs.items():
            setattr(e, k, v)
        return e


class EmpOrgRelModelStub:
    org_id = ExprField("org_id")
    employee_id = ExprField("employee_id")
    status = ExprField("status")
    query = QueryStub()

    def __call__(self, **kwargs):
        return EmpOrgRelObj(
            employee_id=kwargs.get("employee_id", 1),
            org_id=kwargs.get("org_id", 1),
            ext_uid=kwargs.get("external_user_id", "uX"),
        )


class EmpDeptRelModelStub:
    employee_id = ExprField("employee_id")
    dept_id = ExprField("dept_id")
    query = QueryStub()

    def __call__(self, **kwargs):
        return EmpDeptRelObj(
            employee_id=kwargs.get("employee_id", 1),
            dept_id=kwargs.get("dept_id", 1),
            external_dept_id=kwargs.get("external_dept_id"),
        )


class SyncServiceImpl(BaseSyncService):
    external_source = ExternalSource.WECHAT_WORK
    org_model = OrgModelStub
    dept_model = DeptModelStub()
    employee_model = EmployeeModelStub()
    emp_org_rel_model = EmpOrgRelModelStub()
    emp_dept_rel_model = EmpDeptRelModelStub()

    def __init__(self, depts=None, emps=None, org_info=None):
        self._depts = list(depts or [])
        self._emps = list(emps or [])
        self._org_info = org_info
        super().__init__()

    def fetch_departments(self, org):
        _ = org
        return list(self._depts)

    def fetch_employees(self, org):
        _ = org
        return list(self._emps)

    def fetch_organization_info(self, org):
        _ = org
        return self._org_info


class TestSyncServiceExtraDeep:
    def test_sync_from_external_success_aggregate(self, monkeypatch):
        svc = SyncServiceImpl(
            depts=[{"external_dept_id": "1", "name": "D1"}],
            emps=[{"external_user_id": "u1", "name": "E1"}],
        )
        monkeypatch.setattr(DeptModelStub.query, "_count", 1, raising=False)
        monkeypatch.setattr(EmpOrgRelModelStub.query, "_count", 1, raising=False)

        monkeypatch.setattr(svc, "sync_organization", lambda org: SyncResult())
        r_dept = SyncResult()
        r_dept.created_count = 2
        monkeypatch.setattr(svc, "sync_departments", lambda org: r_dept)
        r_emp = SyncResult()
        r_emp.updated_count = 3
        monkeypatch.setattr(svc, "sync_employees", lambda org: r_emp)
        monkeypatch.setattr(svc, "sync_employee_dept_relations", lambda org: SyncResult())

        result = svc.sync_from_external(org_id=1)
        assert result.success is True
        assert result.created_count == 2
        assert result.updated_count == 3
        assert "同步完成" in result.message

    def test_sync_from_external_safety_check_abort(self, monkeypatch):
        svc = SyncServiceImpl(depts=[], emps=[])
        monkeypatch.setattr(DeptModelStub.query, "_count", 100, raising=False)
        monkeypatch.setattr(EmpOrgRelModelStub.query, "_count", 120, raising=False)
        result = svc.sync_from_external(org_id=1)
        assert result.success is False
        assert "安全检查未通过" in result.message

    def test_sync_organization_update_fields(self):
        org = SimpleNamespace(
            id=1,
            name="old",
            code="old",
            external_source=ExternalSource.WECHAT_WORK.value,
            external_corp_id="cid",
            save=lambda commit=True: None,
        )
        svc = SyncServiceImpl(org_info={"name": "new_name", "code": "new_code", "id": 999})
        result = svc.sync_organization(org)
        assert result.success is True
        assert org.name == "new_name"
        # id 不应被覆盖
        assert org.id == 1

    def test_sync_employee_dept_relations_add_and_remove(self):
        # 本地部门映射：10, 20
        DeptModelStub.query = QueryStub(rows=[DeptObj("10"), DeptObj("20")])
        # 员工映射：u1 -> employee_id=1
        EmpOrgRelModelStub.query = QueryStub(rows=[EmpOrgRelObj(employee_id=1, org_id=1, ext_uid="u1")])
        # 现有关联：dept_id=20，外部将改成10，触发删除20并新增10
        existing_rel = EmpDeptRelObj(employee_id=1, dept_id=20, external_dept_id="20")
        EmpDeptRelModelStub.query = QueryStub(rows=[existing_rel])

        svc = SyncServiceImpl(
            emps=[{"external_user_id": "u1", "department_ids": ["10"]}],
        )
        org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)
        result = svc.sync_employee_dept_relations(org)
        assert result.success is True
        # 命中删除路径
        assert EmpDeptRelModelStub.query.deleted_calls >= 1
