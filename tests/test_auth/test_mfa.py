"""MFA 多因素认证模块测试

测试 TOTP、恢复码等 MFA 功能
"""

import pytest
from yweb.auth.mfa import (
    MFAManager,
    TOTPProvider,
    RecoveryCodeProvider,
    SMSProvider,
    EmailProvider,
    MFAType,
)


class TestTOTPProvider:
    """TOTP 提供者测试"""
    
    @pytest.fixture
    def totp_provider(self):
        """创建独立的 TOTP 提供者"""
        provider = TOTPProvider(
            issuer="TestApp",
            digits=6,
            time_step=30,
        )
        # 使用独立的内存存储
        secrets = {}
        provider.set_stores(
            store=lambda user_id, secret: secrets.update({user_id: secret}) or True,
            getter=lambda user_id: secrets.get(user_id),
        )
        return provider
    
    def test_mfa_type(self, totp_provider):
        """测试 MFA 类型"""
        assert totp_provider.mfa_type == MFAType.TOTP
    
    def test_setup_totp(self, totp_provider):
        """测试设置 TOTP"""
        setup_data = totp_provider.setup(
            user_id=1,
            username="testuser",
            email="test@example.com",
        )
        
        assert setup_data.mfa_type == MFAType.TOTP
        assert setup_data.secret is not None
        assert setup_data.uri is not None
        assert "otpauth://totp/" in setup_data.uri
        assert "TestApp" in setup_data.uri
    
    def test_verify_totp_with_generated_code(self, totp_provider):
        """测试使用生成的代码验证 TOTP"""
        totp_provider.setup(user_id=1, username="testuser")
        
        # 生成当前的有效代码
        code = totp_provider.generate_current_code(user_id=1)
        
        result = totp_provider.verify(user_id=1, code=code)
        
        assert result.success is True
    
    def test_verify_invalid_totp(self, totp_provider):
        """测试验证无效的 TOTP"""
        totp_provider.setup(user_id=1, username="testuser")
        
        result = totp_provider.verify(user_id=1, code="000000")
        
        assert result.success is False
    
    def test_is_enabled(self, totp_provider):
        """测试检查 TOTP 是否启用"""
        assert totp_provider.is_enabled(user_id=1) is False
        
        totp_provider.setup(user_id=1, username="testuser")
        
        assert totp_provider.is_enabled(user_id=1) is True
    
    def test_disable_totp(self, totp_provider):
        """测试禁用 TOTP"""
        totp_provider.setup(user_id=1, username="testuser")
        
        totp_provider.disable(user_id=1)
        
        assert totp_provider.is_enabled(user_id=1) is False

    def test_verify_totp_without_setup(self, totp_provider):
        """测试未配置 TOTP 时验证失败"""
        result = totp_provider.verify(user_id=999, code="123456")
        assert result.success is False
        assert "not configured" in result.message

    def test_verify_totp_with_invalid_length(self, totp_provider):
        """测试 TOTP 长度错误时返回明确失败信息"""
        totp_provider.setup(user_id=1, username="testuser")
        result = totp_provider.verify(user_id=1, code="12345")
        assert result.success is False
        assert "6 digits" in result.message


