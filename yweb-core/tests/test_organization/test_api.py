"""
组织管理模块 - API 测试

测试组织管理 API 的功能，包括：
1. Schema 的 extra="allow" 配置
2. 扩展字段在响应中的传递
3. 响应构建器的工作方式
4. HTTP 端点测试（CRUD 操作）
"""

import pytest
from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from fastapi.testclient import TestClient

from sqlalchemy import Integer, String, Numeric
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import BaseModel, CoreModel
from yweb.organization import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
)
from yweb.organization.schemas import (
    OrganizationResponse,
    DepartmentResponse,
    DepartmentTreeNode,
    EmployeeResponse,
    EmployeeDetailResponse,
)
from yweb.organization.api import (
    create_organization_crud_router,
    create_department_crud_router,
    create_employee_crud_router,
)
from yweb.organization.services import (
    BaseOrganizationService,
    BaseDepartmentService,
    BaseEmployeeService,
)


# ==================== 扩展模型定义（模拟用户场景） ====================
# 注意：类名不以 Test 开头，避免 pytest 误认为是测试类

class SampleOrganization(AbstractOrganization):
    """扩展的组织模型"""
    __tablename__ = "test_api_org"
    __table_args__ = {'extend_existing': True}
    
    # 用户扩展字段
    license_no: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="营业执照号"
    )


class SampleDepartment(AbstractDepartment):
    """扩展的部门模型"""
    __tablename__ = "test_api_dept"
    __org_tablename__ = "test_api_org"
    __employee_tablename__ = "test_api_emp"
    __table_args__ = {'extend_existing': True}
    
    # 用户扩展字段
    budget: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="部门预算"
    )


class SampleEmployee(AbstractEmployee):
    """扩展的员工模型"""
    __tablename__ = "test_api_emp"
    __org_tablename__ = "test_api_org"
    __dept_tablename__ = "test_api_dept"
    __table_args__ = {'extend_existing': True}
    
    # 用户扩展字段
    id_card: Mapped[Optional[str]] = mapped_column(
        String(18),
        nullable=True,
        comment="身份证号"
    )
    
    work_years: Mapped[int] = mapped_column(
        Integer,
        default=0,
        comment="工龄"
    )


class SampleEmployeeOrgRel(AbstractEmployeeOrgRel):
    """员工-组织关联"""
    __tablename__ = "test_api_emp_org"
    __employee_tablename__ = "test_api_emp"
    __org_tablename__ = "test_api_org"
    __table_args__ = {'extend_existing': True}


class SampleEmployeeDeptRel(AbstractEmployeeDeptRel):
    """员工-部门关联"""
    __tablename__ = "test_api_emp_dept"
    __employee_tablename__ = "test_api_emp"
    __dept_tablename__ = "test_api_dept"
    __table_args__ = {'extend_existing': True}


class SampleDeptLeader(AbstractDepartmentLeader):
    """部门负责人"""
    __tablename__ = "test_api_dept_leader"
    __dept_tablename__ = "test_api_dept"
    __employee_tablename__ = "test_api_emp"
    __table_args__ = {'extend_existing': True}


# ==================== 服务类实现（用于测试 API） ====================

class SampleDeptService(BaseDepartmentService):
    """测试用部门服务"""
    dept_model = SampleDepartment
    dept_leader_model = SampleDeptLeader


class SampleEmpService(BaseEmployeeService):
    """测试用员工服务"""
    employee_model = SampleEmployee
    dept_model = SampleDepartment
    emp_org_rel_model = SampleEmployeeOrgRel
    emp_dept_rel_model = SampleEmployeeDeptRel
    dept_leader_model = SampleDeptLeader


class SampleOrgService(BaseOrganizationService):
    """测试用组织服务"""
    org_model = SampleOrganization
    
    def __init__(self):
        super().__init__()
        # 初始化子服务
        self.dept_service = SampleDeptService()
        self.employee_service = SampleEmpService()


# ==================== Schema 测试（不需要数据库） ====================

