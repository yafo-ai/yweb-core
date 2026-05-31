"""
权限模块 - 主体直接权限抽象模型

定义主体（用户）直接拥有的权限（绕过角色）
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, DateTime, Text, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm.core_model import CoreModel
from yweb.orm.orm_extensions import SimpleSoftDeleteMixin


class AbstractSubjectPermission(CoreModel, SimpleSoftDeleteMixin):
    """主体直接权限抽象模型
    
    允许直接给主体（员工或外部用户）授予权限，绕过角色。
    适用于临时权限、特殊权限等场景。
    
    字段说明:
        - subject_type: 主体类型
        - subject_id: 主体ID
        - permission_id: 权限ID
        - granted_by: 授权人ID
        - granted_at: 授权时间
        - expires_at: 过期时间
        - reason: 授权原因
        - is_active: 是否启用
    
    使用示例:
        from yweb.permission.models import AbstractSubjectPermission
        
        class SubjectPermission(AbstractSubjectPermission):
            __tablename__ = "sys_subject_permission"
            __permission_tablename__ = "sys_permission"
            enable_history = True
    
    授权示例:
        # 给员工授予临时权限
        sp = SubjectPermission(
            subject_type="employee",
            subject_id=123,
            permission_id=1,
            granted_by=admin_id,
            expires_at=datetime(2026, 12, 31),
            reason="临时需要查看财务报告"
        )
        sp.save()
    """
    __abstract__ = True
    
    # 子类需要设置权限表名
    # __permission_tablename__: ClassVar[str] = "permission"
    
    # 主体类型
    subject_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        index=True,
        comment="主体类型: employee, external"
    )
    
    # 主体ID
    subject_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
        comment="主体ID"
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
    
    # 过期时间
    expires_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="过期时间（NULL 表示永不过期）"
    )
    
    # 授权原因
    reason: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="授权原因"
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
                'subject_type', 'subject_id', 'permission_id',
                name=f'uk_{cls.__tablename__}_subject_permission'
            ),
        )
    
    def __repr__(self) -> str:
        return f"<SubjectPermission(subject={self.subject_type}:{self.subject_id}, permission_id={self.permission_id})>"
    
    @property
    def is_expired(self) -> bool:
        """检查是否已过期"""
        if self.expires_at is None:
            return False
        return datetime.now() > self.expires_at
    
    @property
    def is_valid(self) -> bool:
        """检查是否有效"""
        return self.is_active and not self.is_expired
    
    @classmethod
    def get_subject_permissions(
        cls,
        subject_type: str,
        subject_id: int,
        include_expired: bool = False
    ) -> list["AbstractSubjectPermission"]:
        """获取主体的所有直接权限
        
        Args:
            subject_type: 主体类型
            subject_id: 主体ID
            include_expired: 是否包含已过期的
            
        Returns:
            权限关联列表
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


__all__ = ["AbstractSubjectPermission"]
