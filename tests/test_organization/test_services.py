"""组织管理模块 - 服务层测试

测试拆分后的服务类：
- BaseOrganizationService: 组织管理
- BaseDepartmentService: 部门管理 + 负责人
- BaseEmployeeService: 员工管理 + 关联管理
"""

import pytest
from datetime import datetime
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, relationship

from yweb.orm import CoreModel, BaseModel
from yweb.organization import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
    BaseOrganizationService,
    BaseDepartmentService,
    BaseEmployeeService,
    EmployeeStatus,
)


# ==================== 测试用具体模型定义 ====================

class SvcOrganization(AbstractOrganization):
    """测试用组织模型"""
    __tablename__ = "test_svc_organization"
    __table_args__ = {'extend_existing': True}


class SvcEmployee(AbstractEmployee):
    """测试用员工模型"""
    __tablename__ = "test_svc_employee"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_svc_organization"
    __dept_tablename__ = "test_svc_department"


class SvcDepartment(AbstractDepartment):
    """测试用部门模型"""
    __tablename__ = "test_svc_department"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_svc_organization"
    __employee_tablename__ = "test_svc_employee"
    
    # 员工-部门关联（用于验证删除时是否有员工）
    employee_dept_rels = relationship(
        "SvcEmployeeDeptRel",
        back_populates="department",
        foreign_keys="SvcEmployeeDeptRel.dept_id"
    )


class SvcEmployeeOrgRel(AbstractEmployeeOrgRel):
    """测试用员工-组织关联模型"""
    __tablename__ = "test_svc_emp_org_rel"
    __table_args__ = {'extend_existing': True}
    __employee_tablename__ = "test_svc_employee"
    __org_tablename__ = "test_svc_organization"


class SvcEmployeeDeptRel(AbstractEmployeeDeptRel):
    """测试用员工-部门关联模型"""
    __tablename__ = "test_svc_emp_dept_rel"
    __table_args__ = {'extend_existing': True}
    __employee_tablename__ = "test_svc_employee"
    __dept_tablename__ = "test_svc_department"
    
    # 关联到部门（用于 back_populates）
    department = relationship(
        "SvcDepartment",
        back_populates="employee_dept_rels",
        foreign_keys="SvcEmployeeDeptRel.dept_id"
    )


class SvcDepartmentLeader(AbstractDepartmentLeader):
    """测试用部门负责人模型"""
    __tablename__ = "test_svc_dept_leader"
    __table_args__ = {'extend_existing': True}
    __dept_tablename__ = "test_svc_department"
    __employee_tablename__ = "test_svc_employee"


# ==================== 测试用服务类 ====================

class OrgServiceImpl(BaseOrganizationService):
    """测试用组织服务"""
    org_model = SvcOrganization


class DeptServiceImpl(BaseDepartmentService):
    """测试用部门服务"""
    dept_model = SvcDepartment
    dept_leader_model = SvcDepartmentLeader


class EmpServiceImpl(BaseEmployeeService):
    """测试用员工服务"""
    employee_model = SvcEmployee
    dept_model = SvcDepartment
    emp_org_rel_model = SvcEmployeeOrgRel
    emp_dept_rel_model = SvcEmployeeDeptRel
    dept_leader_model = SvcDepartmentLeader


# ==================== 测试类 ====================

