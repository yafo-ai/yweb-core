"""用户安全 Mixins 测试"""

import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

from yweb.auth.mixins import (
    LockableMixin,
    PasswordMixin,
    LastLoginMixin,
    FullUserMixin,
)

from tests.helpers import (
    get_lock_status,
    get_failed_attempts_info,
    get_password_info,
    verify_password_format,
    get_last_login_info,
)


class MockLockableUser(LockableMixin):
    """模拟可锁定用户（用于测试）"""

    def __init__(self):
        self.is_active = True
        self.is_locked = False
        self.locked_at = None
        self.locked_until = None
        self.lock_reason = None
        self.failed_login_attempts = 0
        self.last_failed_login_at = None
        self.update_calls = []

    def update(self, commit: bool = True):
        """模拟更新方法"""
        self.update_calls.append(commit)


class MockPasswordUser(PasswordMixin):
    """模拟带密码管理的用户"""

    def __init__(self):
        self.password_hash = ""
        self.password_changed_at = None
        self.password_expires_days = 0
        self.must_change_password = False
        self.update_calls = []

    def update(self, commit: bool = True):
        self.update_calls.append(commit)


class MockLastLoginUser(LastLoginMixin):
    """模拟带最后登录信息的用户"""

    def __init__(self):
        self.last_login_at = None
        self.last_login_ip = None
        self.update_calls = []

    def update(self, commit: bool = True):
        self.update_calls.append(commit)


class MockFullUser(FullUserMixin):
    """模拟完整用户"""

    def __init__(self):
        # LockableMixin 字段
        self.is_active = True
        self.is_locked = False
        self.locked_at = None
        self.locked_until = None
        self.lock_reason = None
        self.failed_login_attempts = 0
        self.last_failed_login_at = None
        # PasswordMixin 字段
        self.password_hash = ""
        self.password_changed_at = None
        self.password_expires_days = 0
        self.must_change_password = False
        # LastLoginMixin 字段
        self.last_login_at = None
        self.last_login_ip = None
        self.update_calls = []

    def update(self, commit: bool = True):
        self.update_calls.append(commit)


