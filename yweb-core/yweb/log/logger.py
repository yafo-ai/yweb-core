"""
日志工具模块
提供简化的日志配置功能
"""

import inspect
import logging
import os
import time
from typing import Optional, Union, List, Any, Protocol, runtime_checkable

from .handlers import TimeAndSizeRotatingFileHandler, BufferedRotatingFileHandler


@runtime_checkable
class LoggingConfigProtocol(Protocol):
    """日志配置协议
    
    定义日志配置对象需要提供的属性。
    业务项目的 LoggingSettings 类应该实现这些属性。
    """
    level: str
    file_path: str
    file_backup_count: int
    file_encoding: str
    file_when: str
    file_interval: int
    
    @property
    def parsed_file_max_bytes(self) -> int: ...


@runtime_checkable  
class SQLLoggingConfigProtocol(Protocol):
    """SQL日志配置协议"""
    sql_log_enabled: bool
    sql_log_file_path: str
    sql_log_level: str
    sql_log_backup_count: int
    file_encoding: str
    file_when: str
    file_interval: int
    
    @property
    def parsed_sql_log_max_bytes(self) -> int: ...


def _parse_log_level(level_str: str) -> int:
    """解析日志级别字符串为整数
    
    Args:
        level_str: 日志级别字符串，如 "ERROR", "WARNING" 等
        
    Returns:
        int: 日志级别整数值
    """
    import logging
    return getattr(logging, level_str.upper(), logging.ERROR)


def _extract_file_handler_options(config: Any) -> dict:
    """从配置对象中提取文件处理器选项
    
    Args:
        config: 配置对象，需要有相关属性
        
    Returns:
        file_handler_options 字典
    """
    options = {
        "maxBytes": getattr(config, "parsed_file_max_bytes", 10*1024*1024),
        "backupCount": getattr(config, "file_backup_count", 5),
        "encoding": getattr(config, "file_encoding", "utf-8"),
        "when": getattr(config, "file_when", "midnight"),
        "interval": getattr(config, "file_interval", 1),
        "maxRetentionDays": getattr(config, "max_retention_days", 0),
        "maxTotalBytes": getattr(config, "parsed_max_total_size", 0),
    }
    
    # 写缓存配置
    options["bufferEnabled"] = getattr(config, "buffer_enabled", False)
    if options["bufferEnabled"]:
        options["bufferCapacity"] = getattr(config, "buffer_capacity", 100)
        options["flushInterval"] = getattr(config, "buffer_flush_interval", 5.0)
        flush_level_str = getattr(config, "buffer_flush_level", "ERROR")
        options["flushLevel"] = _parse_log_level(flush_level_str)
    
    return options


def _extract_sql_file_handler_options(config: Any) -> dict:
    """从配置对象中提取 SQL 日志文件处理器选项
    
    Args:
        config: 配置对象，需要有相关属性
        
    Returns:
        file_handler_options 字典
    """
    options = {
        "maxBytes": getattr(config, "parsed_sql_log_max_bytes", 50*1024*1024),
        "backupCount": getattr(config, "sql_log_backup_count", 10),
        "encoding": getattr(config, "file_encoding", "utf-8"),
        "when": getattr(config, "file_when", "midnight"),
        "interval": getattr(config, "file_interval", 1),
        "maxRetentionDays": getattr(config, "sql_log_max_retention_days", 0),
        "maxTotalBytes": getattr(config, "parsed_sql_log_max_total_size", 0),
    }
    
    # SQL 日志写缓存配置
    options["bufferEnabled"] = getattr(config, "sql_log_buffer_enabled", False)
    if options["bufferEnabled"]:
        options["bufferCapacity"] = getattr(config, "sql_log_buffer_capacity", 100)
        options["flushInterval"] = getattr(config, "sql_log_buffer_flush_interval", 5.0)
        options["flushLevel"] = logging.ERROR  # SQL 日志 ERROR 立即刷新
    
    return options


def _load_logging_config_from_file(config_path: str, base_dir: str = None) -> Any:
    """从配置文件加载日志配置
    
    Args:
        config_path: 配置文件路径
        base_dir: 基础目录，用于解析相对路径
        
    Returns:
        LoggingSettings 配置对象
    """
    from ..config import ConfigLoader, LoggingSettings
    
    # 加载 YAML 配置
    config_data = ConfigLoader.load(config_path, base_dir=base_dir)
    
    # 提取 logging 配置
    logging_data = config_data.get("logging", {})
    
    # 创建 LoggingSettings 对象
    return LoggingSettings(**logging_data)