class TestRecoveryCodeProvider:
    """恢复码提供者测试"""
    
    @pytest.fixture
    def recovery_provider(self):
        """创建独立的恢复码提供者"""
        provider = RecoveryCodeProvider(
            code_count=10,
            code_length=8,
        )
        # 使用独立的内存存储
        storage = {}
        provider.set_stores(
            store=lambda user_id, code_set: storage.update({user_id: code_set}) or True,
            getter=lambda user_id: storage.get(user_id),
        )
        return provider
    
    def test_mfa_type(self, recovery_provider):
        """测试 MFA 类型"""
        assert recovery_provider.mfa_type == MFAType.RECOVERY
    
    def test_generate_recovery_codes(self, recovery_provider):
        """测试生成恢复码"""
        setup_data = recovery_provider.setup(user_id=1)
        
        assert setup_data.mfa_type == MFAType.RECOVERY
        assert len(setup_data.recovery_codes) == 10
        
        # 验证格式：XXXX-XXXX
        for code in setup_data.recovery_codes:
            assert "-" in code
            assert len(code) == 9  # 8 字符 + 1 分隔符
    
    def test_verify_recovery_code(self, recovery_provider):
        """测试验证恢复码"""
        setup_data = recovery_provider.setup(user_id=1)
        code = setup_data.recovery_codes[0]
        
        result = recovery_provider.verify(user_id=1, code=code)
        
        assert result.success is True
        assert result.recovery_code_used is True
    
    def test_recovery_code_single_use(self, recovery_provider):
        """测试恢复码只能使用一次"""
        setup_data = recovery_provider.setup(user_id=1)
        code = setup_data.recovery_codes[0]
        
        # 第一次使用
        result1 = recovery_provider.verify(user_id=1, code=code)
        assert result1.success is True
        
        # 第二次使用（应该失败）
        result2 = recovery_provider.verify(user_id=1, code=code)
        assert result2.success is False
    
    def test_remaining_count(self, recovery_provider):
        """测试剩余恢复码数量"""
        setup_data = recovery_provider.setup(user_id=1)
        
        assert recovery_provider.get_remaining_count(user_id=1) == 10
        
        # 使用一个恢复码
        recovery_provider.verify(user_id=1, code=setup_data.recovery_codes[0])
        
        assert recovery_provider.get_remaining_count(user_id=1) == 9
    
    def test_regenerate_codes(self, recovery_provider):
        """测试重新生成恢复码"""
        old_data = recovery_provider.setup(user_id=1)
        new_data = recovery_provider.regenerate(user_id=1)
        
        # 新旧恢复码应该不同
        assert old_data.recovery_codes != new_data.recovery_codes
        
        # 旧码不能用了
        result = recovery_provider.verify(user_id=1, code=old_data.recovery_codes[0])
        assert result.success is False


class TestSMSAndEmailProvider:
    """SMS 和邮件验证码提供者测试"""
    
    @pytest.fixture
    def sms_provider(self):
        """创建独立的 SMS 提供者"""
        provider = SMSProvider(
            code_length=6,
            expire_minutes=5,
            rate_limit_minutes=0,  # 测试时禁用频率限制
        )
        return provider
    
    @pytest.fixture
    def email_provider(self):
        """创建独立的邮件提供者"""
        provider = EmailProvider(
            code_length=6,
            expire_minutes=10,
            rate_limit_minutes=0,
        )
        return provider
    
    def test_sms_send_code(self, sms_provider):
        """测试发送短信验证码"""
        # 没有设置发送函数，使用开发模式
        success, msg = sms_provider.send_code(user_id=1, phone="+8613800138000")
        
        assert success is True
        assert "Code generated" in msg
    
    def test_email_send_code(self, email_provider):
        """测试发送邮件验证码"""
        success, msg = email_provider.send_code(user_id=1, email="test@example.com")
        
        assert success is True
    
    def test_verify_otp_code(self, sms_provider):
        """测试验证 OTP 代码"""
        # 生成验证码
        otp_code = sms_provider.generate_code(user_id=1, target="+8613800138000")
        
        # 验证
        result = sms_provider.verify(user_id=1, code=otp_code.code)
        
        assert result.success is True
    
    def test_otp_max_attempts(self, sms_provider):
        """测试 OTP 最大尝试次数"""
        sms_provider.generate_code(user_id=1)
        
        # 尝试错误代码
        for _ in range(3):
            result = sms_provider.verify(user_id=1, code="000000")
        
        # 超过最大尝试次数
        assert result.remaining_attempts == 0

    def test_sms_rate_limit(self):
        """测试短信发送频率限制"""
        provider = SMSProvider(code_length=6, expire_minutes=5, rate_limit_minutes=10)
        ok1, _ = provider.send_code(user_id=1, phone="+8613800138000")
        ok2, msg2 = provider.send_code(user_id=1, phone="+8613800138000")
        assert ok1 is True
        assert ok2 is False
        assert "Please wait" in msg2


