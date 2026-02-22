"""OTP (One-Time Password) 提供者

提供短信和邮件验证码功能。

使用示例:
    # SMS 验证码
    sms_provider = SMSProvider(
        code_length=6,
        expire_minutes=5,
        sms_sender=send_sms_func,
    )
    
    # 发送验证码
    sms_provider.send_code(user_id=1, phone="+8613800138000")
    
    # 验证
    result = sms_provider.verify(user_id=1, code="123456")
    
    # 邮件验证码
    email_provider = EmailProvider(
        code_length=6,
        expire_minutes=10,
        email_sender=send_email_func,
    )
    
    email_provider.send_code(user_id=1, email="user@example.com")
"""

import secrets
import time
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, Callable

from .base import MFAProvider, MFAType, MFASetupData, MFAVerifyResult


@dataclass
class OTPCode:
    """OTP 代码数据"""
    code: str
    user_id: Any
    created_at: datetime
    expires_at: datetime
    attempts: int = 0
    max_attempts: int = 3
    is_used: bool = False
    target: str = ""  # 手机号或邮箱
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_valid(self) -> bool:
        """检查是否有效"""
        return not self.is_used and not self.is_expired() and self.attempts < self.max_attempts


def generate_numeric_code(length: int = 6) -> str:
    """生成纯数字验证码"""
    return "".join(str(secrets.randbelow(10)) for _ in range(length))


def generate_alphanumeric_code(length: int = 6) -> str:
    """生成字母数字验证码"""
    chars = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 排除易混淆字符
    return "".join(secrets.choice(chars) for _ in range(length))


class OTPProvider(MFAProvider):
    """通用 OTP 提供者基类
    
    提供验证码的生成、存储和验证功能。
    子类需要实现 send_code 方法。
    """
    
    def __init__(
        self,
        mfa_type: MFAType,
        code_length: int = 6,
        expire_minutes: int = 5,
        max_attempts: int = 3,
        numeric_only: bool = True,
        rate_limit_minutes: int = 1,  # 发送间隔限制
        code_store: Callable[[Any, OTPCode], bool] = None,
        code_getter: Callable[[Any], Optional[OTPCode]] = None,
        code_consumer: Callable[[Any], bool] = None,
    ):
        """
        Args:
            mfa_type: MFA 类型
            code_length: 验证码长度
            expire_minutes: 过期时间（分钟）
            max_attempts: 最大尝试次数
            numeric_only: 是否只使用数字
            rate_limit_minutes: 发送频率限制（分钟）
            code_store: 存储验证码的回调
            code_getter: 获取验证码的回调
            code_consumer: 标记验证码已使用的回调
        """
        self._mfa_type = mfa_type
        self.code_length = code_length
        self.expire_minutes = expire_minutes
        self.max_attempts = max_attempts
        self.numeric_only = numeric_only
        self.rate_limit_minutes = rate_limit_minutes
        
        # 存储回调
        self._code_store = code_store
        self._code_getter = code_getter
        self._code_consumer = code_consumer
        
        # 内存存储（默认）
        self._codes: Dict[Any, OTPCode] = {}
        self._last_sent: Dict[Any, datetime] = {}
    
    def set_stores(
        self,
        store: Callable[[Any, OTPCode], bool],
        getter: Callable[[Any], Optional[OTPCode]],
        consumer: Callable[[Any], bool] = None,
    ) -> "OTPProvider":
        """设置存储回调"""
        self._code_store = store
        self._code_getter = getter
        self._code_consumer = consumer
        return self
    
    @property
    def mfa_type(self) -> MFAType:
        return self._mfa_type
    
    def setup(self, user_id: Any, **kwargs) -> MFASetupData:
        """设置 OTP（OTP 不需要特殊设置）"""
        return MFASetupData(
            mfa_type=self._mfa_type,
            extra={
                "code_length": self.code_length,
                "expire_minutes": self.expire_minutes,
            },
        )
    
    def generate_code(
        self,
        user_id: Any,
        target: str = "",
    ) -> Optional[OTPCode]:
        """生成验证码
        
        Args:
            user_id: 用户 ID
            target: 目标（手机号或邮箱）
            
        Returns:
            OTPCode: 验证码对象，或 None（如果受频率限制）
        """
        # 检查发送频率
        if not self._check_rate_limit(user_id):
            return None
        
        # 生成验证码
        if self.numeric_only:
            code = generate_numeric_code(self.code_length)
        else:
            code = generate_alphanumeric_code(self.code_length)
        
        now = datetime.now(timezone.utc)
        otp_code = OTPCode(
            code=code,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(minutes=self.expire_minutes),
            max_attempts=self.max_attempts,
            target=target,
        )
        
        # 保存
        self._save_code(user_id, otp_code)
        self._last_sent[user_id] = now
        
        return otp_code
    
    def _check_rate_limit(self, user_id: Any) -> bool:
        """检查发送频率限制"""
        last_sent = self._last_sent.get(user_id)
        if last_sent:
            elapsed = datetime.now(timezone.utc) - last_sent
            if elapsed < timedelta(minutes=self.rate_limit_minutes):
                return False
        return True
    
    def verify(
        self,
        user_id: Any,
        code: str,
        **kwargs,
    ) -> MFAVerifyResult:
        """验证 OTP 代码"""
        otp_code = self._get_code(user_id)
        
        if not otp_code:
            return MFAVerifyResult.fail("No verification code found")
        
        if otp_code.is_used:
            return MFAVerifyResult.fail("Code already used")
        
        if otp_code.is_expired():
            return MFAVerifyResult.fail("Code expired")
        
        # 更新尝试次数
        otp_code.attempts += 1
        remaining = otp_code.max_attempts - otp_code.attempts
        
        if otp_code.attempts >= otp_code.max_attempts:
            self._consume_code(user_id)
            return MFAVerifyResult.fail(
                "Maximum attempts exceeded",
                remaining_attempts=0,
            )
        
        # 验证代码（大小写不敏感）
        if code.upper() == otp_code.code.upper():
            self._consume_code(user_id)
            return MFAVerifyResult.ok("Verification successful")
        
        # 更新存储
        self._save_code(user_id, otp_code)
        
        return MFAVerifyResult.fail(
            "Invalid verification code",
            remaining_attempts=remaining,
        )
    
    def _save_code(self, user_id: Any, otp_code: OTPCode) -> bool:
        """保存验证码"""
        if self._code_store:
            return self._code_store(user_id, otp_code)
        self._codes[user_id] = otp_code
        return True
    
    def _get_code(self, user_id: Any) -> Optional[OTPCode]:
        """获取验证码"""
        if self._code_getter:
            return self._code_getter(user_id)
        return self._codes.get(user_id)
    
    def _consume_code(self, user_id: Any) -> bool:
        """标记验证码已使用"""
        if self._code_consumer:
            return self._code_consumer(user_id)
        if user_id in self._codes:
            self._codes[user_id].is_used = True
            return True
        return False


