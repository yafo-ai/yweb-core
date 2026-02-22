"""
组织管理模块 - 模型工厂

提供 create_org_models() 函数，用于快速创建组织架构所有模型。
简化使用方式，同时保留自定义扩展能力。

使用方式：
=========

级别1：零配置快速启用
-------------------
    from yweb.organization import create_org_models
    
    # 一行创建所有模型
    org = create_org_models(table_prefix="sys_")
    
    # 使用模型
    Organization = org.Organization
    Department = org.Department
    Employee = org.Employee
    # ...

级别2：轻量自定义（通过 Mixin）
---------------------------
    from yweb.organization import create_org_models
    from yweb.orm import fields
    
    class EmployeeUserMixin:
        '''员工关联用户账号'''
        user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)
    
    org = create_org_models(
        table_prefix="sys_",
        employee_mixin=EmployeeUserMixin,
    )

级别3：完全自定义（现有方式）
------------------------
    # 继承抽象类，手动定义模型
    class Employee(AbstractEmployee):
        __tablename__ = "sys_employee"
        # 完全自定义...
"""

from types import SimpleNamespace
from typing import Type, Optional, Callable, Any
from dataclasses import dataclass, field

from .models import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
)
from .helpers import setup_org_relationships
from .enums import ExternalSource, EmployeeStatus, AccountStatus, Gender, SyncStatus


def _generate_tablename(base_name: str, prefix: str = "") -> str:
    """生成表名
    
    Args:
        base_name: 基础表名（如 'organization'）
        prefix: 表名前缀（如 'sys_'）
    
    Returns:
        完整表名（如 'sys_organization'）
    """
    return f"{prefix}{base_name}" if prefix else base_name


def _create_model_class(
    name: str,
    base_class: Type,
    tablename: str,
    extra_attrs: dict = None,
    mixin: Type = None,
) -> Type:
    """动态创建模型类
    
    Args:
        name: 类名
        base_class: 基类（抽象模型）
        tablename: 表名
        extra_attrs: 额外的类属性
        mixin: 可选的 Mixin 类
    
    Returns:
        新创建的模型类
    """
    from yweb.orm.fields import (
        _OneToOneConfig, _ManyToOneConfig, _ManyToManyConfig,
    )
    
    # 确定基类列表
    if mixin:
        bases = (mixin, base_class)
    else:
        bases = (base_class,)
    
    # 类属性
    attrs = {
        "__tablename__": tablename,
        "__table_args__": {"extend_existing": True},
    }
    
    # 合并额外属性
    if extra_attrs:
        attrs.update(extra_attrs)
    
    # 将 Mixin 中的关系字段配置复制到类属性中
    # 因为 __init_subclass__ 使用 vars(cls) 检测字段，
    # 只检查类自身的 __dict__，不会遍历 MRO 父类，
    # 所以必须把 Mixin 的字段"提升"到新类的属性里才能被识别和处理
    if mixin:
        for attr_name, value in vars(mixin).items():
            if isinstance(value, (_OneToOneConfig, _ManyToOneConfig, _ManyToManyConfig)):
                attrs[attr_name] = value
    
    # 动态创建类
    return type(name, bases, attrs)


