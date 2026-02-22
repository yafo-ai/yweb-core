"""统计与控制路由

端点列表：
    GET  /stats      获取调度器统计
    GET  /dashboard  获取仪表板数据
    GET  /status     获取调度器状态
    POST /cleanup    清理过期历史
"""

from typing import Optional, List

from fastapi import APIRouter, Query
from pydantic import Field

from yweb.response import Resp
from yweb.orm import DTO


class StatsResponse(DTO):
    """统计响应"""
    total_jobs: int = 0
    active_jobs: int = 0
    paused_jobs: int = 0
    total_runs: int = 0
    success_runs: int = 0
    failed_runs: int = 0
    success_rate: float = 0.0
    is_running: bool = False


class DashboardResponse(DTO):
    """仪表板响应"""
    today: dict = Field(default_factory=dict)
    yesterday: dict = Field(default_factory=dict)
    this_week: dict = Field(default_factory=dict)
    recent_failures: List[dict] = Field(default_factory=list)


def create_stats_router(scheduler) -> APIRouter:
    """创建统计与控制路由

    Args:
        scheduler: Scheduler 实例

    Returns:
        APIRouter
    """
    router = APIRouter()

    @router.get("/stats", summary="获取调度器统计")
    def get_stats():
        """获取调度器整体统计信息"""
        stats = scheduler.get_stats()
        return Resp.OK(data=StatsResponse.from_dict(stats))

    @router.get("/dashboard", summary="获取仪表板数据")
    def get_dashboard():
        """获取仪表板概览数据"""
        default_data = DashboardResponse()

        try:
            history_manager = scheduler._get_history_manager()
            if history_manager is None:
                return Resp.OK(data=default_data)
        except AttributeError:
            return Resp.OK(data=default_data)

        data = history_manager.get_dashboard_data()
        return Resp.OK(data=DashboardResponse.from_dict(data))

    @router.post("/cleanup", summary="清理过期历史")
    def cleanup_history(days: Optional[int] = Query(None, description="保留天数")):
        """清理过期的历史记录和统计数据"""
        try:
            history_manager = scheduler._get_history_manager()
            if history_manager is None:
                return Resp.OK(
                    data={"history": 0, "stats": 0},
                    message="历史记录未启用，无需清理",
                )
        except AttributeError:
            return Resp.OK(
                data={"history": 0, "stats": 0},
                message="历史记录未启用，无需清理",
            )

        result = history_manager.cleanup_all(days)
        return Resp.OK(
            data=result,
            message=f"已清理 {result['history']} 条历史记录和 {result['stats']} 条统计记录",
        )

    @router.get("/status", summary="获取调度器状态")
    def get_status():
        """获取调度器运行状态"""
        return Resp.OK(data={
            "is_running": scheduler._running,
            "enabled": scheduler.settings.enabled,
            "store": scheduler.settings.store,
            "timezone": scheduler.settings.timezone,
            "total_jobs": len(scheduler._jobs),
        })

    return router
