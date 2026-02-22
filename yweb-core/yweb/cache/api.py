"""
缓存模块 - 通用缓存管理 API

提供所有 @cached 函数的统一查看和管理接口。

使用示例:
    from yweb.cache import create_cache_router

    app = FastAPI()
    app.include_router(
        create_cache_router(),
        prefix="/api/cache",
        tags=["缓存管理"],
    )
"""

from typing import Any, Dict, List, Optional, Union

from fastapi import APIRouter, Query
from pydantic import Field

from yweb.orm import DTO
from yweb.response import ItemResponse, OkResponse, Resp

from .decorators import cache_registry
from .invalidation import cache_invalidator


class CacheFunctionInfoResponse(DTO):
    """缓存函数摘要"""
    name: str = ""
    module: str = ""
    ttl: int = 0
    backend: str = ""
    key_prefix: str = ""


class CacheFunctionsResponse(DTO):
    """缓存函数列表响应"""
    total: int = 0
    functions: List[CacheFunctionInfoResponse] = Field(default_factory=list)


class CacheFunctionStatsResponse(DTO):
    """单函数缓存统计响应"""
    function: str = ""
    backend: str = ""
    ttl: int = 0
    hits: int = 0
    misses: int = 0
    invalidations: int = 0
    hit_rate: str = "0.00%"
    size: Optional[int] = None
    maxsize: Optional[int] = None
    prefix: Optional[str] = None


class CacheSummaryStatsResponse(DTO):
    """汇总缓存统计响应"""
    total_functions: int = 0
    total_hits: int = 0
    total_misses: int = 0
    total_hit_rate: float = 0.0
    functions: Dict[str, CacheFunctionStatsResponse] = Field(default_factory=dict)


class CacheEntryResponse(DTO):
    """缓存条目预览"""
    key: str = ""
    ttl_remaining: Optional[int] = None
    value_type: str = ""
    value_size: int = 0
    value_preview: Any = None


class CacheEntriesResponse(DTO):
    """缓存条目列表响应"""
    function: str = ""
    total: int = 0
    entries: List[CacheEntryResponse] = Field(default_factory=list)


class CacheInvalidatorRegistrationsResponse(DTO):
    """自动失效注册信息响应"""
    enabled: bool = True
    models_count: int = 0
    registrations: Dict[str, List[Dict[str, Any]]] = Field(default_factory=dict)


class CacheInvalidatorToggleResponse(DTO):
    """自动失效开关响应"""
    enabled: bool = True


CacheStatsResponse = Union[CacheSummaryStatsResponse, CacheFunctionStatsResponse]


