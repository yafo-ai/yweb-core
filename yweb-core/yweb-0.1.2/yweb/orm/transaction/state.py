"""事务状态枚举

定义事务的生命周期状态
"""

from enum import Enum


class TransactionState(str, Enum):
    """事务状态
    
    状态转换图:
    
        INACTIVE → ACTIVE → COMMITTED
                      ↓
                  ROLLED_BACK
                      ↓
                   FAILED
    
    状态说明:
        - INACTIVE: 事务未开始或已结束
        - ACTIVE: 事务进行中
        - COMMITTED: 事务已成功提交
        - ROLLED_BACK: 事务已回滚
        - FAILED: 事务执行失败
    """
    
    INACTIVE = "inactive"
    """未激活状态：事务尚未开始"""
    
    ACTIVE = "active"
    """活跃状态：事务正在进行中"""
    
    COMMITTED = "committed"
    """已提交状态：事务已成功提交到数据库"""
    
    ROLLED_BACK = "rolled_back"
    """已回滚状态：事务已被回滚"""
    
    FAILED = "failed"
    """失败状态：事务执行过程中发生错误"""
    
    def is_terminal(self) -> bool:
        """判断是否为终态（不可再转换的状态）"""
        return self in (
            TransactionState.COMMITTED,
            TransactionState.ROLLED_BACK,
            TransactionState.FAILED
        )
    
    def can_commit(self) -> bool:
        """判断是否可以提交"""
        return self == TransactionState.ACTIVE
    
    def can_rollback(self) -> bool:
        """判断是否可以回滚"""
        return self in (TransactionState.ACTIVE, TransactionState.FAILED)
