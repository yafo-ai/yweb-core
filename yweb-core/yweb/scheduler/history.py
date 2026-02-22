"""执行历史管理

提供任务执行历史的记录和查询功能。

使用示例:
    from yweb.scheduler import create_scheduler_models
    
    # 创建模型
    scheduler_models = create_scheduler_models(table_prefix="sys_")
    
    # 获取历史管理器
    history_manager = scheduler_models.get_history_manager()
    
    # 查询执行历史
    executions = history_manager.get_executions("DAILY_REPORT", limit=10)
    
    # 查询单次执行
    execution = history_manager.get_execution("run_20260121_080000_abc123")
"""

import json
import logging
import socket
import os
from datetime import datetime, date, timedelta
from typing import Optional, List, Dict, Any, Union, Type

from .context import JobContext
from .events import JobExecutedEvent, JobErrorEvent

logger = logging.getLogger(__name__)


class HistoryManager:
    """执行历史管理器
    
    负责记录任务执行历史、查询历史记录、更新统计数据。
    
    支持两种使用方式：
    1. 通过工厂函数创建（推荐）：scheduler_models.get_history_manager()
    2. 直接实例化并传入模型类
    
    使用示例:
        # 方式1：通过工厂（推荐）
        scheduler_models = create_scheduler_models(table_prefix="sys_")
        history_manager = scheduler_models.get_history_manager()
        
        # 方式2：直接实例化
        history_manager = HistoryManager(
            job_model=SchedulerJob,
            history_model=SchedulerJobHistory,
            stats_model=SchedulerJobStats,
        )
    """
    
    def __init__(
        self,
        enabled: bool = True,
        retention_days: int = 30,
        job_model: Type = None,
        history_model: Type = None,
        stats_model: Type = None,
    ):
        """初始化历史管理器
        
        Args:
            enabled: 是否启用历史记录
            retention_days: 历史记录保留天数
            job_model: SchedulerJob 模型类（可选）
            history_model: SchedulerJobHistory 模型类（必须）
            stats_model: SchedulerJobStats 模型类（必须）
        """
        self.enabled = enabled
        self.retention_days = retention_days
        
        # 保存模型类引用
        self._job_model = job_model
        self._history_model = history_model
        self._stats_model = stats_model
    
    @property
    def job_model(self) -> Type:
        """获取任务模型类"""
        if self._job_model is None:
            raise RuntimeError(
                "job_model 未设置。请通过 create_scheduler_models() 创建模型后使用 "
                "scheduler_models.get_history_manager() 获取历史管理器。"
            )
        return self._job_model
    
    @property
    def history_model(self) -> Type:
        """获取历史模型类"""
        if self._history_model is None:
            raise RuntimeError(
                "history_model 未设置。请通过 create_scheduler_models() 创建模型后使用 "
                "scheduler_models.get_history_manager() 获取历史管理器。"
            )
        return self._history_model
    
    @property
    def stats_model(self) -> Type:
        """获取统计模型类"""
        if self._stats_model is None:
            raise RuntimeError(
                "stats_model 未设置。请通过 create_scheduler_models() 创建模型后使用 "
                "scheduler_models.get_history_manager() 获取历史管理器。"
            )
        return self._stats_model
    
    def record_start(
        self,
        context: JobContext,
    ) -> Optional[Any]:
        """记录任务开始执行
        
        Args:
            context: 任务执行上下文
        
        Returns:
            历史记录实例
        """
        if not self.enabled:
            return None
        
        try:
            history = self.history_model(
                run_id=context.run_id,
                job_id=context.job_id,
                job_code=context.job_code,
                job_name=context.job_name,
                scheduled_time=context.scheduled_time or datetime.now(),
                start_time=context.start_time or datetime.now(),
                status="running",
                attempt=context.attempt,
                retry_of=context.retry_of,
                trigger_type=context.trigger_type,
                hostname=socket.gethostname(),
                process_id=os.getpid(),
            )
            history.save(commit=True)
            return history
        except Exception as e:
            logger.error(f"Failed to record job start: {e}")
            return None
    
    def record_success(
        self,
        context: JobContext,
        result: Any = None,
        duration_ms: int = 0,
    ) -> Optional[Any]:
        """记录任务执行成功
        
        Args:
            context: 任务执行上下文
            result: 执行结果
            duration_ms: 执行耗时（毫秒）
        
        Returns:
            更新后的历史记录
        """
        if not self.enabled:
            return None
        
        try:
            HistoryModel = self.history_model
            history = HistoryModel.query.filter(
                HistoryModel.run_id == context.run_id
            ).first()
            
            if history:
                history.status = "success"
                history.end_time = datetime.now()
                history.duration_ms = duration_ms
                history.result = json.dumps(result) if result is not None else None
                history.save(commit=True)
                
                # 更新任务统计
                self._update_job_stats(context.job_id, context.job_code, "success", duration_ms)
                
                return history
        except Exception as e:
            logger.error(f"Failed to record job success: {e}")
        
        return None
    
    def record_failure(
        self,
        context: JobContext,
        error: str,
        traceback: Optional[str] = None,
        duration_ms: int = 0,
    ) -> Optional[Any]:
        """记录任务执行失败
        
        Args:
            context: 任务执行上下文
            error: 错误信息
            traceback: 错误堆栈
            duration_ms: 执行耗时（毫秒）
        
        Returns:
            更新后的历史记录
        """
        if not self.enabled:
            return None
        
        try:
            HistoryModel = self.history_model
            history = HistoryModel.query.filter(
                HistoryModel.run_id == context.run_id
            ).first()
            
            if history:
                history.status = "failed"
                history.end_time = datetime.now()
                history.duration_ms = duration_ms
                history.error = error
                history.traceback = traceback
                history.save(commit=True)
                
                # 更新任务统计
                self._update_job_stats(context.job_id, context.job_code, "failed", duration_ms)
                
                return history
        except Exception as e:
            logger.error(f"Failed to record job failure: {e}")
        
        return None
    
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
        HistoryModel = self.history_model
        query = HistoryModel.query
        
        if job_code:
            query = query.filter(HistoryModel.job_code == job_code)
        
        if status:
            query = query.filter(HistoryModel.status == status)
        
        if start_date:
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_date = datetime.combine(start_date, datetime.min.time())
            query = query.filter(HistoryModel.start_time >= start_date)
        
        if end_date:
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_date = datetime.combine(end_date, datetime.max.time())
            query = query.filter(HistoryModel.start_time <= end_date)
        
        return query.order_by(
            HistoryModel.start_time.desc()
        ).offset(offset).limit(limit).all()
    
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
        HistoryModel = self.history_model
        query = HistoryModel.query
        
        if job_code:
            query = query.filter(HistoryModel.job_code == job_code)
        
        if status:
            query = query.filter(HistoryModel.status == status)
        
        if start_date:
            if isinstance(start_date, date) and not isinstance(start_date, datetime):
                start_date = datetime.combine(start_date, datetime.min.time())
            query = query.filter(HistoryModel.start_time >= start_date)
        
        if end_date:
            if isinstance(end_date, date) and not isinstance(end_date, datetime):
                end_date = datetime.combine(end_date, datetime.max.time())
            query = query.filter(HistoryModel.start_time <= end_date)
        
        return query.count()
    
    def get_execution(self, run_id: str) -> Optional[Any]:
        """查询单次执行记录
        
        Args:
            run_id: 执行ID
        
        Returns:
            执行历史记录
        """
        HistoryModel = self.history_model
        return HistoryModel.query.filter(
            HistoryModel.run_id == run_id
        ).first()
    
    def get_stats(
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
        StatsModel = self.stats_model
        query = StatsModel.query
        
        if job_code:
            query = query.filter(StatsModel.job_code == job_code)
        
        if start_date:
            query = query.filter(StatsModel.stat_date >= start_date)
        
        if end_date:
            query = query.filter(StatsModel.stat_date <= end_date)
        
        return query.order_by(StatsModel.stat_date.desc()).all()
    
    def cleanup_old_history(self, days: Optional[int] = None) -> int:
        """清理过期的历史记录
        
        Args:
            days: 保留天数，默认使用配置值
        
        Returns:
            清理的记录数
        """
        retention = days or self.retention_days
        if retention <= 0:
            return 0
        
        cutoff_date = datetime.now() - timedelta(days=retention)
        
        HistoryModel = self.history_model
        old_records = HistoryModel.query.filter(
            HistoryModel.start_time < cutoff_date
        ).all()
        
        count = len(old_records)
        for record in old_records:
            record.delete()
        
        if count > 0:
            logger.info(f"Cleaned up {count} old history records")
        
        return count
    
    def cleanup_old_stats(self, days: Optional[int] = None) -> int:
        """清理过期的统计记录
        
        Args:
            days: 保留天数，默认使用配置值
        
        Returns:
            清理的记录数
        """
        retention = days or self.retention_days
        if retention <= 0:
            return 0
        
        cutoff_date = date.today() - timedelta(days=retention)
        
        StatsModel = self.stats_model
        old_records = StatsModel.query.filter(
            StatsModel.stat_date < cutoff_date
        ).all()
        
        count = len(old_records)
        for record in old_records:
            record.delete()
        
        if count > 0:
            logger.info(f"Cleaned up {count} old stats records")
        
        return count
    
    def cleanup_all(self, days: Optional[int] = None) -> Dict[str, int]:
        """清理所有过期记录
        
        Args:
            days: 保留天数，默认使用配置值
        
        Returns:
            清理的记录数字典
        """
        return {
            "history": self.cleanup_old_history(days),
            "stats": self.cleanup_old_stats(days),
        }
    
    def get_dashboard_data(self) -> Dict[str, Any]:
        """获取仪表板数据
        
        Returns:
            仪表板数据字典
        """
        today = date.today()
        yesterday = today - timedelta(days=1)
        week_ago = today - timedelta(days=7)
        
        # 今日统计
        today_stats = self._get_period_stats(today, today)
        
        # 昨日统计
        yesterday_stats = self._get_period_stats(yesterday, yesterday)
        
        # 本周统计
        week_stats = self._get_period_stats(week_ago, today)
        
        # 最近失败的任务
        HistoryModel = self.history_model
        recent_failures = HistoryModel.query.filter(
            HistoryModel.status == "failed"
        ).order_by(
            HistoryModel.start_time.desc()
        ).limit(10).all()
        
        return {
            "today": today_stats,
            "yesterday": yesterday_stats,
            "this_week": week_stats,
            "recent_failures": [
                {
                    "run_id": f.run_id,
                    "job_code": f.job_code,
                    "job_name": f.job_name,
                    "error": f.error,
                    "start_time": f.start_time.isoformat() if f.start_time else None,
                }
                for f in recent_failures
            ],
        }
    
    def _get_period_stats(
        self,
        start_date: date,
        end_date: date,
    ) -> Dict[str, Any]:
        """获取指定时间段的统计"""
        StatsModel = self.stats_model
        stats = StatsModel.query.filter(
            StatsModel.stat_date >= start_date,
            StatsModel.stat_date <= end_date,
            StatsModel.stat_hour == None,  # 只取天级统计
        ).all()
        
        total_runs = sum(s.total_runs for s in stats)
        success_runs = sum(s.success_runs for s in stats)
        failed_runs = sum(s.failed_runs for s in stats)
        
        return {
            "total_runs": total_runs,
            "success_runs": success_runs,
            "failed_runs": failed_runs,
            "success_rate": round(success_runs / total_runs * 100, 2) if total_runs > 0 else 0,
        }
    
    def _update_job_stats(
        self,
        job_id: str,
        job_code: str,
        status: str,
        duration_ms: int,
    ):
        """更新任务统计
        
        Args:
            job_id: 任务ID
            job_code: 任务编码
            status: 执行状态
            duration_ms: 执行耗时
        """
        try:
            today = date.today()
            current_hour = datetime.now().hour
            
            # 更新天级统计
            self._update_stats_record(job_id, job_code, today, None, status, duration_ms)
            
            # 更新小时级统计
            self._update_stats_record(job_id, job_code, today, current_hour, status, duration_ms)
            
        except Exception as e:
            logger.error(f"Failed to update job stats: {e}")
    
    def _update_stats_record(
        self,
        job_id: str,
        job_code: str,
        stat_date: date,
        stat_hour: Optional[int],
        status: str,
        duration_ms: int,
    ):
        """更新或创建统计记录"""
        StatsModel = self.stats_model
        
        # 查找现有记录
        query = StatsModel.query.filter(
            StatsModel.job_code == job_code,
            StatsModel.stat_date == stat_date
        )
        
        if stat_hour is not None:
            query = query.filter(StatsModel.stat_hour == stat_hour)
        else:
            query = query.filter(StatsModel.stat_hour == None)
        
        stats = query.first()
        
        if stats is None:
            # 创建新记录
            stats = StatsModel(
                job_id=job_id,
                job_code=job_code,
                stat_date=stat_date,
                stat_hour=stat_hour,
                total_runs=0,
                success_runs=0,
                failed_runs=0,
                timeout_runs=0,
                retry_runs=0,
                min_duration=None,
                max_duration=None,
                avg_duration=None,
                total_duration=0,
            )
        
        # 更新计数
        stats.total_runs += 1
        
        if status == "success":
            stats.success_runs += 1
        elif status == "failed":
            stats.failed_runs += 1
        elif status == "timeout":
            stats.timeout_runs += 1
        
        # 更新耗时统计
        stats.total_duration += duration_ms
        
        if stats.min_duration is None or duration_ms < stats.min_duration:
            stats.min_duration = duration_ms
        
        if stats.max_duration is None or duration_ms > stats.max_duration:
            stats.max_duration = duration_ms
        
        stats.avg_duration = stats.total_duration // stats.total_runs
        
        stats.save(commit=True)
