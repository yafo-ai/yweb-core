"""ORM模块

提供完整的ORM解决方案：
- CoreModel: 核心模型基类，包含ID、时间戳、版本控制、CRUD、分页等
- BaseModel: 业务模型基类，继承CoreModel，添加name/code/note/caption等常用字段
- DTO: 数据传输对象基类
- BaseSchemas: Pydantic Schema基类
- 数据库会话管理
- 异步安全检测（防止 async 上下文中阻塞事件循环）
- 软删除扩展
- 树形结构扩展

使用示例:
    from yweb.orm import BaseModel,  get_db, activate_soft_delete_hook, init_versioning
    
    # 初始化版本化（必须在定义模型之前）
    init_versioning()
    
    # 激活软删除钩子
    activate_soft_delete_hook()
    
    # 定义模型
    class User(BaseModel):
        __tablename__ = 'user'
        email = Column(String(255))
    
    # 在路由中使用（纯 DB 操作推荐 def 路由）
    @app.get("/users")
    def get_users(db: Session = Depends(get_db)):
        return User.query.all()
    
    # 混合 async I/O 时使用 async_db_call()
    from yweb.orm import async_db_call
    
    @app.get("/users")
    async def get_users():
        users = await async_db_call(User.get_all)
        extra = await some_async_call()
        return {"users": users, "extra": extra}

异步安全:
    ORM 基于同步 Session，在 async def 中直接调用会阻塞事件循环。
    框架内置检测机制，会抛出 SynchronousOnlyOperation 异常并给出修复指引。
    通过环境变量 YWEB_ASYNC_SAFETY 控制行为：error（默认）/ warn / off。
"""

from .base_dto import DTO
from .base_schemas import (
    BaseSchemas,
    PaginationField,
    PaginationTmpField,
    Page,
    DateTimeStr,
    format_datetime_to_string,
)
from .id_model import IdModel, Base
from .base_model import CoreModel, BaseModel
from .core_model import PKType  # 主键类型别名
from .db_session import (
    # 管理器单例
    db_manager,
    # 公开 API
    init_database,
    get_engine,
    get_db,
    on_request_end,
    db_session_scope,
    with_db_session,
    # 异步支持
    async_db_call,
    run_db,  # [DEPRECATED] alias of async_db_call
)

# 异步安全检测
from .async_safety import (
    SynchronousOnlyOperation,
    check_async_safety,
    allow_sync,
)

# 软删除扩展
from .orm_extensions import (
    IgnoredTable,
    SoftDeleteRewriter,
    activate_soft_delete_hook,
    deactivate_soft_delete_hook,
    is_soft_delete_active,
    generate_soft_delete_mixin_class,
    SimpleSoftDeleteMixin,
    # 级联软删除
    CascadeSoftDeleteManager,
    configure_cascade_soft_delete,
    get_cascade_manager,
)

# Django 风格关系字段（推荐）
from . import fields
from .fields import (
    # 字段类型
    OneToOne,
    ManyToOne,
    ManyToMany,
    OwnsOne,
    # 类型标记（用于 IDE 提示）
    HasMany,
    HasOne,
    # on_delete 常量
    OnDelete,
    DELETE,
    SET_NULL,
    PROTECT,
    UNLINK,
    DO_NOTHING,
)

# 值对象类型（OwnsOne 配套）
from .owned_types import (
    OwnedType,
    owned_field,
    OwnedMeta,
)

# 版本历史记录
from .history.history_helper import (
    init_versioning,
    is_versioning_initialized,
    get_version_class,
    get_history,
    get_history_count,
    get_history_diff,
    get_field_text_diff,
    restore_to_version,
)

# 当前用户追踪（审计功能）
from .history.current_user import (
    CurrentUserPlugin,
    set_user,
    get_user_id,
    clear_user,
)

# 事务管理
from .transaction import (
    # 状态
    TransactionState,

    # 异常
    TransactionError,
    TransactionNotActiveError,
    TransactionAlreadyCommittedError,
    TransactionAlreadyRolledBackError,
    SavepointError,
    SavepointNotFoundError,
    HookExecutionError,
    PropagationError,

    # 传播行为
    TransactionPropagation,

    # 钩子
    TransactionHookType,
    TransactionHook,
    TransactionHooks,

    # 上下文
    TransactionContext,
    SavepointContext,

    # 管理器
    TransactionManager,
    GlobalHooksRegistry,
    transaction_manager,
    get_current_transaction,

    # 重试装饰器
    transaction_with_retry,
)

# 主键策略配置
from .primary_key_config import (
    IdType,
    PrimaryKeyConfig,
    configure_primary_key,
    get_primary_key_config,
)

from .primary_key_generators import (
    generate_uuid,
    generate_short_uuid,
    generate_snowflake_id,
    SnowflakeIDGenerator,
    PrimaryKeyGenerator,
)

