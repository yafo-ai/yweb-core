"""
权限模块 - 权限 CRUD API

提供权限的增删改查接口。
使用动词风格路由，只使用 GET 和 POST 请求。
"""

from typing import Type, Optional, List, TYPE_CHECKING
from fastapi import APIRouter, Query

from yweb.response import Resp

from ..schemas.permission import (
    PermissionCreate,
    PermissionUpdate,
    PermissionResponse,
    PermissionListResponse,
)
from ..exceptions import (
    PermissionNotFoundException,
    DuplicatePermissionException,
)

if TYPE_CHECKING:
    from ..models import AbstractPermission


def create_permission_crud_router(
    permission_model: Type["AbstractPermission"],
) -> APIRouter:
    """创建权限 CRUD 路由
    
    Args:
        permission_model: 权限模型类
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list           - 获取权限列表
        GET  /get            - 获取权限详情
        POST /create         - 创建权限
        POST /update         - 更新权限
        POST /delete         - 删除权限
        GET  /modules/list   - 获取模块列表
        GET  /resources/list - 获取资源列表
    """
    router = APIRouter()
    
    @router.get(
        "/list",
        response_model=PermissionListResponse,
        summary="获取权限列表",
        description="获取所有权限，支持按模块、资源筛选"
    )
    async def list_permissions(
        module: Optional[str] = Query(None, description="按模块筛选"),
        resource: Optional[str] = Query(None, description="按资源筛选"),
        is_active: Optional[bool] = Query(None, description="按状态筛选"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """获取权限列表"""
        query = permission_model.query
        
        if module:
            query = query.filter(permission_model.module == module)
        if resource:
            query = query.filter(permission_model.resource == resource)
        if is_active is not None:
            query = query.filter(permission_model.is_active == is_active)
        
        # 使用框架的分页方法
        page_result = query.order_by(
            permission_model.module,
            permission_model.sort_order
        ).paginate(page=page, page_size=page_size)
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段），再用 Schema 包装
        page_result.rows = [PermissionResponse(**p.to_dict()).model_dump() for p in page_result.rows]
        return Resp.OK(data=page_result)
    
    @router.get(
        "/get",
        response_model=PermissionResponse,
        summary="获取权限详情",
        description="根据权限编码获取详情"
    )
    async def get_permission(
        code: str = Query(..., description="权限编码"),
    ):
        """获取权限详情"""
        permission = permission_model.query.filter_by(code=code).first()
        if not permission:
            return Resp.NotFound(message=f"权限不存在: {code}")
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        return Resp.OK(data=PermissionResponse(**permission.to_dict()).model_dump())
    
    @router.post(
        "/create",
        response_model=PermissionResponse,
        summary="创建权限",
        description="创建新的权限"
    )
    async def create_permission(data: PermissionCreate):
        """创建权限"""
        # 检查是否存在
        existing = permission_model.query.filter_by(code=data.code).first()
        if existing:
            return Resp.Conflict(message=f"权限已存在: {data.code}")
        
        # 解析 resource 和 action
        resource = data.resource
        action = data.action
        if not resource or not action:
            if ":" in data.code:
                parts = data.code.split(":", 1)
                resource = resource or parts[0]
                action = action or parts[1]
            else:
                resource = resource or data.code
                action = action or "*"
        
        permission = permission_model(
            code=data.code,
            name=data.name,
            resource=resource,
            action=action,
            description=data.description,
            module=data.module,
        )
        permission.save(True)
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        return Resp.OK(data=PermissionResponse(**permission.to_dict()).model_dump(), message="创建成功")
    
    @router.post(
        "/update",
        response_model=PermissionResponse,
        summary="更新权限",
        description="更新权限信息"
    )
    async def update_permission(
        data: PermissionUpdate,
        code: str = Query(..., description="权限编码"),
    ):
        """更新权限"""
        permission = permission_model.query.filter_by(code=code).first()
        if not permission:
            return Resp.NotFound(message=f"权限不存在: {code}")
        
        if data.name is not None:
            permission.name = data.name
        if data.description is not None:
            permission.description = data.description
        if data.is_active is not None:
            permission.is_active = data.is_active
        if data.module is not None:
            permission.module = data.module
        if data.sort_order is not None:
            permission.sort_order = data.sort_order
        
        permission.save(True)
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        return Resp.OK(data=PermissionResponse(**permission.to_dict()).model_dump(), message="更新成功")
    
    @router.post(
        "/delete",
        summary="删除权限",
        description="删除权限（软删除）"
    )
    async def delete_permission(
        code: str = Query(..., description="权限编码"),
    ):
        """删除权限"""
        permission = permission_model.query.filter_by(code=code).first()
        if not permission:
            return Resp.NotFound(message=f"权限不存在: {code}")
        
        permission.delete()
        
        return Resp.OK(data={"code": code}, message="删除成功")
    
    @router.get(
        "/modules/list",
        summary="获取模块列表",
        description="获取所有权限模块"
    )
    async def list_modules():
        """获取所有模块"""
        from sqlalchemy import distinct
        
        modules = permission_model.query.with_entities(
            distinct(permission_model.module)
        ).filter(
            permission_model.module.isnot(None)
        ).all()
        
        return Resp.OK(data={"modules": [m[0] for m in modules if m[0]]})
    
    @router.get(
        "/resources/list",
        summary="获取资源列表",
        description="获取所有权限资源类型"
    )
    async def list_resources():
        """获取所有资源类型"""
        from sqlalchemy import distinct
        
        resources = permission_model.query.with_entities(
            distinct(permission_model.resource)
        ).all()
        
        return Resp.OK(data={"resources": [r[0] for r in resources if r[0]]})
    
    return router


__all__ = ["create_permission_crud_router"]
