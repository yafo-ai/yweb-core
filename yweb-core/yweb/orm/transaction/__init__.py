"""事务管理模块

提供完整的事务管理功能：
- 嵌套事务（Savepoint）支持
- 事务钩子系统（before_commit, after_commit 等）
- 事务传播行为（REQUIRED, REQUIRES_NEW, NESTED 等）
- 提交抑制机制（事务上下文中自动忽略 commit=True）

使用示例:
    from yweb.orm import transaction_manager as tm
    
    # 方式1：上下文管理器
    with tm.transaction() as tx:
        user = User(username="tom")
        user.add()
        
        @tx.after_commit
        def on_committed(ctx):
            send_welcome_email(user)
    
    # 方式2：装饰器
    @tm.transactional()
    def create_user(data):
        user = User(**data)
        user.save()
        return user
    
    # 方式3：嵌套事务（Savepoint）
    with tm.transaction() as tx:
        order.add()
        
        with tx.savepoint("sp1") as sp:
            risky_operation()
            # 如果失败，只回滚到 sp1
"""

from .state import TransactionState
from .exceptions import (
    TransactionError,
    TransactionNotActiveError,
    TransactionAlreadyCommittedError,
    TransactionAlreadyRolledBackError,
    SavepointError,
    SavepointNotFoundError,
    HookExecutionError,
    PropagationError,
)
from .propagation import TransactionPropagation
from .hooks import (
    TransactionHookType,
    TransactionHook,
    TransactionHooks,
)
from .context import (
    TransactionContext,
    SavepointContext,
)
from .manager import (
    TransactionManager,
    GlobalHooksRegistry,
    transaction_manager,
    get_current_transaction,
)
from .retry import transaction_with_retry

__all__ = [
    # 状态
    "TransactionState",
    
    # 异常
    "TransactionError",
    "TransactionNotActiveError",
    "TransactionAlreadyCommittedError",
    "TransactionAlreadyRolledBackError",
    "SavepointError",
    "SavepointNotFoundError",
    "HookExecutionError",
    "PropagationError",
    
    # 传播行为
    "TransactionPropagation",
    
    # 钩子
    "TransactionHookType",
    "TransactionHook",
    "TransactionHooks",
    
    # 上下文
    "TransactionContext",
    "SavepointContext",
    
    # 管理器
    "TransactionManager",
    "GlobalHooksRegistry",
    "transaction_manager",
    "get_current_transaction",
    
    # 重试装饰器
    "transaction_with_retry",
]