@dataclass
class OrgModels:
    """组织架构模型容器
    
    包含所有组织架构相关的模型类和枚举，支持点号访问。
    
    属性:
        # 模型
        Organization: 组织模型
        Department: 部门模型
        Employee: 员工模型
        EmployeeOrgRel: 员工-组织关联模型
        EmployeeDeptRel: 员工-部门关联模型
        DepartmentLeader: 部门负责人模型
        
        # 枚举（便捷访问）
        ExternalSource: 外部系统来源枚举
        EmployeeStatus: 员工状态枚举
        AccountStatus: 账号激活状态枚举
        Gender: 性别枚举
        SyncStatus: 同步状态枚举
    
    使用示例:
        org = create_org_models(table_prefix="sys_")
        
        # 访问模型
        emp = org.Employee(name="张三")
        
        # 访问枚举
        emp.gender = org.Gender.MALE.value
        
        # 获取单例服务
        service = org.get_org_service()
    """
    # 模型
    Organization: Type
    Department: Type
    Employee: Type
    EmployeeOrgRel: Type
    EmployeeDeptRel: Type
    DepartmentLeader: Type
    
    # 枚举（便捷访问）
    ExternalSource: Type = field(default=ExternalSource)
    EmployeeStatus: Type = field(default=EmployeeStatus)
    AccountStatus: Type = field(default=AccountStatus)
    Gender: Type = field(default=Gender)
    SyncStatus: Type = field(default=SyncStatus)
    
    # 私有：单例服务实例
    _service_instance: Any = field(default=None, repr=False)
    
    def as_dict(self) -> dict:
        """返回模型字典，方便传递给 create_org_router"""
        return {
            "org_model": self.Organization,
            "dept_model": self.Department,
            "employee_model": self.Employee,
            "emp_org_rel_model": self.EmployeeOrgRel,
            "emp_dept_rel_model": self.EmployeeDeptRel,
            "dept_leader_model": self.DepartmentLeader,
        }
    
    def get_org_service(self):
        """获取组织架构服务单例
        
        Returns:
            OrganizationService 实例（单例模式）
        
        使用示例:
            org = create_org_models(table_prefix="sys_")
            service = org.get_org_service()
            
            # 创建组织
            org_entity = service.create_org(name="某某公司")
        """
        if self._service_instance is None:
            from .services import BaseOrganizationService
            
            # 动态创建服务类
            service_class = type(
                "OrganizationService",
                (BaseOrganizationService,),
                {
                    "org_model": self.Organization,
                    "dept_model": self.Department,
                    "employee_model": self.Employee,
                    "emp_org_rel_model": self.EmployeeOrgRel,
                    "emp_dept_rel_model": self.EmployeeDeptRel,
                    "dept_leader_model": self.DepartmentLeader,
                }
            )
            # 使用 object.__setattr__ 绕过 frozen dataclass 的限制
            object.__setattr__(self, '_service_instance', service_class())
        
        return self._service_instance
    
    def mount_routes(
        self,
        app,
        prefix: str = "/api/org",
        tags: list = None,
        dependencies: list = None,
        tree_node_builder=None,
        employee_response_builder=None,
    ):
        """挂载组织管理路由到 FastAPI 应用
        
        与 auth.mount_routes() 风格一致的路由挂载方法。
        
        Args:
            app: FastAPI 应用实例
            prefix: API 路由前缀（默认 "/api/org"）
            tags: OpenAPI 标签
            dependencies: 路由依赖（如权限检查）
            tree_node_builder: 自定义部门树节点构建函数（可选）
            employee_response_builder: 自定义员工响应构建函数（可选）
        
        使用示例:
            org = create_org_models(table_prefix="sys_")
            org.mount_routes(
                app,
                prefix="/api/v1/org",
                dependencies=[Depends(get_current_user)],
            )
        """
        from .api import create_org_router
        
        router = create_org_router(
            org_model=self.Organization,
            dept_model=self.Department,
            employee_model=self.Employee,
            emp_org_rel_model=self.EmployeeOrgRel,
            emp_dept_rel_model=self.EmployeeDeptRel,
            dept_leader_model=self.DepartmentLeader,
            org_service=self.get_org_service(),
            prefix="",
            tags=tags or ["组织管理"],
            dependencies=dependencies,
            tree_node_builder=tree_node_builder,
            employee_response_builder=employee_response_builder,
        )
        app.include_router(router, prefix=prefix)


