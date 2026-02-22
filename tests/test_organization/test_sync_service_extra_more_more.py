"""sync_service 额外补充分支（新文件）"""

import pytest

from yweb.organization.services.sync_service import BaseSyncService, SyncResult

from tests.test_organization.test_sync_service_extra_deep import (
    DeptModelStub,
    EmpOrgRelModelStub,
    EmployeeModelStub,
    OrgModelStub,
    SyncServiceImpl,
)


class TestSyncServiceExtraMoreMore:
    def test_sync_result_duration_and_to_dict(self):
        r = SyncResult()
        assert r.duration_seconds == 0
        r.finish("done")
        payload = r.to_dict()
        assert payload["message"] == "done"
        assert "duration_seconds" in payload

    def test_validate_config_missing_models_raises(self):
        class SyncBad(BaseSyncService):
            external_source = object()
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

        with pytest.raises(ValueError):
            SyncBad()

    def test_sync_from_external_collects_sub_errors(self, monkeypatch):
        svc = SyncServiceImpl(depts=[{"external_dept_id": "1", "name": "D"}], emps=[])
        org = OrgModelStub.get(1)
        monkeypatch.setattr(OrgModelStub, "get", classmethod(lambda cls, oid: org))

        # 避免安全阈值中止
        monkeypatch.setattr(DeptModelStub.query, "_count", 0, raising=False)
        monkeypatch.setattr(EmpOrgRelModelStub.query, "_count", 0, raising=False)

        fail_r = SyncResult()
        fail_r.add_error("sub-error")
        fail_r.finish("sub-fail")
        ok_r = SyncResult()
        ok_r.finish("ok")

        monkeypatch.setattr(svc, "sync_organization", lambda _org: fail_r)
        monkeypatch.setattr(svc, "sync_departments", lambda _org: fail_r)
        monkeypatch.setattr(svc, "sync_employees", lambda _org: ok_r)
        monkeypatch.setattr(svc, "sync_employee_dept_relations", lambda _org: fail_r)

        result = svc.sync_from_external(org_id=1)
        assert result.success is False
        assert len(result.errors) >= 2

    def test_sync_organization_exception_branch(self, monkeypatch):
        svc = SyncServiceImpl()
        org = OrgModelStub.get(1)
        monkeypatch.setattr(svc, "fetch_organization_info", lambda _org: (_ for _ in ()).throw(RuntimeError("x")))
        result = svc.sync_organization(org)
        assert result.success is False
        assert "同步组织信息失败" in result.errors[0]

    def test_create_update_helpers_for_dept_and_employee(self):
        svc = SyncServiceImpl()
        org = OrgModelStub.get(1)

        # _create_dept_from_external / _update_dept_from_external
        dept = svc._create_dept_from_external(
            org,
            {"external_dept_id": "9", "external_parent_id": "1", "name": "Dept9", "sort_order": 3},
        )
        assert dept.external_dept_id == "9"
        svc._update_dept_from_external(dept, {"name": "Dept9-upd", "sort_order": 5})
        assert dept.name == "Dept9-upd"

        # _create_employee_from_external / _update_employee_from_external
        emp = svc._create_employee_from_external(
            org,
            {
                "external_user_id": "u9",
                "name": "Emp9",
                "mobile": "13800138000",
                "email": "u9@test.com",
                "avatar": "a",
                "gender": 1,
                "emp_no": "EMP9",
                "position": "dev",
                "external_union_id": "union9",
            },
        )
        assert emp.name == "Emp9"

        rel = type(
            "RelObj",
            (),
            {
                "employee_id": emp.id,
                "org_id": org.id,
                "emp_no": None,
                "position": None,
                "external_union_id": None,
                "save": lambda self, commit=True: None,
            },
        )()
        svc._update_employee_from_external(
            emp,
            rel,
            {"name": "Emp9-upd", "position": "lead", "external_union_id": "union10"},
        )
        assert emp.name == "Emp9-upd"
        assert rel.position == "lead"
