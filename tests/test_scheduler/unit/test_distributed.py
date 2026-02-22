"""分布式锁测试

测试 Redis 分布式锁功能。
"""

import pytest
import asyncio

from yweb.scheduler.locks import (
    DistributedLock,
    MemoryLock,
    RedisDistributedLock,
    create_distributed_lock,
)


class TestMemoryLock:
    """内存锁测试"""
    
    @pytest.mark.asyncio
    async def test_acquire_and_release(self):
        """测试获取和释放锁"""
        lock = MemoryLock()
        
        # 获取锁
        result = await lock.acquire("test_key", timeout=60)
        assert result == True
        
        # 释放锁
        result = await lock.release("test_key")
        assert result == True
    
    @pytest.mark.asyncio
    async def test_lock_prevents_duplicate(self):
        """测试锁阻止重复获取"""
        lock = MemoryLock()
        
        # 第一次获取成功
        result1 = await lock.acquire("test_key", timeout=60)
        assert result1 == True
        
        # 第二次获取失败
        result2 = await lock.acquire("test_key", timeout=60)
        assert result2 == False
        
        # 释放后可以再次获取
        await lock.release("test_key")
        result3 = await lock.acquire("test_key", timeout=60)
        assert result3 == True
    
    @pytest.mark.asyncio
    async def test_extend_lock(self):
        """测试延长锁时间"""
        lock = MemoryLock()
        
        await lock.acquire("test_key", timeout=60)
        result = await lock.extend("test_key", timeout=120)
        
        assert result == True
    
    @pytest.mark.asyncio
    async def test_extend_nonexistent_lock(self):
        """测试延长不存在的锁"""
        lock = MemoryLock()
        
        result = await lock.extend("nonexistent", timeout=60)
        assert result == False
    
    @pytest.mark.asyncio
    async def test_release_nonexistent_lock(self):
        """测试释放不存在的锁"""
        lock = MemoryLock()
        
        result = await lock.release("nonexistent")
        assert result == False


class TestCreateDistributedLock:
    """创建分布式锁测试"""
    
    def test_create_memory_lock(self):
        """测试创建内存锁"""
        lock = create_distributed_lock()
        
        assert isinstance(lock, MemoryLock)
    
    def test_create_redis_lock(self):
        """测试创建 Redis 锁"""
        lock = create_distributed_lock(
            redis_url="redis://localhost:6379/0"
        )
        
        assert isinstance(lock, RedisDistributedLock)
    
    def test_custom_prefix(self):
        """测试自定义前缀"""
        lock = create_distributed_lock(
            redis_url="redis://localhost:6379/0",
            prefix="custom:lock:"
        )
        
        assert lock.prefix == "custom:lock:"


class TestRedisDistributedLock:
    """Redis 分布式锁测试（不需要真实 Redis）"""
    
    def test_lock_value_format(self):
        """测试锁值格式"""
        lock = RedisDistributedLock("redis://localhost:6379/0")
        
        value = lock._get_lock_value()
        
        # 格式应该是 hostname:pid:timestamp
        parts = value.split(":")
        assert len(parts) == 3
    
    def test_lock_prefix(self):
        """测试锁前缀"""
        lock = RedisDistributedLock(
            "redis://localhost:6379/0",
            prefix="test:scheduler:lock:"
        )
        
        assert lock.prefix == "test:scheduler:lock:"
