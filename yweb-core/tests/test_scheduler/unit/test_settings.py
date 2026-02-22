"""SchedulerSettings 配置测试

测试定时任务配置类。
"""

import pytest
import os

from yweb.config import SchedulerSettings


class TestSchedulerSettings:
    """SchedulerSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = SchedulerSettings()
        
        assert settings.enabled == True
        assert settings.timezone == "Asia/Shanghai"
        assert settings.store == "memory"
        assert settings.max_workers == 10
        assert settings.misfire_grace_time == 60
        assert settings.coalesce == True
        assert settings.distributed_lock == False
        assert settings.redis_url is None
        assert settings.lock_timeout == 300
        assert settings.enable_history == True
        assert settings.history_retention_days == 30
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = SchedulerSettings(
            enabled=False,
            timezone="UTC",
            store="orm",
            max_workers=20,
            misfire_grace_time=120,
        )
        
        assert settings.enabled == False
        assert settings.timezone == "UTC"
        assert settings.store == "orm"
        assert settings.max_workers == 20
        assert settings.misfire_grace_time == 120
    
    def test_distributed_settings(self):
        """测试分布式配置"""
        settings = SchedulerSettings(
            distributed_lock=True,
            redis_url="redis://localhost:6379/0",
            lock_timeout=600,
        )
        
        assert settings.distributed_lock == True
        assert settings.redis_url == "redis://localhost:6379/0"
        assert settings.lock_timeout == 600
    
    def test_history_settings(self):
        """测试历史记录配置"""
        settings = SchedulerSettings(
            enable_history=True,
            history_retention_days=60,
        )
        
        assert settings.enable_history == True
        assert settings.history_retention_days == 60
    
    def test_env_prefix(self):
        """测试环境变量前缀"""
        os.environ["YWEB_SCHEDULER_ENABLED"] = "false"
        os.environ["YWEB_SCHEDULER_TIMEZONE"] = "UTC"
        os.environ["YWEB_SCHEDULER_STORE"] = "orm"
        
        try:
            settings = SchedulerSettings()
            assert settings.enabled == False
            assert settings.timezone == "UTC"
            assert settings.store == "orm"
        finally:
            del os.environ["YWEB_SCHEDULER_ENABLED"]
            del os.environ["YWEB_SCHEDULER_TIMEZONE"]
            del os.environ["YWEB_SCHEDULER_STORE"]
    
    def test_store_memory(self):
        """测试内存存储配置"""
        settings = SchedulerSettings(store="memory")
        
        assert settings.store == "memory"
    
    def test_store_orm(self):
        """测试 ORM 存储配置"""
        settings = SchedulerSettings(store="orm")
        
        assert settings.store == "orm"
    
    def test_coalesce_false(self):
        """测试禁用合并执行"""
        settings = SchedulerSettings(coalesce=False)
        
        assert settings.coalesce == False
    
    def test_disable_history(self):
        """测试禁用历史记录"""
        settings = SchedulerSettings(enable_history=False)
        
        assert settings.enable_history == False