class TestMFAManager:
    """MFA 管理器测试"""
    
    @pytest.fixture
    def mfa_manager(self):
        """创建独立的 MFA 管理器"""
        manager = MFAManager()
        
        # 注册提供者（每个使用独立存储）
        totp = TOTPProvider(issuer="TestApp")
        totp_secrets = {}
        totp.set_stores(
            store=lambda user_id, secret: totp_secrets.update({user_id: secret}) or True,
            getter=lambda user_id: totp_secrets.get(user_id),
        )
        
        recovery = RecoveryCodeProvider()
        recovery_storage = {}
        recovery.set_stores(
            store=lambda user_id, code_set: recovery_storage.update({user_id: code_set}) or True,
            getter=lambda user_id: recovery_storage.get(user_id),
        )
        
        manager.register_provider("totp", totp)
        manager.register_provider("recovery", recovery)
        
        return manager
    
    def test_register_provider(self, mfa_manager):
        """测试注册提供者"""
        providers = mfa_manager.list_providers()
        
        assert "totp" in providers
        assert "recovery" in providers
    
    def test_setup_mfa(self, mfa_manager):
        """测试设置 MFA"""
        setup_data = mfa_manager.setup(
            user_id=1,
            provider_name="totp",
            username="testuser",
        )
        
        assert setup_data is not None
        assert setup_data.mfa_type == MFAType.TOTP
    
    def test_get_enabled_providers(self, mfa_manager):
        """测试获取已启用的提供者"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        mfa_manager.setup(user_id=1, provider_name="recovery")
        
        enabled = mfa_manager.get_enabled_providers(user_id=1)
        
        assert "totp" in enabled
        assert "recovery" in enabled
    
    def test_is_enabled(self, mfa_manager):
        """测试检查 MFA 是否启用"""
        assert mfa_manager.is_enabled(user_id=1) is False
        
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        
        assert mfa_manager.is_enabled(user_id=1) is True
    
    def test_disable_mfa(self, mfa_manager):
        """测试禁用特定 MFA"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        mfa_manager.setup(user_id=1, provider_name="recovery")
        
        mfa_manager.disable(user_id=1, provider_name="totp")
        
        enabled = mfa_manager.get_enabled_providers(user_id=1)
        assert "totp" not in enabled
        assert "recovery" in enabled
    
    def test_disable_all_mfa(self, mfa_manager):
        """测试禁用所有 MFA"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        mfa_manager.setup(user_id=1, provider_name="recovery")
        
        mfa_manager.disable_all(user_id=1)
        
        assert mfa_manager.is_enabled(user_id=1) is False

    def test_verify_unknown_provider(self, mfa_manager):
        """测试验证不存在的提供者"""
        result = mfa_manager.verify(user_id=1, provider_name="unknown", code="123456")
        assert result.success is False
        assert "not found" in result.message

    def test_verify_any_without_enabled_provider(self, mfa_manager):
        """测试未配置 MFA 时 verify_any 失败"""
        result = mfa_manager.verify_any(user_id=1, code="123456")
        assert result.success is False
        assert "No MFA configured" in result.message

    def test_verify_any_with_invalid_code(self, mfa_manager):
        """测试 verify_any 在所有方式失败时返回统一错误"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        result = mfa_manager.verify_any(user_id=1, code="000000")
        assert result.success is False
        assert result.message == "Invalid verification code"

    def test_verify_any_success_with_one_provider(self, mfa_manager):
        """测试 verify_any 任一方式成功即通过"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        provider = mfa_manager.get_provider("totp")
        code = provider.generate_current_code(user_id=1)
        result = mfa_manager.verify_any(user_id=1, code=code)
        assert result.success is True

    def test_primary_provider_flow(self, mfa_manager):
        """测试首选 MFA 提供者设置与读取"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        mfa_manager.setup(user_id=1, provider_name="recovery")
        assert mfa_manager.set_primary_provider(user_id=1, provider_name="totp") is True
        assert mfa_manager.get_primary_provider(user_id=1) == "totp"

    def test_primary_provider_fallback_to_first_enabled(self, mfa_manager):
        """测试首选方式未配置时回退到第一个启用方式"""
        mfa_manager.setup(user_id=1, provider_name="totp", username="testuser")
        mfa_manager.setup(user_id=1, provider_name="recovery")
        assert mfa_manager.get_primary_provider(user_id=1) == "totp"

    def test_set_primary_provider_unknown_returns_false(self, mfa_manager):
        """测试设置不存在的首选提供者返回 False"""
        assert mfa_manager.set_primary_provider(user_id=1, provider_name="unknown") is False
