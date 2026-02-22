# 16. 事务管理器设计文档

## 概述

本文档描述 YWeb ORM 的高级事务管理功能设计，包括嵌套事务（Savepoints）、事务钩子机制，以及为分布式事务预留的扩展接口。

## 设计目标

1. **嵌套事务支持**：通过 Savepoints 实现，内层事务回滚不影响外层事务
2. **事务钩子机制**：支持 before_commit、after_commit、before_rollback、after_rollback 等钩子
3. **易用性**：提供上下文管理器和装饰器两种使用方式
4. **可扩展性**：为分布式事务预留接口，支持未来扩展
5. **与现有代码兼容**：不破坏现有的 `commit=True` 参数和 Service 层模式

## 架构设计

```
┌─────────────────────────────────────────────────────────────────────┐
│                         应用层 (FastAPI)                             │
├─────────────────────────────────────────────────────────────────────┤
│                         Service 层                                   │
├─────────────────────────────────────────────────────────────────────┤
│                    TransactionManager                                │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  TransactionContext (上下文管理器)                            │   │
│  │  ├── begin() / commit() / rollback()                        │   │
│  │  ├── savepoint() / release_savepoint() / rollback_to()      │   │
│  │  └── Hooks: before_commit, after_commit, etc.               │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  TransactionHook (钩子管理)                                   │   │
│  │  ├── register_hook() / unregister_hook()                    │   │
│  │  └── execute_hooks()                                        │   │
│  └─────────────────────────────────────────────────────────────┘   │
│  ┌─────────────────────────────────────────────────────────────┐   │
│  │  DistributedTransaction (预留接口)                            │   │
│  │  ├── prepare() / commit() / rollback()                      │   │
│  │  └── 2PC / Saga 模式支持                                     │   │
│  └─────────────────────────────────────────────────────────────┘   │
├─────────────────────────────────────────────────────────────────────┤
│                    SQLAlchemy Session                                │
│  ┌───────────────────────────────────────────────────────────────┐ │
│  │  session.begin_nested() → Savepoint                           │ │
│  │  session.commit() / session.rollback()                        │ │
│  └───────────────────────────────────────────────────────────────┘ │
├─────────────────────────────────────────────────────────────────────┤
│                          数据库                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### 核心组件

| 组件 | 职责 | 文件位置 |
|------|------|----------|
| `TransactionManager` | 事务管理器主类，全局单例 | `yweb/orm/transaction/manager.py` |
| `TransactionContext` | 事务上下文对象，管理生命周期 | `yweb/orm/transaction/context.py` |
| `SavepointContext` | 保存点管理 | `yweb/orm/transaction/context.py` |
| `TransactionHooks` | 钩子系统 | `yweb/orm/transaction/hooks.py` |
| `TransactionState` | 事务状态枚举 | `yweb/orm/transaction/context.py` |
| `TransactionPropagation` | 事务传播行为枚举 | `yweb/orm/transaction/propagation.py` |

### 事务状态机

```
                    ┌──────────┐
                    │ INACTIVE │  （初始状态）
                    └────┬─────┘
                         │ begin()
                         ▼
                    ┌──────────┐
          ┌────────│  ACTIVE  │────────┐
          │        └────┬─────┘        │
          │             │              │
    rollback()     commit()      exception
          │             │              │
          ▼             ▼              ▼
    ┌──────────┐  ┌──────────┐  ┌──────────┐
    │ ROLLED   │  │COMMITTED │  │  FAILED  │
    │  BACK    │  │          │  │          │
    └──────────┘  └──────────┘  └──────────┘
```

## 核心类设计

### 1. TransactionState - 事务状态枚举

```python
from enum import Enum

class TransactionState(Enum):
    """事务状态"""
    INACTIVE = "inactive"       # 未激活
    ACTIVE = "active"           # 活跃中
    COMMITTED = "committed"     # 已提交
    ROLLED_BACK = "rolled_back" # 已回滚
    FAILED = "failed"           # 失败
```

### 2. TransactionHookType - 钩子类型枚举

```python
class TransactionHookType(Enum):
    """事务钩子类型"""
    BEFORE_BEGIN = "before_begin"       # 事务开始前
    AFTER_BEGIN = "after_begin"         # 事务开始后
    BEFORE_COMMIT = "before_commit"     # 提交前
    AFTER_COMMIT = "after_commit"       # 提交后
    BEFORE_ROLLBACK = "before_rollback" # 回滚前
    AFTER_ROLLBACK = "after_rollback"   # 回滚后
    ON_ERROR = "on_error"               # 发生错误时
```

### 3. TransactionHook - 钩子基类

```python
from abc import ABC, abstractmethod
from typing import Any, Optional

class TransactionHook(ABC):
    """事务钩子基类
    
    用户可以继承此类实现自定义钩子逻辑
    """
    
    @property
    @abstractmethod
    def hook_type(self) -> TransactionHookType:
        """钩子类型"""
        pass
    
    @property
    def priority(self) -> int:
        """执行优先级（数字越小越先执行）"""
        return 100
    
    @property
    def name(self) -> str:
        """钩子名称（用于日志和调试）"""
        return self.__class__.__name__
    
    @abstractmethod
    def execute(self, context: 'TransactionContext') -> None:
        """执行钩子逻辑
        
        Args:
            context: 事务上下文对象
        """
        pass
    
    def on_error(self, context: 'TransactionContext', error: Exception) -> None:
        """钩子执行出错时的处理
        
        Args:
            context: 事务上下文
            error: 发生的异常
        """
        pass
```

### 4. TransactionContext - 事务上下文

```python
from typing import List, Dict, Callable, Any, Optional
from sqlalchemy.orm import Session
from contextlib import contextmanager

# 使用预定义的日志器（需在 yweb/log/logger.py 中添加）
from yweb.log import transaction_logger as logger

