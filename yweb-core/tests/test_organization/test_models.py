"""组织管理模块 - 抽象模型测试

测试抽象模型的字段定义和基本功能
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
    ExternalSource,
    Gender,
    EmployeeStatus,
)


# ==================== 测试用具体模型定义 ====================
# 使用 extend_existing=True 避免 pytest 多文件加载时重复定义表的错误

class OrgModelOrganization(AbstractOrganization):
    """测试用组织模型"""
    __tablename__ = "test_org_organization"
    __table_args__ = {'extend_existing': True}


class OrgModelDepartment(AbstractDepartment):
    """测试用部门模型"""
    __tablename__ = "test_org_department"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_org_organization"
    __employee_tablename__ = "test_org_employee"


class OrgModelEmployee(AbstractEmployee):
    """测试用员工模型"""
    __tablename__ = "test_org_employee"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_org_organization"
    __dept_tablename__ = "test_org_department"


class OrgModelEmployeeOrgRel(AbstractEmployeeOrgRel):
    """测试用员工-组织关联模型"""
    __tablename__ = "test_org_emp_org_rel"
    __table_args__ = {'extend_existing': True}
    __employee_tablename__ = "test_org_employee"
    __org_tablename__ = "test_org_organization"


class OrgModelEmployeeDeptRel(AbstractEmployeeDeptRel):
    """测试用员工-部门关联模型"""
    __tablename__ = "test_org_emp_dept_rel"
    __table_args__ = {'extend_existing': True}
    __employee_tablename__ = "test_org_employee"
    __dept_tablename__ = "test_org_department"


class OrgModelDepartmentLeader(AbstractDepartmentLeader):
    """测试用部门负责人模型"""
    __tablename__ = "test_org_dept_leader"
    __table_args__ = {'extend_existing': True}
    __dept_tablename__ = "test_org_department"
    __employee_tablename__ = "test_org_employee"


# ==================== 测试类 ====================

class OrgModelOrganizationModel:
    """组织模型测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_organization(self):
        """测试创建组织"""
        org = OrgModelOrganization(
            name="测试公司",
            code="TEST001"
        )
        org.save(commit=True)
        
        assert org.id is not None
        assert org.name == "测试公司"
        assert org.code == "TEST001"
    
    def test_organization_has_base_fields(self):
        """测试组织有基础字段"""
        org = OrgModelOrganization(name="Test", code="T001")
        org.save(commit=True)
        
        # 继承自 BaseModel 的字段
        assert hasattr(org, 'id')
        assert hasattr(org, 'name')
        assert hasattr(org, 'code')
        assert hasattr(org, 'note')
        assert hasattr(org, 'caption')
        assert hasattr(org, 'created_at')
        assert hasattr(org, 'updated_at')
        assert hasattr(org, 'deleted_at')
        assert hasattr(org, 'ver')
    
    def test_organization_external_fields(self):
        """测试组织外部系统字段"""
        org = OrgModelOrganization(
            name="外部同步公司",
            code="EXT001",
            external_source=ExternalSource.WECHAT_WORK.value,
            external_corp_id="ww123456789"
        )
        org.save(commit=True)
        
        assert org.external_source == ExternalSource.WECHAT_WORK.value
        assert org.external_corp_id == "ww123456789"
    
    def test_organization_is_external(self):
        """测试判断是否为外部组织"""
        # 本地组织
        local_org = OrgModelOrganization(name="本地公司", code="LOCAL001")
        local_org.save(commit=True)
        assert local_org.is_external() == False
        
        # 外部组织
        external_org = OrgModelOrganization(
            name="外部公司",
            code="EXT001",
            external_source=ExternalSource.FEISHU.value
        )
        external_org.save(commit=True)
        assert external_org.is_external() == True
    
    def test_organization_external_config(self):
        """测试外部配置的JSON存取"""
        org = OrgModelOrganization(name="Test", code="T001")
        org.save(commit=True)
        
        # 设置配置
        config = {"app_id": "123", "app_secret": "secret"}
        org.set_external_config_dict(config)
        org.save(commit=True)
        
        # 读取配置
        loaded_config = org.get_external_config_dict()
        assert loaded_config["app_id"] == "123"
        assert loaded_config["app_secret"] == "secret"


