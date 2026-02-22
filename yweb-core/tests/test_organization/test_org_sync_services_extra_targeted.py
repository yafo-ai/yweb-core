"""组织/同步服务低覆盖分支定向补测（新文件）"""

from types import SimpleNamespace

import pytest

from yweb.organization.enums import ExternalSource
from yweb.organization.services.org_service import BaseOrganizationService
from yweb.organization.services.sync_service import BaseSyncService, SyncResult


class QueryBag:
    def __init__(self, rows=None, first_obj=None, count_value=0):
        self._rows = list(rows or [])
        self._first = first_obj
        self._count = count_value
        self.deleted_calls = 0

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first

    def count(self):
        return self._count

    def delete(self, *args, **kwargs):
        _ = (args, kwargs)
        self.deleted_calls += 1
        return 1


class ExprField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return (self.name, "eq", other)

    def in_(self, value):
        return (self.name, "in", value)


class OrgObj:
    def __init__(self, oid=1, code="ORG"):
        self.id = oid
        self.code = code
        self.name = "Org"
        self.deleted = 0
        self.saved = 0

    def update_properties(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def save(self, commit=True):
        _ = commit
        self.saved += 1

    def delete(self, commit=True):
        _ = commit
        self.deleted += 1


class OrgModelUnit:
    code = ExprField("code")
    is_active = ExprField("is_active")
    query = QueryBag()
    _store = {1: OrgObj(1, "A001")}
    validated_calls = []

    @classmethod
    def get(cls, oid):
        return cls._store.get(oid)

    @classmethod
    def validate_code_unique(cls, code, exclude_id=None):
        cls.validated_calls.append((code, exclude_id))

    def __call__(self, **kwargs):
        obj = OrgObj(99, kwargs.get("code"))
        obj.name = kwargs.get("name", "N")
        return obj


class OrgServiceUnit(BaseOrganizationService):
    org_model = OrgModelUnit


class DeptObj:
    def __init__(self, did, org_id=1, ext_id=None, parent_id=None):
        self.id = did
        self.org_id = org_id
        self.external_dept_id = ext_id
        self.external_parent_id = None
        self.parent_id = parent_id
        self.name = f"D{did}"
        self.sort_order = 0
        self.deleted_at = None
        self.saved = 0
        self.path_calls = 0

    def update_path_and_level(self):
        self.path_calls += 1

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
    def __init__(self, employee_id=1, org_id=1, external_user_id="u1", status=3):
        self.employee_id = employee_id
        self.org_id = org_id
        self.external_user_id = external_user_id
        self.status = status
        self.emp_no = None
        self.position = None
        self.external_union_id = None
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class DeptModelUnit:
    org_id = ExprField("org_id")
    query = QueryBag()

    def __call__(self, **kwargs):
        return DeptObj(
            did=int(str(kwargs.get("external_dept_id", "99")) or "99"),
            org_id=kwargs.get("org_id", 1),
            ext_id=str(kwargs.get("external_dept_id", "")),
            parent_id=None,
        )


class EmployeeModelUnit:
    _store = {1: EmployeeObj(1)}

    @classmethod
    def get(cls, employee_id):
        return cls._store.get(employee_id)

    def __call__(self, **kwargs):
        emp = EmployeeObj(99)
        for k, v in kwargs.items():
            setattr(emp, k, v)
        return emp


class EmpOrgRelModelUnit:
    org_id = ExprField("org_id")
    employee_id = ExprField("employee_id")
    query = QueryBag()

    def __call__(self, **kwargs):
        return EmpOrgRelObj(
            employee_id=kwargs.get("employee_id", 1),
            org_id=kwargs.get("org_id", 1),
            external_user_id=kwargs.get("external_user_id", "uX"),
        )


class EmpDeptRelModelUnit:
    employee_id = ExprField("employee_id")
    dept_id = ExprField("dept_id")
    query = QueryBag()

    def __call__(self, **kwargs):
        rel = SimpleNamespace(**kwargs)
        rel.saved = 0

        def _save(commit=True):
            _ = commit
            rel.saved += 1

        rel.save = _save
        return rel


class SyncServiceUnit(BaseSyncService):
    external_source = ExternalSource.WECHAT_WORK
    org_model = None
    dept_model = DeptModelUnit()
    employee_model = EmployeeModelUnit()
    emp_org_rel_model = EmpOrgRelModelUnit()
    emp_dept_rel_model = EmpDeptRelModelUnit()

    def __init__(self, org_obj, depts=None, emps=None, org_info=None):
        self._org_obj = org_obj
        self._depts = list(depts or [])
        self._emps = list(emps or [])
        self._org_info = org_info
        self.__class__.org_model = type(
            "OrgModelDyn",
            (),
            {"get": classmethod(lambda cls, oid: org_obj)},
        )
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


class TestOrgServiceTargeted:
    def test_org_service_missing_and_delegation_success_paths(self):
        svc = OrgServiceUnit()

        # update_org: 组织不存在
        with pytest.raises(ValueError):
            svc.update_org(999, name="x")

        # update_org: code 变更触发唯一校验
        OrgModelUnit._store[1] = OrgObj(1, "A001")
        svc.update_org(1, code="A002")
        assert ("A002", 1) in OrgModelUnit.validated_calls

        # delete_org: 组织不存在
        with pytest.raises(ValueError):
            svc.delete_org(999)

        # delete_org: 员工数>0 拦截
        svc.dept_service = SimpleNamespace(count_by_org=lambda oid: 0)
        svc.employee_service = SimpleNamespace(count_employees_in_org=lambda oid: 2)
        with pytest.raises(ValueError):
            svc.delete_org(1)

        calls = []
        svc.dept_service = SimpleNamespace(
            update_dept=lambda **kw: calls.append(("update_dept", kw)) or {"ok": 1},
            delete_dept=lambda **kw: calls.append(("delete_dept", kw)) or {"deleted": 1},
            move_dept=lambda **kw: calls.append(("move_dept", kw)) or {"moved": 1},
            get_dept_tree=lambda oid: [f"d-{oid}"],
        )
        svc.employee_service = SimpleNamespace(
            remove_from_org=lambda eid, oid: calls.append(("remove_from_org", eid, oid)),
            get_org_employees=lambda oid: [f"e-{oid}"],
            update_emp_org_status=lambda **kw: calls.append(("update_emp_org_status", kw)) or "r1",
            update_account_status=lambda **kw: calls.append(("update_account_status", kw)) or "r2",
        )

        # 命中行 187 / 201 / 231 / 237 / 243 / 317 / 323
        svc.remove_employee(org_id=3, employee_id=9)
        assert svc.get_employees(org_id=3) == ["e-3"]
        assert svc.update_dept(dept_id=1, name="new") == {"ok": 1}
        assert svc.delete_dept(dept_id=2, force=True, promote_children=False) == {"deleted": 1}
        assert svc.move_dept(dept_id=2, new_parent_id=None) == {"moved": 1}
        assert svc.update_emp_org_status(employee_id=9, org_id=3, status=1) == "r1"
        assert svc.update_account_status(employee_id=9, account_status=-1) == "r2"


class TestSyncServiceTargeted:
    def test_sync_from_external_extends_emp_errors_and_abstract_pass_lines(self, monkeypatch):
        org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)
        svc = SyncServiceUnit(org_obj=org)

        # 避免安全检查中止
        monkeypatch.setattr(DeptModelUnit.query, "_count", 0, raising=False)
        monkeypatch.setattr(EmpOrgRelModelUnit.query, "_count", 0, raising=False)

        fail = SyncResult()
        fail.add_error("emp-fail")
        fail.finish("emp-fail")
        ok = SyncResult()
        ok.finish("ok")

        monkeypatch.setattr(svc, "sync_organization", lambda _org: ok)
        monkeypatch.setattr(svc, "sync_departments", lambda _org: ok)
        monkeypatch.setattr(svc, "sync_employees", lambda _org: fail)
        monkeypatch.setattr(svc, "sync_employee_dept_relations", lambda _org: ok)
        res = svc.sync_from_external(org_id=1)
        assert res.success is False
        assert "emp-fail" in res.errors

        # 覆盖 BaseSyncService 抽象方法中的 pass 行
        assert BaseSyncService.fetch_departments(svc, org) is None
        assert BaseSyncService.fetch_employees(svc, org) is None
        assert BaseSyncService.fetch_organization_info(svc, org) is None

    def test_sync_departments_create_parent_root_and_exception(self, monkeypatch):
        org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)
        existing_root_candidate = DeptObj(did=20, org_id=1, ext_id="20", parent_id=999)
        DeptModelUnit.query = QueryBag(rows=[existing_root_candidate], count_value=0)

        svc = SyncServiceUnit(
            org_obj=org,
            depts=[
                {"external_dept_id": "10", "name": "P"},
                {"external_dept_id": "11", "name": "C", "external_parent_id": "10"},
                {"external_dept_id": "20", "name": "R"},
            ],
        )
        result = svc.sync_departments(org)
        assert result.success is True
        assert result.created_count >= 2  # 覆盖 374-375
        assert result.updated_count >= 1
        assert existing_root_candidate.parent_id is None  # 覆盖 392-394

        # 命中 404-405 异常分支
        monkeypatch.setattr(svc, "fetch_departments", lambda _org: (_ for _ in ()).throw(RuntimeError("boom")))
        svc._cached_departments = None
        failed = svc.sync_departments(org)
        assert failed.success is False
        assert "同步部门失败" in failed.errors[0]

    def test_sync_employees_create_and_exception(self, monkeypatch):
        org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)
        EmpOrgRelModelUnit.query = QueryBag(rows=[], count_value=0)
        svc = SyncServiceUnit(
            org_obj=org,
            emps=[{"external_user_id": "u2", "name": "U2"}],
        )
        created = svc.sync_employees(org)
        assert created.success is True
        assert created.created_count == 1  # 覆盖 457-458

        monkeypatch.setattr(svc, "fetch_employees", lambda _org: (_ for _ in ()).throw(RuntimeError("x")))
        svc._cached_employees = None
        failed = svc.sync_employees(org)
        assert failed.success is False
        assert "同步员工失败" in failed.errors[0]  # 覆盖 477-478

    def test_sync_emp_dept_rel_continue_string_and_exception(self, monkeypatch):
        org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)

        # 部门映射
        DeptModelUnit.query = QueryBag(rows=[DeptObj(did=10, org_id=1, ext_id="10")])
        # 仅 u1 有映射，u2 无映射会命中 continue(519)
        EmpOrgRelModelUnit.query = QueryBag(rows=[EmpOrgRelObj(employee_id=1, org_id=1, external_user_id="u1")])
        EmpDeptRelModelUnit.query = QueryBag(rows=[])

        svc = SyncServiceUnit(
            org_obj=org,
            emps=[
                {"external_user_id": "u2", "department_ids": ["10"]},
                {"external_user_id": "u1", "department_ids": "10"},  # 命中字符串分支 524
            ],
        )
        ok = svc.sync_employee_dept_relations(org)
        assert ok.success is True

        # 命中 560-561 异常分支
        monkeypatch.setattr(DeptModelUnit.query, "filter", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("bad")))
        failed = svc.sync_employee_dept_relations(org)
        assert failed.success is False
        assert "同步员工-部门关系失败" in failed.errors[0]
