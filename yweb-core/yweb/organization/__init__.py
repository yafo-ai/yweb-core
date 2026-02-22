"""
组织管理模块 (Organization Module)

提供组织、部门、员工管理的抽象模型和服务，支持：
- 多组织管理
- 树形部门结构
- 员工多组织多部门归属
- 部门多负责人
- 外部系统（企业微信、飞书、钉钉）数据同步

使用方式（三个级别，按需选择）：
================================

级别1：零配置快速启用（推荐新项目使用）
------------------------------------
    from fastapi import FastAPI, Depends
    from yweb.organization import setup_organization
    
    # get_current_user 是你项目中定义的认证依赖，通常用 yweb.auth.create_auth_dependency 创建
    from app.api.dependencies import get_current_user
    
    app = FastAPI()
    
    # 一行完成：创建模型 + 创建路由 + 挂载路由
    org = setup_organization(
        app=app,
        table_prefix="sys_",
        api_prefix="/api/v1/org",
        dependencies=[Depends(get_current_user)],  # 可选，不传则接口无需认证
    )
    
    # 使用模型
    Organization = org.Organization
    Department = org.Department
    Employee = org.Employee

级别2：轻量自定义（通过 Mixin 扩展字段）
--------------------------------------
    from yweb.organization import create_org_models
    from yweb.orm import fields
    
    class EmployeeUserMixin:
        '''员工关联用户账号'''
        user = fields.ManyToOne(User, on_delete=fields.DO_NOTHING, nullable=True)
    
    org = create_org_models(
        table_prefix="sys_",
        employee_mixin=EmployeeUserMixin,  # 自动混入自定义字段
    )

级别3：完全自定义（继承抽象类）
-----------------------------
    from yweb.organization import (
        AbstractOrganization,
        AbstractDepartment,
        AbstractEmployee,
        AbstractEmployeeOrgRel,
        AbstractEmployeeDeptRel,
        AbstractDepartmentLeader,
        setup_org_relationships,
    )
    
    class Organization(AbstractOrganization):
        __tablename__ = "sys_organization"
    
    class Department(AbstractDepartment):
        __tablename__ = "sys_department"
        __org_tablename__ = "sys_organization"
        __employee_tablename__ = "sys_employee"
    
    class Employee(AbstractEmployee):
        __tablename__ = "sys_employee"
        __org_tablename__ = "sys_organization"
        __dept_tablename__ = "sys_department"
        
        # 完全自定义字段
        user_id = mapped_column(Integer, ForeignKey("user.id"), nullable=True)
    
    # ... 其他模型定义 ...
    
    # 设置 relationship
    setup_org_relationships(
        Organization, Department, Employee,
        EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader
    )

服务层使用：
----------
    # 方式1：使用工厂函数创建服务
    from yweb.organization import create_org_service
    
    service = create_org_service(org)  # org 是 create_org_models() 的返回值
    
    # 方式2：继承服务类
    from yweb.organization import BaseOrganizationService
    
    class OrganizationService(BaseOrganizationService):
        org_model = Organization
        dept_model = Department
        # ...

外部系统同步（可选）：
-------------------
    from yweb.organization import BaseSyncService, ExternalSource
    
    class WechatWorkSyncService(BaseSyncService):
        external_source = ExternalSource.WECHAT_WORK
        # 实现 fetch_departments, fetch_employees 等方法

数据关系说明：
    - 员工-组织：多对多（通过 EmployeeOrgRel）
    - 员工-部门：多对多（通过 EmployeeDeptRel）
    - 员工的主组织/主部门：存储在 Employee 表的冗余字段
    - 部门的主负责人：存储在 Department.primary_leader_id
    - 部门的所有负责人：通过 DepartmentLeader 关联表
"""

# 枚举
from .enums import (
    ExternalSource,
    EmployeeStatus,
    AccountStatus,
    Gender,
    SyncStatus,
)

# 异常处理：直接使用 ValueError，不定义自定义异常类

# Mixin（从 orm.tree 模块导入）
from yweb.orm.tree import TreeMixin

# 辅助函数
from .helpers import setup_org_relationships

# 工厂函数（推荐）
from .factory import (
    create_org_models,
    create_org_service,
    setup_organization,
    OrgModels,
)

# 抽象模型
from .models import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
)

# 服务
from .services import (
    BaseOrganizationService,
    BaseDepartmentService,
    BaseEmployeeService,
    BaseSyncService,
    SyncResult,
)

# API 路由
from .api import (
    create_org_router,
    create_organization_crud_router,
    create_department_crud_router,
    create_employee_crud_router,
)

# Schemas
from .schemas import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentTreeNode,
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeDetailResponse,
    EmployeeOrgRelCreate,
    EmployeeOrgRelResponse,
    EmployeeDeptRelCreate,
    EmployeeDeptRelResponse,
    DeptLeaderCreate,
    DeptLeaderResponse,
)

__all__ = [
    # 枚举
    "ExternalSource",
    "EmployeeStatus",
    "AccountStatus",
    "Gender",
    "SyncStatus",
    
    
    # Mixin
    "TreeMixin",
    
    # 辅助函数
    "setup_org_relationships",
    
    # 工厂函数（推荐）
    "create_org_models",
    "create_org_service",
    "setup_organization",
    "OrgModels",
    
    # 抽象模型
    "AbstractOrganization",
    "AbstractDepartment",
    "AbstractEmployee",
    "AbstractEmployeeOrgRel",
    "AbstractEmployeeDeptRel",
    "AbstractDepartmentLeader",
    
    # 服务
    "BaseOrganizationService",
    "BaseDepartmentService",
    "BaseEmployeeService",
    "BaseSyncService",
    "SyncResult",
    
    # API 路由
    "create_org_router",
    "create_organization_crud_router",
    "create_department_crud_router",
    "create_employee_crud_router",
    
    # Schemas
    "OrganizationCreate",
    "OrganizationUpdate",
    "OrganizationResponse",
    "DepartmentCreate",
    "DepartmentUpdate",
    "DepartmentResponse",
    "DepartmentTreeNode",
    "EmployeeCreate",
    "EmployeeUpdate",
    "EmployeeResponse",
    "EmployeeDetailResponse",
    "EmployeeOrgRelCreate",
    "EmployeeOrgRelResponse",
    "EmployeeDeptRelCreate",
    "EmployeeDeptRelResponse",
    "DeptLeaderCreate",
    "DeptLeaderResponse",
]
