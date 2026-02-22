"""配置类测试

测试各种配置类的功能
"""

import pytest
import os

from yweb.config import (
    AppSettings,
    JWTSettings,
    DatabaseSettings,
    LoggingSettings,
    MiddlewareSettings,
    PaginationSettings,
    RedisSettings,
)


class TestAppSettings:
    """AppSettings 测试"""
    
    def test_default_values(self):
        """测试默认嵌套配置值"""
        settings = AppSettings()
        
        assert isinstance(settings.jwt, JWTSettings)
        assert isinstance(settings.database, DatabaseSettings)
        assert isinstance(settings.logging, LoggingSettings)
        assert isinstance(settings.middleware, MiddlewareSettings)
        assert isinstance(settings.pagination, PaginationSettings)
        assert isinstance(settings.redis, RedisSettings)
        # 覆盖聚合类中的其他关键子配置，避免仅检查部分字段
        assert settings.scheduler is not None
        assert settings.storage is not None
    
    def test_nested_access(self):
        """测试嵌套属性访问"""
        settings = AppSettings()
        
        assert settings.jwt.algorithm == "HS256"
        assert settings.jwt.access_token_expire_minutes == 30
        assert settings.pagination.default_page_size == 10
        assert settings.pagination.max_page_size == 1000
    
    def test_custom_settings(self):
        """测试继承自定义配置"""
        from pydantic import Field
        
        class MySettings(AppSettings):
            app_name: str = Field(default="My Custom App")
        
        settings = MySettings()
        
        assert settings.app_name == "My Custom App"
        assert isinstance(settings.jwt, JWTSettings)


class TestJWTSettings:
    """JWTSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = JWTSettings()
        
        assert settings.secret_key == "change-me-in-production"
        assert settings.algorithm == "HS256"
        assert settings.access_token_expire_minutes == 30
        assert settings.refresh_token_expire_days == 7
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = JWTSettings(
            secret_key="my-secret",
            algorithm="HS512",
            access_token_expire_minutes=60,
            refresh_token_expire_days=14
        )
        
        assert settings.secret_key == "my-secret"
        assert settings.algorithm == "HS512"
        assert settings.access_token_expire_minutes == 60
        assert settings.refresh_token_expire_days == 14


class TestDatabaseSettings:
    """DatabaseSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = DatabaseSettings()
        
        assert settings.url == ""
        assert settings.echo == False
        assert settings.pool_pre_ping == True
        assert settings.pool_size == 5
        assert settings.max_overflow == 10
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = DatabaseSettings(
            url="postgresql://user:pass@localhost/mydb",
            echo=True,
            pool_size=10,
            max_overflow=20
        )
        
        assert settings.url == "postgresql://user:pass@localhost/mydb"
        assert settings.echo == True
        assert settings.pool_size == 10
        assert settings.max_overflow == 20


class TestLoggingSettings:
    """LoggingSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = LoggingSettings()
        
        assert settings.level == "INFO"
        assert settings.file_max_bytes == "10MB"
        assert settings.file_backup_count == 30
        assert settings.enable_console == True
        assert settings.sql_log_enabled == False
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = LoggingSettings(
            level="DEBUG",
            file_path="logs/custom.log",
            sql_log_enabled=True
        )
        
        assert settings.level == "DEBUG"
        assert settings.file_path == "logs/custom.log"
        assert settings.sql_log_enabled == True

    def test_parsed_size_fields(self):
        """测试文件大小计算字段解析"""
        settings = LoggingSettings(
            file_max_bytes="2MB",
            sql_log_max_bytes="3MB",
            max_total_size="4MB",
            sql_log_max_total_size="5MB",
        )

        assert settings.parsed_file_max_bytes == 2 * 1024 * 1024
        assert settings.parsed_sql_log_max_bytes == 3 * 1024 * 1024
        assert settings.parsed_max_total_size == 4 * 1024 * 1024
        assert settings.parsed_sql_log_max_total_size == 5 * 1024 * 1024

    def test_invalid_size_raises_value_error_when_accessing_computed_field(self):
        """测试非法文件大小在访问计算字段时抛出异常"""
        settings = LoggingSettings(file_max_bytes="invalid-size")

        with pytest.raises(ValueError):
            _ = settings.parsed_file_max_bytes


class TestMiddlewareSettings:
    """MiddlewareSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = MiddlewareSettings()
        
        assert settings.request_log_max_body_size == "10KB"
        assert settings.slow_request_threshold == 1.0
        assert "/health" in settings.request_log_skip_paths
    
    def test_custom_skip_paths(self):
        """测试自定义跳过路径"""
        settings = MiddlewareSettings(
            request_log_skip_paths=["/api/upload", "/static"]
        )
        
        assert "/api/upload" in settings.request_log_skip_paths
        assert "/static" in settings.request_log_skip_paths

    def test_default_skip_paths_are_isolated_between_instances(self):
        """测试默认跳过路径在实例之间互不污染"""
        settings_a = MiddlewareSettings()
        settings_b = MiddlewareSettings()

        settings_a.request_log_skip_paths.append("/internal-only")

        assert "/internal-only" in settings_a.request_log_skip_paths
        assert "/internal-only" not in settings_b.request_log_skip_paths


class TestPaginationSettings:
    """PaginationSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = PaginationSettings()
        
        assert settings.max_page_size == 1000
        assert settings.default_page_size == 10
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = PaginationSettings(
            max_page_size=500,
            default_page_size=20
        )
        
        assert settings.max_page_size == 500
        assert settings.default_page_size == 20


class TestRedisSettings:
    """RedisSettings 测试"""
    
    def test_default_values(self):
        """测试默认值"""
        settings = RedisSettings()
        
        assert settings.url == ""
        assert settings.max_connections == 10
    
    def test_custom_values(self):
        """测试自定义值"""
        settings = RedisSettings(
            url="redis://localhost:6379/0",
            max_connections=20
        )
        
        assert settings.url == "redis://localhost:6379/0"
        assert settings.max_connections == 20

