"""事务管理器

提供事务管理的统一入口
"""

from __future__ import annotations

import asyncio
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import (
    Dict, List, Callable, Any, Optional, TypeVar, Generator, TYPE_CHECKING
)

from sqlalchemy.orm import Session

from yweb.log import get_logger

from .state import TransactionState
from .propagation import TransactionPropagation
from .hooks import TransactionHook, TransactionHookType, TransactionHooks
from .context import TransactionContext
from .exceptions import PropagationError

if TYPE_CHECKING:
    pass

logger = get_logger("yweb.orm.transaction")

T = TypeVar('T')

# 当前事务上下文（线程/协程安全）
_current_transaction: ContextVar[Optional[TransactionContext]] = ContextVar(
    '_current_transaction', default=None
)


def get_current_transaction() -> Optional[TransactionContext]:
    """获取当前事务上下文
    
    Returns:
        当前的事务上下文，如果不在事务中则返回 None
    
    使用示例:
        tx = get_current_transaction()
        if tx and tx.is_active:
            # 在事务中
            pass
    """
    return _current_transaction.get()


class GlobalHooksRegistry:
    """全局钩子注册器
    
    提供装饰器方式注册全局钩子
    
    使用示例:
        @tm.global_hooks.before_commit
        def audit_log():
            logger.info("事务即将提交...")
    """
    
    def __init__(self, manager: 'TransactionManager'):
        self._manager = manager
    
    def before_begin(self, func: Callable) -> Callable:
        """注册全局 before_begin 钩子"""
        self._manager._global_hooks[TransactionHookType.BEFORE_BEGIN].append(func)
        return func
    
    def after_begin(self, func: Callable) -> Callable:
        """注册全局 after_begin 钩子"""
        self._manager._global_hooks[TransactionHookType.AFTER_BEGIN].append(func)
        return func
    
    def before_commit(self, func: Callable) -> Callable:
        """注册全局 before_commit 钩子"""
        self._manager._global_hooks[TransactionHookType.BEFORE_COMMIT].append(func)
        return func
    
    def after_commit(self, func: Callable) -> Callable:
        """注册全局 after_commit 钩子"""
        self._manager._global_hooks[TransactionHookType.AFTER_COMMIT].append(func)
        return func
    
    def before_rollback(self, func: Callable) -> Callable:
        """注册全局 before_rollback 钩子"""
        self._manager._global_hooks[TransactionHookType.BEFORE_ROLLBACK].append(func)
        return func
    
    def after_rollback(self, func: Callable) -> Callable:
        """注册全局 after_rollback 钩子"""
        self._manager._global_hooks[TransactionHookType.AFTER_ROLLBACK].append(func)
        return func
    
    def on_error(self, func: Callable) -> Callable:
        """注册全局错误处理钩子"""
        self._manager._global_hooks[TransactionHookType.ON_ERROR].append(func)
        return func