class TestSchemaExtraAllow:
    """测试 Schema 的 extra='allow' 配置"""
    
    def test_organization_response_accepts_extra_fields(self):
        """测试 OrganizationResponse 接受额外字段"""
        data = {
            "id": 1,
            "name": "测试公司",
            "code": "TEST",
            "note": "备注",
            "caption": None,
            "external_source": None,
            "external_corp_id": None,
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "license_no": "91110000000000000X",
        }
        
        response = OrganizationResponse.from_dict(data)
        dumped = response.model_dump()
        
        # 验证核心字段
        assert dumped["name"] == "测试公司"
        assert dumped["code"] == "TEST"
        
        # 验证扩展字段
        assert dumped["license_no"] == "91110000000000000X"
    
    def test_department_response_accepts_extra_fields(self):
        """测试 DepartmentResponse 接受额外字段"""
        data = {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "code": "TECH",
            "parent_id": None,
            "path": "/1/",
            "level": 1,
            "sort_order": 0,
            "primary_leader_id": None,
            "note": None,
            "is_active": True,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "budget": 1000000,
        }
        
        response = DepartmentResponse.from_dict(data)
        dumped = response.model_dump()
        
        # 验证核心字段
        assert dumped["name"] == "技术部"
        assert dumped["org_id"] == 1
        
        # 验证扩展字段
        assert dumped["budget"] == 1000000
    
    def test_department_tree_node_accepts_extra_fields(self):
        """测试 DepartmentTreeNode 接受额外字段"""
        data = {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "code": "TECH",
            "parent_id": None,
            "level": 1,
            "sort_order": 0,
            "children": [],
            # 扩展字段
            "budget": 1000000,
            "employee_count": 50,
        }
        
        response = DepartmentTreeNode(**data)
        dumped = response.model_dump()
        
        assert dumped["budget"] == 1000000
        assert dumped["employee_count"] == 50
    
    def test_employee_response_accepts_extra_fields(self):
        """测试 EmployeeResponse 接受额外字段"""
        data = {
            "id": 1,
            "name": "张三",
            "mobile": "13800138000",
            "email": "zhangsan@test.com",
            "gender": 1,
            "avatar": None,
            "is_senior": False,
            "primary_org_id": 1,
            "primary_dept_id": 1,
            "account_status": 1,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "id_card": "110101199001011234",
            "work_years": 5,
        }
        
        response = EmployeeResponse.from_dict(data)
        dumped = response.model_dump()
        
        # 验证核心字段
        assert dumped["name"] == "张三"
        assert dumped["mobile"] == "13800138000"
        
        # 验证扩展字段
        assert dumped["id_card"] == "110101199001011234"
        assert dumped["work_years"] == 5
    
    def test_employee_detail_response_with_relations(self):
        """测试 EmployeeDetailResponse 包含关联信息"""
        data = {
            "id": 1,
            "name": "张三",
            "mobile": "13800138000",
            "email": "zhangsan@test.com",
            "gender": 1,
            "avatar": None,
            "is_senior": False,
            "primary_org_id": 1,
            "primary_dept_id": 1,
            "account_status": 1,
            "created_at": datetime.now(),
            "updated_at": None,
            # 扩展字段
            "id_card": "110101199001011234",
            # 关联信息
            "organizations": [
                {"org_id": 1, "org_name": "总公司", "emp_no": "EMP001", "position": "工程师", "status": 3, "is_primary": True}
            ],
            "departments": [
                {"dept_id": 1, "dept_name": "技术部", "is_primary": True}
            ],
        }
        
        response = EmployeeDetailResponse.from_dict(data)
        dumped = response.model_dump()
        
        # 验证关联信息
        assert len(dumped["organizations"]) == 1
        assert dumped["organizations"][0]["org_name"] == "总公司"
        assert len(dumped["departments"]) == 1
        assert dumped["departments"][0]["dept_name"] == "技术部"
        
        # 验证扩展字段
        assert dumped["id_card"] == "110101199001011234"


# ==================== to_dict() 集成测试 ====================

