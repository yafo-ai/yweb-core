"""核心调度器类

提供定时任务调度的核心功能。

使用示例:
    from yweb import Scheduler
    
    scheduler = Scheduler()
    
    @scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
    async def daily_report(context):
        pass
    
    scheduler.init_app(app)
"""

import asyncio
import functools
import inspect
import logging
import os
import random
import socket
import string
import traceback
import json
from datetime import datetime, date
from typing import Optional, Callable, Any, Dict, List, Union, TypeVar, Type, TYPE_CHECKING

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.jobstores.memory import MemoryJobStore
from apscheduler.executors.asyncio import AsyncIOExecutor
from apscheduler.triggers.base import BaseTrigger
from apscheduler.events import (
    EVENT_JOB_EXECUTED,
    EVENT_JOB_ERROR,
    EVENT_JOB_MISSED,
    JobExecutionEvent,
)

from .triggers import cron, interval, once
from .context import JobContext
from .events import (
    JobEvent,
    JobExecutedEvent,
    JobErrorEvent,
    JobRetryEvent,
    JobMissedEvent,
)
from .retry import RetryStrategy
from ..config import SchedulerSettings

if TYPE_CHECKING:
    from .job import Job
    from .builder import JobConfig


logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def generate_run_id() -> str:
    """生成执行ID
    
    格式: run_YYYYMMDD_HHMMSS_XXXXXX
    """
    random_suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    return f"run_{datetime.now():%Y%m%d_%H%M%S}_{random_suffix}"


