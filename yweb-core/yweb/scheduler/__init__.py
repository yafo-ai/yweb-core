"""定时任务调度模块

提供简洁易用的定时任务 API，基于 APScheduler 封装。

快速开始（推荐）:
================

1. 创建模型（显式控制表创建）:

    from yweb.scheduler import create_scheduler_models
    
    # 创建所有模型（此时才会注册到 Base.metadata）
    scheduler_models = create_scheduler_models(table_prefix="sys_")
    
    # 使用模型
    SchedulerJob = scheduler_models.SchedulerJob

2. 基础用法（内存模式，无需数据库）:

    from yweb import Scheduler, cron, interval, once

    scheduler = Scheduler()

    @scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
    async def daily_report(context):
        print(f"[{context.run_id}] 生成日报...")

    @scheduler.interval(minutes=30, code="SYNC_DATA", name="数据同步")
    async def sync_data():
        pass

    # FastAPI 集成
    scheduler.init_app(app)

3. 一站式设置（含 API 路由）:

    from yweb.scheduler import setup_scheduler, Scheduler
    
    scheduler = Scheduler()
    
    scheduler_models = setup_scheduler(
        app=app,
        table_prefix="sys_",
        api_prefix="/api/v1/scheduler",
        dependencies=[Depends(get_current_user)],
        scheduler_instance=scheduler,
    )

高级用法:
========

Job 类:
    from yweb.scheduler import Job, cron
    
    class DailyReportJob(Job):
        code = "DAILY_REPORT"
        trigger = cron("0 8 * * *")
        
        async def execute(self, context):
            pass
    
    scheduler.add_job_class(DailyReportJob)

JobBuilder:
    from yweb.scheduler import JobBuilder
    
    config = (
        JobBuilder(my_func)
        .code("MY_JOB")
        .trigger(cron("0 8 * * *"))
        .build()
    )
    scheduler.add_job_from_builder(config)

HttpJob:
    from yweb.scheduler import HttpJob
    
    class WebhookJob(HttpJob):
        code = "WEBHOOK"
        trigger = cron("0 8 * * *")
        url = "https://api.example.com/webhook"
        method = "POST"

RetryStrategy:
    from yweb.scheduler import RetryStrategy
    
    strategy = RetryStrategy.exponential(max_retries=5, base_delay=10)

自定义模型（添加字段）:
    from yweb.scheduler import create_scheduler_models
    from sqlalchemy import String
    from sqlalchemy.orm import Mapped, mapped_column
    
    class JobTenantMixin:
        '''多租户支持'''
        tenant_id: Mapped[str] = mapped_column(String(50), index=True)
    
    scheduler_models = create_scheduler_models(
        table_prefix="sys_",
        job_mixin=JobTenantMixin,
    )

继承抽象类（完全自定义）:
    from yweb.scheduler.models import AbstractSchedulerJob
    
    class SchedulerJob(AbstractSchedulerJob):
        __tablename__ = "my_scheduler_job"
        # 完全自定义...
"""

from .triggers import cron, interval, once
from .context import JobContext
from .events import (
    JobEvent,
    JobExecutedEvent,
    JobErrorEvent,
    JobRetryEvent,
    JobMissedEvent,
    JobPausedEvent,
    JobResumedEvent,
)
from .scheduler import Scheduler
from .job import Job
from .builder import JobBuilder, JobConfig
from .retry import RetryStrategy
from .http_job import HttpJob, HttpJobConfig, HttpResponse, HttpJobError, HttpRetryError
from .api import create_scheduler_router, setup_scheduler_api  # api/ 子目录
from .locks import DistributedLock, RedisDistributedLock, MemoryLock, create_distributed_lock
from .stores import BaseStore, MemoryStore, ORMJobStore
from .executors import AsyncExecutor, ThreadExecutor
from .history import HistoryManager

# 工厂函数（推荐）
from .factory import (
    create_scheduler_models,
    setup_scheduler,
    SchedulerModels,
)

# 抽象模型（高级用法）
from .models import (
    AbstractSchedulerJob,
    AbstractSchedulerJobHistory,
    AbstractSchedulerJobStats,
)

__all__ = [
    # ===== 核心类（推荐） =====
    "Scheduler",
    "JobBuilder",
    
    # ===== 工厂函数（推荐） =====
    "create_scheduler_models",
    "setup_scheduler",
    "SchedulerModels",
    
    # ===== 触发器 =====
    "cron",
    "interval",
    "once",
    
    # ===== 任务基类 =====
    "Job",
    "HttpJob",
    
    # ===== 重试策略 =====
    "RetryStrategy",
    
    # ===== 执行上下文 =====
    "JobContext",
    "JobConfig",
    
    # ===== HTTP 任务 =====
    "HttpJobConfig",
    "HttpResponse",
    "HttpJobError",
    "HttpRetryError",
    
    # ===== 事件类 =====
    "JobEvent",
    "JobExecutedEvent",
    "JobErrorEvent",
    "JobRetryEvent",
    "JobMissedEvent",
    "JobPausedEvent",
    "JobResumedEvent",
    
    # ===== 管理 API =====
    "create_scheduler_router",
    "setup_scheduler_api",
    
    # ===== 抽象模型（高级用法） =====
    "AbstractSchedulerJob",
    "AbstractSchedulerJobHistory",
    "AbstractSchedulerJobStats",
    
    # ===== 历史管理 =====
    "HistoryManager",
    
    # ===== 分布式锁 =====
    "DistributedLock",
    "RedisDistributedLock",
    "MemoryLock",
    "create_distributed_lock",
    
    # ===== 存储 =====
    "BaseStore",
    "MemoryStore",
    "ORMJobStore",
    
    # ===== 执行器 =====
    "AsyncExecutor",
    "ThreadExecutor",
]
