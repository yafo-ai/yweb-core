"""执行历史测试

测试执行历史记录和查询功能。
"""

import pytest
from datetime import datetime, date, timedelta
from unittest.mock import Mock, patch, MagicMock

from yweb.scheduler.history import HistoryManager
from yweb.scheduler.context import JobContext
from yweb.scheduler import create_scheduler_models


# 获取测试用的模型
def get_test_models():
    """获取测试用的 scheduler 模型"""
    from tests.test_scheduler.conftest import get_scheduler_models
    return get_scheduler_models()


class TestHistoryManagerBasic:
    """HistoryManager 基础测试"""
    
    def test_init_enabled(self):
        """测试启用历史记录"""
        manager = HistoryManager(enabled=True, retention_days=30)
        
        assert manager.enabled == True
        assert manager.retention_days == 30
    
    def test_init_disabled(self):
        """测试禁用历史记录"""
        manager = HistoryManager(enabled=False)
        
        assert manager.enabled == False
    
    def test_record_start_disabled(self):
        """测试禁用时不记录"""
        manager = HistoryManager(enabled=False)
        
        context = JobContext(
            job_id="test",
            job_code="TEST",
            job_name="Test",
            run_id="run_001",
        )
        
        result = manager.record_start(context)
        
        assert result is None
    
    def test_record_success_disabled(self):
        """测试禁用时不记录成功"""
        manager = HistoryManager(enabled=False)
        
        context = JobContext(
            job_id="test",
            job_code="TEST",
            job_name="Test",
            run_id="run_001",
        )
        
        result = manager.record_success(context, "ok", 100)
        
        assert result is None
    
    def test_record_failure_disabled(self):
        """测试禁用时不记录失败"""
        manager = HistoryManager(enabled=False)
        
        context = JobContext(
            job_id="test",
            job_code="TEST",
            job_name="Test",
            run_id="run_001",
        )
        
        result = manager.record_failure(context, "error", "traceback", 100)
        
        assert result is None


