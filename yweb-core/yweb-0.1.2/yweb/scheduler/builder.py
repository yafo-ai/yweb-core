"""任务构建器

提供链式 API 构建任务配置。

使用示例:
    from yweb.scheduler import JobBuilder, cron, interval
    
    # 链式配置
    job = (
        JobBuilder(my_func)
        .code("DAILY_REPORT")
        .name("每日报表")
        .description("每天早上8点生成销售报表")
        .trigger(cron("0 8 * * *"))
        .max_retries(3)
        .retry_delay(60)
        .concurrent(False)
        .build()
    )
    
    # 注册到调度器
    scheduler.add_job_from_builder(job)
    
    # 多触发器
    job = (
        JobBuilder(my_func)
        .code("MULTI_TRIGGER")
        .triggers([
            cron("0 9 * * *"),
            cron("0 14 * * *"),
        ])
        .build()
    )
"""

from typing import Optional, List, Callable, Any, Union, Type

from apscheduler.triggers.base import BaseTrigger

from .context import JobContext
from .job import Job


class JobConfig:
    """任务配置数据类
    
    存储 JobBuilder 构建的配置。
    """
    
    def __init__(self):
        self.func: Optional[Callable] = None
        self.job_class: Optional[Type[Job]] = None
        self.code: Optional[str] = None
        self.name: Optional[str] = None
        self.description: Optional[str] = None
        self.trigger: Optional[BaseTrigger] = None
        self.triggers: Optional[List[BaseTrigger]] = None
        self.args: tuple = ()
        self.kwargs: dict = {}
        self.max_retries: int = 0
        self.retry_delay: int = 60
        self.concurrent: bool = True
        self.max_instances: int = 1
        self.timeout: Optional[int] = None
        self.enabled: bool = True
    
    def get_triggers(self) -> List[BaseTrigger]:
        """获取所有触发器"""
        if self.triggers:
            return self.triggers
        elif self.trigger:
            return [self.trigger]
        return []
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "code": self.code,
            "name": self.name,
            "description": self.description,
            "max_retries": self.max_retries,
            "retry_delay": self.retry_delay,
            "concurrent": self.concurrent,
            "max_instances": self.max_instances,
            "timeout": self.timeout,
            "enabled": self.enabled,
        }