class TransactionContext:
    """事务上下文
    
    管理单个事务的完整生命周期，包括：
    - 事务状态跟踪
    - Savepoint 管理
    - 钩子执行
    - 嵌套事务支持
    
    使用示例:
        with TransactionContext(session) as tx:
            user = User(name="tom")
            user.add()
            
            # 创建保存点
            with tx.savepoint("sp1"):
                profile = Profile(user_id=user.id)
                profile.add()
                # 如果这里抛出异常，只回滚到 sp1
    """
    
    def __init__(
        self,
        session: Session,
        auto_commit: bool = True,
        propagation: 'TransactionPropagation' = None,
        suppress_commit: bool = True
    ):
        """初始化事务上下文
        
        Args:
            session: SQLAlchemy Session 对象
            auto_commit: 是否在上下文结束时自动提交
            propagation: 事务传播行为（用于嵌套事务）
            suppress_commit: 是否抑制内部的 commit=True 调用
        """
        self._session = session
        self._auto_commit = auto_commit
        self._propagation = propagation or TransactionPropagation.REQUIRED
        self._state = TransactionState.INACTIVE
        self._suppress_commit = suppress_commit
        self._allow_commit_depth = 0  # 临时允许提交的深度计数
        
        # Savepoint 管理
        self._savepoints: List[str] = []
        self._savepoint_counter = 0
        
        # 钩子管理
        self._hooks: Dict[TransactionHookType, List[TransactionHook]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        self._inline_hooks: Dict[TransactionHookType, List[Callable]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        
        # 嵌套层级
        self._nesting_level = 0
        self._parent_context: Optional['TransactionContext'] = None
        
        # 上下文数据（用于在钩子之间传递数据）
        self.data: Dict[str, Any] = {}
    
    @property
    def session(self) -> Session:
        return self._session
    
    @property
    def state(self) -> TransactionState:
        return self._state
    
    @property
    def is_active(self) -> bool:
        return self._state == TransactionState.ACTIVE
    
    @property
    def nesting_level(self) -> int:
        return self._nesting_level
    
    @property
    def suppress_commit(self) -> bool:
        """是否抑制内部的 commit=True 调用"""
        return self._suppress_commit and self._allow_commit_depth == 0
    
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
    
    def force_flush_and_commit(self):
        """强制刷新并提交当前变更（慎用）
        
        注意：这会提交事务中到目前为止的所有变更，
        但事务上下文会继续，后续操作仍在同一事务中。
        """
        self._session.flush()
        self._session.commit()
        logger.warning("force_flush_and_commit: 事务已强制提交")
    
    # ==================== 事务生命周期方法 ====================
    
    def begin(self) -> 'TransactionContext':
        """开始事务"""
        if self._state == TransactionState.ACTIVE:
            # 已在事务中，增加嵌套层级
            self._nesting_level += 1
            return self
        
        self._execute_hooks(TransactionHookType.BEFORE_BEGIN)
        
        # 开始事务（SQLAlchemy 默认 autobegin）
        self._state = TransactionState.ACTIVE
        self._nesting_level = 1
        
        self._execute_hooks(TransactionHookType.AFTER_BEGIN)
        logger.debug(f"事务开始 (level={self._nesting_level})")
        
        return self
    
    def commit(self) -> None:
        """提交事务"""
        if self._state != TransactionState.ACTIVE:
            raise RuntimeError(f"无法提交：事务状态为 {self._state}")
        
        if self._nesting_level > 1:
            # 嵌套事务，只减少层级
            self._nesting_level -= 1
            logger.debug(f"嵌套事务退出 (level={self._nesting_level})")
            return
        
        try:
            self._execute_hooks(TransactionHookType.BEFORE_COMMIT)
            
            self._session.commit()
            self._state = TransactionState.COMMITTED
            
            self._execute_hooks(TransactionHookType.AFTER_COMMIT)
            logger.debug("事务提交成功")
        except Exception as e:
            self._state = TransactionState.FAILED
            self._execute_hooks(TransactionHookType.ON_ERROR, error=e)
            raise
    
    def rollback(self) -> None:
        """回滚事务"""
        if self._state not in (TransactionState.ACTIVE, TransactionState.FAILED):
            return
        
        try:
            self._execute_hooks(TransactionHookType.BEFORE_ROLLBACK)
            
            self._session.rollback()
            self._state = TransactionState.ROLLED_BACK
            self._nesting_level = 0
            self._savepoints.clear()
            
            self._execute_hooks(TransactionHookType.AFTER_ROLLBACK)
            logger.debug("事务回滚成功")
        except Exception as e:
            logger.error(f"事务回滚失败: {e}")
            raise
    
    # ==================== Savepoint 方法 ====================
    
    @contextmanager
    def savepoint(self, name: str = None):
        """创建保存点上下文
        
        Args:
            name: 保存点名称，不传则自动生成
        
        使用示例:
            with tx.savepoint("sp1") as sp:
                # 操作...
                if error:
                    sp.rollback()  # 只回滚到此保存点
        
        Yields:
            SavepointContext 对象
        """
        if name is None:
            self._savepoint_counter += 1
            name = f"sp_{self._savepoint_counter}"
        
        sp = self._create_savepoint(name)
        try:
            yield sp
            sp.release()
        except Exception as e:
            sp.rollback()
            raise
    
    def _create_savepoint(self, name: str) -> 'SavepointContext':
        """创建保存点"""
        nested = self._session.begin_nested()
        sp = SavepointContext(name, nested, self)
        self._savepoints.append(name)
        logger.debug(f"创建保存点: {name}")
        return sp
    
    def rollback_to_savepoint(self, name: str) -> None:
        """回滚到指定保存点"""
        if name not in self._savepoints:
            raise ValueError(f"保存点不存在: {name}")
        
        # 回滚到该保存点之后的所有保存点
        idx = self._savepoints.index(name)
        self._savepoints = self._savepoints[:idx]
        logger.debug(f"回滚到保存点: {name}")
    
    # ==================== 钩子管理 ====================
    
    def register_hook(self, hook: TransactionHook) -> None:
        """注册钩子对象"""
        self._hooks[hook.hook_type].append(hook)
        self._hooks[hook.hook_type].sort(key=lambda h: h.priority)
    
    def before_commit(self, func: Callable) -> Callable:
        """注册 before_commit 钩子（装饰器方式）
        
        使用示例:
            @tx.before_commit
            def validate_data(ctx):
                # 验证逻辑
                pass
        """
        self._inline_hooks[TransactionHookType.BEFORE_COMMIT].append(func)
        return func
    
    def after_commit(self, func: Callable) -> Callable:
        """注册 after_commit 钩子（装饰器方式）
        
        使用示例:
            @tx.after_commit
            def send_notification(ctx):
                # 发送通知
                pass
        """
        self._inline_hooks[TransactionHookType.AFTER_COMMIT].append(func)
        return func
    
    def before_rollback(self, func: Callable) -> Callable:
        """注册 before_rollback 钩子"""
        self._inline_hooks[TransactionHookType.BEFORE_ROLLBACK].append(func)
        return func
    
    def after_rollback(self, func: Callable) -> Callable:
        """注册 after_rollback 钩子"""
        self._inline_hooks[TransactionHookType.AFTER_ROLLBACK].append(func)
        return func
    
    def on_error(self, func: Callable) -> Callable:
        """注册错误处理钩子"""
        self._inline_hooks[TransactionHookType.ON_ERROR].append(func)
        return func
    
    def _execute_hooks(
        self,
        hook_type: TransactionHookType,
        error: Exception = None
    ) -> None:
        """执行指定类型的所有钩子"""
        # 执行注册的钩子对象
        for hook in self._hooks[hook_type]:
            try:
                if hook_type == TransactionHookType.ON_ERROR:
                    hook.execute(self, error)
                else:
                    hook.execute(self)
            except Exception as e:
                logger.error(f"钩子 {hook.name} 执行失败: {e}")
                hook.on_error(self, e)
        
        # 执行内联钩子函数
        for func in self._inline_hooks[hook_type]:
            try:
                if hook_type == TransactionHookType.ON_ERROR:
                    func(self, error)
                else:
                    func(self)
            except Exception as e:
                logger.error(f"钩子函数 {func.__name__} 执行失败: {e}")
    
    # ==================== 上下文管理器 ====================
    
    def __enter__(self) -> 'TransactionContext':
        return self.begin()
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self.rollback()
            return False
        
        if self._auto_commit and self._nesting_level == 1:
            self.commit()
        elif self._nesting_level > 1:
            self._nesting_level -= 1
        
        return False


class SavepointContext:
    """保存点上下文"""
    
    def __init__(self, name: str, nested, parent: TransactionContext):
        self.name = name
        self._nested = nested
        self._parent = parent
        self._released = False
        self._rolled_back = False
    
    def release(self) -> None:
        """释放保存点（提交到外层事务）"""
        if not self._released and not self._rolled_back:
            self._nested.commit()
            self._released = True
            logger.debug(f"保存点 {self.name} 已释放")
    
    def rollback(self) -> None:
        """回滚到此保存点"""
        if not self._released and not self._rolled_back:
            self._nested.rollback()
            self._rolled_back = True
            logger.debug(f"保存点 {self.name} 已回滚")
```

### 5. TransactionPropagation - 事务传播行为

```python
class TransactionPropagation(Enum):
    """事务传播行为
    
    定义当方法在已有事务上下文中被调用时的行为
    """
    
    # 如果当前有事务则加入，没有则新建（默认）
    REQUIRED = "required"
    
    # 总是新建事务（使用 savepoint 实现嵌套）
    REQUIRES_NEW = "requires_new"
    
    # 如果当前有事务则加入，没有则以非事务方式执行
    SUPPORTS = "supports"
    
    # 以非事务方式执行，如果当前有事务则挂起
    NOT_SUPPORTED = "not_supported"
    
    # 必须在事务中执行，否则抛出异常
    MANDATORY = "mandatory"
    
    # 必须不在事务中执行，否则抛出异常
    NEVER = "never"
    
    # 如果当前有事务则创建嵌套事务（savepoint）
    NESTED = "nested"
```

### 6. TransactionManager - 事务管理器

```python
from typing import TypeVar, Callable, Optional, List, Type
from functools import wraps
from contextvars import ContextVar

T = TypeVar('T')

# 当前事务上下文（线程/协程安全）
_current_transaction: ContextVar[Optional[TransactionContext]] = ContextVar(
    '_current_transaction', default=None
)

class TransactionManager:
    """事务管理器
    
    提供事务管理的统一入口，包括：
    - 获取/创建事务上下文
    - 事务装饰器
    - 全局钩子注册
    
    使用示例:
        from yweb.orm import TransactionManager, db_manager
        
        # 初始化
        tm = TransactionManager()
        
        # 使用上下文管理器
        with tm.transaction() as tx:
            user.save()
            tx.after_commit(lambda ctx: print("已提交"))
        
        # 使用装饰器
        @tm.transactional
        def create_order(data):
            order = Order(**data)
            order.save()
            return order
        
        # 嵌套事务
        @tm.transactional
        def process_order(order_id):
            order = Order.get(order_id)
            
            @tm.transactional(propagation=TransactionPropagation.NESTED)
            def update_inventory():
                # 这是一个嵌套事务（savepoint）
                # 如果失败不影响外层事务
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
        
        self._global_hooks: Dict[TransactionHookType, List[TransactionHook]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        self._initialized = True
    
    def get_session(self) -> Session:
        """获取数据库 session"""
        from .db_session import db_manager
        return db_manager.get_session()
    
    @property
    def current_transaction(self) -> Optional[TransactionContext]:
        """获取当前事务上下文"""
        return _current_transaction.get()
    
    @contextmanager
    def transaction(
        self,
        session: Session = None,
        propagation: TransactionPropagation = TransactionPropagation.REQUIRED,
        auto_commit: bool = True,
        read_only: bool = False
    ):
        """创建事务上下文
        
        Args:
            session: 数据库会话，不传则自动获取
            propagation: 事务传播行为
            auto_commit: 是否自动提交
            read_only: 是否只读事务（优化提示）
        
        Yields:
            TransactionContext 对象
        
        使用示例:
            with tm.transaction() as tx:
                user = User(name="tom")
                user.add()
                
                # 注册提交后回调
                @tx.after_commit
                def on_committed(ctx):
                    send_welcome_email(user)
        """
        if session is None:
            session = self.get_session()
        
        current = self.current_transaction
        
        # 处理事务传播
        if propagation == TransactionPropagation.REQUIRED:
            if current and current.is_active:
                # 加入现有事务
                current._nesting_level += 1
                try:
                    yield current
                finally:
                    current._nesting_level -= 1
                return
        
        elif propagation == TransactionPropagation.REQUIRES_NEW:
            # 总是新建事务（通过 savepoint）
            if current and current.is_active:
                with current.savepoint() as sp:
                    yield current
                return
        
        elif propagation == TransactionPropagation.MANDATORY:
            if not current or not current.is_active:
                raise RuntimeError("MANDATORY: 必须在事务中执行")
            current._nesting_level += 1
            try:
                yield current
            finally:
                current._nesting_level -= 1
            return
        
        elif propagation == TransactionPropagation.NEVER:
            if current and current.is_active:
                raise RuntimeError("NEVER: 不能在事务中执行")
        
        elif propagation == TransactionPropagation.NESTED:
            if current and current.is_active:
                with current.savepoint() as sp:
                    yield current
                return
        
        # 创建新事务
        ctx = TransactionContext(session, auto_commit, propagation)
        
        # 注册全局钩子
        for hook_type, hooks in self._global_hooks.items():
            for hook in hooks:
                ctx.register_hook(hook)
        
        token = _current_transaction.set(ctx)
        try:
            with ctx:
                yield ctx
        finally:
            _current_transaction.reset(token)
    
    def transactional(
        self,
        propagation: TransactionPropagation = TransactionPropagation.REQUIRED,
        read_only: bool = False,
        rollback_for: tuple = (Exception,),
        no_rollback_for: tuple = ()
    ):
        """事务装饰器
        
        Args:
            propagation: 事务传播行为
            read_only: 是否只读
            rollback_for: 触发回滚的异常类型
            no_rollback_for: 不触发回滚的异常类型
        
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
                with self.transaction(propagation=propagation, read_only=read_only) as tx:
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
                with self.transaction(propagation=propagation, read_only=read_only) as tx:
                    try:
                        result = await func(*args, **kwargs)
                        return result
                    except no_rollback_for:
                        raise
                    except rollback_for:
                        tx.rollback()
                        raise
            
            import asyncio
            if asyncio.iscoroutinefunction(func):
                return async_wrapper
            return wrapper
        
        return decorator
    
    def register_global_hook(self, hook: TransactionHook) -> None:
        """注册全局钩子（对所有事务生效）"""
        self._global_hooks[hook.hook_type].append(hook)
        self._global_hooks[hook.hook_type].sort(key=lambda h: h.priority)
    
    def unregister_global_hook(self, hook: TransactionHook) -> None:
        """取消注册全局钩子"""
        if hook in self._global_hooks[hook.hook_type]:
            self._global_hooks[hook.hook_type].remove(hook)
    
    @property
    def global_hooks(self) -> 'GlobalHooksRegistry':
        """全局钩子注册器（装饰器方式）
        
        使用示例:
            @tm.global_hooks.before_commit
            def audit_log():
                logger.info("事务即将提交...")
            
            @tm.global_hooks.after_commit
            def clear_cache():
                cache.invalidate_all()
        """
        return GlobalHooksRegistry(self)


class GlobalHooksRegistry:
    """全局钩子注册器
    
    提供装饰器方式注册全局钩子
    """
    
    def __init__(self, manager: TransactionManager):
        self._manager = manager
    
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


# 全局单例
transaction_manager = TransactionManager()
```

## 分布式事务接口设计

### 1. DistributedTransactionCoordinator - 分布式事务协调器接口

```python
from abc import ABC, abstractmethod
from typing import List, Any
from enum import Enum

class DistributedTransactionState(Enum):
    """分布式事务状态"""
    PREPARING = "preparing"
    PREPARED = "prepared"
    COMMITTING = "committing"
    COMMITTED = "committed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class TransactionParticipant(ABC):
    """事务参与者接口
    
    每个参与分布式事务的服务/资源需要实现此接口
    """
    
    @property
    @abstractmethod
    def participant_id(self) -> str:
        """参与者唯一标识"""
        pass
    
    @abstractmethod
    def prepare(self, transaction_id: str) -> bool:
        """准备阶段
        
        Returns:
            是否准备成功
        """
        pass
    
    @abstractmethod
    def commit(self, transaction_id: str) -> bool:
        """提交阶段"""
        pass
    
    @abstractmethod
    def rollback(self, transaction_id: str) -> bool:
        """回滚阶段"""
        pass
    
    def get_status(self, transaction_id: str) -> DistributedTransactionState:
        """获取事务状态"""
        pass


class DistributedTransactionCoordinator(ABC):
    """分布式事务协调器接口
    
    支持两种模式：
    1. 2PC（两阶段提交）
    2. Saga 模式
    
    具体实现可以基于：
    - Seata
    - DTM
    - 自定义实现
    """
    
    @abstractmethod
    def begin_transaction(self, timeout: int = 30000) -> str:
        """开始分布式事务
        
        Args:
            timeout: 超时时间（毫秒）
        
        Returns:
            事务ID（XID）
        """
        pass
    
    @abstractmethod
    def register_participant(
        self,
        transaction_id: str,
        participant: TransactionParticipant
    ) -> None:
        """注册事务参与者"""
        pass
    
    @abstractmethod
    def commit(self, transaction_id: str) -> bool:
        """提交分布式事务"""
        pass
    
    @abstractmethod
    def rollback(self, transaction_id: str) -> bool:
        """回滚分布式事务"""
        pass
    
    @abstractmethod
    def get_status(self, transaction_id: str) -> DistributedTransactionState:
        """获取事务状态"""
        pass


class SagaStep(ABC):
    """Saga 步骤接口"""
    
    @property
    @abstractmethod
    def step_name(self) -> str:
        """步骤名称"""
        pass
    
    @abstractmethod
    def execute(self, context: dict) -> Any:
        """执行正向操作"""
        pass
    
    @abstractmethod
    def compensate(self, context: dict) -> None:
        """执行补偿操作"""
        pass


class SagaOrchestrator(ABC):
    """Saga 编排器接口
    
    使用示例:
        saga = SagaOrchestrator()
        saga.add_step(CreateOrderStep())
        saga.add_step(DeductInventoryStep())
        saga.add_step(ChargePaymentStep())
        
        result = saga.execute({"order_data": {...}})
    """
    
    @abstractmethod
    def add_step(self, step: SagaStep) -> 'SagaOrchestrator':
        """添加 Saga 步骤"""
        pass
    
    @abstractmethod
    def execute(self, context: dict) -> Any:
        """执行 Saga"""
        pass
    
    @abstractmethod
    def get_execution_status(self, saga_id: str) -> dict:
        """获取执行状态"""
        pass
```

### 2. 本地事务参与者实现示例

```python
from yweb.log import transaction_logger as logger

class LocalTransactionParticipant(TransactionParticipant):
    """本地数据库事务参与者
    
    将本地事务包装为分布式事务参与者
    """
    
    def __init__(self, session: Session, participant_id: str = None):
        self._session = session
        self._participant_id = participant_id or f"local_{id(session)}"
        self._savepoint = None
    
    @property
    def participant_id(self) -> str:
        return self._participant_id
    
    def prepare(self, transaction_id: str) -> bool:
        """准备阶段：创建 savepoint"""
        try:
            self._savepoint = self._session.begin_nested()
            return True
        except Exception as e:
            logger.error(f"Prepare failed: {e}")
            return False
    
    def commit(self, transaction_id: str) -> bool:
        """提交阶段：释放 savepoint"""
        try:
            if self._savepoint:
                self._savepoint.commit()
            self._session.commit()
            return True
        except Exception as e:
            logger.error(f"Commit failed: {e}")
            return False
    
    def rollback(self, transaction_id: str) -> bool:
        """回滚阶段：回滚到 savepoint"""
        try:
            if self._savepoint:
                self._savepoint.rollback()
            else:
                self._session.rollback()
            return True
        except Exception as e:
            logger.error(f"Rollback failed: {e}")
            return False
```

## 使用示例

### 1. 基本事务管理

```python
from yweb.orm import transaction_manager as tm, db_manager

# 方式1：上下文管理器
with tm.transaction() as tx:
    user = User(username="tom", email="tom@example.com")
    user.save()
    
    # 访问 user.id 时自动 flush，可直接使用
    profile = UserProfile(user_id=user.id, bio="Hello")
    profile.save()
    # 自动提交

# 方式2：装饰器
@tm.transactional()
def create_user_with_profile(user_data, profile_data):
    user = User(**user_data)
    user.save()
    
    # 访问 user.id 时自动 flush
    profile = UserProfile(user_id=user.id, **profile_data)
    profile.save()
    return user
```

### 2. 嵌套事务（Savepoints）

```python
from yweb.log import transaction_logger as logger

with tm.transaction() as tx:
    # 创建订单
    order = Order(customer_name="张三")
    order.add()
    
    # 使用保存点处理订单项
    for item_data in items:
        with tx.savepoint(f"item_{item_data['product_id']}") as sp:
            try:
                product = Product.get(item_data['product_id'])
                if product.stock < item_data['quantity']:
                    raise ValueError("库存不足")
                
                # 扣减库存
                product.stock -= item_data['quantity']
                product.update()
                
                # 创建订单项
                order_item = OrderItem(
                    order_id=order.id,
                    product_id=product.id,
                    quantity=item_data['quantity']
                )
                order_item.add()
            except ValueError as e:
                # 只回滚当前订单项，继续处理下一个
                sp.rollback()
                logger.warning(f"订单项处理失败: {e}")
                continue
    
    # 外层事务继续
    order.status = "completed"
    order.update()
```

### 3. 事务钩子

```python
# 方式1：内联钩子
with tm.transaction() as tx:
    user = User(username="tom")
    user.add()
    
    @tx.after_commit
    def send_welcome_email(ctx):
        # 提交成功后发送欢迎邮件
        email_service.send_welcome(ctx.data['user_email'])
    
    tx.data['user_email'] = user.email

# 方式2：全局钩子（类方式）
class AuditLogHook(TransactionHook):
    """审计日志钩子"""
    
    @property
    def hook_type(self):
        return TransactionHookType.AFTER_COMMIT
    
    @property
    def priority(self):
        return 10  # 优先执行
    
    def execute(self, context):
        # 记录审计日志
        audit_log = AuditLog(
            action="transaction_commit",
            timestamp=datetime.now()
        )
        # 注意：这里需要用新的 session
        with tm.transaction(propagation=TransactionPropagation.REQUIRES_NEW):
            audit_log.save()

# 注册全局钩子
tm.register_global_hook(AuditLogHook())

# 方式3：全局钩子（装饰器方式，更简洁）
@tm.global_hooks.before_commit
def validate_all_changes():
    """所有事务提交前的验证"""
    logger.debug("事务即将提交...")

@tm.global_hooks.after_commit
def clear_query_cache():
    """所有事务提交后清理缓存"""
    cache.invalidate_changed_entities()

@tm.global_hooks.after_rollback
def log_rollback():
    """记录回滚事件"""
    logger.warning("事务已回滚")
```

### 4. Service 层模式

```python
class OrderService:
    def __init__(self):
        self.tm = transaction_manager
    
    @tm.transactional()
    def create_order(self, customer_name: str, items: list) -> Order:
        """创建订单（事务性方法）"""
        order = Order(customer_name=customer_name, status="pending")
        order.save()
        
        # 访问 order.id 时自动 flush
        total_amount = 0
        for item_data in items:
            total_amount += self._process_order_item(order.id, item_data)
        
        order.total_amount = total_amount
        order.status = "completed"
        order.save()
        
        return order
    
    @tm.transactional(propagation=TransactionPropagation.NESTED)
    def _process_order_item(self, order_id: int, item_data: dict) -> float:
        """处理订单项（嵌套事务）
        
        如果单个订单项处理失败，只回滚该项，不影响整个订单
        """
        product = Product.get(item_data['product_id'])
        
        if product.stock < item_data['quantity']:
            raise InsufficientStockError(f"产品 {product.name} 库存不足")
        
        product.stock -= item_data['quantity']
        product.update()
        
        order_item = OrderItem(
            order_id=order_id,
            product_id=product.id,
            quantity=item_data['quantity'],
            price=product.price
        )
        order_item.add()
        
        return product.price * item_data['quantity']
```

## 模块结构

```
yweb/orm/
├── __init__.py                 # 导出事务相关 API
├── transaction/
│   ├── __init__.py
│   ├── context.py              # TransactionContext, SavepointContext
│   ├── manager.py              # TransactionManager
│   ├── hooks.py                # TransactionHook, 钩子类型
│   ├── propagation.py          # TransactionPropagation
│   └── distributed/            # 分布式事务（预留）
│       ├── __init__.py
│       ├── coordinator.py      # 协调器接口
│       ├── participant.py      # 参与者接口
│       └── saga.py             # Saga 模式接口
```

## API 导出

```python
# yweb/orm/__init__.py 新增导出
from .transaction import (
    # 核心类
    TransactionManager,
    TransactionContext,
    TransactionState,
    
    # 钩子
    TransactionHook,
    TransactionHookType,
    
    # 传播行为
    TransactionPropagation,
    
    # 全局单例
    transaction_manager,
    
    # 便捷函数
    transactional,  # 装饰器快捷方式
)

# 分布式事务（预留）
from .transaction.distributed import (
    DistributedTransactionCoordinator,
    TransactionParticipant,
    SagaOrchestrator,
    SagaStep,
)
```

## 日志配置

事务模块使用预定义的日志器，需要在 `yweb/log/logger.py` 中添加以下定义：

```python
# yweb/log/logger.py 新增预定义日志器

# ORM 相关日志器
orm_logger = logging.getLogger("yweb.orm")
transaction_logger = logging.getLogger("yweb.orm.transaction")
```

同时在 `yweb/log/__init__.py` 中导出：

```python
# yweb/log/__init__.py 新增导出
from .logger import (
    # ... 现有导出 ...
    orm_logger,
    transaction_logger,
)

__all__ = [
    # ... 现有导出 ...
    "orm_logger",
    "transaction_logger",
]
```

### 日志层级关系

```
yweb                          # 根日志器
├── yweb.api                  # API 日志
├── yweb.auth                 # 认证日志
├── yweb.sql                  # SQL 日志
└── yweb.orm                  # ORM 日志（orm_logger）
    └── yweb.orm.transaction  # 事务日志（transaction_logger）
```

事务日志器 `yweb.orm.transaction` 是 `yweb.orm` 的子日志器，会自动继承父日志器的配置。

## 与现有代码的兼容性

### 现有 API 保持不变

```python
# 以下 API 继续正常工作
user.save(commit=True)
user.add(commit=True)
session.commit()
session.rollback()

# Service 层模式继续支持
class MyService:
    def create(self):
        try:
            # 操作
            session.commit()
        except:
            session.rollback()
            raise
```

### 混合使用

```python
# 在事务上下文中使用
with tm.transaction() as tx:
    user = User(username="tom")
    user.save()
    
    # 访问 user.id 时自动 flush
    profile = UserProfile(user_id=user.id)
    profile.save()
    # 上下文结束时自动提交
```

### 事务内提交抑制（Commit Suppression）

当代码运行在事务上下文中时，`commit=True` 参数会被**自动忽略**，所有提交由事务管理器统一控制。

#### 设计原理

```python
# 业务方法（可能被多处调用）
def create_user(data):
    user = User(**data)
    user.save(commit=True)  # 独立调用时会提交
    return user

# 独立调用：commit=True 正常生效
user = create_user({"name": "tom"})  # ✅ 立即提交

# 在事务中调用：commit=True 被自动忽略
with tm.transaction() as tx:
    user = create_user({"name": "tom"})      # commit=True 被忽略
    profile = create_profile({"bio": "hi"})  # commit=True 被忽略
    # 统一提交，保证原子性
```

#### 实现机制

```python
# TransactionContext 中
class TransactionContext:
    def __init__(self, ...):
        self._suppress_commit = True  # 默认抑制内部提交
    
    @property
    def suppress_commit(self) -> bool:
        """是否抑制内部提交"""
        return self._suppress_commit

# CoreModel 中修改 __is_commit 方法
def __is_commit(self, commit=False):
    """根据参数决定是否提交"""
    if commit:
        # 检查是否在事务上下文中
        ctx = _current_transaction.get()
        if ctx and ctx.is_active and ctx.suppress_commit:
            # 在事务中且启用了抑制，忽略 commit=True
            logger.debug("commit=True 被事务上下文抑制")
            return
        self.session.commit()
```

#### 优缺点

| 优点 | 说明 |
|------|------|
| 向后兼容 | 现有代码无需修改，被事务包裹后自动变成事务安全的 |
| 降低心智负担 | 开发者不用记住"在事务中要用 commit=False" |
| 防止意外提交 | 避免内层代码意外破坏外层事务的原子性 |
| 渐进式重构 | 可以逐步将老代码迁移到事务管理，无需一次性改完 |

| 缺点 | 说明 |
|------|------|
| 隐式行为 | 代码字面意思和实际行为可能不一致 |
| 调试注意 | 需要通过日志了解 commit 被抑制的情况 |

#### 逃逸机制

某些场景（如审计日志）确实需要独立提交，可以使用以下方式：

**方式1：使用 REQUIRES_NEW 传播行为（推荐）**

```python
with tm.transaction() as tx:
    user.save(commit=True)  # 被抑制
    
    # 审计日志需要独立提交，使用新事务
    with tm.transaction(propagation=TransactionPropagation.REQUIRES_NEW) as audit_tx:
        audit_log = AuditLog(action="create_user")
        audit_log.save(commit=True)  # ✅ 在新事务中正常提交
    
    profile.save(commit=True)  # 继续被抑制
    # 主事务统一提交
```

**方式2：临时禁用抑制**

```python
with tm.transaction() as tx:
    user.save(commit=True)  # 被抑制
    
    # 临时禁用抑制
    with tx.allow_commit():
        critical_log.save(commit=True)  # ✅ 正常提交
    
    profile.save(commit=True)  # 继续被抑制
```

**方式3：强制提交方法**

```python
with tm.transaction() as tx:
    user.save()
    
    # 强制提交当前所有变更（慎用）
    tx.force_flush_and_commit()
    
    profile.save()
```

#### 配置控制

```python
# 全局禁用提交抑制（不推荐，仅用于调试）
with tm.transaction(suppress_commit=False) as tx:
    user.save(commit=True)  # 正常提交（危险！）
```

## 配置选项

```python
# 全局配置
class TransactionConfig:
    """事务配置"""
    
    # 默认超时时间（秒）
    default_timeout: int = 30
    
    # 是否启用钩子
    hooks_enabled: bool = True
    
    # 是否记录事务日志
    logging_enabled: bool = True
    
    # 日志级别
    log_level: str = "DEBUG"
    
    # Savepoint 前缀
    savepoint_prefix: str = "sp_"
    
    # 是否在事务中抑制 commit=True（推荐开启）
    suppress_commit_in_transaction: bool = True
    
    # 抑制 commit 时是否输出日志提示
    log_suppressed_commit: bool = True

# 初始化时配置
def init_transaction(config: TransactionConfig = None):
    """初始化事务管理器"""
    if config:
        transaction_manager.configure(config)
```

## 最佳实践

### 1. 合理使用传播行为

```python
# REQUIRED（默认）：大多数情况
@tm.transactional()
def business_method():
    pass

# REQUIRES_NEW：独立事务（如日志记录）
@tm.transactional(propagation=TransactionPropagation.REQUIRES_NEW)
def audit_log():
    pass

# NESTED：允许部分回滚
@tm.transactional(propagation=TransactionPropagation.NESTED)
def process_item():
    pass
```

### 2. 钩子使用建议

```python
# after_commit：发送通知、更新缓存
@tx.after_commit
def update_cache(ctx):
    cache.invalidate(f"user:{ctx.data['user_id']}")

# before_commit：数据验证
@tx.before_commit
def validate(ctx):
    if not ctx.data.get('validated'):
        raise ValidationError("数据未验证")

# on_error：错误处理、告警
@tx.on_error
def handle_error(ctx, error):
    alert_service.send(f"事务失败: {error}")
```

### 3. 避免长事务

```python
# 不推荐：在一个大事务中处理所有数据
with tm.transaction() as tx:
    for item in large_list:
        # 业务逻辑处理...
        item.status = "processed"
        item.update()
    # 问题：事务持有时间长，锁竞争严重，数据库连接占用久

# 推荐：分批处理，每批独立事务
def chunks(lst, size):
    """将列表分割成指定大小的批次"""
    for i in range(0, len(lst), size):
        yield lst[i:i + size]

for batch in chunks(large_list, 100):
    with tm.transaction() as tx:
        for item in batch:
            # 业务逻辑处理...
            item.status = "processed"
            item.update()
        # 每 100 条提交一次，释放锁和连接
```

### 4. 嵌套事务异常处理（重要）

> ⚠️ **警告**：当使用嵌套事务时，如果在内层捕获异常后继续执行而不处理，可能导致 session 状态不一致！

#### 问题场景

```python
# ❌ 错误示例：可能导致数据不一致
with tm.transaction() as tx:
    user = User(name="tom")
    user.add()
    
    try:
        with tm.transaction():  # 嵌套事务（REQUIRED 传播）
            # 假设这里触发唯一键冲突或其他数据库错误
            duplicate_user = User(name="tom")
            duplicate_user.add()
    except Exception:
        pass  # ❌ 仅捕获不处理，session 状态可能已损坏
    
    # ⚠️ 此时 session 可能处于不一致状态
    profile = Profile(user_id=user.id)
    profile.add()  # 可能失败或行为异常
# commit - 可能提交不一致的数据或失败
```

#### 为什么会这样？

1. **嵌套事务共享 session**：REQUIRED/MANDATORY/SUPPORTS 传播行为下，内外层使用同一个 session
2. **异常后 session 状态不明确**：数据库操作失败后，session 中可能存在脏数据或处于错误状态
3. **nesting_level 正确但数据不一致**：框架正确管理了嵌套层级，但无法自动修复用户捕获异常后的 session 状态

#### 正确做法

**方式 1：重新抛出异常（推荐）**

```python
# ✅ 让异常自然传播，外层事务会自动回滚
with tm.transaction() as tx:
    user = User(name="tom")
    user.add()
    
    with tm.transaction():  # 如果这里抛出异常
        risky_operation()
    # 异常会传播到外层，触发整个事务回滚
```

**方式 2：捕获后主动回滚**

```python
# ✅ 捕获异常后主动回滚整个事务
with tm.transaction() as tx:
    user = User(name="tom")
    user.add()
    
    try:
        with tm.transaction():
            risky_operation()
    except Exception as e:
        tx.rollback()  # ✅ 主动回滚整个事务
        raise  # ✅ 重新抛出或处理
```

**方式 3：使用 savepoint 隔离风险操作（推荐）**

```python
# ✅ 使用保存点，内层失败不影响外层
with tm.transaction() as tx:
    user = User(name="tom")
    user.add()
    
    try:
        with tx.savepoint():  # ✅ 使用保存点而非嵌套事务
            risky_operation()
    except Exception as e:
        # 保存点自动回滚，外层事务继续
        logger.warning(f"风险操作失败，已回滚: {e}")
    
    # 外层事务正常继续
    profile = Profile(user_id=user.id)
    profile.add()
# 正常提交 user 和 profile
```

#### 总结

| 场景 | 处理方式 | 结果 |
|------|----------|------|
| 内层异常，不捕获 | 让异常传播 | ✅ 外层自动回滚 |
| 内层异常，捕获后重新抛出 | `raise` | ✅ 外层自动回滚 |
| 内层异常，捕获后主动回滚 | `tx.rollback()` | ✅ 事务回滚 |
| 内层异常，使用 savepoint | `with tx.savepoint()` | ✅ 只回滚保存点 |
| 内层异常，仅捕获不处理 | `except: pass` | ❌ **数据可能不一致** |

## 异常处理

### 自定义异常体系

```python
class TransactionError(Exception):
    """事务错误基类"""
    pass


class TransactionNotActiveError(TransactionError):
    """事务未激活错误"""
    pass


class TransactionAlreadyCommittedError(TransactionError):
    """事务已提交错误"""
    pass


class TransactionAlreadyRolledBackError(TransactionError):
    """事务已回滚错误"""
    pass


class SavepointError(TransactionError):
    """保存点错误"""
    pass


class SavepointNotFoundError(SavepointError):
    """保存点不存在错误"""
    pass


class HookExecutionError(TransactionError):
    """钩子执行错误
    
    包含钩子名称和原始异常，便于调试
    """
    def __init__(self, hook_name: str, original_error: Exception):
        self.hook_name = hook_name
        self.original_error = original_error
        super().__init__(f"钩子 '{hook_name}' 执行失败: {original_error}")


class PropagationError(TransactionError):
    """事务传播错误"""
    pass
```

### 异常处理策略

| 场景 | 处理方式 | 说明 |
|------|----------|------|
| before_commit 钩子异常 | 阻止提交，回滚事务 | 钩子失败意味着业务逻辑不满足 |
| after_commit 钩子异常 | 仅记录日志，不影响已提交的事务 | 事务已持久化，钩子失败不应影响 |
| after_rollback 钩子异常 | 仅记录日志，不影响回滚结果 | 回滚已完成，钩子失败仅记录 |
| 保存点回滚 | 仅回滚保存点，外层事务继续 | 内层失败不影响外层 |
| 数据库连接异常 | 标记事务为 FAILED，触发回滚 | 连接问题需要重试 |
| 死锁异常 | 自动重试（可配置次数） | 数据库死锁可通过重试解决 |

### 钩子异常处理实现

```python
class TransactionHooks:
    """钩子执行时的异常处理"""
    
    def _execute_before_commit(self) -> None:
        """执行 before_commit 钩子
        
        异常处理：任何钩子失败都会阻止提交
        """
        for hook in self._before_commit:
            try:
                hook()
            except Exception as e:
                # before_commit 异常会阻止提交
                raise HookExecutionError(hook.__name__, e) from e
    
    def _execute_after_commit(self) -> None:
        """执行 after_commit 钩子
        
        异常处理：钩子失败仅记录日志，不影响已提交的事务
        """
        errors = []
        for hook in self._after_commit:
            try:
                hook()
            except Exception as e:
                # after_commit 异常仅记录，不抛出
                logger.error(f"after_commit 钩子 '{hook.__name__}' 执行失败: {e}")
                errors.append(HookExecutionError(hook.__name__, e))
        
        if errors:
            logger.warning(f"{len(errors)} 个 after_commit 钩子执行失败")
    
    def _execute_after_rollback(self) -> None:
        """执行 after_rollback 钩子
        
        异常处理：钩子失败仅记录日志
        """
        for hook in self._after_rollback:
            try:
                hook()
            except Exception as e:
                logger.error(f"after_rollback 钩子 '{hook.__name__}' 执行失败: {e}")
```

### 死锁重试装饰器

```python
from functools import wraps
from sqlalchemy.exc import OperationalError
import time

def transaction_with_retry(
    max_retries: int = 3,
    retry_delay: float = 0.1,
    retry_on: tuple = (OperationalError,),
    backoff_multiplier: float = 2.0
):
    """带重试机制的事务装饰器
    
    Args:
        max_retries: 最大重试次数
        retry_delay: 初始重试间隔（秒）
        retry_on: 需要重试的异常类型
        backoff_multiplier: 退避乘数（指数退避）
    
    使用示例:
        @transaction_with_retry(max_retries=3)
        def transfer_money(from_account, to_account, amount):
            from_account.balance -= amount
            to_account.balance += amount
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            last_error = None
            current_delay = retry_delay
            
            for attempt in range(max_retries + 1):
                try:
                    with transaction_manager.transaction() as tx:
                        result = func(*args, **kwargs)
                        return result
                except retry_on as e:
                    last_error = e
                    if attempt < max_retries:
                        logger.warning(
                            f"事务失败 (尝试 {attempt + 1}/{max_retries + 1}), "
                            f"{current_delay:.2f}s 后重试: {e}"
                        )
                        time.sleep(current_delay)
                        current_delay *= backoff_multiplier  # 指数退避
                    else:
                        logger.error(f"事务重试 {max_retries} 次后仍失败")
                        raise
            raise last_error
        return wrapper
    return decorator


# 使用示例
@transaction_with_retry(max_retries=3, retry_on=(OperationalError,))
def transfer_money(from_id: int, to_id: int, amount: float):
    """转账操作（带死锁重试）"""
    from_account = Account.get(from_id)
    to_account = Account.get(to_id)
    
    if from_account.balance < amount:
        raise InsufficientFundsError("余额不足")
    
    from_account.balance -= amount
    to_account.balance += amount
    
    from_account.update()
    to_account.update()
```

### 异常处理使用示例

```python
from yweb.orm import transaction_manager as tm
from yweb.orm.transaction import TransactionError, HookExecutionError

# 示例 1：捕获钩子异常
try:
    with tm.transaction() as tx:
        user = User(username="tom")
        user.add()
        
        @tx.before_commit
        def validate_user(ctx):
            if not user.email:
                raise ValueError("邮箱是必填项")

except HookExecutionError as e:
    logger.error(f"钩子失败: {e.hook_name}, 原因: {e.original_error}")
except TransactionError as e:
    logger.error(f"事务失败: {e}")


# 示例 2：保存点异常隔离
with tm.transaction() as tx:
    user = User(username="tom")
    user.add()
    
    try:
        with tx.savepoint() as sp:
            # 这里的异常只会回滚保存点
            risky_operation()
    except Exception as e:
        logger.warning(f"保存点已回滚: {e}")
        # 外层事务继续
    
    # 用户仍然会被创建
```

## 测试支持

```python
# conftest.py
import pytest
from yweb.orm import transaction_manager

@pytest.fixture
def tx():
    """提供测试用的事务上下文"""
    with transaction_manager.transaction(auto_commit=False) as ctx:
        yield ctx
        ctx.rollback()  # 测试后回滚

# 测试用例
def test_create_user(tx):
    user = User(username="test")
    user.add()
    
    assert user.id is not None
    # 自动回滚，不影响数据库
```

## 验证计划

### 单元测试

1. **基础事务测试**
   - 正常提交
   - 异常回滚
   - 手动回滚
   - 事务状态转换

2. **嵌套事务测试**
   - 保存点创建和提交
   - 保存点回滚不影响外层
   - 多层嵌套保存点
   - 命名保存点

3. **钩子测试**
   - before_commit 执行顺序和优先级
   - after_commit 执行（含异常场景）
   - after_rollback 执行
   - 钩子异常处理
   - 全局钩子

4. **传播行为测试**
   - REQUIRED 行为
   - REQUIRES_NEW 行为
   - NESTED 行为
   - MANDATORY 行为

5. **提交抑制测试**
   - commit=True 在事务中被抑制
   - allow_commit() 临时允许
   - REQUIRES_NEW 中正常提交

### 集成测试

1. 与 FastAPI 依赖注入集成
2. 与软删除功能集成
3. 与历史记录功能集成
4. 并发事务测试
5. 死锁重试测试

## 实现步骤

| 步骤 | 任务 | 优先级 |
|------|------|--------|
| 1 | 创建 `yweb/orm/transaction/` 目录结构 | P0 |
| 2 | 实现 `TransactionState` 枚举 | P0 |
| 3 | 实现异常类体系 | P0 |
| 4 | 实现 `TransactionHooks` 钩子系统 | P0 |
| 5 | 实现 `SavepointContext` 保存点类 | P0 |
| 6 | 实现 `TransactionContext` 事务上下文类 | P0 |
| 7 | 实现 `TransactionManager` 事务管理器 | P0 |
| 8 | 实现 `TransactionPropagation` 传播行为 | P0 |
| 9 | 实现提交抑制机制（修改 CoreModel） | P1 |
| 10 | 实现 `transaction_with_retry` 重试装饰器 | P1 |
| 11 | 更新 `yweb/orm/__init__.py` 导出 | P0 |
| 12 | 更新 `yweb/log/logger.py` 添加日志器 | P0 |
| 13 | 定义分布式事务扩展接口 | P2 |
| 14 | 编写单元测试 | P0 |
| 15 | 编写集成测试 | P1 |
| 16 | 更新文档 | P1 |

## 下一步

- [17_分布式事务实现](17_distributed_transaction.md) - 分布式事务具体实现方案
- [11_事务管理](11_transaction.md) - 基础事务管理
- [12_数据库会话](12_db_session.md) - 会话管理

## 参考资料

- [SQLAlchemy Transaction Management](https://docs.sqlalchemy.org/en/20/orm/session_transaction.html)
- [Spring Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Saga Pattern](https://microservices.io/patterns/data/saga.html)
- [Two-Phase Commit](https://en.wikipedia.org/wiki/Two-phase_commit_protocol)
