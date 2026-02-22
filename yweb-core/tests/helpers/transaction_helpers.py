"""事务管理器测试辅助工具

提供测试专用的事务管理器辅助函数
"""

from yweb.orm.transaction import TransactionManager


def reset_transaction_manager(tm: TransactionManager) -> None:
    """重置事务管理器状态
    
    Args:
        tm: 要重置的事务管理器实例
        
    警告：此函数仅用于测试环境，不应在生产代码中使用
    """
    tm._initialized = False
    tm._session_factory = None


def is_transaction_manager_initialized(tm: TransactionManager) -> bool:
    """检查事务管理器是否已初始化
    
    Args:
        tm: 要检查的事务管理器实例
        
    Returns:
        bool: 是否已初始化
    """
    return tm._initialized
