"""
组织管理模块 - 员工 CRUD API

提供员工的增删改查接口，以及员工与组织/部门的关联操作。
使用动词风格路由，只使用 GET 和 POST 请求。

设计原则（DDD 分层）：
- API 层只负责：参数验证、DTO 转换、异常处理、调用服务层
- 业务逻辑封装在领域模型和服务层
- 捕获 ValueError 统一处理
"""

from typing import Type, Optional, Callable, TYPE_CHECKING
from fastapi import APIRouter, Query

from yweb.response import Resp, PageResponse, ItemResponse, OkResponse

from ..schemas.employee import (
    EmployeeCreate,
    EmployeeUpdate,
    EmployeeResponse,
    EmployeeDetailResponse,
    EmployeeOrgRelCreate,
    EmployeeOrgRelResponse,
    EmployeeDeptRelCreate,
    EmployeeDeptRelResponse,
    EmployeeOrgInfo,
    EmployeeDeptInfo,
)

if TYPE_CHECKING:
    from ..models import (
        AbstractEmployee,
        AbstractOrganization,
        AbstractDepartment,
        AbstractEmployeeOrgRel,
        AbstractEmployeeDeptRel,
        AbstractDepartmentLeader,
    )
    from ..services import BaseOrganizationService


def create_employee_crud_router(
    employee_model: Type["AbstractEmployee"],
    org_model: Type["AbstractOrganization"],
    dept_model: Type["AbstractDepartment"],
    emp_org_rel_model: Type["AbstractEmployeeOrgRel"],
    emp_dept_rel_model: Type["AbstractEmployeeDeptRel"],
    dept_leader_model: Type["AbstractDepartmentLeader"],
    org_service: "BaseOrganizationService" = None,
    response_builder: Optional[Callable] = None,
) -> APIRouter:
    """创建员工 CRUD 路由
    
    Args:
        employee_model: 员工模型类
        org_model: 组织模型类
        dept_model: 部门模型类
        emp_org_rel_model: 员工-组织关联模型类
        emp_dept_rel_model: 员工-部门关联模型类
        dept_leader_model: 部门负责人模型类
        org_service: 组织服务实例（必须提供，用于业务操作）
        response_builder: 自定义响应构建函数（可选）
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list            - 获取员工列表
        GET  /get             - 获取员工详情
        POST /create          - 创建员工
        POST /update          - 更新员工
        POST /delete          - 删除员工
        POST /add-to-org      - 员工加入组织
        POST /remove-from-org - 员工离开组织
        POST /set-primary-org - 设置主组织
        POST /add-to-dept     - 员工加入部门
        POST /remove-from-dept - 员工离开部门
        POST /set-primary-dept - 设置主部门
    """
    router = APIRouter()
    
    # ==================== 辅助函数（展示层 DTO 转换） ====================
    
    def _compute_account_status(emp) -> int | None:
        """从关联的 User 推导账号状态（容错：无 user 关联时返回 None）"""
        if not hasattr(emp, 'user_id'):
            return None
        if getattr(emp, 'user_id', None) is None:
            return 0   # 未激活（无账号）
        user = getattr(emp, 'user', None)
        if user and getattr(user, 'is_active', False):
            return 1   # 已激活
        return -1       # 已禁用
    
    def _build_employee_response(emp, include_options: set = None):
        """构建员工响应数据"""
        if response_builder:
            data = response_builder(emp, emp.to_dict())
            # 注入推导的 account_status
            account_status = _compute_account_status(emp)
            if account_status is not None:
                data["account_status"] = account_status
            return EmployeeResponse.from_dict(data)
        
        include_options = include_options or set()
        
        # 构建字典（统一走字典路径以注入推导字段）
        data = emp.to_dict()
        
        # 注入推导的 account_status
        account_status = _compute_account_status(emp)
        if account_status is not None:
            data["account_status"] = account_status
        
        if "org_name" in include_options or "primary_org_name" in include_options:
            if hasattr(emp, 'primary_org') and emp.primary_org:
                data["primary_org_name"] = emp.primary_org.name
        
        if "dept_name" in include_options or "primary_dept_name" in include_options:
            if hasattr(emp, 'primary_dept') and emp.primary_dept:
                data["primary_dept_name"] = emp.primary_dept.name
        
        # 附带主组织的雇佣状态
        try:
            org_rel = None
            if hasattr(emp, 'primary_org_id') and emp.primary_org_id:
                org_rel = emp_org_rel_model.query.filter_by(
                    employee_id=emp.id,
                    org_id=emp.primary_org_id
                ).first()
            if not org_rel:
                org_rel = emp_org_rel_model.query.filter_by(
                    employee_id=emp.id
                ).first()
            if org_rel:
                data["emp_status"] = org_rel.status
        except Exception:
            pass
        
        return EmployeeResponse.from_dict(data)
    
    def _build_employee_detail(emp):
        """构建员工详情响应（包含关联信息）"""
        data = emp.to_dict()
        
        if hasattr(emp, 'primary_org') and emp.primary_org:
            data["primary_org_name"] = emp.primary_org.name
        if hasattr(emp, 'primary_dept') and emp.primary_dept:
            data["primary_dept_name"] = emp.primary_dept.name
        
        # 构建组织列表
        organizations = []
        if hasattr(emp, 'employee_org_rels'):
            for rel in emp.employee_org_rels:
                org_info = rel.to_dict()
                org_info["org_name"] = rel.organization.name if hasattr(rel, 'organization') and rel.organization else None
                org_info["is_primary"] = rel.org_id == emp.primary_org_id
                organizations.append(EmployeeOrgInfo.from_dict(org_info))
        data["organizations"] = organizations
        
        # 构建部门列表
        departments = []
        if hasattr(emp, 'employee_dept_rels'):
            for rel in emp.employee_dept_rels:
                dept_info = rel.to_dict()
                dept_info["dept_name"] = rel.department.name if hasattr(rel, 'department') and rel.department else None
                dept_info["is_primary"] = rel.dept_id == emp.primary_dept_id
                departments.append(EmployeeDeptInfo.from_dict(dept_info))
        data["departments"] = departments
        
        return EmployeeDetailResponse.from_dict(data)
    
    # ==================== 查询接口（直接查询模型） ====================
    
    @router.get(
        "/list",
        response_model=PageResponse[EmployeeResponse],
        summary="获取员工列表",
        description="获取员工列表，支持按组织、部门筛选"
    )
    async def list_employees(
        org_id: Optional[int] = Query(None, description="按组织筛选"),
        dept_id: Optional[int] = Query(None, description="按部门筛选"),
        keyword: Optional[str] = Query(None, description="按姓名/手机号搜索"),
        account_status: Optional[int] = Query(None, description="按账号状态筛选（-1-已禁用，0-未激活，1-已激活）"),
        emp_status: Optional[int] = Query(None, description="按雇佣状态筛选（-1-离职，0-停职，1-待入职，2-试用，3-在职）"),
        include: Optional[str] = Query(None, description="附加信息，逗号分隔（org_name,dept_name）"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """获取员工列表"""
        query = employee_model.query
        
        # 按组织筛选
        if org_id is not None:
            emp_ids = [r.employee_id for r in emp_org_rel_model.query.filter_by(org_id=org_id).all()]
            query = query.filter(employee_model.id.in_(emp_ids))
        
        # 按部门筛选
        if dept_id is not None:
            emp_ids = [r.employee_id for r in emp_dept_rel_model.query.filter_by(dept_id=dept_id).all()]
            query = query.filter(employee_model.id.in_(emp_ids))
        
        # 关键字搜索
        if keyword:
            query = query.filter(
                (employee_model.name.contains(keyword)) |
                (employee_model.mobile.contains(keyword))
            )
        
        # 账号状态筛选（从 user 关联推导：0=无账号，1=已激活，-1=已禁用）
        if account_status is not None and hasattr(employee_model, 'user_id'):
            if account_status == 0:
                # 未激活 = 没有关联用户
                query = query.filter(employee_model.user_id.is_(None))
            elif account_status in (1, -1):
                # 有账号的员工，需要关联 User 表判断 is_active
                from sqlalchemy.orm import RelationshipProperty
                user_rel = getattr(employee_model, 'user', None)
                if user_rel is not None and hasattr(user_rel, 'property'):
                    user_model_cls = user_rel.property.mapper.class_
                    is_active_target = (account_status == 1)
                    matching_user_ids = [
                        u.id for u in user_model_cls.query.filter(
                            user_model_cls.is_active == is_active_target
                        ).all()
                    ]
                    query = query.filter(employee_model.user_id.in_(matching_user_ids))
        
        # 雇佣状态筛选（通过员工-组织关联表）
        if emp_status is not None:
            emp_ids = [
                r.employee_id for r in emp_org_rel_model.query.filter(
                    emp_org_rel_model.status == emp_status
                ).all()
            ]
            query = query.filter(employee_model.id.in_(emp_ids))
        
        include_options = set(include.split(",")) if include else set()
        
        page_result = query.order_by(employee_model.id).paginate(page=page, page_size=page_size)
        
        # 统一走 _build_employee_response 以注入推导的 account_status
        page_result.rows = [_build_employee_response(e, include_options) for e in page_result.rows]
        return Resp.OK(data=page_result)
    
    @router.get(
        "/get",
        response_model=ItemResponse[EmployeeDetailResponse],
        summary="获取员工详情",
        description="根据员工ID获取详情（包含组织和部门信息）"
    )
    async def get_employee(
        employee_id: int = Query(..., description="员工ID"),
    ):
        """获取员工详情"""
        emp = employee_model.get(employee_id)
        if not emp:
            return Resp.NotFound(message=f"员工不存在: {employee_id}")
        
        return Resp.OK(data=_build_employee_detail(emp))
    
    # ==================== 员工 CRUD（调用服务层） ====================
    
    @router.post(
        "/create",
        response_model=ItemResponse[EmployeeResponse],
        summary="创建员工",
        description="创建新的员工"
    )
    async def create_employee(data: EmployeeCreate):
        """创建员工"""
        try:
            emp = org_service.create_employee(
                name=data.name,
                mobile=data.mobile,
                email=data.email,
                gender=data.gender,
                avatar=data.avatar,
                is_senior=data.is_senior,
            )
            return Resp.OK(data=EmployeeResponse.from_entity(emp), message="创建成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/update",
        response_model=ItemResponse[EmployeeResponse],
        summary="更新员工",
        description="更新员工信息"
    )
    async def update_employee(
        data: EmployeeUpdate,
        employee_id: int = Query(..., description="员工ID"),
    ):
        """更新员工"""
        try:
            update_data = data.model_dump(exclude_unset=True)
            emp = org_service.update_employee(employee_id=employee_id, **update_data)
            return Resp.OK(data=EmployeeResponse.from_entity(emp), message="更新成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/delete",
        response_model=OkResponse,
        summary="删除员工",
        description="删除员工（软删除，自动级联清理关联数据）"
    )
    async def delete_employee(
        employee_id: int = Query(..., description="员工ID"),
    ):
        """删除员工"""
        try:
            org_service.delete_employee(employee_id=employee_id)
            return Resp.OK(data={"id": employee_id}, message="删除成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    # ==================== 员工-组织关联（调用服务层） ====================
    
    @router.post(
        "/add-to-org",
        response_model=ItemResponse[EmployeeOrgRelResponse],
        summary="员工加入组织",
        description="将员工添加到指定组织"
    )
    async def add_employee_to_org(data: EmployeeOrgRelCreate):
        """员工加入组织"""
        try:
            rel = org_service.add_employee_to_org(
                employee_id=data.employee_id,
                org_id=data.org_id,
                emp_no=data.emp_no,
                position=data.position,
                status=data.status,
                set_as_primary=data.set_primary,
            )
            return Resp.OK(data=EmployeeOrgRelResponse.from_entity(rel), message="加入成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/remove-from-org",
        response_model=OkResponse,
        summary="员工离开组织",
        description="将员工从指定组织移除（同时移除该组织下的部门关联）"
    )
    async def remove_employee_from_org(
        employee_id: int = Query(..., description="员工ID"),
        org_id: int = Query(..., description="组织ID"),
    ):
        """员工离开组织"""
        try:
            org_service.remove_employee_from_org(employee_id=employee_id, org_id=org_id)
            return Resp.OK(data={"employee_id": employee_id, "org_id": org_id}, message="移除成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/set-primary-org",
        response_model=OkResponse,
        summary="设置主组织",
        description="将指定组织设为员工的主组织"
    )
    async def set_primary_org(
        employee_id: int = Query(..., description="员工ID"),
        org_id: int = Query(..., description="组织ID"),
    ):
        """设置主组织"""
        try:
            org_service.set_primary_org(employee_id=employee_id, org_id=org_id)
            return Resp.OK(data={"employee_id": employee_id, "primary_org_id": org_id}, message="设置成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    # ==================== 员工-部门关联（调用服务层） ====================
    
    @router.post(
        "/add-to-dept",
        response_model=ItemResponse[EmployeeDeptRelResponse],
        summary="员工加入部门",
        description="将员工添加到指定部门（需先加入该部门所属组织）"
    )
    async def add_employee_to_dept(data: EmployeeDeptRelCreate):
        """员工加入部门"""
        try:
            rel = org_service.add_employee_to_dept(
                employee_id=data.employee_id,
                dept_id=data.dept_id,
                set_as_primary=data.set_primary,
            )
            return Resp.OK(data=EmployeeDeptRelResponse.from_entity(rel), message="加入成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/remove-from-dept",
        response_model=OkResponse,
        summary="员工离开部门",
        description="将员工从指定部门移除（同时移除负责人身份）"
    )
    async def remove_employee_from_dept(
        employee_id: int = Query(..., description="员工ID"),
        dept_id: int = Query(..., description="部门ID"),
    ):
        """员工离开部门"""
        try:
            org_service.remove_employee_from_dept(employee_id=employee_id, dept_id=dept_id)
            return Resp.OK(data={"employee_id": employee_id, "dept_id": dept_id}, message="移除成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/set-primary-dept",
        response_model=OkResponse,
        summary="设置主部门",
        description="将指定部门设为员工的主部门（主部门必须属于主组织）"
    )
    async def set_primary_dept(
        employee_id: int = Query(..., description="员工ID"),
        dept_id: int = Query(..., description="部门ID"),
    ):
        """设置主部门"""
        try:
            org_service.set_primary_dept(employee_id=employee_id, dept_id=dept_id)
            return Resp.OK(data={"employee_id": employee_id, "primary_dept_id": dept_id}, message="设置成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    # ==================== 状态管理 ====================
    
    @router.post(
        "/update-org-status",
        response_model=ItemResponse[EmployeeOrgRelResponse],
        summary="修改雇佣状态",
        description="修改员工在指定组织中的雇佣状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）"
    )
    async def update_org_status(
        employee_id: int = Query(..., description="员工ID"),
        org_id: int = Query(..., description="组织ID"),
        status: int = Query(..., description="新状态（-1-离职，0-停职，1-待入职，2-试用，3-在职）"),
    ):
        """修改员工雇佣状态"""
        try:
            rel = org_service.update_emp_org_status(
                employee_id=employee_id, org_id=org_id, status=status
            )
            return Resp.OK(data=EmployeeOrgRelResponse.from_entity(rel), message="状态更新成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/update-account-status",
        response_model=ItemResponse[EmployeeResponse],
        summary="修改账号状态",
        description="修改员工的账号状态（1-激活，-1-禁用），直接操作关联的用户账号"
    )
    async def update_account_status(
        employee_id: int = Query(..., description="员工ID"),
        account_status: int = Query(..., description="新账号状态（-1-已禁用，1-已激活）"),
    ):
        """修改员工账号状态（通过关联的 User.is_active）"""
        try:
            emp = org_service.update_account_status(
                employee_id=employee_id, account_status=account_status
            )
            return Resp.OK(data=_build_employee_response(emp), message="账号状态更新成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    return router


__all__ = ["create_employee_crud_router"]
