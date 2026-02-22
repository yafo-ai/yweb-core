"""认证相关 Mixins - 用户安全

提供用户模型的安全扩展功能：
- LockableMixin: 账户锁定/解锁
- PasswordMixin: 密码管理
- LastLoginMixin: 最后登录信息
- FullUserMixin: 以上三者的组合

角色管理 RoleMixin 已移至 models.py（与 AbstractRole 放在一起）。

使用示例:
    from yweb.auth.mixins import LockableMixin, PasswordMixin
    from yweb.orm import BaseModel
    
    class User(LockableMixin, PasswordMixin, BaseModel):
        __tablename__ = "user"
        username = Column(String(255), unique=True)
"""

from datetime import datetime, timezone, timedelta
from typing import Optional
from sqlalchemy import Boolean, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column


class LockableMixin:
    """可锁定用户 Mixin
    
    提供账户锁定/解锁功能。
    
    使用示例:
        class User(LockableMixin, BaseModel):
            __tablename__ = "user"
        
        user = User.get(1)
        
        # 锁定账户
        user.lock("登录失败次数过多")
        
        # 检查锁定状态
        if user.is_locked:
            print("账户已锁定")
        
        # 解锁
        user.unlock()
    """
    
    # 账户是否激活
    is_active: Mapped[bool] = mapped_column(
        Boolean, 
        default=True, 
        nullable=False,
        comment="账户是否激活"
    )
    
    # 锁定相关字段
    is_locked: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="账户是否被锁定"
    )
    locked_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="锁定时间"
    )
    locked_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="锁定到期时间（为空表示永久锁定）"
    )
    lock_reason: Mapped[Optional[str]] = mapped_column(
        String(500), 
        nullable=True,
        comment="锁定原因"
    )
    
    # 登录失败计数
    failed_login_attempts: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        nullable=False,
        comment="连续登录失败次数"
    )
    last_failed_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="最后一次登录失败时间"
    )
    
    def lock(
        self, 
        reason: str = "", 
        duration_minutes: Optional[int] = None,
        commit: bool = True
    ) -> None:
        """锁定账户
        
        Args:
            reason: 锁定原因
            duration_minutes: 锁定时长（分钟），None 表示永久锁定
            commit: 是否立即提交
        """
        self.is_locked = True
        self.locked_at = datetime.now(timezone.utc)
        self.lock_reason = reason
        
        if duration_minutes:
            self.locked_until = datetime.now(timezone.utc) + timedelta(minutes=duration_minutes)
        else:
            self.locked_until = None
        
        if hasattr(self, 'update') and commit:
            self.update(commit)
    
    def unlock(self, commit: bool = True) -> None:
        """解锁账户
        
        Args:
            commit: 是否立即提交
        """
        self.is_locked = False
        self.locked_at = None
        self.locked_until = None
        self.lock_reason = None
        self.failed_login_attempts = 0
        
        if hasattr(self, 'update') and commit:
            self.update(commit)
    
    def check_lock_expired(self) -> bool:
        """检查锁定是否已过期
        
        Returns:
            True 表示已过期（应该解锁）
        """
        if not self.is_locked:
            return False
        
        if self.locked_until is None:
            # 永久锁定
            return False
        
        return datetime.now(timezone.utc) >= self.locked_until
    
    def auto_unlock_if_expired(self, commit: bool = True) -> bool:
        """如果锁定已过期则自动解锁
        
        Args:
            commit: 是否立即提交
            
        Returns:
            True 表示已解锁
        """
        if self.check_lock_expired():
            self.unlock(commit)
            return True
        return False
    
    def record_failed_login(
        self, 
        max_attempts: int = 5, 
        lock_duration_minutes: int = 30,
        commit: bool = True
    ) -> bool:
        """记录登录失败
        
        如果失败次数超过阈值，自动锁定账户。
        
        Args:
            max_attempts: 最大失败次数
            lock_duration_minutes: 锁定时长（分钟）
            commit: 是否立即提交
            
        Returns:
            True 表示账户被锁定
        """
        self.failed_login_attempts += 1
        self.last_failed_login_at = datetime.now(timezone.utc)
        
        if self.failed_login_attempts >= max_attempts:
            self.lock(
                reason=f"登录失败次数过多（{self.failed_login_attempts}次）",
                duration_minutes=lock_duration_minutes,
                commit=False
            )
            if hasattr(self, 'update') and commit:
                self.update(commit)
            return True
        
        if hasattr(self, 'update') and commit:
            self.update(commit)
        return False
    
    def reset_failed_attempts(self, commit: bool = True) -> None:
        """重置登录失败计数（登录成功时调用）"""
        if self.failed_login_attempts > 0:
            self.failed_login_attempts = 0
            self.last_failed_login_at = None
            if hasattr(self, 'update') and commit:
                self.update(commit)
    
    def disable(self, commit: bool = True) -> None:
        """禁用账户"""
        self.is_active = False
        if hasattr(self, 'update') and commit:
            self.update(commit)
    
    def enable(self, commit: bool = True) -> None:
        """启用账户"""
        self.is_active = True
        if hasattr(self, 'update') and commit:
            self.update(commit)
    
    @property
    def can_login(self) -> bool:
        """检查账户是否可以登录"""
        if not self.is_active:
            return False
        
        if self.is_locked:
            # 检查是否自动解锁
            if not self.check_lock_expired():
                return False
        
        return True


