"""内存任务存储

默认的内存存储实现，适用于单实例场景。

注意：APScheduler 内置了 MemoryJobStore，本模块提供的是
YWeb 风格的封装，实际使用时推荐直接使用 APScheduler 的实现。
"""

from typing import Optional, List, Any, Dict
from datetime import datetime

from .base import BaseStore


class MemoryStore(BaseStore):
    """内存任务存储
    
    将任务存储在内存中，适用于：
    - 单实例部署
    - 开发测试
    - 不需要持久化的场景
    
    注意：应用重启后任务会丢失。
    """
    
    def __init__(self):
        self._jobs: Dict[str, Any] = {}
    
    def add_job(self, job: Any) -> None:
        """添加任务"""
        self._jobs[job.id] = job
    
    def update_job(self, job: Any) -> None:
        """更新任务"""
        if job.id not in self._jobs:
            raise KeyError(f"Job {job.id} not found")
        self._jobs[job.id] = job
    
    def remove_job(self, job_id: str) -> None:
        """删除任务"""
        if job_id in self._jobs:
            del self._jobs[job_id]
    
    def lookup_job(self, job_id: str) -> Optional[Any]:
        """查找任务"""
        return self._jobs.get(job_id)
    
    def get_all_jobs(self) -> List[Any]:
        """获取所有任务"""
        return list(self._jobs.values())
    
    def get_due_jobs(self, now: datetime) -> List[Any]:
        """获取到期的任务"""
        due_jobs = []
        for job in self._jobs.values():
            if job.next_run_time and job.next_run_time <= now:
                due_jobs.append(job)
        return sorted(due_jobs, key=lambda j: j.next_run_time)
    
    def get_next_run_time(self) -> Optional[datetime]:
        """获取下次执行时间"""
        next_times = [
            job.next_run_time 
            for job in self._jobs.values() 
            if job.next_run_time
        ]
        return min(next_times) if next_times else None
    
    def remove_all_jobs(self) -> None:
        """删除所有任务"""
        self._jobs.clear()
