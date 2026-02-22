"""调度器管理 API

提供任务管理的路由工厂函数，按职责拆分到独立文件：

- job_api        任务管理（列表/详情/执行/暂停/恢复/删除）
- execution_api  执行历史查询
- stats_api      统计/仪表板/状态/清理

使用示例::

    from yweb.scheduler.api import create_scheduler_router

    router = create_scheduler_router(
        scheduler,
        history_model=scheduler_models.SchedulerJobHistory,
    )
    app.include_router(router, prefix="/api/scheduler", tags=["Scheduler"])
"""

from typing import Optional, List, Sequence, Type

from fastapi import APIRouter, Depends

from .job_api import create_job_router
from .execution_api import create_execution_router
from .stats_api import create_stats_router


def create_scheduler_router(
    scheduler,
    history_model: Type = None,
    prefix: str = "",
    tags: Optional[List[str]] = None,
    dependencies: Optional[Sequence] = None,
) -> APIRouter:
    """创建调度器管理路由

    组合任务管理、执行历史、统计控制三组子路由。

    Args:
        scheduler: Scheduler 实例
        history_model: SchedulerJobHistory 模型类（用于执行历史查询）
        prefix: 路由前缀
        tags: OpenAPI 标签列表
        dependencies: 路由级别依赖（如权限检查）

    Returns:
        FastAPI APIRouter
    """
    router = APIRouter(
        prefix=prefix,
        tags=tags or ["Scheduler"],
        dependencies=list(dependencies) if dependencies else None,
    )

    # 组合子路由
    router.include_router(create_job_router(scheduler))
    router.include_router(create_execution_router(scheduler, history_model))
    router.include_router(create_stats_router(scheduler))

    return router


def setup_scheduler_api(
    app,
    scheduler,
    history_model: Type = None,
    prefix: str = "/api/scheduler",
    tags: Optional[List[str]] = None,
    dependencies: Optional[Sequence] = None,
):
    """快速设置调度器管理 API

    Args:
        app: FastAPI 应用实例
        scheduler: Scheduler 实例
        history_model: SchedulerJobHistory 模型类（用于执行历史查询）
        prefix: API 路由前缀
        tags: OpenAPI 标签列表
        dependencies: 路由级别依赖（如权限检查）
    """
    router = create_scheduler_router(
        scheduler,
        history_model=history_model,
        prefix=prefix,
        tags=tags,
        dependencies=dependencies,
    )
    app.include_router(router)
