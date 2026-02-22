"""
YWeb - FastAPI基础类库

提供响应封装、中间件、ORM、认证、日志等基础功能
"""

from .version import __version__, __author__, __description__

# 导出响应模块
from .response import (
    # 响应快捷类（推荐）
    Resp,
    # 响应函数（高级用法）
    OK,
    BadRequest,
    Unauthorized,
    Forbidden,
    NotFound,
    InternalServerError,
    Conflict,
    TooManyRequests,
    Warning,
    Info,
    # 泛型响应模型
    PageData,
    PageResponse,
    ItemResponse,
    OkResponse,
    # 动态模型生成工具
    create_response_model,
    create_item_model,
    create_page_model,
)

# 导出中间件
from .middleware import (
    RequestLoggingMiddleware,
    RequestIDMiddleware,
    PerformanceMonitoringMiddleware,
    get_request_id,
)

# 导出ORM基类
from .orm import (
    DTO,
    BaseSchemas,
    PaginationField,
    PaginationTmpField,
    Page,
    DateTimeStr,
    BaseModel,
    init_database,
    get_engine,
    get_db,
    # 软删除扩展
    IgnoredTable,
    SoftDeleteRewriter,
    activate_soft_delete_hook,
    is_soft_delete_active,
    generate_soft_delete_mixin_class,
    SimpleSoftDeleteMixin,
)

# 导出认证模块
from .auth import (
    # JWT (原有)
    JWTManager,
    create_jwt_token,
    verify_jwt_token,
    TokenPayload,
    TokenResponse,
    TokenData,
    oauth2_scheme,
    AuthDependency,
    create_auth_dependency,
    RoleChecker,
    get_token_from_header,
    # 统一认证接口 (新增)
    AuthProvider,
    AuthManager,
    AuthType,
    UserIdentity,
    AuthResult,
    # API Key (新增)
    APIKeyManager,
    APIKeyData,
    APIKeyAuthProvider,
    # Session (新增)
    Session,
    SessionManager,
    SessionAuthProvider,
    set_session_cookie,
    clear_session_cookie,
    # LDAP (新增)
    LDAPManager,
    LDAPAuthProvider,
    LDAPConfig,
    LDAPType,
    # OIDC (新增)
    OIDCManager,
    OIDCAuthProvider,
)

# 导出日志模块
from .log import (
    setup_logger,
    api_logger,
    auth_logger,
    sql_logger,
    logger,
    get_logger,
    # 日志过滤钩子
    LogFilterHook,
    SensitiveDataFilterHook,
    LogFilterHookManager,
    log_filter_hook_manager,
    # 自定义日志处理器
    TimeAndSizeRotatingFileHandler,
    DailyRotatingFileHandler,
)

# 导出工具函数
from .utils import (
    hash_password,
    verify_password,
    EncryptionUtil,
    parse_file_size,
    format_file_size,
)

# 导出配置
from .config import (
    AppSettings,
    JWTSettings,
    DatabaseSettings,
    LoggingSettings,
    PaginationSettings,
    ConfigLoader,
    ConfigManager,
    load_yaml_config,
)

# 导出组织管理模块
from .organization import (
    # 枚举
    ExternalSource,
    EmployeeStatus,
    Gender,
    SyncStatus,
    # Mixin
    TreeMixin,
    # 抽象模型
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    AbstractEmployeeOrgRel,
    AbstractEmployeeDeptRel,
    AbstractDepartmentLeader,
    # 服务
    BaseOrganizationService,
    BaseSyncService,
    SyncResult,
)

# 导出异常处理模块
from .exceptions import (
    # 异常快捷创建类（推荐）
    Err,
    # 错误代码枚举
    ErrorCode,
    ErrorCodeType,
    # 业务异常
    BusinessException,
    AuthenticationException,
    AuthorizationException,
    ResourceNotFoundException,
    ResourceConflictException,
    ValidationException,
    ServiceUnavailableException,
    # 异常处理器
    register_exception_handlers,
    # 验证错误翻译器
    ValidationErrorTranslator,
)