class JobBuilder:
    """任务构建器
    
    提供流畅的链式 API 来构建任务配置。
    
    Examples:
        # 基本用法
        job = (
            JobBuilder(my_func)
            .code("MY_JOB")
            .trigger(cron("0 8 * * *"))
            .build()
        )
        
        # 完整配置
        job = (
            JobBuilder(process_data)
            .code("DATA_PROCESS")
            .name("数据处理")
            .description("每小时处理新数据")
            .trigger(interval(hours=1))
            .args(("source1",))
            .kwargs({"batch_size": 100})
            .max_retries(3)
            .retry_delay(120)
            .concurrent(False)
            .timeout(300)
            .build()
        )
        
        # 从 Job 类构建
        job = (
            JobBuilder.from_class(MyJobClass)
            .name("自定义名称")  # 覆盖类定义
            .build()
        )
    """
    
    def __init__(self, func: Optional[Callable] = None):
        """初始化构建器
        
        Args:
            func: 任务函数（可选）
        """
        self._config = JobConfig()
        self._config.func = func
    
    @classmethod
    def from_class(cls, job_class: Type[Job]) -> "JobBuilder":
        """从 Job 类创建构建器
        
        Args:
            job_class: Job 子类
        
        Returns:
            JobBuilder 实例
        """
        builder = cls()
        builder._config.job_class = job_class
        
        # 继承类的配置
        builder._config.code = job_class.code
        builder._config.name = job_class.name
        builder._config.description = job_class.description
        builder._config.trigger = job_class.trigger
        builder._config.triggers = job_class.triggers
        builder._config.max_retries = job_class.max_retries
        builder._config.retry_delay = job_class.retry_delay
        builder._config.concurrent = job_class.concurrent
        builder._config.max_instances = job_class.max_instances
        builder._config.timeout = job_class.timeout
        
        return builder
    
    def code(self, code: str) -> "JobBuilder":
        """设置任务编码
        
        Args:
            code: 任务编码
        
        Returns:
            self
        """
        self._config.code = code
        return self
    
    def name(self, name: str) -> "JobBuilder":
        """设置任务名称
        
        Args:
            name: 任务名称
        
        Returns:
            self
        """
        self._config.name = name
        return self
    
    def description(self, description: str) -> "JobBuilder":
        """设置任务描述
        
        Args:
            description: 任务描述
        
        Returns:
            self
        """
        self._config.description = description
        return self
    
    def trigger(self, trigger: BaseTrigger) -> "JobBuilder":
        """设置触发器
        
        Args:
            trigger: 触发器实例
        
        Returns:
            self
        """
        self._config.trigger = trigger
        return self
    
    def triggers(self, triggers: List[BaseTrigger]) -> "JobBuilder":
        """设置多个触发器
        
        Args:
            triggers: 触发器列表
        
        Returns:
            self
        """
        self._config.triggers = triggers
        return self
    
    def args(self, args: tuple) -> "JobBuilder":
        """设置位置参数
        
        Args:
            args: 位置参数元组
        
        Returns:
            self
        """
        self._config.args = args
        return self
    
    def kwargs(self, kwargs: dict) -> "JobBuilder":
        """设置关键字参数
        
        Args:
            kwargs: 关键字参数字典
        
        Returns:
            self
        """
        self._config.kwargs = kwargs
        return self
    
    def max_retries(self, retries: int) -> "JobBuilder":
        """设置最大重试次数
        
        Args:
            retries: 重试次数
        
        Returns:
            self
        """
        self._config.max_retries = retries
        return self
    
    def retry_delay(self, delay: int) -> "JobBuilder":
        """设置重试间隔（秒）
        
        Args:
            delay: 间隔秒数
        
        Returns:
            self
        """
        self._config.retry_delay = delay
        return self
    
    def concurrent(self, concurrent: bool) -> "JobBuilder":
        """设置是否允许并发
        
        Args:
            concurrent: 是否并发
        
        Returns:
            self
        """
        self._config.concurrent = concurrent
        return self
    
    def max_instances(self, instances: int) -> "JobBuilder":
        """设置最大并发实例数
        
        Args:
            instances: 实例数
        
        Returns:
            self
        """
        self._config.max_instances = instances
        return self
    
    def timeout(self, timeout: int) -> "JobBuilder":
        """设置执行超时（秒）
        
        Args:
            timeout: 超时秒数
        
        Returns:
            self
        """
        self._config.timeout = timeout
        return self
    
    def enabled(self, enabled: bool) -> "JobBuilder":
        """设置是否启用
        
        Args:
            enabled: 是否启用
        
        Returns:
            self
        """
        self._config.enabled = enabled
        return self
    
    def build(self) -> JobConfig:
        """构建任务配置
        
        Returns:
            JobConfig 实例
        
        Raises:
            ValueError: 配置不完整
        """
        # 验证必要配置
        if not self._config.func and not self._config.job_class:
            raise ValueError("Must provide either a function or a Job class")
        
        if not self._config.code:
            # 尝试从函数名或类名推断
            if self._config.func:
                self._config.code = self._config.func.__name__
            elif self._config.job_class:
                self._config.code = self._config.job_class.code
        
        if not self._config.code:
            raise ValueError("Must provide a code")
        
        if not self._config.trigger and not self._config.triggers:
            raise ValueError("Must provide at least one trigger")
        
        # 设置默认名称
        if not self._config.name:
            if self._config.func:
                self._config.name = self._config.func.__name__
            elif self._config.job_class:
                self._config.name = self._config.job_class.__name__
        
        return self._config
    
    def __repr__(self) -> str:
        return f"<JobBuilder(code={self._config.code})>"