class SMSProvider(OTPProvider):
    """短信验证码提供者
    
    使用示例:
        async def send_sms(phone: str, code: str) -> bool:
            # 调用短信服务 API
            return await sms_service.send(phone, f"Your code is: {code}")
        
        provider = SMSProvider(
            code_length=6,
            expire_minutes=5,
            sms_sender=send_sms,
        )
        
        # 发送验证码
        success = await provider.send_code(user_id=1, phone="+8613800138000")
    """
    
    def __init__(
        self,
        code_length: int = 6,
        expire_minutes: int = 5,
        max_attempts: int = 3,
        rate_limit_minutes: int = 1,
        sms_sender: Callable[[str, str], bool] = None,
        **kwargs,
    ):
        """
        Args:
            sms_sender: 短信发送函数，接收 (phone, code)，返回是否成功
        """
        super().__init__(
            mfa_type=MFAType.SMS,
            code_length=code_length,
            expire_minutes=expire_minutes,
            max_attempts=max_attempts,
            numeric_only=True,  # 短信验证码通常是纯数字
            rate_limit_minutes=rate_limit_minutes,
            **kwargs,
        )
        self.sms_sender = sms_sender
    
    def set_sms_sender(
        self,
        sender: Callable[[str, str], bool],
    ) -> "SMSProvider":
        """设置短信发送函数"""
        self.sms_sender = sender
        return self
    
    def send_code(
        self,
        user_id: Any,
        phone: str,
    ) -> tuple:
        """发送短信验证码
        
        Args:
            user_id: 用户 ID
            phone: 手机号
            
        Returns:
            tuple: (success, message)
        """
        # 生成验证码
        otp_code = self.generate_code(user_id, target=phone)
        if not otp_code:
            return False, "Please wait before requesting a new code"
        
        # 发送短信
        if self.sms_sender:
            try:
                success = self.sms_sender(phone, otp_code.code)
                if success:
                    return True, "Verification code sent"
                return False, "Failed to send SMS"
            except Exception as e:
                return False, f"SMS sending error: {str(e)}"
        
        # 未配置发送函数（开发模式）
        return True, f"Code generated (dev mode): {otp_code.code}"


class EmailProvider(OTPProvider):
    """邮件验证码提供者
    
    使用示例:
        async def send_email(email: str, code: str) -> bool:
            # 调用邮件服务
            return await email_service.send(
                to=email,
                subject="Verification Code",
                body=f"Your verification code is: {code}"
            )
        
        provider = EmailProvider(
            code_length=6,
            expire_minutes=10,
            email_sender=send_email,
        )
        
        # 发送验证码
        success = await provider.send_code(user_id=1, email="user@example.com")
    """
    
    def __init__(
        self,
        code_length: int = 6,
        expire_minutes: int = 10,
        max_attempts: int = 3,
        rate_limit_minutes: int = 1,
        numeric_only: bool = True,
        email_sender: Callable[[str, str], bool] = None,
        **kwargs,
    ):
        """
        Args:
            email_sender: 邮件发送函数，接收 (email, code)，返回是否成功
        """
        super().__init__(
            mfa_type=MFAType.EMAIL,
            code_length=code_length,
            expire_minutes=expire_minutes,
            max_attempts=max_attempts,
            numeric_only=numeric_only,
            rate_limit_minutes=rate_limit_minutes,
            **kwargs,
        )
        self.email_sender = email_sender
    
    def set_email_sender(
        self,
        sender: Callable[[str, str], bool],
    ) -> "EmailProvider":
        """设置邮件发送函数"""
        self.email_sender = sender
        return self
    
    def send_code(
        self,
        user_id: Any,
        email: str,
    ) -> tuple:
        """发送邮件验证码
        
        Args:
            user_id: 用户 ID
            email: 邮箱地址
            
        Returns:
            tuple: (success, message)
        """
        # 生成验证码
        otp_code = self.generate_code(user_id, target=email)
        if not otp_code:
            return False, "Please wait before requesting a new code"
        
        # 发送邮件
        if self.email_sender:
            try:
                success = self.email_sender(email, otp_code.code)
                if success:
                    return True, "Verification code sent to your email"
                return False, "Failed to send email"
            except Exception as e:
                return False, f"Email sending error: {str(e)}"
        
        # 未配置发送函数（开发模式）
        return True, f"Code generated (dev mode): {otp_code.code}"
