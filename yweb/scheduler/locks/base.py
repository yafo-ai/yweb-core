"""分布式锁抽象基类

定义分布式锁的接口规范。
"""

from abc import ABC, abstractmethod
from typing import AsyncContextManager


class DistributedLock(ABC):
    """分布式锁基类
    
    定义分布式锁的标准接口，所有锁实现都应继承此类。
    """
    
    @abstractmethod
    async def acquire(self, key: str, timeout: int) -> bool:
        """获取锁
        
        Args:
            key: 锁的键名
            timeout: 锁超时时间（秒）
        
        Returns:
            是否成功获取锁
        """
        pass
    
    @abstractmethod
    async def release(self, key: str) -> bool:
        """释放锁
        
        Args:
            key: 锁的键名
        
        Returns:
            是否成功释放锁
        """
        pass
    
    @abstractmethod
    async def extend(self, key: str, timeout: int) -> bool:
        """延长锁的过期时间
        
        Args:
            key: 锁的键名
            timeout: 新的超时时间（秒）
        
        Returns:
            是否成功延长
        """
        pass
