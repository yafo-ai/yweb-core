"""密码工具测试"""

import pytest
import hashlib
from yweb.auth.password import (
    PasswordHelper, 
    hash_password, 
    verify_password, 
    needs_rehash,
    PasswordTooShortError,
    PasswordTooLongError,
)

from tests.helpers import get_password_helper_config


@pytest.fixture(autouse=True)
def reset_password_helper():
    """每个测试前后重置 PasswordHelper 配置"""

    original_config = get_password_helper_config()
    
    yield
    
    PasswordHelper.configure(
        md5_salt=original_config['md5_salt'],
        min_length=original_config['min_length'],
        max_length=original_config['max_length']
    )


class TestPasswordHelper:
    """PasswordHelper 测试"""
    
    def test_hash_returns_pbkdf2_format(self):
        """测试哈希返回 pbkdf2 格式"""
        hashed = PasswordHelper.hash("password123")
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_hash_unique_each_time(self):
        """测试每次哈希结果不同（随机盐值）"""
        hash1 = PasswordHelper.hash("password")
        hash2 = PasswordHelper.hash("password")
        assert hash1 != hash2  # 因为有随机盐值
    
    def test_verify_correct_password(self):
        """测试正确密码验证"""
        hashed = PasswordHelper.hash("correct_password")
        assert PasswordHelper.verify("correct_password", hashed) is True
    
    def test_verify_wrong_password(self):
        """测试错误密码验证"""
        hashed = PasswordHelper.hash("correct_password")
        assert PasswordHelper.verify("wrong_password", hashed) is False
    
    def test_verify_empty_hash(self):
        """测试空哈希返回 False"""
        assert PasswordHelper.verify("password", "") is False
        assert PasswordHelper.verify("password", None) is False
    
    def test_verify_md5_format(self):
        """测试 MD5 格式密码验证"""
        # 配置 MD5 盐值
        PasswordHelper.configure(md5_salt="test-salt")
        
        # 生成 MD5 哈希
        password = "test123"
        salted = password + "test-salt"
        md5_hash = hashlib.md5(salted.encode()).hexdigest()
        
        assert PasswordHelper.verify(password, md5_hash) is True
        assert PasswordHelper.verify("wrong", md5_hash) is False
        
        # 清理配置
        PasswordHelper.configure(md5_salt="")

    def test_verify_md5_with_missing_salt_fails(self):
        """测试未配置正确盐值时 MD5 验证失败"""
        password = "test123"
        salted_hash = hashlib.md5((password + "right-salt").encode()).hexdigest()
        PasswordHelper.configure(md5_salt="wrong-salt")
        assert PasswordHelper.verify(password, salted_hash) is False
    
    def test_verify_sha256_format(self):
        """测试 SHA256 格式密码验证"""
        password = "test123"
        sha256_hash = hashlib.sha256(password.encode()).hexdigest()
        
        assert PasswordHelper.verify(password, sha256_hash) is True
        assert PasswordHelper.verify("wrong", sha256_hash) is False
    
    def test_needs_rehash_pbkdf2(self):
        """测试 pbkdf2 格式不需要升级"""
        hashed = PasswordHelper.hash("password")
        assert PasswordHelper.needs_rehash(hashed) is False
    
    def test_needs_rehash_md5(self):
        """测试 MD5 格式需要升级"""
        md5_hash = hashlib.md5(b"password").hexdigest()
        assert PasswordHelper.needs_rehash(md5_hash) is True
    
    def test_needs_rehash_sha256(self):
        """测试 SHA256 格式需要升级"""
        sha256_hash = hashlib.sha256(b"password").hexdigest()
        assert PasswordHelper.needs_rehash(sha256_hash) is True
    
    def test_needs_rehash_empty(self):
        """测试空哈希需要升级"""
        assert PasswordHelper.needs_rehash("") is True
        assert PasswordHelper.needs_rehash(None) is True

    def test_verify_unknown_hash_format(self):
        """测试未知哈希格式返回 False"""
        assert PasswordHelper.verify("password", "not-a-valid-hash-format") is False

    def test_needs_rehash_unknown_hash_format(self):
        """测试未知哈希格式视为需要升级"""
        assert PasswordHelper.needs_rehash("not-a-valid-hash-format") is True
    
    def test_configure_md5_salt(self):
        """测试配置 MD5 盐值"""
        PasswordHelper.configure(md5_salt="custom-salt")
        config = get_password_helper_config()
        assert config['md5_salt'] == "custom-salt"