def create_org_models(
    table_prefix: str = "",
    # 自定义表名（可选）
    organization_tablename: str = None,
    department_tablename: str = None,
    employee_tablename: str = None,
    emp_org_rel_tablename: str = None,
    emp_dept_rel_tablename: str = None,
    dept_leader_tablename: str = None,
    # Mixin 扩展（可选）
    organization_mixin: Type = None,
    department_mixin: Type = None,
    employee_mixin: Type = None,
    emp_org_rel_mixin: Type = None,
    emp_dept_rel_mixin: Type = None,
    dept_leader_mixin: Type = None,
    # 回调自定义（可选）
    organization_customizer: Callable[[Type], None] = None,
    department_customizer: Callable[[Type], None] = None,
    employee_customizer: Callable[[Type], None] = None,
    emp_org_rel_customizer: Callable[[Type], None] = None,
    emp_dept_rel_customizer: Callable[[Type], None] = None,
    dept_leader_customizer: Callable[[Type], None] = None,
    # 是否自动设置 relationship
    auto_setup_relationships: bool = True,
    # 级联软删除配置（可选）
    cascade_config: dict = None,
) -> OrgModels:
    """创建组织架构所有模型
    
    一站式创建组织、部门、员工及关联表的模型类。
    支持通过 Mixin 或回调函数自定义扩展。
    
    Args:
        table_prefix: 表名前缀（如 "sys_"），应用于所有表
        
        organization_tablename: 组织表名（默认根据 prefix 生成）
        department_tablename: 部门表名
        employee_tablename: 员工表名
        emp_org_rel_tablename: 员工-组织关联表名
        emp_dept_rel_tablename: 员工-部门关联表名
        dept_leader_tablename: 部门负责人表名
        
        organization_mixin: 组织模型的 Mixin 类
        department_mixin: 部门模型的 Mixin 类
        employee_mixin: 员工模型的 Mixin 类（常用于关联用户）
        emp_org_rel_mixin: 员工-组织关联的 Mixin 类
        emp_dept_rel_mixin: 员工-部门关联的 Mixin 类
        dept_leader_mixin: 部门负责人的 Mixin 类
        
        organization_customizer: 组织模型的回调自定义函数
        department_customizer: 部门模型的回调自定义函数
        employee_customizer: 员工模型的回调自定义函数
        emp_org_rel_customizer: 员工-组织关联的回调自定义函数
        emp_dept_rel_customizer: 员工-部门关联的回调自定义函数
        dept_leader_customizer: 部门负责人的回调自定义函数
        
        auto_setup_relationships: 是否自动设置模型间的 relationship（默认 True）
        
        cascade_config: 级联软删除配置（可选），覆盖默认配置
            默认策略：
            - 组织有部门/员工时禁止删除（PROTECT）
            - 部门有子部门/员工时禁止删除（PROTECT）
            - 员工删除时自动清理关联（DELETE/SET_NULL）
            可配置的键参见 helpers.DEFAULT_CASCADE_CONFIG
    
    Returns:
        OrgModels 对象，包含所有模型类
    
    使用示例:
        # 级别1：零配置
        org = create_org_models(table_prefix="sys_")
        
        # 级别2：添加自定义字段
        from yweb.orm import fields
        
        class EmployeeUserMixin:
            user = fields.OneToOne(User, on_delete=fields.DO_NOTHING)
        
        org = create_org_models(
            table_prefix="sys_",
            employee_mixin=EmployeeUserMixin,
        )
        
        # 在 API 中使用
        from yweb.organization import create_org_router
        
        router = create_org_router(
            **org.as_dict(),
            prefix="/org",
            dependencies=[...],
        )
    """
    # 1. 生成表名
    org_table = organization_tablename or _generate_tablename("organization", table_prefix)
    dept_table = department_tablename or _generate_tablename("department", table_prefix)
    emp_table = employee_tablename or _generate_tablename("employee", table_prefix)
    emp_org_rel_table = emp_org_rel_tablename or _generate_tablename("employee_org_rel", table_prefix)
    emp_dept_rel_table = emp_dept_rel_tablename or _generate_tablename("employee_dept_rel", table_prefix)
    dept_leader_table = dept_leader_tablename or _generate_tablename("department_leader", table_prefix)
    
    # 2. 创建 Organization 模型
    Organization = _create_model_class(
        name="Organization",
        base_class=AbstractOrganization,
        tablename=org_table,
        mixin=organization_mixin,
    )
    
    # 3. 创建 Department 模型（需要引用 org_table 和 emp_table）
    Department = _create_model_class(
        name="Department",
        base_class=AbstractDepartment,
        tablename=dept_table,
        extra_attrs={
            "__org_tablename__": org_table,
            "__employee_tablename__": emp_table,
        },
        mixin=department_mixin,
    )
    
    # 4. 创建 Employee 模型（需要引用 org_table 和 dept_table）
    Employee = _create_model_class(
        name="Employee",
        base_class=AbstractEmployee,
        tablename=emp_table,
        extra_attrs={
            "__org_tablename__": org_table,
            "__dept_tablename__": dept_table,
        },
        mixin=employee_mixin,
    )
    
    # 5. 创建 EmployeeOrgRel 模型
    EmployeeOrgRel = _create_model_class(
        name="EmployeeOrgRel",
        base_class=AbstractEmployeeOrgRel,
        tablename=emp_org_rel_table,
        extra_attrs={
            "__employee_tablename__": emp_table,
            "__org_tablename__": org_table,
        },
        mixin=emp_org_rel_mixin,
    )
    
    # 6. 创建 EmployeeDeptRel 模型
    EmployeeDeptRel = _create_model_class(
        name="EmployeeDeptRel",
        base_class=AbstractEmployeeDeptRel,
        tablename=emp_dept_rel_table,
        extra_attrs={
            "__employee_tablename__": emp_table,
            "__dept_tablename__": dept_table,
        },
        mixin=emp_dept_rel_mixin,
    )
    
    # 7. 创建 DepartmentLeader 模型
    DepartmentLeader = _create_model_class(
        name="DepartmentLeader",
        base_class=AbstractDepartmentLeader,
        tablename=dept_leader_table,
        extra_attrs={
            "__dept_tablename__": dept_table,
            "__employee_tablename__": emp_table,
        },
        mixin=dept_leader_mixin,
    )
    
    # 8. 应用自定义回调
    if organization_customizer:
        organization_customizer(Organization)
    if department_customizer:
        department_customizer(Department)
    if employee_customizer:
        employee_customizer(Employee)
    if emp_org_rel_customizer:
        emp_org_rel_customizer(EmployeeOrgRel)
    if emp_dept_rel_customizer:
        emp_dept_rel_customizer(EmployeeDeptRel)
    if dept_leader_customizer:
        dept_leader_customizer(DepartmentLeader)
    
    # 9. 自动设置 relationship（含级联软删除配置）
    if auto_setup_relationships:
        setup_org_relationships(
            Organization, Department, Employee,
            EmployeeOrgRel, EmployeeDeptRel, DepartmentLeader,
            cascade_config=cascade_config,
        )
    
    # 10. 返回模型容器
    return OrgModels(
        Organization=Organization,
        Department=Department,
        Employee=Employee,
        EmployeeOrgRel=EmployeeOrgRel,
        EmployeeDeptRel=EmployeeDeptRel,
        DepartmentLeader=DepartmentLeader,
    )


