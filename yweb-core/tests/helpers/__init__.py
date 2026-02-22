"""测试辅助工具模块

提供测试专用的辅助函数，避免在核心代码中添加测试专用方法。
"""

from .transaction_helpers import (
    reset_transaction_manager,
    is_transaction_manager_initialized,
)
from .primary_key_helpers import (
    get_primary_key_strategy,
    get_short_uuid_length,
    get_max_retries,
    set_max_retries,
)
from .permission_helpers import (
    get_cache_version,
)
from .auth_helpers import (
    get_lock_status,
    get_failed_attempts_info,
    get_password_info,
    verify_password_format,
    get_last_login_info,
    get_password_helper_config,
)

__all__ = [
    # 事务管理器辅助
    'reset_transaction_manager',
    'is_transaction_manager_initialized',
    # 主键配置辅助
    'get_primary_key_strategy',
    'get_short_uuid_length',
    'get_max_retries',
    'set_max_retries',
    # 权限缓存辅助
    'get_cache_version',
    # 认证模块辅助
    'get_lock_status',
    'get_failed_attempts_info',
    'get_password_info',
    'verify_password_format',
    'get_last_login_info',
    'get_password_helper_config',
]
