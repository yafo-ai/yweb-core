"""线程执行器

提供基于线程池的任务执行器。

注意：APScheduler 内置了 ThreadPoolExecutor，本模块提供参考实现。
实际使用时推荐直接使用 APScheduler 的 ThreadPoolExecutor。
"""

import logging
from concurrent.futures import ThreadPoolExecutor as Executor, Future
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


class ThreadExecutor:
    """线程执行器
    
    使用线程池执行同步任务。
    
    特性：
    - 支持同步函数
    - 线程池复用
    - 并发控制
    
    Examples:
        executor = ThreadExecutor(max_workers=4)
        future = executor.submit(my_sync_func, arg1, arg2)
        result = future.result()
    """
    
    def __init__(
        self,
        max_workers: int = 10,
        max_instances: int = 1,
    ):
        """初始化线程执行器
        
        Args:
            max_workers: 线程池最大工作线程数
            max_instances: 同一任务的最大并发实例数
        """
        self.max_workers = max_workers
        self.max_instances = max_instances
        self._executor: Optional[Executor] = None
        self._running_jobs = {}  # job_id -> count
    
    def _get_executor(self) -> Executor:
        """获取线程池（延迟初始化）"""
        if self._executor is None:
            self._executor = Executor(max_workers=self.max_workers)
        return self._executor
    
    def submit(
        self,
        func: Callable,
        *args,
        job_id: str = None,
        **kwargs
    ) -> Optional[Future]:
        """提交任务到线程池
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            job_id: 任务 ID（用于并发控制）
            **kwargs: 关键字参数
        
        Returns:
            Future 对象，或 None（如果超过并发限制）
        """
        # 检查并发限制
        if job_id:
            current = self._running_jobs.get(job_id, 0)
            if current >= self.max_instances:
                logger.warning(f"Job {job_id} max instances reached: {current}")
                return None
            self._running_jobs[job_id] = current + 1
        
        def wrapper():
            try:
                return func(*args, **kwargs)
            finally:
                if job_id and job_id in self._running_jobs:
                    self._running_jobs[job_id] -= 1
                    if self._running_jobs[job_id] <= 0:
                        del self._running_jobs[job_id]
        
        return self._get_executor().submit(wrapper)
    
    def execute(self, func: Callable, *args, **kwargs) -> Any:
        """同步执行任务
        
        Args:
            func: 要执行的函数
            *args: 位置参数
            **kwargs: 关键字参数
        
        Returns:
            函数返回值
        """
        future = self.submit(func, *args, **kwargs)
        if future:
            return future.result()
        return None
    
    def get_running_count(self, job_id: str) -> int:
        """获取任务当前运行实例数"""
        return self._running_jobs.get(job_id, 0)
    
    def shutdown(self, wait: bool = True):
        """关闭线程池
        
        Args:
            wait: 是否等待所有任务完成
        """
        if self._executor:
            self._executor.shutdown(wait=wait)
            self._executor = None
