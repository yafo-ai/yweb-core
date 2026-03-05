"""Redis 分布式锁

提供 Redis 分布式锁实现，防止多实例重复执行任务。

使用示例:
    from yweb.scheduler import Scheduler
    from yweb.config import SchedulerSettings
    
    # 启用分布式锁
    settings = SchedulerSettings(
        distributed_lock=True,
        redis_url="redis://localhost:6379/0",
        lock_timeout=300,
    )
    scheduler = Scheduler(settings=settings)
"""

import logging
import socket
import os
import time
from typing import Optional
from contextlib import asynccontextmanager

from .base import DistributedLock

logger = logging.getLogger(__name__)


class RedisDistributedLock(DistributedLock):
    """Redis 分布式锁
    
    使用 Redis SET NX 命令实现分布式锁。
    
    特性：
    - 原子性获取锁
    - 自动过期
    - 支持锁续期
    - 只有持有者能释放锁
    
    Attributes:
        redis_url: Redis 连接 URL
        prefix: 锁键名前缀
        _redis: Redis 客户端
        _lock_values: 当前持有的锁值
    """
    
    def __init__(
        self,
        redis_url: str,
        prefix: str = "yweb:scheduler:lock:",
    ):
        """初始化 Redis 分布式锁
        
        Args:
            redis_url: Redis 连接 URL
            prefix: 锁键名前缀
        """
        self.redis_url = redis_url
        self.prefix = prefix
        self._redis = None
        self._lock_values = {}  # key -> value
    
    async def _get_redis(self):
        """获取 Redis 客户端（延迟初始化）"""
        if self._redis is None:
            try:
                import redis.asyncio as redis
                self._redis = redis.from_url(self.redis_url)
            except ImportError:
                raise ImportError(
                    "redis package is required for distributed lock. "
                    "Install with: pip install redis"
                )
        return self._redis
    
    def _get_lock_value(self) -> str:
        """生成锁值（包含主机和进程信息）"""
        hostname = socket.gethostname()
        pid = os.getpid()
        timestamp = int(time.time() * 1000)
        return f"{hostname}:{pid}:{timestamp}"
    
    async def acquire(self, key: str, timeout: int) -> bool:
        """获取锁
        
        使用 SET NX EX 命令原子性地获取锁。
        
        Args:
            key: 锁的键名（会自动添加前缀）
            timeout: 锁超时时间（秒）
        
        Returns:
            是否成功获取锁
        """
        redis_client = await self._get_redis()
        full_key = f"{self.prefix}{key}"
        lock_value = self._get_lock_value()
        
        try:
            result = await redis_client.set(
                full_key,
                lock_value,
                nx=True,  # 只在键不存在时设置
                ex=timeout,  # 过期时间
            )
            
            if result:
                self._lock_values[key] = lock_value
                logger.debug(f"Acquired lock: {key}")
                return True
            else:
                logger.debug(f"Failed to acquire lock: {key} (already held)")
                return False
                
        except Exception as e:
            logger.error(f"Error acquiring lock {key}: {e}")
            return False
    
    async def release(self, key: str) -> bool:
        """释放锁
        
        使用 Lua 脚本原子性地检查并删除锁，确保只有持有者能释放。
        
        Args:
            key: 锁的键名
        
        Returns:
            是否成功释放锁
        """
        redis_client = await self._get_redis()
        full_key = f"{self.prefix}{key}"
        lock_value = self._lock_values.get(key)
        
        if not lock_value:
            logger.warning(f"Attempted to release unheld lock: {key}")
            return False
        
        # Lua 脚本：只有值匹配时才删除
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("del", KEYS[1])
        else
            return 0
        end
        """
        
        try:
            result = await redis_client.eval(lua_script, 1, full_key, lock_value)
            
            if result:
                del self._lock_values[key]
                logger.debug(f"Released lock: {key}")
                return True
            else:
                logger.warning(f"Failed to release lock: {key} (not held or expired)")
                return False
                
        except Exception as e:
            logger.error(f"Error releasing lock {key}: {e}")
            return False
    
    async def extend(self, key: str, timeout: int) -> bool:
        """延长锁的过期时间
        
        使用 Lua 脚本原子性地检查并更新过期时间。
        
        Args:
            key: 锁的键名
            timeout: 新的超时时间（秒）
        
        Returns:
            是否成功延长
        """
        redis_client = await self._get_redis()
        full_key = f"{self.prefix}{key}"
        lock_value = self._lock_values.get(key)
        
        if not lock_value:
            return False
        
        # Lua 脚本：只有值匹配时才延长
        lua_script = """
        if redis.call("get", KEYS[1]) == ARGV[1] then
            return redis.call("expire", KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        
        try:
            result = await redis_client.eval(
                lua_script, 1, full_key, lock_value, timeout
            )
            
            if result:
                logger.debug(f"Extended lock: {key} for {timeout}s")
                return True
            else:
                return False
                
        except Exception as e:
            logger.error(f"Error extending lock {key}: {e}")
            return False
    
    async def is_held(self, key: str) -> bool:
        """检查是否持有锁
        
        Args:
            key: 锁的键名
        
        Returns:
            是否持有该锁
        """
        redis_client = await self._get_redis()
        full_key = f"{self.prefix}{key}"
        lock_value = self._lock_values.get(key)
        
        if not lock_value:
            return False
        
        try:
            current_value = await redis_client.get(full_key)
            return current_value and current_value.decode() == lock_value
        except Exception:
            return False
    
    @asynccontextmanager
    async def lock(self, key: str, timeout: int = 300):
        """上下文管理器方式使用锁
        
        Args:
            key: 锁的键名
            timeout: 锁超时时间（秒）
        
        Yields:
            是否成功获取锁
        
        Examples:
            async with lock.lock("my_task", timeout=60) as acquired:
                if acquired:
                    # 执行任务
                    pass
        """
        acquired = await self.acquire(key, timeout)
        try:
            yield acquired
        finally:
            if acquired:
                await self.release(key)
    
    async def close(self):
        """关闭 Redis 连接"""
        if self._redis:
            await self._redis.close()
            self._redis = None


class MemoryLock(DistributedLock):
    """内存锁（用于单实例或测试）
    
    使用内存字典实现简单的锁，仅用于单实例场景。
    """
    
    def __init__(self):
        self._locks = {}  # key -> (value, expire_time)
    
    async def acquire(self, key: str, timeout: int) -> bool:
        now = time.time()
        
        # 检查是否已有锁且未过期
        if key in self._locks:
            _, expire_time = self._locks[key]
            if expire_time > now:
                return False
        
        # 获取锁
        self._locks[key] = (id(self), now + timeout)
        return True
    
    async def release(self, key: str) -> bool:
        if key in self._locks:
            del self._locks[key]
            return True
        return False
    
    async def extend(self, key: str, timeout: int) -> bool:
        if key in self._locks:
            value, _ = self._locks[key]
            self._locks[key] = (value, time.time() + timeout)
            return True
        return False


def create_distributed_lock(
    redis_url: Optional[str] = None,
    prefix: str = "yweb:scheduler:lock:",
) -> DistributedLock:
    """创建分布式锁实例
    
    Args:
        redis_url: Redis 连接 URL，为空则使用内存锁
        prefix: 锁键名前缀
    
    Returns:
        分布式锁实例
    """
    if redis_url:
        return RedisDistributedLock(redis_url, prefix)
    else:
        return MemoryLock()
