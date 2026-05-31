"""
权限模块 - 角色权限关联抽象模型

定义角色与权限的关联关系
"""

from sqlalchemy import Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm.core_model import CoreModel
from yweb.orm.orm_extensions import SimpleSoftDeleteMixin


class AbstractRolePermission(CoreModel, SimpleSoftDeleteMixin):
    """角色-权限关联抽象模型
    
    将角色与权限关联，一个角色可以拥有多个权限。
    
    使用示例:
        from yweb.permission.models import AbstractRolePermission
        
        class RolePermission(AbstractRolePermission):
            __tablename__ = "sys_role_permission"
            __role_tablename__ = "sys_role"
            __permission_tablename__ = "sys_permission"
            enable_history = True
    """
    __abstract__ = True
    
    # 子类需要设置表名
    # __role_tablename__: ClassVar[str] = "role"
    # __permission_tablename__: ClassVar[str] = "permission"
    
    # 角色ID
    @declared_attr
    def role_id(cls) -> Mapped[int]:
        """角色ID"""
        role_tablename = getattr(cls, '__role_tablename__', 'role')
        return mapped_column(
            Integer,
            ForeignKey(f"{role_tablename}.id"),
            nullable=False,
            index=True,
            comment="角色ID"
        )
    
    # 权限ID
    @declared_attr
    def permission_id(cls) -> Mapped[int]:
        """权限ID"""
        permission_tablename = getattr(cls, '__permission_tablename__', 'permission')
        return mapped_column(
            Integer,
            ForeignKey(f"{permission_tablename}.id"),
            nullable=False,
            index=True,
            comment="权限ID"
        )
    
    # 联合唯一约束
    @declared_attr
    def __table_args__(cls):
        return (
            UniqueConstraint(
                'role_id', 'permission_id',
                name=f'uk_{cls.__tablename__}_role_permission'
            ),
        )
    
    def __repr__(self) -> str:
        return f"<RolePermission(role_id={self.role_id}, permission_id={self.permission_id})>"
    
    @classmethod
    def get_role_permission_ids(cls, role_id: int) -> list[int]:
        """获取角色的所有权限ID
        
        Args:
            role_id: 角色ID
            
        Returns:
            权限ID列表
        """
        rps = cls.query.filter_by(role_id=role_id).all()
        return [rp.permission_id for rp in rps]
    
    @classmethod
    def get_permission_role_ids(cls, permission_id: int) -> list[int]:
        """获取拥有指定权限的所有角色ID
        
        Args:
            permission_id: 权限ID
            
        Returns:
            角色ID列表
        """
        rps = cls.query.filter_by(permission_id=permission_id).all()
        return [rp.role_id for rp in rps]
    
    @classmethod
    def set_role_permissions(cls, role_id: int, permission_ids: list[int]):
        """设置角色的权限（全量覆盖）
        
        Args:
            role_id: 角色ID
            permission_ids: 权限ID列表
        """
        # 删除旧的关联
        cls.query.filter_by(role_id=role_id).delete()
        
        # 添加新的关联
        for perm_id in permission_ids:
            rp = cls(role_id=role_id, permission_id=perm_id)
            rp.add()
    
    @classmethod
    def add_role_permission(cls, role_id: int, permission_id: int) -> bool:
        """添加角色权限
        
        Args:
            role_id: 角色ID
            permission_id: 权限ID
            
        Returns:
            是否成功（已存在返回 False）
        """
        existing = cls.query.filter_by(
            role_id=role_id,
            permission_id=permission_id
        ).first()
        
        if existing:
            return False
        
        rp = cls(role_id=role_id, permission_id=permission_id)
        rp.save()
        return True
    
    @classmethod
    def remove_role_permission(cls, role_id: int, permission_id: int) -> bool:
        """移除角色权限
        
        Args:
            role_id: 角色ID
            permission_id: 权限ID
            
        Returns:
            是否成功（不存在返回 False）
        """
        rp = cls.query.filter_by(
            role_id=role_id,
            permission_id=permission_id
        ).first()
        
        if not rp:
            return False
        
        rp.delete()
        return True


__all__ = ["AbstractRolePermission"]
