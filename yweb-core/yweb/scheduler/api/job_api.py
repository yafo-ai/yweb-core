"""任务管理路由

端点列表：
    GET  /jobs/list    获取所有任务
    GET  /jobs/get     获取任务详情
    POST /jobs/run     立即执行任务
    POST /jobs/pause   暂停任务
    POST /jobs/resume  恢复任务
    POST /jobs/delete  删除任务
"""

from typing import Optional

from fastapi import APIRouter, Query

from yweb.controller import ResourceController, get, post
from yweb.response import Resp
from yweb.orm import DTO


class JobResponse(DTO):
    """任务信息响应"""
    code: str = ""
    name: str = ""
    description: Optional[str] = None
    is_paused: bool = False
    run_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    last_run_time: Optional[str] = None
    last_run_id: Optional[str] = None
    last_status: Optional[str] = None
    next_run_time: Optional[str] = None


class RunJobResponse(DTO):
    """运行任务响应"""
    run_id: str = ""
    job_code: str = ""


_scheduler = None


def init_job_controller(scheduler) -> None:
    """注入 Scheduler 实例（挂载路由前调用）。"""
    global _scheduler
    _scheduler = scheduler


class JobController(ResourceController):
    """任务管理控制器。

    生成路由（prefix=/jobs）：
        GET  /jobs/list    获取所有任务
        GET  /jobs/get     获取任务详情
        POST /jobs/run     立即执行任务
        POST /jobs/pause   暂停任务
        POST /jobs/resume  恢复任务
        POST /jobs/delete  删除任务
    """

    prefix = "/jobs"
    tags = ["Scheduler"]

    @get(summary="获取所有任务")
    def list(self):
        """获取所有注册的任务列表"""
        jobs = _scheduler.get_jobs()
        return Resp.OK(data=[
            JobResponse.from_dict(j)
            for j in jobs
            if not j.get("parent_code")  # 排除子任务
        ])

    @get(summary="获取任务详情")
    def get(self, code: str = Query(..., description="任务编码")):
        """获取指定任务的详细信息"""
        job = _scheduler.get_job(code)
        if not job:
            return Resp.NotFound(message=f"任务 {code} 不存在")
        return Resp.OK(data=JobResponse.from_dict(job))

    @post(summary="立即执行任务")
    def run(self, code: str = Query(..., description="任务编码")):
        """立即执行指定任务（不影响正常调度）"""
        run_id = _scheduler.run_job(code)
        if not run_id:
            return Resp.NotFound(message=f"任务 {code} 不存在")
        return Resp.OK(
            data=RunJobResponse(run_id=run_id, job_code=code),
            message="任务已触发",
        )

    @post(summary="暂停任务")
    def pause(self, code: str = Query(..., description="任务编码")):
        """暂停指定任务"""
        result = _scheduler.pause_job(code)
        if not result:
            return Resp.NotFound(message=f"任务 {code} 不存在或暂停失败")
        return Resp.OK(message=f"任务 {code} 已暂停")

    @post(summary="恢复任务")
    def resume(self, code: str = Query(..., description="任务编码")):
        """恢复暂停的任务"""
        result = _scheduler.resume_job(code)
        if not result:
            return Resp.NotFound(message=f"任务 {code} 不存在或恢复失败")
        return Resp.OK(message=f"任务 {code} 已恢复")

    @post(summary="删除任务")
    def delete(self, code: str = Query(..., description="任务编码")):
        """删除指定任务"""
        result = _scheduler.remove_job(code)
        if not result:
            return Resp.NotFound(message=f"任务 {code} 不存在")
        return Resp.OK(message=f"任务 {code} 已删除")


def create_job_router(scheduler) -> APIRouter:
    """创建任务管理路由（注入 scheduler 后返回 JobController 路由）。

    Args:
        scheduler: Scheduler 实例

    Returns:
        APIRouter
    """
    init_job_controller(scheduler)
    router = APIRouter()
    router.include_router(JobController.router)
    return router
