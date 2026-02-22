"""调度器核心测试

测试 Scheduler 类的核心功能。
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from yweb.scheduler import Scheduler, JobContext, cron, interval, once
from yweb.scheduler.events import JobExecutedEvent, JobErrorEvent
from yweb.config import SchedulerSettings


class TestSchedulerInit:
    """调度器初始化测试"""
    
    def test_default_init(self):
        """测试默认初始化"""
        scheduler = Scheduler()
        
        assert isinstance(scheduler.settings, SchedulerSettings)
        assert scheduler.settings.enabled == True
        assert scheduler.settings.timezone == "Asia/Shanghai"
        assert scheduler._running == False
    
    def test_init_with_settings(self):
        """测试带配置初始化"""
        settings = SchedulerSettings(
            enabled=True,
            timezone="UTC",
            max_workers=20,
        )
        scheduler = Scheduler(settings=settings)
        
        assert scheduler.settings.timezone == "UTC"
        assert scheduler.settings.max_workers == 20
    
    def test_init_with_kwargs(self):
        """测试关键字参数覆盖"""
        scheduler = Scheduler(timezone="UTC", enabled=False)
        
        assert scheduler.settings.timezone == "UTC"
        assert scheduler.settings.enabled == False
    
    def test_init_disabled(self):
        """测试禁用调度器"""
        scheduler = Scheduler(enabled=False)
        
        assert scheduler.settings.enabled == False


class TestSchedulerDecorators:
    """装饰器测试"""
    
    def test_cron_decorator(self):
        """测试 cron 装饰器"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="DAILY_REPORT", name="每日报表")
        async def daily_report():
            pass
        
        assert "DAILY_REPORT" in scheduler._jobs
        job_info = scheduler._jobs["DAILY_REPORT"]
        assert job_info["name"] == "每日报表"
    
    def test_cron_decorator_default_code(self):
        """测试 cron 装饰器默认 code"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *")
        async def my_task():
            pass
        
        # 默认使用函数名作为 code
        assert "my_task" in scheduler._jobs
    
    def test_interval_decorator(self):
        """测试 interval 装饰器"""
        scheduler = Scheduler()
        
        @scheduler.interval(minutes=30, code="SYNC_DATA", name="数据同步")
        async def sync_data():
            pass
        
        assert "SYNC_DATA" in scheduler._jobs
        job_info = scheduler._jobs["SYNC_DATA"]
        assert job_info["name"] == "数据同步"
    
    def test_once_decorator(self):
        """测试 once 装饰器"""
        scheduler = Scheduler()
        future = datetime.now() + timedelta(hours=1)
        
        @scheduler.once(future, code="ONE_TIME_TASK", name="一次性任务")
        async def one_time_task():
            pass
        
        assert "ONE_TIME_TASK" in scheduler._jobs
    
    def test_decorator_with_description(self):
        """测试装饰器带描述"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="REPORT", description="每天早上生成报表")
        async def report():
            pass
        
        job_info = scheduler._jobs["REPORT"]
        assert job_info["description"] == "每天早上生成报表"
    
    def test_decorator_with_retry(self):
        """测试装饰器带重试配置"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="RETRY_TASK", max_retries=3, retry_delay=60)
        async def retry_task():
            pass
        
        job_info = scheduler._jobs["RETRY_TASK"]
        assert job_info["max_retries"] == 3
        assert job_info["retry_delay"] == 60
    
    def test_decorator_with_concurrent(self):
        """测试装饰器并发配置"""
        scheduler = Scheduler()
        
        @scheduler.interval(seconds=10, code="NO_CONCURRENT", concurrent=False)
        async def no_concurrent_task():
            pass
        
        job_info = scheduler._jobs["NO_CONCURRENT"]
        assert job_info["concurrent"] == False


class TestSchedulerJobManagement:
    """任务管理测试"""
    
    def test_add_job(self):
        """测试添加任务"""
        scheduler = Scheduler()
        
        async def my_task():
            pass
        
        code = scheduler.add_job(
            func=my_task,
            trigger=cron("0 8 * * *"),
            code="DYNAMIC_TASK",
            name="动态任务",
        )
        
        assert code == "DYNAMIC_TASK"
        assert "DYNAMIC_TASK" in scheduler._jobs
    
    def test_add_job_default_code(self):
        """测试添加任务默认 code"""
        scheduler = Scheduler()
        
        async def another_task():
            pass
        
        code = scheduler.add_job(
            func=another_task,
            trigger=interval(minutes=5),
        )
        
        assert code == "another_task"
    
    def test_add_job_duplicate_error(self):
        """测试重复添加任务报错"""
        scheduler = Scheduler()
        
        async def task1():
            pass
        
        async def task2():
            pass
        
        scheduler.add_job(func=task1, trigger=cron("0 8 * * *"), code="SAME_CODE")
        
        with pytest.raises(ValueError) as exc_info:
            scheduler.add_job(func=task2, trigger=cron("0 9 * * *"), code="SAME_CODE")
        
        assert "already exists" in str(exc_info.value)
    
    def test_add_job_replace_existing(self):
        """测试替换已存在的任务"""
        scheduler = Scheduler()
        
        async def task1():
            pass
        
        async def task2():
            pass
        
        scheduler.add_job(func=task1, trigger=cron("0 8 * * *"), code="REPLACE_TASK")
        scheduler.add_job(
            func=task2, 
            trigger=cron("0 9 * * *"), 
            code="REPLACE_TASK",
            replace_existing=True
        )
        
        # 应该是 task2
        assert scheduler._jobs["REPLACE_TASK"]["func"] is task2
    
    def test_remove_job(self):
        """测试删除任务"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="TO_REMOVE")
        async def to_remove():
            pass
        
        assert "TO_REMOVE" in scheduler._jobs
        
        result = scheduler.remove_job("TO_REMOVE")
        
        assert result == True
        assert "TO_REMOVE" not in scheduler._jobs
    
    def test_remove_nonexistent_job(self):
        """测试删除不存在的任务"""
        scheduler = Scheduler()
        
        result = scheduler.remove_job("NOT_EXIST")
        
        assert result == False
    
    def test_pause_resume_job(self):
        """测试暂停/恢复任务"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="PAUSABLE")
        async def pausable():
            pass
        
        # 暂停
        result = scheduler.pause_job("PAUSABLE")
        assert result == True
        assert scheduler._jobs["PAUSABLE"]["is_paused"] == True
        
        # 恢复
        result = scheduler.resume_job("PAUSABLE")
        assert result == True
        assert scheduler._jobs["PAUSABLE"]["is_paused"] == False
    
    def test_get_job(self):
        """测试获取任务信息"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="GET_JOB_TEST", name="测试任务")
        async def test_job():
            pass
        
        job_info = scheduler.get_job("GET_JOB_TEST")
        
        assert isinstance(job_info, dict)
        assert job_info["code"] == "GET_JOB_TEST"
        assert job_info["name"] == "测试任务"
    
    def test_get_nonexistent_job(self):
        """测试获取不存在的任务"""
        scheduler = Scheduler()
        
        job_info = scheduler.get_job("NOT_EXIST")
        
        assert job_info is None
    
    def test_get_jobs(self):
        """测试获取所有任务"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="JOB1")
        async def job1():
            pass
        
        @scheduler.interval(minutes=5, code="JOB2")
        async def job2():
            pass
        
        jobs = scheduler.get_jobs()
        
        assert len(jobs) == 2
        codes = [j["code"] for j in jobs]
        assert "JOB1" in codes
        assert "JOB2" in codes


class TestSchedulerEventListeners:
    """事件监听器测试"""
    
    @pytest.mark.asyncio
    async def test_on_job_executed_decorator(self):
        """测试执行成功监听器"""
        scheduler = Scheduler()
        listener_called = []
        
        @scheduler.on_job_executed
        def on_success(event):
            listener_called.append(event)
        
        probe_event = {"type": "executed", "id": "evt_1"}
        await scheduler._emit_event("job_executed", probe_event)

        assert listener_called == [probe_event]
    
    @pytest.mark.asyncio
    async def test_on_job_error_decorator(self):
        """测试执行失败监听器"""
        scheduler = Scheduler()
        listener_called = []
        
        @scheduler.on_job_error
        async def on_error(event):
            listener_called.append(event)
        
        probe_event = {"type": "error", "id": "evt_2"}
        await scheduler._emit_event("job_error", probe_event)

        assert listener_called == [probe_event]
    
    @pytest.mark.asyncio
    async def test_on_job_retry_decorator(self):
        """测试重试监听器"""
        scheduler = Scheduler()
        listener_called = []
        
        @scheduler.on_job_retry
        def on_retry(event):
            listener_called.append(event)
        
        probe_event = {"type": "retry", "id": "evt_3"}
        await scheduler._emit_event("job_retry", probe_event)

        assert listener_called == [probe_event]
    
    @pytest.mark.asyncio
    async def test_on_job_missed_decorator(self):
        """测试错过执行监听器"""
        scheduler = Scheduler()
        listener_called = []
        
        @scheduler.on_job_missed
        def on_missed(event):
            listener_called.append(event)
        
        probe_event = {"type": "missed", "id": "evt_4"}
        await scheduler._emit_event("job_missed", probe_event)

        assert listener_called == [probe_event]
    
    @pytest.mark.asyncio
    async def test_multiple_listeners(self):
        """测试多个监听器"""
        scheduler = Scheduler()
        called_order = []
        
        @scheduler.on_job_executed
        def listener1(event):
            called_order.append(("l1", event))
        
        @scheduler.on_job_executed
        def listener2(event):
            called_order.append(("l2", event))
        
        probe_event = {"type": "executed", "id": "evt_5"}
        await scheduler._emit_event("job_executed", probe_event)

        assert called_order == [("l1", probe_event), ("l2", probe_event)]


class TestSchedulerStats:
    """调度器统计测试"""
    
    def test_get_stats_empty(self):
        """测试空调度器统计"""
        scheduler = Scheduler()
        
        stats = scheduler.get_stats()
        
        assert stats["total_jobs"] == 0
        assert stats["active_jobs"] == 0
        assert stats["paused_jobs"] == 0
        assert stats["total_runs"] == 0
        assert stats["is_running"] == False
    
    def test_get_stats_with_jobs(self):
        """测试有任务的统计"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="JOB1")
        async def job1():
            pass
        
        @scheduler.interval(minutes=5, code="JOB2")
        async def job2():
            pass
        
        # 模拟暂停一个任务
        scheduler.pause_job("JOB2")
        
        stats = scheduler.get_stats()
        
        assert stats["total_jobs"] == 2
        assert stats["active_jobs"] == 1
        assert stats["paused_jobs"] == 1