class TestToDictWithExtendedFields:
    """测试 to_dict() 包含扩展字段（需要数据库）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_organization_to_dict_includes_extended_fields(self):
        """测试 Organization 的 to_dict() 包含扩展字段"""
        org = SampleOrganization(
            name="测试公司",
            code="TEST",
            license_no="91110000000000000X",
        )
        org.add(commit=True)
        
        data = org.to_dict()
        
        # 验证核心字段
        assert data["name"] == "测试公司"
        assert data["code"] == "TEST"
        
        # 验证扩展字段
        assert data["license_no"] == "91110000000000000X"
    
    def test_department_to_dict_includes_extended_fields(self):
        """测试 Department 的 to_dict() 包含扩展字段"""
        # 先创建组织
        org = SampleOrganization(name="测试公司", code="TEST")
        org.add(commit=True)
        
        dept = SampleDepartment(
            org_id=org.id,
            name="技术部",
            budget=1000000,
        )
        dept.add(commit=True)
        
        data = dept.to_dict()
        
        # 验证核心字段
        assert data["name"] == "技术部"
        assert data["org_id"] == org.id
        
        # 验证扩展字段
        assert data["budget"] == 1000000
    
    def test_employee_to_dict_includes_extended_fields(self):
        """测试 Employee 的 to_dict() 包含扩展字段"""
        emp = SampleEmployee(
            name="张三",
            mobile="13800138000",
            id_card="110101199001011234",
            work_years=5,
        )
        emp.add(commit=True)
        
        data = emp.to_dict()
        
        # 验证核心字段
        assert data["name"] == "张三"
        assert data["mobile"] == "13800138000"
        
        # 验证扩展字段
        assert data["id_card"] == "110101199001011234"
        assert data["work_years"] == 5


# ==================== API 流程集成测试 ====================

class TestAPIWithExtendedModel:
    """测试完整的 API 流程：模型 -> to_dict() -> Schema -> 响应"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_organization_api_response(self):
        """测试组织 API 响应包含扩展字段"""
        org = SampleOrganization(
            name="API测试公司",
            code="API_TEST",
            license_no="91110000000000000X",
        )
        org.add(commit=True)
        
        # 模拟 API 响应构建（使用 from_dict 以包含扩展字段）
        response_data = OrganizationResponse.from_dict(org.to_dict()).model_dump()
        
        assert response_data["name"] == "API测试公司"
        assert response_data["license_no"] == "91110000000000000X"
    
    def test_employee_api_response(self):
        """测试员工 API 响应包含扩展字段"""
        emp = SampleEmployee(
            name="API测试员工",
            mobile="13900139000",
            id_card="110101199001011234",
            work_years=3,
        )
        emp.add(commit=True)
        
        # 模拟 API 响应构建（使用 from_dict 以包含扩展字段）
        response_data = EmployeeResponse.from_dict(emp.to_dict()).model_dump()
        
        assert response_data["name"] == "API测试员工"
        assert response_data["id_card"] == "110101199001011234"
        assert response_data["work_years"] == 3
    
    def test_list_api_includes_extended_fields(self):
        """测试列表 API 响应包含扩展字段"""
        # 创建多个组织
        for i in range(3):
            org = SampleOrganization(
                name=f"公司{i}",
                code=f"ORG{i}",
                license_no=f"911100000000000{i}X",
            )
            org.add(commit=True)
        
        # 模拟列表 API 响应（使用 from_dict 以包含扩展字段）
        orgs = SampleOrganization.query.all()
        items = [OrganizationResponse.from_dict(o.to_dict()).model_dump() for o in orgs]
        
        assert len(items) == 3
        for i, item in enumerate(items):
            assert item["name"] == f"公司{i}"
            assert item["license_no"] == f"911100000000000{i}X"


# ==================== 模型配置验证 ====================

class TestModelConfig:
    """验证 Schema 的 model_config 配置"""
    
    def test_organization_response_config(self):
        """验证 OrganizationResponse 配置"""
        assert hasattr(OrganizationResponse, 'model_config')
        config = OrganizationResponse.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True
    
    def test_department_response_config(self):
        """验证 DepartmentResponse 配置"""
        assert hasattr(DepartmentResponse, 'model_config')
        config = DepartmentResponse.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True
    
    def test_employee_response_config(self):
        """验证 EmployeeResponse 配置"""
        assert hasattr(EmployeeResponse, 'model_config')
        config = EmployeeResponse.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True
    
    def test_department_tree_node_config(self):
        """验证 DepartmentTreeNode 配置"""
        assert hasattr(DepartmentTreeNode, 'model_config')
        config = DepartmentTreeNode.model_config
        assert config.get('extra') == 'allow'
        assert config.get('from_attributes') is True


# ==================== 新功能测试：include 参数 ====================

