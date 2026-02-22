"""配置模块

提供配置管理功能：
- AppSettings: 应用基础配置（推荐），支持 YAML + 环境变量
- 子配置类: JWTSettings, DatabaseSettings, LoggingSettings 等
- ConfigLoader: YAML 配置加载器
- ConfigManager: 配置管理器

快速开始:
    from yweb.config import AppSettings, load_yaml_config
    
    class Settings(AppSettings):
        app_name: str = "My App"
    
    settings = load_yaml_config("config/settings.yaml", Settings)

配置优先级: 环境变量 > YAML 文件 > 默认值
容器化部署时通过环境变量注入敏感配置即可，详见 AppSettings 文档。
"""

from .settings import (
    AppSettings,
    JWTSettings,
    DatabaseSettings,
    LoggingSettings,
    MiddlewareSettings,
    PaginationSettings,
    RedisSettings,
    SchedulerSettings,
    # 存储配置
    StorageSettings,
    LocalStorageConfig,
    MemoryStorageConfig,
    OSSStorageConfig,
    S3StorageConfig,
    SecureURLConfig,
)

from .loader import (
    ConfigLoader,
    ConfigManager,
    load_yaml_config,
    load_env_file,
    set_env_from_file,
    YAML_AVAILABLE,
)

__all__ = [
    # Settings Classes
    "AppSettings",
    "JWTSettings",
    "DatabaseSettings",
    "LoggingSettings",
    "MiddlewareSettings",
    "PaginationSettings",
    "RedisSettings",
    "SchedulerSettings",
    # Storage Settings
    "StorageSettings",
    "LocalStorageConfig",
    "MemoryStorageConfig",
    "OSSStorageConfig",
    "S3StorageConfig",
    "SecureURLConfig",
    
    # Config Loader
    "ConfigLoader",
    "ConfigManager",
    "load_yaml_config",
    "load_env_file",
    "set_env_from_file",
    "YAML_AVAILABLE",
]
