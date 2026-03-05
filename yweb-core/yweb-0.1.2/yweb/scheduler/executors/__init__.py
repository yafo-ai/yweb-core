"""执行器模块

提供不同的任务执行器：
- AsyncExecutor: 异步执行器
- ThreadExecutor: 线程执行器

注意：APScheduler 内置了执行器实现，本模块提供的是 YWeb 风格的封装。
实际使用时推荐直接使用 APScheduler 的 AsyncIOExecutor 和 ThreadPoolExecutor。
"""

from .async_executor import AsyncExecutor
from .thread_executor import ThreadExecutor

__all__ = [
    "AsyncExecutor",
    "ThreadExecutor",
]
