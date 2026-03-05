"""执行历史路由

端点列表：
    GET /executions/list  查询执行历史
    GET /executions/get   获取执行详情
"""

from datetime import date, datetime
from typing import Optional, Type

from fastapi import APIRouter, Query

from yweb.response import Resp, PageResponse
from yweb.orm import DTO, Page


class ExecutionResponse(DTO):
    """执行记录响应"""
    run_id: str = ""
    job_code: str = ""
    job_name: Optional[str] = None
    status: str = ""
    scheduled_time: Optional[str] = None
    start_time: Optional[str] = None
    end_time: Optional[str] = None
    duration_ms: Optional[int] = None
    attempt: int = 1
    trigger_type: str = "scheduled"
    error: Optional[str] = None


# 分页响应类型
ExecutionPageResponse = PageResponse[ExecutionResponse]


def create_execution_router(scheduler, history_model: Type = None) -> APIRouter:
    """创建执行历史路由

    Args:
        scheduler: Scheduler 实例
        history_model: SchedulerJobHistory 模型类

    Returns:
        APIRouter
    """
    router = APIRouter()
    _history_model = history_model

    @router.get("/executions/list", response_model=ExecutionPageResponse, summary="查询执行历史")
    def list_executions(
        job_code: Optional[str] = Query(None, description="任务编码"),
        status: Optional[str] = Query(None, description="执行状态"),
        start_date: Optional[date] = Query(None, description="开始日期"),
        end_date: Optional[date] = Query(None, description="结束日期"),
        page: int = Query(1, ge=1, description="页码"),
        page_size: int = Query(20, ge=1, le=100, description="每页数量"),
    ):
        """查询任务执行历史记录"""
        if _history_model is None:
            empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
            return Resp.OK(data=ExecutionResponse.from_page(empty_page))

        try:
            history_manager = scheduler._get_history_manager()
            if history_manager is None:
                empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
                return Resp.OK(data=ExecutionResponse.from_page(empty_page))
        except AttributeError:
            empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
            return Resp.OK(data=ExecutionResponse.from_page(empty_page))

        try:
            HistoryModel = _history_model
            query = HistoryModel.query

            if job_code:
                query = query.filter(HistoryModel.job_code == job_code)
            if status:
                query = query.filter(HistoryModel.status == status)
            if start_date:
                start_datetime = datetime.combine(start_date, datetime.min.time())
                query = query.filter(HistoryModel.start_time >= start_datetime)
            if end_date:
                end_datetime = datetime.combine(end_date, datetime.max.time())
                query = query.filter(HistoryModel.start_time <= end_datetime)

            page_result = query.order_by(
                HistoryModel.start_time.desc()
            ).paginate(page=page, page_size=page_size)
            return Resp.OK(data=ExecutionResponse.from_page(page_result))

        except Exception:
            empty_page = Page(rows=[], total_records=0, page=page, page_size=page_size, total_pages=0)
            return Resp.OK(data=ExecutionResponse.from_page(empty_page))

    @router.get("/executions/get", summary="获取执行详情")
    def get_execution(
        run_id: str = Query(..., description="执行记录 ID"),
    ):
        """获取单次执行的详细信息"""
        try:
            history_manager = scheduler._get_history_manager()
            if history_manager is None:
                return Resp.NotFound(message=f"执行记录 {run_id} 不存在（历史记录未启用）")
        except AttributeError:
            return Resp.NotFound(message=f"执行记录 {run_id} 不存在（历史记录未启用）")

        execution = scheduler.get_execution(run_id)
        if not execution:
            return Resp.NotFound(message=f"执行记录 {run_id} 不存在")
        return Resp.OK(data=ExecutionResponse.from_entity(execution))

    return router
