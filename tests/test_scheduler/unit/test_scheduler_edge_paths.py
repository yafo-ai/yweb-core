"""Scheduler 边界分支补充测试"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.scheduler import JobContext, Scheduler, cron, interval
from yweb.scheduler.job import Job
from yweb.config import SchedulerSettings


class TestSchedulerApiEdgePaths:
    """覆盖 scheduler.py 中较少触达的 API 分支"""

    def test_job_decorator_requires_trigger_or_triggers(self):
        """测试 job 装饰器必须提供触发器"""
        scheduler = Scheduler()

        with pytest.raises(ValueError, match="Must provide either 'trigger' or 'triggers'"):
            @scheduler.job(code="NO_TRIGGER")
            async def no_trigger_job():
                return None

    def test_scheduler_operation_returns_false_when_apscheduler_errors(self):
        """测试 pause/resume/remove/reschedule 在 APScheduler 异常时返回 False"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="EDGE_JOB")
        async def edge_job():
            return None

        scheduler._running = True
        scheduler._scheduler = Mock()
        scheduler._scheduler.pause_job.side_effect = RuntimeError("pause failed")
        scheduler._scheduler.resume_job.side_effect = RuntimeError("resume failed")
        scheduler._scheduler.remove_job.side_effect = RuntimeError("remove failed")
        scheduler._scheduler.reschedule_job.side_effect = RuntimeError("reschedule failed")

        assert scheduler.pause_job("EDGE_JOB") is False
        assert scheduler.resume_job("EDGE_JOB") is False
        assert scheduler.remove_job("EDGE_JOB") is True  # remove 先 pop，本地删除成功

        @scheduler.cron("0 9 * * *", code="EDGE_JOB_2")
        async def edge_job2():
            return None

        assert scheduler.reschedule_job("EDGE_JOB_2", interval(minutes=5)) is False

    def test_get_job_swallow_apscheduler_error(self):
        """测试 get_job 在获取 next_run_time 失败时仍返回任务信息"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="GET_JOB_EDGE")
        async def get_job_edge():
            return None

        scheduler._running = True
        scheduler._scheduler = Mock()
        scheduler._scheduler.get_job.side_effect = RuntimeError("boom")

        info = scheduler.get_job("GET_JOB_EDGE")
        assert isinstance(info, dict)
        assert info["code"] == "GET_JOB_EDGE"

    def test_register_job_calls_add_to_apscheduler_when_running(self):
        """测试运行中注册任务会立即加入 APScheduler"""
        scheduler = Scheduler()
        scheduler._running = True

        with patch.object(scheduler, "_add_to_apscheduler") as mock_add:
            @scheduler.cron("0 8 * * *", code="RUNNING_ADD")
            async def running_add():
                return None

        assert "RUNNING_ADD" in scheduler._jobs
        mock_add.assert_called_once()


class TestSchedulerMultiTriggerAndJobClassPaths:
    """覆盖多触发器和 Job 类相关分支"""

    def test_decorator_stacking_converts_and_extends_multi_trigger_job(self):
        """测试同一函数多次装饰会自动扩展为多触发器任务"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="STACKED")
        @scheduler.cron("0 9 * * *", code="STACKED")
        @scheduler.cron("0 10 * * *", code="STACKED")
        async def stacked_job():
            return None

        job_info = scheduler._jobs["STACKED"]
        assert job_info["is_multi_trigger"] is True
        assert len(job_info["triggers"]) == 3
        assert "STACKED#2" in job_info["sub_job_ids"]

    def test_add_job_class_rejects_non_job_subclass(self):
        """测试 add_job_class 会拒绝非 Job 子类"""
        scheduler = Scheduler()

        class NotAJob:
            pass

        with pytest.raises(TypeError, match="must be a subclass of Job"):
            scheduler.add_job_class(NotAJob)

    def test_add_job_class_raises_when_no_triggers(self):
        """测试 add_job_class 在 get_triggers 为空时抛错"""
        scheduler = Scheduler()

        class TriggerlessJob(Job):
            code = "TRIGGERLESS_JOB"
            trigger = cron("0 8 * * *")

            async def execute(self, context):
                return context.run_id

            def get_triggers(self):
                return []

        with pytest.raises(ValueError, match="must define at least one trigger"):
            scheduler.add_job_class(TriggerlessJob)

    @pytest.mark.asyncio
    async def test_create_job_executor_calls_on_error_then_reraises(self):
        """测试 Job 执行器异常时调用 on_error 并继续抛错"""
        scheduler = Scheduler()

        class BrokenJob(Job):
            code = "BROKEN_JOB"
            trigger = cron("0 8 * * *")

            def __init__(self):
                super().__init__()
                self.error_called = False

            async def execute(self, _context):
                raise RuntimeError("job failed")

            async def on_error(self, _context, _error):
                self.error_called = True

        job_instance = BrokenJob()
        executor = scheduler._create_job_executor(job_instance)
        context = JobContext(
            job_id="j1",
            job_code="BROKEN_JOB",
            job_name="BrokenJob",
            run_id="run_1",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )

        with pytest.raises(RuntimeError, match="job failed"):
            await executor(context)
        assert job_instance.error_called is True

    def test_add_job_from_builder_requires_func_or_job_class(self):
        """测试 add_job_from_builder 必须提供 func 或 job_class"""
        scheduler = Scheduler()
        bad_config = SimpleNamespace(job_class=None, func=None)

        with pytest.raises(ValueError, match="either func or job_class"):
            scheduler.add_job_from_builder(bad_config)


