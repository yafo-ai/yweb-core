"""历史记录模块

提供版本历史记录功能，包括：
- 自动版本历史记录
- 当前用户追踪（审计功能）
- 版本差异比较
- 版本恢复
"""

from .history_helper import (
    init_versioning,
    is_versioning_initialized,
    get_version_class,
    get_history,
    get_history_count,
    get_history_diff,
    get_field_text_diff,
    restore_to_version,
)

from .current_user import (
    # Plugin
    CurrentUserPlugin,
    
    # 便捷函数（推荐）
    set_user,
    get_user_id,
    clear_user,
    

)

__all__ = [
    # 版本化初始化
    "init_versioning",
    "is_versioning_initialized",
    
    # 历史记录查询
    "get_version_class",
    "get_history",
    "get_history_count",
    "get_history_diff",
    "get_field_text_diff",
    "restore_to_version",
    
    # 当前用户追踪（Session 方式）
    "CurrentUserPlugin",
    "set_user",
    "get_user_id",
    "clear_user",
]
