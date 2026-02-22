"""
权限模块 - API 资源管理

提供 API 资源的管理接口，包括自动扫描路由功能。
使用动词风格路由，只使用 GET 和 POST 请求。
"""

from typing import Type, Optional, List, TYPE_CHECKING
from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, ConfigDict

from yweb.response import Resp

if TYPE_CHECKING:
    from ..models import AbstractAPIResource, AbstractPermission


class APIResourceCreate(BaseModel):
    """创建 API 资源请求"""
    path: str = Field(..., description="API 路径")
    method: str = Field(..., description="HTTP 方法")
    api_name: Optional[str] = Field(None, description="API 名称")
    permission_code: Optional[str] = Field(None, description="关联的权限编码")
    is_public: bool = Field(False, description="是否公开访问")
    module: Optional[str] = Field(None, description="所属模块")


class APIResourceUpdate(BaseModel):
    """更新 API 资源请求"""
    api_name: Optional[str] = Field(None, description="API 名称")
    permission_code: Optional[str] = Field(None, description="关联的权限编码")
    is_public: Optional[bool] = Field(None, description="是否公开访问")
    is_active: Optional[bool] = Field(None, description="是否启用")
    module: Optional[str] = Field(None, description="所属模块")


class APIResourceResponse(BaseModel):
    """API 资源响应
    
    使用 extra="allow" 允许返回用户扩展的字段。
    """
    id: int
    path: str
    method: str
    api_name: Optional[str]
    permission_id: Optional[int]
    permission_code: Optional[str] = None
    is_public: bool
    is_active: bool
    module: Optional[str]
    
    model_config = ConfigDict(from_attributes=True, extra="allow")