# 导出验证约束模块（类似 .NET MVC 特性）
from .validators import (
    # 验证类型快捷类（推荐）
    Typed,
    # 约束函数
    StringLength,
    RegularExpression,
    Range,
    # 验证类型（高级用法）
    Phone,
    Email,
    Url,
    IdCard,
    CreditCard,
    # 可选验证类型
    OptionalPhone,
    OptionalEmail,
    OptionalUrl,
    OptionalIdCard,
)

# 导出定时任务模块
from .scheduler import (
    # 核心类（推荐）
    Scheduler,
    JobBuilder,
    # 工厂函数（推荐）
    create_scheduler_models,
    setup_scheduler,
    SchedulerModels,
    # 触发器
    cron,
    interval,
    once,
    # 任务基类
    Job,
    HttpJob,
    # 重试策略
    RetryStrategy,
    # 执行上下文
    JobContext,
    # 抽象模型（高级用法）
    AbstractSchedulerJob,
    AbstractSchedulerJobHistory,
    AbstractSchedulerJobStats,
)

# 导出缓存模块
from .cache import (
    # 装饰器（推荐）
    cached,
    memory_cache,
    redis_cache,
    # 自动失效（推荐）
    cache_invalidator,
    no_auto_invalidation,
    # 类型
    CachedFunction,
    CacheInvalidator,
    # 后端（高级用法）
    CacheBackend,
    MemoryBackend,
    RedisBackend,
    CacheStats,
)