def _setup_sql_logger_internal(config: Any) -> Optional[logging.Logger]:
    """内部函数：设置 SQL 日志器
    
    Args:
        config: 日志配置对象
        
    Returns:
        SQL 日志记录器
    """
    sql_format = "%(asctime)s - %(levelname)s - %(message)s"
    level = getattr(config, "sql_log_level", "DEBUG")
    log_file = getattr(config, "sql_log_file_path", None)
    file_handler_options = _extract_sql_file_handler_options(config)
    
    # 设置 SQLAlchemy engine 日志器
    _sql_logger = setup_logger(
        name="sqlalchemy.engine",
        level=level,
        log_file=log_file,
        log_format=sql_format,
        console=False,
        propagate=False,
        file_handler_options=file_handler_options
    )
    
    # 设置 SQLAlchemy pool 日志器
    setup_logger(
        name="sqlalchemy.pool",
        level=level,
        log_file=log_file,
        log_format=sql_format,
        console=False,
        propagate=False,
        file_handler_options=file_handler_options
    )
    
    return _sql_logger


class MicrosecondFormatter(logging.Formatter):
    """支持微秒精度的日志格式化器"""
    
    def formatTime(self, record, datefmt=None):
        ct = self.converter(record.created)
        if datefmt:
            s = time.strftime(datefmt, ct)
        else:
            s = time.strftime("%Y-%m-%d %H:%M:%S", ct)
        # 添加微秒部分（6位数）
        return "%s.%06d" % (s, (record.created - int(record.created)) * 1000000)


# 默认日志格式
DEFAULT_LOG_FORMAT = "%(asctime)s - %(levelname)s - %(name)s - %(filename)s:%(lineno)d - %(message)s"


def create_formatter(
    log_format: str = None,
    datefmt: str = "%Y-%m-%d %H:%M:%S",
    use_microseconds: bool = True
) -> logging.Formatter:
    """创建日志格式化器
    
    Args:
        log_format: 日志格式字符串
        datefmt: 时间格式
        use_microseconds: 是否使用微秒精度
        
    Returns:
        日志格式化器
    """
    fmt = log_format or DEFAULT_LOG_FORMAT
    if use_microseconds:
        return MicrosecondFormatter(fmt=fmt, datefmt=datefmt)
    return logging.Formatter(fmt, datefmt=datefmt)


