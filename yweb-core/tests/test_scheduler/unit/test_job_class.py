"""Job 基类测试

测试声明式类任务的功能。
"""

import pytest
from datetime import datetime

from yweb.scheduler import Job, cron, interval, JobContext


class TestJobClass:
    """Job 基类测试"""
    
    def test_simple_job_class(self):
        """测试简单 Job 类定义"""
        class SimpleJob(Job):
            code = "SIMPLE"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                return "done"
        
        job = SimpleJob()
        assert job.code == "SIMPLE"
        assert job.get_name() == "SimpleJob"
        assert len(job.get_triggers()) == 1
    
    def test_job_with_all_options(self):
        """测试完整配置的 Job 类"""
        class FullJob(Job):
            code = "FULL_JOB"
            name = "完整配置任务"
            description = "测试所有配置项"
            trigger = interval(minutes=30)
            max_retries = 3
            retry_delay = 120
            concurrent = False
            max_instances = 1
            timeout = 300
            
            async def execute(self, context):
                pass
        
        job = FullJob()
        assert job.code == "FULL_JOB"
        assert job.get_name() == "完整配置任务"
        assert job.get_description() == "测试所有配置项"
        assert job.max_retries == 3
        assert job.retry_delay == 120
        assert job.concurrent == False
        assert job.timeout == 300
    
    def test_job_with_multi_triggers(self):
        """测试多触发器 Job 类"""
        class MultiTriggerJob(Job):
            code = "MULTI_TRIGGER"
            triggers = [
                cron("0 9 * * *"),
                cron("0 14 * * *"),
                cron("0 18 * * *"),
            ]
            
            async def execute(self, context):
                pass
        
        job = MultiTriggerJob()
        triggers = job.get_triggers()
        assert len(triggers) == 3
    
    def test_job_without_code_raises_error(self):
        """测试缺少 code 抛出错误"""
        class NoCodeJob(Job):
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        with pytest.raises(ValueError) as exc_info:
            NoCodeJob()
        
        assert "must define 'code'" in str(exc_info.value)
    
    def test_job_without_trigger_raises_error(self):
        """测试缺少触发器抛出错误"""
        class NoTriggerJob(Job):
            code = "NO_TRIGGER"
            
            async def execute(self, context):
                pass
        
        with pytest.raises(ValueError) as exc_info:
            NoTriggerJob()
        
        assert "must define 'trigger'" in str(exc_info.value)
    
    def test_job_info(self):
        """测试获取任务信息"""
        class InfoJob(Job):
            code = "INFO_JOB"
            name = "信息任务"
            description = "测试任务信息"
            trigger = cron("0 8 * * *")
            max_retries = 2
            
            async def execute(self, context):
                pass
        
        info = InfoJob.get_job_info()
        
        assert info["code"] == "INFO_JOB"
        assert info["name"] == "信息任务"
        assert info["description"] == "测试任务信息"
        assert info["max_retries"] == 2
    
    def test_job_default_name(self):
        """测试默认名称（使用类名）"""
        class MyCustomJob(Job):
            code = "CUSTOM"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        job = MyCustomJob()
        assert job.get_name() == "MyCustomJob"
    
    def test_job_docstring_as_description(self):
        """测试使用 docstring 作为描述"""
        class DocstringJob(Job):
            """这是任务的文档字符串描述"""
            code = "DOCSTRING"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        job = DocstringJob()
        assert "文档字符串描述" in job.get_description()
    
    def test_job_repr(self):
        """测试 Job 字符串表示"""
        class ReprJob(Job):
            code = "REPR"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        job = ReprJob()
        repr_str = repr(job)
        
        assert "ReprJob" in repr_str
        assert "REPR" in repr_str


class TestJobCallbacks:
    """Job 回调测试"""
    
    @pytest.mark.asyncio
    async def test_on_success_callback(self):
        """测试成功回调"""
        callback_called = []
        
        class SuccessCallbackJob(Job):
            code = "SUCCESS_CB"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                return "result"
            
            async def on_success(self, context, result):
                callback_called.append(("success", result))
        
        job = SuccessCallbackJob()
        context = JobContext(
            job_id="test",
            job_code="SUCCESS_CB",
            job_name="test",
        )
        
        result = await job.execute(context)
        await job.on_success(context, result)
        
        assert len(callback_called) == 1
        assert callback_called[0] == ("success", "result")
    
    @pytest.mark.asyncio
    async def test_on_error_callback(self):
        """测试失败回调"""
        callback_called = []
        
        class ErrorCallbackJob(Job):
            code = "ERROR_CB"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                raise ValueError("Test error")
            
            async def on_error(self, context, error):
                callback_called.append(("error", str(error)))
        
        job = ErrorCallbackJob()
        context = JobContext(
            job_id="test",
            job_code="ERROR_CB",
            job_name="test",
        )
        
        try:
            await job.execute(context)
        except ValueError as e:
            await job.on_error(context, e)
        
        assert len(callback_called) == 1
        assert "Test error" in callback_called[0][1]


class TestSchedulerJobClassIntegration:
    """Scheduler 与 Job 类集成测试"""
    
    def test_add_job_class(self):
        """测试添加 Job 类到调度器"""
        from yweb.scheduler import Scheduler
        
        class IntegrationJob(Job):
            code = "INTEGRATION"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        scheduler = Scheduler()
        code = scheduler.add_job_class(IntegrationJob)
        
        assert code == "INTEGRATION"
        assert "INTEGRATION" in scheduler._jobs
    
    def test_add_job_class_with_multi_triggers(self):
        """测试添加多触发器 Job 类"""
        from yweb.scheduler import Scheduler
        
        class MultiTriggerIntJob(Job):
            code = "MULTI_INT"
            triggers = [
                cron("0 9 * * *"),
                cron("0 18 * * *"),
            ]
            
            async def execute(self, context):
                pass
        
        scheduler = Scheduler()
        code = scheduler.add_job_class(MultiTriggerIntJob)
        
        assert code == "MULTI_INT"
        # 主任务
        assert "MULTI_INT" in scheduler._jobs
        # 子任务
        assert "MULTI_INT#1" in scheduler._jobs
        assert "MULTI_INT#2" in scheduler._jobs
