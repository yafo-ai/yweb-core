"""事务异常类

定义事务管理相关的异常层次结构
"""

from typing import Optional


class TransactionError(Exception):
    """事务错误基类
    
    所有事务相关的异常都继承自此类
    """
    pass


class TransactionNotActiveError(TransactionError):
    """事务未激活错误
    
    当尝试在非活跃状态的事务上执行操作时抛出
    """
    
    def __init__(self, message: str = "事务未激活"):
        super().__init__(message)


class TransactionAlreadyCommittedError(TransactionError):
    """事务已提交错误
    
    当尝试对已提交的事务执行操作时抛出
    """
    
    def __init__(self, message: str = "事务已提交，无法执行此操作"):
        super().__init__(message)


class TransactionAlreadyRolledBackError(TransactionError):
    """事务已回滚错误
    
    当尝试对已回滚的事务执行操作时抛出
    """
    
    def __init__(self, message: str = "事务已回滚，无法执行此操作"):
        super().__init__(message)


class SavepointError(TransactionError):
    """保存点错误基类"""
    pass


class SavepointNotFoundError(SavepointError):
    """保存点不存在错误
    
    当尝试回滚到不存在的保存点时抛出
    """
    
    def __init__(self, savepoint_name: str):
        self.savepoint_name = savepoint_name
        super().__init__(f"保存点 '{savepoint_name}' 不存在")


class SavepointAlreadyReleasedError(SavepointError):
    """保存点已释放错误"""
    
    def __init__(self, savepoint_name: str):
        self.savepoint_name = savepoint_name
        super().__init__(f"保存点 '{savepoint_name}' 已释放")


class HookExecutionError(TransactionError):
    """钩子执行错误
    
    当事务钩子执行失败时抛出，包含钩子名称和原始异常
    """
    
    def __init__(self, hook_name: str, original_error: Exception):
        self.hook_name = hook_name
        self.original_error = original_error
        super().__init__(f"钩子 '{hook_name}' 执行失败: {original_error}")
    
    def __repr__(self) -> str:
        return f"HookExecutionError(hook_name={self.hook_name!r}, original_error={self.original_error!r})"


class PropagationError(TransactionError):
    """事务传播错误
    
    当事务传播行为不满足条件时抛出
    """
    
    def __init__(self, propagation: str, message: str):
        self.propagation = propagation
        super().__init__(f"[{propagation}] {message}")


class CommitSuppressedError(TransactionError):
    """提交被抑制错误（内部使用）
    
    当在事务上下文中尝试提交但被抑制时使用
    注意：这个异常通常不会被抛出，仅用于内部标记
    """
    pass
