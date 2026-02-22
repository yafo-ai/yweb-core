"""认证模块测试辅助工具

提供测试专用的认证相关辅助函数
"""

from typing import Dict, Optional
from yweb.auth.password import PasswordHelper


# ==================== Mixin 辅助函数 ====================

def get_lock_status(user) -> dict:
    """获取用户锁定状态信息
    
    Args:
        user: 具有 LockableMixin 的用户对象
        
    Returns:
        dict: 锁定状态信息
    """
    return {
        'is_locked': user.is_locked,
        'locked_at': user.locked_at,
        'locked_until': user.locked_until,
        'lock_reason': user.lock_reason
    }


def get_failed_attempts_info(user) -> dict:
    """获取失败尝试信息
    
    Args:
        user: 具有 LockableMixin 的用户对象
        
    Returns:
        dict: 失败尝试信息
    """
    return {
        'failed_login_attempts': user.failed_login_attempts,
        'last_failed_login_at': user.last_failed_login_at
    }


def get_password_info(user) -> dict:
    """获取密码信息
    
    Args:
        user: 具有 PasswordMixin 的用户对象
        
    Returns:
        dict: 密码信息
    """
    return {
        'password_changed_at': user.password_changed_at,
        'password_expires_days': user.password_expires_days,
        'must_change_password': user.must_change_password
    }


def verify_password_format(user, expected_prefix: Optional[str] = None) -> bool:
    """验证密码哈希格式
    
    Args:
        user: 具有 PasswordMixin 的用户对象
        expected_prefix: 期望的前缀
        
    Returns:
        bool: 是否匹配
    """
    if expected_prefix:
        return user.password_hash.startswith(expected_prefix)
    return bool(user.password_hash)


def get_last_login_info(user) -> dict:
    """获取最后登录信息
    
    Args:
        user: 具有 LastLoginMixin 的用户对象
        
    Returns:
        dict: 最后登录信息
    """
    return {
        'last_login_at': user.last_login_at,
        'last_login_ip': user.last_login_ip
    }


# ==================== PasswordHelper 辅助函数 ====================

def get_password_helper_config() -> Dict[str, any]:
    """获取 PasswordHelper 配置信息
    
    Returns:
        dict: 配置信息
    """
    return {
        'md5_salt': PasswordHelper._md5_salt,
        'min_length': PasswordHelper._min_length,
        'max_length': PasswordHelper._max_length
    }