class TestSchedulerLifecycle:
    """调度器生命周期测试"""
    
    def test_start_disabled_scheduler(self):
        """测试启动禁用的调度器"""
        scheduler = Scheduler(enabled=False)
        
        @scheduler.cron("0 8 * * *", code="TEST")
        async def test_job():
            pass
        
        scheduler.start()
        
        # 禁用时不应该运行
        assert scheduler._running == False
    
    def test_scheduler_init_state(self):
        """测试初始化状态"""
        scheduler = Scheduler()
        
        assert scheduler._running == False
        assert hasattr(scheduler._scheduler, "add_job")


class TestSchedulerExecution:
    """任务执行测试"""
    
    @pytest.mark.asyncio
    async def test_execute_job_no_context(self):
        """测试执行无参数任务"""
        scheduler = Scheduler()
        executed = []
        
        @scheduler.cron("0 8 * * *", code="NO_CONTEXT")
        async def no_context_job():
            executed.append(True)
        
        # 获取任务信息并手动执行
        job_info = scheduler._jobs["NO_CONTEXT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="NO_CONTEXT",
            job_name="no_context_job",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(executed) == 1
    
    @pytest.mark.asyncio
    async def test_execute_job_with_context(self):
        """测试执行带上下文参数任务"""
        scheduler = Scheduler()
        received_context = []
        
        @scheduler.cron("0 8 * * *", code="WITH_CONTEXT")
        async def with_context_job(ctx: JobContext):
            received_context.append(ctx)
        
        job_info = scheduler._jobs["WITH_CONTEXT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="WITH_CONTEXT",
            job_name="with_context_job",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(received_context) == 1
        assert received_context[0].job_code == "WITH_CONTEXT"
    
    @pytest.mark.asyncio
    async def test_execute_job_success_event(self):
        """测试执行成功触发事件"""
        scheduler = Scheduler()
        events = []
        
        @scheduler.on_job_executed
        async def on_success(event):
            events.append(event)
        
        @scheduler.cron("0 8 * * *", code="SUCCESS_EVENT")
        async def success_job():
            return "ok"
        
        job_info = scheduler._jobs["SUCCESS_EVENT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="SUCCESS_EVENT",
            job_name="success_job",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(events) == 1
        assert isinstance(events[0], JobExecutedEvent)
        assert events[0].job_code == "SUCCESS_EVENT"
    
    @pytest.mark.asyncio
    async def test_execute_job_error_event(self):
        """测试执行失败触发事件"""
        scheduler = Scheduler()
        events = []
        
        @scheduler.on_job_error
        async def on_error(event):
            events.append(event)
        
        @scheduler.cron("0 8 * * *", code="ERROR_EVENT")
        async def error_job():
            raise ValueError("Test error")
        
        job_info = scheduler._jobs["ERROR_EVENT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="ERROR_EVENT",
            job_name="error_job",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(events) == 1
        assert isinstance(events[0], JobErrorEvent)
        assert "Test error" in events[0].error
    
    @pytest.mark.asyncio
    async def test_execute_sync_function(self):
        """测试执行同步函数"""
        scheduler = Scheduler()
        executed = []
        
        @scheduler.cron("0 8 * * *", code="SYNC_JOB")
        def sync_job():  # 注意：不是 async
            executed.append(True)
        
        job_info = scheduler._jobs["SYNC_JOB"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="SYNC_JOB",
            job_name="sync_job",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(executed) == 1


class TestSchedulerRunId:
    """run_id 生成测试"""
    
    def test_generate_run_id_format(self):
        """测试 run_id 格式"""
        from yweb.scheduler.scheduler import generate_run_id
        
        run_id = generate_run_id()
        
        assert run_id.startswith("run_")
        parts = run_id.split("_")
        assert len(parts) == 4  # run, date, time, random
    
    def test_generate_run_id_unique(self):
        """测试 run_id 唯一性"""
        from yweb.scheduler.scheduler import generate_run_id
        
        ids = [generate_run_id() for _ in range(100)]
        
        # 所有 ID 应该唯一
        assert len(ids) == len(set(ids))
