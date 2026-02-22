"""JobBuilder 测试

测试链式配置构建器的功能。
"""

import pytest

from yweb.scheduler import JobBuilder, Job, cron, interval, Scheduler
from yweb.scheduler.builder import JobConfig


class TestJobBuilder:
    """JobBuilder 测试"""
    
    def test_basic_builder(self):
        """测试基本构建器"""
        async def my_func():
            pass
        
        config = (
            JobBuilder(my_func)
            .code("BASIC")
            .trigger(cron("0 8 * * *"))
            .build()
        )
        
        assert config.code == "BASIC"
        assert config.func is my_func
        assert len(config.get_triggers()) == 1
    
    def test_builder_with_all_options(self):
        """测试完整配置的构建器"""
        async def full_func():
            pass
        
        config = (
            JobBuilder(full_func)
            .code("FULL")
            .name("完整任务")
            .description("测试所有配置项")
            .trigger(interval(hours=1))
            .args(("arg1",))
            .kwargs({"key": "value"})
            .max_retries(3)
            .retry_delay(120)
            .concurrent(False)
            .max_instances(2)
            .timeout(300)
            .enabled(True)
            .build()
        )
        
        assert config.code == "FULL"
        assert config.name == "完整任务"
        assert config.description == "测试所有配置项"
        assert config.args == ("arg1",)
        assert config.kwargs == {"key": "value"}
        assert config.max_retries == 3
        assert config.retry_delay == 120
        assert config.concurrent == False
        assert config.max_instances == 2
        assert config.timeout == 300
        assert config.enabled == True
    
    def test_builder_with_multi_triggers(self):
        """测试多触发器"""
        async def multi_func():
            pass
        
        config = (
            JobBuilder(multi_func)
            .code("MULTI")
            .triggers([
                cron("0 9 * * *"),
                cron("0 14 * * *"),
            ])
            .build()
        )
        
        triggers = config.get_triggers()
        assert len(triggers) == 2
    
    def test_builder_default_code(self):
        """测试默认 code（使用函数名）"""
        async def auto_code_func():
            pass
        
        config = (
            JobBuilder(auto_code_func)
            .trigger(cron("0 8 * * *"))
            .build()
        )
        
        assert config.code == "auto_code_func"
    
    def test_builder_default_name(self):
        """测试默认 name（使用函数名）"""
        async def auto_name_func():
            pass
        
        config = (
            JobBuilder(auto_name_func)
            .code("TEST")
            .trigger(cron("0 8 * * *"))
            .build()
        )
        
        assert config.name == "auto_name_func"
    
    def test_builder_from_class(self):
        """测试从 Job 类创建构建器"""
        class FromClassJob(Job):
            code = "FROM_CLASS"
            name = "类任务"
            description = "从类创建"
            trigger = cron("0 8 * * *")
            max_retries = 2
            
            async def execute(self, context):
                pass
        
        config = (
            JobBuilder.from_class(FromClassJob)
            .build()
        )
        
        assert config.code == "FROM_CLASS"
        assert config.name == "类任务"
        assert config.description == "从类创建"
        assert config.max_retries == 2
    
    def test_builder_from_class_override(self):
        """测试从 Job 类创建并覆盖配置"""
        class OverrideJob(Job):
            code = "OVERRIDE"
            name = "原始名称"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        config = (
            JobBuilder.from_class(OverrideJob)
            .name("覆盖名称")
            .max_retries(5)
            .build()
        )
        
        assert config.name == "覆盖名称"
        assert config.max_retries == 5
    
    def test_builder_without_func_or_class_raises(self):
        """测试缺少函数或类抛出错误"""
        with pytest.raises(ValueError) as exc_info:
            JobBuilder().code("NO_FUNC").trigger(cron("0 8 * * *")).build()
        
        assert "function" in str(exc_info.value).lower() or "class" in str(exc_info.value).lower()
    
    def test_builder_without_trigger_raises(self):
        """测试缺少触发器抛出错误"""
        async def no_trigger():
            pass
        
        with pytest.raises(ValueError) as exc_info:
            JobBuilder(no_trigger).code("NO_TRIGGER").build()
        
        assert "trigger" in str(exc_info.value).lower()
    
    def test_builder_repr(self):
        """测试构建器字符串表示"""
        async def repr_func():
            pass
        
        builder = JobBuilder(repr_func).code("REPR_TEST")
        
        assert "REPR_TEST" in repr(builder)


class TestJobConfig:
    """JobConfig 测试"""
    
    def test_config_to_dict(self):
        """测试配置转字典"""
        config = JobConfig()
        config.code = "DICT_TEST"
        config.name = "字典测试"
        config.max_retries = 3
        
        d = config.to_dict()
        
        assert d["code"] == "DICT_TEST"
        assert d["name"] == "字典测试"
        assert d["max_retries"] == 3
    
    def test_config_get_triggers_single(self):
        """测试获取单个触发器"""
        config = JobConfig()
        config.trigger = cron("0 8 * * *")
        
        triggers = config.get_triggers()
        assert len(triggers) == 1
    
    def test_config_get_triggers_multiple(self):
        """测试获取多个触发器"""
        config = JobConfig()
        config.triggers = [
            cron("0 8 * * *"),
            cron("0 18 * * *"),
        ]
        
        triggers = config.get_triggers()
        assert len(triggers) == 2
    
    def test_config_get_triggers_empty(self):
        """测试无触发器"""
        config = JobConfig()
        
        triggers = config.get_triggers()
        assert len(triggers) == 0


class TestSchedulerBuilderIntegration:
    """Scheduler 与 JobBuilder 集成测试"""
    
    def test_add_job_from_builder(self):
        """测试从构建器添加任务"""
        async def builder_job():
            pass
        
        config = (
            JobBuilder(builder_job)
            .code("BUILDER_INT")
            .name("构建器任务")
            .trigger(cron("0 8 * * *"))
            .build()
        )
        
        scheduler = Scheduler()
        code = scheduler.add_job_from_builder(config)
        
        assert code == "BUILDER_INT"
        assert "BUILDER_INT" in scheduler._jobs
        
        job_info = scheduler._jobs["BUILDER_INT"]
        assert job_info["name"] == "构建器任务"
    
    def test_add_job_from_builder_with_multi_triggers(self):
        """测试从构建器添加多触发器任务"""
        async def multi_builder_job():
            pass
        
        config = (
            JobBuilder(multi_builder_job)
            .code("MULTI_BUILDER")
            .triggers([
                cron("0 9 * * *"),
                cron("0 18 * * *"),
            ])
            .build()
        )
        
        scheduler = Scheduler()
        code = scheduler.add_job_from_builder(config)
        
        assert code == "MULTI_BUILDER"
        # 主任务
        assert "MULTI_BUILDER" in scheduler._jobs
        # 子任务
        assert "MULTI_BUILDER#1" in scheduler._jobs
        assert "MULTI_BUILDER#2" in scheduler._jobs
    
    def test_add_job_from_builder_with_class(self):
        """测试从 Job 类构建器添加任务"""
        class BuilderClassJob(Job):
            code = "BUILDER_CLASS"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                pass
        
        config = (
            JobBuilder.from_class(BuilderClassJob)
            .name("覆盖名称")
            .build()
        )
        
        scheduler = Scheduler()
        code = scheduler.add_job_from_builder(config)
        
        assert code == "BUILDER_CLASS"
        assert scheduler._jobs["BUILDER_CLASS"]["name"] == "覆盖名称"