def create_cache_router() -> APIRouter:
    """创建通用缓存管理路由
    
    提供以下端点:
        - GET  /functions                  列出所有缓存函数
        - GET  /stats                      获取缓存统计（汇总或指定函数）
        - GET  /entries                    查看指定函数的缓存条目列表（预览）
        - GET  /entry                      查看指定函数的单个缓存条目（预览）
        - POST /clear                      清空缓存（全部或指定函数）
        - GET  /invalidator/registrations  查看自动失效注册
        - POST /invalidator/toggle         启用/禁用自动失效
    
    Returns:
        APIRouter
    """
    router = APIRouter()
    
    @router.get(
        "/functions",
        summary="列出缓存函数",
        description="列出所有通过 @cached 装饰的函数及其配置信息",
        response_model=ItemResponse[CacheFunctionsResponse],
    )
    async def list_functions():
        """列出所有已注册的缓存函数"""
        functions = cache_registry.list_functions()
        return Resp.OK(
            data=CacheFunctionsResponse(
                total=len(functions),
                functions=[CacheFunctionInfoResponse.from_dict(item) for item in functions],
            )
        )
    
    @router.get(
        "/stats",
        summary="获取缓存统计",
        description="获取所有缓存函数的统计信息，或指定函数的统计",
        response_model=ItemResponse[CacheStatsResponse],
    )
    async def get_stats(
        function_name: Optional[str] = Query(
            None, description="指定函数名，不指定则返回汇总统计"
        ),
    ):
        """获取缓存统计信息"""
        if function_name:
            func = cache_registry.get(function_name)
            if func is None:
                return Resp.NotFound(message=f"缓存函数 '{function_name}' 不存在")
            return Resp.OK(data=CacheFunctionStatsResponse.from_dict(func.stats()))
        
        return Resp.OK(data=CacheSummaryStatsResponse.from_dict(cache_registry.get_all_stats()))
    
    @router.get(
        "/entries",
        summary="查看缓存条目列表",
        description="查看指定缓存函数的条目列表（返回脱敏预览，不返回完整原始值）",
        response_model=ItemResponse[CacheEntriesResponse],
    )
    async def list_entries(
        function_name: str = Query(..., description="缓存函数名"),
        limit: int = Query(50, ge=1, le=100, description="最多返回条目数"),
    ):
        """查看指定函数的缓存条目列表。"""
        result = cache_registry.list_entries(function_name, limit=limit)
        if result is None:
            return Resp.NotFound(message=f"缓存函数 '{function_name}' 不存在")
        return Resp.OK(data=CacheEntriesResponse.from_dict(result))
    
    @router.get(
        "/entry",
        summary="查看单个缓存条目",
        description="查看指定缓存函数的单个条目（返回脱敏预览，不返回完整原始值）",
        response_model=ItemResponse[CacheEntryResponse],
    )
    async def get_entry(
        function_name: str = Query(..., description="缓存函数名"),
        key: str = Query(..., description="缓存键（函数内部键）"),
    ):
        """查看指定函数的单个缓存条目。"""
        func = cache_registry.get(function_name)
        if func is None:
            return Resp.NotFound(message=f"缓存函数 '{function_name}' 不存在")
        
        entry = cache_registry.get_entry(function_name, key)
        if entry is None:
            return Resp.NotFound(message=f"缓存条目不存在: {function_name}:{key}")
        return Resp.OK(data=CacheEntryResponse.from_dict(entry))
    
    @router.post(
        "/clear",
        summary="清空缓存",
        description="清空指定函数或所有函数的缓存数据",
        response_model=OkResponse,
    )
    async def clear_cache(
        function_name: Optional[str] = Query(
            None, description="指定函数名，不指定则清空所有缓存"
        ),
    ):
        """清空缓存"""
        if function_name:
            success = cache_registry.clear_function(function_name)
            if not success:
                return Resp.NotFound(message=f"缓存函数 '{function_name}' 不存在")
            return Resp.OK(
                data={"function": function_name},
                message=f"缓存已清空: {function_name}",
            )
        
        count = cache_registry.clear_all()
        return Resp.OK(
            data={"cleared_count": count},
            message=f"已清空 {count} 个函数的缓存",
        )
    
    @router.get(
        "/invalidator/registrations",
        summary="查看自动失效注册",
        description="查看 CacheInvalidator 中所有模型与缓存函数的关联注册",
        response_model=ItemResponse[CacheInvalidatorRegistrationsResponse],
    )
    async def get_invalidator_registrations():
        """获取自动失效注册信息"""
        registrations = cache_invalidator.get_registrations()
        return Resp.OK(
            data=CacheInvalidatorRegistrationsResponse(
                enabled=cache_invalidator.is_enabled,
                models_count=len(registrations),
                registrations=registrations,
            )
        )
    
    @router.post(
        "/invalidator/toggle",
        summary="切换自动失效",
        description="启用或禁用 ORM 事件驱动的缓存自动失效",
        response_model=ItemResponse[CacheInvalidatorToggleResponse],
    )
    async def toggle_invalidator(
        enabled: bool = Query(..., description="是否启用自动失效"),
    ):
        """启用/禁用自动失效"""
        if enabled:
            cache_invalidator.enable()
        else:
            cache_invalidator.disable()
        
        return Resp.OK(
            data=CacheInvalidatorToggleResponse(enabled=cache_invalidator.is_enabled),
            message=f"自动失效已{'启用' if enabled else '禁用'}",
        )
    
    return router


__all__ = ["create_cache_router"]