class OrgModelEmployeeModel:
    """员工模型测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_employee(self):
        """测试创建员工"""
        emp = OrgModelEmployee(
            name="张三",
            mobile="13800138000",
            email="zhangsan@example.com"
        )
        emp.save(commit=True)
        
        assert emp.id is not None
        assert emp.name == "张三"
        assert emp.mobile == "13800138000"
    
    def test_employee_gender(self):
        """测试员工性别"""
        emp = OrgModelEmployee(name="李四", gender=Gender.MALE.value)
        emp.save(commit=True)
        
        assert emp.is_male() == True
        assert emp.is_female() == False
        assert emp.get_gender_display() == "男"
    
    def test_employee_primary_fields(self):
        """测试员工主归属字段"""
        # 先创建组织和部门
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        dept = OrgModelDepartment(name="Test Dept", org_id=org.id)
        dept.save(commit=True)
        dept.update_path_and_level()
        dept.save(commit=True)
        
        # 创建员工并设置主归属
        emp = OrgModelEmployee(
            name="王五",
            primary_org_id=org.id,
            primary_dept_id=dept.id
        )
        emp.save(commit=True)
        
        assert emp.primary_org_id == org.id
        assert emp.primary_dept_id == dept.id


class OrgModelEmployeeOrgRelModel:
    """员工-组织关联模型测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_emp_org_rel(self):
        """测试创建员工-组织关联"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        emp = OrgModelEmployee(name="Test Emp")
        emp.save(commit=True)
        
        rel = OrgModelEmployeeOrgRel(
            employee_id=emp.id,
            org_id=org.id,
            emp_no="EMP001",
            position="工程师",
            status=EmployeeStatus.ACTIVE.value
        )
        rel.save(commit=True)
        
        assert rel.id is not None
        assert rel.emp_no == "EMP001"
        assert rel.is_active() == True
    
    def test_emp_org_rel_status(self):
        """测试员工-组织关联状态"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        emp = OrgModelEmployee(name="Test Emp")
        emp.save(commit=True)
        
        rel = OrgModelEmployeeOrgRel(
            employee_id=emp.id,
            org_id=org.id,
            status=EmployeeStatus.RESIGNED.value
        )
        rel.save(commit=True)
        
        assert rel.is_active() == False
        assert rel.is_resigned() == True
        assert rel.get_status_display() == "离职"
    
    def test_emp_org_rel_external_config(self):
        """测试员工-组织关联的外部配置"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        emp = OrgModelEmployee(name="Test Emp")
        emp.save(commit=True)
        
        rel = OrgModelEmployeeOrgRel(
            employee_id=emp.id,
            org_id=org.id,
            external_user_id="wx_user_001"
        )
        rel.save(commit=True)
        
        # 设置扩展配置
        config = {"is_leader_in_dept": [1, 2], "alias": "小张"}
        rel.set_external_config_dict(config)
        rel.save(commit=True)
        
        # 读取配置
        loaded = rel.get_external_config_dict()
        assert loaded["is_leader_in_dept"] == [1, 2]


class OrgModelDepartmentModel:
    """部门模型测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_department(self):
        """测试创建部门"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        dept = OrgModelDepartment(
            name="技术部",
            org_id=org.id
        )
        dept.save(commit=True)  # 先保存获取 id
        dept.update_path_and_level()
        dept.save(commit=True)
        
        assert dept.id is not None
        assert dept.name == "技术部"
        assert dept.level == 1  # 根部门
        assert dept.is_root_department() == True
    
    def test_department_hierarchy(self):
        """测试部门层级结构"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        # 创建父部门
        parent_dept = OrgModelDepartment(name="研发中心", org_id=org.id)
        parent_dept.save(commit=True)
        parent_dept.update_path_and_level()
        parent_dept.save(commit=True)
        
        # 创建子部门
        child_dept = OrgModelDepartment(
            name="后端组",
            org_id=org.id,
            parent_id=parent_dept.id
        )
        child_dept.save(commit=True)
        child_dept.update_path_and_level()
        child_dept.save(commit=True)
        
        assert child_dept.level == 2
        assert child_dept.parent_id == parent_dept.id
        assert child_dept.path.startswith(parent_dept.path.rstrip('/'))
    
    def test_department_full_name(self):
        """测试部门完整名称"""
        org = OrgModelOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        
        # 创建三级部门结构
        dept1 = OrgModelDepartment(name="总公司", org_id=org.id)
        dept1.save(commit=True)
        dept1.update_path_and_level()
        dept1.save(commit=True)
        
        dept2 = OrgModelDepartment(name="技术部", org_id=org.id, parent_id=dept1.id)
        dept2.save(commit=True)
        dept2.update_path_and_level()
        dept2.save(commit=True)
        
        dept3 = OrgModelDepartment(name="研发组", org_id=org.id, parent_id=dept2.id)
        dept3.save(commit=True)
        dept3.update_path_and_level()
        dept3.save(commit=True)
        
        full_name = dept3.get_full_name()
        assert "总公司" in full_name
        assert "技术部" in full_name
        assert "研发组" in full_name


class TestEnums:
    """枚举测试"""
    
    def test_external_source_values(self):
        """测试外部来源枚举值"""
        assert ExternalSource.NONE.value == "none"
        assert ExternalSource.WECHAT_WORK.value == "wechat_work"
        assert ExternalSource.FEISHU.value == "feishu"
        assert ExternalSource.DINGTALK.value == "dingtalk"
        assert ExternalSource.CUSTOM.value == "custom"
    
    def test_employee_status_values(self):
        """测试员工状态枚举值（按生命周期排列）"""
        assert EmployeeStatus.RESIGNED == -1
        assert EmployeeStatus.SUSPENDED == 0
        assert EmployeeStatus.PENDING == 1
        assert EmployeeStatus.PROBATION == 2
        assert EmployeeStatus.ACTIVE == 3
    
    def test_gender_values(self):
        """测试性别枚举值"""
        assert Gender.UNKNOWN == 0
        assert Gender.MALE == 1
        assert Gender.FEMALE == 2
