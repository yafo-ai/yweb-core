"""调度器修复功能测试

测试 timeout、分布式锁、RetryStrategy 等新功能。
"""

import pytest
import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, patch, MagicMock

from yweb.scheduler import Scheduler, JobContext, cron, interval
from yweb.scheduler.retry import RetryStrategy
from yweb.config import SchedulerSettings


class TestSchedulerTimeout:
    """超时控制测试"""
    
    def test_cron_decorator_with_timeout(self):
        """测试 cron 装饰器支持 timeout 参数"""
        scheduler = Scheduler()
        
        @scheduler.cron("0 8 * * *", code="TIMEOUT_TASK", timeout=30)
        async def timeout_task():
            pass
        
        job_info = scheduler._jobs["TIMEOUT_TASK"]
        assert job_info["timeout"] == 30
    
    def test_interval_decorator_with_timeout(self):
        """测试 interval 装饰器支持 timeout 参数"""
        scheduler = Scheduler()
        
        @scheduler.interval(minutes=5, code="INTERVAL_TIMEOUT", timeout=60)
        async def interval_task():
            pass
        
        job_info = scheduler._jobs["INTERVAL_TIMEOUT"]
        assert job_info["timeout"] == 60
    
    def test_add_job_with_timeout(self):
        """测试 add_job 支持 timeout 参数"""
        scheduler = Scheduler()
        
        async def my_task():
            pass
        
        scheduler.add_job(
            func=my_task,
            trigger=cron("0 8 * * *"),
            code="DYNAMIC_TIMEOUT",
            timeout=120,
        )
        
        job_info = scheduler._jobs["DYNAMIC_TIMEOUT"]
        assert job_info["timeout"] == 120
    
    @pytest.mark.asyncio
    async def test_execute_job_timeout(self):
        """测试任务执行超时"""
        scheduler = Scheduler()
        events = []
        
        @scheduler.on_job_error
        async def on_error(event):
            events.append(event)
        
        @scheduler.cron("0 8 * * *", code="WILL_TIMEOUT", timeout=1)
        async def slow_task():
            await asyncio.sleep(5)  # 会超时
        
        job_info = scheduler._jobs["WILL_TIMEOUT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="WILL_TIMEOUT",
            job_name="slow_task",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        # 应该触发错误事件
        assert len(events) == 1
        assert "timed out" in events[0].error
        assert job_info["last_status"] == "timeout"
    
    @pytest.mark.asyncio
    async def test_execute_job_within_timeout(self):
        """测试任务在超时内完成"""
        scheduler = Scheduler()
        executed = []
        
        @scheduler.cron("0 8 * * *", code="FAST_TASK", timeout=10)
        async def fast_task():
            executed.append(True)
        
        job_info = scheduler._jobs["FAST_TASK"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="FAST_TASK",
            job_name="fast_task",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        await scheduler._execute_job(job_info, context)
        
        assert len(executed) == 1
        assert job_info["last_status"] == "success"


class TestSchedulerDistributedLock:
    """分布式锁测试"""
    
    def test_get_distributed_lock_memory(self):
        """测试获取内存锁（默认）"""
        scheduler = Scheduler()
        
        lock = scheduler._get_distributed_lock()
        
        # 默认应该是 MemoryLock
        from yweb.scheduler.locks.redis_lock import MemoryLock
        assert isinstance(lock, MemoryLock)
    
    def test_get_distributed_lock_redis(self):
        """测试获取 Redis 锁"""
        settings = SchedulerSettings(
            distributed_lock=True,
            redis_url="redis://localhost:6379/0",
        )
        scheduler = Scheduler(settings=settings)
        
        lock = scheduler._get_distributed_lock()
        
        from yweb.scheduler.locks.redis_lock import RedisDistributedLock
        assert isinstance(lock, RedisDistributedLock)
    
    @pytest.mark.asyncio
    async def test_concurrent_false_uses_lock(self):
        """测试 concurrent=False 时使用分布式锁"""
        scheduler = Scheduler()
        executed = []
        
        @scheduler.cron("0 8 * * *", code="NO_CONCURRENT", concurrent=False)
        async def no_concurrent_task():
            executed.append(True)
        
        job_info = scheduler._jobs["NO_CONCURRENT"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="NO_CONCURRENT",
            job_name="no_concurrent_task",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        # Mock 分布式锁
        mock_lock = AsyncMock()
        mock_lock.acquire = AsyncMock(return_value=True)
        mock_lock.release = AsyncMock(return_value=True)
        scheduler._distributed_lock = mock_lock
        
        await scheduler._execute_job(job_info, context)
        
        # 应该获取锁和释放锁
        mock_lock.acquire.assert_called_once()
        mock_lock.release.assert_called_once()
        assert len(executed) == 1
    
    @pytest.mark.asyncio
    async def test_concurrent_false_lock_fail_skip(self):
        """测试 concurrent=False 且获取锁失败时跳过执行"""
        scheduler = Scheduler()
        executed = []
        
        @scheduler.cron("0 8 * * *", code="LOCK_FAIL", concurrent=False)
        async def lock_fail_task():
            executed.append(True)
        
        job_info = scheduler._jobs["LOCK_FAIL"]
        context = JobContext(
            job_id=job_info["id"],
            job_code="LOCK_FAIL",
            job_name="lock_fail_task",
            run_id="test_run_id",
            start_time=datetime.now(),
            scheduled_time=datetime.now(),
        )
        
        # Mock 分布式锁获取失败
        mock_lock = AsyncMock()
        mock_lock.acquire = AsyncMock(return_value=False)
        scheduler._distributed_lock = mock_lock
        
        await scheduler._execute_job(job_info, context)
        
        # 应该跳过执行
        assert len(executed) == 0
        mock_lock.release.assert_not_called()


class TestSchedulerRetryStrategy:
    """重试策略测试"""
    
    def test_cron_decorator_with_retry_strategy(self):
        """测试 cron 装饰器支持 retry_strategy 参数"""
        scheduler = Scheduler()
        strategy = RetryStrategy.exponential(max_retries=5, base_delay=10)
        
        @scheduler.cron("0 8 * * *", code="RETRY_STRATEGY", retry_strategy=strategy)
        async def retry_task():
            pass
        
        job_info = scheduler._jobs["RETRY_STRATEGY"]
        assert job_info["retry_strategy"] is strategy
        assert job_info["max_retries"] == 5
        assert job_info["retry_delay"] == 10
    
    def test_interval_decorator_with_retry_strategy(self):
        """测试 interval 装饰器支持 retry_strategy 参数"""
        scheduler = Scheduler()
        strategy = RetryStrategy.fixed(max_retries=3, delay=30)
        
        @scheduler.interval(minutes=5, code="INTERVAL_RETRY", retry_strategy=strategy)
        async def interval_task():
            pass
        
        job_info = scheduler._jobs["INTERVAL_RETRY"]
        assert job_info["retry_strategy"] is strategy
        assert job_info["max_retries"] == 3
    
    def test_retry_strategy_priority_over_params(self):
        """测试 retry_strategy 优先于 max_retries/retry_delay"""
        scheduler = Scheduler()
        strategy = RetryStrategy.fixed(max_retries=10, delay=100)
        
        @scheduler.cron(
            "0 8 * * *", 
            code="PRIORITY_TEST",
            max_retries=1,  # 会被忽略
            retry_delay=5,  # 会被忽略
            retry_strategy=strategy,
        )
        async def priority_task():
            pass
        
        job_info = scheduler._jobs["PRIORITY_TEST"]
        # retry_strategy 的值应该优先
        assert job_info["max_retries"] == 10
        assert job_info["retry_delay"] == 100
    
    def test_should_retry_with_strategy(self):
        """测试 _should_retry 使用 retry_strategy"""
        scheduler = Scheduler()
        
        # 创建忽略 ValueError 的策略
        strategy = RetryStrategy.fixed(
            max_retries=3,
            delay=10,
            ignore_on=[ValueError],
        )
        
        job_info = {
            "max_retries": 3,
            "retry_strategy": strategy,
        }
        
        # ValueError 应该不重试
        assert scheduler._should_retry(job_info, ValueError("test"), 1) == False
        
        # 其他异常应该重试
        assert scheduler._should_retry(job_info, RuntimeError("test"), 1) == True
        
        # 超过重试次数不重试
        assert scheduler._should_retry(job_info, RuntimeError("test"), 3) == False
    
    def test_should_retry_without_strategy(self):
        """测试 _should_retry 不使用 retry_strategy（简单计数）"""
        scheduler = Scheduler()
        
        job_info = {
            "max_retries": 3,
            "retry_strategy": None,
        }
        
        # 在最大重试次数内应该重试
        assert scheduler._should_retry(job_info, ValueError("test"), 1) == True
        assert scheduler._should_retry(job_info, ValueError("test"), 2) == True
        assert scheduler._should_retry(job_info, ValueError("test"), 3) == True
        
        # 超过最大重试次数不重试
        assert scheduler._should_retry(job_info, ValueError("test"), 4) == False


class TestRetryStrategyDelayCalculation:
    """重试策略延迟计算测试"""
    
    def test_fixed_delay(self):
        """测试固定延迟"""
        strategy = RetryStrategy.fixed(max_retries=3, delay=60)
        
        assert strategy.get_delay(1) == 60
        assert strategy.get_delay(2) == 60
        assert strategy.get_delay(3) == 60
    
    def test_exponential_delay(self):
        """测试指数退避"""
        strategy = RetryStrategy.exponential(
            max_retries=5,
            base_delay=10,
            max_delay=300,
            backoff_factor=2.0,
            jitter=False,
        )
        
        assert strategy.get_delay(1) == 10
        assert strategy.get_delay(2) == 20
        assert strategy.get_delay(3) == 40
        assert strategy.get_delay(4) == 80
        assert strategy.get_delay(5) == 160
        assert strategy.get_delay(6) == 300  # 受 max_delay 限制
    
    def test_linear_delay(self):
        """测试线性递增"""
        strategy = RetryStrategy.linear(
            max_retries=5,
            initial_delay=10,
            increment=10,
        )
        
        assert strategy.get_delay(1) == 10
        assert strategy.get_delay(2) == 20
        assert strategy.get_delay(3) == 30
    
    def test_custom_delay(self):
        """测试自定义延迟函数"""
        strategy = RetryStrategy.custom(
            max_retries=3,
            delay_func=lambda attempt: attempt * 30,
        )
        
        assert strategy.get_delay(1) == 30
        assert strategy.get_delay(2) == 60
        assert strategy.get_delay(3) == 90


class TestRetryStrategyShouldRetry:
    """重试策略判断测试"""
    
    def test_should_retry_within_limit(self):
        """测试在重试次数内"""
        strategy = RetryStrategy.fixed(max_retries=3)
        
        assert strategy.should_retry(ValueError(), 1) == True
        assert strategy.should_retry(ValueError(), 2) == True
        assert strategy.should_retry(ValueError(), 3) == False
    
    def test_should_retry_on_specific_exception(self):
        """测试只对特定异常重试"""
        strategy = RetryStrategy.fixed(
            max_retries=3,
            retry_on=[ConnectionError, TimeoutError],
        )
        
        assert strategy.should_retry(ConnectionError(), 1) == True
        assert strategy.should_retry(TimeoutError(), 1) == True
        assert strategy.should_retry(ValueError(), 1) == False
    
    def test_should_not_retry_on_ignored_exception(self):
        """测试忽略特定异常不重试"""
        strategy = RetryStrategy.fixed(
            max_retries=3,
            ignore_on=[ValueError, KeyError],
        )
        
        assert strategy.should_retry(ValueError(), 1) == False
        assert strategy.should_retry(KeyError(), 1) == False
        assert strategy.should_retry(RuntimeError(), 1) == True
