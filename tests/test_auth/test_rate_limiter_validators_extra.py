"""rate_limiter / validators 补充测试"""

from datetime import datetime, timedelta

import pytest

from yweb.auth.rate_limiter import LoginRateLimiter
from yweb.auth.validators import PasswordStrength, PasswordValidator, UsernameValidator, ValidationError


class TestLoginRateLimiterExtra:
    """LoginRateLimiter 补充分支测试"""

    def test_block_flow_and_manual_unblock(self):
        limiter = LoginRateLimiter(max_attempts=2, block_minutes=1, window_minutes=1)
        ip = "10.0.0.1"

        blocked, remaining = limiter.record_failure(ip)
        assert blocked is False
        assert remaining == 1

        blocked, remaining = limiter.record_failure(ip)
        assert blocked is True
        assert remaining == 0
        assert limiter.is_blocked(ip) is True
        assert limiter.get_remaining_attempts(ip) == 0
        assert limiter.get_block_remaining_seconds(ip) >= 0

        assert limiter.unblock(ip) is True
        assert limiter.is_blocked(ip) is False
        assert limiter.unblock(ip) is False

    def test_expired_block_is_auto_cleaned(self):
        limiter = LoginRateLimiter(max_attempts=2, block_minutes=1, window_minutes=1)
        ip = "10.0.0.2"
        limiter._blocked[ip] = datetime.now() - timedelta(seconds=1)
        limiter._attempts[ip] = {"count": 3, "window_start": datetime.now() - timedelta(minutes=5)}

        assert limiter.is_blocked(ip) is False
        assert ip not in limiter._blocked
        assert ip not in limiter._attempts

    def test_get_remaining_attempts_with_expired_window(self):
        limiter = LoginRateLimiter(max_attempts=3, block_minutes=1, window_minutes=1)
        ip = "10.0.0.3"
        limiter._attempts[ip] = {"count": 2, "window_start": datetime.now() - timedelta(minutes=2)}
        assert limiter.get_remaining_attempts(ip) == 3

    def test_record_failure_when_already_blocked_and_cleanup(self):
        limiter = LoginRateLimiter(max_attempts=3, block_minutes=1, window_minutes=1)
        ip = "10.0.0.4"
        limiter._blocked[ip] = datetime.now() + timedelta(seconds=30)

        blocked, remaining = limiter.record_failure(ip)
        assert blocked is True
        assert remaining == 0

        limiter._blocked["10.0.0.5"] = datetime.now() - timedelta(seconds=1)
        limiter._attempts["10.0.0.6"] = {"count": 1, "window_start": datetime.now() - timedelta(minutes=2)}
        cleaned = limiter.cleanup()
        assert cleaned >= 2

    def test_get_blocked_ips_and_reset_behavior(self):
        limiter = LoginRateLimiter(max_attempts=3, block_minutes=1, window_minutes=1)
        limiter._blocked["x1"] = datetime.now() + timedelta(minutes=1)
        limiter._blocked["x2"] = datetime.now() - timedelta(seconds=1)
        limiter._attempts["x2"] = {"count": 9, "window_start": datetime.now()}
        ips = limiter.get_blocked_ips()
        assert "x1" in ips
        assert "x2" not in ips

        limiter._attempts["x1"] = {"count": 2, "window_start": datetime.now()}
        limiter.reset("x1")
        assert "x1" not in limiter._attempts
        # reset 不会解除封锁
        assert "x1" in limiter._blocked

    def test_get_block_remaining_seconds_not_blocked(self):
        """测试未封锁 IP 的剩余秒数为 0"""
        limiter = LoginRateLimiter(max_attempts=3, block_minutes=1, window_minutes=1)
        assert limiter.get_block_remaining_seconds("not-blocked") == 0


class TestValidatorsExtra:
    """validators 补充分支测试"""

    def test_password_validator_strength_and_raise(self):
        basic = PasswordValidator.of(PasswordStrength.BASIC, min_length=6)
        assert basic.validate_instance("abc123") is True
        assert basic.validate_instance("abcdef") is False

        medium = PasswordValidator.of(PasswordStrength.MEDIUM, min_length=6)
        assert medium.validate_instance("Abc123") is True
        assert medium.validate_instance("abc123") is False

        strong = PasswordValidator.of(PasswordStrength.STRONG, min_length=8)
        with pytest.raises(ValidationError) as exc:
            strong.validate_instance_or_raise("Abcdef12")
        assert "特殊字符" in ";".join(exc.value.errors)

    def test_password_validator_configure_class_methods(self):
        old_strength = PasswordValidator._default_strength
        old_min = PasswordValidator._default_min_length
        old_max = PasswordValidator._default_max_length
        try:
            PasswordValidator.configure(strength=PasswordStrength.BASIC, min_length=6, max_length=10)
            assert PasswordValidator.validate("abc123") is True
            assert PasswordValidator.validate("ab12") is False
            with pytest.raises(ValidationError):
                PasswordValidator.validate_or_raise("abcdef")
        finally:
            PasswordValidator.configure(strength=old_strength, min_length=old_min, max_length=old_max)

    def test_username_validator_errors_and_configure(self):
        v = UsernameValidator(min_length=2, max_length=5, allow_chinese=False)
        assert v.get_errors("") == ["用户名不能为空"]
        assert v.validate_instance("ab_1") is True
        assert v.validate_instance("中文") is False
        assert v.validate_instance("abcde6") is False

        with pytest.raises(ValidationError):
            v.validate_instance_or_raise("中文")

        old_min = UsernameValidator._default_min_length
        old_max = UsernameValidator._default_max_length
        old_allow = UsernameValidator._default_allow_chinese
        try:
            UsernameValidator.configure(min_length=3, max_length=10, allow_chinese=False)
            assert UsernameValidator.validate("abc_123") is True
            assert UsernameValidator.validate("中a") is False
            with pytest.raises(ValidationError):
                UsernameValidator.validate_or_raise("ab")
        finally:
            UsernameValidator.configure(min_length=old_min, max_length=old_max, allow_chinese=old_allow)

    def test_username_validator_validate_or_raise_empty(self):
        """测试空用户名触发 ValidationError"""
        with pytest.raises(ValidationError) as exc:
            UsernameValidator.validate_or_raise("")
        assert "用户名不能为空" in ";".join(exc.value.errors)
