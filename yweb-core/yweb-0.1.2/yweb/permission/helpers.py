"""
权限模块 - 辅助函数

提供 setup_permission_relationships() 辅助函数，用于自动设置模型间的 relationship。
解决抽象类无法预先定义 relationship 的问题。

使用方式：

方式1（推荐）：使用辅助函数自动设置所有关系
    
    from yweb.permission import (
        setup_permission_relationships,
    )
    from yweb.permission.models import (
        AbstractPermission, AbstractRole,
        AbstractSubjectRole, AbstractRolePermission, AbstractSubjectPermission,
    )
    
    class Permission(AbstractPermission): pass
    class Role(AbstractRole): pass
    class SubjectRole(AbstractSubjectRole): pass
    class RolePermission(AbstractRolePermission): pass
    class SubjectPermission(AbstractSubjectPermission): pass
    
    # 一行代码设置所有关系
    setup_permission_relationships(
        Permission, Role, SubjectRole, RolePermission, SubjectPermission
    )
    
    # 现在可以直接使用：
    role = Role.get(1)
    print(role.parent)            # 父角色
    print(role.children)          # 子角色列表
    
    sr = SubjectRole.query.filter_by(subject_id=123).first()
    print(sr.role.name)           # 关联的角色

方式2：手动定义关系（更灵活但代码更多）

    class Role(AbstractRole):
        parent = relationship("Role", remote_side="Role.id", back_populates="children")
        children = relationship("Role", back_populates="parent")
        # ... 更多关系定义
"""

from typing import Type, Optional
from sqlalchemy.orm import relationship


def setup_permission_relationships(
    permission_model: Type,
    role_model: Type,
    subject_role_model: Optional[Type] = None,
    role_permission_model: Optional[Type] = None,
    subject_permission_model: Optional[Type] = None,
) -> None:
    """设置权限模型间的所有 relationship
    
    此函数会自动为各模型添加 relationship 属性，简化用户代码。
    
    Args:
        permission_model: 权限模型类（继承自 AbstractPermission）
        role_model: 角色模型类（继承自 AbstractRole）
        subject_role_model: 主体-角色关联模型（可选）
        role_permission_model: 角色-权限关联模型（可选）
        subject_permission_model: 主体-权限关联模型（可选）
    
    设置的关系包括：
    
    Permission:
        - role_permissions: List[RolePermission] (一对多，如果提供)
        - subject_permissions: List[SubjectPermission] (一对多，如果提供)
    
    Role:
        - parent: Role (自引用，多对一) - 父角色
        - children: List[Role] (自引用，一对多) - 子角色
        - role_permissions: List[RolePermission] (一对多，如果提供)
        - subject_roles: List[SubjectRole] (一对多，如果提供)
    
    SubjectRole (如果提供):
        - role: Role (多对一)
    
    RolePermission (如果提供):
        - role: Role (多对一)
        - permission: Permission (多对一)
    
    SubjectPermission (如果提供):
        - permission: Permission (多对一)
    
    Example:
        >>> from yweb.permission import setup_permission_relationships
        >>> setup_permission_relationships(
        ...     Permission, Role, SubjectRole, RolePermission, SubjectPermission
        ... )
        >>> 
        >>> # 现在可以使用关系了
        >>> role = Role.get(1)
        >>> print(role.parent.name if role.parent else "无父角色")
        >>> for child in role.children:
        ...     print(child.name)
        >>> 
        >>> sr = SubjectRole.query.filter_by(subject_id=123).first()
        >>> print(sr.role.name)
    """
    perm_name = permission_model.__name__
    role_name = role_model.__name__
    
    # ============================================================
    # Permission 的关系
    # ============================================================
    
    # Permission.role_permissions -> List[RolePermission]
    if role_permission_model and (not hasattr(permission_model, 'role_permissions') or permission_model.role_permissions is None):
        permission_model.role_permissions = relationship(
            role_permission_model.__name__,
            back_populates="permission",
            lazy="selectin",
        )
    
    # Permission.subject_permissions -> List[SubjectPermission]
    if subject_permission_model and (not hasattr(permission_model, 'subject_permissions') or permission_model.subject_permissions is None):
        permission_model.subject_permissions = relationship(
            subject_permission_model.__name__,
            back_populates="permission",
            lazy="selectin",
        )
    
    # ============================================================
    # Role 的关系
    # ============================================================
    
    # Role.parent -> Role (自引用，用于角色继承)
    if not hasattr(role_model, 'parent') or role_model.parent is None:
        role_model.parent = relationship(
            role_name,
            remote_side=f"{role_name}.id",
            back_populates="children",
            foreign_keys=f"[{role_name}.parent_id]",
        )
    
    # Role.children -> List[Role] (自引用)
    if not hasattr(role_model, 'children') or role_model.children is None:
        role_model.children = relationship(
            role_name,
            back_populates="parent",
            foreign_keys=f"[{role_name}.parent_id]",
            lazy="selectin",
        )
    
    # Role.role_permissions -> List[RolePermission]
    if role_permission_model and (not hasattr(role_model, 'role_permissions') or role_model.role_permissions is None):
        role_model.role_permissions = relationship(
            role_permission_model.__name__,
            back_populates="role",
            lazy="selectin",
        )
    
    # Role.subject_roles -> List[SubjectRole]
    if subject_role_model and (not hasattr(role_model, 'subject_roles') or role_model.subject_roles is None):
        role_model.subject_roles = relationship(
            subject_role_model.__name__,
            back_populates="role",
            lazy="selectin",
        )
    
    # ============================================================
    # SubjectRole 的关系
    # ============================================================
    if subject_role_model:
        rel_name = subject_role_model.__name__
        
        # SubjectRole.role -> Role
        if not hasattr(subject_role_model, 'role') or subject_role_model.role is None:
            subject_role_model.role = relationship(
                role_name,
                back_populates="subject_roles",
                foreign_keys=f"[{rel_name}.role_id]",
            )
    
    # ============================================================
    # RolePermission 的关系
    # ============================================================
    if role_permission_model:
        rel_name = role_permission_model.__name__
        
        # RolePermission.role -> Role
        if not hasattr(role_permission_model, 'role') or role_permission_model.role is None:
            role_permission_model.role = relationship(
                role_name,
                back_populates="role_permissions",
                foreign_keys=f"[{rel_name}.role_id]",
            )
        
        # RolePermission.permission -> Permission
        if not hasattr(role_permission_model, 'permission') or role_permission_model.permission is None:
            role_permission_model.permission = relationship(
                perm_name,
                back_populates="role_permissions",
                foreign_keys=f"[{rel_name}.permission_id]",
            )
    
    # ============================================================
    # SubjectPermission 的关系
    # ============================================================
    if subject_permission_model:
        rel_name = subject_permission_model.__name__
        
        # SubjectPermission.permission -> Permission
        if not hasattr(subject_permission_model, 'permission') or subject_permission_model.permission is None:
            subject_permission_model.permission = relationship(
                perm_name,
                back_populates="subject_permissions",
                foreign_keys=f"[{rel_name}.permission_id]",
            )


__all__ = ["setup_permission_relationships"]
