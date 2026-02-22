"""organization services 额外深度测试（新文件）"""

import pytest
from sqlalchemy.orm import scoped_session, sessionmaker

from yweb.organization.enums import EmployeeStatus
from yweb.orm import BaseModel, CoreModel

from tests.test_organization.test_services import (
    DeptServiceImpl,
    EmpServiceImpl,
    OrgServiceImpl,
)


class TestOrganizationServicesExtraDeepMore:
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        BaseModel.metadata.create_all(bind=memory_engine)
        session_local = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(session_local)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()

    def test_org_service_delegation_and_list_branches(self):
        svc = OrgServiceImpl()

        # list_orgs: is_active None / True
        org1 = svc.create_org(name="A", code="A001", is_active=True)
        svc.create_org(name="B", code="B001", is_active=False)
        assert len(svc.list_orgs()) >= 2
        actives = svc.list_orgs(is_active=True)
        assert any(o.id == org1.id for o in actives)

        # 未配置子服务时的便捷方法分支
        with pytest.raises(ValueError):
            svc.update_dept(dept_id=1, name="x")
        with pytest.raises(ValueError):
            svc.delete_dept(dept_id=1)
        with pytest.raises(ValueError):
            svc.move_dept(dept_id=1, new_parent_id=None)
        with pytest.raises(ValueError):
            svc.add_dept_leader(dept_id=1, employee_id=1)
        with pytest.raises(ValueError):
            svc.remove_dept_leader(dept_id=1, employee_id=1)
        with pytest.raises(ValueError):
            svc.update_employee(employee_id=1, name="u")
        with pytest.raises(ValueError):
            svc.delete_employee(employee_id=1)
        with pytest.raises(ValueError):
            svc.add_employee_to_org(employee_id=1, org_id=1)
        with pytest.raises(ValueError):
            svc.remove_employee_from_org(employee_id=1, org_id=1)
        with pytest.raises(ValueError):
            svc.set_primary_org(employee_id=1, org_id=1)
        with pytest.raises(ValueError):
            svc.add_employee_to_dept(employee_id=1, dept_id=1)
        with pytest.raises(ValueError):
            svc.remove_employee_from_dept(employee_id=1, dept_id=1)
        with pytest.raises(ValueError):
            svc.set_primary_dept(employee_id=1, dept_id=1)
        with pytest.raises(ValueError):
            svc.update_emp_org_status(employee_id=1, org_id=1, status=3)
        with pytest.raises(ValueError):
            svc.update_account_status(employee_id=1, account_status=1)

        # get_* 在未配置下应返回空
        assert svc.get_employees(org_id=1) == []
        assert svc.get_departments(org_id=1) == []

    def test_emp_service_status_account_and_fallback_branches(self):
        org_svc = OrgServiceImpl()
        dept_svc = DeptServiceImpl()
        emp_svc = EmpServiceImpl()
        org_svc.dept_service = dept_svc
        org_svc.employee_service = emp_svc
        dept_svc.org_service = org_svc
        dept_svc.employee_service = emp_svc

        org = org_svc.create_org(name="Org", code="ORG1")
        dept = dept_svc.create_dept(org_id=org.id, name="Dept")
        emp = emp_svc.create_employee(name="Emp", mobile="13800000000")

        # list_employees keyword 分支
        page = emp_svc.list_employees(keyword="Emp", page=1, page_size=10)
        assert page.total_records >= 1

        # add_to_org / add_to_dept
        emp_svc.add_to_org(emp.id, org.id, status=EmployeeStatus.ACTIVE.value, set_as_primary=True)
        emp_svc.add_to_dept(emp.id, dept.id, set_as_primary=True)

        # update_emp_org_status: 参数非法
        with pytest.raises(ValueError):
            emp_svc.update_emp_org_status(employee_id=emp.id, org_id=org.id, status=999)

        # update_emp_org_status: 关系不存在
        with pytest.raises(ValueError):
            emp_svc.update_emp_org_status(employee_id=9999, org_id=org.id, status=EmployeeStatus.ACTIVE.value)

        # 先设离职，命中 status<=0 分支（会触发账号禁用路径，当前无 user_id 会静默）
        rel = emp_svc.update_emp_org_status(
            employee_id=emp.id,
            org_id=org.id,
            status=EmployeeStatus.RESIGNED.value,
        )
        assert rel.status == EmployeeStatus.RESIGNED.value

        # update_account_status 分支覆盖
        with pytest.raises(ValueError):
            emp_svc.update_account_status(employee_id=emp.id, account_status=0)  # 非法状态值
        with pytest.raises(ValueError):
            emp_svc.update_account_status(employee_id=9999, account_status=1)  # 员工不存在
        with pytest.raises(ValueError):
            emp_svc.update_account_status(employee_id=emp.id, account_status=1)  # 未创建账号

        # set_primary_org / set_primary_dept 失败分支
        with pytest.raises(ValueError):
            emp_svc.set_primary_org(employee_id=9999, org_id=org.id)
        with pytest.raises(ValueError):
            emp_svc.set_primary_dept(employee_id=9999, dept_id=dept.id)

        # remove_from_org / remove_from_dept 失败分支
        with pytest.raises(ValueError):
            emp_svc.remove_from_org(employee_id=9999, org_id=org.id)
        with pytest.raises(ValueError):
            emp_svc.remove_from_dept(employee_id=9999, dept_id=dept.id)
