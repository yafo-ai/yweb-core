"""RetryStrategy 测试

测试重试策略功能。
"""

import pytest

from yweb.scheduler import RetryStrategy


class TestRetryStrategyFixed:
    """固定间隔重试策略测试"""
    
    def test_fixed_basic(self):
        """测试基本固定间隔"""
        strategy = RetryStrategy.fixed(max_retries=3, delay=60)
        
        assert strategy.max_retries == 3
        assert strategy.delay == 60
        assert strategy.get_delay(1) == 60
        assert strategy.get_delay(2) == 60
        assert strategy.get_delay(3) == 60
    
    def test_fixed_should_retry(self):
        """测试重试判断"""
        strategy = RetryStrategy.fixed(max_retries=3)
        
        error = ValueError("test error")
        
        assert strategy.should_retry(error, 1) == True
        assert strategy.should_retry(error, 2) == True
        assert strategy.should_retry(error, 3) == False  # 达到最大重试次数


class TestRetryStrategyExponential:
    """指数退避重试策略测试"""
    
    def test_exponential_basic(self):
        """测试基本指数退避"""
        strategy = RetryStrategy.exponential(
            max_retries=5,
            base_delay=10,
            backoff_factor=2.0,
            jitter=False,
        )
        
        assert strategy.get_delay(1) == 10   # 10 * 2^0
        assert strategy.get_delay(2) == 20   # 10 * 2^1
        assert strategy.get_delay(3) == 40   # 10 * 2^2
        assert strategy.get_delay(4) == 80   # 10 * 2^3
        assert strategy.get_delay(5) == 160  # 10 * 2^4
    
    def test_exponential_max_delay(self):
        """测试最大延迟限制"""
        strategy = RetryStrategy.exponential(
            max_retries=5,
            base_delay=10,
            max_delay=50,
            backoff_factor=2.0,
            jitter=False,
        )
        
        assert strategy.get_delay(1) == 10
        assert strategy.get_delay(2) == 20
        assert strategy.get_delay(3) == 40
        assert strategy.get_delay(4) == 50  # 受限于 max_delay
        assert strategy.get_delay(5) == 50  # 受限于 max_delay
    
    def test_exponential_with_jitter(self):
        """测试带抖动的指数退避"""
        strategy = RetryStrategy.exponential(
            max_retries=3,
            base_delay=100,
            jitter=True,
        )
        
        # 抖动应该在 ±20% 范围内
        delay = strategy.get_delay(1)
        assert 80 <= delay <= 120


class TestRetryStrategyLinear:
    """线性递增重试策略测试"""
    
    def test_linear_basic(self):
        """测试基本线性递增"""
        strategy = RetryStrategy.linear(
            max_retries=5,
            initial_delay=10,
            increment=10,
            jitter=False,
        )
        
        assert strategy.get_delay(1) == 10  # 10 + 10 * 0
        assert strategy.get_delay(2) == 20  # 10 + 10 * 1
        assert strategy.get_delay(3) == 30  # 10 + 10 * 2
        assert strategy.get_delay(4) == 40  # 10 + 10 * 3
        assert strategy.get_delay(5) == 50  # 10 + 10 * 4
    
    def test_linear_max_delay(self):
        """测试线性递增最大延迟"""
        strategy = RetryStrategy.linear(
            max_retries=5,
            initial_delay=10,
            increment=20,
            max_delay=50,
            jitter=False,
        )
        
        assert strategy.get_delay(1) == 10
        assert strategy.get_delay(2) == 30
        assert strategy.get_delay(3) == 50  # 受限于 max_delay


class TestRetryStrategyCustom:
    """自定义重试策略测试"""
    
    def test_custom_delay_func(self):
        """测试自定义延迟函数"""
        strategy = RetryStrategy.custom(
            max_retries=3,
            delay_func=lambda attempt: attempt * 30,
        )
        
        assert strategy.get_delay(1) == 30
        assert strategy.get_delay(2) == 60
        assert strategy.get_delay(3) == 90
    
    def test_custom_fibonacci(self):
        """测试斐波那契延迟"""
        def fibonacci_delay(attempt):
            a, b = 1, 1
            for _ in range(attempt - 1):
                a, b = b, a + b
            return a * 10
        
        strategy = RetryStrategy.custom(
            max_retries=5,
            delay_func=fibonacci_delay,
        )
        
        assert strategy.get_delay(1) == 10   # 1 * 10
        assert strategy.get_delay(2) == 10   # 1 * 10
        assert strategy.get_delay(3) == 20   # 2 * 10
        assert strategy.get_delay(4) == 30   # 3 * 10
        assert strategy.get_delay(5) == 50   # 5 * 10


class TestRetryStrategyNone:
    """不重试策略测试"""
    
    def test_none_strategy(self):
        """测试不重试"""
        strategy = RetryStrategy.none()
        
        assert strategy.max_retries == 0
        assert strategy.should_retry(ValueError("test"), 1) == False


class TestRetryStrategyExceptions:
    """异常过滤测试"""
    
    def test_retry_on_specific_exceptions(self):
        """测试只在特定异常时重试"""
        strategy = RetryStrategy.fixed(
            max_retries=3,
            retry_on=[ConnectionError, TimeoutError],
        )
        
        # 连接错误应该重试
        assert strategy.should_retry(ConnectionError("test"), 1) == True
        
        # 值错误不应该重试
        assert strategy.should_retry(ValueError("test"), 1) == False
    
    def test_ignore_specific_exceptions(self):
        """测试忽略特定异常"""
        strategy = RetryStrategy.fixed(
            max_retries=3,
            ignore_on=[KeyboardInterrupt, SystemExit],
        )
        
        # 普通错误应该重试
        assert strategy.should_retry(ValueError("test"), 1) == True
        
        # 键盘中断不应该重试
        assert strategy.should_retry(KeyboardInterrupt(), 1) == False


class TestRetryStrategyRepr:
    """字符串表示测试"""
    
    def test_fixed_repr(self):
        """测试固定间隔的字符串表示"""
        strategy = RetryStrategy.fixed(max_retries=3, delay=60)
        repr_str = repr(strategy)
        
        assert "max_retries=3" in repr_str
        assert "fixed" in repr_str
    
    def test_exponential_repr(self):
        """测试指数退避的字符串表示"""
        strategy = RetryStrategy.exponential(max_retries=5)
        repr_str = repr(strategy)
        
        assert "max_retries=5" in repr_str
        assert "exponential" in repr_str
    
    def test_custom_repr(self):
        """测试自定义的字符串表示"""
        strategy = RetryStrategy.custom(
            max_retries=3,
            delay_func=lambda x: x * 10
        )
        repr_str = repr(strategy)
        
        assert "custom" in repr_str
