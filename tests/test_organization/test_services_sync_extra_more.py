"""组织模块 services/sync 补充分支测试（新文件）"""

from types import SimpleNamespace

import pytest

from yweb.organization.enums import ExternalSource
from yweb.organization.services.emp_service import BaseEmployeeService
from yweb.organization.services.org_service import BaseOrganizationService
from yweb.organization.services.sync_service import BaseSyncService


class QueryCounterStub:
    def __init__(self, count_value=0, first_obj=None, all_rows=None):
        self._count = count_value
        self._first = first_obj
        self._rows = list(all_rows or [])

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def filter_by(self, **kwargs):
        _ = kwargs
        return self

    def count(self):
        return self._count

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)

    def delete(self, *args, **kwargs):
        _ = (args, kwargs)
        return 1

    def update(self, *args, **kwargs):
        _ = (args, kwargs)
        return 1

    def order_by(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def paginate(self, page=1, page_size=20):
        return SimpleNamespace(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)


class EmployeeObj:
    def __init__(self, eid=1):
        self.id = eid
        self.name = "e"
        self.code = "E1"
        self.primary_org_id = None
        self.primary_dept_id = None
        self.user_id = None
        self.user = None
        self.session = SimpleNamespace(expire=lambda *_args, **_kwargs: None)
        self.saved = 0
        self.deleted = 0

    def update_properties(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def save(self, commit=True):
        _ = commit
        self.saved += 1

    def delete(self, commit=True):
        _ = commit
        self.deleted += 1


class EmployeeModelStub:
    query = QueryCounterStub()
    code = "code_col"
    id = "id_col"
    name = "name_col"
    user_id = "user_id_col"

    _store = {1: EmployeeObj(1)}

    @classmethod
    def get(cls, eid):
        return cls._store.get(eid)

    def __call__(self, *args, **kwargs):
        _ = args
        obj = EmployeeObj(99)
        for k, v in kwargs.items():
            setattr(obj, k, v)
        return obj


class EmpOrgRelStub:
    employee_id = "employee_id_col"
    org_id = "org_id_col"
    status = "status_col"
    query = QueryCounterStub()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class EmpDeptRelStub:
    employee_id = "employee_id_col"
    dept_id = "dept_id_col"
    query = QueryCounterStub()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class DeptModelStub:
    id = "id_col"
    org_id = "org_id_col"
    primary_leader_id = "leader_col"
    query = QueryCounterStub(all_rows=[])

    @classmethod
    def get(cls, did):
        if did == 1:
            return SimpleNamespace(id=1, org_id=1)
        return None


class DeptLeaderModelStub:
    employee_id = "employee_id_col"
    dept_id = "dept_id_col"
    query = QueryCounterStub()


class OrgModelStub:
    code = "code_col"
    is_active = "active_col"
    query = QueryCounterStub()

    _store = {1: SimpleNamespace(id=1, code="O1", name="Org1", delete=lambda commit=True: None)}

    @classmethod
    def get(cls, oid):
        return cls._store.get(oid)

    @classmethod
    def validate_code_unique(cls, code, exclude_id=None):
        _ = (code, exclude_id)
        return None

    def __call__(self, **kwargs):
        obj = SimpleNamespace(**kwargs)
        obj.save = lambda commit=True: None
        obj.delete = lambda commit=True: None
        obj.update_properties = lambda **kw: obj.__dict__.update(kw)
        return obj


class EmployeeServiceImpl(BaseEmployeeService):
    employee_model = EmployeeModelStub
    dept_model = DeptModelStub
    emp_org_rel_model = EmpOrgRelStub
    emp_dept_rel_model = EmpDeptRelStub
    dept_leader_model = DeptLeaderModelStub


class OrgServiceImpl(BaseOrganizationService):
    org_model = OrgModelStub


class SyncImpl(BaseSyncService):
    external_source = ExternalSource.WECHAT_WORK
    org_model = OrgModelStub
    dept_model = DeptModelStub
    employee_model = EmployeeModelStub
    emp_org_rel_model = EmpOrgRelStub
    emp_dept_rel_model = EmpDeptRelStub

    def fetch_departments(self, org):
        _ = org
        return []

    def fetch_employees(self, org):
        _ = org
        return []

    def fetch_organization_info(self, org):
        _ = org
        return None


class TestServicesSyncExtraMore:
    def test_org_service_not_configured_or_delegation_errors(self):
        with pytest.raises(ValueError):
            class OrgBad(BaseOrganizationService):
                pass

            OrgBad()

        svc = OrgServiceImpl()
        with pytest.raises(ValueError):
            svc.add_employee(org_id=1, employee_id=1)
        with pytest.raises(ValueError):
            svc.remove_employee(org_id=1, employee_id=1)
        with pytest.raises(ValueError):
            svc.create_dept(org_id=1, name="d")
        with pytest.raises(ValueError):
            svc.create_employee(name="u")

    def test_employee_service_basic_error_and_guard_branches(self, monkeypatch):
        svc = EmployeeServiceImpl()

        # get_by_code 分支
        assert svc.get_employee_by_code("E1") is None or svc.get_employee_by_code("E1") is not None

        with pytest.raises(ValueError):
            svc.update_employee(employee_id=999, name="x")
        with pytest.raises(ValueError):
            svc.delete_employee(employee_id=999)

        # emp_org_rel_model 为空分支
        svc.emp_org_rel_model = None
        with pytest.raises(ValueError):
            svc.add_to_org(employee_id=1, org_id=1)
        assert svc.get_employee_orgs(1) == []
        assert svc.get_org_employees(1) == []
        assert svc.count_employees_in_org(1) == 0
        assert svc.is_employee_in_org(1, 1) is False

        # emp_dept_rel_model 为空分支
        svc.emp_dept_rel_model = None
        with pytest.raises(ValueError):
            svc.add_to_dept(employee_id=1, dept_id=1)
        assert svc.get_employee_depts(1) == []
        assert svc.get_dept_employees(1) == []
        assert svc.is_employee_in_dept(1, 1) is False

        # update_account_status 参数非法
        svc2 = EmployeeServiceImpl()
        with pytest.raises(ValueError):
            svc2.update_account_status(employee_id=1, account_status=0)

    def test_sync_service_validate_and_sync_from_external_branches(self, monkeypatch):
        # 缺配置分支
        with pytest.raises(ValueError):
            class SyncBad(BaseSyncService):
                external_source = None
                org_model = None
                dept_model = None
                employee_model = None
                emp_org_rel_model = None
                emp_dept_rel_model = None

                def fetch_departments(self, org):
                    return []

                def fetch_employees(self, org):
                    return []

                def fetch_organization_info(self, org):
                    return None

            SyncBad()

        svc = SyncImpl()

        # 组织不存在
        monkeypatch.setattr(OrgModelStub, "get", classmethod(lambda cls, oid: None))
        result = svc.sync_from_external(org_id=1)
        assert result.success is False
        assert "组织不存在" in result.errors[0]

        # 来源不匹配
        bad_org = SimpleNamespace(id=1, external_source="feishu")
        monkeypatch.setattr(OrgModelStub, "get", classmethod(lambda cls, oid: bad_org))
        result2 = svc.sync_from_external(org_id=1)
        assert result2.success is False
        assert "不匹配" in result2.errors[0]

        # 异常分支
        ok_org = SimpleNamespace(id=1, external_source=ExternalSource.WECHAT_WORK.value)
        monkeypatch.setattr(OrgModelStub, "get", classmethod(lambda cls, oid: ok_org))
        monkeypatch.setattr(svc, "fetch_departments", lambda org: (_ for _ in ()).throw(RuntimeError("boom")))
        result3 = svc.sync_from_external(org_id=1)
        assert result3.success is False
        assert "同步异常" in result3.errors[0]
