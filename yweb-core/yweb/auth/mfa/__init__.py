"""多因素认证 (MFA/2FA) 模块

提供多种二次验证方式：
- TOTP: 基于时间的一次性密码（Google Authenticator、Microsoft Authenticator 等）
- SMS: 短信验证码
- Email: 邮件验证码
- Recovery Codes: 备用恢复码

使用示例:
    from yweb.auth.mfa import MFAManager, TOTPProvider, SMSProvider
    
    # 创建 MFA 管理器
    mfa_manager = MFAManager()
    
    # 注册 TOTP 提供者
    totp_provider = TOTPProvider(issuer="MyApp")
    mfa_manager.register_provider("totp", totp_provider)
    
    # 为用户启用 TOTP
    secret, uri = totp_provider.generate_secret(user_id=1, username="john")
    # 用户使用 URI 生成二维码并在 Authenticator 中扫描
    
    # 验证 TOTP
    is_valid = totp_provider.verify(user_id=1, code="123456")
"""

from .base import (
    MFAProvider,
    MFAType,
    MFASetupData,
    MFAVerifyResult,
)

from .totp import TOTPProvider
from .otp import OTPProvider, SMSProvider, EmailProvider
from .recovery import RecoveryCodeProvider
from .manager import MFAManager

__all__ = [
    # Base
    "MFAProvider",
    "MFAType",
    "MFASetupData",
    "MFAVerifyResult",
    
    # Providers
    "TOTPProvider",
    "OTPProvider",
    "SMSProvider",
    "EmailProvider",
    "RecoveryCodeProvider",
    
    # Manager
    "MFAManager",
]
