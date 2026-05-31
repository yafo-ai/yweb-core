"""
权限模块 - 抽象数据模型

提供权限、角色等抽象模型类，应用层通过继承这些抽象类来创建具体的模型。

使用示例:
    from yweb.permission.models import (
        AbstractPermission,
        AbstractRole,
        AbstractSubjectRole,
        AbstractRolePermission,
        AbstractSubjectPermission,
    )
    
    class Permission(AbstractPermission):
        __tablename__ = "sys_permission"
        enable_history = True  # 启用变更历史记录
    
    class Role(AbstractRole):
        __tablename__ = "sys_role"
        enable_history = True

注意:
    用户模型已统一到认证模块，使用 yweb.auth.AbstractUser 代替原来的 AbstractExternalUser。
    如需权限主体能力，配合 yweb.permission.mixins.ExternalUserSubjectMixin 使用。
"""

from .permission import AbstractPermission
from .role import AbstractRole
from .subject_role import AbstractSubjectRole
from .role_permission import AbstractRolePermission
from .subject_permission import AbstractSubjectPermission
from .api_resource import AbstractAPIResource

__all__ = [
    "AbstractPermission",
    "AbstractRole",
    "AbstractSubjectRole",
    "AbstractRolePermission",
    "AbstractSubjectPermission",
    "AbstractAPIResource",
]