class TestIncludeParameter:
    """测试 include 参数机制"""
    
    def test_include_options_parsing(self):
        """测试 include 参数解析"""
        # 模拟 API 中的解析逻辑
        include = "org_name,dept_name,employee_count"
        include_options = set(include.split(","))
        
        assert "org_name" in include_options
        assert "dept_name" in include_options
        assert "employee_count" in include_options
        assert len(include_options) == 3
    
    def test_include_options_empty(self):
        """测试空 include 参数"""
        include = None
        include_options = set()
        if include:
            include_options = set(include.split(","))
        
        assert len(include_options) == 0
    
    def test_employee_response_with_include_options(self):
        """测试员工响应根据 include 选项添加字段"""
        # 模拟 _build_employee_response 的逻辑
        base_data = {
            "id": 1,
            "name": "张三",
            "mobile": "13800138000",
            "primary_org_id": 1,
            "primary_dept_id": 1,
            "account_status": 1,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        
        include_options = {"org_name", "dept_name"}
        
        # 模拟添加关联数据
        if "org_name" in include_options:
            base_data["primary_org_name"] = "总公司"
        if "dept_name" in include_options:
            base_data["primary_dept_name"] = "技术部"
        
        response = EmployeeResponse.from_dict(base_data)
        dumped = response.model_dump()
        
        assert dumped["primary_org_name"] == "总公司"
        assert dumped["primary_dept_name"] == "技术部"
    
    def test_department_tree_node_with_include_options(self):
        """测试部门树节点根据 include 选项添加字段"""
        base_data = {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "code": "TECH",
            "parent_id": None,
            "level": 1,
            "sort_order": 0,
            "children": [],
        }
        
        include_options = {"employee_count", "full_name", "primary_leader_name"}
        
        # 模拟添加附加信息
        if "employee_count" in include_options:
            base_data["employee_count"] = 50
        if "full_name" in include_options:
            base_data["full_name"] = "总公司 > 技术部"
        if "primary_leader_name" in include_options:
            base_data["primary_leader_name"] = "张经理"
        
        response = DepartmentTreeNode(**base_data)
        dumped = response.model_dump()
        
        assert dumped["employee_count"] == 50
        assert dumped["full_name"] == "总公司 > 技术部"
        assert dumped["primary_leader_name"] == "张经理"


# ==================== 新功能测试：响应构建钩子 ====================

class TestResponseBuilderHook:
    """测试响应构建钩子函数"""
    
    def test_custom_employee_response_builder(self):
        """测试自定义员工响应构建器"""
        # 定义自定义构建器
        def my_employee_builder(emp_mock, base_data: dict) -> dict:
            base_data["avatar_url"] = f"https://cdn.example.com/{base_data.get('avatar', 'default.png')}"
            base_data["display_name"] = f"{base_data['name']} ({base_data.get('emp_no', 'N/A')})"
            return base_data
        
        # 模拟员工数据
        base_data = {
            "id": 1,
            "name": "张三",
            "avatar": "user123.jpg",
            "emp_no": "EMP001",
            "mobile": "13800138000",
            "account_status": 1,
            "created_at": datetime.now(),
            "updated_at": None,
        }
        
        # 应用构建器
        result = my_employee_builder(None, base_data)
        
        assert result["avatar_url"] == "https://cdn.example.com/user123.jpg"
        assert result["display_name"] == "张三 (EMP001)"
    
    def test_custom_tree_node_builder(self):
        """测试自定义部门树节点构建器"""
        # 定义自定义构建器
        def my_tree_node_builder(dept_mock, base_data: dict) -> dict:
            base_data["budget_display"] = f"¥{base_data.get('budget', 0):,}"
            base_data["is_root"] = base_data.get("parent_id") is None
            base_data["custom_tag"] = "important" if base_data.get("level") == 1 else "normal"
            return base_data
        
        # 模拟部门数据
        base_data = {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "parent_id": None,
            "level": 1,
            "budget": 1000000,
        }
        
        # 应用构建器
        result = my_tree_node_builder(None, base_data)
        
        assert result["budget_display"] == "¥1,000,000"
        assert result["is_root"] is True
        assert result["custom_tag"] == "important"
    
    def test_builder_preserves_original_fields(self):
        """测试构建器保留原始字段"""
        def simple_builder(obj, data: dict) -> dict:
            data["extra_field"] = "added"
            return data
        
        original = {
            "id": 1,
            "name": "测试",
            "code": "TEST",
        }
        
        result = simple_builder(None, original.copy())
        
        # 原始字段应该保留
        assert result["id"] == 1
        assert result["name"] == "测试"
        assert result["code"] == "TEST"
        # 新字段应该添加
        assert result["extra_field"] == "added"


# ==================== 新功能测试：部门树构建 ====================

class SampleDepartmentTreeBuilding:
    """测试部门树构建逻辑"""
    
    def test_build_tree_basic(self):
        """测试基本的树构建"""
        # 模拟平铺的部门数据
        class MockDept:
            def __init__(self, id, name, parent_id, level):
                self.id = id
                self.name = name
                self.parent_id = parent_id
                self.level = level
            
            def to_dict(self):
                return {
                    "id": self.id,
                    "name": self.name,
                    "parent_id": self.parent_id,
                    "level": self.level,
                }
        
        depts = [
            MockDept(1, "技术部", None, 1),
            MockDept(2, "前端组", 1, 2),
            MockDept(3, "后端组", 1, 2),
            MockDept(4, "销售部", None, 1),
        ]
        
        # 模拟 _build_tree 逻辑
        def build_tree(depts, parent_id=None):
            result = []
            for d in depts:
                if d.parent_id == parent_id:
                    node = d.to_dict()
                    node["children"] = build_tree(depts, d.id)
                    result.append(node)
            return result
        
        tree = build_tree(depts)
        
        # 验证树结构
        assert len(tree) == 2  # 两个根节点
        
        tech_dept = next(n for n in tree if n["name"] == "技术部")
        assert len(tech_dept["children"]) == 2  # 两个子部门
        
        sales_dept = next(n for n in tree if n["name"] == "销售部")
        assert len(sales_dept["children"]) == 0  # 无子部门
    
    def test_build_tree_with_include_options(self):
        """测试带 include 选项的树构建"""
        class MockDept:
            def __init__(self, id, name, parent_id, employee_count=0):
                self.id = id
                self.name = name
                self.parent_id = parent_id
                self.employee_count = employee_count
            
            def to_dict(self):
                return {"id": self.id, "name": self.name, "parent_id": self.parent_id}
        
        depts = [
            MockDept(1, "技术部", None, 50),
            MockDept(2, "前端组", 1, 20),
        ]
        
        def build_tree_node(dept, include_options):
            node = dept.to_dict()
            if "employee_count" in include_options:
                node["employee_count"] = dept.employee_count
            return node
        
        def build_tree(depts, parent_id=None, include_options=None):
            include_options = include_options or set()
            result = []
            for d in depts:
                if d.parent_id == parent_id:
                    node = build_tree_node(d, include_options)
                    node["children"] = build_tree(depts, d.id, include_options)
                    result.append(node)
            return result
        
        # 不带 include
        tree_basic = build_tree(depts)
        assert "employee_count" not in tree_basic[0]
        
        # 带 include
        tree_with_count = build_tree(depts, include_options={"employee_count"})
        assert tree_with_count[0]["employee_count"] == 50
        assert tree_with_count[0]["children"][0]["employee_count"] == 20
    
    def test_tree_preserves_extended_fields(self):
        """测试树构建保留扩展字段"""
        # 模拟扩展字段的部门数据
        dept_data = {
            "id": 1,
            "org_id": 1,
            "name": "技术部",
            "code": "TECH",
            "parent_id": None,
            "level": 1,
            "sort_order": 0,
            # 扩展字段
            "budget": 1000000,
            "cost_center": "CC001",
        }
        
        # 模拟树节点构建（保留扩展字段）
        node = {
            "id": dept_data["id"],
            "name": dept_data["name"],
            "parent_id": dept_data["parent_id"],
            "level": dept_data["level"],
            "children": [],
        }
        
        # 保留扩展字段
        for key, value in dept_data.items():
            if key not in node:
                node[key] = value
        
        # 使用 Schema 包装
        response = DepartmentTreeNode(**node)
        dumped = response.model_dump()
        
        # 验证扩展字段保留
        assert dumped["budget"] == 1000000
        assert dumped["cost_center"] == "CC001"
    
    def test_deeply_nested_tree(self):
        """测试深层嵌套的树结构"""
        class MockDept:
            def __init__(self, id, name, parent_id, level):
                self.id = id
                self.name = name
                self.parent_id = parent_id
                self.level = level
            
            def to_dict(self):
                return {
                    "id": self.id,
                    "name": self.name,
                    "parent_id": self.parent_id,
                    "level": self.level,
                }
        
        # 创建 5 层嵌套结构
        depts = [
            MockDept(1, "一级部门", None, 1),
            MockDept(2, "二级部门", 1, 2),
            MockDept(3, "三级部门", 2, 3),
            MockDept(4, "四级部门", 3, 4),
            MockDept(5, "五级部门", 4, 5),
        ]
        
        def build_tree(depts, parent_id=None):
            result = []
            for d in depts:
                if d.parent_id == parent_id:
                    node = d.to_dict()
                    node["children"] = build_tree(depts, d.id)
                    result.append(node)
            return result
        
        tree = build_tree(depts)
        
        # 验证嵌套深度
        assert len(tree) == 1
        current = tree[0]
        for i in range(4):  # 遍历 4 层子节点
            assert len(current["children"]) == 1
            current = current["children"][0]
        
        # 最深层无子节点
        assert current["name"] == "五级部门"
        assert len(current["children"]) == 0


# ==================== HTTP 端点测试 ====================

class TestOrganizationAPIEndpoints:
    """测试组织管理 HTTP API 端点"""
    
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
    def org_app(self):
        """创建包含组织 API 的测试应用"""
        app = FastAPI()
        
        # 创建组织服务实例
        org_service = SampleOrgService()
        
        router = create_organization_crud_router(SampleOrganization, org_service=org_service)
        app.include_router(router, prefix="/api/org")
        return app
    
    @pytest.fixture
    def org_client(self, org_app):
        """组织 API 测试客户端"""
        return TestClient(org_app)
    
    def test_create_organization(self, org_client):
        """测试创建组织"""
        response = org_client.post("/api/org/create", json={
            "name": "测试公司",
            "code": "TEST001"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "测试公司"
        assert data["data"]["code"] == "TEST001"
        assert data["data"]["id"] is not None
    
    def test_get_organization(self, org_client):
        """测试获取组织详情"""
        # 先创建
        create_resp = org_client.post("/api/org/create", json={
            "name": "查询测试公司",
            "code": "QUERY001"
        })
        org_id = create_resp.json()["data"]["id"]
        
        # 再查询
        response = org_client.get(f"/api/org/get?org_id={org_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "查询测试公司"
    
    def test_list_organizations(self, org_client):
        """测试获取组织列表"""
        # 创建多个组织
        for i in range(3):
            org_client.post("/api/org/create", json={
                "name": f"列表测试公司{i}",
                "code": f"LIST{i:03d}"
            })
        
        # 获取列表
        response = org_client.get("/api/org/list")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["total_records"] >= 3
        assert len(data["data"]["rows"]) >= 3
    
    def test_update_organization(self, org_client):
        """测试更新组织"""
        # 先创建
        create_resp = org_client.post("/api/org/create", json={
            "name": "待更新公司",
            "code": "UPDATE001"
        })
        org_id = create_resp.json()["data"]["id"]
        
        # 更新
        response = org_client.post(f"/api/org/update?org_id={org_id}", json={
            "name": "已更新公司"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "已更新公司"
    
    def test_get_nonexistent_organization(self, org_client):
        """测试获取不存在的组织"""
        response = org_client.get("/api/org/get?org_id=99999")
        
        assert response.status_code == 404
        data = response.json()
        assert data["status"] == "error"


class TestEmployeeAPIEndpoints:
    """测试员工管理 HTTP API 端点"""
    
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
    def emp_app(self):
        """创建包含员工 API 的测试应用"""
        app = FastAPI()
        
        # 创建组织服务实例
        org_service = SampleOrgService()
        
        router = create_employee_crud_router(
            employee_model=SampleEmployee,
            org_model=SampleOrganization,
            dept_model=SampleDepartment,
            emp_org_rel_model=SampleEmployeeOrgRel,
            emp_dept_rel_model=SampleEmployeeDeptRel,
            dept_leader_model=SampleDeptLeader,
            org_service=org_service,
        )
        app.include_router(router, prefix="/api/emp")
        return app
    
    @pytest.fixture
    def emp_client(self, emp_app):
        """员工 API 测试客户端"""
        return TestClient(emp_app)
    
    def test_create_employee(self, emp_client):
        """测试创建员工"""
        response = emp_client.post("/api/emp/create", json={
            "name": "张三",
            "mobile": "13800138001"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "张三"
        assert data["data"]["mobile"] == "13800138001"
    
    def test_get_employee(self, emp_client):
        """测试获取员工详情"""
        # 先创建
        create_resp = emp_client.post("/api/emp/create", json={
            "name": "李四",
            "mobile": "13800138002"
        })
        emp_id = create_resp.json()["data"]["id"]
        
        # 再查询
        response = emp_client.get(f"/api/emp/get?employee_id={emp_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "李四"
    
    def test_list_employees(self, emp_client):
        """测试获取员工列表"""
        # 创建多个员工
        for i in range(3):
            emp_client.post("/api/emp/create", json={
                "name": f"员工{i}",
                "mobile": f"1380013800{i}"
            })
        
        # 获取列表
        response = emp_client.get("/api/emp/list")
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["total_records"] >= 3
    
    def test_update_employee(self, emp_client):
        """测试更新员工"""
        # 先创建
        create_resp = emp_client.post("/api/emp/create", json={
            "name": "待更新员工",
            "mobile": "13800138099"
        })
        emp_id = create_resp.json()["data"]["id"]
        
        # 更新
        response = emp_client.post(f"/api/emp/update?employee_id={emp_id}", json={
            "name": "已更新员工"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["data"]["name"] == "已更新员工"
    
    def test_delete_employee(self, emp_client):
        """测试删除员工"""
        # 先创建
        create_resp = emp_client.post("/api/emp/create", json={
            "name": "待删除员工",
            "mobile": "13800138088"
        })
        emp_id = create_resp.json()["data"]["id"]
        
        # 删除
        response = emp_client.post(f"/api/emp/delete?employee_id={emp_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["id"] == emp_id


class TestDepartmentAPIEndpoints:
    """测试部门管理 HTTP API 端点"""
    
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
    def dept_app(self):
        """创建包含部门 API 的测试应用"""
        app = FastAPI()
        
        # 创建组织服务实例
        org_service = SampleOrgService()
        
        # 先添加组织 API
        org_router = create_organization_crud_router(SampleOrganization, org_service=org_service)
        app.include_router(org_router, prefix="/api/org")
        
        # 再添加部门 API
        dept_router = create_department_crud_router(
            SampleDepartment,
            SampleOrganization,
            SampleDeptLeader,
            SampleEmployee,
            SampleEmployeeDeptRel,
            org_service=org_service,
        )
        app.include_router(dept_router, prefix="/api/dept")
        return app
    
    @pytest.fixture
    def dept_client(self, dept_app):
        """部门 API 测试客户端"""
        return TestClient(dept_app)
    
    def test_create_department(self, dept_client):
        """测试创建部门"""
        # 先创建组织
        org_resp = dept_client.post("/api/org/create", json={
            "name": "测试公司",
            "code": "DEPT_TEST"
        })
        org_id = org_resp.json()["data"]["id"]
        
        # 创建部门
        response = dept_client.post("/api/dept/create", json={
            "org_id": org_id,
            "name": "技术部"
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["data"]["name"] == "技术部"
        assert data["data"]["org_id"] == org_id
    
    def test_get_department_tree(self, dept_client):
        """测试获取部门树"""
        # 先创建组织
        org_resp = dept_client.post("/api/org/create", json={
            "name": "树测试公司",
            "code": "TREE_TEST"
        })
        org_id = org_resp.json()["data"]["id"]
        
        # 创建根部门
        root_resp = dept_client.post("/api/dept/create", json={
            "org_id": org_id,
            "name": "总经办"
        })
        root_id = root_resp.json()["data"]["id"]
        
        # 创建子部门
        dept_client.post("/api/dept/create", json={
            "org_id": org_id,
            "name": "技术部",
            "parent_id": root_id
        })
        
        # 获取部门树
        response = dept_client.get(f"/api/dept/tree?org_id={org_id}")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert isinstance(data["data"], list)


class TestEmployeeRelationAPIEndpoints:
    """测试员工关联操作 API 端点（组织/部门关联）"""
    
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
    def full_app(self):
        """创建包含完整组织架构 API 的测试应用"""
        app = FastAPI()
        
        # 创建组织服务实例
        org_service = SampleOrgService()
        
        # 组织 API
        org_router = create_organization_crud_router(SampleOrganization, org_service=org_service)
        app.include_router(org_router, prefix="/api/org")
        
        # 部门 API
        dept_router = create_department_crud_router(
            SampleDepartment,
            SampleOrganization,
            SampleDeptLeader,
            SampleEmployee,
            SampleEmployeeDeptRel,
            org_service=org_service,
        )
        app.include_router(dept_router, prefix="/api/dept")
        
        # 员工 API
        emp_router = create_employee_crud_router(
            employee_model=SampleEmployee,
            org_model=SampleOrganization,
            dept_model=SampleDepartment,
            emp_org_rel_model=SampleEmployeeOrgRel,
            emp_dept_rel_model=SampleEmployeeDeptRel,
            dept_leader_model=SampleDeptLeader,
            org_service=org_service,
        )
        app.include_router(emp_router, prefix="/api/emp")
        
        return app
    
    @pytest.fixture
    def client(self, full_app):
        """完整 API 测试客户端"""
        return TestClient(full_app)
    
    @pytest.fixture
    def setup_org_dept_emp(self, client):
        """创建测试用的组织、部门、员工"""
        # 创建组织
        org_resp = client.post("/api/org/create", json={
            "name": "关联测试公司",
            "code": "REL_TEST"
        })
        org_id = org_resp.json()["data"]["id"]
        
        # 创建部门
        dept_resp = client.post("/api/dept/create", json={
            "org_id": org_id,
            "name": "技术部"
        })
        dept_id = dept_resp.json()["data"]["id"]
        
        # 创建员工
        emp_resp = client.post("/api/emp/create", json={
            "name": "测试员工",
            "mobile": "13800138000"
        })
        emp_id = emp_resp.json()["data"]["id"]
        
        return {"org_id": org_id, "dept_id": dept_id, "emp_id": emp_id}
    
    def test_add_employee_to_org(self, client, setup_org_dept_emp):
        """测试员工加入组织"""
        data = setup_org_dept_emp
        
        response = client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": True
        })
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
    
    def test_remove_employee_from_org(self, client, setup_org_dept_emp):
        """测试员工离开组织"""
        data = setup_org_dept_emp
        
        # 先加入组织
        client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": True
        })
        
        # 再离开组织
        response = client.post(
            f"/api/emp/remove-from-org?employee_id={data['emp_id']}&org_id={data['org_id']}"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
    
    def test_add_employee_to_dept(self, client, setup_org_dept_emp):
        """测试员工加入部门"""
        data = setup_org_dept_emp
        
        # 先加入组织
        client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": True
        })
        
        # 再加入部门
        response = client.post("/api/emp/add-to-dept", json={
            "employee_id": data["emp_id"],
            "dept_id": data["dept_id"],
            "set_primary": True
        })
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
    
    def test_remove_employee_from_dept(self, client, setup_org_dept_emp):
        """测试员工离开部门"""
        data = setup_org_dept_emp
        
        # 先加入组织
        client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": True
        })
        
        # 加入部门
        client.post("/api/emp/add-to-dept", json={
            "employee_id": data["emp_id"],
            "dept_id": data["dept_id"],
            "set_primary": True
        })
        
        # 离开部门
        response = client.post(
            f"/api/emp/remove-from-dept?employee_id={data['emp_id']}&dept_id={data['dept_id']}"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
    
    def test_set_primary_org(self, client, setup_org_dept_emp):
        """测试设置主组织"""
        data = setup_org_dept_emp
        
        # 先加入组织
        client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": False
        })
        
        # 设置为主组织
        response = client.post(
            f"/api/emp/set-primary-org?employee_id={data['emp_id']}&org_id={data['org_id']}"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
    
    def test_set_primary_dept(self, client, setup_org_dept_emp):
        """测试设置主部门"""
        data = setup_org_dept_emp
        
        # 先加入组织
        client.post("/api/emp/add-to-org", json={
            "employee_id": data["emp_id"],
            "org_id": data["org_id"],
            "set_primary": True
        })
        
        # 加入部门
        client.post("/api/emp/add-to-dept", json={
            "employee_id": data["emp_id"],
            "dept_id": data["dept_id"],
            "set_primary": False
        })
        
        # 设置为主部门
        response = client.post(
            f"/api/emp/set-primary-dept?employee_id={data['emp_id']}&dept_id={data['dept_id']}"
        )
        
        assert response.status_code == 200
        result = response.json()
        assert result["status"] == "success"
