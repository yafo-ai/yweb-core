"""任务基类

提供声明式的任务定义方式。

使用示例:
    from yweb.scheduler import Job, cron
    
    class DailyReportJob(Job):
        code = "DAILY_REPORT"
        name = "每日报表"
        description = "每天早上8点生成销售报表"
        trigger = cron("0 8 * * *")
        max_retries = 3
        
        async def execute(self, context):
            print(f"[{context.run_id}] 生成日报...")
    
    # 注册任务
    scheduler.add_job_class(DailyReportJob)
"""

import abc
import logging
from typing import Optional, List, Any, Union, ClassVar

from apscheduler.triggers.base import BaseTrigger

from .context import JobContext
from .triggers import cron, interval, once

logger = logging.getLogger(__name__)


class JobMeta(abc.ABCMeta):
    """Job 元类
    
    自动处理 Job 类的注册和验证。
    """
    
    def __new__(mcs, name, bases, namespace, **kwargs):
        cls = super().__new__(mcs, name, bases, namespace, **kwargs)
        
        # 跳过基类
        if name == "Job":
            return cls
        
        # 验证必须定义 execute 方法
        if not hasattr(cls, 'execute') or not callable(getattr(cls, 'execute')):
            raise TypeError(f"{name} must implement the 'execute' method")
        
        return cls


class Job(metaclass=JobMeta):
    """任务基类
    
    使用声明式方式定义任务，提供面向对象的任务封装。
    
    类属性:
        code: 任务编码（必须）
        name: 任务名称（可选，默认为类名）
        description: 任务描述（可选）
        trigger: 触发器（必须）
        triggers: 多触发器列表（可选，与 trigger 二选一）
        max_retries: 最大重试次数（默认 0）
        retry_delay: 重试间隔秒数（默认 60）
        concurrent: 是否允许并发（默认 True）
        max_instances: 最大并发实例数（默认 1）
        timeout: 执行超时秒数（可选）
    
    Examples:
        # 基本用法
        class SimpleJob(Job):
            code = "SIMPLE"
            trigger = cron("0 8 * * *")
            
            async def execute(self, context):
                print("执行任务")
        
        # 完整配置
        class FullJob(Job):
            code = "FULL_JOB"
            name = "完整配置任务"
            description = "演示所有配置项"
            trigger = interval(minutes=30)
            max_retries = 3
            retry_delay = 120
            concurrent = False
            timeout = 300
            
            async def execute(self, context):
                pass
        
        # 多触发器
        class MultiTriggerJob(Job):
            code = "MULTI_TRIGGER"
            triggers = [
                cron("0 9 * * *"),   # 每天9点
                cron("0 14 * * *"),  # 每天14点
                cron("0 18 * * *"),  # 每天18点
            ]
            
            async def execute(self, context):
                pass
    """
    
    # 必须配置
    code: ClassVar[str] = ""
    trigger: ClassVar[Optional[BaseTrigger]] = None
    
    # 可选配置
    name: ClassVar[Optional[str]] = None
    description: ClassVar[Optional[str]] = None
    triggers: ClassVar[Optional[List[BaseTrigger]]] = None
    
    # 执行配置
    max_retries: ClassVar[int] = 0
    retry_delay: ClassVar[int] = 60
    concurrent: ClassVar[bool] = True
    max_instances: ClassVar[int] = 1
    timeout: ClassVar[Optional[int]] = None
    
    def __init__(self):
        """初始化任务实例"""
        # 验证配置
        if not self.code:
            raise ValueError(f"{self.__class__.__name__} must define 'code'")
        
        if not self.trigger and not self.triggers:
            raise ValueError(f"{self.__class__.__name__} must define 'trigger' or 'triggers'")
    
    @abc.abstractmethod
    async def execute(self, context: JobContext) -> Any:
        """执行任务（子类必须实现）
        
        Args:
            context: 任务执行上下文
        
        Returns:
            任务执行结果（可选）
        """
        raise NotImplementedError
    
    async def on_success(self, context: JobContext, result: Any) -> None:
        """任务执行成功回调（可选覆盖）
        
        Args:
            context: 任务执行上下文
            result: 执行结果
        """
        pass
    
    async def on_error(self, context: JobContext, error: Exception) -> None:
        """任务执行失败回调（可选覆盖）
        
        Args:
            context: 任务执行上下文
            error: 异常对象
        """
        pass
    
    async def on_retry(self, context: JobContext, error: Exception) -> None:
        """任务重试回调（可选覆盖）
        
        Args:
            context: 任务执行上下文
            error: 导致重试的异常
        """
        pass
    
    def get_triggers(self) -> List[BaseTrigger]:
        """获取所有触发器
        
        Returns:
            触发器列表
        """
        if self.triggers:
            return self.triggers
        elif self.trigger:
            return [self.trigger]
        return []
    
    def get_name(self) -> str:
        """获取任务名称
        
        Returns:
            任务名称
        """
        return self.name or self.__class__.__name__
    
    def get_description(self) -> Optional[str]:
        """获取任务描述
        
        Returns:
            任务描述
        """
        return self.description or self.__class__.__doc__
    
    @classmethod
    def get_job_info(cls) -> dict:
        """获取任务配置信息
        
        Returns:
            任务配置字典
        """
        instance = cls()
        return {
            "code": cls.code,
            "name": instance.get_name(),
            "description": instance.get_description(),
            "max_retries": cls.max_retries,
            "retry_delay": cls.retry_delay,
            "concurrent": cls.concurrent,
            "max_instances": cls.max_instances,
            "timeout": cls.timeout,
        }
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(code={self.code})>"
