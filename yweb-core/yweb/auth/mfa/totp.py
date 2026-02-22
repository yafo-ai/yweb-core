"""TOTP (Time-based One-Time Password) 提供者

实现基于时间的一次性密码，兼容 Google Authenticator、Microsoft Authenticator 等。

使用示例:
    provider = TOTPProvider(issuer="MyApp")
    
    # 为用户生成密钥
    setup_data = provider.setup(user_id=1, username="john", email="john@example.com")
    print(setup_data.secret)  # JBSWY3DPEHPK3PXP
    print(setup_data.uri)  # otpauth://totp/MyApp:john?secret=...
    
    # 验证代码
    result = provider.verify(user_id=1, code="123456")
    if result.success:
        print("验证成功")
"""

import time
import hmac
import struct
import base64
import hashlib
from typing import Optional, Any, Dict, Callable
from urllib.parse import quote

from .base import MFAProvider, MFAType, MFASetupData, MFAVerifyResult


def _generate_secret(length: int = 32) -> str:
    """生成随机密钥"""
    import secrets
    # 生成随机字节并 Base32 编码
    random_bytes = secrets.token_bytes(length)
    return base64.b32encode(random_bytes).decode("utf-8").rstrip("=")


def _hotp(secret: str, counter: int, digits: int = 6) -> str:
    """HOTP (HMAC-based One-Time Password)
    
    Args:
        secret: Base32 编码的密钥
        counter: 计数器
        digits: 密码位数
        
    Returns:
        str: 一次性密码
    """
    # 解码密钥
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    
    # 计算 HMAC
    counter_bytes = struct.pack(">Q", counter)
    hmac_hash = hmac.new(key, counter_bytes, hashlib.sha1).digest()
    
    # 动态截断
    offset = hmac_hash[-1] & 0x0F
    truncated = struct.unpack(">I", hmac_hash[offset:offset + 4])[0]
    truncated &= 0x7FFFFFFF
    
    # 生成 OTP
    otp = truncated % (10 ** digits)
    return str(otp).zfill(digits)


def _totp(secret: str, time_step: int = 30, digits: int = 6, timestamp: int = None) -> str:
    """TOTP (Time-based One-Time Password)
    
    Args:
        secret: Base32 编码的密钥
        time_step: 时间步长（秒）
        digits: 密码位数
        timestamp: 时间戳（默认当前时间）
        
    Returns:
        str: 一次性密码
    """
    if timestamp is None:
        timestamp = int(time.time())
    counter = timestamp // time_step
    return _hotp(secret, counter, digits)


def _verify_totp(
    secret: str,
    code: str,
    time_step: int = 30,
    digits: int = 6,
    window: int = 1,
    timestamp: int = None,
) -> bool:
    """验证 TOTP
    
    Args:
        secret: Base32 编码的密钥
        code: 待验证的代码
        time_step: 时间步长（秒）
        digits: 密码位数
        window: 允许的时间窗口（前后多少个时间步）
        timestamp: 时间戳（默认当前时间）
        
    Returns:
        bool: 是否验证通过
    """
    if timestamp is None:
        timestamp = int(time.time())
    
    # 在时间窗口内验证
    for offset in range(-window, window + 1):
        check_time = timestamp + (offset * time_step)
        expected = _totp(secret, time_step, digits, check_time)
        if hmac.compare_digest(code, expected):
            return True
    
    return False


