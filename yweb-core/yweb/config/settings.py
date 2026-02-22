"""
配置模块
提供基础库的默认配置，业务项目可以继承并覆盖
"""

from pydantic_settings import BaseSettings
from pydantic import Field, computed_field
from typing import Any, Dict, Set, List, Optional

from ..utils import parse_file_size


class JWTSettings(BaseSettings):
    """JWT 配置
    
    使用示例:
        from yweb.config import JWTSettings
        
        jwt_config = JWTSettings(
            secret_key="your-secret-key",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
            refresh_token_sliding_days=2,  # Refresh Token 剩余 2 天时自动续期
        )
    
    配置说明:
        - access_token_expire_minutes: Access Token 有效期，决定"Token 被盗后黑客最多能用多久"
        - refresh_token_expire_days: Refresh Token 基础有效期
        - refresh_token_sliding_days: 滑动过期阈值，当用 Refresh Token 换取新 Access Token 时，
                                      如果 Refresh Token 剩余时间少于此值，也会返回新的 Refresh Token
    """
    secret_key: str = Field(default="change-me-in-production", description="JWT 密钥")
    algorithm: str = Field(default="HS256", description="JWT 算法")
    access_token_expire_minutes: int = Field(default=30, description="访问令牌过期时间（分钟）")
    refresh_token_expire_days: int = Field(default=7, description="刷新令牌基础过期时间（天）")
    refresh_token_sliding_days: int = Field(default=2, description="Refresh Token 滑动过期阈值（天），剩余时间少于此值时返回新的 Refresh Token")
    
    class Config:
        env_prefix = "YWEB_JWT_"


class DatabaseSettings(BaseSettings):
    """数据库配置
    
    使用示例:
        from yweb.config import DatabaseSettings
        
        db_config = DatabaseSettings(
            url="postgresql://user:pass@localhost/mydb"
        )
    """
    url: str = Field(default="", description="数据库连接URL")
    echo: bool = Field(default=False, description="是否打印SQL语句")
    pool_pre_ping: bool = Field(default=True, description="连接前检查")
    pool_size: int = Field(default=5, description="连接池大小")
    max_overflow: int = Field(default=10, description="连接池最大溢出")
    pool_timeout: int = Field(default=30, description="连接超时（秒）")
    pool_recycle: int = Field(default=3600, description="连接回收时间（秒）")
    
    class Config:
        env_prefix = "YWEB_DB_"


class LoggingSettings(BaseSettings):
    """日志配置
    
    使用示例:
        from yweb.config import LoggingSettings
        
        log_config = LoggingSettings(
            level="DEBUG",
            file_path="logs/app.log",
            max_retention_days=30,    # 保留最近30天
            max_total_size="1GB",     # 总大小限制1GB
            buffer_enabled=True,      # 启用写缓存
            buffer_capacity=100,      # 缓存100条
            buffer_flush_interval=5.0 # 每5秒刷新
        )
        
        # 获取解析后的字节数
        max_bytes = log_config.parsed_file_max_bytes
    """
    level: str = Field(default="INFO", description="日志级别")
    file_path: str = Field(default="logs/app_{date}.log", description="日志文件路径")
    file_max_bytes: str = Field(default="10MB", description="单个日志文件最大大小")
    file_backup_count: int = Field(default=30, description="保留的备份文件数量（同一天内的序号备份）")
    file_encoding: str = Field(default="utf-8", description="文件编码")
    file_when: str = Field(default="midnight", description="轮转时间点")
    file_interval: int = Field(default=1, description="轮转间隔")
    enable_console: bool = Field(default=True, description="是否启用控制台输出")
    
    # 日志清理配置
    max_retention_days: int = Field(default=0, description="日志保留天数，0表示不限制")
    max_total_size: str = Field(default="0", description="日志文件总大小限制，0表示不限制，支持 KB/MB/GB 单位")
    
    # 写缓存配置（默认关闭）
    buffer_enabled: bool = Field(default=False, description="是否启用写缓存，启用后日志会先缓存再批量写入")
    buffer_capacity: int = Field(default=100, description="缓冲区容量（条数），达到后刷新")
    buffer_flush_interval: float = Field(default=5.0, description="缓冲区刷新间隔（秒）")
    buffer_flush_level: str = Field(default="ERROR", description="触发立即刷新的日志级别，ERROR及以上会立即落盘")
    
    # SQL 日志配置
    sql_log_enabled: bool = Field(default=False, description="是否启用SQL日志")
    sql_log_file_path: str = Field(default="logs/sql_{date}.log", description="SQL日志文件路径")
    sql_log_level: str = Field(default="DEBUG", description="SQL日志级别")
    sql_log_max_bytes: str = Field(default="50MB", description="SQL日志最大大小")
    sql_log_backup_count: int = Field(default=10, description="SQL日志备份数量")
    sql_log_max_retention_days: int = Field(default=0, description="SQL日志保留天数，0表示不限制")
    sql_log_max_total_size: str = Field(default="0", description="SQL日志总大小限制，0表示不限制")
    sql_log_buffer_enabled: bool = Field(default=False, description="SQL日志是否启用写缓存")
    sql_log_buffer_capacity: int = Field(default=100, description="SQL日志缓冲区容量")
    sql_log_buffer_flush_interval: float = Field(default=5.0, description="SQL日志缓冲区刷新间隔")
    
    @computed_field
    @property
    def parsed_file_max_bytes(self) -> int:
        """解析文件最大字节数字符串为整数"""
        return parse_file_size(self.file_max_bytes)
    
    @computed_field
    @property
    def parsed_sql_log_max_bytes(self) -> int:
        """解析 SQL 日志文件最大字节数字符串为整数"""
        return parse_file_size(self.sql_log_max_bytes)
    
    @computed_field
    @property
    def parsed_max_total_size(self) -> int:
        """解析日志总大小限制字符串为整数"""
        return parse_file_size(self.max_total_size)
    
    @computed_field
    @property
    def parsed_sql_log_max_total_size(self) -> int:
        """解析 SQL 日志总大小限制字符串为整数"""
        return parse_file_size(self.sql_log_max_total_size)
    
    class Config:
        env_prefix = "YWEB_LOG_"