class TestLockableMixin:
    """可锁定用户 Mixin 测试"""

    @pytest.fixture
    def user(self):
        return MockLockableUser()

    def test_initial_state(self, user):
        """测试初始状态"""
        assert user.is_active is True
        assert user.is_locked is False
        assert user.can_login is True

    def test_lock_permanently(self, user):
        """测试永久锁定"""
        user.lock(reason="违规操作")

        lock_status = get_lock_status(user)
        assert lock_status['is_locked'] is True
        assert lock_status['locked_at'] is not None
        assert lock_status['locked_until'] is None  # 永久锁定
        assert lock_status['lock_reason'] == "违规操作"
        assert user.can_login is False
        assert user.update_calls[-1] is True

    def test_lock_with_duration(self, user):
        """测试限时锁定"""
        user.lock(reason="登录失败", duration_minutes=30)

        assert user.is_locked is True
        assert user.locked_until is not None

        # locked_until 应该在 30 分钟后
        expected = datetime.now(timezone.utc) + timedelta(minutes=30)
        diff = abs((user.locked_until - expected).total_seconds())
        assert diff < 5  # 允许 5 秒误差

    def test_unlock(self, user):
        """测试解锁"""
        user.lock(reason="test")
        user.unlock()

        lock_status = get_lock_status(user)
        assert lock_status['is_locked'] is False
        assert lock_status['locked_at'] is None
        assert lock_status['locked_until'] is None
        assert lock_status['lock_reason'] is None
        
        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 0
        assert user.can_login is True
        assert user.update_calls[-1] is True

    def test_lock_with_commit_false(self, user):
        """测试 lock(commit=False) 不触发更新"""
        user.lock(reason="test", commit=False)
        assert user.is_locked is True
        assert user.update_calls == []

    def test_check_lock_expired(self, user):
        """测试锁定过期检查"""
        # 未锁定
        assert user.check_lock_expired() is False

        # 永久锁定
        user.lock(reason="test")
        assert user.check_lock_expired() is False

        # 已过期的锁定
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)
        assert user.check_lock_expired() is True

    def test_auto_unlock_if_expired(self, user):
        """测试自动解锁"""
        # 设置过期的锁定
        user.is_locked = True
        user.locked_until = datetime.now(timezone.utc) - timedelta(minutes=1)

        result = user.auto_unlock_if_expired()

        assert result is True
        assert user.is_locked is False

    def test_auto_unlock_not_expired(self, user):
        """测试未过期不自动解锁"""
        user.lock(reason="test", duration_minutes=30)

        result = user.auto_unlock_if_expired()

        assert result is False
        assert user.is_locked is True

    def test_record_failed_login(self, user):
        """测试记录登录失败"""
        # 第一次失败
        is_locked = user.record_failed_login(max_attempts=3)
        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 1
        assert is_locked is False

        # 第二次失败
        is_locked = user.record_failed_login(max_attempts=3)
        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 2
        assert is_locked is False

        # 第三次失败 - 触发锁定
        is_locked = user.record_failed_login(max_attempts=3, lock_duration_minutes=15)
        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 3
        assert is_locked is True
        
        lock_status = get_lock_status(user)
        assert lock_status['is_locked'] is True

    def test_reset_failed_attempts(self, user):
        """测试重置失败计数"""
        user.failed_login_attempts = 3
        user.last_failed_login_at = datetime.now(timezone.utc)

        user.reset_failed_attempts()

        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 0
        assert attempts_info['last_failed_login_at'] is None

    def test_record_failed_login_immediate_lock_when_max_is_one(self, user):
        """测试最大失败次数为 1 时立即锁定"""
        is_locked = user.record_failed_login(max_attempts=1, lock_duration_minutes=10)
        assert is_locked is True
        assert user.is_locked is True

    def test_disable_enable(self, user):
        """测试禁用和启用"""
        user.disable()
        assert user.is_active is False
        assert user.can_login is False

        user.enable()
        assert user.is_active is True
        assert user.can_login is True

    def test_can_login_locked(self, user):
        """测试锁定时不能登录"""
        user.lock(reason="test")
        assert user.can_login is False

    def test_can_login_disabled(self, user):
        """测试禁用时不能登录"""
        user.disable()
        assert user.can_login is False


class TestPasswordMixin:
    """密码管理 Mixin 测试"""

    @pytest.fixture
    def user(self):
        return MockPasswordUser()

    def test_set_password_default_hash(self, user):
        """测试使用默认哈希设置密码（pbkdf2_sha256）"""
        user.set_password("mypassword123")

        # 默认使用 pbkdf2_sha256，格式为 $pbkdf2-sha256$...
        assert verify_password_format(user, "$pbkdf2-sha256$")
        
        password_info = get_password_info(user)
        assert password_info['password_changed_at'] is not None
        assert password_info['must_change_password'] is False
        
        # 验证密码可以正确验证
        assert user.verify_password("mypassword123") is True
        assert user.verify_password("wrongpassword") is False

    def test_set_password_custom_hash(self, user):
        """测试使用自定义哈希函数"""
        custom_hash = lambda p: f"custom_{p}_hash"

        user.set_password("mypassword", hash_func=custom_hash)

        assert user.password_hash == "custom_mypassword_hash"

    def test_set_password_with_commit_true(self, user):
        """测试设置密码时 commit=True 会触发更新"""
        user.set_password("abc123", commit=True)
        assert user.update_calls[-1] is True

    def test_verify_password_default(self, user):
        """测试默认密码验证"""
        user.set_password("correct_password")

        assert user.verify_password("correct_password") is True
        assert user.verify_password("wrong_password") is False

    def test_verify_password_custom_hash(self, user):
        """测试自定义哈希函数验证"""
        custom_hash = lambda p: f"custom_{p}"

        user.set_password("test", hash_func=custom_hash)

        assert user.verify_password("test", hash_func=custom_hash) is True
        assert user.verify_password("wrong", hash_func=custom_hash) is False

    def test_verify_password_verify_func(self, user):
        """测试自定义验证函数"""
        # 模拟 passlib 的 verify 函数
        def mock_verify(password, hash_value):
            return password == "secret" and hash_value == "hashed_secret"

        user.password_hash = "hashed_secret"

        assert user.verify_password("secret", verify_func=mock_verify) is True
        assert user.verify_password("wrong", verify_func=mock_verify) is False

    def test_verify_password_without_hash_returns_false(self, user):
        """测试空密码哈希时默认验证失败"""
        user.password_hash = ""
        assert user.verify_password("any_password") is False

    def test_is_password_expired_never(self, user):
        """测试永不过期的密码"""
        user.password_expires_days = 0
        user.set_password("test123")

        assert user.is_password_expired is False

    def test_is_password_expired_not_expired(self, user):
        """测试未过期的密码"""
        user.password_expires_days = 90
        user.set_password("test123")

        assert user.is_password_expired is False

    def test_is_password_expired_expired(self, user):
        """测试已过期的密码"""
        user.password_expires_days = 30
        user.password_changed_at = datetime.now(timezone.utc) - timedelta(days=31)

        assert user.is_password_expired is True

    def test_is_password_expired_no_change_date(self, user):
        """测试没有密码更新时间时视为过期"""
        user.password_expires_days = 30
        user.password_changed_at = None

        assert user.is_password_expired is True

    def test_require_password_change(self, user):
        """测试要求修改密码"""
        assert user.must_change_password is False

        user.require_password_change()

        assert user.must_change_password is True
        assert user.update_calls[-1] is True