__all__ = [
    # 版本信息
    "__version__",
    "__author__",
    "__description__",
    
    # Response - 推荐使用
    "Resp",                     # 响应快捷类：Resp.OK, Resp.NotFound 等
    # Response - 高级用法
    "OK",
    "BadRequest",
    "Unauthorized",
    "Forbidden",
    "NotFound",
    "InternalServerError",
    "Conflict",
    "TooManyRequests",
    "Warning",
    "Info",
    # 泛型响应模型
    "PageData",
    "PageResponse",
    "ItemResponse",
    "OperationResponse",
    # 动态模型生成工具
    "create_response_model",
    "create_item_model",
    "create_page_model",
    
    # Middleware
    "RequestLoggingMiddleware",
    "RequestIDMiddleware",
    "PerformanceMonitoringMiddleware",
    "get_request_id",
    
    # ORM
    "DTO",
    "BaseSchemas",
    "PaginationField",
    "PaginationTmpField",
    "Page",
    "DateTimeStr",
    "BaseModel",
    "init_database",
    "get_engine",
    "get_db",
    # Soft Delete
    "IgnoredTable",
    "SoftDeleteRewriter",
    "activate_soft_delete_hook",
    "deactivate_soft_delete_hook",
    "is_soft_delete_active",
    "generate_soft_delete_mixin_class",
    "SimpleSoftDeleteMixin",
    
    # Auth - JWT (原有)
    "JWTManager",
    "create_jwt_token",
    "verify_jwt_token",
    "TokenPayload",
    "TokenResponse",
    "TokenData",
    "oauth2_scheme",
    "AuthDependency",
    "create_auth_dependency",
    "RoleChecker",
    "get_token_from_header",
    # Auth - 统一认证接口 (新增)
    "AuthProvider",
    "AuthManager",
    "AuthType",
    "UserIdentity",
    "AuthResult",
    # Auth - API Key (新增)
    "APIKeyManager",
    "APIKeyData",
    "APIKeyAuthProvider",
    # Auth - Session (新增)
    "Session",
    "SessionManager",
    "SessionAuthProvider",
    "set_session_cookie",
    "clear_session_cookie",
    # Auth - LDAP (新增)
    "LDAPManager",
    "LDAPAuthProvider",
    "LDAPConfig",
    "LDAPType",
    # Auth - OIDC (新增)
    "OIDCManager",
    "OIDCAuthProvider",
    
    # Log
    "setup_logger",
    "api_logger",
    "auth_logger",
    "sql_logger",
    "logger",
    "get_logger",
    "LogFilterHook",
    "SensitiveDataFilterHook",
    "LogFilterHookManager",
    "log_filter_hook_manager",
    "TimeAndSizeRotatingFileHandler",
    "DailyRotatingFileHandler",
    
    # Utils
    "hash_password",
    "verify_password",
    "EncryptionUtil",
    "parse_file_size",
    "format_file_size",
    
    # Config
    "AppSettings",
    "JWTSettings",
    "DatabaseSettings",
    "LoggingSettings",
    "PaginationSettings",
    "ConfigLoader",
    "ConfigManager",
    "load_yaml_config",
    
    # Organization
    "ExternalSource",
    "EmployeeStatus",
    "Gender",
    "SyncStatus",
    "TreeMixin",
    "AbstractOrganization",
    "AbstractDepartment",
    "AbstractEmployee",
    "AbstractEmployeeOrgRel",
    "AbstractEmployeeDeptRel",
    "AbstractDepartmentLeader",
    "BaseOrganizationService",
    "BaseSyncService",
    "SyncResult",

    # Exceptions - 推荐使用
    "Err",                          # 异常快捷创建：Err.auth(), Err.not_found() 等
    "ErrorCode",                    # 错误代码枚举
    "register_exception_handlers",  # 注册全局异常处理器
    # Exceptions - 高级用法（类型检查、自定义异常继承、单元测试）
    "ErrorCodeType",
    "BusinessException",
    "AuthenticationException",
    "AuthorizationException",
    "ResourceNotFoundException",
    "ResourceConflictException",
    "ValidationException",
    "ServiceUnavailableException",
    "ValidationErrorTranslator",
    
    # Validators - 推荐使用
    "Typed",                    # 验证类型快捷类：Typed.Phone, Typed.Email 等
    # Validators - 约束函数
    "StringLength",
    "RegularExpression",
    "Range",
    # Validators - 高级用法
    "Phone",
    "Email",
    "Url",
    "IdCard",
    "CreditCard",
    "OptionalPhone",
    "OptionalEmail",
    "OptionalUrl",
    
    # Scheduler - 定时任务
    "Scheduler",                    # 调度器
    "JobBuilder",                   # 链式配置构建器
    "create_scheduler_models",      # 工厂函数（推荐）
    "setup_scheduler",              # 一站式设置
    "SchedulerModels",              # 模型容器
    "Job",                          # 任务基类
    "HttpJob",                      # HTTP 任务基类
    "RetryStrategy",                # 重试策略
    "cron",                         # Cron 触发器
    "interval",                     # 间隔触发器
    "once",                         # 一次性触发器
    "JobContext",                   # 执行上下文
    "AbstractSchedulerJob",         # 抽象模型
    "AbstractSchedulerJobHistory",  # 抽象模型
    "AbstractSchedulerJobStats",    # 抽象模型
    "OptionalIdCard",
    
    # Cache - 缓存装饰器
    "cached",                       # 通用缓存装饰器（推荐）
    "memory_cache",                 # 内存缓存装饰器
    "redis_cache",                  # Redis 缓存装饰器
    # Cache - 自动失效
    "cache_invalidator",            # 缓存自动失效管理器（推荐）
    "no_auto_invalidation",         # 禁用自动失效上下文
    # Cache - 类型
    "CachedFunction",               # 缓存函数类型
    "CacheInvalidator",             # 失效管理器类型
    "CacheBackend",                 # 缓存后端基类
    "MemoryBackend",                # 内存后端
    "RedisBackend",                 # Redis 后端
    "CacheStats",                   # 缓存统计
]