class Scheduler:
    """定时任务调度器
    
    基于 APScheduler 封装，提供简洁易用的 API。
    
    使用示例:
        from yweb import Scheduler
        
        scheduler = Scheduler()
        
        # 装饰器方式
        @scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
        async def daily_report(context: JobContext):
            print(f"[{context.run_id}] 生成日报...")
        
        # FastAPI 集成
        scheduler.init_app(app)
    
    Attributes:
        settings: 调度器配置
        _scheduler: APScheduler 实例
        _jobs: 已注册的任务字典 {code: job_info}
        _running: 是否正在运行
    """
    
    def __init__(
        self,
        settings: Optional[SchedulerSettings] = None,
        **kwargs
    ):
        """初始化调度器
        
        Args:
            settings: 调度器配置，为空时使用默认配置
            **kwargs: 额外配置参数，会覆盖 settings 中的配置
        """
        self.settings = settings or SchedulerSettings()
        
        # 覆盖配置
        for key, value in kwargs.items():
            if hasattr(self.settings, key):
                setattr(self.settings, key, value)
        
        # 任务存储
        self._jobs: Dict[str, Dict[str, Any]] = {}  # code -> job_info
        
        # Job 类实例缓存
        self._job_instances: Dict[str, "Job"] = {}
        
        # 事件监听器
        self._event_listeners: Dict[str, List[Callable]] = {
            "job_executed": [],
            "job_error": [],
            "job_retry": [],
            "job_missed": [],
        }
        
        # APScheduler 实例
        self._scheduler: Optional[AsyncIOScheduler] = None
        self._running = False
        
        # 历史管理器（延迟初始化）
        self._history_manager = None
        
        # 分布式锁（延迟初始化）
        self._distributed_lock = None
        
        # 初始化 APScheduler
        self._init_apscheduler()
    
    def _init_apscheduler(self):
        """初始化 APScheduler"""
        # 根据配置选择存储
        if self.settings.store == "orm":
            from .stores import ORMJobStore
            jobstores = {
                "default": ORMJobStore()
            }
        else:
            jobstores = {
                "default": MemoryJobStore()
            }
        
        executors = {
            "default": AsyncIOExecutor()
        }
        
        job_defaults = {
            "coalesce": self.settings.coalesce,
            "max_instances": 1,
            "misfire_grace_time": self.settings.misfire_grace_time,
        }
        
        self._scheduler = AsyncIOScheduler(
            jobstores=jobstores,
            executors=executors,
            job_defaults=job_defaults,
            timezone=self.settings.timezone,
        )
        
        # 注册事件监听
        self._scheduler.add_listener(
            self._on_job_executed,
            EVENT_JOB_EXECUTED
        )
        self._scheduler.add_listener(
            self._on_job_error,
            EVENT_JOB_ERROR
        )
        self._scheduler.add_listener(
            self._on_job_missed,
            EVENT_JOB_MISSED
        )
    
    def _get_history_manager(self):
        """获取历史管理器（延迟初始化）"""
        if self._history_manager is None:
            from .history import HistoryManager
            self._history_manager = HistoryManager(
                enabled=self.settings.enable_history,
                retention_days=self.settings.history_retention_days,
            )
        return self._history_manager
    
    def _get_distributed_lock(self):
        """获取分布式锁（延迟初始化）
        
        当 settings.distributed_lock=True 且 redis_url 可用时返回 RedisDistributedLock，
        否则返回 MemoryLock（用于单实例场景）。
        """
        if self._distributed_lock is None:
            from .locks.redis_lock import create_distributed_lock
            self._distributed_lock = create_distributed_lock(
                redis_url=self.settings.redis_url if self.settings.distributed_lock else None,
                prefix="yweb:scheduler:lock:",
            )
        return self._distributed_lock
    
    # ========== 装饰器 API ==========
    
    def cron(
        self,
        expression: Optional[str] = None,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
        **trigger_kwargs
    ) -> Callable[[F], F]:
        """Cron 表达式装饰器
        
        Args:
            expression: Cron 表达式
            code: 任务编码（默认为函数名）
            name: 任务名称
            description: 任务描述
            max_retries: 最大重试次数（retry_strategy 优先级更高）
            retry_delay: 重试间隔（秒）（retry_strategy 优先级更高）
            retry_strategy: 重试策略（优先于 max_retries/retry_delay）
            concurrent: 是否允许并发
            timeout: 超时时间（秒），None 表示不超时
            **trigger_kwargs: 传递给 cron() 的额外参数
        
        Returns:
            装饰器函数
        
        Examples:
            @scheduler.cron("0 8 * * *")
            async def daily_report():
                pass
            
            @scheduler.cron("0 8 * * *", retry_strategy=RetryStrategy.exponential())
            async def daily_report(context: JobContext):
                pass
        """
        trigger = cron(expression, **trigger_kwargs) if expression else cron(**trigger_kwargs)
        
        def decorator(func: F) -> F:
            self._register_job(
                func=func,
                trigger=trigger,
                code=code,
                name=name,
                description=description,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_strategy=retry_strategy,
                concurrent=concurrent,
                timeout=timeout,
            )
            return func
        
        return decorator
    
    def interval(
        self,
        *,
        weeks: int = 0,
        days: int = 0,
        hours: int = 0,
        minutes: int = 0,
        seconds: int = 0,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
        **trigger_kwargs
    ) -> Callable[[F], F]:
        """间隔触发器装饰器
        
        Args:
            weeks: 周数
            days: 天数
            hours: 小时数
            minutes: 分钟数
            seconds: 秒数
            code: 任务编码
            name: 任务名称
            description: 任务描述
            max_retries: 最大重试次数（retry_strategy 优先级更高）
            retry_delay: 重试间隔（秒）（retry_strategy 优先级更高）
            retry_strategy: 重试策略（优先于 max_retries/retry_delay）
            concurrent: 是否允许并发
            timeout: 超时时间（秒），None 表示不超时
            **trigger_kwargs: 传递给 interval() 的额外参数
        
        Returns:
            装饰器函数
        """
        trigger = interval(
            weeks=weeks,
            days=days,
            hours=hours,
            minutes=minutes,
            seconds=seconds,
            **trigger_kwargs
        )
        
        def decorator(func: F) -> F:
            self._register_job(
                func=func,
                trigger=trigger,
                code=code,
                name=name,
                description=description,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_strategy=retry_strategy,
                concurrent=concurrent,
                timeout=timeout,
            )
            return func
        
        return decorator
    
    def once(
        self,
        run_date: Optional[Union[str, datetime]] = None,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        timeout: Optional[int] = None,
        **trigger_kwargs
    ) -> Callable[[F], F]:
        """一次性任务装饰器
        
        Args:
            run_date: 执行时间
            code: 任务编码
            name: 任务名称
            description: 任务描述
            max_retries: 最大重试次数（retry_strategy 优先级更高）
            retry_delay: 重试间隔（秒）（retry_strategy 优先级更高）
            retry_strategy: 重试策略（优先于 max_retries/retry_delay）
            timeout: 超时时间（秒），None 表示不超时
            **trigger_kwargs: 传递给 once() 的额外参数
        
        Returns:
            装饰器函数
        """
        trigger = once(run_date=run_date, **trigger_kwargs)
        
        def decorator(func: F) -> F:
            self._register_job(
                func=func,
                trigger=trigger,
                code=code,
                name=name,
                description=description,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_strategy=retry_strategy,
                concurrent=True,  # 一次性任务不存在并发问题
                timeout=timeout,
            )
            return func
        
        return decorator
    
    def job(
        self,
        trigger: Optional[BaseTrigger] = None,
        triggers: Optional[List[BaseTrigger]] = None,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
    ) -> Callable[[F], F]:
        """通用任务装饰器（支持多触发器）
        
        Args:
            trigger: 单个触发器
            triggers: 多个触发器列表（与 trigger 二选一）
            code: 任务编码（默认为函数名）
            name: 任务名称
            description: 任务描述
            max_retries: 最大重试次数（retry_strategy 优先级更高）
            retry_delay: 重试间隔（秒）（retry_strategy 优先级更高）
            retry_strategy: 重试策略（优先于 max_retries/retry_delay）
            concurrent: 是否允许并发
            timeout: 超时时间（秒），None 表示不超时
        
        Returns:
            装饰器函数
        
        Examples:
            # 单触发器
            @scheduler.job(trigger=cron("0 8 * * *"), code="DAILY")
            async def daily_task():
                pass
            
            # 多触发器 + 指数退避重试
            @scheduler.job(
                triggers=[cron("0 9 * * *"), cron("0 18 * * *")],
                code="REMINDER",
                retry_strategy=RetryStrategy.exponential()
            )
            async def send_reminder():
                pass
        """
        # 确定触发器列表
        trigger_list = triggers or ([trigger] if trigger else [])
        
        if not trigger_list:
            raise ValueError("Must provide either 'trigger' or 'triggers'")
        
        def decorator(func: F) -> F:
            job_code = code or func.__name__
            
            if len(trigger_list) == 1:
                # 单触发器
                self._register_job(
                    func=func,
                    trigger=trigger_list[0],
                    code=job_code,
                    name=name,
                    description=description,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    retry_strategy=retry_strategy,
                    concurrent=concurrent,
                    timeout=timeout,
                )
            else:
                # 多触发器
                self._register_multi_trigger_job(
                    func=func,
                    triggers=trigger_list,
                    code=job_code,
                    name=name,
                    description=description,
                    max_retries=max_retries,
                    retry_delay=retry_delay,
                    retry_strategy=retry_strategy,
                    concurrent=concurrent,
                    timeout=timeout,
                )
            return func
        
        return decorator
    
    # ========== 动态任务管理 ==========
    
    def add_job(
        self,
        func: Callable,
        trigger: BaseTrigger,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[dict] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
        replace_existing: bool = False,
    ) -> str:
        """动态添加任务
        
        Args:
            func: 任务函数
            trigger: 触发器
            code: 任务编码
            name: 任务名称
            description: 任务描述
            args: 位置参数
            kwargs: 关键字参数
            max_retries: 最大重试次数（retry_strategy 优先级更高）
            retry_delay: 重试间隔（秒）（retry_strategy 优先级更高）
            retry_strategy: 重试策略（优先于 max_retries/retry_delay）
            concurrent: 是否允许并发
            replace_existing: 是否替换已存在的任务
        
        Returns:
            任务编码
        """
        return self._register_job(
            func=func,
            trigger=trigger,
            code=code,
            name=name,
            description=description,
            args=args,
            kwargs=kwargs,
            max_retries=max_retries,
            retry_delay=retry_delay,
            retry_strategy=retry_strategy,
            concurrent=concurrent,
            timeout=timeout,
            replace_existing=replace_existing,
        )
    
    def remove_job(self, code: str) -> bool:
        """删除任务
        
        Args:
            code: 任务编码
        
        Returns:
            是否删除成功
        """
        if code not in self._jobs:
            logger.warning(f"Job not found: {code}")
            return False
        
        job_info = self._jobs.pop(code)
        
        if self._scheduler and self._running:
            try:
                self._scheduler.remove_job(job_info["apscheduler_id"])
            except Exception as e:
                logger.error(f"Failed to remove job from APScheduler: {e}")
        
        logger.info(f"Job removed: {code}")
        return True
    
    def pause_job(self, code: str) -> bool:
        """暂停任务
        
        Args:
            code: 任务编码
        
        Returns:
            是否暂停成功
        """
        if code not in self._jobs:
            logger.warning(f"Job not found: {code}")
            return False
        
        job_info = self._jobs[code]
        
        if self._scheduler and self._running:
            try:
                self._scheduler.pause_job(job_info["apscheduler_id"])
                job_info["is_paused"] = True
                logger.info(f"Job paused: {code}")
                return True
            except Exception as e:
                logger.error(f"Failed to pause job: {e}")
                return False
        
        job_info["is_paused"] = True
        return True
    
    def resume_job(self, code: str) -> bool:
        """恢复任务
        
        Args:
            code: 任务编码
        
        Returns:
            是否恢复成功
        """
        if code not in self._jobs:
            logger.warning(f"Job not found: {code}")
            return False
        
        job_info = self._jobs[code]
        
        if self._scheduler and self._running:
            try:
                self._scheduler.resume_job(job_info["apscheduler_id"])
                job_info["is_paused"] = False
                logger.info(f"Job resumed: {code}")
                return True
            except Exception as e:
                logger.error(f"Failed to resume job: {e}")
                return False
        
        job_info["is_paused"] = False
        return True
    
    def reschedule_job(self, code: str, trigger: BaseTrigger) -> bool:
        """修改任务调度
        
        修改已存在任务的触发器。
        
        Args:
            code: 任务编码
            trigger: 新的触发器
        
        Returns:
            是否修改成功
        
        Examples:
            # 将每日任务改为每2小时执行
            scheduler.reschedule_job("MY_JOB", trigger=cron("0 */2 * * *"))
            
            # 改为每10分钟执行
            scheduler.reschedule_job("MY_JOB", trigger=interval(minutes=10))
        """
        if code not in self._jobs:
            logger.warning(f"Job not found: {code}")
            return False
        
        job_info = self._jobs[code]
        
        # 更新 job_info 中的触发器
        job_info["trigger"] = trigger
        
        if self._scheduler and self._running:
            try:
                self._scheduler.reschedule_job(
                    job_info["apscheduler_id"],
                    trigger=trigger
                )
                logger.info(f"Job rescheduled: {code}")
                return True
            except Exception as e:
                logger.error(f"Failed to reschedule job: {e}")
                return False
        
        return True
    
    def run_job(self, code: str) -> Optional[str]:
        """立即执行任务（不影响正常调度）
        
        Args:
            code: 任务编码
        
        Returns:
            执行ID（run_id）
        """
        if code not in self._jobs:
            logger.warning(f"Job not found: {code}")
            return None
        
        job_info = self._jobs[code]
        run_id = generate_run_id()
        
        # 创建执行上下文
        context = JobContext(
            job_id=job_info["id"],
            job_code=code,
            job_name=job_info["name"],
            job_description=job_info.get("description"),
            run_id=run_id,
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            attempt=1,
            trigger_type="manual",
            run_count=job_info.get("run_count", 0),
        )
        
        # 异步执行
        try:
            # 尝试在现有事件循环中创建任务
            loop = asyncio.get_running_loop()
            loop.create_task(self._execute_job(job_info, context))
        except RuntimeError:
            # 没有运行中的事件循环
            # 注意：不使用 asyncio.run()，因为它可能在新线程中执行，导致数据库问题
            logger.debug(f"No event loop available, job will be executed when loop starts: {code}")
        
        logger.info(f"Job triggered manually: {code}, run_id: {run_id}")
        return run_id
    
    def get_job(self, code: str) -> Optional[Dict[str, Any]]:
        """获取任务信息
        
        Args:
            code: 任务编码
        
        Returns:
            任务信息字典
        """
        if code not in self._jobs:
            return None
        
        job_info = self._jobs[code].copy()
        
        # 获取下次执行时间
        if self._scheduler and self._running:
            try:
                ap_job = self._scheduler.get_job(job_info["apscheduler_id"])
                if ap_job:
                    job_info["next_run_time"] = ap_job.next_run_time
            except Exception:
                pass
        
        return job_info
    
    def get_jobs(self) -> List[Dict[str, Any]]:
        """获取所有任务
        
        Returns:
            任务信息列表
        """
        jobs = []
        for code in self._jobs:
            job_info = self.get_job(code)
            if job_info:
                jobs.append(job_info)
        return jobs
    
    # ========== Job 类支持 ==========
    
    def add_job_class(
        self,
        job_class: Type["Job"],
        replace_existing: bool = False,
    ) -> str:
        """注册 Job 类
        
        Args:
            job_class: Job 子类
            replace_existing: 是否替换已存在的任务
        
        Returns:
            任务编码
        
        Examples:
            class DailyReportJob(Job):
                code = "DAILY_REPORT"
                trigger = cron("0 8 * * *")
                
                async def execute(self, context):
                    pass
            
            scheduler.add_job_class(DailyReportJob)
        """
        from .job import Job
        
        if not issubclass(job_class, Job):
            raise TypeError(f"{job_class} must be a subclass of Job")
        
        # 创建实例
        instance = job_class()
        code = instance.code
        
        # 缓存实例
        self._job_instances[code] = instance
        
        # 获取触发器
        triggers = instance.get_triggers()
        if not triggers:
            raise ValueError(f"{job_class.__name__} must define at least one trigger")
        
        # 注册任务（支持多触发器）
        if len(triggers) == 1:
            return self._register_job(
                func=self._create_job_executor(instance),
                trigger=triggers[0],
                code=code,
                name=instance.get_name(),
                description=instance.get_description(),
                max_retries=instance.max_retries,
                retry_delay=instance.retry_delay,
                concurrent=instance.concurrent,
                replace_existing=replace_existing,
            )
        else:
            # 多触发器：为每个触发器创建一个子任务
            return self._register_multi_trigger_job(
                func=self._create_job_executor(instance),
                triggers=triggers,
                code=code,
                name=instance.get_name(),
                description=instance.get_description(),
                max_retries=instance.max_retries,
                retry_delay=instance.retry_delay,
                concurrent=instance.concurrent,
                replace_existing=replace_existing,
            )
    
    def _create_job_executor(self, job_instance: "Job") -> Callable:
        """为 Job 实例创建执行函数"""
        async def executor(context: JobContext):
            try:
                result = await job_instance.execute(context)
                await job_instance.on_success(context, result)
                return result
            except Exception as e:
                await job_instance.on_error(context, e)
                raise
        
        return executor
    
    # ========== JobBuilder 支持 ==========
    
    def add_job_from_builder(
        self,
        config: "JobConfig",
        replace_existing: bool = False,
    ) -> str:
        """从 JobBuilder 配置添加任务
        
        Args:
            config: JobConfig 实例
            replace_existing: 是否替换已存在的任务
        
        Returns:
            任务编码
        
        Examples:
            from yweb.scheduler import JobBuilder, cron
            
            config = (
                JobBuilder(my_func)
                .code("MY_JOB")
                .name("我的任务")
                .trigger(cron("0 8 * * *"))
                .build()
            )
            
            scheduler.add_job_from_builder(config)
        """
        # 确定执行函数
        if config.job_class:
            instance = config.job_class()
            self._job_instances[config.code] = instance
            func = self._create_job_executor(instance)
        elif config.func:
            func = config.func
        else:
            raise ValueError("JobConfig must have either func or job_class")
        
        # 获取触发器
        triggers = config.get_triggers()
        
        if len(triggers) == 1:
            return self._register_job(
                func=func,
                trigger=triggers[0],
                code=config.code,
                name=config.name,
                description=config.description,
                args=config.args,
                kwargs=config.kwargs,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                concurrent=config.concurrent,
                replace_existing=replace_existing,
            )
        else:
            return self._register_multi_trigger_job(
                func=func,
                triggers=triggers,
                code=config.code,
                name=config.name,
                description=config.description,
                args=config.args,
                kwargs=config.kwargs,
                max_retries=config.max_retries,
                retry_delay=config.retry_delay,
                concurrent=config.concurrent,
                replace_existing=replace_existing,
            )
    
    # ========== HTTP 任务支持 ==========
    
    def add_http_job(
        self,
        url: str,
        trigger: BaseTrigger,
        *,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        method: str = "GET",
        headers: Optional[dict] = None,
        body: Optional[dict] = None,
        timeout: int = 30,
        max_retries: int = 0,
        retry_delay: int = 60,
        replace_existing: bool = False,
    ) -> str:
        """添加 HTTP 任务
        
        Args:
            url: 请求 URL
            trigger: 触发器
            code: 任务编码
            name: 任务名称
            description: 任务描述
            method: HTTP 方法
            headers: 请求头
            body: 请求体
            timeout: 超时时间（秒）
            max_retries: 最大重试次数
            retry_delay: 重试间隔（秒）
            replace_existing: 是否替换已存在的任务
        
        Returns:
            任务编码
        
        Examples:
            scheduler.add_http_job(
                url="https://api.example.com/sync",
                trigger=cron("*/5 * * * *"),
                code="SYNC_API",
                method="POST",
                body={"action": "sync"},
            )
        """
        from .http_job import HttpJobConfig, create_http_job_class
        
        if code is None:
            # 从 URL 生成 code
            from urllib.parse import urlparse
            parsed = urlparse(url)
            code = f"HTTP_{parsed.netloc.replace('.', '_').replace('-', '_').upper()}"
        
        config = HttpJobConfig(
            url=url,
            method=method,
            headers=headers or {},
            body=body,
            timeout=timeout,
        )
        
        job_class = create_http_job_class(
            config=config,
            code=code,
            trigger=trigger,
            name=name,
            description=description,
            max_retries=max_retries,
        )
        
        return self.add_job_class(job_class, replace_existing=replace_existing)
    
    # ========== 多触发器支持 ==========
    
    def _register_multi_trigger_job(
        self,
        func: Callable,
        triggers: List[BaseTrigger],
        code: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[dict] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
        replace_existing: bool = False,
    ) -> str:
        """注册多触发器任务
        
        为每个触发器创建独立的子任务，共享同一个 code。
        """
        # 注册主任务信息
        job_id = f"{code}_{datetime.now():%Y%m%d%H%M%S}"
        
        # 如果提供了 retry_strategy，使用其配置
        effective_max_retries = retry_strategy.max_retries if retry_strategy else max_retries
        effective_retry_delay = retry_strategy.delay if retry_strategy else retry_delay
        
        job_info = {
            "id": job_id,
            "code": code,
            "name": name or func.__name__,
            "description": description or func.__doc__,
            "func": func,
            "triggers": triggers,
            "args": args or (),
            "kwargs": kwargs or {},
            "max_retries": effective_max_retries,
            "retry_delay": effective_retry_delay,
            "retry_strategy": retry_strategy,
            "concurrent": concurrent,
            "timeout": timeout,
            "is_paused": False,
            "run_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "last_run_time": None,
            "last_run_id": None,
            "last_status": None,
            "is_multi_trigger": True,
            "sub_job_ids": [],
        }
        
        # 为每个触发器创建子任务
        for i, trigger in enumerate(triggers):
            sub_code = f"{code}#{i+1}"
            sub_job_id = self._register_job(
                func=func,
                trigger=trigger,
                code=sub_code,
                name=f"{name or func.__name__} (触发器 {i+1})",
                description=description,
                args=args,
                kwargs=kwargs,
                max_retries=max_retries,
                retry_delay=retry_delay,
                retry_strategy=retry_strategy,
                concurrent=concurrent,
                timeout=timeout,
                replace_existing=replace_existing,
                _parent_code=code,
            )
            job_info["sub_job_ids"].append(sub_code)
        
        self._jobs[code] = job_info
        logger.info(f"Multi-trigger job registered: {code} with {len(triggers)} triggers")
        return code
    
    # ========== 执行历史查询 ==========
    
    def get_executions(
        self,
        job_code: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[Union[datetime, date]] = None,
        end_date: Optional[Union[datetime, date]] = None,
        limit: int = 100,
        offset: int = 0,
    ) -> List[Any]:
        """查询执行历史
        
        Args:
            job_code: 任务编码（可选）
            status: 状态过滤（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
            limit: 返回数量限制
            offset: 偏移量
        
        Returns:
            执行历史列表
        """
        return self._get_history_manager().get_executions(
            job_code=job_code,
            status=status,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            offset=offset,
        )
    
    def count_executions(
        self,
        job_code: Optional[str] = None,
        status: Optional[str] = None,
        start_date: Optional[Union[datetime, date]] = None,
        end_date: Optional[Union[datetime, date]] = None,
    ) -> int:
        """统计执行历史总数
        
        Args:
            job_code: 任务编码（可选）
            status: 状态过滤（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
        
        Returns:
            符合条件的记录总数
        """
        return self._get_history_manager().count_executions(
            job_code=job_code,
            status=status,
            start_date=start_date,
            end_date=end_date,
        )
    
    def get_execution(self, run_id: str) -> Optional[Any]:
        """查询单次执行记录
        
        Args:
            run_id: 执行ID
        
        Returns:
            执行历史记录
        """
        return self._get_history_manager().get_execution(run_id)
    
    def get_execution_stats(
        self,
        job_code: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> List[Any]:
        """查询执行统计
        
        Args:
            job_code: 任务编码（可选）
            start_date: 开始日期（可选）
            end_date: 结束日期（可选）
        
        Returns:
            统计记录列表
        """
        return self._get_history_manager().get_stats(
            job_code=job_code,
            start_date=start_date,
            end_date=end_date,
        )
    
    # ========== 事件监听 ==========
    
    def on_job_executed(self, func: Callable) -> Callable:
        """注册任务执行成功事件监听器"""
        self._event_listeners["job_executed"].append(func)
        return func
    
    def on_job_error(self, func: Callable) -> Callable:
        """注册任务执行失败事件监听器"""
        self._event_listeners["job_error"].append(func)
        return func
    
    def on_job_retry(self, func: Callable) -> Callable:
        """注册任务重试事件监听器"""
        self._event_listeners["job_retry"].append(func)
        return func
    
    def on_job_missed(self, func: Callable) -> Callable:
        """注册任务错过执行事件监听器"""
        self._event_listeners["job_missed"].append(func)
        return func
    
    # ========== 生命周期管理 ==========
    
    def start(self):
        """启动调度器"""
        if self._running:
            logger.warning("Scheduler is already running")
            return
        
        if not self.settings.enabled:
            logger.info("Scheduler is disabled")
            return
        
        # 将注册的任务添加到 APScheduler
        for code, job_info in self._jobs.items():
            if not job_info.get("is_paused"):
                self._add_to_apscheduler(job_info)
        
        self._scheduler.start()
        self._running = True
        logger.info(f"Scheduler started with {len(self._jobs)} jobs")
    
    def shutdown(self, wait: bool = True):
        """关闭调度器
        
        Args:
            wait: 是否等待正在执行的任务完成
        """
        if not self._running:
            return
        
        self._scheduler.shutdown(wait=wait)
        self._running = False
        logger.info("Scheduler shutdown complete")
    
    def init_app(self, app):
        """集成到 FastAPI 应用
        
        Args:
            app: FastAPI 应用实例
        """
        @app.on_event("startup")
        async def _start_scheduler():
            if self.settings.enabled:
                self.start()
        
        @app.on_event("shutdown")
        async def _shutdown_scheduler():
            if self._running:
                self.shutdown(wait=True)
        
        # 挂载到 app.state
        app.state.scheduler = self
    
    # ========== 内部方法 ==========
    
    def _register_job(
        self,
        func: Callable,
        trigger: BaseTrigger,
        code: Optional[str] = None,
        name: Optional[str] = None,
        description: Optional[str] = None,
        args: Optional[tuple] = None,
        kwargs: Optional[dict] = None,
        max_retries: int = 0,
        retry_delay: int = 60,
        retry_strategy: Optional[RetryStrategy] = None,
        concurrent: bool = True,
        timeout: Optional[int] = None,
        replace_existing: bool = False,
        _parent_code: Optional[str] = None,  # 多触发器的父任务编码
    ) -> str:
        """注册任务
        
        支持装饰器叠加：当同一函数被多次装饰时，自动合并为多触发器任务。
        """
        # 生成 code
        if code is None:
            code = func.__name__
        
        # 检查是否是装饰器叠加（同一函数多次装饰）
        # 通过检查现有任务是否使用相同的函数对象来判断
        existing_job = self._jobs.get(code)
        if existing_job and existing_job.get("func") is func and not replace_existing:
            # 装饰器叠加：将当前触发器添加到现有任务
            return self._add_trigger_to_existing_job(code, trigger)
        
        # 检查重复（不同函数但相同 code）
        if code in self._jobs and not replace_existing:
            raise ValueError(f"Job with code '{code}' already exists. Use replace_existing=True to replace.")
        
        # 生成任务ID
        job_id = f"{code}_{datetime.now():%Y%m%d%H%M%S}"
        
        # 如果提供了 retry_strategy，使用其配置
        effective_max_retries = retry_strategy.max_retries if retry_strategy else max_retries
        effective_retry_delay = retry_strategy.delay if retry_strategy else retry_delay
        
        # 任务信息
        job_info = {
            "id": job_id,
            "code": code,
            "name": name or func.__name__,
            "description": description or func.__doc__,
            "func": func,
            "trigger": trigger,
            "args": args or (),
            "kwargs": kwargs or {},
            "max_retries": effective_max_retries,
            "retry_delay": effective_retry_delay,
            "retry_strategy": retry_strategy,
            "concurrent": concurrent,
            "timeout": timeout,
            "is_paused": False,
            "run_count": 0,
            "success_count": 0,
            "fail_count": 0,
            "last_run_time": None,
            "last_run_id": None,
            "last_status": None,
            "apscheduler_id": f"yweb_{code}",
            "parent_code": _parent_code,  # 多触发器的父任务编码
        }
        
        self._jobs[code] = job_info
        
        # 如果调度器已运行，立即添加到 APScheduler
        if self._running:
            self._add_to_apscheduler(job_info)
        
        logger.info(f"Job registered: {code} ({name or func.__name__})")
        return code
    
    def _add_trigger_to_existing_job(self, code: str, new_trigger: BaseTrigger) -> str:
        """为现有任务添加新触发器（装饰器叠加支持）
        
        将单触发器任务转换为多触发器任务，或向已有的多触发器任务添加新触发器。
        
        Args:
            code: 任务编码
            new_trigger: 要添加的新触发器
        
        Returns:
            任务编码
        """
        job_info = self._jobs[code]
        
        # 检查是否已经是多触发器任务
        if job_info.get("is_multi_trigger"):
            # 已经是多触发器，添加新的子任务
            triggers = job_info.get("triggers", [])
            triggers.append(new_trigger)
            job_info["triggers"] = triggers
            
            # 创建新的子任务
            sub_index = len(job_info.get("sub_job_ids", [])) + 1
            sub_code = f"{code}#{sub_index}"
            sub_job_id = self._register_job(
                func=job_info["func"],
                trigger=new_trigger,
                code=sub_code,
                name=f"{job_info['name']} (触发器 {sub_index})",
                description=job_info.get("description"),
                args=job_info.get("args"),
                kwargs=job_info.get("kwargs"),
                max_retries=job_info.get("max_retries", 0),
                retry_delay=job_info.get("retry_delay", 60),
                concurrent=job_info.get("concurrent", True),
                _parent_code=code,
            )
            job_info.setdefault("sub_job_ids", []).append(sub_job_id)
            
            logger.info(f"Added trigger #{sub_index} to multi-trigger job: {code}")
        else:
            # 转换为多触发器任务
            old_trigger = job_info["trigger"]
            
            # 标记为多触发器任务
            job_info["is_multi_trigger"] = True
            job_info["triggers"] = [old_trigger, new_trigger]
            job_info["sub_job_ids"] = []
            
            # 为第二个触发器创建子任务
            sub_code = f"{code}#2"
            sub_job_id = self._register_job(
                func=job_info["func"],
                trigger=new_trigger,
                code=sub_code,
                name=f"{job_info['name']} (触发器 2)",
                description=job_info.get("description"),
                args=job_info.get("args"),
                kwargs=job_info.get("kwargs"),
                max_retries=job_info.get("max_retries", 0),
                retry_delay=job_info.get("retry_delay", 60),
                concurrent=job_info.get("concurrent", True),
                _parent_code=code,
            )
            job_info["sub_job_ids"].append(sub_job_id)
            
            logger.info(f"Converted job to multi-trigger: {code} (now has 2 triggers)")
        
        return code
    
    def _add_to_apscheduler(self, job_info: Dict[str, Any]):
        """将任务添加到 APScheduler"""
        # 包装函数以注入上下文
        wrapped_func = self._wrap_job_func(job_info)
        
        self._scheduler.add_job(
            wrapped_func,
            trigger=job_info["trigger"],
            id=job_info["apscheduler_id"],
            name=job_info["name"],
            max_instances=1 if not job_info["concurrent"] else 3,
            replace_existing=True,
        )
    
    def _wrap_job_func(self, job_info: Dict[str, Any]) -> Callable:
        """包装任务函数，注入上下文"""
        original_func = job_info["func"]
        code = job_info["code"]
        
        @functools.wraps(original_func)
        async def wrapped():
            run_id = generate_run_id()
            start_time = datetime.now()
            
            # 创建上下文
            context = JobContext(
                job_id=job_info["id"],
                job_code=code,
                job_name=job_info["name"],
                job_description=job_info.get("description"),
                run_id=run_id,
                scheduled_time=start_time,
                start_time=start_time,
                attempt=1,
                trigger_type="scheduled",
                run_count=job_info.get("run_count", 0),
            )
            
            await self._execute_job(job_info, context)
        
        return wrapped
    
    async def _invoke_job_func(
        self,
        func: Callable,
        context: JobContext,
        timeout: Optional[int] = None,
    ) -> Any:
        """执行任务函数，支持超时控制
        
        Args:
            func: 任务函数
            context: 任务上下文
            timeout: 超时时间（秒），None 表示不超时
            
        Returns:
            任务函数的返回值
            
        Raises:
            asyncio.TimeoutError: 超时
        """
        # 检查函数是否接受 context 参数
        sig = inspect.signature(func)
        
        async def run_func():
            if sig.parameters:
                # 有参数，传入 context
                if asyncio.iscoroutinefunction(func):
                    return await func(context)
                else:
                    return func(context)
            else:
                # 无参数
                if asyncio.iscoroutinefunction(func):
                    return await func()
                else:
                    return func()
        
        if timeout is not None:
            return await asyncio.wait_for(run_func(), timeout=timeout)
        else:
            return await run_func()
    
    async def _execute_job(
        self,
        job_info: Dict[str, Any],
        context: JobContext,
    ):
        """执行任务"""
        func = job_info["func"]
        code = job_info["code"]
        timeout = job_info.get("timeout")
        concurrent = job_info.get("concurrent", True)
        
        # 对于多触发器子任务，使用父任务的 code 记录历史
        history_code = job_info.get("parent_code") or code
        
        # 如果不允许并发，尝试获取分布式锁
        lock = None
        lock_acquired = False
        if not concurrent:
            lock = self._get_distributed_lock()
            lock_key = f"job:{code}"
            lock_timeout = timeout or self.settings.lock_timeout
            lock_acquired = await lock.acquire(lock_key, lock_timeout)
            
            if not lock_acquired:
                logger.info(
                    f"Job {code} skipped: another instance is running "
                    f"(run_id: {context.run_id})"
                )
                return
        
        # 记录执行开始
        history_manager = self._get_history_manager()
        history_manager.record_start(context)
        
        try:
            # 更新统计
            job_info["run_count"] = job_info.get("run_count", 0) + 1
            job_info["last_run_time"] = context.start_time
            job_info["last_run_id"] = context.run_id
            
            # 执行任务（可能带超时）
            result = await self._invoke_job_func(func, context, timeout)
            
            # 执行成功
            end_time = datetime.now()
            duration_ms = int((end_time - context.start_time).total_seconds() * 1000)
            
            job_info["success_count"] = job_info.get("success_count", 0) + 1
            job_info["last_status"] = "success"
            
            # 记录执行成功
            history_manager.record_success(context, result, duration_ms)
            
            # 触发成功事件
            event = JobExecutedEvent(
                job_id=job_info["id"],
                job_code=code,
                job_name=job_info["name"],
                run_id=context.run_id,
                scheduled_time=context.scheduled_time,
                start_time=context.start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                attempt=context.attempt,
                trigger_type=context.trigger_type,
                result=result,
            )
            await self._emit_event("job_executed", event)
            
            logger.info(
                f"Job executed successfully: {code}, "
                f"run_id: {context.run_id}, duration: {duration_ms}ms"
            )
            
        except asyncio.TimeoutError:
            # 超时失败
            end_time = datetime.now()
            duration_ms = int((end_time - context.start_time).total_seconds() * 1000)
            error_msg = f"Job timed out after {timeout}s"
            error_tb = ""
            
            job_info["fail_count"] = job_info.get("fail_count", 0) + 1
            job_info["last_status"] = "timeout"
            
            # 记录执行失败
            history_manager.record_failure(context, error_msg, error_tb, duration_ms)
            
            # 触发失败事件
            event = JobErrorEvent(
                job_id=job_info["id"],
                job_code=code,
                job_name=job_info["name"],
                run_id=context.run_id,
                scheduled_time=context.scheduled_time,
                start_time=context.start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                attempt=context.attempt,
                trigger_type=context.trigger_type,
                error=error_msg,
                traceback=error_tb,
                exception=asyncio.TimeoutError(error_msg),
            )
            await self._emit_event("job_error", event)
            
            logger.error(
                f"Job timeout: {code}, run_id: {context.run_id}, "
                f"timeout: {timeout}s, duration: {duration_ms}ms"
            )
            
            # 检查是否需要重试
            timeout_exc = asyncio.TimeoutError(error_msg)
            if self._should_retry(job_info, timeout_exc, context.attempt):
                await self._schedule_retry(job_info, context, error_msg, timeout_exc)
                
        except Exception as e:
            # 执行失败
            end_time = datetime.now()
            duration_ms = int((end_time - context.start_time).total_seconds() * 1000)
            error_msg = str(e)
            error_tb = traceback.format_exc()
            
            job_info["fail_count"] = job_info.get("fail_count", 0) + 1
            job_info["last_status"] = "failed"
            
            # 记录执行失败
            history_manager.record_failure(context, error_msg, error_tb, duration_ms)
            
            # 触发失败事件
            event = JobErrorEvent(
                job_id=job_info["id"],
                job_code=code,
                job_name=job_info["name"],
                run_id=context.run_id,
                scheduled_time=context.scheduled_time,
                start_time=context.start_time,
                end_time=end_time,
                duration_ms=duration_ms,
                attempt=context.attempt,
                trigger_type=context.trigger_type,
                error=error_msg,
                traceback=error_tb,
                exception=e,
            )
            await self._emit_event("job_error", event)
            
            logger.error(
                f"Job failed: {code}, run_id: {context.run_id}, "
                f"error: {error_msg}"
            )
            
            # 检查是否需要重试
            if self._should_retry(job_info, e, context.attempt):
                await self._schedule_retry(job_info, context, error_msg, e)
        
        finally:
            # 释放分布式锁
            if lock and lock_acquired:
                try:
                    await lock.release(f"job:{code}")
                except Exception as e:
                    logger.warning(f"Failed to release lock for job {code}: {e}")
    
    def _should_retry(
        self,
        job_info: Dict[str, Any],
        exception: Exception,
        current_attempt: int,
    ) -> bool:
        """判断是否应该重试
        
        Args:
            job_info: 任务信息
            exception: 捕获的异常
            current_attempt: 当前重试次数
            
        Returns:
            是否应该重试
        """
        retry_strategy = job_info.get("retry_strategy")
        max_retries = job_info.get("max_retries", 0)
        
        if retry_strategy:
            return retry_strategy.should_retry(exception, current_attempt)
        else:
            # 使用简单的次数判断
            return current_attempt < max_retries + 1
    
    async def _schedule_retry(
        self,
        job_info: Dict[str, Any],
        context: JobContext,
        error: str,
        exception: Optional[Exception] = None,
    ):
        """安排重试"""
        retry_strategy = job_info.get("retry_strategy")
        next_attempt = context.attempt + 1
        
        # 使用 retry_strategy 计算延迟（如果有）
        if retry_strategy:
            retry_delay = retry_strategy.get_delay(next_attempt)
        else:
            retry_delay = job_info.get("retry_delay", 60)
        
        # 触发重试事件
        event = JobRetryEvent(
            job_id=job_info["id"],
            job_code=job_info["code"],
            job_name=job_info["name"],
            run_id=context.run_id,
            scheduled_time=context.scheduled_time,
            start_time=context.start_time,
            attempt=next_attempt,
            trigger_type="retry",
            error=error,
            max_retries=job_info.get("max_retries", 0),
        )
        await self._emit_event("job_retry", event)
        
        logger.info(
            f"Scheduling retry for job {job_info['code']}, "
            f"attempt {next_attempt}, delay: {retry_delay}s"
        )
        
        # 延迟后重试
        await asyncio.sleep(retry_delay)
        
        # 创建新的上下文
        new_context = JobContext(
            job_id=context.job_id,
            job_code=context.job_code,
            job_name=context.job_name,
            job_description=context.job_description,
            run_id=generate_run_id(),
            scheduled_time=context.scheduled_time,
            start_time=datetime.now(),
            attempt=next_attempt,
            trigger_type="retry",
            run_count=job_info.get("run_count", 0),
            retry_of=context.run_id,
        )
        
        await self._execute_job(job_info, new_context)
    
    async def _emit_event(self, event_type: str, event: JobEvent):
        """触发事件"""
        listeners = self._event_listeners.get(event_type, [])
        for listener in listeners:
            try:
                if asyncio.iscoroutinefunction(listener):
                    await listener(event)
                else:
                    listener(event)
            except Exception as e:
                logger.error(f"Error in event listener: {e}")
    
    def _on_job_executed(self, event: JobExecutionEvent):
        """APScheduler 任务执行成功回调"""
        pass  # 已在 _execute_job 中处理
    
    def _on_job_error(self, event: JobExecutionEvent):
        """APScheduler 任务执行失败回调"""
        pass  # 已在 _execute_job 中处理
    
    def _on_job_missed(self, event: JobExecutionEvent):
        """APScheduler 任务错过执行回调"""
        job_id = event.job_id
        
        # 查找对应的任务
        for code, job_info in self._jobs.items():
            if job_info["apscheduler_id"] == job_id:
                missed_event = JobMissedEvent(
                    job_id=job_info["id"],
                    job_code=code,
                    job_name=job_info["name"],
                    run_id=generate_run_id(),
                    scheduled_time=event.scheduled_run_time,
                )
                asyncio.create_task(self._emit_event("job_missed", missed_event))
                logger.warning(f"Job missed: {code}")
                break
    
    # ========== 统计 ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """获取调度器统计信息"""
        total_jobs = len(self._jobs)
        active_jobs = sum(1 for j in self._jobs.values() if not j.get("is_paused"))
        paused_jobs = total_jobs - active_jobs
        
        total_runs = sum(j.get("run_count", 0) for j in self._jobs.values())
        success_runs = sum(j.get("success_count", 0) for j in self._jobs.values())
        failed_runs = sum(j.get("fail_count", 0) for j in self._jobs.values())
        
        return {
            "total_jobs": total_jobs,
            "active_jobs": active_jobs,
            "paused_jobs": paused_jobs,
            "total_runs": total_runs,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_runs / total_runs * 100, 2) if total_runs > 0 else 0,
            "is_running": self._running,
        }
    
    def get_job_stats(self, code: str) -> Optional[Dict[str, Any]]:
        """获取单个任务的详细统计信息
        
        Args:
            code: 任务编码
        
        Returns:
            任务统计信息字典，任务不存在时返回 None
        
        Examples:
            stats = scheduler.get_job_stats("DAILY_REPORT")
            # {
            #     "code": "DAILY_REPORT",
            #     "name": "每日报表",
            #     "description": "每天早上8点生成销售报表",
            #     "total_runs": 30,
            #     "success_runs": 28,
            #     "failed_runs": 2,
            #     "success_rate": 93.33,
            #     "avg_duration_ms": 5678,
            #     "last_run_id": "run_20260121_080000_a1b2c3",
            #     "last_run_time": "2026-01-21 08:00:00",
            #     "last_status": "success",
            #     "next_run_time": "2026-01-22 08:00:00",
            #     "is_paused": False,
            # }
        """
        if code not in self._jobs:
            return None
        
        job_info = self._jobs[code]
        
        total_runs = job_info.get("run_count", 0)
        success_runs = job_info.get("success_count", 0)
        failed_runs = job_info.get("fail_count", 0)
        
        # 计算下次执行时间
        next_run_time = None
        if self._scheduler and self._running:
            try:
                apscheduler_job = self._scheduler.get_job(job_info["apscheduler_id"])
                if apscheduler_job:
                    next_run_time = apscheduler_job.next_run_time
            except Exception:
                pass
        
        # 尝试从历史记录获取更详细的统计
        avg_duration_ms = None
        try:
            history_manager = self._get_history_manager()
            stats_records = history_manager.get_stats(job_code=code)
            if stats_records:
                total_duration = sum(s.total_duration or 0 for s in stats_records)
                total_stat_runs = sum(s.total_runs or 0 for s in stats_records)
                if total_stat_runs > 0:
                    avg_duration_ms = total_duration // total_stat_runs
        except Exception:
            pass
        
        return {
            "code": code,
            "name": job_info.get("name"),
            "description": job_info.get("description"),
            "total_runs": total_runs,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_runs / total_runs * 100, 2) if total_runs > 0 else 0,
            "avg_duration_ms": avg_duration_ms,
            "last_run_id": job_info.get("last_run_id"),
            "last_run_time": job_info.get("last_run_time"),
            "last_status": job_info.get("last_status"),
            "next_run_time": next_run_time,
            "is_paused": job_info.get("is_paused", False),
            "is_multi_trigger": job_info.get("is_multi_trigger", False),
            "trigger_count": len(job_info.get("triggers", [])) if job_info.get("is_multi_trigger") else 1,
        }