def create_org_service(
    org_models: OrgModels,
    service_class: Type = None,
    dept_service_class: Type = None,
    emp_service_class: Type = None,
) -> Any:
    """创建组织架构服务实例
    
    自动创建并注入子服务（DeptService、EmpService），支持完整的委托操作。
    如果用户自定义的 service_class 已经设置了 dept_service 或 employee_service，
    则保留用户的设置，不会覆盖。
    
    Args:
        org_models: create_org_models() 返回的模型容器
        service_class: 自定义组织服务类（可选，默认使用 BaseOrganizationService）
        dept_service_class: 自定义部门服务类（可选，默认动态创建）
        emp_service_class: 自定义员工服务类（可选，默认动态创建）
    
    Returns:
        服务实例（已注入 dept_service 和 employee_service）
    
    使用示例:
        # 基础用法
        org = create_org_models(table_prefix="sys_")
        service = create_org_service(org)
        
        # 使用自定义服务类
        class MyOrgService(BaseOrganizationService):
            org_model = org.Organization
            # 可以不设置 dept_service/employee_service，会自动注入
        
        service = create_org_service(org, service_class=MyOrgService)
        
        # 使用自定义子服务
        class MyDeptService(BaseDepartmentService):
            dept_model = org.Department
        
        service = create_org_service(org, dept_service_class=MyDeptService)
    """
    from .services import BaseOrganizationService, BaseDepartmentService, BaseEmployeeService
    
    # 1. 创建 EmpService（使用用户自定义类或动态创建）
    if emp_service_class is None:
        emp_service_class = type(
            "EmployeeService",
            (BaseEmployeeService,),
            {
                "employee_model": org_models.Employee,
                "dept_model": org_models.Department,
                "emp_org_rel_model": org_models.EmployeeOrgRel,
                "emp_dept_rel_model": org_models.EmployeeDeptRel,
                "dept_leader_model": org_models.DepartmentLeader,
            }
        )
    emp_service = emp_service_class()
    
    # 2. 创建 DeptService（使用用户自定义类或动态创建）
    if dept_service_class is None:
        dept_service_class = type(
            "DepartmentService",
            (BaseDepartmentService,),
            {
                "dept_model": org_models.Department,
                "dept_leader_model": org_models.DepartmentLeader,
            }
        )
    dept_service = dept_service_class()
    
    # 注入 EmpService 到 DeptService（如果用户未自行设置）
    if not hasattr(dept_service, 'employee_service') or dept_service.employee_service is None:
        dept_service.employee_service = emp_service
    
    # 3. 创建 OrgService（使用用户自定义类或动态创建）
    if service_class is None:
        service_class = type(
            "OrganizationService",
            (BaseOrganizationService,),
            {
                "org_model": org_models.Organization,
            }
        )
    
    org_service = service_class()
    
    # 注入子服务（如果用户未自行设置）
    if not hasattr(org_service, 'dept_service') or org_service.dept_service is None:
        org_service.dept_service = dept_service
    if not hasattr(org_service, 'employee_service') or org_service.employee_service is None:
        org_service.employee_service = emp_service
    
    # 4. 回填 org_service 到 dept_service（用于组织验证，如果用户未自行设置）
    if not hasattr(dept_service, 'org_service') or dept_service.org_service is None:
        dept_service.org_service = org_service
    
    return org_service


