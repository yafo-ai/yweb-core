"""任务事件类

提供任务执行过程中的事件信息。

使用示例:
    @scheduler.on_job_executed
    async def on_success(event: JobExecutedEvent):
        print(f"任务 {event.job_code} 执行成功")
    
    @scheduler.on_job_error
    async def on_error(event: JobErrorEvent):
        print(f"任务 {event.job_code} 执行失败: {event.error}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any


@dataclass
class JobEvent:
    """任务事件基类"""
    
    # 任务标识
    job_id: str
    job_code: str
    job_name: str
    
    # 执行标识
    run_id: str
    
    # 时间信息
    scheduled_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    
    # 执行信息
    attempt: int = 1
    trigger_type: str = "scheduled"


@dataclass
class JobExecutedEvent(JobEvent):
    """任务执行成功事件"""
    
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    result: Any = None


@dataclass
class JobErrorEvent(JobEvent):
    """任务执行失败事件"""
    
    end_time: Optional[datetime] = None
    duration_ms: int = 0
    error: Optional[str] = None
    traceback: Optional[str] = None
    exception: Optional[Exception] = None


@dataclass
class JobRetryEvent(JobEvent):
    """任务重试事件"""
    
    error: Optional[str] = None
    next_retry_time: Optional[datetime] = None
    max_retries: int = 0


@dataclass
class JobMissedEvent(JobEvent):
    """任务错过执行事件"""
    
    pass


@dataclass
class JobPausedEvent(JobEvent):
    """任务暂停事件"""
    
    pass


@dataclass
class JobResumedEvent(JobEvent):
    """任务恢复事件"""
    
    pass
