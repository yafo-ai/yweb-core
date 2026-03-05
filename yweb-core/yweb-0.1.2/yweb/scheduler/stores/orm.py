"""ORM 任务存储

基于 YWeb ORM 的任务持久化存储，支持应用重启后恢复任务。

使用示例:
    from yweb.scheduler import create_scheduler_models, Scheduler
    from yweb.config import SchedulerSettings
    
    # 创建模型
    scheduler_models = create_scheduler_models(table_prefix="sys_")
    
    # 获取 ORM 存储
    orm_store = scheduler_models.get_orm_store()
    
    # 或者直接实例化
    from yweb.scheduler.stores import ORMJobStore
    orm_store = ORMJobStore(job_model=scheduler_models.SchedulerJob)
"""

import pickle
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any, Type

from apscheduler.jobstores.base import BaseJobStore, JobLookupError, ConflictingIdError
from apscheduler.job import Job as APSchedulerJob
from apscheduler.util import datetime_to_utc_timestamp, utc_timestamp_to_datetime

logger = logging.getLogger(__name__)


class ORMJobStore(BaseJobStore):
    """基于 YWeb ORM 的任务存储
    
    将任务持久化到数据库，支持：
    - 应用重启后恢复任务
    - 多实例共享任务状态
    - 任务历史查询
    
    使用示例:
        # 方式1：通过工厂（推荐）
        scheduler_models = create_scheduler_models(table_prefix="sys_")
        orm_store = scheduler_models.get_orm_store()
        
        # 方式2：直接实例化
        orm_store = ORMJobStore(job_model=SchedulerJob)
    
    Attributes:
        pickle_protocol: pickle 序列化协议版本
    """
    
    def __init__(
        self,
        pickle_protocol: int = pickle.HIGHEST_PROTOCOL,
        scheduler=None,
        job_model: Type = None,
    ):
        """初始化 ORM 存储
        
        Args:
            pickle_protocol: pickle 序列化协议版本
            scheduler: Scheduler 实例（可选）
            job_model: SchedulerJob 模型类（必须）
        """
        super().__init__()
        self.pickle_protocol = pickle_protocol
        self._job_model = job_model
    
    @property
    def job_model(self) -> Type:
        """获取任务模型类"""
        if self._job_model is None:
            raise RuntimeError(
                "job_model 未设置。请通过 create_scheduler_models() 创建模型后使用 "
                "scheduler_models.get_orm_store() 获取存储，或直接传入 job_model 参数。"
            )
        return self._job_model
    
    def lookup_job(self, job_id: str) -> Optional[APSchedulerJob]:
        """根据 ID 查找任务
        
        Args:
            job_id: APScheduler 任务 ID（对应 SchedulerJob.code）
        
        Returns:
            APScheduler Job 实例，不存在则返回 None
        """
        # 从 apscheduler_id 查找（格式: yweb_{code}）
        code = job_id.replace("yweb_", "") if job_id.startswith("yweb_") else job_id
        
        JobModel = self.job_model
        job_record = JobModel.query.filter(
            JobModel.code == code
        ).first()
        
        if job_record is None:
            return None
        
        return self._reconstitute_job(job_record)
    
    def get_due_jobs(self, now: datetime) -> List[APSchedulerJob]:
        """获取到期的任务
        
        Args:
            now: 当前时间
        
        Returns:
            到期任务列表
        """
        timestamp = datetime_to_utc_timestamp(now)
        
        JobModel = self.job_model
        job_records = JobModel.query.filter(
            JobModel.next_run_time <= now,
            JobModel.is_enabled == True
        ).order_by(JobModel.next_run_time).all()
        
        return [self._reconstitute_job(r) for r in job_records if r]
    
    def get_next_run_time(self) -> Optional[datetime]:
        """获取最近的下次执行时间
        
        Returns:
            最近的执行时间，无任务则返回 None
        """
        JobModel = self.job_model
        job_record = JobModel.query.filter(
            JobModel.next_run_time != None,
            JobModel.is_enabled == True
        ).order_by(JobModel.next_run_time).first()
        
        if job_record:
            return job_record.next_run_time
        return None
    
    def get_all_jobs(self) -> List[APSchedulerJob]:
        """获取所有任务
        
        Returns:
            所有任务列表
        """
        JobModel = self.job_model
        job_records = JobModel.query.all()
        
        jobs = []
        for record in job_records:
            try:
                job = self._reconstitute_job(record)
                if job:
                    jobs.append(job)
            except Exception as e:
                logger.error(f"Failed to reconstitute job {record.code}: {e}")
        
        return jobs
    
    def add_job(self, job: APSchedulerJob):
        """添加任务
        
        Args:
            job: APScheduler Job 实例
        
        Raises:
            ConflictingIdError: 任务 ID 已存在
        """
        code = job.id.replace("yweb_", "") if job.id.startswith("yweb_") else job.id
        
        JobModel = self.job_model
        
        # 检查是否已存在
        existing = JobModel.query.filter(
            JobModel.code == code
        ).first()
        
        if existing:
            raise ConflictingIdError(job.id)
        
        # 序列化任务状态
        job_state = job.__getstate__()
        
        # 创建记录
        job_record = JobModel(
            code=code,
            name=job.name or code,
            description=None,
            trigger_type=self._get_trigger_type(job.trigger),
            trigger_args=self._serialize_trigger(job.trigger),
            func_ref=f"{job.func.__module__}:{job.func.__name__}" if hasattr(job.func, '__module__') else str(job.func),
            args=list(job.args) if job.args else [],
            kwargs=dict(job.kwargs) if job.kwargs else {},
            executor=job.executor,
            concurrent=job.max_instances > 1,
            max_instances=job.max_instances,
            misfire_grace_time=job.misfire_grace_time,
            coalesce=job.coalesce,
            is_enabled=True,
            next_run_time=job.next_run_time,
        )
        
        # 存储完整的 job state 用于恢复
        job_record.kwargs["__job_state__"] = pickle.dumps(job_state, self.pickle_protocol).hex()
        
        job_record.save()
        logger.debug(f"Added job {code} to ORM store")
    
    def update_job(self, job: APSchedulerJob):
        """更新任务
        
        Args:
            job: APScheduler Job 实例
        
        Raises:
            JobLookupError: 任务不存在
        """
        code = job.id.replace("yweb_", "") if job.id.startswith("yweb_") else job.id
        
        JobModel = self.job_model
        job_record = JobModel.query.filter(
            JobModel.code == code
        ).first()
        
        if job_record is None:
            raise JobLookupError(job.id)
        
        # 更新字段
        job_record.next_run_time = job.next_run_time
        job_record.trigger_type = self._get_trigger_type(job.trigger)
        job_record.trigger_args = self._serialize_trigger(job.trigger)
        
        # 更新 job state
        job_state = job.__getstate__()
        job_record.kwargs["__job_state__"] = pickle.dumps(job_state, self.pickle_protocol).hex()
        
        job_record.save()
        logger.debug(f"Updated job {code} in ORM store")
    
    def remove_job(self, job_id: str):
        """删除任务
        
        Args:
            job_id: APScheduler 任务 ID
        
        Raises:
            JobLookupError: 任务不存在
        """
        code = job_id.replace("yweb_", "") if job_id.startswith("yweb_") else job_id
        
        JobModel = self.job_model
        job_record = JobModel.query.filter(
            JobModel.code == code
        ).first()
        
        if job_record is None:
            raise JobLookupError(job_id)
        
        # 软删除
        job_record.delete()
        logger.debug(f"Removed job {code} from ORM store")
    
    def remove_all_jobs(self):
        """删除所有任务"""
        JobModel = self.job_model
        job_records = JobModel.query.all()
        
        for record in job_records:
            record.delete()
        
        logger.debug("Removed all jobs from ORM store")
    
    def _reconstitute_job(self, job_record) -> Optional[APSchedulerJob]:
        """从数据库记录恢复 APScheduler Job
        
        Args:
            job_record: 数据库记录
        
        Returns:
            APScheduler Job 实例
        """
        try:
            # 尝试从存储的 state 恢复
            job_state_hex = job_record.kwargs.get("__job_state__")
            if job_state_hex:
                job_state = pickle.loads(bytes.fromhex(job_state_hex))
                job = APSchedulerJob.__new__(APSchedulerJob)
                job.__setstate__(job_state)
                job._scheduler = self._scheduler
                job._jobstore_alias = self._alias
                return job
        except Exception as e:
            logger.warning(f"Failed to restore job from state: {e}")
        
        return None
    
    def _get_trigger_type(self, trigger) -> str:
        """获取触发器类型名称"""
        trigger_class = trigger.__class__.__name__
        type_map = {
            "CronTrigger": "cron",
            "IntervalTrigger": "interval",
            "DateTrigger": "once",
        }
        return type_map.get(trigger_class, "unknown")
    
    def _serialize_trigger(self, trigger) -> Dict[str, Any]:
        """序列化触发器参数"""
        trigger_type = self._get_trigger_type(trigger)
        
        if trigger_type == "cron":
            return {
                "year": str(trigger.fields[6]) if len(trigger.fields) > 6 else "*",
                "month": str(trigger.fields[5]) if len(trigger.fields) > 5 else "*",
                "day": str(trigger.fields[4]) if len(trigger.fields) > 4 else "*",
                "week": str(trigger.fields[3]) if len(trigger.fields) > 3 else "*",
                "day_of_week": str(trigger.fields[6]) if len(trigger.fields) > 6 else "*",
                "hour": str(trigger.fields[2]),
                "minute": str(trigger.fields[1]),
                "second": str(trigger.fields[0]),
                "timezone": str(trigger.timezone) if trigger.timezone else None,
            }
        elif trigger_type == "interval":
            return {
                "weeks": trigger.interval.days // 7,
                "days": trigger.interval.days % 7,
                "hours": trigger.interval.seconds // 3600,
                "minutes": (trigger.interval.seconds % 3600) // 60,
                "seconds": trigger.interval.seconds % 60,
                "timezone": str(trigger.timezone) if hasattr(trigger, 'timezone') and trigger.timezone else None,
            }
        elif trigger_type == "once":
            return {
                "run_date": trigger.run_date.isoformat() if trigger.run_date else None,
                "timezone": str(trigger.timezone) if hasattr(trigger, 'timezone') and trigger.timezone else None,
            }
        
        return {}