def setup_organization(
    app,  # FastAPI 实例
    table_prefix: str = "",
    api_prefix: str = "/api/v1",
    prefix: str = "/org",
    tags: list = None,
    dependencies: list = None,
    # Mixin 扩展（可选）
    organization_mixin: Type = None,
    department_mixin: Type = None,
    employee_mixin: Type = None,
    emp_org_rel_mixin: Type = None,
    emp_dept_rel_mixin: Type = None,
    dept_leader_mixin: Type = None,
    # 回调自定义（可选）
    organization_customizer: Callable[[Type], None] = None,
    department_customizer: Callable[[Type], None] = None,
    employee_customizer: Callable[[Type], None] = None,
    # 自定义表名（可选）
    organization_tablename: str = None,
    department_tablename: str = None,
    employee_tablename: str = None,
    emp_org_rel_tablename: str = None,
    emp_dept_rel_tablename: str = None,
    dept_leader_tablename: str = None,
    # 级联软删除配置（可选）
    cascade_config: dict = None,
) -> OrgModels:
    """一站式设置组织架构模块
    
    最简洁的使用方式：一个函数完成模型创建、路由创建、路由挂载。
    
    Args:
        app: FastAPI 应用实例
        table_prefix: 表名前缀（如 "sys_"）
        api_prefix: API 基础前缀（默认 "/api/v1"），与 setup_auth 一致
        prefix: 模块路由前缀（默认 "/org"），最终路由为 api_prefix + prefix
        tags: OpenAPI 标签
        dependencies: 路由依赖（如权限检查）
        
        organization_mixin: 组织模型的 Mixin 类
        department_mixin: 部门模型的 Mixin 类
        employee_mixin: 员工模型的 Mixin 类
        emp_org_rel_mixin: 员工-组织关联的 Mixin 类
        emp_dept_rel_mixin: 员工-部门关联的 Mixin 类
        dept_leader_mixin: 部门负责人的 Mixin 类
        
        organization_customizer: 组织模型的回调自定义函数
        department_customizer: 部门模型的回调自定义函数
        employee_customizer: 员工模型的回调自定义函数
        
        organization_tablename: 自定义组织表名
        department_tablename: 自定义部门表名
        employee_tablename: 自定义员工表名
        emp_org_rel_tablename: 自定义员工-组织关联表名
        emp_dept_rel_tablename: 自定义员工-部门关联表名
        dept_leader_tablename: 自定义部门负责人表名
    
    Returns:
        OrgModels 对象，包含所有模型类
    
    使用示例:
        from fastapi import FastAPI, Depends
        from yweb.organization import setup_organization
        
        app = FastAPI()
        
        # 一行完成所有设置（路由挂载在 /api/v1/org 下）
        org = setup_organization(
            app=app,
            table_prefix="sys_",
            api_prefix="/api/v1",
            dependencies=[Depends(get_current_user)],
        )
        
        # 在其他地方使用模型
        Organization = org.Organization
        Employee = org.Employee
        
        # 带自定义字段的使用
        from yweb.orm import fields
        
        class EmployeeUserMixin:
            user = fields.OneToOne(User, on_delete=fields.DO_NOTHING, nullable=True)
        
        org = setup_organization(
            app=app,
            table_prefix="sys_",
            api_prefix="/api/v1",
            employee_mixin=EmployeeUserMixin,
            dependencies=[Depends(get_current_user)],
        )
    """
    from .api import create_org_router
    
    # 1. 创建所有模型
    org_models = create_org_models(
        table_prefix=table_prefix,
        organization_tablename=organization_tablename,
        department_tablename=department_tablename,
        employee_tablename=employee_tablename,
        emp_org_rel_tablename=emp_org_rel_tablename,
        emp_dept_rel_tablename=emp_dept_rel_tablename,
        dept_leader_tablename=dept_leader_tablename,
        organization_mixin=organization_mixin,
        department_mixin=department_mixin,
        employee_mixin=employee_mixin,
        emp_org_rel_mixin=emp_org_rel_mixin,
        emp_dept_rel_mixin=emp_dept_rel_mixin,
        dept_leader_mixin=dept_leader_mixin,
        organization_customizer=organization_customizer,
        department_customizer=department_customizer,
        employee_customizer=employee_customizer,
        cascade_config=cascade_config,
    )
    
    # 2. 创建服务实例
    org_service = create_org_service(org_models)
    
    # 3. 创建路由
    router = create_org_router(
        org_model=org_models.Organization,
        dept_model=org_models.Department,
        employee_model=org_models.Employee,
        emp_org_rel_model=org_models.EmployeeOrgRel,
        emp_dept_rel_model=org_models.EmployeeDeptRel,
        dept_leader_model=org_models.DepartmentLeader,
        org_service=org_service,
        prefix="",  # 前缀在 include_router 时设置
        tags=tags or ["组织架构"],
        dependencies=dependencies,
    )
    
    # 4. 挂载路由到应用
    app.include_router(router, prefix=f"{api_prefix}{prefix}")
    
    return org_models


__all__ = [
    "create_org_models",
    "create_org_service",
    "setup_organization",
    "OrgModels",
]