class MiddlewareSettings(BaseSettings):
    """中间件配置
    
    使用示例:
        from yweb.config import MiddlewareSettings
        
        mw_config = MiddlewareSettings(
            request_log_max_body_size="100KB"
        )
        
        # 获取解析后的字节数
        max_bytes = mw_config.parsed_request_log_max_body_size
    """
    request_log_max_body_size: str = Field(default="10KB", description="请求体日志最大大小")
    request_log_skip_paths: List[str] = Field(
        default=["/health", "/metrics", "/docs", "/redoc", "/openapi.json"],
        description="跳过日志记录的路径"
    )
    slow_request_threshold: float = Field(default=1.0, description="慢请求阈值（秒）")
    
    @computed_field
    @property
    def parsed_request_log_max_body_size(self) -> int:
        """解析请求体日志最大大小字符串为整数"""
        return parse_file_size(self.request_log_max_body_size)
    
    class Config:
        env_prefix = "YWEB_MW_"


class PaginationSettings(BaseSettings):
    """分页配置
    
    使用示例:
        from yweb.config import PaginationSettings
        
        page_config = PaginationSettings(
            max_page_size=500
        )
    """
    max_page_size: int = Field(default=1000, description="最大页大小")
    default_page_size: int = Field(default=10, description="默认页大小")
    
    class Config:
        env_prefix = "YWEB_PAGE_"


class RedisSettings(BaseSettings):
    """Redis 配置
    
    使用示例:
        from yweb.config import RedisSettings
        
        redis_config = RedisSettings(
            url="redis://localhost:6379/0"
        )
    """
    url: str = Field(default="", description="Redis连接URL")
    max_connections: int = Field(default=10, description="最大连接数")
    
    class Config:
        env_prefix = "YWEB_REDIS_"


class SchedulerSettings(BaseSettings):
    """定时任务配置
    
    使用示例:
        from yweb.config import SchedulerSettings
        
        config = SchedulerSettings(
            store="orm",              # 使用数据库持久化
            timezone="Asia/Shanghai",
            enable_history=True,
        )
    
    环境变量:
        YWEB_SCHEDULER_ENABLED=true
        YWEB_SCHEDULER_STORE=orm
        YWEB_SCHEDULER_TIMEZONE=Asia/Shanghai
    """
    
    # 基础配置
    enabled: bool = Field(default=True, description="是否启用定时任务")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    
    # 存储配置
    store: str = Field(
        default="memory", 
        description="任务存储方式: memory | orm"
    )
    
    # 执行器配置
    max_workers: int = Field(default=10, description="最大并发执行数")
    
    # 容错配置
    misfire_grace_time: int = Field(
        default=60, 
        description="任务错过执行的宽限时间（秒），超过此时间的任务不再执行"
    )
    coalesce: bool = Field(
        default=True, 
        description="是否合并错过的多次执行为一次"
    )
    
    # 分布式配置（可选）
    distributed_lock: bool = Field(
        default=False, 
        description="是否启用分布式锁（需要 Redis）"
    )
    redis_url: Optional[str] = Field(
        default=None, 
        description="Redis URL，用于分布式锁"
    )
    lock_timeout: int = Field(
        default=300, 
        description="分布式锁超时时间（秒）"
    )
    
    # 监控配置
    enable_history: bool = Field(
        default=True, 
        description="是否记录执行历史"
    )
    history_retention_days: int = Field(
        default=30, 
        description="历史记录保留天数"
    )
    
    class Config:
        env_prefix = "YWEB_SCHEDULER_"


