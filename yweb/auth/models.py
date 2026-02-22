"""认证模块 - 抽象模型与角色管理

提供认证相关的所有抽象基类和角色 Mixin：
- AbstractUser: 用户抽象模型（BaseModel），包含登录认证所需的最小字段集
- AbstractSimpleRole: 轻量级角色抽象模型（BaseModel），简单角色标识
- AbstractLoginRecord: 登录记录抽象模型（CoreModel），审计日志
- RoleMixin: 角色管理 Mixin，为用户模型提供角色便捷方法

角色模型层级关系:
    AbstractSimpleRole (yweb.auth)      ← 轻量级，仅 description
        └── AbstractRole (yweb.permission)  ← 完整 RBAC，树形继承 + is_active/is_system
    
    两者共享 RoleMixin API（User.has_role / User.role_codes），
    从轻量版升级到完整版只需更换 Role 基类，无需改动用户侧代码。

设计原则:
    - 只包含认证相关的核心字段，不掺杂权限/组织等概念
    - 项目通过继承添加业务特有字段
    - 推荐使用 setup_auth(role_model=True) 自动配置角色

使用示例:

    基础用法（只需认证）::
    
        from yweb.auth import AbstractUser, setup_auth
        
        class User(AbstractUser):
            __tablename__ = "sys_user"
        
        auth = setup_auth(User)
    
    认证 + 角色（推荐，零配置）::
    
        from yweb.auth import AbstractUser, setup_auth
        
        class User(AbstractUser):
            __tablename__ = "sys_user"
        
        auth = setup_auth(User, role_model=True)
        # 自动创建 Role 模型 + User.roles + RoleMixin
    
    登录审计::
    
        from yweb.auth import AbstractLoginRecord
        
        class LoginRecord(AbstractLoginRecord):
            __tablename__ = "login_record"
"""

from typing import Optional, List
from datetime import datetime, timezone
from sqlalchemy import String, Boolean, DateTime, Integer, Text, Index
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import BaseModel, CoreModel