class PasswordMixin:
    """密码管理 Mixin
    
    提供密码相关功能。
    
    使用示例:
        class User(PasswordMixin, BaseModel):
            __tablename__ = "user"
        
        user = User()
        user.set_password("my_password")
        
        if user.verify_password("my_password"):
            print("密码正确")
    """
    
    # 密码哈希
    password_hash: Mapped[str] = mapped_column(
        String(255), 
        nullable=False,
        comment="密码哈希"
    )
    
    # 密码更新时间
    password_changed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="密码最后更新时间"
    )
    
    # 密码过期天数（0 表示永不过期）
    password_expires_days: Mapped[int] = mapped_column(
        Integer, 
        default=0, 
        nullable=False,
        comment="密码过期天数（0=永不过期）"
    )
    
    # 是否需要修改密码
    must_change_password: Mapped[bool] = mapped_column(
        Boolean, 
        default=False, 
        nullable=False,
        comment="是否需要修改密码"
    )
    
    def set_password(
        self, 
        password: str, 
        hash_func: Optional[callable] = None,
        commit: bool = False
    ) -> None:
        """设置密码
        
        Args:
            password: 明文密码
            hash_func: 密码哈希函数，默认使用 pbkdf2_sha256
            commit: 是否立即提交
        """
        if hash_func:
            self.password_hash = hash_func(password)
        else:
            # 默认使用 pbkdf2_sha256（更安全）
            from .password import PasswordHelper
            self.password_hash = PasswordHelper.hash(password)
        
        self.password_changed_at = datetime.now(timezone.utc)
        self.must_change_password = False
        
        if hasattr(self, 'update') and commit:
            self.update(commit)
    
    def verify_password(
        self, 
        password: str, 
        hash_func: Optional[callable] = None,
        verify_func: Optional[callable] = None
    ) -> bool:
        """验证密码
        
        支持多种哈希格式（pbkdf2_sha256、MD5、SHA256）。
        
        Args:
            password: 明文密码
            hash_func: 密码哈希函数（用于计算哈希后比较）
            verify_func: 密码验证函数（如 passlib 的 verify）
            
        Returns:
            是否匹配
        """
        if verify_func:
            return verify_func(password, self.password_hash)
        
        if hash_func:
            return hash_func(password) == self.password_hash
        
        # 默认使用 PasswordHelper（支持多种格式）
        from .password import PasswordHelper
        return PasswordHelper.verify(password, self.password_hash)
    
    def needs_password_rehash(self) -> bool:
        """检查密码是否需要升级到新算法
        
        Returns:
            是否需要重新哈希
        """
        from .password import PasswordHelper
        return PasswordHelper.needs_rehash(self.password_hash)
    
    def rehash_password_if_needed(
        self, 
        password: str, 
        commit: bool = True
    ) -> bool:
        """如果需要，升级密码哈希算法
        
        Args:
            password: 明文密码（已验证正确）
            commit: 是否立即提交
            
        Returns:
            是否进行了升级
        """
        if self.needs_password_rehash():
            self.set_password(password, commit=commit)
            return True
        return False
    
    @property
    def is_password_expired(self) -> bool:
        """检查密码是否过期"""
        if self.password_expires_days <= 0:
            return False
        
        if not self.password_changed_at:
            return True
        
        expires_at = self.password_changed_at + timedelta(days=self.password_expires_days)
        return datetime.now(timezone.utc) >= expires_at
    
    def require_password_change(self, commit: bool = True) -> None:
        """要求用户修改密码"""
        self.must_change_password = True
        if hasattr(self, 'update') and commit:
            self.update(commit)


class LastLoginMixin:
    """最后登录信息 Mixin
    
    记录用户最后登录信息。
    """
    
    last_login_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), 
        nullable=True,
        comment="最后登录时间"
    )
    last_login_ip: Mapped[Optional[str]] = mapped_column(
        String(50), 
        nullable=True,
        comment="最后登录IP"
    )
    
    def update_last_login(
        self, 
        ip_address: Optional[str] = None,
        commit: bool = True
    ) -> None:
        """更新最后登录信息
        
        Args:
            ip_address: 登录 IP 地址
            commit: 是否立即提交
        """
        self.last_login_at = datetime.now(timezone.utc)
        if ip_address:
            self.last_login_ip = ip_address
        
        if hasattr(self, 'update') and commit:
            self.update(commit)


class FullUserMixin(LockableMixin, PasswordMixin, LastLoginMixin):
    """完整用户 Mixin
    
    组合所有用户相关的 Mixin。
    
    使用示例:
        class User(FullUserMixin, BaseModel):
            __tablename__ = "user"
            username = Column(String(255), unique=True)
    """
    pass