class TestSchedulerStatsAndMissedEventPaths:
    """覆盖 get_job_stats 与 missed 事件分支"""

    def test_on_job_missed_emits_event_for_matched_job(self):
        """测试 APScheduler missed 回调会发出业务事件"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="MISSED_JOB")
        async def missed_job():
            return None

        fake_event = SimpleNamespace(
            job_id=scheduler._jobs["MISSED_JOB"]["apscheduler_id"],
            scheduled_run_time=datetime.now(),
        )

        def create_task_and_close(coro):
            coro.close()
            return Mock()

        with patch("yweb.scheduler.scheduler.asyncio.create_task", side_effect=create_task_and_close) as mock_create_task:
            scheduler._on_job_missed(fake_event)

        mock_create_task.assert_called_once()

    def test_get_job_stats_not_found_and_history_failure(self):
        """测试 get_job_stats 的不存在分支与历史查询异常分支"""
        scheduler = Scheduler()
        assert scheduler.get_job_stats("NOT_EXIST") is None

        @scheduler.cron("0 8 * * *", code="STATS_JOB")
        async def stats_job():
            return None

        scheduler._running = True
        scheduler._scheduler = Mock()
        scheduler._scheduler.get_job.return_value = SimpleNamespace(next_run_time="next_time")
        scheduler._jobs["STATS_JOB"]["run_count"] = 4
        scheduler._jobs["STATS_JOB"]["success_count"] = 3
        scheduler._jobs["STATS_JOB"]["fail_count"] = 1

        with patch.object(scheduler, "_get_history_manager", side_effect=RuntimeError("db down")):
            stats = scheduler.get_job_stats("STATS_JOB")

        assert stats["next_run_time"] == "next_time"
        assert stats["success_rate"] == 75.0
        assert stats["avg_duration_ms"] is None


class TestSchedulerDelegationAndLifecyclePaths:
    """覆盖委托查询与生命周期边界分支"""

    def test_history_query_methods_delegate_to_history_manager(self):
        """测试执行历史查询方法正确委托到 history manager"""
        scheduler = Scheduler()
        history_manager = Mock()
        history_manager.get_executions.return_value = ["e1"]
        history_manager.count_executions.return_value = 9
        history_manager.get_execution.return_value = {"run_id": "run_x"}
        history_manager.get_stats.return_value = [{"job_code": "J"}]

        with patch.object(scheduler, "_get_history_manager", return_value=history_manager):
            executions = scheduler.get_executions(job_code="A", status="success", limit=5, offset=1)
            count = scheduler.count_executions(job_code="A")
            execution = scheduler.get_execution("run_x")
            stats = scheduler.get_execution_stats(job_code="A")

        assert executions == ["e1"]
        assert count == 9
        assert execution == {"run_id": "run_x"}
        assert stats == [{"job_code": "J"}]
        history_manager.get_executions.assert_called_once()
        history_manager.count_executions.assert_called_once()
        history_manager.get_execution.assert_called_once_with("run_x")
        history_manager.get_stats.assert_called_once()

    def test_start_returns_when_already_running(self):
        """测试调度器已运行时 start 直接返回"""
        scheduler = Scheduler()
        scheduler._running = True
        scheduler._scheduler = Mock()

        scheduler.start()

        scheduler._scheduler.start.assert_not_called()

    def test_shutdown_returns_when_not_running(self):
        """测试调度器未运行时 shutdown 直接返回"""
        scheduler = Scheduler()
        scheduler._running = False
        scheduler._scheduler = Mock()

        scheduler.shutdown(wait=False)

        scheduler._scheduler.shutdown.assert_not_called()

    def test_start_only_adds_non_paused_jobs(self):
        """测试 start 时仅加载未暂停任务到 APScheduler"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="ACTIVE_JOB")
        async def active_job():
            return None

        @scheduler.cron("0 9 * * *", code="PAUSED_JOB")
        async def paused_job():
            return None

        scheduler._jobs["PAUSED_JOB"]["is_paused"] = True
        scheduler._scheduler = Mock()

        with patch.object(scheduler, "_add_to_apscheduler") as mock_add:
            scheduler.start()

        called_codes = {call.args[0]["code"] for call in mock_add.call_args_list}
        assert "ACTIVE_JOB" in called_codes
        assert "PAUSED_JOB" not in called_codes
        assert scheduler._running is True
        scheduler._scheduler.start.assert_called_once()


