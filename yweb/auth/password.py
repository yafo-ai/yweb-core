"""密码工具模块

提供安全的密码哈希和验证功能。

使用示例:
    from yweb.auth import PasswordHelper
    
    # 配置密码长度限制
    PasswordHelper.configure(min_length=6, max_length=128)
    
    # 哈希密码
    hashed = PasswordHelper.hash("my_password")
    
    # 验证密码
    if PasswordHelper.verify("my_password", hashed):
        print("密码正确")
    
    # 检查是否需要重新哈希（升级算法）
    if PasswordHelper.needs_rehash(old_hash):
        new_hash = PasswordHelper.hash(password)
"""

from typing import Optional, Callable, List
from passlib.context import CryptContext

# 密码哈希上下文
# 默认使用 pbkdf2_sha256，同时支持验证旧的 MD5 和 SHA256 格式
_pwd_context = CryptContext(
    schemes=["pbkdf2_sha256"],
    deprecated="auto"
)


class PasswordTooShortError(ValueError):
    """密码太短"""
    pass


class PasswordTooLongError(ValueError):
    """密码太长"""
    pass


class PasswordHelper:
    """密码工具类
    
    提供密码哈希、验证和升级功能。
    默认使用 pbkdf2_sha256 算法，比 MD5/SHA256 更安全。
    
    特点:
    - 自带随机盐值，每次哈希结果不同
    - 支持旧格式（MD5、SHA256）的验证和自动升级
    - 可配置密码长度限制
    - 线程安全
    
    使用示例:
        # 配置
        PasswordHelper.configure(min_length=6, max_length=128)
        
        # 基础用法
        hash = PasswordHelper.hash("password123")
        is_valid = PasswordHelper.verify("password123", hash)
        
        # 检查是否需要升级
        if PasswordHelper.needs_rehash(old_hash):
            new_hash = PasswordHelper.hash(password)
    """
    
    # 密码长度限制（默认值）
    _min_length: int = 6      # 最小 6 字符
    _max_length: int = 128    # 最大 128 字符
    
    # 用于兼容旧 MD5 格式的盐值（可被业务项目覆盖）
    _md5_salt: str = ""
    
    @classmethod
    def configure(
        cls,
        md5_salt: Optional[str] = None,
        min_length: Optional[int] = None,
        max_length: Optional[int] = None,
    ) -> None:
        """配置密码工具
        
        Args:
            md5_salt: MD5 兼容模式的盐值（用于验证旧数据）
            min_length: 密码最小长度（默认 6）
            max_length: 密码最大长度（默认 128）
        """
        if md5_salt is not None:
            cls._md5_salt = md5_salt
        if min_length is not None:
            cls._min_length = min_length
        if max_length is not None:
            cls._max_length = max_length
    
    @classmethod
    def validate_length(cls, password: str) -> None:
        """验证密码长度
        
        Args:
            password: 明文密码
            
        Raises:
            PasswordTooShortError: 密码太短
            PasswordTooLongError: 密码太长
        """
        if len(password) < cls._min_length:
            raise PasswordTooShortError(
                f"密码长度不能少于 {cls._min_length} 个字符，当前 {len(password)} 个字符"
            )
        if len(password) > cls._max_length:
            raise PasswordTooLongError(
                f"密码长度不能超过 {cls._max_length} 个字符，当前 {len(password)} 个字符"
            )
    
    @classmethod
    def hash(cls, password: str, validate: bool = True) -> str:
        """对密码进行哈希处理
        
        使用 pbkdf2_sha256 算法，自带随机盐值。
        
        Args:
            password: 明文密码
            validate: 是否验证密码长度（默认 True）
            
        Returns:
            哈希后的密码字符串（格式：$pbkdf2-sha256$...）
            
        Raises:
            PasswordTooShortError: 密码太短
            PasswordTooLongError: 密码太长
        """
        if validate:
            cls.validate_length(password)
        return _pwd_context.hash(password)
    
    @classmethod
    def verify(cls, password: str, hash: str) -> bool:
        """验证密码
        
        支持多种哈希格式：
        - pbkdf2_sha256（推荐）
        - MD5（32位十六进制，需配置 md5_salt）
        - SHA256（64位十六进制）
        
        Args:
            password: 明文密码
            hash: 数据库存储的哈希值
            
        Returns:
            密码是否匹配
        """
        if not hash:
            return False
        
        # pbkdf2_sha256 格式
        if hash.startswith("$pbkdf2"):
            return _pwd_context.verify(password, hash)
        
        # MD5 格式（32位十六进制）
        if len(hash) == 32 and cls._is_hex(hash):
            return cls._verify_md5(password, hash)
        
        # SHA256 格式（64位十六进制）
        if len(hash) == 64 and cls._is_hex(hash):
            return cls._verify_sha256(password, hash)
        
        # 尝试用 passlib 验证其他格式
        try:
            return _pwd_context.verify(password, hash)
        except Exception:
            return False
    
    @classmethod
    def needs_rehash(cls, hash: str) -> bool:
        """检查密码哈希是否需要升级
        
        以下情况需要升级：
        - MD5 格式（32位）
        - SHA256 格式（64位）
        - passlib 认为需要升级的格式
        
        Args:
            hash: 数据库存储的哈希值
            
        Returns:
            是否需要重新哈希
        """
        if not hash:
            return True
        
        # MD5 或 SHA256 格式需要升级
        if len(hash) in (32, 64) and cls._is_hex(hash):
            return True
        
        # 让 passlib 判断是否需要升级
        try:
            return _pwd_context.needs_update(hash)
        except Exception:
            return True
    
    @classmethod
    def _is_hex(cls, s: str) -> bool:
        """检查字符串是否为十六进制"""
        try:
            int(s, 16)
            return True
        except ValueError:
            return False
    
    @classmethod
    def _verify_md5(cls, password: str, hash: str) -> bool:
        """验证 MD5 格式密码"""
        import hashlib
        salted = password + cls._md5_salt
        computed = hashlib.md5(salted.encode('utf-8')).hexdigest()
        return computed == hash
    
    @classmethod
    def _verify_sha256(cls, password: str, hash: str) -> bool:
        """验证 SHA256 格式密码"""
        import hashlib
        computed = hashlib.sha256(password.encode('utf-8')).hexdigest()
        return computed == hash


# 便捷函数
def hash_password(password: str) -> str:
    """对密码进行哈希处理（便捷函数）"""
    return PasswordHelper.hash(password)


def verify_password(password: str, hash: str) -> bool:
    """验证密码（便捷函数）"""
    return PasswordHelper.verify(password, hash)


def needs_rehash(hash: str) -> bool:
    """检查是否需要重新哈希（便捷函数）"""
    return PasswordHelper.needs_rehash(hash)
