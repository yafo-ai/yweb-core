"""日志模块

提供完整的日志解决方案：
- 日志配置与管理
- 敏感数据过滤
- 时间+大小双重轮转的日志处理器

使用示例:
    from yweb.log import (
        setup_logger,
        api_logger,
        log_filter_hook_manager,
        TimeAndSizeRotatingFileHandler,
    )
    
    # 创建自定义日志记录器
    logger = setup_logger("my_app", level="DEBUG", log_file="logs/app.log")
    
    # 使用敏感数据过滤
    filtered_data = log_filter_hook_manager.apply_filters(log_data)
    
    # 使用高级日志处理器
    handler = TimeAndSizeRotatingFileHandler(
        filename="logs/app_{date}.log",
        maxBytes=10*1024*1024,
        backupCount=5
    )
"""

from .logger import (
    setup_logger,
    setup_root_logger,
    setup_sql_logger,
    create_formatter,
    MicrosecondFormatter,
    DEFAULT_LOG_FORMAT,
    api_logger,
    auth_logger,
    sql_logger,
    orm_logger,
    transaction_logger,
    logger,
    get_logger,
)

from .filter_hooks import (
    LogFilterHook,
    SensitiveDataFilterHook,
    LogFilterHookManager,
    log_filter_hook_manager,
    DEFAULT_SENSITIVE_PATTERNS,
    DEFAULT_SENSITIVE_PATHS,
)

from .handlers import (
    TimeAndSizeRotatingFileHandler,
    DailyRotatingFileHandler,
    BufferedRotatingFileHandler,
    BufferedDailyRotatingFileHandler,
)

__all__ = [
    # 日志工具
    "setup_logger",
    "setup_root_logger",
    "setup_sql_logger",
    "create_formatter",
    "MicrosecondFormatter",
    "DEFAULT_LOG_FORMAT",
    "api_logger",
    "auth_logger",
    "sql_logger",
    "orm_logger",
    "transaction_logger",
    "logger",
    "get_logger",
    
    # 日志过滤钩子
    "LogFilterHook",
    "SensitiveDataFilterHook",
    "LogFilterHookManager",
    "log_filter_hook_manager",
    "DEFAULT_SENSITIVE_PATTERNS",
    "DEFAULT_SENSITIVE_PATHS",
    
    # 自定义日志处理器
    "TimeAndSizeRotatingFileHandler",
    "DailyRotatingFileHandler",
    "BufferedRotatingFileHandler",
    "BufferedDailyRotatingFileHandler",
]

