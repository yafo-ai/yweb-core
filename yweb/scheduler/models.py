"""定时任务 ORM 抽象模型

提供任务定义、执行历史、统计等数据的抽象模型。
用户需要通过 create_scheduler_models() 工厂函数或继承抽象类来创建具体模型。

模型说明:
    - AbstractSchedulerJob: 任务定义表，存储任务配置
    - AbstractSchedulerJobHistory: 执行历史表，记录每次执行详情
    - AbstractSchedulerJobStats: 统计表，按天/小时聚合统计

使用示例:
    # 方式1：使用工厂函数（推荐）
    from yweb.scheduler import create_scheduler_models
    
    scheduler_models = create_scheduler_models(table_prefix="sys_")
    SchedulerJob = scheduler_models.SchedulerJob
    
    # 方式2：继承抽象类（完全自定义）
    from yweb.scheduler.models import AbstractSchedulerJob
    
    class SchedulerJob(AbstractSchedulerJob):
        __tablename__ = "my_scheduler_job"
        # 可添加自定义字段
        tenant_id = mapped_column(String(50), index=True)
"""

from datetime import datetime, date
from typing import Optional, List, Dict, Any
from sqlalchemy import String, Text, Integer, Boolean, DateTime, Date, JSON, UniqueConstraint, Float
from sqlalchemy.orm import Mapped, mapped_column

from ..orm import CoreModel
from ..orm.orm_extensions.soft_delete_mixin import SimpleSoftDeleteMixin


class AbstractSchedulerJob(CoreModel, SimpleSoftDeleteMixin):
    """定时任务抽象模型
    
    存储任务定义，支持应用重启后恢复任务。
    
    标识说明：
    - id: 继承自 CoreModel，自动生成（UUID/雪花ID）
    - code: 业务编码，用户定义，用于 API 操作
    - name: 任务名称，用于展示
    - description: 任务描述
    
    使用示例:
        from yweb.scheduler.models import AbstractSchedulerJob
        
        class SchedulerJob(AbstractSchedulerJob):
            __tablename__ = "sys_scheduler_job"
            
            # 可添加自定义字段
            tenant_id = mapped_column(String(50), index=True, comment="租户ID")
    """
    __abstract__ = True
    
    # ===== 任务标识 =====
    # id 继承自 CoreModel，自动生成
    code: Mapped[str] = mapped_column(
        String(100), unique=True, index=True, 
        comment="业务编码，用于API操作"
    )
    name: Mapped[str] = mapped_column(String(200), comment="任务名称")
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="任务描述")
    
    # ===== 触发器配置 =====
    trigger_type: Mapped[str] = mapped_column(
        String(50), comment="触发器类型: cron|interval|once"
    )
    trigger_args: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, comment="触发器参数")
    
    # ===== 任务目标 =====
    func_ref: Mapped[str] = mapped_column(String(500), comment="函数引用路径")
    args: Mapped[List[Any]] = mapped_column(JSON, default=list, comment="位置参数")
    kwargs: Mapped[Dict[str, Any]] = mapped_column(JSON, default=dict, comment="关键字参数")
    
    # ===== 执行配置 =====
    executor: Mapped[str] = mapped_column(String(50), default="default", comment="执行器")
    concurrent: Mapped[bool] = mapped_column(Boolean, default=True, comment="是否允许并发执行")
    max_instances: Mapped[int] = mapped_column(Integer, default=1, comment="最大并发实例数")
    timeout: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="执行超时（秒）")
    
    # ===== 重试配置 =====
    max_retries: Mapped[int] = mapped_column(Integer, default=0, comment="最大重试次数")
    retry_delay: Mapped[int] = mapped_column(Integer, default=60, comment="重试间隔（秒）")
    retry_backoff: Mapped[float] = mapped_column(Float, default=1.0, comment="退避因子")
    
    # ===== 容错配置 =====
    misfire_grace_time: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, comment="错过执行宽限时间（秒）"
    )
    coalesce: Mapped[bool] = mapped_column(
        Boolean, default=True, comment="是否合并错过的执行"
    )
    
    # ===== 状态 =====
    is_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, index=True, comment="是否启用"
    )
    next_run_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, index=True, comment="下次执行时间"
    )
    
    # ===== 统计 =====
    run_count: Mapped[int] = mapped_column(Integer, default=0, comment="累计执行次数")
    success_count: Mapped[int] = mapped_column(Integer, default=0, comment="成功次数")
    fail_count: Mapped[int] = mapped_column(Integer, default=0, comment="失败次数")
    last_run_time: Mapped[Optional[datetime]] = mapped_column(
        DateTime, nullable=True, comment="上次执行时间"
    )
    last_run_id: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, comment="上次执行ID"
    )
    last_status: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="上次执行状态"
    )
    
    def __repr__(self) -> str:
        return f"<SchedulerJob(code={self.code}, name={self.name})>"


