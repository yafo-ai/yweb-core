"""当前用户追踪模块（Session 方式）

提供历史记录审计功能，通过 session.info 追踪操作者的 user_id。

核心组件：
- CurrentUserPlugin: sqlalchemy-history 插件，自动将 user_id 写入 Transaction 表
- 便捷函数：set_user, get_user_id, clear_user（基于 session.info）

使用方式：
    方式1（推荐）：使用 CurrentUserMiddleware 中间件，自动追踪
    
        from yweb.middleware import CurrentUserMiddleware
        app.add_middleware(CurrentUserMiddleware, jwt_manager=jwt_manager)
    
    方式2：手动设置（适用于后台任务等场景）
    
        from yweb.orm.history import set_user, clear_user
        
        set_user(session, user)  # 传入用户对象或用户ID
        # 执行操作...
        clear_user(session)

注意：
    - ContextVar 方式的函数（set_current_user_id 等）在 yweb.middleware.current_user 中
    - Session 方式的函数（set_user 等）在本模块中
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional, Union

import sqlalchemy as sa
from sqlalchemy_history.plugins import Plugin

if TYPE_CHECKING:
    from sqlalchemy.orm import Session


# ============================================================================
# CurrentUserPlugin - sqlalchemy-history 插件
# ============================================================================



class CurrentUserPlugin(Plugin):
    """
    当前用户追踪插件

    使用方式：
        # 方式1：自动查找User类
        make_versioned(plugins=[CurrentUserPlugin()])

        # 方式2：手动指定user_cls
        make_versioned(user_cls="MyUser", plugins=[CurrentUserPlugin()])

        # 设置当前用户
        session.info['user_id'] = user.id

        # 或使用便捷函数
        set_user(session, user)
    """

    def transaction_args(self, uow, session):
        """
        从session.info中获取user_id

        支持的key（按优先级）：
        1. user_id - 直接的用户ID
        2. current_user_id - 当前用户ID
        3. user - 用户对象（自动提取主键）
        4. current_user - 当前用户对象（自动提取主键）
        """
        # 尝试获取user_id
        user_id = session.info.get('user_id')
        if user_id is not None:
            return {'user_id': user_id}

        # 尝试获取current_user_id
        user_id = session.info.get('current_user_id')
        if user_id is not None:
            return {'user_id': user_id}

        # 尝试从user对象获取主键
        user = session.info.get('user')
        if user is not None:
            user_id = self._extract_primary_key(user)
            if user_id is not None:
                return {'user_id': user_id}

        # 尝试从current_user对象获取主键
        user = session.info.get('current_user')
        if user is not None:
            user_id = self._extract_primary_key(user)
            if user_id is not None:
                return {'user_id': user_id}

        return {}

    def _extract_primary_key(self, obj):
        """
        从对象中提取主键值

        Args:
            obj: SQLAlchemy模型对象

        Returns:
            主键值或None
        """
        try:
            # 获取对象的mapper
            mapper = sa.inspect(obj.__class__)
            # 获取主键列
            primary_keys = mapper.primary_key
            if primary_keys:
                # 获取第一个主键的值
                pk_column = primary_keys[0]
                return getattr(obj, pk_column.name)
        except Exception:
            # 如果失败，尝试直接获取id属性（兼容性）
            if hasattr(obj, 'id'):
                return obj.id
        return None





def set_user(session, user):
    """
    设置当前用户（推荐方式）

    Args:
        session: SQLAlchemy session对象
        user: 用户对象或用户ID（支持 SQLAlchemy 模型或普通 Python 对象）

    Example:
        set_user(session, user)  # 传入用户对象
        set_user(session, 123)   # 传入用户ID
    """
    if isinstance(user, (int, str)):
        # 如果是整数或字符串，直接设置为user_id
        session.info['user_id'] = user
    else:
        # 如果是对象，动态提取主键
        # 先检查是否是 SQLAlchemy 映射的类（不抛异常）
        mapper = sa.inspect(user.__class__, raiseerr=False)
        
        if mapper is not None and hasattr(mapper, 'primary_key'):
            # 是 SQLAlchemy 模型，从 mapper 获取主键
            primary_keys = mapper.primary_key
            if primary_keys:
                pk_column = primary_keys[0]
                session.info['user_id'] = getattr(user, pk_column.name)
                return
        
        # 不是 SQLAlchemy 模型，或者没有主键，fallback 到 id 属性
        if hasattr(user, 'id'):
            session.info['user_id'] = user.id
        else:
            raise ValueError(f"无法从对象中提取主键: {type(user)}")


def get_user_id(session):
    """
    获取当前用户ID

    Args:
        session: SQLAlchemy session对象

    Returns:
        用户ID或None
    """
    return session.info.get('user_id')



def clear_user(session):
    """
    清除当前用户

    Args:
        session: SQLAlchemy session对象
    """
    session.info.pop('user_id', None)
    session.info.pop('current_user_id', None)
    session.info.pop('user', None)
    session.info.pop('current_user', None)


# ============================================================================
# 导出
# ============================================================================

__all__ = [
    # Plugin
    "CurrentUserPlugin",
    
    # 便捷函数（推荐）
    "set_user",
    "get_user_id",
    "clear_user",

]
