"""事务传播行为

定义当方法在已有事务上下文中被调用时的行为
"""

from enum import Enum


class TransactionPropagation(str, Enum):
    """事务传播行为
    
    定义嵌套调用时事务的处理方式，类似 Spring 的事务传播机制
    
    使用示例:
        @tm.transactional(propagation=TransactionPropagation.REQUIRED)
        def service_a():
            pass
        
        @tm.transactional(propagation=TransactionPropagation.REQUIRES_NEW)
        def service_b():
            # 总是在新事务中执行
            pass
    """
    
    REQUIRED = "required"
    """如果当前有事务则加入，没有则新建（默认）
    
    最常用的传播行为：
    - 如果调用者已在事务中，则加入该事务
    - 如果调用者没有事务，则创建新事务
    """
    
    REQUIRES_NEW = "requires_new"
    """总是新建事务（使用 savepoint 实现嵌套）
    
    适用场景：
    - 审计日志：无论主事务是否成功，都要记录
    - 独立操作：不受外层事务影响
    """
    
    SUPPORTS = "supports"
    """如果当前有事务则加入，没有则以非事务方式执行
    
    适用场景：
    - 查询操作：有事务则保证一致性，无事务也可执行
    """
    
    NOT_SUPPORTED = "not_supported"
    """以非事务方式执行，如果当前有事务则挂起
    
    适用场景：
    - 需要独立执行的操作，不希望被事务影响
    """
    
    MANDATORY = "mandatory"
    """必须在事务中执行，否则抛出异常
    
    适用场景：
    - 必须由上层方法开启事务的内部方法
    """
    
    NEVER = "never"
    """必须不在事务中执行，否则抛出异常
    
    适用场景：
    - 不允许在事务中调用的方法
    """
    
    NESTED = "nested"
    """如果当前有事务则创建嵌套事务（savepoint）
    
    与 REQUIRES_NEW 的区别：
    - NESTED：外层回滚会一起回滚嵌套事务
    - REQUIRES_NEW：外层回滚不影响已提交的新事务
    """