class AbstractUser(BaseModel):
    """认证用户抽象模型
    
    提供 setup_auth() 所需的最小字段集，以及常用的用户查询方法。
    
    内置字段:
        - username: 用户名，唯一标识（登录凭据）
        - password_hash: 密码哈希
        - email: 邮箱（可选）
        - phone: 手机号（可选）
        - is_active: 是否启用（setup_auth 默认检查此字段）
        - last_login_at: 最后登录时间
    
    继承自 BaseModel，自动拥有:
        - id: 主键
        - name / code / note / caption: 常用业务字段
        - created_at / updated_at: 时间戳
        - .get(id)、.query 等 ORM 便捷方法
        - 软删除支持
    
    使用示例:
        class User(AbstractUser):
            __tablename__ = "sys_user"
            
            # 可添加自定义字段
            avatar = mapped_column(String(500), nullable=True, comment="头像URL")
    """
    __abstract__ = True
    
    # 用户名，唯一标识（登录凭据）
    username: Mapped[str] = mapped_column(
        String(50),
        unique=True,
        nullable=False,
        index=True,
        comment="用户名"
    )
    
    # 密码哈希
    password_hash: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        comment="密码哈希"
    )
    
    # 邮箱
    email: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
        index=True,
        comment="邮箱"
    )
    
    # 手机号
    phone: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        index=True,
        comment="手机号"
    )
    
    # 是否启用（setup_auth 默认检查此字段）
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        nullable=False,
        comment="是否启用"
    )
    
    # 最后登录时间
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime,
        nullable=True,
        comment="最后登录时间"
    )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(username='{self.username}')>"
    
    # ==================== 便捷查询方法 ====================
    
    @classmethod
    def get_by_username(cls, username: str) -> Optional["AbstractUser"]:
        """根据用户名获取用户
        
        Args:
            username: 用户名
            
        Returns:
            用户对象，不存在返回 None
        """
        return cls.query.filter_by(username=username).first()
    
    @classmethod
    def get_by_email(cls, email: str) -> Optional["AbstractUser"]:
        """根据邮箱获取用户
        
        Args:
            email: 邮箱
            
        Returns:
            用户对象，不存在返回 None
        """
        return cls.query.filter_by(email=email).first()
    
    @classmethod
    def get_by_phone(cls, phone: str) -> Optional["AbstractUser"]:
        """根据手机号获取用户
        
        Args:
            phone: 手机号
            
        Returns:
            用户对象，不存在返回 None
        """
        return cls.query.filter_by(phone=phone).first()
    
    def update_last_login(self) -> None:
        """更新最后登录时间"""
        self.last_login_at = datetime.now()
        self.save()
    
    @property
    def display_name(self) -> str:
        """获取显示名称
        
        优先使用 name（BaseModel 内置），其次 username
        """
        return self.name or self.username
    
    # ==================== 便捷创建方法 ====================
    
    @classmethod
    def create_user(
        cls,
        username: str,
        password: str,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        **kwargs,
    ) -> "AbstractUser":
        """创建用户（自动验证输入 + 密码哈希）
        
        自动完成：用户名格式验证、密码强度验证、邮箱/手机号格式验证、密码哈希。
        
        Args:
            username: 用户名
            password: 明文密码
            email: 邮箱（可选）
            phone: 手机号（可选）
            **kwargs: 其他字段（如 name, is_active 等）
            
        Returns:
            创建的用户对象
            
        Raises:
            ValidationError: 用户名或密码格式不合规
            ValueError: 邮箱或手机号格式无效
            
        使用示例:
            user = User.create_user("admin", "MyP@ss123", email="admin@example.com")
        """
        from .validators import PasswordValidator, UsernameValidator
        from .password import PasswordHelper
        from yweb.validators import is_valid_email, is_valid_phone
        
        # 验证输入
        UsernameValidator.validate_or_raise(username)
        PasswordValidator.validate_or_raise(password)
        if email and not is_valid_email(email):
            raise ValueError(f"无效的邮箱格式: {email}")
        if phone and not is_valid_phone(phone):
            raise ValueError(f"无效的手机号格式: {phone}")
        
        # 创建并保存
        user = cls(
            username=username,
            password_hash=PasswordHelper.hash(password),
            email=email,
            phone=phone,
            **kwargs,
        )
        user.add(True)
        return user
    
    # ==================== 便捷搜索方法 ====================
    
    @classmethod
    def _build_search_query(cls, keyword: Optional[str] = None, is_active: Optional[bool] = None):
        """构建用户搜索基础查询（内部复用）
        
        Args:
            keyword: 搜索关键词（模糊匹配用户名、姓名、邮箱、手机号）
            is_active: 活跃状态过滤（None 表示不过滤）
            
        Returns:
            构建好的 query 对象
        """
        query = cls.query.order_by(cls.created_at.desc())
        
        if keyword:
            query = query.filter(
                cls.username.ilike(f"%{keyword}%") |
                cls.name.ilike(f"%{keyword}%") |
                cls.email.ilike(f"%{keyword}%") |
                cls.phone.ilike(f"%{keyword}%")
            )
        
        if is_active is not None:
            query = query.filter(cls.is_active == is_active)
        
        return query
    
    @classmethod
    def search(
        cls,
        keyword: Optional[str] = None,
        is_active: Optional[bool] = None,
        page: int = 1,
        page_size: int = 10,
    ):
        """搜索用户（仅用户属性过滤，不含角色信息）
        
        按 created_at 倒序排列。关键词同时搜索 username、name、email、phone 字段。
        
        Args:
            keyword: 搜索关键词（模糊匹配用户名、姓名、邮箱、手机号）
            is_active: 活跃状态过滤（None 表示不过滤）
            page: 页码，默认 1
            page_size: 每页数量，默认 10
            
        Returns:
            分页结果对象（rows 为用户列表，不含 roles）
            
        使用示例:
            page = User.search(keyword="admin", page=1, page_size=10)
            page = User.search(is_active=True)
        """
        query = cls._build_search_query(keyword=keyword, is_active=is_active)
        return query.paginate(page=page, page_size=page_size)
    
    @classmethod
    def search_with_roles(
        cls,
        keyword: Optional[str] = None,
        is_active: Optional[bool] = None,
        role_code: Optional[str] = None,
        page: int = 1,
        page_size: int = 10,
    ):
        """搜索用户并预加载角色（用户属性过滤 + 角色过滤 + 角色预加载）
        
        使用 selectinload 预加载 roles 关联，避免 N+1 查询。
        按 created_at 倒序排列。
        
        Args:
            keyword: 搜索关键词（模糊匹配用户名、姓名、邮箱、手机号）
            is_active: 活跃状态过滤（None 表示不过滤）
            role_code: 角色编码过滤（None 表示不过滤）
            page: 页码，默认 1
            page_size: 每页数量，默认 10
            
        Returns:
            分页结果对象（rows 为用户列表，每个用户已加载 roles）
            
        使用示例:
            page = User.search_with_roles(keyword="admin", page=1, page_size=10)
            page = User.search_with_roles(role_code="admin")
        """
        from sqlalchemy.orm import selectinload
        
        query = cls._build_search_query(keyword=keyword, is_active=is_active)
        
        # 预加载 roles 关联，避免逐个查询
        if hasattr(cls, 'roles'):
            query = query.options(selectinload(cls.roles))
        
        if role_code and hasattr(cls, 'roles'):
            query = query.filter(cls.roles.any(code=role_code))
        
        return query.paginate(page=page, page_size=page_size)