class TestOrganizationServices:
    """组织服务测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    @pytest.fixture
    def services(self):
        """创建服务实例并设置依赖关系"""
        org_svc = OrgServiceImpl()
        dept_svc = DeptServiceImpl()
        emp_svc = EmpServiceImpl()
        
        # 设置服务间依赖
        org_svc.dept_service = dept_svc
        org_svc.employee_service = emp_svc
        dept_svc.org_service = org_svc
        dept_svc.employee_service = emp_svc
        
        return {
            'org': org_svc,
            'dept': dept_svc,
            'emp': emp_svc,
        }
    
    # ==================== 组织管理测试 ====================
    
    def test_create_org(self, services):
        """测试创建组织"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        
        assert org.id is not None
        assert org.name == "测试公司"
        assert org.code == "TEST001"
    
    def test_update_org(self, services):
        """测试更新组织"""
        org = services['org'].create_org(name="原名称", code="TEST001")
        
        updated = services['org'].update_org(org.id, name="新名称")
        
        assert updated.name == "新名称"
    
    def test_delete_org_empty(self, services):
        """测试删除空组织（软删除）"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        org_id = org.id
        
        services['org'].delete_org(org_id)
        
        deleted_org = services['org'].get_org(org_id)
        if deleted_org is not None:
            assert deleted_org.is_deleted == True
    
    def test_delete_org_with_dept_fails(self, services):
        """测试删除有部门的组织失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        services['dept'].create_dept(org_id=org.id, name="技术部")
        
        with pytest.raises(ValueError, match="部门"):
            services['org'].delete_org(org.id)
    
    def test_get_org_by_code(self, services):
        """测试根据编码获取组织"""
        services['org'].create_org(name="公司A", code="A001")
        services['org'].create_org(name="公司B", code="B001")
        
        org = services['org'].get_org_by_code("A001")
        
        assert org.name == "公司A"
    
    # ==================== 部门管理测试 ====================
    
    def test_create_dept(self, services):
        """测试创建部门"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        
        assert dept.id is not None
        assert dept.name == "技术部"
        assert dept.org_id == org.id
        assert dept.level == 1
    
    def test_create_child_dept(self, services):
        """测试创建子部门"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        parent = services['dept'].create_dept(org_id=org.id, name="技术部")
        child = services['dept'].create_dept(org_id=org.id, name="后端组", parent_id=parent.id)
        
        assert child.parent_id == parent.id
        assert child.level == 2
    
    def test_create_dept_wrong_org_fails(self, services):
        """测试在不同组织下创建子部门失败"""
        org1 = services['org'].create_org(name="公司A", code="A001")
        org2 = services['org'].create_org(name="公司B", code="B001")
        parent = services['dept'].create_dept(org_id=org1.id, name="技术部")
        
        with pytest.raises(ValueError, match="不属于同一组织"):
            services['dept'].create_dept(org_id=org2.id, name="后端组", parent_id=parent.id)
    
    def test_delete_dept_with_employee_fails(self, services):
        """测试删除有员工的部门失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        services['emp'].add_to_dept(emp.id, dept.id)
        
        with pytest.raises(ValueError, match="员工"):
            services['dept'].delete_dept(dept.id)
    
    def test_delete_dept_with_children_fails(self, services):
        """测试删除有子部门的部门失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        parent = services['dept'].create_dept(org_id=org.id, name="技术部")
        services['dept'].create_dept(org_id=org.id, name="后端组", parent_id=parent.id)
        
        with pytest.raises(ValueError, match="子部门"):
            services['dept'].delete_dept(parent.id)
    
    def test_get_dept_tree(self, services):
        """测试获取部门树"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        services['dept'].create_dept(org_id=org.id, name="技术部")
        services['dept'].create_dept(org_id=org.id, name="市场部")
        
        tree = services['dept'].get_dept_tree(org.id)
        
        assert len(tree) == 2
    
    def test_move_dept(self, services):
        """测试移动部门"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        tech = services['dept'].create_dept(org_id=org.id, name="技术部")
        market = services['dept'].create_dept(org_id=org.id, name="市场部")
        backend = services['dept'].create_dept(org_id=org.id, name="后端组", parent_id=tech.id)
        
        # 将后端组移动到市场部下
        services['dept'].move_dept(backend.id, market.id)
        
        # 重新查询验证
        backend = services['dept'].get_dept(backend.id)
        assert backend.parent_id == market.id
    
    # ==================== 员工管理测试 ====================
    
    def test_create_employee(self, services):
        """测试创建员工"""
        emp = services['emp'].create_employee(name="张三", mobile="13800138000")
        
        assert emp.id is not None
        assert emp.name == "张三"
        assert emp.mobile == "13800138000"
    
    def test_update_employee(self, services):
        """测试更新员工"""
        emp = services['emp'].create_employee(name="张三")
        
        updated = services['emp'].update_employee(emp.id, name="李四")
        
        assert updated.name == "李四"
    
    def test_delete_employee(self, services):
        """测试删除员工（软删除）"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        emp_id = emp.id
        services['emp'].add_to_org(emp_id, org.id)
        services['emp'].add_to_dept(emp_id, dept.id)
        
        services['emp'].delete_employee(emp_id)
        
        deleted_emp = services['emp'].get_employee(emp_id)
        if deleted_emp is not None:
            assert deleted_emp.is_deleted == True
    
    # ==================== 员工-组织关联测试 ====================
    
    def test_add_employee_to_org(self, services):
        """测试添加员工到组织"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        emp = services['emp'].create_employee(name="张三")
        
        rel = services['emp'].add_to_org(
            emp.id, org.id,
            emp_no="EMP001",
            position="工程师"
        )
        
        assert rel.emp_no == "EMP001"
        assert rel.position == "工程师"
    
    def test_add_employee_to_org_duplicate_fails(self, services):
        """测试重复添加员工到组织失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        emp = services['emp'].create_employee(name="张三")
        
        services['emp'].add_to_org(emp.id, org.id)
        
        with pytest.raises(ValueError, match="已在该组织中"):
            services['emp'].add_to_org(emp.id, org.id)
    
    def test_remove_employee_from_org(self, services):
        """测试从组织中移除员工"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id, set_as_primary=True)
        services['emp'].add_to_dept(emp.id, dept.id)
        
        services['emp'].remove_from_org(emp.id, org.id)
        
        # 员工-组织关联被删除
        assert len(services['emp'].get_employee_orgs(emp.id)) == 0
        # 员工-部门关联也被删除
        assert len(services['emp'].get_employee_depts(emp.id)) == 0
        # 主组织被清空
        emp = services['emp'].get_employee(emp.id)
        assert emp.primary_org_id is None
    
    # ==================== 员工-部门关联测试 ====================
    
    def test_add_employee_to_dept(self, services):
        """测试添加员工到部门"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        
        rel = services['emp'].add_to_dept(emp.id, dept.id)
        
        assert rel.employee_id == emp.id
        assert rel.dept_id == dept.id
    
    def test_add_employee_to_dept_not_in_org_fails(self, services):
        """测试添加不在组织中的员工到部门失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        
        with pytest.raises(ValueError, match="不在该部门所属的组织中"):
            services['emp'].add_to_dept(emp.id, dept.id)
    
    def test_add_employee_to_dept_duplicate_fails(self, services):
        """测试重复添加员工到部门失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        services['emp'].add_to_dept(emp.id, dept.id)
        
        with pytest.raises(ValueError, match="已在该部门中"):
            services['emp'].add_to_dept(emp.id, dept.id)
    
    # ==================== 主组织/主部门测试 ====================
    
    def test_set_primary_org(self, services):
        """测试设置主组织"""
        org1 = services['org'].create_org(name="公司A", code="A001")
        org2 = services['org'].create_org(name="公司B", code="B001")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org1.id)
        services['emp'].add_to_org(emp.id, org2.id)
        
        services['emp'].set_primary_org(emp.id, org2.id)
        
        emp = services['emp'].get_employee(emp.id)
        assert emp.primary_org_id == org2.id
    
    def test_set_primary_org_not_in_org_fails(self, services):
        """测试设置不在组织中的主组织失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        emp = services['emp'].create_employee(name="张三")
        
        with pytest.raises(ValueError, match="不在该组织中"):
            services['emp'].set_primary_org(emp.id, org.id)
    
    def test_set_primary_dept(self, services):
        """测试设置主部门"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept1 = services['dept'].create_dept(org_id=org.id, name="技术部")
        dept2 = services['dept'].create_dept(org_id=org.id, name="市场部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id, set_as_primary=True)
        services['emp'].add_to_dept(emp.id, dept1.id)
        services['emp'].add_to_dept(emp.id, dept2.id)
        
        services['emp'].set_primary_dept(emp.id, dept2.id)
        
        emp = services['emp'].get_employee(emp.id)
        assert emp.primary_dept_id == dept2.id
    
    def test_set_primary_dept_not_in_dept_fails(self, services):
        """测试设置不在部门中的主部门失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id, set_as_primary=True)
        
        with pytest.raises(ValueError, match="不在该部门中"):
            services['emp'].set_primary_dept(emp.id, dept.id)
    
    def test_set_primary_dept_wrong_org_fails(self, services):
        """测试设置不属于主组织的主部门失败"""
        org1 = services['org'].create_org(name="公司A", code="A001")
        org2 = services['org'].create_org(name="公司B", code="B001")
        dept2 = services['dept'].create_dept(org_id=org2.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org1.id, set_as_primary=True)
        services['emp'].add_to_org(emp.id, org2.id)
        services['emp'].add_to_dept(emp.id, dept2.id)
        
        with pytest.raises(ValueError, match="主部门必须属于主组织"):
            services['emp'].set_primary_dept(emp.id, dept2.id)
    
    # ==================== 部门负责人测试 ====================
    
    def test_add_dept_leader(self, services):
        """测试添加部门负责人"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        services['emp'].add_to_dept(emp.id, dept.id)
        
        leader = services['dept'].add_dept_leader(dept.id, emp.id)
        
        assert leader.dept_id == dept.id
        assert leader.employee_id == emp.id
    
    def test_add_dept_leader_not_in_dept_fails(self, services):
        """测试添加不在部门中的负责人失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        
        with pytest.raises(ValueError, match="不在该部门中"):
            services['dept'].add_dept_leader(dept.id, emp.id)
    
    def test_set_primary_leader(self, services):
        """测试设置主负责人"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp1 = services['emp'].create_employee(name="张三")
        emp2 = services['emp'].create_employee(name="李四")
        services['emp'].add_to_org(emp1.id, org.id)
        services['emp'].add_to_org(emp2.id, org.id)
        services['emp'].add_to_dept(emp1.id, dept.id)
        services['emp'].add_to_dept(emp2.id, dept.id)
        services['dept'].add_dept_leader(dept.id, emp1.id)
        services['dept'].add_dept_leader(dept.id, emp2.id)
        
        services['dept'].set_primary_leader(dept.id, emp2.id)
        
        dept = services['dept'].get_dept(dept.id)
        assert dept.primary_leader_id == emp2.id
    
    def test_set_primary_leader_not_leader_fails(self, services):
        """测试设置非负责人为主负责人失败"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        services['emp'].add_to_dept(emp.id, dept.id)
        
        with pytest.raises(ValueError, match="不是部门负责人"):
            services['dept'].set_primary_leader(dept.id, emp.id)
    
    def test_get_dept_leaders(self, services):
        """测试获取部门负责人列表"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp1 = services['emp'].create_employee(name="张三")
        emp2 = services['emp'].create_employee(name="李四")
        services['emp'].add_to_org(emp1.id, org.id)
        services['emp'].add_to_org(emp2.id, org.id)
        services['emp'].add_to_dept(emp1.id, dept.id)
        services['emp'].add_to_dept(emp2.id, dept.id)
        services['dept'].add_dept_leader(dept.id, emp1.id)
        services['dept'].add_dept_leader(dept.id, emp2.id)
        
        leaders = services['dept'].get_dept_leaders(dept.id)
        
        assert len(leaders) == 2
    
    def test_remove_dept_leader(self, services):
        """测试移除部门负责人"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        services['emp'].add_to_dept(emp.id, dept.id)
        services['dept'].add_dept_leader(dept.id, emp.id, set_as_primary=True)
        
        services['dept'].remove_dept_leader(dept.id, emp.id)
        
        leaders = services['dept'].get_dept_leaders(dept.id)
        assert len(leaders) == 0
        
        dept = services['dept'].get_dept(dept.id)
        assert dept.primary_leader_id is None
    
    # ==================== 便捷方法测试 ====================
    
    def test_org_add_employee_convenience(self, services):
        """测试组织服务的便捷方法：添加员工"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        emp = services['emp'].create_employee(name="张三")
        
        # 通过组织服务添加员工
        rel = services['org'].add_employee(org.id, emp.id, emp_no="EMP001")
        
        assert rel.emp_no == "EMP001"
    
    def test_dept_add_employee_convenience(self, services):
        """测试部门服务的便捷方法：添加员工"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        dept = services['dept'].create_dept(org_id=org.id, name="技术部")
        emp = services['emp'].create_employee(name="张三")
        services['emp'].add_to_org(emp.id, org.id)
        
        # 通过部门服务添加员工
        rel = services['dept'].add_employee(dept.id, emp.id)
        
        assert rel.dept_id == dept.id
    
    def test_org_get_departments_convenience(self, services):
        """测试组织服务的便捷方法：获取部门列表"""
        org = services['org'].create_org(name="测试公司", code="TEST001")
        services['dept'].create_dept(org_id=org.id, name="技术部")
        services['dept'].create_dept(org_id=org.id, name="市场部")
        
        # 通过组织服务获取部门
        depts = services['org'].get_departments(org.id)
        
        assert len(depts) == 2
