"""MFA 基础定义"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Any, Dict, List
from enum import Enum


class MFAType(str, Enum):
    """MFA 类型"""
    TOTP = "totp"  # 基于时间的一次性密码
    SMS = "sms"  # 短信验证码
    EMAIL = "email"  # 邮件验证码
    RECOVERY = "recovery"  # 恢复码
    WEBAUTHN = "webauthn"  # WebAuthn/FIDO2
    PUSH = "push"  # 推送通知


@dataclass
class MFASetupData:
    """MFA 设置数据
    
    Attributes:
        mfa_type: MFA 类型
        secret: 密钥（TOTP）
        uri: URI（用于生成二维码）
        recovery_codes: 恢复码列表
        extra: 额外数据
    """
    mfa_type: MFAType
    secret: Optional[str] = None
    uri: Optional[str] = None
    recovery_codes: List[str] = field(default_factory=list)
    extra: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MFAVerifyResult:
    """MFA 验证结果
    
    Attributes:
        success: 是否验证成功
        message: 消息
        remaining_attempts: 剩余尝试次数
        locked_until: 锁定到期时间
        recovery_code_used: 是否使用了恢复码
    """
    success: bool
    message: str = ""
    remaining_attempts: Optional[int] = None
    locked_until: Optional[datetime] = None
    recovery_code_used: bool = False
    
    @classmethod
    def ok(cls, message: str = "Verification successful") -> "MFAVerifyResult":
        """创建成功结果"""
        return cls(success=True, message=message)
    
    @classmethod
    def fail(
        cls, 
        message: str = "Verification failed",
        remaining_attempts: int = None,
        locked_until: datetime = None,
    ) -> "MFAVerifyResult":
        """创建失败结果"""
        return cls(
            success=False,
            message=message,
            remaining_attempts=remaining_attempts,
            locked_until=locked_until,
        )


class MFAProvider(ABC):
    """MFA 提供者抽象基类
    
    所有 MFA 方式都应继承此类。
    """
    
    @property
    @abstractmethod
    def mfa_type(self) -> MFAType:
        """返回 MFA 类型"""
        pass
    
    @abstractmethod
    def setup(self, user_id: Any, **kwargs) -> MFASetupData:
        """设置 MFA
        
        Args:
            user_id: 用户 ID
            **kwargs: 额外参数
            
        Returns:
            MFASetupData: 设置数据
        """
        pass
    
    @abstractmethod
    def verify(self, user_id: Any, code: str, **kwargs) -> MFAVerifyResult:
        """验证 MFA 代码
        
        Args:
            user_id: 用户 ID
            code: 验证码
            **kwargs: 额外参数
            
        Returns:
            MFAVerifyResult: 验证结果
        """
        pass
    
    def is_enabled(self, user_id: Any) -> bool:
        """检查用户是否启用了此 MFA
        
        Args:
            user_id: 用户 ID
            
        Returns:
            bool: 是否启用
        """
        return False
    
    def disable(self, user_id: Any) -> bool:
        """禁用用户的 MFA
        
        Args:
            user_id: 用户 ID
            
        Returns:
            bool: 是否成功
        """
        return False
