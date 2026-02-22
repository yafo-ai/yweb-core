"""事务钩子系统

提供事务生命周期的钩子机制
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Callable, List, Dict, Any, Optional, TYPE_CHECKING

from yweb.log import get_logger

from .exceptions import HookExecutionError

if TYPE_CHECKING:
    from .context import TransactionContext

logger = get_logger("yweb.orm.transaction")


class TransactionHookType(str, Enum):
    """事务钩子类型"""
    
    BEFORE_BEGIN = "before_begin"
    """事务开始前"""
    
    AFTER_BEGIN = "after_begin"
    """事务开始后"""
    
    BEFORE_COMMIT = "before_commit"
    """提交前（失败会阻止提交）"""
    
    AFTER_COMMIT = "after_commit"
    """提交后（失败不影响已提交的事务）"""
    
    BEFORE_ROLLBACK = "before_rollback"
    """回滚前"""
    
    AFTER_ROLLBACK = "after_rollback"
    """回滚后"""
    
    ON_ERROR = "on_error"
    """发生错误时"""


class TransactionHook(ABC):
    """事务钩子基类
    
    用户可以继承此类实现自定义钩子逻辑
    
    使用示例:
        class AuditLogHook(TransactionHook):
            @property
            def hook_type(self):
                return TransactionHookType.AFTER_COMMIT
            
            @property
            def priority(self):
                return 10  # 数字越小越先执行
            
            def execute(self, context):
                audit_log.save()
        
        tm.register_global_hook(AuditLogHook())
    """
    
    @property
    @abstractmethod
    def hook_type(self) -> TransactionHookType:
        """钩子类型"""
        pass
    
    @property
    def priority(self) -> int:
        """执行优先级（数字越小越先执行）
        
        默认优先级为 100
        """
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
        
        默认只记录日志，子类可以覆盖实现自定义错误处理
        
        Args:
            context: 事务上下文
            error: 发生的异常
        """
        logger.error(f"钩子 {self.name} 执行出错: {error}")


class TransactionHooks:
    """事务钩子管理器
    
    管理单个事务的钩子注册和执行
    """
    
    def __init__(self):
        # 类钩子（TransactionHook 子类）
        self._hooks: Dict[TransactionHookType, List[TransactionHook]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
        # 函数钩子（直接注册的函数）
        self._func_hooks: Dict[TransactionHookType, List[Callable]] = {
            hook_type: [] for hook_type in TransactionHookType
        }
    
    def register(self, hook: TransactionHook) -> None:
        """注册钩子对象"""
        self._hooks[hook.hook_type].append(hook)
        self._hooks[hook.hook_type].sort(key=lambda h: h.priority)
    
    def register_func(self, hook_type: TransactionHookType, func: Callable) -> None:
        """注册函数钩子"""
        self._func_hooks[hook_type].append(func)
    
    def unregister(self, hook: TransactionHook) -> None:
        """取消注册钩子"""
        if hook in self._hooks[hook.hook_type]:
            self._hooks[hook.hook_type].remove(hook)
    
    def clear(self) -> None:
        """清空所有钩子"""
        for hook_type in TransactionHookType:
            self._hooks[hook_type].clear()
            self._func_hooks[hook_type].clear()
    
    def execute(
        self,
        hook_type: TransactionHookType,
        context: 'TransactionContext',
        error: Optional[Exception] = None,
        raise_on_error: bool = False
    ) -> List[Exception]:
        """执行指定类型的所有钩子
        
        Args:
            hook_type: 钩子类型
            context: 事务上下文
            error: 触发钩子的异常（用于 ON_ERROR 钩子）
            raise_on_error: 是否在钩子执行失败时抛出异常
        
        Returns:
            执行过程中发生的异常列表
        """
        errors = []
        
        # 执行类钩子
        for hook in self._hooks[hook_type]:
            try:
                if hook_type == TransactionHookType.ON_ERROR:
                    hook.execute(context, error)
                else:
                    hook.execute(context)
            except Exception as e:
                hook_error = HookExecutionError(hook.name, e)
                errors.append(hook_error)
                logger.error(f"钩子 {hook.name} 执行失败: {e}")
                hook.on_error(context, e)
                
                if raise_on_error:
                    raise hook_error from e
        
        # 执行函数钩子
        for func in self._func_hooks[hook_type]:
            try:
                if hook_type == TransactionHookType.ON_ERROR:
                    func(context, error)
                else:
                    func(context)
            except Exception as e:
                func_name = getattr(func, '__name__', str(func))
                hook_error = HookExecutionError(func_name, e)
                errors.append(hook_error)
                logger.error(f"钩子函数 {func_name} 执行失败: {e}")
                
                if raise_on_error:
                    raise hook_error from e
        
        return errors
    
    def execute_before_commit(self, context: 'TransactionContext') -> None:
        """执行 before_commit 钩子
        
        before_commit 钩子失败会阻止提交，因此会抛出异常
        """
        self.execute(TransactionHookType.BEFORE_COMMIT, context, raise_on_error=True)
    
    def execute_after_commit(self, context: 'TransactionContext') -> List[Exception]:
        """执行 after_commit 钩子
        
        after_commit 钩子失败不影响已提交的事务，仅记录日志
        """
        return self.execute(TransactionHookType.AFTER_COMMIT, context, raise_on_error=False)
    
    def execute_before_rollback(self, context: 'TransactionContext') -> List[Exception]:
        """执行 before_rollback 钩子"""
        return self.execute(TransactionHookType.BEFORE_ROLLBACK, context, raise_on_error=False)
    
    def execute_after_rollback(self, context: 'TransactionContext') -> List[Exception]:
        """执行 after_rollback 钩子"""
        return self.execute(TransactionHookType.AFTER_ROLLBACK, context, raise_on_error=False)
    
    def execute_on_error(
        self,
        context: 'TransactionContext',
        error: Exception
    ) -> List[Exception]:
        """执行错误处理钩子"""
        return self.execute(TransactionHookType.ON_ERROR, context, error=error, raise_on_error=False)