class TestLastLoginMixin:
    """最后登录信息 Mixin 测试"""

    @pytest.fixture
    def user(self):
        return MockLastLoginUser()

    def test_initial_state(self, user):
        """测试初始状态"""
        assert user.last_login_at is None
        assert user.last_login_ip is None

    def test_update_last_login(self, user):
        """测试更新最后登录信息"""
        user.update_last_login(ip_address="192.168.1.100")

        login_info = get_last_login_info(user)
        assert login_info['last_login_at'] is not None
        assert login_info['last_login_ip'] == "192.168.1.100"
        assert user.update_calls[-1] is True

    def test_update_last_login_no_ip(self, user):
        """测试更新最后登录时间（不更新 IP）"""
        user.last_login_ip = "old_ip"

        user.update_last_login()

        login_info = get_last_login_info(user)
        assert login_info['last_login_at'] is not None
        assert login_info['last_login_ip'] == "old_ip"  # 保持不变


class TestFullUserMixin:
    """完整用户 Mixin 测试"""

    @pytest.fixture
    def user(self):
        return MockFullUser()

    def test_has_all_features(self, user):
        """测试包含所有功能"""
        # LockableMixin 功能
        assert hasattr(user, 'lock')
        assert hasattr(user, 'unlock')
        assert hasattr(user, 'can_login')
        assert hasattr(user, 'record_failed_login')

        # PasswordMixin 功能
        assert hasattr(user, 'set_password')
        assert hasattr(user, 'verify_password')
        assert hasattr(user, 'is_password_expired')

        # LastLoginMixin 功能
        assert hasattr(user, 'update_last_login')

    def test_complete_login_flow(self, user):
        """测试完整登录流程"""
        # 1. 设置密码
        user.set_password("secure_password_123")

        # 2. 验证密码正确
        assert user.verify_password("secure_password_123") is True

        # 3. 检查是否可以登录
        assert user.can_login is True

        # 4. 登录成功，更新最后登录
        user.reset_failed_attempts()
        user.update_last_login(ip_address="10.0.0.1")

        attempts_info = get_failed_attempts_info(user)
        assert attempts_info['failed_login_attempts'] == 0
        
        login_info = get_last_login_info(user)
        assert login_info['last_login_ip'] == "10.0.0.1"

    def test_failed_login_flow(self, user):
        """测试登录失败流程"""
        user.set_password("correct_password")

        # 模拟多次登录失败
        for i in range(5):
            if not user.verify_password("wrong_password"):
                is_locked = user.record_failed_login(
                    max_attempts=5,
                    lock_duration_minutes=30
                )

        # 第 5 次失败后应该被锁定
        lock_status = get_lock_status(user)
        assert lock_status['is_locked'] is True
        assert user.can_login is False
