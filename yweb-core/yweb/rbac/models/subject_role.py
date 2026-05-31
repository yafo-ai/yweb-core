"""
权限模块 - 主体角色关联抽象模型

定义主体（用户）与角色的关联关系
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm.core_model import CoreModel
from yweb.orm.orm_extensions import SimpleSoftDeleteMixin


class AbstractSubjectRole(CoreModel, SimpleSoftDeleteMixin):
    """主体-角色关联抽象模型
    
    将主体（员工或外部用户）与角色关联。
    支持设置过期时间，用于临时角色分配。
    
    字段说明:
        - subject_type: 主体类型 ("employee" 或 "external")
        - subject_id: 主体ID
        - role_id: 角色ID
        - granted_by: 授权人ID
        - granted_at: 授权时间
        - expires_at: 过期时间（NULL 表示永不过期）
        - is_active: 是否启用
    
    使用示例:
        from yweb.permission.models import AbstractSubjectRole
        
        class SubjectRole(AbstractSubjectRole):
            __tablename__ = "sys_subject_role"
            __role_tablename__ = "sys_role"
            enable_history = True
    
    授权示例:
        # 给员工分配角色
        sr = SubjectRole(
            subject_type="employee",
            subject_id=123,
            role_id=1,
            granted_by=admin_id
        )
        sr.save()
        
        # 给外部用户分配临时角色
        sr = SubjectRole(
            subject_type="external",
            subject_id=456,
            role_id=2,
            expires_at=datetime(2026, 12, 31)
        )
        sr.save()
    """
    __abstract__ = True
    
    # 子类需要设置角色表名
    # __role_tablename__: ClassVar[str] = "role"
    
    # 主体类型: "employee" 或 "external"
    subject_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="主体类型: employee, external"
    )
    
    # 主体ID（员工ID或外部用户ID）
    subject_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="主体ID（员工ID或外部用户ID）"
    )
    
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
    
    # 授权人ID
    granted_by: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="授权人ID"
    )
    
    # 授权时间
    granted_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.now,
        nullable=False,
        comment="授权时间"
    )
    
    # 过期时间（NULL 表示永不过期）
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="过期时间（NULL 表示永不过期）"
    )
    
    # 是否启用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用"
    )
    
    # 联合唯一约束
    @declared_attr
    def __table_args__(cls):
        return (
            UniqueConstraint(
                'subject_type', 'subject_id', 'role_id',
                name=f'uk_{cls.__tablename__}_subject_role'
            ),
        )
    
    def __repr__(self) -> str:
        return f"<SubjectRole(subject={self.subject_type}:{self.subject_id}, role_id={self.role_id})>"
    
    @property
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """检查是否有效（启用且未过期）"""
        return self.is_active and not self.is_expired
    
    @classmethod
    def get_subject_roles(
        cls,
        subject_type: str,
        subject_id: int,
        include_expired: bool = False
    ) -> list["AbstractSubjectRole"]:
        """获取主体的所有角色关联
        
        Args:
            subject_type: 主体类型
            subject_id: 主体ID
            include_expired: 是否包含已过期的
            
        Returns:
            角色关联列表
        """
        query = cls.query.filter(
            cls.subject_type == subject_type,
            cls.subject_id == subject_id,
            cls.is_active == True
        )
        
        if not include_expired:
            now = datetime.now()
            query = query.filter(
                (cls.expires_at.is_(None)) | (cls.expires_at > now)
            )
        
        return query.all()
    
    @classmethod
    def get_role_subjects(
        cls,
        role_id: int,
        subject_type: Optional[str] = None
    ) -> list["AbstractSubjectRole"]:
        """获取拥有指定角色的所有主体
        
        Args:
            role_id: 角色ID
            subject_type: 可选，筛选主体类型
            
        Returns:
            角色关联列表
        """
        query = cls.query.filter(
            cls.role_id == role_id,
            cls.is_active == True
        )
        
        if subject_type:
            query = query.filter(cls.subject_type == subject_type)
        
        now = datetime.now()
        query = query.filter(
            (cls.expires_at.is_(None)) | (cls.expires_at > now)
        )
        
        return query.all()


__all__ = ["AbstractSubjectRole"]