class TestSchedulerRetrySchedulePaths:
    """覆盖 _schedule_retry 关键分支"""

    @pytest.mark.asyncio
    async def test_schedule_retry_uses_strategy_delay(self):
        """测试存在 retry_strategy 时使用策略延迟"""
        scheduler = Scheduler()
        strategy = Mock()
        strategy.get_delay.return_value = 7

        job_info = {
            "id": "job_id",
            "code": "RETRY_JOB",
            "name": "Retry Job",
            "retry_strategy": strategy,
            "max_retries": 3,
            "run_count": 2,
        }
        context = JobContext(
            job_id="job_id",
            job_code="RETRY_JOB",
            job_name="Retry Job",
            run_id="run_1",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
            attempt=1,
        )

        scheduler._emit_event = AsyncMock()
        scheduler._execute_job = AsyncMock()

        with patch("yweb.scheduler.scheduler.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await scheduler._schedule_retry(job_info, context, "failed", RuntimeError("x"))

        strategy.get_delay.assert_called_once_with(2)
        mock_sleep.assert_awaited_once_with(7)
        scheduler._emit_event.assert_awaited_once()
        scheduler._execute_job.assert_awaited_once()
        retried_context = scheduler._execute_job.await_args.args[1]
        assert retried_context.attempt == 2
        assert retried_context.trigger_type == "retry"
        assert retried_context.retry_of == "run_1"

    @pytest.mark.asyncio
    async def test_schedule_retry_uses_default_retry_delay_without_strategy(self):
        """测试无 retry_strategy 时使用 retry_delay"""
        scheduler = Scheduler()
        job_info = {
            "id": "job_id",
            "code": "RETRY_JOB",
            "name": "Retry Job",
            "retry_strategy": None,
            "retry_delay": 0,
            "max_retries": 2,
            "run_count": 1,
        }
        context = JobContext(
            job_id="job_id",
            job_code="RETRY_JOB",
            job_name="Retry Job",
            run_id="run_1",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
            attempt=1,
        )

        scheduler._emit_event = AsyncMock()
        scheduler._execute_job = AsyncMock()

        with patch("yweb.scheduler.scheduler.asyncio.sleep", new=AsyncMock()) as mock_sleep:
            await scheduler._schedule_retry(job_info, context, "failed", RuntimeError("x"))

        mock_sleep.assert_awaited_once_with(0)
        scheduler._execute_job.assert_awaited_once()

    def test_on_job_executed_and_error_callbacks_are_noop(self):
        """测试 APScheduler 成功/失败回调是空实现"""
        scheduler = Scheduler()
        fake_event = Mock()

        # 仅验证不会抛异常
        scheduler._on_job_executed(fake_event)
        scheduler._on_job_error(fake_event)

    def test_get_job_stats_next_run_time_none_when_scheduler_get_job_raises(self):
        """测试 get_job_stats 中获取 next_run_time 异常会被吞掉"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="STAT_EDGE")
        async def stat_edge():
            return None

        scheduler._running = True
        scheduler._scheduler = Mock()
        scheduler._scheduler.get_job.side_effect = RuntimeError("boom")
        scheduler._jobs["STAT_EDGE"]["run_count"] = 2
        scheduler._jobs["STAT_EDGE"]["success_count"] = 1
        scheduler._jobs["STAT_EDGE"]["fail_count"] = 1

        history_manager = Mock()
        history_manager.get_stats.return_value = []
        with patch.object(scheduler, "_get_history_manager", return_value=history_manager):
            stats = scheduler.get_job_stats("STAT_EDGE")

        assert stats["next_run_time"] is None
        assert stats["success_rate"] == 50.0


class TestSchedulerInternalAndInitPaths:
    """覆盖调度器初始化与内部边界分支"""

    def test_init_apscheduler_uses_orm_store_when_configured(self):
        """测试 store=orm 时会构建 ORMJobStore"""
        fake_orm_store = Mock(name="orm_store")
        fake_scheduler_instance = Mock(name="apscheduler")

        with patch("yweb.scheduler.stores.ORMJobStore", return_value=fake_orm_store) as mock_store, \
             patch("yweb.scheduler.scheduler.AsyncIOScheduler", return_value=fake_scheduler_instance) as mock_scheduler:
            scheduler = Scheduler(settings=SchedulerSettings(store="orm"))

        assert scheduler._scheduler is fake_scheduler_instance
        mock_store.assert_called_once()
        kwargs = mock_scheduler.call_args.kwargs
        assert kwargs["jobstores"]["default"] is fake_orm_store

    def test_run_job_returns_run_id_when_no_running_loop(self):
        """测试无事件循环时 run_job 返回 run_id 且不抛错"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="NO_LOOP_JOB")
        async def no_loop_job():
            return None

        with patch("yweb.scheduler.scheduler.asyncio.get_running_loop", side_effect=RuntimeError):
            run_id = scheduler.run_job("NO_LOOP_JOB")

        assert isinstance(run_id, str)
        assert run_id.startswith("run_")

    @pytest.mark.asyncio
    async def test_execute_job_release_lock_warning_path(self):
        """测试释放分布式锁异常时走 warning 分支"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="LOCK_WARN_JOB", concurrent=False)
        async def lock_warn_job():
            return "ok"

        job_info = scheduler._jobs["LOCK_WARN_JOB"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="LOCK_WARN_JOB",
            job_name="lock_warn_job",
            run_id="run_lock_warn",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )

        fake_history = Mock()
        fake_lock = AsyncMock()
        fake_lock.acquire = AsyncMock(return_value=True)
        fake_lock.release = AsyncMock(side_effect=RuntimeError("release failed"))

        scheduler._distributed_lock = fake_lock
        with patch.object(scheduler, "_get_history_manager", return_value=fake_history):
            await scheduler._execute_job(job_info, context)

        fake_lock.acquire.assert_awaited_once()
        fake_lock.release.assert_awaited_once()
        fake_history.record_start.assert_called_once()
        fake_history.record_success.assert_called_once()

    @pytest.mark.asyncio
    async def test_invoke_job_func_sync_and_no_context_branches(self):
        """测试 _invoke_job_func 的同步和无参数分支"""
        scheduler = Scheduler()

        def sync_with_context(ctx):
            return ctx.job_code

        def sync_without_context():
            return "no_ctx"

        context = JobContext(job_id="j", job_code="SYNC_CTX", job_name="n")

        result1 = await scheduler._invoke_job_func(sync_with_context, context, timeout=None)
        result2 = await scheduler._invoke_job_func(sync_without_context, context, timeout=None)

        assert result1 == "SYNC_CTX"
        assert result2 == "no_ctx"

    def test_on_job_missed_no_matching_job_does_not_create_task(self):
        """测试 missed 事件未匹配到任务时不创建异步任务"""
        scheduler = Scheduler()
        fake_event = SimpleNamespace(job_id="not_exists", scheduled_run_time=datetime.now())

        with patch("yweb.scheduler.scheduler.asyncio.create_task") as mock_create_task:
            scheduler._on_job_missed(fake_event)

        mock_create_task.assert_not_called()

    def test_get_job_stats_calculates_avg_duration(self):
        """测试 get_job_stats 会基于历史统计计算平均耗时"""
        scheduler = Scheduler()

        @scheduler.cron("0 8 * * *", code="AVG_JOB")
        async def avg_job():
            return None

        scheduler._jobs["AVG_JOB"]["run_count"] = 5
        scheduler._jobs["AVG_JOB"]["success_count"] = 4
        scheduler._jobs["AVG_JOB"]["fail_count"] = 1

        record1 = SimpleNamespace(total_duration=300, total_runs=2)
        record2 = SimpleNamespace(total_duration=900, total_runs=3)
        fake_history = Mock()
        fake_history.get_stats.return_value = [record1, record2]

        with patch.object(scheduler, "_get_history_manager", return_value=fake_history):
            stats = scheduler.get_job_stats("AVG_JOB")

        assert stats["avg_duration_ms"] == 240
        assert stats["success_rate"] == 80.0

    def test_init_app_disabled_scheduler_does_not_call_start(self):
        """测试 init_app 在 disabled 配置下不会启动调度器"""
        app = FastAPI()
        scheduler = Scheduler(enabled=False)

        with patch.object(scheduler, "start") as mock_start:
            scheduler.init_app(app)
            with TestClient(app):
                pass

        mock_start.assert_not_called()

    def test_init_app_shutdown_calls_shutdown_after_startup_when_enabled(self):
        """测试 init_app 在启用场景会在 shutdown 阶段调用 shutdown()"""
        app = FastAPI()
        scheduler = Scheduler()

        with patch.object(scheduler, "shutdown") as mock_shutdown:
            scheduler.init_app(app)
            with TestClient(app):
                pass

        mock_shutdown.assert_called_once_with(wait=True)

