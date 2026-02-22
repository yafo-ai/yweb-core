"""事务重试装饰器

提供带重试机制的事务装饰器，用于处理死锁等可重试的异常
"""

import time
from functools import wraps
from typing import Callable, TypeVar, Tuple, Type

from sqlalchemy.exc import OperationalError

from yweb.log import get_logger

logger = get_logger("yweb.orm.transaction")

T = TypeVar('T')


def transaction_with_retry(
    max_retries: int = 3,
    retry_delay: float = 0.1,
    retry_on: Tuple[Type[Exception], ...] = (OperationalError,),
    backoff_multiplier: float = 2.0,
    max_delay: float = 10.0
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """带重试机制的事务装饰器
    
    当遇到指定的异常时，自动重试事务。支持指数退避策略。
    
    Args:
        max_retries: 最大重试次数（不包括首次尝试）
        retry_delay: 初始重试间隔（秒）
        retry_on: 需要重试的异常类型元组
        backoff_multiplier: 退避乘数（每次重试后延迟乘以此值）
        max_delay: 最大延迟时间（秒）
    
    Returns:
        装饰后的函数
    
    使用示例:
        from yweb.orm.transaction import transaction_with_retry
        from sqlalchemy.exc import OperationalError
        
        @transaction_with_retry(max_retries=3)
        def transfer_money(from_id: int, to_id: int, amount: float):
            from_account = Account.get(from_id)
            to_account = Account.get(to_id)
            
            if from_account.balance < amount:
                raise InsufficientFundsError("余额不足")
            
            from_account.balance -= amount
            to_account.balance += amount
            
            from_account.update()
            to_account.update()
        
        # 自定义重试异常
        @transaction_with_retry(
            max_retries=5,
            retry_on=(OperationalError, DeadlockError),
            backoff_multiplier=1.5
        )
        def batch_update(items):
            for item in items:
                item.process()
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        def wrapper(*args, **kwargs) -> T:
            from .manager import transaction_manager
            
            last_error = None
            current_delay = retry_delay
            
            for attempt in range(max_retries + 1):
                try:
                    with transaction_manager.transaction() as tx:
                        result = func(*args, **kwargs)
                        return result
                except retry_on as e:
                    last_error = e
                    
                    if attempt < max_retries:
                        # 计算下次延迟（带上限）
                        actual_delay = min(current_delay, max_delay)
                        
                        logger.warning(
                            f"事务执行失败 (尝试 {attempt + 1}/{max_retries + 1}), "
                            f"{actual_delay:.2f}s 后重试. "
                            f"异常: {type(e).__name__}: {e}"
                        )
                        
                        time.sleep(actual_delay)
                        current_delay *= backoff_multiplier
                    else:
                        logger.error(
                            f"事务重试 {max_retries} 次后仍失败. "
                            f"异常: {type(e).__name__}: {e}"
                        )
                        raise
            
            # 不应该到达这里，但为了类型安全
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected state in transaction_with_retry")
        
        @wraps(func)
        async def async_wrapper(*args, **kwargs) -> T:
            import asyncio
            from .manager import transaction_manager
            
            last_error = None
            current_delay = retry_delay
            
            for attempt in range(max_retries + 1):
                try:
                    with transaction_manager.transaction() as tx:
                        result = await func(*args, **kwargs)
                        return result
                except retry_on as e:
                    last_error = e
                    
                    if attempt < max_retries:
                        actual_delay = min(current_delay, max_delay)
                        
                        logger.warning(
                            f"异步事务执行失败 (尝试 {attempt + 1}/{max_retries + 1}), "
                            f"{actual_delay:.2f}s 后重试. "
                            f"异常: {type(e).__name__}: {e}"
                        )
                        
                        await asyncio.sleep(actual_delay)
                        current_delay *= backoff_multiplier
                    else:
                        logger.error(
                            f"异步事务重试 {max_retries} 次后仍失败. "
                            f"异常: {type(e).__name__}: {e}"
                        )
                        raise
            
            if last_error:
                raise last_error
            raise RuntimeError("Unexpected state in transaction_with_retry")
        
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return wrapper
    
    return decorator
