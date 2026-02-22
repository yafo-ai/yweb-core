"""
权限模块 - 权限抽象模型

定义权限（Permission）的抽象基类
"""

from typing import Optional, ClassVar
from sqlalchemy import String, Integer, Boolean, Text
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm.core_model import CoreModel
from yweb.orm.orm_extensions import SimpleSoftDeleteMixin


class AbstractPermission(CoreModel, SimpleSoftDeleteMixin):
    """权限抽象模型
    
    定义系统中的权限项，如 "user:read", "order:write" 等。
    
    字段说明:
        - code: 权限编码，格式为 "resource:action"，如 "user:read"
        - name: 权限名称，用于显示
        - resource: 资源类型，如 "user", "order"
        - action: 操作类型，如 "read", "write", "delete"
        - description: 权限描述
        - is_active: 是否启用
        - sort_order: 排序
        - module: 所属模块，用于分组管理
    
    使用示例:
        from yweb.permission.models import AbstractPermission
        
        class Permission(AbstractPermission):
            __tablename__ = "sys_permission"
            enable_history = True  # 可选：启用变更历史记录
    """
    __abstract__ = True
    
    # 权限编码，唯一标识，格式: "resource:action"
    code: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        nullable=False,
        index=True,
        comment="权限编码，如 user:read, order:write"
    )
    
    # 权限名称
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
        comment="权限名称"
    )
    
    # 资源类型
    resource: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        index=True,
        comment="资源类型，如 user, order"
    )
    
    # 操作类型
    action: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        comment="操作类型，如 read, write, delete"
    )
    
    # 权限描述
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="权限描述"
    )
    
    # 是否启用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用"
    )
    
    # 排序
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序"
    )
    
    # 所属模块（用于分组管理）
    module: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="所属模块，用于分组管理"
    )
    
    def __repr__(self) -> str:
        return f"<Permission(code='{self.code}', name='{self.name}')>"
    
    @classmethod
    def get_by_code(cls, code: str) -> Optional["AbstractPermission"]:
        """根据权限编码获取权限
        
        Args:
            code: 权限编码
            
        Returns:
            权限对象，不存在返回 None
        """
        return cls.query.filter_by(code=code, is_active=True).first()
    
    @classmethod
    def get_by_resource(cls, resource: str) -> list["AbstractPermission"]:
        """获取指定资源的所有权限
        
        Args:
            resource: 资源类型
            
        Returns:
            权限列表
        """
        return cls.query.filter_by(resource=resource, is_active=True).order_by(cls.sort_order).all()
    
    @classmethod
    def get_by_module(cls, module: str) -> list["AbstractPermission"]:
        """获取指定模块的所有权限
        
        Args:
            module: 模块名称
            
        Returns:
            权限列表
        """
        return cls.query.filter_by(module=module, is_active=True).order_by(cls.sort_order).all()


__all__ = ["AbstractPermission"]
