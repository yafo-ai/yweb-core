"""加密工具测试

测试密码哈希和验证功能
"""

import pytest

from yweb.utils import (
    hash_password,
    verify_password,
    EncryptionUtil,
)


class TestHashPassword:
    """hash_password 函数测试"""
    
    def test_hash_password_basic(self):
        """测试基本密码哈希"""
        password = "mypassword123"
        hashed = hash_password(password)
        
        assert hashed is not None
        assert hashed != password
        assert len(hashed) > 0
    
    def test_hash_password_is_deterministic_with_default_salt(self):
        """测试默认盐值下同一密码哈希结果稳定"""
        password = "samepassword"
        hash1 = hash_password(password)
        hash2 = hash_password(password)
        assert hash1 == hash2

    def test_hash_password_with_custom_salt_changes_result(self):
        """测试自定义盐值会影响哈希结果"""
        password = "samepassword"
        default_hash = hash_password(password)
        custom_hash = hash_password(password, salt="custom_salt")
        assert custom_hash != default_hash
    
    def test_hash_password_unicode(self):
        """测试 Unicode 密码"""
        password = "密码123中文"
        hashed = hash_password(password)
        
        assert hashed is not None
        assert len(hashed) > 0
    
    def test_hash_password_empty_string(self):
        """测试空字符串密码"""
        password = ""
        hashed = hash_password(password)
        
        # 空字符串也应该能被哈希
        assert hashed is not None
        assert len(hashed) > 0
    
    def test_hash_password_long_password(self):
        """测试超长密码"""
        # bcrypt 限制密码长度为 72 字节
        password = "a" * 100
        hashed = hash_password(password)
        
        assert hashed is not None
    
    def test_hash_password_special_characters(self):
        """测试特殊字符密码"""
        password = "!@#$%^&*()_+-=[]{}|;':\",./<>?"
        hashed = hash_password(password)
        
        assert hashed is not None


class TestVerifyPassword:
    """verify_password 函数测试"""
    
    def test_verify_correct_password(self):
        """测试验证正确密码"""
        password = "correctpassword"
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) == True
    
    def test_verify_wrong_password(self):
        """测试验证错误密码"""
        password = "correctpassword"
        wrong_password = "wrongpassword"
        hashed = hash_password(password)
        
        assert verify_password(wrong_password, hashed) == False
    
    def test_verify_case_sensitive(self):
        """测试密码区分大小写"""
        password = "Password123"
        hashed = hash_password(password)
        
        assert verify_password("Password123", hashed) == True
        assert verify_password("password123", hashed) == False
        assert verify_password("PASSWORD123", hashed) == False
    
    def test_verify_unicode_password(self):
        """测试验证 Unicode 密码"""
        password = "密码123"
        hashed = hash_password(password)
        
        assert verify_password("密码123", hashed) == True
        assert verify_password("密码124", hashed) == False
    
    def test_verify_invalid_hash(self):
        """测试无效的哈希值"""
        password = "password"
        invalid_hash = "not_a_valid_hash"
        assert verify_password(password, invalid_hash) == False


class TestEncryptionUtil:
    """EncryptionUtil 类测试"""
    
    def test_create_instance(self):
        """测试创建实例"""
        util = EncryptionUtil()
        assert util is not None
        assert util.salt == EncryptionUtil.DEFAULT_SALT
    
    def test_hash_and_verify(self):
        """测试哈希和验证"""
        util = EncryptionUtil()
        password = "testpassword"
        
        hashed = hash_password(password)
        
        assert verify_password(password, hashed) == True
        assert verify_password("wrongpassword", hashed) == False
    
    def test_hash_with_salt(self):
        """测试带盐值的哈希"""
        util = EncryptionUtil(salt="custom_salt")
        password = "password"

        hashed = util.hash_password_md5(password)

        assert util.verify_password_md5(password, hashed) == True
        assert verify_password(password, hashed, salt="custom_salt") == True
        assert verify_password(password, hashed, salt="another_salt") == False
    
    def test_generate_random_salt(self):
        """测试生成随机盐值"""
        salt1 = EncryptionUtil.generate_salt()
        salt2 = EncryptionUtil.generate_salt()
        
        assert salt1 is not None
        assert salt2 is not None
        assert salt1 != salt2
    
    def test_generate_random_password(self):
        """测试生成随机密码"""
        password = EncryptionUtil.generate_password(length=16)
        
        assert password is not None
        assert len(password) == 16
    
    def test_generate_password_custom_length(self):
        """测试自定义长度的随机密码"""
        for length in [8, 12, 20, 32]:
            password = EncryptionUtil.generate_password(length=length)
            assert len(password) == length
    
    def test_generate_token(self):
        """测试生成随机令牌"""
        token = EncryptionUtil.generate_token(length=32)
        
        assert token is not None
        assert len(token) > 0
    
    def test_tokens_are_unique(self):
        """测试生成的令牌唯一"""
        tokens = set()
        for _ in range(100):
            token = EncryptionUtil.generate_token()
            assert token not in tokens
            tokens.add(token)


class TestPasswordComplexity:
    """密码复杂度测试"""
    
    def test_weak_passwords_still_hash(self):
        """测试弱密码也能被哈希"""
        weak_passwords = ["123", "abc", "password", "1"]
        
        for pwd in weak_passwords:
            hashed = hash_password(pwd)
            assert hashed is not None
            assert verify_password(pwd, hashed) == True
    
    def test_complex_password(self):
        """测试复杂密码"""
        complex_password = "MyC0mpl3x!P@ssw0rd#2024"
        hashed = hash_password(complex_password)
        
        assert verify_password(complex_password, hashed) == True