def create_api_resource_router(
    api_resource_model: Type["AbstractAPIResource"],
    permission_model: Type["AbstractPermission"],
) -> APIRouter:
    """创建 API 资源管理路由
    
    Args:
        api_resource_model: API 资源模型类
        permission_model: 权限模型类
        
    Returns:
        APIRouter
        
    生成的路由:
        GET  /list             - 获取 API 资源列表
        GET  /get              - 获取 API 资源详情
        POST /create           - 创建 API 资源
        POST /update           - 更新 API 资源
        POST /delete           - 删除 API 资源
        POST /scan             - 扫描路由
        GET  /modules/list     - 获取模块列表
        POST /batch-set-permission - 批量设置权限
    """
    router = APIRouter()
    
    @router.get(
        "/list",
        summary="获取 API 资源列表",
        description="获取所有 API 资源"
    )
    async def list_api_resources(
        module: Optional[str] = Query(None, description="按模块筛选"),
        method: Optional[str] = Query(None, description="按方法筛选"),
        is_public: Optional[bool] = Query(None, description="按公开状态筛选"),
        has_permission: Optional[bool] = Query(None, description="是否已配置权限"),
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
    ):
        """获取 API 资源列表"""
        query = api_resource_model.query.filter(api_resource_model.is_active == True)
        
        if module:
            query = query.filter(api_resource_model.module == module)
        if method:
            query = query.filter(api_resource_model.method == method.upper())
        if is_public is not None:
            query = query.filter(api_resource_model.is_public == is_public)
        if has_permission is not None:
            if has_permission:
                query = query.filter(api_resource_model.permission_id.isnot(None))
            else:
                query = query.filter(api_resource_model.permission_id.is_(None))
        
        # 使用框架的分页方法
        page_result = query.order_by(
            api_resource_model.module,
            api_resource_model.path,
            api_resource_model.method
        ).paginate(page=page, page_size=page_size)
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        rows = []
        for item in page_result.rows:
            item_data = item.to_dict()
            if item.permission_id:
                perm = permission_model.get(item.permission_id)
                item_data["permission_code"] = perm.code if perm else None
            rows.append(APIResourceResponse(**item_data).model_dump())
        
        page_result.rows = rows
        return Resp.OK(data=page_result)
    
    @router.get(
        "/get",
        summary="获取 API 资源详情",
    )
    async def get_api_resource(
        resource_id: int = Query(..., description="资源 ID"),
    ):
        """获取 API 资源详情"""
        resource = api_resource_model.get(resource_id)
        if not resource:
            return Resp.NotFound(message="API 资源不存在")
        
        # 使用 to_dict() 获取完整数据（包含用户扩展字段）
        result = resource.to_dict()
        if resource.permission_id:
            perm = permission_model.get(resource.permission_id)
            result["permission_code"] = perm.code if perm else None
        
        return Resp.OK(data=APIResourceResponse(**result).model_dump())
    
    @router.post(
        "/create",
        summary="创建 API 资源",
        description="手动创建 API 资源"
    )
    async def create_api_resource(data: APIResourceCreate):
        """创建 API 资源"""
        # 检查是否存在
        existing = api_resource_model.query.filter_by(
            path=data.path,
            method=data.method.upper()
        ).first()
        if existing:
            return Resp.Conflict(message=f"API 资源已存在: {data.method} {data.path}")
        
        # 处理权限关联
        permission_id = None
        if data.permission_code:
            perm = permission_model.query.filter_by(code=data.permission_code).first()
            if not perm:
                return Resp.NotFound(message=f"权限不存在: {data.permission_code}")
            permission_id = perm.id
        
        resource = api_resource_model(
            path=data.path,
            method=data.method.upper(),
            api_name=data.api_name,
            permission_id=permission_id,
            is_public=data.is_public,
            module=data.module,
        )
        resource.save(True)
        
        return Resp.OK(data=APIResourceResponse.model_validate(resource), message="创建成功")
    
    @router.post(
        "/update",
        summary="更新 API 资源",
    )
    async def update_api_resource(
        data: APIResourceUpdate,
        resource_id: int = Query(..., description="资源 ID"),
    ):
        """更新 API 资源"""
        resource = api_resource_model.get(resource_id)
        if not resource:
            return Resp.NotFound(message="API 资源不存在")
        
        if data.api_name is not None:
            resource.api_name = data.api_name
        if data.is_public is not None:
            resource.is_public = data.is_public
        if data.is_active is not None:
            resource.is_active = data.is_active
        if data.module is not None:
            resource.module = data.module
        
        if data.permission_code is not None:
            if data.permission_code == "":
                resource.permission_id = None
            else:
                perm = permission_model.query.filter_by(code=data.permission_code).first()
                if not perm:
                    return Resp.NotFound(message=f"权限不存在: {data.permission_code}")
                resource.permission_id = perm.id
        
        resource.save(True)
        
        return Resp.OK(data={"id": resource_id}, message="更新成功")
    
    @router.post(
        "/delete",
        summary="删除 API 资源",
    )
    async def delete_api_resource(
        resource_id: int = Query(..., description="资源 ID"),
    ):
        """删除 API 资源"""
        resource = api_resource_model.get(resource_id)
        if not resource:
            return Resp.NotFound(message="API 资源不存在")
        
        resource.delete()
        
        return Resp.OK(data={"id": resource_id}, message="删除成功")
    
    @router.post(
        "/scan",
        summary="扫描路由",
        description="自动扫描 FastAPI 应用的所有路由并注册为 API 资源"
    )
    async def scan_routes(
        request: Request,
        overwrite: bool = Query(False, description="是否覆盖已存在的资源"),
        include_patterns: Optional[List[str]] = Query(None, description="包含的路径模式"),
        exclude_patterns: Optional[List[str]] = Query(
            ["/docs", "/redoc", "/openapi.json"],
            description="排除的路径模式"
        ),
    ):
        """扫描并注册所有 API 路由"""
        import re
        
        app = request.app
        scanned = []
        created = []
        skipped = []
        
        for route in app.routes:
            # 跳过非 API 路由
            if not hasattr(route, 'methods') or not hasattr(route, 'path'):
                continue
            
            path = route.path
            
            # 检查排除模式
            if exclude_patterns:
                excluded = False
                for pattern in exclude_patterns:
                    if path.startswith(pattern) or re.match(pattern, path):
                        excluded = True
                        break
                if excluded:
                    continue
            
            # 检查包含模式
            if include_patterns:
                included = False
                for pattern in include_patterns:
                    if path.startswith(pattern) or re.match(pattern, path):
                        included = True
                        break
                if not included:
                    continue
            
            # 获取路由名称
            route_name = getattr(route, 'name', None) or path
            
            for method in route.methods:
                if method in ['HEAD', 'OPTIONS']:
                    continue
                
                scanned.append({"path": path, "method": method})
                
                # 检查是否存在
                existing = api_resource_model.query.filter_by(
                    path=path,
                    method=method
                ).first()
                
                if existing:
                    if overwrite:
                        existing.api_name = route_name
                        existing.save(True)
                        created.append({"path": path, "method": method, "action": "updated"})
                    else:
                        skipped.append({"path": path, "method": method, "reason": "已存在"})
                else:
                    resource = api_resource_model(
                        path=path,
                        method=method,
                        api_name=route_name,
                    )
                    resource.save(True)
                    created.append({"path": path, "method": method, "action": "created"})
        
        return Resp.OK(data={
            "scanned_count": len(scanned),
            "created_count": len([c for c in created if c["action"] == "created"]),
            "updated_count": len([c for c in created if c["action"] == "updated"]),
            "skipped_count": len(skipped),
            "created": created,
            "skipped": skipped,
        }, message="扫描完成")
    
    @router.get(
        "/modules/list",
        summary="获取模块列表",
        description="获取所有 API 资源模块"
    )
    async def list_modules():
        """获取所有模块"""
        from sqlalchemy import distinct
        
        modules = api_resource_model.query.with_entities(
            distinct(api_resource_model.module)
        ).filter(
            api_resource_model.module.isnot(None)
        ).all()
        
        return Resp.OK(data={"modules": [m[0] for m in modules if m[0]]})
    
    @router.post(
        "/batch-set-permission",
        summary="批量设置权限",
        description="批量为 API 资源设置权限"
    )
    async def batch_set_permission(
        resource_ids: List[int],
        permission_code: str,
    ):
        """批量设置权限"""
        perm = permission_model.query.filter_by(code=permission_code).first()
        if not perm:
            return Resp.NotFound(message=f"权限不存在: {permission_code}")
        
        updated = 0
        for resource_id in resource_ids:
            resource = api_resource_model.get(resource_id)
            if resource:
                resource.permission_id = perm.id
                resource.save(True)
                updated += 1
        
        return Resp.OK(data={
            "updated_count": updated,
            "permission_code": permission_code,
        }, message="批量设置完成")
    
    return router


__all__ = ["create_api_resource_router"]
