"""
ACL 模块 - 枚举定义

框架层唯一的业务枚举：Effect（ALLOW/DENY）。
其他枚举（PermissionLevel、ResourceType、SubjectType、DeptScope）由应用层自定义。
"""

from enum import Enum


class Effect(str, Enum):
    """ACL 规则效果

    引擎 DENY 优先算法硬依赖此枚举。
    - ALLOW: 允许访问
    - DENY: 拒绝访问（优先级高于 ALLOW）
    """
    ALLOW = "ALLOW"
    DENY = "DENY"


__all__ = ["Effect"]
