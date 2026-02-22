"""事务上下文

提供事务和保存点的上下文管理
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Dict, List, Callable, Any, Optional, TYPE_CHECKING

from sqlalchemy.orm import Session

from yweb.log import get_logger

from .state import TransactionState
from .propagation import TransactionPropagation
from .hooks import TransactionHooks, TransactionHookType
from .exceptions import (
    TransactionNotActiveError,
    TransactionAlreadyCommittedError,
    TransactionAlreadyRolledBackError,
    SavepointError,
)

if TYPE_CHECKING:
    from sqlalchemy.orm.session import SessionTransaction

logger = get_logger("yweb.orm.transaction")


class SavepointContext:
    """保存点上下文
    
    管理单个保存点的生命周期
    
    使用示例:
        with tx.savepoint("sp1") as sp:
            risky_operation()
            # 如果发生异常，自动回滚到此保存点
    """
    
    def __init__(
        self,
        name: str,
        nested: 'SessionTransaction',
        parent: 'TransactionContext'
    ):
        """初始化保存点
        
        Args:
            name: 保存点名称
            nested: SQLAlchemy 嵌套事务对象
            parent: 父事务上下文
        """
        self.name = name
        self._nested = nested
        self._parent = parent
        self._state = TransactionState.ACTIVE
        self._hooks = TransactionHooks()
    
    @property
    def state(self) -> TransactionState:
        """获取保存点状态"""
        return self._state
    
    @property
    def is_active(self) -> bool:
        """保存点是否活跃"""
        return self._state == TransactionState.ACTIVE
    
    @property
    def hooks(self) -> TransactionHooks:
        """获取钩子管理器"""
        return self._hooks
    
    def release(self) -> None:
        """释放保存点（提交到外层事务）
        
        调用后，保存点的变更将合并到外层事务
        """
        if self._state != TransactionState.ACTIVE:
            return
        
        try:
            self._hooks.execute_before_commit(self._parent)
            self._nested.commit()
            self._state = TransactionState.COMMITTED
            self._hooks.execute_after_commit(self._parent)
            logger.debug(f"保存点 {self.name} 已释放")
        except Exception as e:
            self._state = TransactionState.FAILED
            raise
    
    def rollback(self) -> None:
        """回滚到此保存点
        
        调用后，保存点之后的所有变更将被撤销
        """
        if self._state != TransactionState.ACTIVE:
            return
        
        try:
            self._hooks.execute_before_rollback(self._parent)
            self._nested.rollback()
            self._state = TransactionState.ROLLED_BACK
            self._hooks.execute_after_rollback(self._parent)
            logger.debug(f"保存点 {self.name} 已回滚")
        except Exception as e:
            self._state = TransactionState.FAILED
            logger.error(f"保存点 {self.name} 回滚失败: {e}")
            raise
    
    def __enter__(self) -> 'SavepointContext':
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            self.rollback()
            return False  # 不抑制异常，让外层处理
        
        if self._state == TransactionState.ACTIVE:
            try:
                self.release()
            except Exception:
                # release 失败时回滚 savepoint，清理状态
                self.rollback()
                raise
        return False


class TransactionContext:
    """事务上下文
    
    管理单个事务的完整生命周期，包括：
    - 事务状态跟踪
    - Savepoint 管理
    - 钩子执行
    - 嵌套事务支持
    - 提交抑制机制
    
    使用示例:
        with TransactionContext(session) as tx:
            user = User(name="tom")
            user.add()
            
            # 创建保存点
            with tx.savepoint("sp1"):
                profile = Profile(user_id=user.id)
                profile.add()
                # 如果这里抛出异常，只回滚到 sp1
            
            # 注册提交后回调
            @tx.after_commit
            def on_committed(ctx):
                send_email()
    """
    
    def __init__(
        self,
        session: Session,
        auto_commit: bool = True,
        propagation: TransactionPropagation = None,
        suppress_commit: bool = True
    ):
        """初始化事务上下文
        
        Args:
            session: SQLAlchemy Session 对象
            auto_commit: 是否在上下文结束时自动提交
            propagation: 事务传播行为
            suppress_commit: 是否抑制内部的 commit=True 调用
        """
        self._session = session
        self._auto_commit = auto_commit
        self._propagation = propagation or TransactionPropagation.REQUIRED
        self._suppress_commit = suppress_commit
        self._state = TransactionState.INACTIVE
        
        # 提交抑制控制
        self._allow_commit_depth = 0
        
        # Savepoint 管理
        self._savepoints: Dict[str, SavepointContext] = {}
        self._savepoint_stack: List[str] = []
        self._savepoint_counter = 0
        
        # 钩子管理
        self._hooks = TransactionHooks()
        
        # 嵌套层级
        self._nesting_level = 0
        self._parent_context: Optional['TransactionContext'] = None
        
        # 上下文数据（用于在钩子之间传递数据）
        self.data: Dict[str, Any] = {}
    
    # ==================== 属性 ====================
    
    @property
    def session(self) -> Session:
        """获取数据库 session"""
        return self._session
    
    @property
    def state(self) -> TransactionState:
        """获取事务状态"""
        return self._state
    
    @property
    def is_active(self) -> bool:
        """事务是否活跃"""
        return self._state == TransactionState.ACTIVE
    
    @property
    def nesting_level(self) -> int:
        """获取嵌套层级"""
        return self._nesting_level
    
    @property
    def hooks(self) -> TransactionHooks:
        """获取钩子管理器"""
        return self._hooks
    
    @property
    def suppress_commit(self) -> bool:
        """是否抑制内部的 commit=True 调用
        
        只有当 _suppress_commit 为 True 且没有通过 allow_commit() 临时允许时才抑制
        """
        return self._suppress_commit and self._allow_commit_depth == 0
    
    @property
    def propagation(self) -> TransactionPropagation:
        """获取事务传播行为"""
        return self._propagation
    
    # ==================== 事务生命周期方法 ====================
    
    def begin(self) -> 'TransactionContext':
        """开始事务"""
        if self._state == TransactionState.ACTIVE:
            # 已在事务中，增加嵌套层级
            self._nesting_level += 1
            logger.debug(f"加入现有事务 (level={self._nesting_level})")
            return self
        
        self._hooks.execute(TransactionHookType.BEFORE_BEGIN, self)
        
        # 开始事务（SQLAlchemy 默认 autobegin）
        self._state = TransactionState.ACTIVE
        self._nesting_level = 1
        
        self._hooks.execute(TransactionHookType.AFTER_BEGIN, self)
        logger.debug(f"事务开始 (level={self._nesting_level})")
        
        return self
    
    def commit(self) -> None:
        """提交事务"""
        if self._state == TransactionState.COMMITTED:
            raise TransactionAlreadyCommittedError()
        if self._state == TransactionState.ROLLED_BACK:
            raise TransactionAlreadyRolledBackError()
        if self._state != TransactionState.ACTIVE:
            raise TransactionNotActiveError(f"无法提交：事务状态为 {self._state}")
        
        if self._nesting_level > 1:
            # 嵌套事务，只减少层级
            self._nesting_level -= 1
            logger.debug(f"嵌套事务退出 (level={self._nesting_level})")
            return
        
        try:
            # 执行 before_commit 钩子（失败会抛出异常）
            self._hooks.execute_before_commit(self)
            
            # 提交数据库事务
            self._session.commit()
            self._state = TransactionState.COMMITTED
            self._nesting_level = 0
            
            # 执行 after_commit 钩子（失败不影响已提交的事务）
            errors = self._hooks.execute_after_commit(self)
            if errors:
                logger.warning(f"{len(errors)} 个 after_commit 钩子执行失败")
            
            logger.debug("事务提交成功")
        except Exception as e:
            self._state = TransactionState.FAILED
            self._hooks.execute_on_error(self, e)
            raise
    
    def rollback(self) -> None:
        """回滚事务"""
        if self._state == TransactionState.COMMITTED:
            raise TransactionAlreadyCommittedError("无法回滚：事务已提交")
        if self._state == TransactionState.ROLLED_BACK:
            return  # 幂等操作
        if self._state not in (TransactionState.ACTIVE, TransactionState.FAILED):
            return
        
        try:
            self._hooks.execute_before_rollback(self)
            
            self._session.rollback()
            self._state = TransactionState.ROLLED_BACK
            self._nesting_level = 0
            
            # 清理所有保存点
            self._savepoints.clear()
            self._savepoint_stack.clear()
            
            self._hooks.execute_after_rollback(self)
            logger.debug("事务回滚成功")
        except Exception as e:
            self._state = TransactionState.FAILED
            logger.error(f"事务回滚失败: {e}")
            
            # 尝试补救性 rollback（忽略失败）
            # 场景：before_rollback 钩子失败导致 session.rollback() 未执行
            try:
                self._session.rollback()
            except Exception:
                pass  # 补救失败没关系，有 session_scope.remove() 兜底
            
            raise
    
    def flush(self) -> None:
        """刷新 session（将变更写入数据库但不提交）"""
        if not self.is_active:
            raise TransactionNotActiveError("无法刷新：事务未激活")
        self._session.flush()
    
    # ==================== Savepoint 方法 ====================
    
    @contextmanager
    def savepoint(self, name: str = None):
        """创建保存点上下文
        
        Args:
            name: 保存点名称，不传则自动生成
        
        Yields:
            SavepointContext 对象
        
        使用示例:
            with tx.savepoint("sp1") as sp:
                # 操作...
                if error:
                    sp.rollback()  # 只回滚到此保存点
        """
        if not self.is_active:
            raise TransactionNotActiveError("无法创建保存点：事务未激活")
        
        if name is None:
            self._savepoint_counter += 1
            name = f"sp_{self._savepoint_counter}"
        
        sp = self._create_savepoint(name)
        try:
            yield sp
            if sp.is_active:
                sp.release()
        except Exception:
            if sp.is_active:
                sp.rollback()
            raise
    
    def _create_savepoint(self, name: str) -> SavepointContext:
        """创建保存点"""
        nested = self._session.begin_nested()
        sp = SavepointContext(name, nested, self)
        self._savepoints[name] = sp
        self._savepoint_stack.append(name)
        logger.debug(f"创建保存点: {name}")
        return sp
    
    def get_savepoint(self, name: str) -> Optional[SavepointContext]:
        """获取指定名称的保存点"""
        return self._savepoints.get(name)
    
    def rollback_to_savepoint(self, name: str) -> None:
        """回滚到指定保存点"""
        sp = self._savepoints.get(name)
        if sp is None:
            from .exceptions import SavepointNotFoundError
            raise SavepointNotFoundError(name)
        
        sp.rollback()
        
        # 移除该保存点之后的所有保存点
        if name in self._savepoint_stack:
            idx = self._savepoint_stack.index(name)
            for sp_name in self._savepoint_stack[idx:]:
                self._savepoints.pop(sp_name, None)
            self._savepoint_stack = self._savepoint_stack[:idx]
        
        logger.debug(f"回滚到保存点: {name}")
    
    # ==================== 提交抑制控制 ====================
    
    @contextmanager
    def allow_commit(self):
        """临时允许 commit=True 生效
        
        使用示例:
            with tx.allow_commit():
                critical_log.save(commit=True)  # 正常提交
        """
        self._allow_commit_depth += 1
        try:
            yield
        finally:
            self._allow_commit_depth -= 1
    
    def force_flush_and_commit(self) -> None:
        """强制刷新并提交当前变更（慎用）
        
        注意：这会提交事务中到目前为止的所有变更，
        事务上下文会继续，后续操作仍在新的隐式事务中。
        """
        self._session.flush()
        self._session.commit()
        # 重置状态为活跃（新的隐式事务）
        self._state = TransactionState.ACTIVE
        logger.warning("force_flush_and_commit: 事务已强制提交，开始新的隐式事务")
    
    def should_suppress_commit(self) -> bool:
        """检查是否应该抑制提交
        
        用于 CoreModel 中判断 commit=True 是否应该被忽略
        """
        return self.is_active and self.suppress_commit
    
    # ==================== 钩子装饰器 ====================
    
    def before_commit(self, func: Callable) -> Callable:
        """注册 before_commit 钩子（装饰器方式）
        
        使用示例:
            @tx.before_commit
            def validate_data(ctx):
                # 验证逻辑
                pass
        """
        self._hooks.register_func(TransactionHookType.BEFORE_COMMIT, func)
        return func
    
    def after_commit(self, func: Callable) -> Callable:
        """注册 after_commit 钩子（装饰器方式）
        
        使用示例:
            @tx.after_commit
            def send_notification(ctx):
                # 发送通知
                pass
        """
        self._hooks.register_func(TransactionHookType.AFTER_COMMIT, func)
        return func
    
    def before_rollback(self, func: Callable) -> Callable:
        """注册 before_rollback 钩子"""
        self._hooks.register_func(TransactionHookType.BEFORE_ROLLBACK, func)
        return func
    
    def after_rollback(self, func: Callable) -> Callable:
        """注册 after_rollback 钩子"""
        self._hooks.register_func(TransactionHookType.AFTER_ROLLBACK, func)
        return func
    
    def on_error(self, func: Callable) -> Callable:
        """注册错误处理钩子"""
        self._hooks.register_func(TransactionHookType.ON_ERROR, func)
        return func
    
    # ==================== 上下文管理器 ====================
    
    def __enter__(self) -> 'TransactionContext':
        return self.begin()
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is not None:
            # 执行错误处理钩子
            self._hooks.execute_on_error(self, exc_val)
            self.rollback()
            return False
        
        if self._auto_commit and self._nesting_level == 1:
            try:
                self.commit()
            except Exception:
                # commit 失败时确保回滚，清理 session 状态
                self.rollback()
                raise
        elif self._nesting_level > 1:
            self._nesting_level -= 1
        
        return False
    
    def __repr__(self) -> str:
        return (
            f"TransactionContext("
            f"state={self._state.value}, "
            f"nesting_level={self._nesting_level}, "
            f"suppress_commit={self.suppress_commit})"
        )