def setup_logger(
    name: str = None,
    level: str = "INFO",
    log_file: str = None,
    log_format: str = None,
    console: bool = True,
    use_microseconds: bool = True,
    propagate: bool = True,
    file_handler_options: dict = None
) -> logging.Logger:
    """设置并返回配置好的日志记录器
    
    Args:
        name: 日志记录器名称，默认为root logger
        level: 日志级别，可选：DEBUG, INFO, WARNING, ERROR, CRITICAL
        log_file: 日志文件路径，如果不指定则不写入文件
        log_format: 日志格式，如果不指定则使用默认格式
        console: 是否输出到控制台
        use_microseconds: 是否使用微秒精度时间戳
        propagate: 是否传播到父日志器
        file_handler_options: 文件处理器选项（用于 TimeAndSizeRotatingFileHandler）
            - maxBytes: 文件最大大小
            - backupCount: 备份文件数量
            - encoding: 文件编码
            - when: 轮转时间点
            - interval: 轮转间隔
        
    Returns:
        配置好的日志记录器
        
    使用示例:
        from yweb.log import setup_logger
        
        # 创建简单日志记录器
        logger = setup_logger("my_app", level="DEBUG")
        
        # 创建带文件输出的日志记录器
        logger = setup_logger(
            "my_app",
            level="DEBUG",
            log_file="logs/app_{date}.log",
            file_handler_options={
                "maxBytes": 10*1024*1024,
                "backupCount": 5
            }
        )
    """
    # 获取或创建日志记录器
    _logger = logging.getLogger(name) if name else logging.getLogger()
    _logger.setLevel(getattr(logging, level.upper(), logging.INFO))
    _logger.propagate = propagate
    
    # 清除现有的处理器
    _logger.handlers.clear()
    
    # 创建格式化器
    formatter = create_formatter(log_format, use_microseconds=use_microseconds)
    
    # 添加控制台处理器
    if console:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        _logger.addHandler(console_handler)
    
    # 添加文件处理器
    if log_file:
        # 确保日志目录存在
        log_dir = os.path.dirname(log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
        
        # 根据是否提供 file_handler_options 决定使用哪种处理器
        if file_handler_options:
            # 提取公共参数
            common_params = {
                "filename": log_file,
                "maxBytes": file_handler_options.get("maxBytes", 10*1024*1024),
                "backupCount": file_handler_options.get("backupCount", 5),
                "encoding": file_handler_options.get("encoding", "utf-8"),
                "when": file_handler_options.get("when", "midnight"),
                "interval": file_handler_options.get("interval", 1),
                "maxRetentionDays": file_handler_options.get("maxRetentionDays", 0),
                "maxTotalBytes": file_handler_options.get("maxTotalBytes", 0),
            }
            
            # 根据配置选择使用普通还是带缓存的处理器
            if file_handler_options.get("bufferEnabled", False):
                file_handler = BufferedRotatingFileHandler(
                    **common_params,
                    bufferCapacity=file_handler_options.get("bufferCapacity", 100),
                    flushInterval=file_handler_options.get("flushInterval", 5.0),
                    flushLevel=file_handler_options.get("flushLevel", logging.ERROR)
                )
            else:
                file_handler = TimeAndSizeRotatingFileHandler(**common_params)
        else:
            file_handler = logging.FileHandler(log_file, encoding='utf-8')
        
        file_handler.setFormatter(formatter)
        _logger.addHandler(file_handler)
    
    return _logger


def setup_root_logger(
    level: str = "INFO",
    log_file: str = None,
    console: bool = True,
    use_microseconds: bool = True,
    file_handler_options: dict = None,
    config: Any = None,
    config_path: str = None,
    config_base_dir: str = None,
    setup_sql_logger: bool = True
) -> logging.Logger:
    """设置根日志记录器
    
    子日志器会自动继承根日志器的处理器配置。
    
    Args:
        level: 日志级别（如果提供 config/config_path 则忽略）
        log_file: 日志文件路径（如果提供 config/config_path 则忽略）
        console: 是否输出到控制台
        use_microseconds: 是否使用微秒精度
        file_handler_options: 文件处理器选项（如果提供 config/config_path 则忽略）
        config: 日志配置对象，提供后自动提取配置
        config_path: 配置文件路径（YAML），提供后自动加载配置
        config_base_dir: 配置文件基础目录，用于解析相对路径
        setup_sql_logger: 是否同时设置 SQL 日志器（默认 True）
        
    Returns:
        根日志记录器
        
    使用示例:
        # 方式1：传统参数方式
        logger = setup_root_logger(level="INFO", log_file="logs/app.log")
        
        # 方式2：配置对象方式
        logger = setup_root_logger(config=settings.logging, console=True)
        
        # 方式3：配置文件路径方式（最简洁，自动配置 SQL 日志）
        logger = setup_root_logger(config_path="config/settings.yaml")
    """
    # 优先使用 config_path 加载配置
    if config_path is not None:
        config = _load_logging_config_from_file(config_path, config_base_dir)
        # 从配置中读取 console 设置
        console = getattr(config, "enable_console", console)
    
    # 如果提供了 config，从中提取配置
    if config is not None:
        level = getattr(config, "level", level)
        log_file = getattr(config, "file_path", log_file)
        file_handler_options = _extract_file_handler_options(config)
        
        # 自动设置 SQL 日志器
        if setup_sql_logger and getattr(config, "sql_log_enabled", False):
            _setup_sql_logger_internal(config)
    
    return setup_logger(
        name=None,  # root logger
        level=level,
        log_file=log_file,
        console=console,
        use_microseconds=use_microseconds,
        propagate=False,
        file_handler_options=file_handler_options
    )


def setup_sql_logger(
    level: str = "DEBUG",
    log_file: str = None,
    console: bool = False,
    file_handler_options: dict = None,
    config: Any = None,
    config_path: str = None,
    config_base_dir: str = None
) -> Optional[logging.Logger]:
    """设置 SQLAlchemy SQL 日志记录器
    
    Args:
        level: 日志级别（如果提供 config/config_path 则忽略）
        log_file: SQL 日志文件路径（如果提供 config/config_path 则忽略）
        console: 是否输出到控制台
        file_handler_options: 文件处理器选项（如果提供 config/config_path 则忽略）
        config: 日志配置对象，提供后自动提取 SQL 日志相关配置
        config_path: 配置文件路径（YAML），提供后自动加载配置
        config_base_dir: 配置文件基础目录，用于解析相对路径
        
    Returns:
        SQL 日志记录器，如果 config.sql_log_enabled 为 False 则返回 None
        
    使用示例:
        # 方式1：传统参数方式
        sql_logger = setup_sql_logger(level="DEBUG", log_file="logs/sql.log")
        
        # 方式2：配置对象方式
        sql_logger = setup_sql_logger(config=settings.logging)
        
        # 方式3：配置文件路径方式（最简洁）
        sql_logger = setup_sql_logger(config_path="config/settings.yaml")
    """
    # 优先使用 config_path 加载配置
    if config_path is not None:
        config = _load_logging_config_from_file(config_path, config_base_dir)
    
    # 如果提供了 config，从中提取配置
    if config is not None:
        # 检查是否启用 SQL 日志
        if not getattr(config, "sql_log_enabled", True):
            return None
        level = getattr(config, "sql_log_level", level)
        log_file = getattr(config, "sql_log_file_path", log_file)
        file_handler_options = _extract_sql_file_handler_options(config)
    
    sql_format = "%(asctime)s - %(levelname)s - %(message)s"
    
    # 设置 SQLAlchemy engine 日志器
    sql_logger = setup_logger(
        name="sqlalchemy.engine",
        level=level,
        log_file=log_file,
        log_format=sql_format,
        console=console,
        propagate=False,  # 不传播到根日志器
        file_handler_options=file_handler_options
    )
    
    # 设置 SQLAlchemy pool 日志器
    pool_logger = setup_logger(
        name="sqlalchemy.pool",
        level=level,
        log_file=log_file,
        log_format=sql_format,
        console=console,
        propagate=False,
        file_handler_options=file_handler_options
    )
    
    return sql_logger


def get_logger(name: str = None) -> logging.Logger:
    """获取日志记录器，支持自动推断模块名
    
    无参数调用时，自动从调用栈获取模块的 __name__ 作为日志器名称。
    有参数调用时，若不以 'yweb.' 开头，自动添加 'yweb.' 前缀。
    
    Args:
        name: 日志记录器名称。
              - None: 自动使用调用模块的 __name__
              - 字符串: 使用指定名称（自动添加 yweb 前缀，如 "orm" -> "yweb.orm"）
        
    Returns:
        日志记录器实例
        
    使用示例:
        from yweb.log import get_logger
        
        # ====== 自动推断（推荐，零硬编码）======
        logger = get_logger()
        # 在 yweb/orm/db_session.py 中 -> "yweb.orm.db_session"
        # 在 yweb/middleware/auth.py 中 -> "yweb.middleware.auth"
        # 在 app/api/v1/users.py 中    -> "app.api.v1.users"
        
        # ====== 显式指定（自动添加 yweb 前缀）======
        logger = get_logger("orm")        # -> "yweb.orm"
        logger = get_logger("yweb.orm")   # -> "yweb.orm"（已有前缀则不重复）
        
        # ====== 不添加前缀 ======
        logger = get_logger("sqlalchemy.engine")  # -> "sqlalchemy.engine"（非 yweb 开头不添加前缀）
    """
    if name is None:
        # 从调用栈自动推断模块名
        frame = inspect.currentframe()
        if frame is not None and frame.f_back is not None:
            name = frame.f_back.f_globals.get('__name__', 'yweb')
        else:
            name = 'yweb'
    elif not name.startswith('yweb.') and name != 'yweb' and '.' not in name:
        # 简写时自动添加 yweb 前缀（如 "orm" -> "yweb.orm"）
        # 但如果包含点号（如 "sqlalchemy.engine"），则不添加前缀
        name = f"yweb.{name}"
    
    return logging.getLogger(name)


# ==================== 向后兼容层 ====================
# 保留旧变量名，让现有代码继续工作
# 新代码推荐直接使用 get_logger() 自动推断
api_logger = get_logger("api")
auth_logger = get_logger("auth")
sql_logger = get_logger("sql")
orm_logger = get_logger("orm")
transaction_logger = get_logger("yweb.orm.transaction")

# 通用日志记录器
logger = logging.getLogger("yweb")

