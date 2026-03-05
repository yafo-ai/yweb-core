"""重试策略

提供多种重试策略，支持自定义重试逻辑。

使用示例:
    from yweb.scheduler import RetryStrategy
    
    # 固定间隔重试
    strategy = RetryStrategy.fixed(max_retries=3, delay=60)
    
    # 指数退避重试
    strategy = RetryStrategy.exponential(max_retries=5, base_delay=10, max_delay=300)
    
    # 自定义重试
    strategy = RetryStrategy.custom(
        max_retries=3,
        delay_func=lambda attempt: attempt * 30
    )
"""

import abc
import random
from dataclasses import dataclass, field
from typing import Callable, Optional, List, Any


@dataclass
class RetryStrategy:
    """重试策略
    
    配置任务失败后的重试行为。
    
    Attributes:
        max_retries: 最大重试次数
        delay: 基础延迟时间（秒）
        max_delay: 最大延迟时间（秒）
        backoff_factor: 退避因子（用于指数退避）
        jitter: 是否添加随机抖动
        retry_on: 只在特定异常时重试（为空则所有异常都重试）
        ignore_on: 忽略这些异常不重试
    """
    
    max_retries: int = 3
    delay: int = 60
    max_delay: Optional[int] = None
    backoff_factor: float = 1.0
    jitter: bool = False
    retry_on: List[type] = field(default_factory=list)
    ignore_on: List[type] = field(default_factory=list)
    _delay_func: Optional[Callable[[int], int]] = field(default=None, repr=False)
    
    def get_delay(self, attempt: int) -> int:
        """计算第 N 次重试的延迟时间
        
        Args:
            attempt: 当前重试次数（从 1 开始）
        
        Returns:
            延迟时间（秒）
        """
        if self._delay_func:
            delay = self._delay_func(attempt)
        elif self.backoff_factor > 1:
            # 指数退避
            delay = int(self.delay * (self.backoff_factor ** (attempt - 1)))
        else:
            # 固定间隔
            delay = self.delay
        
        # 最大延迟限制
        if self.max_delay:
            delay = min(delay, self.max_delay)
        
        # 添加随机抖动（±20%）
        if self.jitter:
            jitter_range = delay * 0.2
            delay = int(delay + random.uniform(-jitter_range, jitter_range))
        
        return max(0, delay)
    
    def should_retry(self, exception: Exception, attempt: int) -> bool:
        """判断是否应该重试
        
        Args:
            exception: 捕获的异常
            attempt: 当前重试次数
        
        Returns:
            是否应该重试
        """
        # 超过最大重试次数
        if attempt >= self.max_retries:
            return False
        
        # 检查忽略列表
        if self.ignore_on:
            for exc_type in self.ignore_on:
                if isinstance(exception, exc_type):
                    return False
        
        # 检查重试列表
        if self.retry_on:
            for exc_type in self.retry_on:
                if isinstance(exception, exc_type):
                    return True
            return False
        
        # 默认重试所有异常
        return True
    
    @classmethod
    def fixed(
        cls,
        max_retries: int = 3,
        delay: int = 60,
        jitter: bool = False,
        retry_on: Optional[List[type]] = None,
        ignore_on: Optional[List[type]] = None,
    ) -> "RetryStrategy":
        """创建固定间隔重试策略
        
        Args:
            max_retries: 最大重试次数
            delay: 固定延迟时间（秒）
            jitter: 是否添加随机抖动
            retry_on: 只在特定异常时重试
            ignore_on: 忽略这些异常不重试
        
        Returns:
            RetryStrategy 实例
        
        Examples:
            # 每次重试间隔 60 秒，最多重试 3 次
            strategy = RetryStrategy.fixed(max_retries=3, delay=60)
        """
        return cls(
            max_retries=max_retries,
            delay=delay,
            backoff_factor=1.0,
            jitter=jitter,
            retry_on=retry_on or [],
            ignore_on=ignore_on or [],
        )
    
    @classmethod
    def exponential(
        cls,
        max_retries: int = 5,
        base_delay: int = 10,
        max_delay: int = 300,
        backoff_factor: float = 2.0,
        jitter: bool = True,
        retry_on: Optional[List[type]] = None,
        ignore_on: Optional[List[type]] = None,
    ) -> "RetryStrategy":
        """创建指数退避重试策略
        
        延迟计算：delay = base_delay * (backoff_factor ^ (attempt - 1))
        
        Args:
            max_retries: 最大重试次数
            base_delay: 基础延迟时间（秒）
            max_delay: 最大延迟时间（秒）
            backoff_factor: 退避因子（默认 2.0，每次延迟翻倍）
            jitter: 是否添加随机抖动（推荐开启）
            retry_on: 只在特定异常时重试
            ignore_on: 忽略这些异常不重试
        
        Returns:
            RetryStrategy 实例
        
        Examples:
            # 指数退避：10s, 20s, 40s, 80s, 160s（最大 300s）
            strategy = RetryStrategy.exponential(
                max_retries=5,
                base_delay=10,
                max_delay=300,
                backoff_factor=2.0
            )
        """
        return cls(
            max_retries=max_retries,
            delay=base_delay,
            max_delay=max_delay,
            backoff_factor=backoff_factor,
            jitter=jitter,
            retry_on=retry_on or [],
            ignore_on=ignore_on or [],
        )
    
    @classmethod
    def linear(
        cls,
        max_retries: int = 5,
        initial_delay: int = 10,
        increment: int = 10,
        max_delay: Optional[int] = None,
        jitter: bool = False,
        retry_on: Optional[List[type]] = None,
        ignore_on: Optional[List[type]] = None,
    ) -> "RetryStrategy":
        """创建线性递增重试策略
        
        延迟计算：delay = initial_delay + increment * (attempt - 1)
        
        Args:
            max_retries: 最大重试次数
            initial_delay: 初始延迟时间（秒）
            increment: 每次递增的时间（秒）
            max_delay: 最大延迟时间（秒）
            jitter: 是否添加随机抖动
            retry_on: 只在特定异常时重试
            ignore_on: 忽略这些异常不重试
        
        Returns:
            RetryStrategy 实例
        
        Examples:
            # 线性递增：10s, 20s, 30s, 40s, 50s
            strategy = RetryStrategy.linear(
                max_retries=5,
                initial_delay=10,
                increment=10
            )
        """
        def delay_func(attempt: int) -> int:
            return initial_delay + increment * (attempt - 1)
        
        return cls(
            max_retries=max_retries,
            delay=initial_delay,
            max_delay=max_delay,
            jitter=jitter,
            retry_on=retry_on or [],
            ignore_on=ignore_on or [],
            _delay_func=delay_func,
        )
    
    @classmethod
    def custom(
        cls,
        max_retries: int,
        delay_func: Callable[[int], int],
        jitter: bool = False,
        retry_on: Optional[List[type]] = None,
        ignore_on: Optional[List[type]] = None,
    ) -> "RetryStrategy":
        """创建自定义重试策略
        
        Args:
            max_retries: 最大重试次数
            delay_func: 延迟计算函数，接收 attempt 参数，返回延迟秒数
            jitter: 是否添加随机抖动
            retry_on: 只在特定异常时重试
            ignore_on: 忽略这些异常不重试
        
        Returns:
            RetryStrategy 实例
        
        Examples:
            # 自定义：第 N 次重试等待 N * 30 秒
            strategy = RetryStrategy.custom(
                max_retries=3,
                delay_func=lambda attempt: attempt * 30
            )
        """
        return cls(
            max_retries=max_retries,
            delay=0,
            jitter=jitter,
            retry_on=retry_on or [],
            ignore_on=ignore_on or [],
            _delay_func=delay_func,
        )
    
    @classmethod
    def none(cls) -> "RetryStrategy":
        """创建不重试策略
        
        Returns:
            RetryStrategy 实例（max_retries=0）
        """
        return cls(max_retries=0)
    
    def __repr__(self) -> str:
        if self._delay_func:
            return f"RetryStrategy(max_retries={self.max_retries}, custom_delay)"
        elif self.backoff_factor > 1:
            return f"RetryStrategy(max_retries={self.max_retries}, exponential, factor={self.backoff_factor})"
        else:
            return f"RetryStrategy(max_retries={self.max_retries}, fixed, delay={self.delay}s)"