class AbstractSchedulerJobHistory(CoreModel):
    """任务执行历史抽象模型
    
    记录每次任务执行的详细信息。每次执行产生一条记录。
    
    标识说明：
    - id: 继承自 CoreModel，自动生成
    - run_id: 执行唯一标识，格式 run_{日期}_{时间}_{随机串}
    - job_id: 关联的任务ID
    - job_code: 关联的任务编码（冗余，便于查询）
    
    使用示例:
        from yweb.scheduler.models import AbstractSchedulerJobHistory
        
        class SchedulerJobHistory(AbstractSchedulerJobHistory):
            __tablename__ = "sys_scheduler_job_history"
    """
    __abstract__ = True
    
    # ===== 执行标识 =====
    run_id: Mapped[str] = mapped_column(
        String(50), unique=True, index=True, 
        comment="执行ID，如 run_20260121_080000_a1b2c3"
    )
    
    # ===== 任务关联 =====
    job_id: Mapped[str] = mapped_column(String(50), index=True, comment="任务ID")
    job_code: Mapped[str] = mapped_column(String(100), index=True, comment="任务编码")
    job_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True, comment="任务名称（快照）")
    
    # ===== 时间信息 =====
    scheduled_time: Mapped[datetime] = mapped_column(DateTime, comment="计划执行时间")
    start_time: Mapped[datetime] = mapped_column(DateTime, comment="实际开始时间")
    end_time: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True, comment="结束时间")
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="执行耗时(毫秒)")
    
    # ===== 执行状态 =====
    status: Mapped[str] = mapped_column(
        String(20), index=True, 
        comment="状态: pending|running|success|failed|timeout|cancelled"
    )
    
    # ===== 结果信息 =====
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="返回值(JSON)")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误信息")
    traceback: Mapped[Optional[str]] = mapped_column(Text, nullable=True, comment="错误堆栈")
    
    # ===== 重试信息 =====
    attempt: Mapped[int] = mapped_column(Integer, default=1, comment="第几次尝试（首次为1）")
    retry_of: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True, 
        comment="重试的原执行ID（首次执行为空）"
    )
    
    # ===== 触发信息 =====
    trigger_type: Mapped[str] = mapped_column(
        String(20), default="scheduled",
        comment="触发类型: scheduled|manual|retry"
    )
    
    # ===== 执行环境 =====
    hostname: Mapped[Optional[str]] = mapped_column(String(100), nullable=True, comment="执行主机")
    process_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="进程ID")
    
    def __repr__(self) -> str:
        return f"<SchedulerJobHistory(run_id={self.run_id}, status={self.status})>"


class AbstractSchedulerJobStats(CoreModel):
    """任务执行统计抽象模型
    
    按天/小时聚合的执行统计。
    
    使用示例:
        from yweb.scheduler.models import AbstractSchedulerJobStats
        
        class SchedulerJobStats(AbstractSchedulerJobStats):
            __tablename__ = "sys_scheduler_job_stats"
    """
    __abstract__ = True
    
    # ===== 统计维度 =====
    job_id: Mapped[str] = mapped_column(String(50), index=True, comment="任务ID")
    job_code: Mapped[str] = mapped_column(String(100), index=True, comment="任务编码")
    stat_date: Mapped[date] = mapped_column(Date, index=True, comment="统计日期")
    stat_hour: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=True, 
        comment="统计小时（0-23），NULL表示天级统计"
    )
    
    # ===== 执行次数 =====
    total_runs: Mapped[int] = mapped_column(Integer, default=0, comment="总执行次数")
    success_runs: Mapped[int] = mapped_column(Integer, default=0, comment="成功次数")
    failed_runs: Mapped[int] = mapped_column(Integer, default=0, comment="失败次数")
    timeout_runs: Mapped[int] = mapped_column(Integer, default=0, comment="超时次数")
    retry_runs: Mapped[int] = mapped_column(Integer, default=0, comment="重试次数")
    
    # ===== 耗时统计（毫秒） =====
    min_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="最小耗时")
    max_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="最大耗时")
    avg_duration: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, comment="平均耗时")
    total_duration: Mapped[int] = mapped_column(Integer, default=0, comment="总耗时")
    
    def __repr__(self) -> str:
        return f"<SchedulerJobStats(code={self.job_code}, date={self.stat_date})>"


__all__ = [
    "AbstractSchedulerJob",
    "AbstractSchedulerJobHistory",
    "AbstractSchedulerJobStats",
]
