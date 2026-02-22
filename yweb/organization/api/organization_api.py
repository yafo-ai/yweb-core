"""
组织管理模块 - 组织 CRUD API

提供组织的增删改查接口。
使用动词风格路由，只使用 GET 和 POST 请求。

设计原则（DDD 分层）：
- API 层只负责：参数验证、DTO 转换、异常处理、调用服务层
- 业务逻辑封装在领域模型和服务层
- 捕获 ValueError 统一处理
"""

from typing import Type, Optional, TYPE_CHECKING
from fastapi import APIRouter, Query

from yweb.response import Resp, PageResponse, ItemResponse, OkResponse

from ..schemas.organization import (
    OrganizationCreate,
    OrganizationUpdate,
    OrganizationResponse,
)

if TYPE_CHECKING:
    from ..models import AbstractOrganization
    from ..services import BaseOrganizationService


def create_organization_crud_router(
    org_model: Type["AbstractOrganization"],
    org_service: Optional["BaseOrganizationService"] = None,
) -> APIRouter:
    """创建组织 CRUD 路由
    
    Args:
        org_model: 组织模型类
        org_service: 组织服务实例（必须提供，用于业务操作）
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list   - 获取组织列表
        GET  /get    - 获取组织详情
        POST /create - 创建组织
        POST /update - 更新组织
        POST /delete - 删除组织
    """
    router = APIRouter()
    
    # ==================== 查询接口（直接查询模型） ====================
    
    @router.get(
        "/list",
        response_model=PageResponse[OrganizationResponse],
        summary="获取组织列表",
        description="获取所有组织，支持按状态筛选"
    )
    async def list_organizations(
        is_active: Optional[bool] = Query(None, description="按状态筛选"),
        keyword: Optional[str] = Query(None, description="按名称/编码搜索"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """获取组织列表"""
        query = org_model.query
        
        if is_active is not None:
            query = query.filter(org_model.is_active == is_active)
        
        if keyword:
            query = query.filter(
                (org_model.name.contains(keyword)) |
                (org_model.code.contains(keyword))
            )
        
        page_result = query.order_by(org_model.id).paginate(page=page, page_size=page_size)  # type: ignore[attr-defined]
        
        return Resp.OK(data=OrganizationResponse.from_page(page_result))
    
    @router.get(
        "/get",
        response_model=ItemResponse[OrganizationResponse],
        summary="获取组织详情",
        description="根据组织ID获取详情"
    )
    async def get_organization(
        org_id: int = Query(..., description="组织ID"),
    ):
        """获取组织详情"""
        org = org_model.get(org_id)
        if not org:
            return Resp.NotFound(message=f"组织不存在: {org_id}")
        
        return Resp.OK(data=OrganizationResponse.from_entity(org))
    
    # ==================== 写入接口（调用服务层） ====================
    
    if org_service is None:
        return router  # 只读模式：未提供 service，仅注册查询接口
    
    @router.post(
        "/create",
        response_model=ItemResponse[OrganizationResponse],
        summary="创建组织",
        description="创建新的组织"
    )
    async def create_organization(data: OrganizationCreate):
        """创建组织"""
        try:
            org = org_service.create_org(
                name=data.name,
                code=data.code,
                note=data.note,
                caption=data.caption,
                external_source=data.external_source,
                external_corp_id=data.external_corp_id,
            )
            return Resp.OK(data=OrganizationResponse.from_entity(org), message="创建成功")
        except ValueError as e:
            return Resp.Conflict(message=str(e))
    
    @router.post(
        "/update",
        response_model=ItemResponse[OrganizationResponse],
        summary="更新组织",
        description="更新组织信息"
    )
    async def update_organization(
        data: OrganizationUpdate,
        org_id: int = Query(..., description="组织ID"),
    ):
        """更新组织"""
        try:
            update_data = data.model_dump(exclude_unset=True)
            org = org_service.update_org(org_id=org_id, **update_data)
            return Resp.OK(data=OrganizationResponse.from_entity(org), message="更新成功")
        except ValueError as e:
            return Resp.Conflict(message=str(e))
    
    @router.post(
        "/delete",
        response_model=OkResponse,
        summary="删除组织",
        description="删除组织（软删除，级联删除策略会阻止存在部门/员工时删除）"
    )
    async def delete_organization(
        org_id: int = Query(..., description="组织ID"),
        force: bool = Query(False, description="是否强制删除"),
    ):
        """删除组织"""
        try:
            org_service.delete_org(org_id=org_id, force=force)
            return Resp.OK(data={"id": org_id}, message="删除成功")
        except ValueError as e:
            return Resp.BadRequest(message=str(e))
    
    return router


__all__ = ["create_organization_crud_router"]
