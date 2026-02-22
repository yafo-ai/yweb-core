"""Token 刷新功能测试

测试 JWTManager 的 Refresh Token 滑动过期功能。
"""

import pytest
import time
import warnings
from datetime import timedelta
from unittest.mock import MagicMock

from yweb.auth import JWTManager, TokenPayload


class TestJWTManagerRefreshTokenSliding:
    """测试 JWTManager 的 Refresh Token 滑动过期功能"""

    @pytest.fixture
    def jwt_manager(self):
        """创建 JWT 管理器"""
        return JWTManager(
            secret_key="test-secret-key-for-sliding",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
            refresh_token_sliding_days=2,  # Refresh Token 剩余 2 天时续期
        )

    @pytest.fixture
    def jwt_manager_no_sliding(self):
        """创建禁用滑动过期的 JWT 管理器"""
        return JWTManager(
            secret_key="test-secret-key-no-sliding",
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
            refresh_token_sliding_days=0,  # 禁用滑动过期
        )

    @pytest.fixture
    def sample_payload(self):
        """示例 Token 载荷"""
        return TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser",
            email="test@example.com",
            roles=["user"],
        )

    def test_get_remaining_seconds(self, jwt_manager, sample_payload):
        """测试获取 Token 剩余秒数"""
        token = jwt_manager.create_access_token(sample_payload)

        remaining = jwt_manager.get_remaining_seconds(token)

        # 应该接近 30 分钟（1800 秒），允许几秒误差
        assert remaining is not None
        assert 1790 < remaining <= 1800

    def test_get_remaining_days(self, jwt_manager, sample_payload):
        """测试获取 Token 剩余天数"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        remaining_days = jwt_manager.get_remaining_days(refresh_token)

        # 应该接近 7 天，允许一点误差
        assert remaining_days is not None
        assert 6.99 < remaining_days <= 7.0

    def test_get_remaining_days_invalid_token(self, jwt_manager):
        """测试无效 Token 返回 None"""
        remaining = jwt_manager.get_remaining_days("invalid.token.here")
        assert remaining is None

    def test_should_renew_new_refresh_token(self, jwt_manager, sample_payload):
        """测试新创建的 Refresh Token 不需要续期"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        # 刚创建的 Refresh Token（7天有效期）不应该需要续期（阈值2天）
        assert jwt_manager.should_renew_refresh_token(refresh_token) is False

    def test_should_renew_refresh_token_disabled(self, jwt_manager_no_sliding, sample_payload):
        """测试禁用滑动过期时不续期"""
        refresh_token = jwt_manager_no_sliding.create_refresh_token(sample_payload)

        # 禁用滑动过期时，应该始终返回 False
        assert jwt_manager_no_sliding.should_renew_refresh_token(refresh_token) is False

    def test_should_renew_invalid_token(self, jwt_manager):
        """测试无效 Token 不续期"""
        assert jwt_manager.should_renew_refresh_token("invalid.token") is False

    def test_refresh_tokens_returns_dict(self, jwt_manager, sample_payload):
        """测试 refresh_tokens 返回正确格式的字典"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        result = jwt_manager.refresh_tokens(refresh_token)

        assert result is not None
        assert "access_token" in result
        assert "refresh_token" in result
        assert "token_type" in result
        assert "refresh_token_renewed" in result
        assert result["token_type"] == "bearer"

    def test_refresh_tokens_no_renew_needed(self, jwt_manager, sample_payload):
        """测试 Refresh Token 不需要续期时，返回的 refresh_token 为 None"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        result = jwt_manager.refresh_tokens(refresh_token)

        assert result is not None
        assert result["access_token"] is not None
        assert result["refresh_token"] is None  # 不需要续期
        assert result["refresh_token_renewed"] is False

    def test_refresh_tokens_with_renew_needed(self, jwt_manager, sample_payload):
        """测试接近过期时会续期 Refresh Token"""
        # 创建一个 1 天后过期的 refresh token（阈值是 2 天）
        refresh_token = jwt_manager.create_refresh_token(
            sample_payload,
            expires_delta=timedelta(days=1),
        )
        assert jwt_manager.should_renew_refresh_token(refresh_token) is True

        result = jwt_manager.refresh_tokens(refresh_token)
        assert result is not None
        assert result["refresh_token_renewed"] is True
        assert isinstance(result["refresh_token"], str)

    def test_refresh_tokens_access_token_valid(self, jwt_manager, sample_payload):
        """测试返回的 Access Token 是有效的"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        result = jwt_manager.refresh_tokens(refresh_token)

        # 验证新 Access Token
        access_data = jwt_manager.verify_token(result["access_token"])
        assert access_data is not None
        assert access_data.token_type == "access"
        assert access_data.user_id == sample_payload.user_id
        assert access_data.username == sample_payload.username

    def test_refresh_tokens_with_user_getter(self, jwt_manager, sample_payload):
        """测试带 user_getter 的刷新"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        # 模拟用户获取函数
        mock_user = MagicMock()
        mock_user.username = "updated_user"
        mock_user.email = "updated@example.com"
        mock_user.is_active = True
        mock_user.roles = [MagicMock(code="admin")]

        def user_getter(user_id):
            return mock_user

        result = jwt_manager.refresh_tokens(refresh_token, user_getter=user_getter)

        assert result is not None
        # 验证使用了用户最新信息
        access_data = jwt_manager.verify_token(result["access_token"])
        assert access_data.username == "updated_user"
        assert "admin" in access_data.roles

    def test_refresh_tokens_user_inactive(self, jwt_manager, sample_payload):
        """测试用户已禁用时刷新失败"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        # 模拟已禁用的用户
        mock_user = MagicMock()
        mock_user.is_active = False

        def user_getter(user_id):
            return mock_user

        result = jwt_manager.refresh_tokens(refresh_token, user_getter=user_getter)

        assert result is None

    def test_refresh_tokens_user_not_found(self, jwt_manager, sample_payload):
        """测试用户不存在时刷新失败"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        def user_getter(user_id):
            return None

        result = jwt_manager.refresh_tokens(refresh_token, user_getter=user_getter)

        assert result is None

    def test_refresh_tokens_invalid_token(self, jwt_manager):
        """测试无效 Token 刷新失败"""
        result = jwt_manager.refresh_tokens("invalid.token")
        assert result is None

    def test_refresh_tokens_missing_user_id(self, jwt_manager):
        """测试 refresh token 缺少 user_id 时刷新失败"""
        refresh_token = jwt_manager.create_refresh_token(
            {"sub": "test-user", "user_id": None}
        )
        result = jwt_manager.refresh_tokens(refresh_token)
        assert result is None

    def test_refresh_tokens_access_token_fails(self, jwt_manager, sample_payload):
        """测试使用 Access Token 刷新失败"""
        access_token = jwt_manager.create_access_token(sample_payload)

        # 使用 access token 应该失败
        result = jwt_manager.refresh_tokens(access_token)
        assert result is None

    def test_refresh_from_refresh_token_compat(self, jwt_manager, sample_payload):
        """测试兼容 API refresh_from_refresh_token"""
        refresh_token = jwt_manager.create_refresh_token(sample_payload)

        # 使用旧 API
        new_access_token = jwt_manager.refresh_from_refresh_token(refresh_token)

        assert new_access_token is not None

        # 验证新 Token 是 access 类型
        new_data = jwt_manager.verify_token(new_access_token)
        assert new_data is not None
        assert new_data.token_type == "access"
        assert new_data.user_id == sample_payload.user_id


class TestJWTManagerValidation:
    """测试 JWTManager 参数验证"""

    def test_sliding_days_less_than_expire_days(self):
        """测试 sliding_days 必须小于 expire_days"""
        with pytest.raises(ValueError, match="必须小于"):
            JWTManager(
                secret_key="test",
                refresh_token_expire_days=7,
                refresh_token_sliding_days=7,  # 等于有效期，应该报错
            )

    def test_sliding_days_greater_than_expire_days(self):
        """测试 sliding_days 不能大于 expire_days"""
        with pytest.raises(ValueError, match="必须小于"):
            JWTManager(
                secret_key="test",
                refresh_token_expire_days=7,
                refresh_token_sliding_days=10,  # 大于有效期，应该报错
            )

    def test_sliding_days_negative(self):
        """测试 sliding_days 不能为负数"""
        with pytest.raises(ValueError, match="大于等于 0"):
            JWTManager(
                secret_key="test",
                refresh_token_sliding_days=-1,
            )

    def test_sliding_days_zero_allowed(self):
        """测试 sliding_days 可以为 0（禁用滑动过期）"""
        manager = JWTManager(
            secret_key="test",
            refresh_token_sliding_days=0,
        )
        assert manager.refresh_token_sliding_days == 0