class TestSchedulerHistoryIntegration:
    """Scheduler 执行历史集成测试"""
    
    def test_get_executions_method_exists(self):
        """测试 get_executions 方法存在"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        assert hasattr(scheduler, 'get_executions')
        assert callable(scheduler.get_executions)
    
    def test_get_execution_method_exists(self):
        """测试 get_execution 方法存在"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        assert hasattr(scheduler, 'get_execution')
        assert callable(scheduler.get_execution)
    
    def test_get_execution_stats_method_exists(self):
        """测试 get_execution_stats 方法存在"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        assert hasattr(scheduler, 'get_execution_stats')
        assert callable(scheduler.get_execution_stats)
    
    def test_history_manager_lazy_init(self):
        """测试历史管理器延迟初始化"""
        from yweb.scheduler import Scheduler
        from yweb.scheduler.history import HistoryManager
        
        scheduler = Scheduler()
        
        # 初始时应该是 None
        assert scheduler._history_manager is None
        
        # 获取时才初始化
        manager = scheduler._get_history_manager()
        assert isinstance(manager, HistoryManager)
        assert scheduler._history_manager is manager


class TestSchedulerHistorySettings:
    """Scheduler 历史记录配置测试"""
    
    def test_history_enabled_by_default(self):
        """测试默认启用历史记录"""
        from yweb.scheduler import Scheduler
        from yweb.config import SchedulerSettings
        
        settings = SchedulerSettings()
        assert settings.enable_history == True
    
    def test_history_retention_days(self):
        """测试历史保留天数配置"""
        from yweb.config import SchedulerSettings
        
        settings = SchedulerSettings(history_retention_days=60)
        assert settings.history_retention_days == 60
    
    def test_disable_history(self):
        """测试禁用历史记录"""
        from yweb.scheduler import Scheduler
        from yweb.config import SchedulerSettings
        
        settings = SchedulerSettings(enable_history=False)
        scheduler = Scheduler(settings=settings)
        
        manager = scheduler._get_history_manager()
        assert manager.enabled == False


class TestHistoryManagerWithDatabase:
    """使用内存数据库的历史管理器测试"""
    
    def test_record_start(self, scheduler_db_session, scheduler_models):
        """测试记录任务开始"""
        manager = HistoryManager(
            enabled=True, 
            retention_days=30,
            job_model=scheduler_models.SchedulerJob,
            history_model=scheduler_models.SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        context = JobContext(
            job_id="test_id",
            job_code="TEST_JOB",
            job_name="测试任务",
            run_id="run_001",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            trigger_type="cron",
        )
        
        result = manager.record_start(context)
        
        assert result is not None
        assert result.run_id == "run_001"
        assert result.job_code == "TEST_JOB"
        assert result.status == "running"
    
    def test_record_success(self, scheduler_db_session, scheduler_models):
        """测试记录任务成功"""
        manager = HistoryManager(
            enabled=True, 
            retention_days=30,
            job_model=scheduler_models.SchedulerJob,
            history_model=scheduler_models.SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        context = JobContext(
            job_id="test_id",
            job_code="SUCCESS_JOB",
            job_name="成功任务",
            run_id="run_002",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            trigger_type="interval",
        )
        
        # 先记录开始
        manager.record_start(context)
        
        # 记录成功
        result = manager.record_success(context, result="ok", duration_ms=150)
        
        assert result is not None
        assert result.status == "success"
        assert result.duration_ms == 150
    
    def test_record_failure(self, scheduler_db_session, scheduler_models):
        """测试记录任务失败"""
        manager = HistoryManager(
            enabled=True, 
            retention_days=30,
            job_model=scheduler_models.SchedulerJob,
            history_model=scheduler_models.SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        context = JobContext(
            job_id="test_id",
            job_code="FAIL_JOB",
            job_name="失败任务",
            run_id="run_003",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
            attempt=1,
        )
        
        # 先记录开始
        manager.record_start(context)
        
        # 记录失败
        result = manager.record_failure(
            context, 
            error="Test error", 
            traceback="Traceback...", 
            duration_ms=50
        )
        
        assert result is not None
        assert result.status == "failed"
        assert result.error == "Test error"
    
    def test_get_executions(self, scheduler_db_session, scheduler_models):
        """测试查询执行历史"""
        manager = HistoryManager(
            enabled=True, 
            retention_days=30,
            job_model=scheduler_models.SchedulerJob,
            history_model=scheduler_models.SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        # 创建几条执行记录
        for i in range(3):
            context = JobContext(
                job_id="test_id",
                job_code="QUERY_JOB",
                job_name="查询任务",
                run_id=f"run_{i:03d}",
                scheduled_time=datetime.now(),
                start_time=datetime.now(),
            )
            manager.record_start(context)
            manager.record_success(context, result="ok", duration_ms=100 + i * 10)
        
        # 查询
        executions = manager.get_executions(job_code="QUERY_JOB", limit=10)
        
        assert len(executions) == 3
    
    def test_get_execution_by_run_id(self, scheduler_db_session, scheduler_models):
        """测试按运行ID查询"""
        manager = HistoryManager(
            enabled=True, 
            retention_days=30,
            job_model=scheduler_models.SchedulerJob,
            history_model=scheduler_models.SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        context = JobContext(
            job_id="test_id",
            job_code="SINGLE_JOB",
            job_name="单次任务",
            run_id="unique_run_id",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
        )
        manager.record_start(context)
        manager.record_success(context, result="done", duration_ms=200)
        
        # 查询
        execution = manager.get_execution("unique_run_id")
        
        assert execution is not None
        assert execution.run_id == "unique_run_id"
        assert execution.status == "success"
    
    def test_cleanup_old_history(self, scheduler_db_session, scheduler_models):
        """测试清理旧历史记录"""
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        
        manager = HistoryManager(
            enabled=True, 
            retention_days=7,
            job_model=scheduler_models.SchedulerJob,
            history_model=SchedulerJobHistory,
            stats_model=scheduler_models.SchedulerJobStats,
        )
        
        # 创建一条"旧"记录（直接操作数据库）
        old_record = SchedulerJobHistory(
            job_id="old_job",
            job_code="OLD_JOB",
            run_id="old_run_001",
            status="success",
            scheduled_time=datetime.now() - timedelta(days=10),
            start_time=datetime.now() - timedelta(days=10),
            end_time=datetime.now() - timedelta(days=10),
        )
        old_record.save(commit=True)
        
        # 创建一条"新"记录
        context = JobContext(
            job_id="new_job",
            job_code="NEW_JOB",
            job_name="新任务",
            run_id="new_run_001",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
        )
        manager.record_start(context)
        manager.record_success(context, result="ok", duration_ms=100)
        
        # 清理（保留7天）
        count = manager.cleanup_old_history(days=7)
        
        # 只应清理 1 条旧记录
        assert count == 1
        
        # 新记录应该还在
        new_exec = manager.get_execution("new_run_001")
        assert new_exec is not None
        assert new_exec.status == "success"


class TestSchedulerWithDatabaseHistory:
    """调度器数据库历史集成测试"""
    
    @pytest.mark.asyncio
    async def test_job_execution_records_history(self, scheduler_with_db, scheduler_db_session, scheduler_models):
        """测试任务执行时记录历史"""
        from yweb.scheduler import cron, JobContext
        
        SchedulerJobHistory = scheduler_models.SchedulerJobHistory
        scheduler = scheduler_with_db
        executed = []
        
        @scheduler.cron("0 8 * * *", code="HISTORY_TEST", name="历史测试")
        async def history_test_job(ctx: JobContext):
            executed.append(ctx.run_id)
        
        # 手动执行任务
        job_info = scheduler._jobs["HISTORY_TEST"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="HISTORY_TEST",
            job_name="历史测试",
            run_id="test_run_history",
            scheduled_time=datetime.now(),
            start_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        # 验证任务执行
        assert len(executed) == 1
        
        # 验证历史记录（需要查询数据库）
        history = SchedulerJobHistory.query.filter(
            SchedulerJobHistory.run_id == "test_run_history"
        ).first()
        
        # 历史记录必须落库，不能条件跳过
        assert history is not None
        assert history.job_code == "HISTORY_TEST"
        assert history.status == "success"
