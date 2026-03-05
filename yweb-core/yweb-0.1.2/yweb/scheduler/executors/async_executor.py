"""异步执行器

提供基于 asyncio 的任务执行器。

注意：APScheduler 内置了 AsyncIOExecutor，本模块提供参考实现。
实际使用时推荐直接使用 APScheduler 的 AsyncIOExecutor。
"""

import asyncio
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


class AsyncExecutor:
    """异步执行器
    
    使用 asyncio 执行异步任务。
    
    特性：
    - 支持协程函数
    - 非阻塞执行
    - 自动异常处理
    
    Examples:
        executor = AsyncExecutor()
        await executor.execute(my_async_func, arg1, arg2)
    """
    
    def __init__(self, max_instances: int = 1):
        """初始化异步执行器
        
        Args:
            max_instances: 同一任务的最大并发实例数
        """
        self.max_instances = max_instances
        self._running_jobs = {}  # job_id -> count
    
    async def execute(
        self,
        func: Callable,
        *args,
        job_id: str = None,
        **kwargs
    ) -> Any:
        """执行任务
        
        Args:
            func: 要执行的函数（同步或异步）
            *args: 位置参数
            job_id: 任务 ID（用于并发控制）
            **kwargs: 关键字参数
        
        Returns:
            函数返回值
        """
        # 检查并发限制
        if job_id:
            current = self._running_jobs.get(job_id, 0)
            if current >= self.max_instances:
                logger.warning(f"Job {job_id} max instances reached: {current}")
                return None
            self._running_jobs[job_id] = current + 1
        
        try:
            # 执行函数
            if asyncio.iscoroutinefunction(func):
                result = await func(*args, **kwargs)
            else:
                # 在线程池中执行同步函数
                loop = asyncio.get_event_loop()
                result = await loop.run_in_executor(None, func, *args)
            
            return result
            
        except Exception as e:
            logger.error(f"Error executing job: {e}")
            raise
            
        finally:
            if job_id and job_id in self._running_jobs:
                self._running_jobs[job_id] -= 1
                if self._running_jobs[job_id] <= 0:
                    del self._running_jobs[job_id]
    
    def get_running_count(self, job_id: str) -> int:
        """获取任务当前运行实例数"""
        return self._running_jobs.get(job_id, 0)