# ==================== 存储配置 ====================

class LocalStorageConfig(BaseSettings):
    """本地存储配置
    
    使用示例:
        local_config = LocalStorageConfig(
            base_path="/data/uploads",
            base_url="/static/uploads",
        )
    
    环境变量:
        YWEB_STORAGE_LOCAL_ENABLED=true
        YWEB_STORAGE_LOCAL_BASE_PATH=/data/uploads
    """
    enabled: bool = Field(default=True, description="是否启用")
    base_path: str = Field(default="./uploads", description="存储根目录")
    base_url: Optional[str] = Field(default=None, description="URL 前缀（用于生成访问链接）")
    create_dirs: bool = Field(default=True, description="目录不存在时自动创建")
    
    class Config:
        env_prefix = "YWEB_STORAGE_LOCAL_"


class MemoryStorageConfig(BaseSettings):
    """内存存储配置
    
    适用于缓存、测试等场景。
    
    环境变量:
        YWEB_STORAGE_MEMORY_ENABLED=true
        YWEB_STORAGE_MEMORY_MAX_SIZE=100MB
    """
    enabled: bool = Field(default=False, description="是否启用")
    max_size: str = Field(default="100MB", description="最大存储容量")
    max_files: int = Field(default=10000, description="最大文件数")
    auto_cleanup: bool = Field(default=True, description="超出容量时自动清理")
    
    @computed_field
    @property
    def parsed_max_size(self) -> int:
        """解析最大容量为字节数"""
        return parse_file_size(self.max_size)
    
    class Config:
        env_prefix = "YWEB_STORAGE_MEMORY_"


class OSSStorageConfig(BaseSettings):
    """阿里云 OSS 存储配置
    
    环境变量:
        YWEB_STORAGE_OSS_ENABLED=true
        YWEB_STORAGE_OSS_ACCESS_KEY_ID=xxx
        YWEB_STORAGE_OSS_ACCESS_KEY_SECRET=xxx
        YWEB_STORAGE_OSS_ENDPOINT=oss-cn-hangzhou.aliyuncs.com
        YWEB_STORAGE_OSS_BUCKET_NAME=my-bucket
    """
    enabled: bool = Field(default=False, description="是否启用")
    access_key_id: str = Field(default="", description="Access Key ID")
    access_key_secret: str = Field(default="", description="Access Key Secret")
    endpoint: str = Field(default="", description="OSS 端点")
    bucket_name: str = Field(default="", description="Bucket 名称")
    prefix: str = Field(default="", description="存储路径前缀")
    internal_endpoint: Optional[str] = Field(default=None, description="内网端点")
    
    class Config:
        env_prefix = "YWEB_STORAGE_OSS_"


class S3StorageConfig(BaseSettings):
    """AWS S3 / MinIO 存储配置
    
    环境变量:
        YWEB_STORAGE_S3_ENABLED=true
        YWEB_STORAGE_S3_ACCESS_KEY_ID=xxx
        YWEB_STORAGE_S3_SECRET_ACCESS_KEY=xxx
        YWEB_STORAGE_S3_BUCKET_NAME=my-bucket
        YWEB_STORAGE_S3_ENDPOINT_URL=http://localhost:9000  # MinIO
    """
    enabled: bool = Field(default=False, description="是否启用")
    access_key_id: str = Field(default="", description="Access Key ID")
    secret_access_key: str = Field(default="", description="Secret Access Key")
    bucket_name: str = Field(default="", description="Bucket 名称")
    region: str = Field(default="us-east-1", description="AWS 区域")
    endpoint_url: Optional[str] = Field(default=None, description="自定义端点（MinIO）")
    prefix: str = Field(default="", description="存储路径前缀")
    
    class Config:
        env_prefix = "YWEB_STORAGE_S3_"


class SecureURLConfig(BaseSettings):
    """安全 URL 配置
    
    用于生成临时访问链接。
    
    环境变量:
        YWEB_STORAGE_SECURE_SECRET_KEY=your-secret-key
        YWEB_STORAGE_SECURE_BASE_URL=/files
    """
    enabled: bool = Field(default=False, description="是否启用安全 URL")
    secret_key: str = Field(default="", description="签名密钥")
    base_url: str = Field(default="/files", description="URL 前缀")
    default_expires: int = Field(default=3600, description="默认过期时间（秒）")
    
    class Config:
        env_prefix = "YWEB_STORAGE_SECURE_"