class TransactionManager:
    """事务管理器
    
    提供事务管理的统一入口，包括：
    - 获取/创建事务上下文
    - 事务装饰器
    - 全局钩子注册
    
    使用示例:
        from yweb.orm import transaction_manager as tm
        
        # 使用上下文管理器
        with tm.transaction() as tx:
            user.save()
            tx.after_commit(lambda ctx: print("已提交"))
        
        # 使用装饰器
        @tm.transactional()
        def create_order(data):
            order = Order(**data)
            order.save()
            return order
        
        # 嵌套事务
        @tm.transactional()
        def process_order(order_id):
            order = Order.get(order_id)
            
            @tm.transactional(propagation=TransactionPropagation.NESTED)
            def update_inventory():
                # 这是一个嵌套事务（savepoint）
                pass
            
            update_inventory()
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        # 全局钩子存储
        self._global_hooks: Dict[TransactionHookType, List[Callable]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        self._global_hook_objects: Dict[TransactionHookType, List[TransactionHook]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        
        # 全局钩子注册器
        self._global_hooks_registry = GlobalHooksRegistry(self)
        
        # 默认配置
        self._default_suppress_commit = True
        self._log_suppressed_commit = True
        
        self._initialized = True
    
    def get_session(self) -> Session:
        """获取数据库 session"""
        from ..db_session import db_manager
        return db_manager.get_session()
    
    @property
    def current_transaction(self) -> Optional[TransactionContext]:
        """获取当前事务上下文"""
        return _current_transaction.get()
    
    @property
    def global_hooks(self) -> GlobalHooksRegistry:
        """全局钩子注册器"""
        return self._global_hooks_registry
    
    def configure(
        self,
        suppress_commit_in_transaction: bool = None,
        log_suppressed_commit: bool = None
    ) -> None:
        """配置事务管理器
        
        Args:
            suppress_commit_in_transaction: 是否在事务中抑制 commit=True
            log_suppressed_commit: 抑制 commit 时是否输出日志
        """
        if suppress_commit_in_transaction is not None:
            self._default_suppress_commit = suppress_commit_in_transaction
        if log_suppressed_commit is not None:
            self._log_suppressed_commit = log_suppressed_commit
    
    @contextmanager
    def transaction(
        self,
        session: Session = None,
        propagation: TransactionPropagation = TransactionPropagation.REQUIRED,
        auto_commit: bool = True,
        read_only: bool = False,
        suppress_commit: bool = None
    ) -> Generator[TransactionContext, None, None]:
        """创建事务上下文
        
        Args:
            session: 数据库会话，不传则自动获取
            propagation: 事务传播行为
            auto_commit: 是否自动提交
            read_only: 是否只读事务（优化提示）
            suppress_commit: 是否抑制内部提交，None 则使用默认配置
        
        Yields:
            TransactionContext 对象
        
        使用示例:
            with tm.transaction() as tx:
                user = User(name="tom")
                user.add()
                
                @tx.after_commit
                def on_committed(ctx):
                    send_welcome_email(user)
        
        ⚠️ 嵌套事务异常处理注意事项:
            当使用嵌套事务（REQUIRED/MANDATORY/SUPPORTS 传播行为）时，
            如果在内层捕获异常后继续执行，session 状态可能不一致。
            
            错误示例（可能导致数据不一致）:
                with tm.transaction() as tx:
                    try:
                        with tm.transaction():  # 嵌套事务
                            risky_operation()   # 可能失败
                    except Exception:
                        pass  # ❌ 仅捕获不处理，session 状态可能已损坏
                    
                    other_operation()  # ⚠️ 可能操作不一致的数据
                # commit - 可能提交不一致的数据
            
            正确做法:
                with tm.transaction() as tx:
                    try:
                        with tm.transaction():
                            risky_operation()
                    except Exception:
                        tx.rollback()  # ✅ 主动回滚整个事务
                        raise          # ✅ 或重新抛出异常
            
            或者使用 savepoint 隔离风险操作:
                with tm.transaction() as tx:
                    with tx.savepoint():  # ✅ 使用保存点
                        risky_operation()
                    # 保存点自动处理异常和回滚
        """
        if session is None:
            session = self.get_session()
        
        if suppress_commit is None:
            suppress_commit = self._default_suppress_commit
        
        current = self.current_transaction
        
        # 处理事务传播
        if propagation == TransactionPropagation.REQUIRED:
            if current and current.is_active:
                # 加入现有事务
                # ⚠️ 注意：如果用户在内层捕获异常后继续执行，session 状态可能不一致
                # 正确做法：捕获异常后应该重新抛出或手动调用 tx.rollback()
                current._nesting_level += 1
                logger.debug(f"REQUIRED: 加入现有事务 (level={current._nesting_level})")
                try:
                    yield current
                finally:
                    if current._nesting_level > 0:
                        current._nesting_level -= 1
                return
        
        elif propagation == TransactionPropagation.REQUIRES_NEW:
            # 总是新建事务（通过 savepoint）
            if current and current.is_active:
                logger.debug("REQUIRES_NEW: 在现有事务中创建 savepoint")
                with current.savepoint() as sp:
                    yield current
                return
        
        elif propagation == TransactionPropagation.MANDATORY:
            if not current or not current.is_active:
                raise PropagationError("MANDATORY", "必须在事务中执行")
            # ⚠️ 注意：如果用户在内层捕获异常后继续执行，session 状态可能不一致
            current._nesting_level += 1
            logger.debug(f"MANDATORY: 加入现有事务 (level={current._nesting_level})")
            try:
                yield current
            finally:
                if current._nesting_level > 0:
                    current._nesting_level -= 1
            return
        
        elif propagation == TransactionPropagation.NEVER:
            if current and current.is_active:
                raise PropagationError("NEVER", "不能在事务中执行")
        
        elif propagation == TransactionPropagation.NESTED:
            if current and current.is_active:
                logger.debug("NESTED: 创建嵌套事务 (savepoint)")
                with current.savepoint() as sp:
                    yield current
                return
            else:
                raise PropagationError("NESTED", "NESTED 需要一个活跃的外层事务")
        
        elif propagation == TransactionPropagation.SUPPORTS:
            if current and current.is_active:
                # 加入现有事务
                # ⚠️ 注意：如果用户在内层捕获异常后继续执行，session 状态可能不一致
                current._nesting_level += 1
                try:
                    yield current
                finally:
                    if current._nesting_level > 0:
                        current._nesting_level -= 1
                return
            # 没有事务，以非事务方式执行
            # 创建一个不自动提交的上下文
            auto_commit = False
        
        elif propagation == TransactionPropagation.NOT_SUPPORTED:
            # 以非事务方式执行
            if current and current.is_active:
                logger.debug("NOT_SUPPORTED: 挂起当前事务")
            auto_commit = False
        
        # 创建新事务
        ctx = TransactionContext(
            session=session,
            auto_commit=auto_commit,
            propagation=propagation,
            suppress_commit=suppress_commit
        )
        
        # 注册全局钩子
        self._apply_global_hooks(ctx)
        
        token = _current_transaction.set(ctx)
        try:
            with ctx:
                yield ctx
        finally:
            _current_transaction.reset(token)
    
    def _apply_global_hooks(self, ctx: TransactionContext) -> None:
        """将全局钩子应用到事务上下文"""
        # 注册全局钩子对象
        for hook_type, hooks in self._global_hook_objects.items():
            for hook in hooks:
                ctx.hooks.register(hook)
        
        # 注册全局钩子函数
        for hook_type, funcs in self._global_hooks.items():
            for func in funcs:
                ctx.hooks.register_func(hook_type, func)
    
    def transactional(
        self,
        propagation: TransactionPropagation = TransactionPropagation.REQUIRED,
        read_only: bool = False,
        rollback_for: tuple = (Exception,),
        no_rollback_for: tuple = (),
        suppress_commit: bool = None
    ):
        """事务装饰器
        
        Args:
            propagation: 事务传播行为
            read_only: 是否只读
            rollback_for: 触发回滚的异常类型
            no_rollback_for: 不触发回滚的异常类型
            suppress_commit: 是否抑制内部提交
        
        使用示例:
            @tm.transactional()
            def create_user(data):
                user = User(**data)
                user.save()
                return user
            
            @tm.transactional(propagation=TransactionPropagation.REQUIRES_NEW)
            def audit_log(action):
                # 独立事务，不受外层影响
                log = AuditLog(action=action)
                log.save()
        """
        def decorator(func: Callable[..., T]) -> Callable[..., T]:
            @wraps(func)
            def wrapper(*args, **kwargs) -> T:
                with self.transaction(
                    propagation=propagation,
                    read_only=read_only,
                    suppress_commit=suppress_commit
                ) as tx:
                    try:
                        result = func(*args, **kwargs)
                        return result
                    except no_rollback_for:
                        raise
                    except rollback_for:
                        tx.rollback()
                        raise
            
            @wraps(func)
            async def async_wrapper(*args, **kwargs) -> T:
                with self.transaction(
                    propagation=propagation,
                    read_only=read_only,
                    suppress_commit=suppress_commit
                ) as tx:
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except no_rollback_for:
                        raise
                    except rollback_for:
                        tx.rollback()
                        raise
            
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper
        
        return decorator
    
    def register_global_hook(self, hook: TransactionHook) -> None:
        """注册全局钩子对象（对所有事务生效）
        
        Args:
            hook: TransactionHook 子类实例
        """
        self._global_hook_objects[hook.hook_type].append(hook)
        self._global_hook_objects[hook.hook_type].sort(key=lambda h: h.priority)
    
    def unregister_global_hook(self, hook: TransactionHook) -> None:
        """取消注册全局钩子"""
        if hook in self._global_hook_objects[hook.hook_type]:
            self._global_hook_objects[hook.hook_type].remove(hook)
    
    def clear_global_hooks(self) -> None:
        """清除所有全局钩子"""
        for hook_type in TransactionHookType:
            self._global_hooks[hook_type].clear()
            self._global_hook_objects[hook_type].clear()
    
    def is_in_transaction(self) -> bool:
        """检查当前是否在事务中"""
        tx = self.current_transaction
        return tx is not None and tx.is_active
    
    def should_suppress_commit(self) -> bool:
        """检查是否应该抑制提交
        
        用于 CoreModel 中判断 commit=True 是否应该被忽略
        """
        tx = self.current_transaction
        if tx is None:
            return False
        return tx.should_suppress_commit()


# 全局单例
transaction_manager = TransactionManager()
