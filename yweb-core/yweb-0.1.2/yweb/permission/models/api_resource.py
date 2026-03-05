"""
权限模块 - API 资源抽象模型

定义 API 资源与权限的映射关系
"""

from typing import Optional
from sqlalchemy import String, Integer, Boolean, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, declared_attr

from yweb.orm.core_model import CoreModel
from yweb.orm.orm_extensions import SimpleSoftDeleteMixin


class AbstractAPIResource(CoreModel, SimpleSoftDeleteMixin):
    """API 资源抽象模型
    
    将 HTTP 路由与权限关联，用于：
    1. 自动扫描 FastAPI 路由并生成资源
    2. 手动配置 API 与权限的映射
    3. 中间件自动检查 API 权限
    
    字段说明:
        - path: API 路径，如 /api/users/{id}
        - method: HTTP 方法，如 GET, POST
        - api_name: API 名称/描述
        - permission_id: 关联的权限ID
        - is_public: 是否公开访问（无需权限）
        - is_active: 是否启用
        - module: 所属模块
        - sort_order: 排序
    
    使用示例:
        from yweb.permission.models import AbstractAPIResource
        
        class APIResource(AbstractAPIResource):
            __tablename__ = "sys_api_resource"
            __permission_tablename__ = "sys_permission"
    
    配置示例:
        # RESTful 风格
        APIResource(path="/api/users", method="GET", name="用户列表", permission_code="user:list")
        APIResource(path="/api/users/{id}", method="PUT", name="修改用户", permission_code="user:update")
        
        # RPC 风格
        APIResource(path="/api/getUser", method="POST", name="获取用户", permission_code="user:read")
        APIResource(path="/api/updateUser", method="POST", name="更新用户", permission_code="user:update")
    """
    __abstract__ = True
    
    # 子类需要设置权限表名
    # __permission_tablename__: ClassVar[str] = "permission"
    
    # API 路径
    path: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
        comment="API 路径，如 /api/users/{id}"
    )
    
    # HTTP 方法
    method: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
        comment="HTTP 方法: GET, POST, PUT, DELETE, PATCH"
    )
    
    # API 名称
    api_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="API 名称/描述"
    )
    
    # 关联的权限ID
    @declared_attr
    def permission_id(cls) -> Mapped[Optional[int]]:
        """关联的权限ID"""
        permission_tablename = getattr(cls, '__permission_tablename__', 'permission')
        return mapped_column(
            Integer,
            ForeignKey(f"{permission_tablename}.id"),
            nullable=True,
            comment="关联的权限ID（NULL 表示未配置）"
        )
    
    # 是否公开访问
    is_public: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
        comment="是否公开访问（无需权限）"
    )
    
    # 是否启用
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用"
    )
    
    # 所属模块
    module: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        index=True,
        comment="所属模块，用于分组管理"
    )
    
    # 排序
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        comment="排序"
    )
    
    # 联合唯一约束
    @declared_attr
    def __table_args__(cls):
        return (
            UniqueConstraint(
                'path', 'method',
                name=f'uk_{cls.__tablename__}_api_resource'
            ),
        )
    
    def __repr__(self) -> str:
        return f"<APIResource(method='{self.method}', path='{self.path}')>"
    
    @classmethod
    def get_by_path_method(
        cls,
        path: str,
        method: str
    ) -> Optional["AbstractAPIResource"]:
        """根据路径和方法获取 API 资源
        
        Args:
            path: API 路径
            method: HTTP 方法
            
        Returns:
            API 资源对象
        """
        return cls.query.filter_by(
            path=path,
            method=method.upper(),
            is_active=True
        ).first()
    
    @classmethod
    def get_by_module(cls, module: str) -> list["AbstractAPIResource"]:
        """获取指定模块的所有 API 资源
        
        Args:
            module: 模块名称
            
        Returns:
            API 资源列表
        """
        return cls.query.filter_by(
            module=module,
            is_active=True
        ).order_by(cls.sort_order).all()
    
    @classmethod
    def match_path(cls, request_path: str, method: str) -> Optional["AbstractAPIResource"]:
        """匹配请求路径（支持路径参数）
        
        将实际请求路径匹配到配置的 API 资源。
        例如: /api/users/123 匹配 /api/users/{id}
        
        Args:
            request_path: 实际请求路径
            method: HTTP 方法
            
        Returns:
            匹配的 API 资源
        """
        import re
        
        # 首先尝试精确匹配
        exact = cls.get_by_path_method(request_path, method)
        if exact:
            return exact
        
        # 获取所有该方法的资源进行模式匹配
        resources = cls.query.filter_by(
            method=method.upper(),
            is_active=True
        ).all()
        
        for resource in resources:
            # 将路径参数 {xxx} 转换为正则表达式
            pattern = re.sub(r'\{[^}]+\}', r'[^/]+', resource.path)
            pattern = f'^{pattern}$'
            
            if re.match(pattern, request_path):
                return resource
        
        return None


__all__ = ["AbstractAPIResource"]