class TOTPProvider(MFAProvider):
    """TOTP 提供者
    
    实现基于时间的一次性密码（RFC 6238）。
    
    Args:
        issuer: 发行者名称（显示在 Authenticator 中）
        digits: OTP 位数
        time_step: 时间步长（秒）
        window: 验证时允许的时间窗口
        secret_length: 密钥长度
        secret_store: 密钥存储回调
        secret_getter: 密钥获取回调
    """
    
    def __init__(
        self,
        issuer: str = "YWeb",
        digits: int = 6,
        time_step: int = 30,
        window: int = 1,
        secret_length: int = 32,
        secret_store: Callable[[Any, str], bool] = None,
        secret_getter: Callable[[Any], Optional[str]] = None,
    ):
        self.issuer = issuer
        self.digits = digits
        self.time_step = time_step
        self.window = window
        self.secret_length = secret_length
        
        # 存储回调
        self._secret_store = secret_store
        self._secret_getter = secret_getter
        
        # 内存存储（默认，生产环境应替换）
        self._secrets: Dict[Any, str] = {}
    
    def set_stores(
        self,
        store: Callable[[Any, str], bool],
        getter: Callable[[Any], Optional[str]],
    ) -> "TOTPProvider":
        """设置存储回调
        
        Args:
            store: 存储密钥的函数
            getter: 获取密钥的函数
            
        Returns:
            self: 支持链式调用
        """
        self._secret_store = store
        self._secret_getter = getter
        return self
    
    @property
    def mfa_type(self) -> MFAType:
        return MFAType.TOTP
    
    def setup(
        self,
        user_id: Any,
        username: str = None,
        email: str = None,
        **kwargs,
    ) -> MFASetupData:
        """设置 TOTP
        
        Args:
            user_id: 用户 ID
            username: 用户名（用于显示）
            email: 邮箱（用于显示）
            
        Returns:
            MFASetupData: 包含密钥和 URI
        """
        # 生成密钥
        secret = _generate_secret(self.secret_length)
        
        # 保存密钥
        self._save_secret(user_id, secret)
        
        # 构建账户名
        account = email or username or str(user_id)
        
        # 构建 URI
        uri = self._build_uri(secret, account)
        
        return MFASetupData(
            mfa_type=MFAType.TOTP,
            secret=secret,
            uri=uri,
            extra={
                "issuer": self.issuer,
                "digits": self.digits,
                "period": self.time_step,
            },
        )
    
    def _build_uri(self, secret: str, account: str) -> str:
        """构建 otpauth URI
        
        Args:
            secret: 密钥
            account: 账户名
            
        Returns:
            str: otpauth URI
        """
        # otpauth://totp/Issuer:account?secret=xxx&issuer=Issuer&digits=6&period=30
        label = f"{self.issuer}:{account}"
        params = {
            "secret": secret,
            "issuer": self.issuer,
            "digits": str(self.digits),
            "period": str(self.time_step),
        }
        param_str = "&".join(f"{k}={quote(v)}" for k, v in params.items())
        return f"otpauth://totp/{quote(label)}?{param_str}"
    
    def verify(
        self,
        user_id: Any,
        code: str,
        **kwargs,
    ) -> MFAVerifyResult:
        """验证 TOTP 代码
        
        Args:
            user_id: 用户 ID
            code: 6 位验证码
            
        Returns:
            MFAVerifyResult: 验证结果
        """
        # 获取密钥
        secret = self._get_secret(user_id)
        if not secret:
            return MFAVerifyResult.fail("TOTP not configured for this user")
        
        # 清理代码（移除空格）
        code = code.replace(" ", "").replace("-", "")
        
        # 验证长度
        if len(code) != self.digits:
            return MFAVerifyResult.fail(f"Code must be {self.digits} digits")
        
        # 验证代码
        if _verify_totp(
            secret=secret,
            code=code,
            time_step=self.time_step,
            digits=self.digits,
            window=self.window,
        ):
            return MFAVerifyResult.ok("TOTP verification successful")
        
        return MFAVerifyResult.fail("Invalid TOTP code")
    
    def is_enabled(self, user_id: Any) -> bool:
        """检查用户是否启用了 TOTP"""
        return self._get_secret(user_id) is not None
    
    def disable(self, user_id: Any) -> bool:
        """禁用用户的 TOTP"""
        if self._secret_store:
            return self._secret_store(user_id, None)
        if user_id in self._secrets:
            del self._secrets[user_id]
            return True
        return False
    
    def generate_current_code(self, user_id: Any) -> Optional[str]:
        """生成当前的 TOTP 代码（仅用于测试）
        
        Args:
            user_id: 用户 ID
            
        Returns:
            str: 当前的 TOTP 代码，或 None
        """
        secret = self._get_secret(user_id)
        if not secret:
            return None
        return _totp(secret, self.time_step, self.digits)
    
    def _save_secret(self, user_id: Any, secret: str) -> bool:
        """保存密钥"""
        if self._secret_store:
            return self._secret_store(user_id, secret)
        self._secrets[user_id] = secret
        return True
    
    def _get_secret(self, user_id: Any) -> Optional[str]:
        """获取密钥"""
        if self._secret_getter:
            return self._secret_getter(user_id)
        return self._secrets.get(user_id)