class TestPasswordLengthValidation:
    """密码长度验证测试"""
    
    def test_default_length_limits(self):
        """测试默认长度限制"""
        config = get_password_helper_config()
        assert config['min_length'] == 6
        assert config['max_length'] == 128
    
    def test_password_too_short(self):
        """测试密码太短"""
        with pytest.raises(PasswordTooShortError) as exc_info:
            PasswordHelper.hash("12345")  # 5 字符 < 6
        assert "6" in str(exc_info.value)
        assert "5" in str(exc_info.value)
    
    def test_password_too_long(self):
        """测试密码太长"""
        long_password = "a" * 129  # 129 字符 > 128
        with pytest.raises(PasswordTooLongError) as exc_info:
            PasswordHelper.hash(long_password)
        assert "128" in str(exc_info.value)
        assert "129" in str(exc_info.value)
    
    def test_password_min_length_ok(self):
        """测试刚好最小长度"""
        hashed = PasswordHelper.hash("123456")  # 6 字符
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_password_max_length_ok(self):
        """测试刚好最大长度"""
        password = "a" * 128
        hashed = PasswordHelper.hash(password)
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_configure_custom_min_length(self):
        """测试自定义最小长度"""
        PasswordHelper.configure(min_length=4)
        
        # 4 字符现在可以了
        hashed = PasswordHelper.hash("1234")
        assert hashed.startswith("$pbkdf2-sha256$")
        
        # 3 字符仍然不行
        with pytest.raises(PasswordTooShortError):
            PasswordHelper.hash("123")
    
    def test_configure_custom_max_length(self):
        """测试自定义最大长度"""
        PasswordHelper.configure(max_length=10)
        
        # 10 字符可以
        hashed = PasswordHelper.hash("1234567890")
        assert hashed.startswith("$pbkdf2-sha256$")
        
        # 11 字符不行
        with pytest.raises(PasswordTooLongError):
            PasswordHelper.hash("12345678901")

    def test_configure_custom_min_and_max_together(self):
        """测试同时配置最小和最大长度"""
        PasswordHelper.configure(min_length=8, max_length=12)
        PasswordHelper.hash("12345678")  # 下限可用
        PasswordHelper.hash("123456789012")  # 上限可用
        with pytest.raises(PasswordTooShortError):
            PasswordHelper.hash("1234567")
        with pytest.raises(PasswordTooLongError):
            PasswordHelper.hash("1234567890123")
    
    def test_skip_validation(self):
        """测试跳过验证"""
        # 即使密码太短，设置 validate=False 也可以哈希
        hashed = PasswordHelper.hash("abc", validate=False)
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_validate_length_method(self):
        """测试 validate_length 方法"""
        # 正常密码不抛异常
        PasswordHelper.validate_length("password123")
        
        # 太短抛异常
        with pytest.raises(PasswordTooShortError):
            PasswordHelper.validate_length("abc")
        
        # 太长抛异常
        with pytest.raises(PasswordTooLongError):
            PasswordHelper.validate_length("a" * 200)


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_hash_password(self):
        """测试 hash_password 函数"""
        hashed = hash_password("password")
        assert hashed.startswith("$pbkdf2-sha256$")
    
    def test_verify_password(self):
        """测试 verify_password 函数"""
        hashed = hash_password("password")
        assert verify_password("password", hashed) is True
        assert verify_password("wrong", hashed) is False
    
    def test_needs_rehash(self):
        """测试 needs_rehash 函数"""
        new_hash = hash_password("password")
        old_hash = hashlib.md5(b"password").hexdigest()
        
        assert needs_rehash(new_hash) is False
        assert needs_rehash(old_hash) is True


class TestPasswordUpgrade:
    """密码升级场景测试"""
    
    def test_upgrade_md5_to_pbkdf2(self):
        """测试从 MD5 升级到 pbkdf2"""
        # 配置 MD5 盐值
        PasswordHelper.configure(md5_salt="old-salt")
        
        password = "user_password"
        
        # 模拟旧的 MD5 密码
        salted = password + "old-salt"
        old_hash = hashlib.md5(salted.encode()).hexdigest()
        
        # 验证旧密码
        assert PasswordHelper.verify(password, old_hash) is True
        
        # 检查需要升级
        assert PasswordHelper.needs_rehash(old_hash) is True
        
        # 升级到新格式
        new_hash = PasswordHelper.hash(password)
        
        # 验证新密码
        assert PasswordHelper.verify(password, new_hash) is True
        assert PasswordHelper.needs_rehash(new_hash) is False
        
        # 清理配置
        PasswordHelper.configure(md5_salt="")