class AbstractSimpleRole(BaseModel):
    """轻量级角色抽象模型
    
    提供简单的角色标识管理，适用于只需要"用户属于哪些角色"的场景。
    如需完整 RBAC（树形角色继承 + 权限管理），请使用 yweb.permission.AbstractRole。
    
    yweb.permission.AbstractRole 继承自本类，两者共享 RoleMixin API（
    User.has_role() / User.role_codes），升级到完整版时无需改动用户侧代码。
    
    继承自 BaseModel，自动拥有:
        - id: 主键
        - name: 角色名称（如 "管理员"）
        - code: 角色代码（如 "admin"），唯一标识
        - note / caption: 备注
        - created_at / updated_at: 时间戳
        - 软删除支持
    
    额外字段:
        - description: 角色描述（Text）
    
    使用示例::
    
        # 轻量级用法（推荐大多数项目）
        class Role(AbstractSimpleRole):
            __tablename__ = "role"
        
        # 或通过 setup_auth 自动创建
        auth = setup_auth(User, role_model=True)
        Role = auth.role_model
    """
    __abstract__ = True
    
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        comment="角色描述"
    )
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}(code='{self.code}', name='{self.name}')>"
    
    # ==================== 便捷查询方法 ====================
    
    @classmethod
    def get_by_code(cls, code: str) -> Optional["AbstractSimpleRole"]:
        """根据角色代码获取角色
        
        Args:
            code: 角色代码（如 "admin"）
            
        Returns:
            角色对象，不存在返回 None
        """
        return cls.query.filter_by(code=code).first()
    
    @classmethod
    def list_all(cls) -> List["AbstractSimpleRole"]:
        """获取所有角色
        
        Returns:
            角色列表
        """
        return cls.query.all()
    
    @classmethod
    def create_role(
        cls,
        name: str,
        code: str,
        description: Optional[str] = None,
    ) -> "AbstractSimpleRole":
        """创建角色
        
        Args:
            name: 角色名称
            code: 角色代码
            description: 角色描述
            
        Returns:
            新创建的角色对象
        """
        role = cls(
            name=name,
            code=code,
            description=description,
        )
        role.add(True)
        return role


