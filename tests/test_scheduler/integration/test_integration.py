"""集成测试

测试调度器与 FastAPI 的集成以及完整使用流程。
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import Mock, AsyncMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.scheduler import Scheduler, JobContext, cron, interval, once
from yweb.config import SchedulerSettings


class TestFastAPIIntegration:
    """FastAPI 集成测试"""
    
    def test_init_app(self):
        """测试 init_app 方法"""
        app = FastAPI()
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="TEST")
        async def test_job():
            pass
        
        scheduler.init_app(app)
        
        # 检查 scheduler 是否挂载到 app.state
        assert hasattr(app.state, "scheduler")
        assert app.state.scheduler is scheduler
    
    def test_init_app_lifecycle_events(self):
        """测试生命周期事件注册并在启动/关闭时执行"""
        app = FastAPI()
        scheduler = Scheduler()

        with patch.object(scheduler, "start") as mock_start, patch.object(
            scheduler, "shutdown"
        ) as mock_shutdown:
            # 启动时将 running 置为 True，确保关闭阶段命中 shutdown 分支
            def _start_side_effect():
                scheduler._running = True

            mock_start.side_effect = _start_side_effect
            scheduler.init_app(app)

            with TestClient(app):
                pass

            assert app.state.scheduler is scheduler
            mock_start.assert_called_once()
            mock_shutdown.assert_called_once_with(wait=True)


class TestCompleteWorkflow:
    """完整工作流测试"""
    
    @pytest.mark.asyncio
    async def test_full_job_lifecycle(self):
        """测试任务完整生命周期"""
        scheduler = Scheduler()
        execution_log = []
        
        # 1. 注册任务
        @scheduler.cron("0 8 * * *", code="LIFECYCLE", name="生命周期测试")
        async def lifecycle_job(ctx: JobContext):
            execution_log.append({
                "run_id": ctx.run_id,
                "attempt": ctx.attempt,
                "time": datetime.now(),
            })
        
        # 2. 注册事件监听器
        events = []
        
        @scheduler.on_job_executed
        async def on_success(event):
            events.append(("success", event))
        
        @scheduler.on_job_error
        async def on_error(event):
            events.append(("error", event))
        
        # 3. 验证任务注册
        assert "LIFECYCLE" in scheduler._jobs
        job_info = scheduler._jobs["LIFECYCLE"]
        assert job_info["name"] == "生命周期测试"
        
        # 4. 手动执行（模拟调度触发）
        context = JobContext(
            job_id=job_info["id"],
            job_code="LIFECYCLE",
            job_name="生命周期测试",
            run_id="run_test_001",
            start_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        # 5. 验证执行
        assert len(execution_log) == 1
        assert execution_log[0]["run_id"] == "run_test_001"
        
        # 6. 验证事件
        assert len(events) == 1
        assert events[0][0] == "success"
    
    @pytest.mark.asyncio
    async def test_job_with_retry(self):
        """测试任务重试"""
        scheduler = Scheduler()
        attempt_count = [0]
        
        @scheduler.cron(
            "0 8 * * *", 
            code="RETRY_TEST", 
            max_retries=2, 
            retry_delay=0  # 立即重试（测试用）
        )
        async def retry_job(ctx: JobContext):
            attempt_count[0] += 1
            if attempt_count[0] < 2:
                raise ValueError("Simulated failure")
        
        retry_events = []
        
        @scheduler.on_job_retry
        async def on_retry(event):
            retry_events.append(event)
        
        error_events = []
        
        @scheduler.on_job_error
        async def on_error(event):
            error_events.append(event)
        
        job_info = scheduler._jobs["RETRY_TEST"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="RETRY_TEST",
            job_name="retry_job",
            run_id="run_retry_001",
            start_time=datetime.now(),
            attempt=1,
        )
        
        # 第一次执行（会失败并重试）
        await scheduler._execute_job(job_info, context)
        
        # 等待重试完成
        await asyncio.sleep(0.2)
        
        # 验证：第一次失败后触发一次重试，第二次成功
        assert attempt_count[0] == 2
        assert len(retry_events) == 1
        assert retry_events[0].job_code == "RETRY_TEST"
        assert retry_events[0].attempt == 2
        assert retry_events[0].trigger_type == "retry"
        # 最终成功，不应保留终态错误事件
        assert len(error_events) == 1
        assert error_events[0].job_code == "RETRY_TEST"
    
    @pytest.mark.asyncio
    async def test_manual_trigger(self):
        """测试手动触发"""
        scheduler = Scheduler()
        executions = []
        
        @scheduler.cron("0 8 * * *", code="MANUAL_TEST")
        async def manual_job(ctx: JobContext):
            executions.append(ctx.trigger_type)
        
        # 启动调度器（但任务不会因为 cron 时间触发）
        scheduler.start()
        
        try:
            # 手动触发
            run_id = scheduler.run_job("MANUAL_TEST")
            
            assert run_id is not None
            assert run_id.startswith("run_")
            
            # 等待执行完成
            await asyncio.sleep(0.1)
            
            # 验证触发类型
            assert len(executions) == 1
            assert executions[0] == "manual"
        finally:
            scheduler.shutdown(wait=False)
    
    def test_multiple_jobs(self):
        """测试多任务调度"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="JOB_A")
        async def job_a():
            pass
        
        @scheduler.interval(minutes=5, code="JOB_B")
        async def job_b():
            pass
        
        @scheduler.once(
            datetime.now() + timedelta(hours=1),
            code="JOB_C"
        )
        async def job_c():
            pass
        
        # 验证所有任务都注册了
        assert len(scheduler._jobs) == 3
        assert "JOB_A" in scheduler._jobs
        assert "JOB_B" in scheduler._jobs
        assert "JOB_C" in scheduler._jobs
        
        # 获取所有任务
        jobs = scheduler.get_jobs()
        assert len(jobs) == 3
    
    def test_job_management_operations(self):
        """测试任务管理操作"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="MANAGEABLE")
        async def manageable_job():
            pass
        
        # 暂停
        assert scheduler.pause_job("MANAGEABLE") == True
        assert scheduler._jobs["MANAGEABLE"]["is_paused"] == True
        
        # 恢复
        assert scheduler.resume_job("MANAGEABLE") == True
        assert scheduler._jobs["MANAGEABLE"]["is_paused"] == False
        
        # 删除
        assert scheduler.remove_job("MANAGEABLE") == True
        assert "MANAGEABLE" not in scheduler._jobs
    
    def test_dynamic_job_addition(self):
        """测试动态添加任务"""
        scheduler = Scheduler()
        
        # 初始无任务
        assert len(scheduler._jobs) == 0
        
        # 动态添加
        async def dynamic_job():
            pass
        
        code = scheduler.add_job(
            func=dynamic_job,
            trigger=interval(minutes=10),
            code="DYNAMIC",
            name="动态任务",
            description="运行时添加的任务",
        )
        
        assert code == "DYNAMIC"
        assert len(scheduler._jobs) == 1
        
        job_info = scheduler.get_job("DYNAMIC")
        assert job_info["name"] == "动态任务"
        assert job_info["description"] == "运行时添加的任务"


class TestImportFromYweb:
    """测试从 yweb 导入"""
    
    def test_import_scheduler(self):
        """测试导入 Scheduler"""
        from yweb import Scheduler
        
        assert Scheduler is not None
        scheduler = Scheduler()
        assert scheduler is not None
    
    def test_import_triggers(self):
        """测试导入触发器"""
        from yweb import cron, interval, once
        
        assert cron is not None
        assert interval is not None
        assert once is not None
    
    def test_import_context(self):
        """测试导入上下文"""
        from yweb import JobContext
        
        assert JobContext is not None
    
    def test_import_settings(self):
        """测试导入配置"""
        from yweb.config import SchedulerSettings
        
        assert SchedulerSettings is not None


class TestEdgeCases:
    """边界情况测试"""
    
    def test_empty_scheduler_init(self):
        """测试空调度器初始化"""
        scheduler = Scheduler()
        
        # 验证初始状态
        assert scheduler._running == False
        assert scheduler._scheduler is not None
        assert len(scheduler._jobs) == 0
    
    def test_pause_nonexistent_job(self):
        """测试暂停不存在的任务"""
        scheduler = Scheduler()
        
        result = scheduler.pause_job("NOT_EXIST")
        assert result == False
    
    def test_resume_nonexistent_job(self):
        """测试恢复不存在的任务"""
        scheduler = Scheduler()
        
        result = scheduler.resume_job("NOT_EXIST")
        assert result == False
    
    def test_run_nonexistent_job(self):
        """测试运行不存在的任务"""
        scheduler = Scheduler()
        
        result = scheduler.run_job("NOT_EXIST")
        assert result is None
    
    @pytest.mark.asyncio
    async def test_listener_exception_handling(self):
        """测试监听器异常处理"""
        scheduler = Scheduler()
        
        @scheduler.on_job_executed
        async def bad_listener(event):
            raise ValueError("Listener error")
        
        @scheduler.cron("0 8 * * *", code="LISTENER_TEST")
        async def test_job():
            return "ok"
        
        job_info = scheduler._jobs["LISTENER_TEST"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="LISTENER_TEST",
            job_name="test_job",
            run_id="run_test",
            start_time=datetime.now(),
        )
        
        # 监听器异常不应该影响任务执行
        # 应该不抛出异常
        await scheduler._execute_job(job_info, context)
