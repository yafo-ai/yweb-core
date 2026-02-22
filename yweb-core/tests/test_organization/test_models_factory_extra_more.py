"""组织模块 models/factory 补充分支测试（新文件）"""

import json
from types import SimpleNamespace

import pytest
from fastapi import FastAPI

from yweb.organization.enums import ExternalSource, Gender
from yweb.organization.factory import (
    OrgModels,
    _create_model_class,
    _generate_tablename,
    create_org_service,
)
from yweb.organization.models.employee import AbstractEmployee
from yweb.organization.models.emp_org_rel import AbstractEmployeeOrgRel
from yweb.organization.models.organization import AbstractOrganization
from tests.test_organization.test_integration import _org_models


class QueryLike:
    def __init__(self, first_obj=None):
        self._first_obj = first_obj

    def filter_by(self, **kwargs):
        _ = kwargs
        return self

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def first(self):
        return self._first_obj


class RelationConfigSample:
    # 这里用普通属性即可，目标是触发 _create_model_class mixin 合并路径
    marker_field = "x"


class TestOrganizationModelsFactoryExtra:
    def test_employee_helper_methods_and_account_status(self):
        emp_like = SimpleNamespace(user_id=None)
        emp_like.get_account_status = lambda: AbstractEmployee.get_account_status(emp_like)
        assert AbstractEmployee.get_account_status(emp_like) == 0
        assert AbstractEmployee.get_account_status_display(emp_like) == "未激活"

        emp_like2 = SimpleNamespace(user_id=1, user=SimpleNamespace(is_active=True))
        emp_like2.get_account_status = lambda: AbstractEmployee.get_account_status(emp_like2)
        assert AbstractEmployee.get_account_status(emp_like2) == 1
        assert AbstractEmployee.get_account_status_display(emp_like2) == "已激活"

        emp_like3 = SimpleNamespace(gender=Gender.MALE.value)
        assert AbstractEmployee.is_male(emp_like3) is True
        assert AbstractEmployee.is_female(emp_like3) is False
        assert AbstractEmployee.get_gender_display(emp_like3) == "男"

    def test_emp_org_rel_json_helpers_and_status_text(self):
        rel_like = SimpleNamespace(status=-1, external_config=None)
        assert AbstractEmployeeOrgRel.is_active(rel_like) is False
        assert AbstractEmployeeOrgRel.is_resigned(rel_like) is True
        assert AbstractEmployeeOrgRel.get_status_display(rel_like) == "离职"
        assert AbstractEmployeeOrgRel.get_external_config_dict(rel_like) == {}

        rel_like.external_config = "not json"
        assert AbstractEmployeeOrgRel.get_external_config_dict(rel_like) == {}

        AbstractEmployeeOrgRel.set_external_config_dict(rel_like, {"k": "v"})
        assert json.loads(rel_like.external_config)["k"] == "v"

    def test_organization_helpers_and_validate_unique(self):
        org_like = SimpleNamespace(external_source=ExternalSource.NONE.value, external_config=None)
        assert AbstractOrganization.is_external(org_like) is False
        assert AbstractOrganization.get_external_config_dict(org_like) == {}

        AbstractOrganization.set_external_config_dict(org_like, {"tenant": "t1"})
        assert AbstractOrganization.get_external_config_dict(org_like)["tenant"] == "t1"

        class OrgFake:
            id = 1
            query = QueryLike(first_obj=object())

        with pytest.raises(ValueError):
            AbstractOrganization.validate_code_unique.__func__(OrgFake, "X001")

        OrgFake.query = QueryLike(first_obj=None)
        AbstractOrganization.validate_code_unique.__func__(OrgFake, "X002")
        AbstractOrganization.validate_code_unique.__func__(OrgFake, "")

    def test_factory_internal_helpers(self):
        assert _generate_tablename("employee", "sys_") == "sys_employee"
        assert _generate_tablename("employee", "") == "employee"

        klass = _create_model_class(
            name="TmpModelA",
            base_class=AbstractOrganization,
            tablename="tmp_org_a",
            mixin=RelationConfigSample,
            extra_attrs={"x_field": 1},
        )
        assert klass.__tablename__ == "tmp_org_a"
        assert getattr(klass, "x_field") == 1

    def test_create_org_models_and_service_and_mount_routes(self, monkeypatch):
        # 复用已有模型，避免重复 create_org_models 触发 SQLAlchemy 同名类警告
        models = _org_models
        assert models.Organization.__tablename__.startswith("integ_")
        assert models.as_dict()["org_model"] is models.Organization

        service = create_org_service(models)
        assert service is not None
        assert service.dept_service is not None
        assert service.employee_service is not None

        # mount_routes 覆盖
        app = FastAPI()
        models.mount_routes(app, prefix="/api/ox")
        route_paths = {r.path for r in app.routes}
        assert any("/api/ox" in p for p in route_paths)

    def test_org_models_get_org_service_singleton(self):
        models = OrgModels(
            Organization=_org_models.Organization,
            Department=_org_models.Department,
            Employee=_org_models.Employee,
            EmployeeOrgRel=_org_models.EmployeeOrgRel,
            EmployeeDeptRel=_org_models.EmployeeDeptRel,
            DepartmentLeader=_org_models.DepartmentLeader,
        )
        s1 = models.get_org_service()
        s2 = models.get_org_service()
        assert s1 is s2