class AbstractLoginRecord(CoreModel):
    """登录记录抽象基类
    
    继承自 CoreModel，自动拥有 id、created_at、updated_at 等 ORM 能力。
    不含 name/code 等业务字段，不含软删除（审计记录应硬删除清理）。
    
    内置字段:
        - user_id, username, ip_address, user_agent
        - status, failure_reason, login_at
        - location, device_info
    
    内置查询方法:
        - create_record(): 创建登录记录
        - get_recent_logins(): 获取最近登录记录
        - get_user_logins(): 获取指定用户的登录记录
        - count_records(): 获取记录总数
    
    使用示例:
        class LoginRecord(AbstractLoginRecord):
            __tablename__ = "login_record"
        
        LoginRecord.get_recent_logins(limit=20)
        LoginRecord.get_user_logins(user_id=1)
    """
    __abstract__ = True
    
    # 用户信息
    user_id: Mapped[Optional[int]] = mapped_column(
        Integer, 
        nullable=True, 
        index=True,
        comment="用户ID（登录失败时可能为空）"
    )
    username: Mapped[str] = mapped_column(
        String(255), 
        nullable=False, 
        index=True,
        comment="用户名"
    )
    
    # 客户端信息
    ip_address: Mapped[str] = mapped_column(
        String(50), 
        nullable=False,
        index=True,
        comment="IP地址"
    )
    user_agent: Mapped[Optional[str]] = mapped_column(
        Text, 
        nullable=True,
        comment="用户代理"
    )
    
    # 登录结果
    status: Mapped[str] = mapped_column(
        String(20), 
        nullable=False, 
        default="success",
        index=True,
        comment="登录状态: success/failed/locked/disabled"
    )
    failure_reason: Mapped[Optional[str]] = mapped_column(
        String(100), 
        nullable=True,
        comment="失败原因"
    )
    
    # 时间戳
    login_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        index=True,
        comment="登录时间"
    )
    
    # 额外信息
    location: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True,
        comment="地理位置"
    )
    device_info: Mapped[Optional[str]] = mapped_column(
        String(255), 
        nullable=True,
        comment="设备信息"
    )
    
    # 定义索引（子类可以覆盖）
    __table_args__ = (
        Index('ix_login_record_user_time', 'user_id', 'login_at'),
        Index('ix_login_record_ip_time', 'ip_address', 'login_at'),
    )
    
    # ==================== 便捷查询方法 ====================
    
    @classmethod
    def create_record(cls, login_record: "AbstractLoginRecord") -> "AbstractLoginRecord":
        """创建登录记录"""
        login_record.add(True)
        return login_record
    
    @classmethod
    def get_recent_logins(cls, limit: int = 10) -> List["AbstractLoginRecord"]:
        """获取最近登录记录（按创建时间倒序）"""
        return cls.query.order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def get_user_logins(cls, user_id: int, limit: int = 10) -> List["AbstractLoginRecord"]:
        """获取指定用户的登录记录（按创建时间倒序）"""
        return cls.query.filter(
            cls.user_id == user_id
        ).order_by(cls.created_at.desc()).limit(limit).all()
    
    @classmethod
    def count_records(cls) -> int:
        """获取登录记录总数"""
        return cls.query.count()


class RoleMixin:
    """角色管理 Mixin
    
    为用户模型提供角色相关的便捷方法。
    
    推荐通过 setup_auth(role_model=True) 自动注入，无需手动继承。
    
    也可手动使用::
    
        from yweb.auth import RoleMixin, AbstractUser
        from yweb.orm import fields
        
        class User(RoleMixin, AbstractUser):
            __tablename__ = "sys_user"
            roles = fields.ManyToMany(Role, on_delete=fields.UNLINK)
    """
    
    def has_role(self, role_code: str) -> bool:
        """检查用户是否拥有指定角色"""
        return any(
            getattr(role, 'code', None) == role_code
            for role in (getattr(self, 'roles', None) or [])
        )
    
    def has_any_role(self, *role_codes: str) -> bool:
        """检查用户是否拥有任一指定角色"""
        current_codes = self.role_codes
        return bool(current_codes & set(role_codes))
    
    def has_all_roles(self, *role_codes: str) -> bool:
        """检查用户是否拥有所有指定角色"""
        current_codes = self.role_codes
        return set(role_codes).issubset(current_codes)
    
    def add_role(self, role) -> None:
        """添加角色"""
        roles = getattr(self, 'roles', None)
        if roles is not None:
            roles.append(role)
    
    def remove_role(self, role) -> None:
        """移除角色"""
        roles = getattr(self, 'roles', None)
        if roles is not None:
            roles.remove(role)
    
    @property
    def role_codes(self) -> set:
        """获取用户所有角色代码集合，如 {"admin", "user"}"""
        roles = getattr(self, 'roles', None) or []
        return {getattr(r, 'code', str(r)) for r in roles}


__all__ = [
    "AbstractUser", "AbstractSimpleRole", "AbstractLoginRecord",
    "RoleMixin",
]