class StorageSettings(BaseSettings):
    """存储模块配置
    
    聚合所有存储后端的配置。
    
    使用示例:
        from yweb.config import StorageSettings
        from yweb.storage import StorageManager
        
        # 方式1：从环境变量自动加载
        settings = StorageSettings()
        StorageManager.init_from_settings(settings)
        
        # 方式2：手动配置
        settings = StorageSettings(
            default="local",
            local=LocalStorageConfig(base_path="/data/uploads"),
            oss=OSSStorageConfig(enabled=True, bucket_name="my-bucket"),
        )
        
        # 方式3：从 YAML 加载
        config = ConfigLoader.load("config/settings.yaml")
        settings = StorageSettings(**config.get('storage', {}))
    
    YAML 配置示例:
        storage:
          default: local
          local:
            base_path: /data/uploads
            base_url: /static/uploads
          oss:
            enabled: true
            access_key_id: ${OSS_ACCESS_KEY_ID}
            access_key_secret: ${OSS_ACCESS_KEY_SECRET}
            endpoint: oss-cn-hangzhou.aliyuncs.com
            bucket_name: my-bucket
    
    环境变量:
        YWEB_STORAGE_DEFAULT=local
        YWEB_STORAGE_LOCAL_BASE_PATH=/data/uploads
        YWEB_STORAGE_OSS_ENABLED=true
    """
    
    # 默认后端名称
    default: str = Field(default="local", description="默认存储后端")
    
    # 各后端配置
    local: LocalStorageConfig = Field(default_factory=LocalStorageConfig)
    memory: MemoryStorageConfig = Field(default_factory=MemoryStorageConfig)
    oss: OSSStorageConfig = Field(default_factory=OSSStorageConfig)
    s3: S3StorageConfig = Field(default_factory=S3StorageConfig)
    
    # 安全 URL 配置
    secure_url: SecureURLConfig = Field(default_factory=SecureURLConfig)
    
    class Config:
        env_prefix = "YWEB_STORAGE_"
        env_nested_delimiter = "__"  # 支持 YWEB_STORAGE_OSS__BUCKET_NAME


class AppSettings(BaseSettings):
    """应用基础配置
    
    将各子配置类聚合为嵌套结构，业务项目继承后只需添加项目特有的配置项。
    同时支持 YAML 配置文件和环境变量两种方式，可混合使用。
    
    配置优先级（从高到低）:
        环境变量 > YAML 配置文件 > 代码中的默认值
    
    内置子配置及环境变量前缀:
        - database:  DatabaseSettings   (YWEB_DB_)
        - redis:     RedisSettings      (YWEB_REDIS_)
        - jwt:       JWTSettings        (YWEB_JWT_)
        - logging:   LoggingSettings    (YWEB_LOG_)
        - middleware: MiddlewareSettings (YWEB_MW_)
        - pagination: PaginationSettings (YWEB_PAGE_)
        - scheduler: SchedulerSettings  (YWEB_SCHEDULER_)
        - storage:   StorageSettings    (YWEB_STORAGE_)
    
    使用示例:
        from yweb.config import AppSettings, load_yaml_config
        
        class Settings(AppSettings):
            app_name: str = "My App"
        
        settings = load_yaml_config("config/settings.yaml", Settings)
    
    YAML 配置示例 (config/settings.yaml):
        database:
          url: "sqlite:///./app.db"
        jwt:
          secret_key: "dev-secret"
          access_token_expire_minutes: 30
        logging:
          level: "INFO"
        redis:
          url: "redis://localhost:6379/0"
    
    容器化 / 云原生部署:
        敏感配置通过环境变量注入，覆盖 YAML 中的值，无需修改配置文件。
        
        # docker-compose.yml
        environment:
          - YWEB_DB_URL=postgresql://user:pass@db:5432/mydb
          - YWEB_JWT_SECRET_KEY=production-secret
          - YWEB_REDIS_URL=redis://redis:6379/0
          - YWEB_LOG_LEVEL=WARNING
        
        # Kubernetes Secret
        env:
          - name: YWEB_JWT_SECRET_KEY
            valueFrom:
              secretKeyRef:
                name: app-secrets
                key: jwt-secret-key
    """
    database: DatabaseSettings = DatabaseSettings()
    redis: RedisSettings = RedisSettings()
    jwt: JWTSettings = JWTSettings()
    logging: LoggingSettings = LoggingSettings()
    middleware: MiddlewareSettings = MiddlewareSettings()
    pagination: PaginationSettings = PaginationSettings()
    scheduler: SchedulerSettings = SchedulerSettings()
    storage: StorageSettings = StorageSettings()
    
    # 可选功能配置（使用时在 settings.yaml 中添加对应段即可）
    ip_access: Optional[Dict[str, Any]] = Field(
        default=None,
        description="IP 访问控制配置（可选），详见 IPAccessMiddleware",
    )
