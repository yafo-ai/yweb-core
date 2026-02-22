"""emp_service 账号联动与容错路径补充测试（新文件）"""

from types import SimpleNamespace

import pytest

from yweb.organization.services.emp_service import BaseEmployeeService


class ExprField:
    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return (self.name, "eq", other)

    def __gt__(self, other):
        return (self.name, "gt", other)

    def in_(self, value):
        return (self.name, "in", value)

    def contains(self, value):
        return (self.name, "contains", value)


class QueryStub:
    def __init__(self, first_obj=None, count_value=0, rows=None):
        self._first = first_obj
        self._count = count_value
        self._rows = list(rows or [])

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        return self._first

    def count(self):
        return self._count

    def order_by(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def paginate(self, page=1, page_size=20):
        return SimpleNamespace(
            rows=list(self._rows),
            total_records=len(self._rows),
            page=page,
            page_size=page_size,
            total_pages=1 if self._rows else 0,
        )

    def delete(self, *args, **kwargs):
        _ = (args, kwargs)
        return 1

    def update(self, *args, **kwargs):
        _ = (args, kwargs)
        return 1


class EmployeeObj:
    def __init__(self, eid=1):
        self.id = eid
        self.primary_org_id = None
        self.primary_dept_id = None
        self.session = SimpleNamespace(expire=lambda *_args, **_kwargs: None)
        self.saved = 0
        self.user_id = None
        self.user = None

    def save(self, commit=True):
        _ = commit
        self.saved += 1

    def update_properties(self, **kwargs):
        for k, v in kwargs.items():
            setattr(self, k, v)

    def delete(self, commit=True):
        _ = commit


class UserObj:
    def __init__(self, active=True):
        self.is_active = active
        self.saved = 0

    def save(self, commit=True):
        _ = commit
        self.saved += 1


class UserClassStub:
    obj = UserObj(active=True)

    @classmethod
    def get(cls, user_id):
        _ = user_id
        return cls.obj


class EmployeeModelNoCode:
    id = ExprField("id")
    name = ExprField("name")
    query = QueryStub(rows=[EmployeeObj(1)])
    _store = {1: EmployeeObj(1)}

    @classmethod
    def get(cls, eid):
        return cls._store.get(eid)

    def __call__(self, **kwargs):
        obj = EmployeeObj(99)
        for k, v in kwargs.items():
            setattr(obj, k, v)
        return obj


class EmployeeModelWithCode(EmployeeModelNoCode):
    code = ExprField("code")


class EmpOrgRelModelStub:
    employee_id = ExprField("employee_id")
    org_id = ExprField("org_id")
    status = ExprField("status")
    query = QueryStub()

    def __call__(self, **kwargs):
        rel = SimpleNamespace(**kwargs)
        rel.status = kwargs.get("status", 3)
        rel.save = lambda commit=True: None
        return rel


class EmpDeptRelModelStub:
    employee_id = ExprField("employee_id")
    dept_id = ExprField("dept_id")
    query = QueryStub()

    def __call__(self, **kwargs):
        rel = SimpleNamespace(**kwargs)
        rel.save = lambda commit=True: None
        return rel


class DeptModelStub:
    id = ExprField("id")
    org_id = ExprField("org_id")
    primary_leader_id = ExprField("primary_leader_id")
    query = QueryStub(rows=[])

    @classmethod
    def get(cls, dept_id):
        if dept_id == 1:
            return SimpleNamespace(id=1, org_id=1)
        return None


class DeptLeaderModelStub:
    employee_id = ExprField("employee_id")
    dept_id = ExprField("dept_id")
    query = QueryStub()


class EmpServiceNoModel(BaseEmployeeService):
    pass


class EmpServiceUnit(BaseEmployeeService):
    employee_model = EmployeeModelWithCode
    dept_model = DeptModelStub
    emp_org_rel_model = EmpOrgRelModelStub
    emp_dept_rel_model = EmpDeptRelModelStub
    dept_leader_model = DeptLeaderModelStub


class TestEmpServiceExtraAccountPaths:
    def test_init_requires_employee_model(self):
        with pytest.raises(ValueError):
            EmpServiceNoModel()

    def test_get_employee_by_code_without_code_attr_and_list_without_keyword(self):
        svc = EmpServiceUnit()
        svc.employee_model = EmployeeModelNoCode
        assert svc.get_employee_by_code("X") is None
        page = svc.list_employees(keyword=None, page=1, page_size=10)
        assert page.page == 1

    def test_none_model_guard_branches(self):
        svc = EmpServiceUnit()
        svc.emp_org_rel_model = None
        svc.emp_dept_rel_model = None

        # remove 分支直接返回
        assert svc.remove_from_org(employee_id=1, org_id=1) is None
        assert svc.remove_from_dept(employee_id=1, dept_id=1) is None

        # getter/count 分支
        assert svc.get_org_employees(org_id=1) == []
        assert svc.count_employees_in_org(org_id=1) == 0
        assert svc.get_employee_orgs(employee_id=1) == []
        assert svc.get_employee_depts(employee_id=1) == []
        assert svc.get_dept_employees(dept_id=1) == []
        assert svc._has_any_active_org(employee_id=1) is False

        with pytest.raises(ValueError):
            svc.update_emp_org_status(employee_id=1, org_id=1, status=1)

    def test_set_primary_org_same_org_does_not_clear_dept(self):
        svc = EmpServiceUnit()
        emp = EmployeeObj(1)
        emp.primary_org_id = 1
        emp.primary_dept_id = 9
        svc.employee_model._store[1] = emp
        svc.emp_org_rel_model.query = QueryStub(count_value=1)
        svc.set_primary_org(employee_id=1, org_id=1)
        assert emp.primary_dept_id == 9
        assert emp.primary_org_id == 1

    def test_set_primary_dept_not_found_and_without_dept_model(self):
        svc = EmpServiceUnit()
        emp = EmployeeObj(1)
        emp.primary_org_id = 1
        svc.employee_model._store[1] = emp

        # 部门不存在
        with pytest.raises(ValueError):
            svc.set_primary_dept(employee_id=1, dept_id=999)

        # 无 dept_model 时跳过部门校验，走“员工不在该部门”分支
        svc.dept_model = None
        svc.emp_dept_rel_model.query = QueryStub(count_value=0)
        with pytest.raises(ValueError):
            svc.set_primary_dept(employee_id=1, dept_id=1)

    def test_update_account_status_branches_and_success(self):
        svc = EmpServiceUnit()

        # 无 user_id 属性
        emp_no_attr = SimpleNamespace(id=10)
        svc.employee_model._store[10] = emp_no_attr
        with pytest.raises(ValueError):
            svc.update_account_status(employee_id=10, account_status=1)

        # user_id 为空
        emp_no_user = EmployeeObj(11)
        emp_no_user.user_id = None
        svc.employee_model._store[11] = emp_no_user
        with pytest.raises(ValueError):
            svc.update_account_status(employee_id=11, account_status=1)

        # user 为空
        emp_user_missing = EmployeeObj(12)
        emp_user_missing.user_id = 88
        emp_user_missing.user = None
        svc.employee_model._store[12] = emp_user_missing
        with pytest.raises(ValueError):
            svc.update_account_status(employee_id=12, account_status=1)

        # 激活时无活跃组织 -> 拒绝
        emp_block = EmployeeObj(13)
        emp_block.user_id = 77
        emp_block.user = UserObj(active=False)
        svc.employee_model._store[13] = emp_block
        svc.emp_org_rel_model.query = QueryStub(count_value=0)
        with pytest.raises(ValueError):
            svc.update_account_status(employee_id=13, account_status=1)

        # 禁用成功
        emp_disable = EmployeeObj(14)
        emp_disable.user_id = 66
        emp_disable.user = UserObj(active=True)
        svc.employee_model._store[14] = emp_disable
        result = svc.update_account_status(employee_id=14, account_status=-1)
        assert result is emp_disable
        assert emp_disable.user.is_active is False
        assert emp_disable.user.saved == 1

        # 激活成功（有活跃组织）
        emp_enable = EmployeeObj(15)
        emp_enable.user_id = 65
        emp_enable.user = UserObj(active=False)
        svc.employee_model._store[15] = emp_enable
        svc.emp_org_rel_model.query = QueryStub(count_value=1)
        result2 = svc.update_account_status(employee_id=15, account_status=1)
        assert result2 is emp_enable
        assert emp_enable.user.is_active is True

    def test_disable_linked_account_fallback_and_inactive_paths(self):
        svc = EmpServiceUnit()

        # user_id 为空
        emp_none = EmployeeObj(20)
        emp_none.user_id = None
        assert svc._disable_linked_account(emp_none) is False

        # 无 user，通过 type(employee).user.property.mapper.class_.get 回退获取
        class EmployeeWithRel:
            user = SimpleNamespace(property=SimpleNamespace(mapper=SimpleNamespace(class_=UserClassStub)))

            def __init__(self):
                self.user_id = 1
                self.user = None

        emp_rel = EmployeeWithRel()
        UserClassStub.obj = UserObj(active=True)
        assert svc._disable_linked_account(emp_rel) is True
        assert UserClassStub.obj.is_active is False

        # 已禁用用户不重复保存
        emp_inactive = EmployeeObj(21)
        emp_inactive.user_id = 2
        emp_inactive.user = UserObj(active=False)
        assert svc._disable_linked_account(emp_inactive) is False