# 树形结构扩展
from .tree import (
    TreeMixin,
    TreeFieldsMixin,
    TreeFieldsWithParentMixin,
    build_tree_list,
    flatten_tree,
    find_node_in_tree,
    get_node_path,
    validate_no_circular_reference,
    calculate_tree_depth,
    filter_tree,
)

# 排序管理扩展
from .sortable import (
    SortFieldMixin,
    SortableMixin,
)

# 状态机扩展
from .statemachine import (
    StateFieldMixin,
    IntStateFieldMixin,
    StateMachineMixin,
    AbstractStateHistory,
    StateHistoryMixin,
    # 异常
    StateMachineError,
    InvalidStateError,
    InvalidTransitionError,
    TransitionGuardError,
    TransitionBlockedError,
    TransitionCallbackError,
)

# 标签系统扩展
from .taggable import (
    AbstractTag,
    AbstractTagRelation,
    TaggableMixin,
)

__all__ = [
    # DTO
    "DTO",
    
    # Schemas
    "BaseSchemas",
    "PaginationField",
    "PaginationTmpField",
    "Page",
    "DateTimeStr",
    "format_datetime_to_string",
    
    # Model Base Classes
    "Base",      # SQLAlchemy 声明基类
    "IdModel",   # ID模型基类（仅包含主键功能）
    "CoreModel", # 核心模型基类（ID + 时间戳 + CRUD）
    "BaseModel", # 业务模型基类（CoreModel + 常用业务字段）
    "PKType",    # 主键类型别名（Union[int, str]）
    
    # Database Session
    "db_manager",  # 管理器单例
    "init_database",
    "get_engine",
    "get_db",
    "on_request_end",
    "db_session_scope",
    "with_db_session",
    
    # Async Support
    "async_db_call",
    "run_db",  # [DEPRECATED] alias of async_db_call
    "SynchronousOnlyOperation",
    "check_async_safety",
    "allow_sync",
    
    # Soft Delete Extensions
    "IgnoredTable",
    "SoftDeleteRewriter",
    "activate_soft_delete_hook",
    "deactivate_soft_delete_hook",
    "is_soft_delete_active",
    "generate_soft_delete_mixin_class",
    "SimpleSoftDeleteMixin",
    # Cascade Soft Delete
    "CascadeSoftDeleteManager",
    "configure_cascade_soft_delete",
    "get_cascade_manager",
    
    # Django 风格关系字段（推荐）
    "fields",
    "OneToOne",
    "ManyToOne",
    "ManyToMany",
    "OwnsOne",
    # 类型标记（用于 IDE 提示）
    "HasMany",
    "HasOne",
    # on_delete 常量
    "OnDelete",
    "DELETE",
    "SET_NULL",
    "PROTECT",
    "UNLINK",
    "DO_NOTHING",
    # 值对象类型（OwnsOne 配套）
    "OwnedType",
    "owned_field",
    "OwnedMeta",
    
    # Version History
    "init_versioning",
    "is_versioning_initialized",
    "get_version_class",
    "get_history",
    "get_history_count",
    "get_history_diff",
    "get_field_text_diff",
    "restore_to_version",
    
    # Current User Tracking (Audit) - Session 方式
    "CurrentUserPlugin",
    "set_user",
    "get_user_id",
    "clear_user",
    
    # Transaction Management
    "TransactionState",
    "TransactionError",
    "TransactionNotActiveError",
    "TransactionAlreadyCommittedError",
    "TransactionAlreadyRolledBackError",
    "SavepointError",
    "SavepointNotFoundError",
    "HookExecutionError",
    "PropagationError",
    "TransactionPropagation",
    "TransactionHookType",
    "TransactionHook",
    "TransactionHooks",
    "TransactionContext",
    "SavepointContext",
    "TransactionManager",
    "GlobalHooksRegistry",
    "transaction_manager",
    "get_current_transaction",
    "transaction_with_retry",

    # Primary Key Strategy
    "IdType",
    "PrimaryKeyConfig",
    "configure_primary_key",
    "get_primary_key_config",
    "generate_uuid",
    "generate_short_uuid",
    "generate_snowflake_id",
    "SnowflakeIDGenerator",
    "PrimaryKeyGenerator",
    
    # Tree Structure Extensions
    "TreeMixin",
    "TreeFieldsMixin",
    "TreeFieldsWithParentMixin",
    "build_tree_list",
    "flatten_tree",
    "find_node_in_tree",
    "get_node_path",
    "validate_no_circular_reference",
    "calculate_tree_depth",
    "filter_tree",
    
    # Sortable Extensions
    "SortFieldMixin",
    "SortableMixin",
    
    # State Machine Extensions
    "StateFieldMixin",
    "IntStateFieldMixin",
    "StateMachineMixin",
    "AbstractStateHistory",
    "StateHistoryMixin",
    "StateMachineError",
    "InvalidStateError",
    "InvalidTransitionError",
    "TransitionGuardError",
    "TransitionBlockedError",
    "TransitionCallbackError",
    
    # Taggable Extensions
    "AbstractTag",
    "AbstractTagRelation",
    "TaggableMixin",
]

