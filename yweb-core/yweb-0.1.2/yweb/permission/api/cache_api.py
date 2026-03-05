"""
权限模块 - 缓存管理 API

提供缓存查看和管理接口。
"""

from typing import Optional, List
from fastapi import APIRouter, Query

from yweb.response import Resp

from ..cache import permission_cache, configure_cache


def create_cache_router() -> APIRouter:
    """创建缓存管理路由
    
    Returns:
        APIRouter
    """
    router = APIRouter()
    
    @router.get(
        "/stats",
        summary="获取缓存统计",
        description="获取权限缓存的统计信息"
    )
    async def get_cache_stats():
        """获取缓存统计信息"""
        return Resp.OK(data=permission_cache.get_cache_info())
    
    @router.post(
        "/invalidate",
        summary="失效缓存",
        description="使指定缓存失效"
    )
    async def invalidate_cache(
        subject_id: Optional[str] = Query(None, description="失效指定用户的缓存"),
        role_code: Optional[str] = Query(None, description="失效指定角色的缓存"),
        all: bool = Query(False, description="失效所有缓存"),
    ):
        """失效缓存"""
        if all:
            permission_cache.invalidate_all()
            return Resp.OK(message="所有缓存已失效")
        
        if subject_id:
            permission_cache.invalidate_subject(subject_id)
            return Resp.OK(data={"subject_id": subject_id}, message=f"用户 {subject_id} 缓存已失效")
        
        if role_code:
            permission_cache.invalidate_role(role_code)
            return Resp.OK(data={"role_code": role_code}, message=f"角色 {role_code} 缓存已失效")
        
        return Resp.BadRequest(message="请指定要失效的缓存类型")
    
    @router.post(
        "/invalidate-batch",
        summary="批量失效缓存",
        description="批量失效多个用户的缓存"
    )
    async def invalidate_cache_batch(subject_ids: List[str]):
        """批量失效用户缓存"""
        permission_cache.invalidate_subjects_batch(subject_ids)
        return Resp.OK(data={"count": len(subject_ids)}, message="批量失效完成")
    
    @router.post(
        "/clear",
        summary="清空缓存",
        description="清空所有缓存数据"
    )
    async def clear_cache():
        """清空所有缓存"""
        permission_cache.clear()
        return Resp.OK(message="缓存已清空")
    
    @router.post(
        "/reset-stats",
        summary="重置统计",
        description="重置缓存统计数据"
    )
    async def reset_stats():
        """重置缓存统计"""
        permission_cache.reset_stats()
        return Resp.OK(message="统计已重置")
    
    @router.post(
        "/configure",
        summary="配置缓存",
        description="重新配置缓存参数（会清空现有缓存）"
    )
    async def configure(
        maxsize: Optional[int] = Query(None, ge=100, le=1000000, description="最大缓存条目数"),
        ttl: Optional[int] = Query(None, ge=10, le=86400, description="过期时间（秒）"),
        enable_stats: Optional[bool] = Query(None, description="是否启用统计"),
    ):
        """重新配置缓存"""
        if maxsize is None and ttl is None and enable_stats is None:
            return Resp.BadRequest(message="请指定要配置的参数")
        
        configure_cache(
            maxsize=maxsize,
            ttl=ttl,
            enable_stats=enable_stats,
        )
        
        return Resp.OK(data={"config": permission_cache.get_cache_info()}, message="缓存已重新配置")
    
    return router


__all__ = ["create_cache_router"]
