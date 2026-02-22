"""
组织管理模块 - API 路由

提供组织管理的 API 路由，使用动词风格路由，只使用 GET 和 POST 请求。

使用示例:
=========

方式1：一次性挂载全部路由（推荐）
------------------------
    from yweb.organization.api import create_org_router
    
    router = create_org_router(
        org_model=Organization,
        dept_model=Department,
        employee_model=Employee,
        emp_org_rel_model=EmployeeOrgRel,
        emp_dept_rel_model=EmployeeDeptRel,
        dept_leader_model=DepartmentLeader,
        prefix="/org",
        dependencies=[Depends(require_role("admin"))],
    )
    app.include_router(router, prefix="/api/v1")
    
    # 生成的路由:
    # GET  /api/v1/org/list, /api/v1/org/get, POST /api/v1/org/create ...
    # GET  /api/v1/org/dept/list, /api/v1/org/dept/tree ...
    # GET  /api/v1/org/employee/list, /api/v1/org/employee/get ...

方式2：按需挂载独立路由
----------------------
    from yweb.organization.api import (
        create_organization_crud_router,
        create_department_crud_router,
        create_employee_crud_router,
    )
    
    # 只挂载需要的部分
    app.include_router(
        create_organization_crud_router(org_model=Organization),
        prefix="/api/admin/org"
    )

方式3：完全自定义
----------------
    # 只使用 Service 类，自己写 API
    from yweb.organization import BaseOrganizationService
    
    class MyOrgService(BaseOrganizationService):
        ...
    
    @app.post("/my-api/employees")
    async def create_employee():
        svc = MyOrgService()
        svc.create_employee(...)
"""

from typing import Type, List, Optional, Callable, TYPE_CHECKING
from fastapi import APIRouter, Depends

if TYPE_CHECKING:
    from ..models import (
        AbstractOrganization,
        AbstractDepartment,
        AbstractEmployee,
        AbstractEmployeeOrgRel,
        AbstractEmployeeDeptRel,
        AbstractDepartmentLeader,
    )
    from ..services import BaseOrganizationService

from .organization_api import create_organization_crud_router
from .department_api import create_department_crud_router
from .employee_api import create_employee_crud_router


def create_org_router(
    org_model: Type["AbstractOrganization"],
    dept_model: Type["AbstractDepartment"],
    employee_model: Type["AbstractEmployee"],
    emp_org_rel_model: Type["AbstractEmployeeOrgRel"],
    emp_dept_rel_model: Type["AbstractEmployeeDeptRel"],
    dept_leader_model: Type["AbstractDepartmentLeader"],
    org_service: Optional["BaseOrganizationService"] = None,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[List] = None,
    tree_node_builder: Optional[Callable] = None,
    employee_response_builder: Optional[Callable] = None,
) -> APIRouter:
    """创建完整的组织管理路由
    
    一次性创建所有组织管理相关的 API 路由，使用动词风格。
    
    Args:
        org_model: 组织模型类
        dept_model: 部门模型类
        employee_model: 员工模型类
        emp_org_rel_model: 员工-组织关联模型类
        emp_dept_rel_model: 员工-部门关联模型类
        dept_leader_model: 部门负责人模型类
        org_service: 组织服务实例（可选）
        prefix: 路由前缀
        tags: OpenAPI 标签
        dependencies: 路由依赖（如权限检查）
        tree_node_builder: 自定义部门树节点构建函数（可选）
        employee_response_builder: 自定义员工响应构建函数（可选）
        
    Returns:
        配置好的 APIRouter
    
    使用示例:
        router = create_org_router(
            org_model=Organization,
            dept_model=Department,
            employee_model=Employee,
            emp_org_rel_model=EmployeeOrgRel,
            emp_dept_rel_model=EmployeeDeptRel,
            dept_leader_model=DepartmentLeader,
            prefix="/org",
            dependencies=[Depends(require_role("admin"))],
        )
        app.include_router(router, prefix="/api/v1")
    
    生成的路由（假设 prefix="/org"）:
    
        组织管理:
        - GET  {prefix}/list       获取组织列表
        - GET  {prefix}/get        获取组织详情
        - POST {prefix}/create     创建组织
        - POST {prefix}/update     更新组织
        - POST {prefix}/delete     删除组织
        
        部门管理:
        - GET  {prefix}/dept/list   获取部门列表
        - GET  {prefix}/dept/tree   获取部门树
        - GET  {prefix}/dept/get    获取部门详情
        - POST {prefix}/dept/create 创建部门
        - POST {prefix}/dept/update 更新部门
        - POST {prefix}/dept/move   移动部门
        - POST {prefix}/dept/delete 删除部门
        
        员工管理:
        - GET  {prefix}/employee/list           获取员工列表
        - GET  {prefix}/employee/get            获取员工详情
        - POST {prefix}/employee/create         创建员工
        - POST {prefix}/employee/update         更新员工
        - POST {prefix}/employee/delete         删除员工
        - POST {prefix}/employee/add-to-org     员工加入组织
        - POST {prefix}/employee/remove-from-org 员工离开组织
        - POST {prefix}/employee/add-to-dept    员工加入部门
        - POST {prefix}/employee/remove-from-dept 员工离开部门
        
        部门员工:
        - GET  {prefix}/dept/employees   获取部门员工列表
        - POST {prefix}/dept/add-leader  添加部门负责人
        - POST {prefix}/dept/remove-leader 移除部门负责人
    """
    router = APIRouter(
        prefix=prefix,
        tags=tags or ["组织管理"],
        dependencies=dependencies or [],
    )
    
    # 组织 CRUD（直接挂载到根路径）
    router.include_router(
        create_organization_crud_router(org_model=org_model, org_service=org_service),
        tags=["组织管理 - 组织"],
    )
    
    # 部门 CRUD（挂载到 /dept 子路径，包含部门员工和负责人功能）
    dept_router = create_department_crud_router(
        dept_model=dept_model,
        org_model=org_model,
        employee_model=employee_model,
        emp_org_rel_model=emp_org_rel_model,
        emp_dept_rel_model=emp_dept_rel_model,
        dept_leader_model=dept_leader_model,
        org_service=org_service,
        tree_node_builder=tree_node_builder,
    )
    router.include_router(
        dept_router,
        prefix="/dept",
        tags=["组织管理 - 部门"],
    )
    
    # 员工 CRUD（挂载到 /employee 子路径）
    emp_router = create_employee_crud_router(
        employee_model=employee_model,
        org_model=org_model,
        dept_model=dept_model,
        emp_org_rel_model=emp_org_rel_model,
        emp_dept_rel_model=emp_dept_rel_model,
        dept_leader_model=dept_leader_model,
        org_service=org_service,
        response_builder=employee_response_builder,
    )
    router.include_router(
        emp_router,
        prefix="/employee",
        tags=["组织管理 - 员工"],
    )
    
    # 把部门员工和负责人相关的路由也加到 /dept 下
    # （从 employee_api 中提取出来单独挂载，保持路径一致性）
    
    return router


__all__ = [
    # 完整路由
    "create_org_router",
    
    # 独立路由
    "create_organization_crud_router",
    "create_department_crud_router",
    "create_employee_crud_router",
]
