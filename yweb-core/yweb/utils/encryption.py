#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
加密工具模块
提供密码哈希和验证功能
"""

import hashlib
import secrets


class EncryptionUtil:
    """加密工具类"""
    
    # 默认盐值（建议在实际使用时通过配置覆盖）
    DEFAULT_SALT = "yweb-default-salt"
    
    def __init__(self, salt: str = None):
        """初始化加密工具
        
        Args:
            salt: 自定义盐值，如果不提供则使用默认值
        """
        self.salt = salt or self.DEFAULT_SALT
    
    @staticmethod
    def generate_salt(length: int = 32) -> str:
        """生成随机盐值
        
        Args:
            length: 盐值长度（字节数），默认32字节
            
        Returns:
            十六进制格式的随机盐值字符串
        """
        return secrets.token_hex(length)
    
    @staticmethod
    def generate_password(length: int = 16) -> str:
        """生成随机密码
        
        Args:
            length: 密码长度，默认16个字符
            
        Returns:
            包含字母和数字的随机密码字符串
        """
        import string
        alphabet = string.ascii_letters + string.digits
        return ''.join(secrets.choice(alphabet) for _ in range(length))
    
    @staticmethod
    def generate_token(length: int = 32) -> str:
        """生成随机令牌
        
        Args:
            length: 令牌字节长度，默认32字节
            
        Returns:
            URL安全的随机令牌字符串
        """
        return secrets.token_urlsafe(length)
    
    def hash_password_md5(self, password: str) -> str:
        """使用MD5加盐对密码进行哈希处理
        
        Args:
            password: 原始密码
            
        Returns:
            MD5哈希后的密码字符串
        """
        # 将密码和盐值组合
        salted_password = password + self.salt
        # 创建MD5哈希对象
        md5_hash = hashlib.md5()
        # 更新哈希对象
        md5_hash.update(salted_password.encode('utf-8'))
        # 返回十六进制格式的哈希值
        return md5_hash.hexdigest()
    
    def verify_password_md5(self, password: str, stored_hash: str) -> bool:
        """验证MD5哈希后的密码
        
        Args:
            password: 原始密码
            stored_hash: 数据库存储的MD5哈希值
            
        Returns:
            密码是否匹配
        """
        # 对输入密码进行相同的哈希处理
        hashed_input = self.hash_password_md5(password)
        # 比较哈希值
        return hashed_input == stored_hash
    
    def verify_encrypted_password(self, encrypted_password: str, stored_hash: str) -> bool:
        """验证加密后的密码（兼容旧的SHA256哈希）
        
        Args:
            encrypted_password: 前端SHA256哈希后的密码
            stored_hash: 数据库存储的密码哈希
            
        Returns:
            密码是否匹配
        """
        return encrypted_password == stored_hash


# 默认加密工具实例
default_encryption = EncryptionUtil()

# 便捷函数
def hash_password(password: str, salt: str = None) -> str:
    """哈希密码的便捷函数
    
    Args:
        password: 原始密码
        salt: 可选的自定义盐值
        
    Returns:
        哈希后的密码
    """
    if salt:
        util = EncryptionUtil(salt)
        return util.hash_password_md5(password)
    return default_encryption.hash_password_md5(password)


def verify_password(password: str, stored_hash: str, salt: str = None) -> bool:
    """验证密码的便捷函数
    
    Args:
        password: 原始密码
        stored_hash: 存储的哈希值
        salt: 可选的自定义盐值
        
    Returns:
        密码是否匹配
    """
    if salt:
        util = EncryptionUtil(salt)
        return util.verify_password_md5(password, stored_hash)
    return default_encryption.verify_password_md5(password, stored_hash)

