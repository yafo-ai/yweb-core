"""
组织管理模块 - 部门 CRUD API

提供部门的增删改查接口，包括树形操作、部门员工、部门负责人。
使用动词风格路由，只使用 GET 和 POST 请求。

设计原则（DDD 分层）：
- API 层只负责：参数验证、DTO 转换、异常处理、调用服务层
- 业务逻辑封装在领域模型和服务层
- 捕获 ValueError 统一处理
"""

from typing import Type, Optional, List, Callable, TYPE_CHECKING
from fastapi import APIRouter, Query

from yweb.response import Resp, PageResponse, ItemResponse, OkResponse

from ..schemas.department import (
    DepartmentCreate,
    DepartmentUpdate,
    DepartmentResponse,
    DepartmentTreeNode,
)
from ..schemas.employee import (
    EmployeeResponse,
    DeptLeaderCreate,
    DeptLeaderResponse,
)

if TYPE_CHECKING:
    from ..models import (
        AbstractDepartment,
        AbstractOrganization,
        AbstractEmployee,
        AbstractEmployeeOrgRel,
        AbstractEmployeeDeptRel,
        AbstractDepartmentLeader,
    )
    from ..services import BaseOrganizationService


def create_department_crud_router(
    dept_model: Type["AbstractDepartment"],
    org_model: Type["AbstractOrganization"],
    employee_model: Type["AbstractEmployee"] = None,
    emp_org_rel_model: Type["AbstractEmployeeOrgRel"] = None,
    emp_dept_rel_model: Type["AbstractEmployeeDeptRel"] = None,
    dept_leader_model: Type["AbstractDepartmentLeader"] = None,
    org_service: "BaseOrganizationService" = None,
    tree_node_builder: Optional[Callable] = None,
) -> APIRouter:
    """创建部门 CRUD 路由
    
    Args:
        dept_model: 部门模型类
        org_model: 组织模型类
        employee_model: 员工模型类（可选，用于部门员工功能）
        emp_org_rel_model: 员工-组织关联模型类（可选）
        emp_dept_rel_model: 员工-部门关联模型类（可选）
        dept_leader_model: 部门负责人模型类（可选）
        org_service: 组织服务实例（必须提供，用于业务操作）
        tree_node_builder: 自定义树节点构建函数（可选）
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list          - 获取部门列表（平铺）
        GET  /tree          - 获取部门树
        GET  /get           - 获取部门详情
        POST /create        - 创建部门
        POST /update        - 更新部门
        POST /move          - 移动部门
        POST /delete        - 删除部门
        GET  /employees     - 获取部门员工（需要 employee_model）
        POST /add-leader    - 添加部门负责人（需要 dept_leader_model）
        POST /remove-leader - 移除部门负责人（需要 dept_leader_model）
    """
    router = APIRouter()
    
    # ==================== 辅助函数（展示层逻辑） ====================
    
    def _build_tree_node(dept, include_options: set = None) -> dict:
        """构建树节点数据（展示层 DTO 转换）"""
        if tree_node_builder:
            return tree_node_builder(dept, dept.to_dict())
        
        include_options = include_options or set()
        
        # 使用 DTO 转换基础字段
        node = DepartmentTreeNode.from_entity(dept).model_dump()
        node["children"] = []
        
        # 处理附加信息
        if "employee_count" in include_options:
            if hasattr(dept, 'employee_dept_rels'):
                node["employee_count"] = len(dept.employee_dept_rels)
            else:
                node["employee_count"] = 0
        
        if "full_name" in include_options:
            if hasattr(dept, 'get_full_name'):
                node["full_name"] = dept.get_full_name()
        
        if "primary_leader_name" in include_options:
            if hasattr(dept, 'primary_leader') and dept.primary_leader:
                node["primary_leader_name"] = dept.primary_leader.name
        
        return node
    
    def _build_tree(depts: List, parent_id: Optional[int] = None, include_options: set = None) -> List[dict]:
        """递归构建部门树（展示层 DTO 转换）"""
        result = []
        for d in depts:
            if d.parent_id == parent_id:
                node = _build_tree_node(d, include_options)
                node["children"] = _build_tree(depts, d.id, include_options)
                result.append(node)
        return result
    
    # ==================== 查询接口（直接查询模型） ====================
    
    @router.get(
        "/list",
        response_model=PageResponse[DepartmentResponse],
        summary="获取部门列表",
        description="获取指定组织下的部门列表（平铺）"
    )
    async def list_departments(
        org_id: int = Query(..., description="组织ID"),
        is_active: Optional[bool] = Query(None, description="按状态筛选"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(100, ge=1, le=500, description="每页数量"),
    ):
        """获取部门列表"""
        query = dept_model.query.filter(dept_model.org_id == org_id)
        
        if is_active is not None:
            query = query.filter(dept_model.is_active == is_active)
        
        page_result = query.order_by(
            dept_model.level,
            dept_model.sort_order
        ).paginate(page=page, page_size=page_size)
        
        return Resp.OK(data=DepartmentResponse.from_page(page_result))
    
    @router.get(
        "/tree",
        response_model=OkResponse,
        summary="获取部门树",
        description="获取指定组织的部门树形结构"
    )
    async def get_department_tree(
        org_id: int = Query(..., description="组织ID"),
        include: Optional[str] = Query(
            None, 
            description="附加信息，逗号分隔（employee_count,full_name,primary_leader_name）"
        ),
    ):
        """获取部门树"""
        org = org_model.get(org_id)
        if not org:
            return Resp.NotFound(message=f"组织不存在: {org_id}")
        
        include_options = set(include.split(",")) if include else set()
        
        depts = dept_model.query.filter(
            dept_model.org_id == org_id,
            dept_model.is_active == True
        ).order_by(dept_model.level, dept_model.sort_order).all()
        
        tree = _build_tree(depts, None, include_options)
        
        return Resp.OK(data=tree)
    
    @router.get(
        "/get",
        response_model=ItemResponse[DepartmentResponse],
        summary="获取部门详情",
        description="根据部门ID获取详情"
    )
    async def get_department(
        dept_id: int = Query(..., description="部门ID"),
        include: Optional[str] = Query(
            None, 
            description="附加信息，逗号分隔（employee_count,full_name,primary_leader_name）"
        ),
    ):
        """获取部门详情"""
        dept = dept_model.get(dept_id)
        if not dept:
            return Resp.NotFound(message=f"部门不存在: {dept_id}")
        
        # 无附加信息时直接使用 from_entity
        if not include:
            return Resp.OK(data=DepartmentResponse.from_entity(dept))
        
        # 有附加信息时，构建字典再转换
        data = dept.to_dict()
        include_options = set(include.split(","))
        
        if "employee_count" in include_options:
            if hasattr(dept, 'employee_dept_rels'):
                data["employee_count"] = len(dept.employee_dept_rels)
            else:
                data["employee_count"] = 0
        
        if "full_name" in include_options:
            if hasattr(dept, 'get_full_name'):
                data["full_name"] = dept.get_full_name()
        
        if "primary_leader_name" in include_options:
            if hasattr(dept, 'primary_leader') and dept.primary_leader:
                data["primary_leader_name"] = dept.primary_leader.name
        
        return Resp.OK(data=DepartmentResponse.from_dict(data))
    
    # ==================== 写入接口（调用服务层） ====================
    
    @router.post(
        "/create",
        response_model=ItemResponse[DepartmentResponse],
        summary="创建部门",
        description="创建新的部门"
    )
    async def create_department(data: DepartmentCreate):
        """创建部门"""
        try:
            dept = org_service.create_dept(
                org_id=data.org_id,
                name=data.name,
                code=data.code,
                parent_id=data.parent_id,
                sort_order=data.sort_order,
                note=data.note,
            )
            return Resp.OK(data=DepartmentResponse.from_entity(dept), message="创建成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/update",
        response_model=ItemResponse[DepartmentResponse],
        summary="更新部门",
        description="更新部门信息"
    )
    async def update_department(
        data: DepartmentUpdate,
        dept_id: int = Query(..., description="部门ID"),
    ):
        """更新部门"""
        try:
            update_data = data.model_dump(exclude_unset=True)
            dept = org_service.update_dept(dept_id=dept_id, **update_data)
            return Resp.OK(data=DepartmentResponse.from_entity(dept), message="更新成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/move",
        response_model=ItemResponse[DepartmentResponse],
        summary="移动部门",
        description="移动部门到新的父部门下"
    )
    async def move_department(
        dept_id: int = Query(..., description="部门ID"),
        new_parent_id: Optional[int] = Query(None, description="新父部门ID，为空表示移到根级"),
    ):
        """移动部门"""
        try:
            dept = org_service.move_dept(dept_id=dept_id, new_parent_id=new_parent_id)
            return Resp.OK(data=DepartmentResponse.from_entity(dept), message="移动成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    @router.post(
        "/delete",
        response_model=OkResponse,
        summary="删除部门",
        description="删除部门（软删除）"
    )
    async def delete_department(
        dept_id: int = Query(..., description="部门ID"),
        force: bool = Query(False, description="是否强制删除（包括子部门）"),
    ):
        """删除部门"""
        try:
            result = org_service.delete_dept(
                dept_id=dept_id, 
                force=force, 
                promote_children=True
            )
            return Resp.OK(data={"id": dept_id, **result}, message="删除成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    # ==================== 部门员工（查询接口） ====================
    
    if employee_model and emp_dept_rel_model:
        @router.get(
            "/employees",
            response_model=PageResponse[EmployeeResponse],
            summary="获取部门员工",
            description="获取指定部门的所有员工"
        )
        async def get_dept_employees(
            dept_id: int = Query(..., description="部门ID"),
            emp_status: Optional[int] = Query(None, description="按雇佣状态筛选（-1-离职，0-停职，1-待入职，2-试用，3-在职）"),
            account_status: Optional[int] = Query(None, description="按账号状态筛选（-1-已禁用，0-未激活，1-已激活）"),
            page: int = Query(1, ge=1, description="页码"),
            page_size: int = Query(20, ge=1, le=100, description="每页数量"),
        ):
            """获取部门员工"""
            dept = dept_model.get(dept_id)
            if not dept:
                return Resp.NotFound(message=f"部门不存在: {dept_id}")
            
            # 构建员工ID集合（先按部门关联筛选，再按状态过滤）
            dept_rel_query = emp_dept_rel_model.query.filter_by(dept_id=dept_id)
            dept_emp_ids = {r.employee_id for r in dept_rel_query.all()}
            
            if not dept_emp_ids:
                from yweb.orm import Page
                return Resp.OK(data=Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0))
            
            # 按雇佣状态筛选（通过 org_rel）
            if emp_status is not None and emp_org_rel_model:
                status_emp_ids = {
                    r.employee_id for r in emp_org_rel_model.query.filter(
                        emp_org_rel_model.employee_id.in_(dept_emp_ids),
                        emp_org_rel_model.org_id == dept.org_id,
                        emp_org_rel_model.status == emp_status
                    ).all()
                }
                dept_emp_ids = dept_emp_ids & status_emp_ids
            
            # 按账号状态筛选（从 user 关联推导）
            if account_status is not None and hasattr(employee_model, 'user_id'):
                if account_status == 0:
                    # 未激活 = 没有关联用户
                    no_account = employee_model.query.filter(
                        employee_model.id.in_(dept_emp_ids),
                        employee_model.user_id.is_(None)
                    )
                    dept_emp_ids = {e.id for e in no_account.all()}
                elif account_status in (1, -1):
                    user_rel = getattr(employee_model, 'user', None)
                    if user_rel is not None and hasattr(user_rel, 'property'):
                        user_model_cls = user_rel.property.mapper.class_
                        is_active_target = (account_status == 1)
                        matching_user_ids = {
                            u.id for u in user_model_cls.query.filter(
                                user_model_cls.is_active == is_active_target
                            ).all()
                        }
                        has_account = employee_model.query.filter(
                            employee_model.id.in_(dept_emp_ids),
                            employee_model.user_id.in_(matching_user_ids)
                        )
                        dept_emp_ids = {e.id for e in has_account.all()}
            
            if not dept_emp_ids:
                from yweb.orm import Page
                return Resp.OK(data=Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0))
            
            # 分页查询员工
            page_result = employee_model.query.filter(
                employee_model.id.in_(dept_emp_ids)
            ).order_by(employee_model.id).paginate(page=page, page_size=page_size)
            
            rows = []
            for emp in page_result.rows:
                data = emp.to_dict()
                
                # 注入推导的 account_status
                if hasattr(emp, 'user_id'):
                    user_id = getattr(emp, 'user_id', None)
                    if user_id is None:
                        data["account_status"] = 0
                    else:
                        user = getattr(emp, 'user', None)
                        data["account_status"] = 1 if (user and getattr(user, 'is_active', False)) else -1
                
                if emp_org_rel_model:
                    org_rel = emp_org_rel_model.query.filter_by(
                        employee_id=emp.id,
                        org_id=dept.org_id
                    ).first()
                    if org_rel:
                        data["emp_no"] = org_rel.emp_no
                        data["position"] = org_rel.position
                        data["status"] = org_rel.status
                
                rows.append(EmployeeResponse.from_dict(data))
            
            page_result.rows = rows
            return Resp.OK(data=page_result)
    
    # ==================== 部门负责人（调用服务层） ====================
    
    if dept_leader_model and employee_model and emp_dept_rel_model:
        @router.post(
            "/add-leader",
            response_model=ItemResponse[DeptLeaderResponse],
            summary="添加部门负责人",
            description="将员工设为部门负责人"
        )
        async def add_dept_leader(data: DeptLeaderCreate):
            """添加部门负责人"""
            try:
                leader = org_service.add_dept_leader(
                    dept_id=data.dept_id,
                    employee_id=data.employee_id,
                    set_as_primary=data.set_primary,
                )
                
                emp = employee_model.get(data.employee_id)
                response_data = leader.to_dict()
                response_data["employee_name"] = emp.name if emp else None
                
                return Resp.OK(data=DeptLeaderResponse.from_dict(response_data), message="设置成功")
            except ValueError as e:
                return Resp.BadRequest(message=str(e))
        
        @router.post(
            "/remove-leader",
            response_model=OkResponse,
            summary="移除部门负责人",
            description="取消员工的部门负责人身份"
        )
        async def remove_dept_leader(
            employee_id: int = Query(..., description="员工ID"),
            dept_id: int = Query(..., description="部门ID"),
        ):
            """移除部门负责人"""
            try:
                org_service.remove_dept_leader(dept_id=dept_id, employee_id=employee_id)
                return Resp.OK(
                    data={"employee_id": employee_id, "dept_id": dept_id}, 
                    message="移除成功"
                )
            except ValueError as e:
                return Resp.BadRequest(message=str(e))
    
    return router


__all__ = ["create_department_crud_router"]
