"""任务执行上下文

提供任务执行时的上下文信息。

使用示例:
    @scheduler.cron("0 8 * * *", code="DAILY_REPORT")
    async def daily_report(context: JobContext):
        print(f"任务编码: {context.job_code}")
        print(f"执行ID: {context.run_id}")
        print(f"第几次尝试: {context.attempt}")
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any, Dict


@dataclass
class JobContext:
    """任务执行上下文
    
    包含任务执行时的所有相关信息。
    
    Attributes:
        job_id: 任务ID（自动生成的UUID）
        job_code: 任务编码（用户定义的业务编码）
        job_name: 任务名称
        job_description: 任务描述
        run_id: 本次执行ID（格式：run_YYYYMMDD_HHMMSS_XXXXXX）
        scheduled_time: 计划执行时间
        start_time: 实际开始时间
        attempt: 第几次尝试（首次为1，重试时递增）
        trigger_type: 触发类型（scheduled/manual/retry）
        run_count: 该任务历史累计执行次数
        extra: 额外的自定义数据
    """
    
    # 任务标识
    job_id: str
    job_code: str
    job_name: str
    job_description: Optional[str] = None
    
    # 执行标识
    run_id: str = ""
    
    # 时间信息
    scheduled_time: Optional[datetime] = None
    start_time: Optional[datetime] = None
    
    # 执行信息
    attempt: int = 1
    trigger_type: str = "scheduled"  # scheduled | manual | retry
    run_count: int = 0
    
    # 重试信息
    retry_of: Optional[str] = None  # 重试的原执行ID
    
    # 额外数据
    extra: Dict[str, Any] = field(default_factory=dict)
    
    def __str__(self) -> str:
        return f"JobContext(code={self.job_code}, run_id={self.run_id}, attempt={self.attempt})"
    
    def __repr__(self) -> str:
        return self.__str__()
