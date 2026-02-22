"""Token 撤销/黑名单测试"""

import pytest
from datetime import datetime, timezone, timedelta

from yweb.auth import JWTManager, TokenPayload
from yweb.auth.token_store import (
    InMemoryTokenStore,
    TokenBlacklist,
    RevokedTokenInfo,
    configure_token_blacklist,
    get_token_blacklist,
)


class TestRevokedTokenInfo:
    """撤销 Token 信息测试"""

    def test_create_revoked_info(self):
        """测试创建撤销信息"""
        info = RevokedTokenInfo(
            token_hash="abc123",
            user_id=1,
            reason="user_logout",
        )

        assert info.token_hash == "abc123"
        assert info.user_id == 1
        assert info.reason == "user_logout"
        assert info.revoked_at is not None

    def test_to_dict(self):
        """测试转换为字典"""
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=1)

        info = RevokedTokenInfo(
            token_hash="abc123",
            user_id=1,
            revoked_at=now,
            expires_at=expires,
            reason="test",
        )

        data = info.to_dict()

        assert data["token_hash"] == "abc123"
        assert data["user_id"] == 1
        assert data["reason"] == "test"
        assert "revoked_at" in data
        assert "expires_at" in data

    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            "token_hash": "xyz789",
            "user_id": 2,
            "revoked_at": "2026-01-01T12:00:00+00:00",
            "expires_at": "2026-01-01T13:00:00+00:00",
            "reason": "password_changed",
        }

        info = RevokedTokenInfo.from_dict(data)

        assert info.token_hash == "xyz789"
        assert info.user_id == 2
        assert info.reason == "password_changed"


class TestInMemoryTokenStore:
    """内存 Token 存储测试"""

    @pytest.fixture
    def store(self):
        """创建存储实例"""
        return InMemoryTokenStore()

    def test_add_and_exists(self, store):
        """测试添加和检查存在"""
        info = RevokedTokenInfo(
            token_hash="test_hash_1",
            user_id=1,
        )

        result = store.add(info)
        assert result is True
        assert store.exists("test_hash_1") is True
        assert store.exists("nonexistent") is False

    def test_get(self, store):
        """测试获取撤销信息"""
        info = RevokedTokenInfo(
            token_hash="test_hash_2",
            user_id=2,
            reason="test_reason",
        )
        store.add(info)

        retrieved = store.get("test_hash_2")

        assert retrieved is not None
        assert retrieved.token_hash == "test_hash_2"
        assert retrieved.user_id == 2
        assert retrieved.reason == "test_reason"

    def test_get_nonexistent(self, store):
        """测试获取不存在的记录"""
        result = store.get("nonexistent_hash")
        assert result is None

    def test_remove(self, store):
        """测试移除记录"""
        info = RevokedTokenInfo(token_hash="to_remove", user_id=1)
        store.add(info)

        assert store.exists("to_remove") is True

        result = store.remove("to_remove")

        assert result is True
        assert store.exists("to_remove") is False

    def test_remove_nonexistent(self, store):
        """测试移除不存在记录返回 False"""
        assert store.remove("not_exists") is False

    def test_get_by_user(self, store):
        """测试获取用户所有撤销记录"""
        # 添加多个 Token
        store.add(RevokedTokenInfo(token_hash="hash1", user_id=1))
        store.add(RevokedTokenInfo(token_hash="hash2", user_id=1))
        store.add(RevokedTokenInfo(token_hash="hash3", user_id=2))

        user1_tokens = store.get_by_user(1)
        user2_tokens = store.get_by_user(2)

        assert len(user1_tokens) == 2
        assert len(user2_tokens) == 1

    def test_user_revocation(self, store):
        """测试用户级别撤销"""
        now = datetime.now(timezone.utc)

        result = store.add_user_revocation(1, now)
        assert result is True

        revoke_time = store.get_user_revocation_time(1)
        assert revoke_time == now

        # 未设置的用户返回 None
        assert store.get_user_revocation_time(999) is None

    def test_cleanup_expired(self, store):
        """测试清理过期记录"""
        past = datetime.now(timezone.utc) - timedelta(hours=1)
        future = datetime.now(timezone.utc) + timedelta(hours=1)

        # 添加过期和未过期的记录
        store.add(RevokedTokenInfo(token_hash="expired", expires_at=past))
        store.add(RevokedTokenInfo(token_hash="valid", expires_at=future))

        cleaned = store.cleanup_expired()

        assert cleaned == 1
        assert store.exists("expired") is False
        assert store.exists("valid") is True


class TestTokenBlacklist:
    """Token 黑名单测试"""

    @pytest.fixture
    def jwt_manager(self):
        """创建 JWT 管理器"""
        return JWTManager(
            secret_key="blacklist-test-secret",
            access_token_expire_minutes=30,
        )

    @pytest.fixture
    def sample_payload(self):
        """示例载荷"""
        return TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser",
        )

    @pytest.fixture
    def blacklist(self, jwt_manager):
        """创建黑名单实例"""
        store = InMemoryTokenStore()
        return TokenBlacklist(store, jwt_manager)

    def test_revoke_token(self, blacklist, jwt_manager, sample_payload):
        """测试撤销单个 Token"""
        token = jwt_manager.create_access_token(sample_payload)

        result = blacklist.revoke_token(token, reason="user_logout")

        assert result is True
        assert blacklist.is_revoked(token) is True

    def test_is_revoked_valid_token(self, blacklist, jwt_manager, sample_payload):
        """测试有效 Token 未被撤销"""
        token = jwt_manager.create_access_token(sample_payload)

        assert blacklist.is_revoked(token) is False

    def test_revoke_all_user_tokens(self, blacklist, jwt_manager, sample_payload):
        """测试撤销用户所有 Token"""
        # 创建多个 Token
        token1 = jwt_manager.create_access_token(sample_payload)
        token2 = jwt_manager.create_access_token(sample_payload)

        # 撤销用户所有 Token
        result = blacklist.revoke_all_user_tokens(user_id=1)
        assert result is True

        # 所有 Token 都应该被撤销
        assert blacklist.is_revoked(token1) is True
        assert blacklist.is_revoked(token2) is True

    def test_revoke_all_user_tokens_new_token_valid(
        self, blacklist, jwt_manager, sample_payload
    ):
        """测试撤销后新创建的 Token 仍然有效"""
        # 先创建旧 Token
        old_token = jwt_manager.create_access_token(sample_payload)

        # 撤销所有 Token
        blacklist.revoke_all_user_tokens(user_id=1)

        # 稍后创建新 Token（需要等待超过 1 秒确保 iat 时间戳不同）
        import time
        time.sleep(1.1)  # 确保时间戳不同（秒级精度）
        new_token = jwt_manager.create_access_token(sample_payload)

        # 旧 Token 被撤销，新 Token 有效
        assert blacklist.is_revoked(old_token) is True
        assert blacklist.is_revoked(new_token) is False

    def test_get_revocation_info(self, blacklist, jwt_manager, sample_payload):
        """测试获取撤销信息"""
        token = jwt_manager.create_access_token(sample_payload)

        # 未撤销时返回 None
        assert blacklist.get_revocation_info(token) is None

        # 撤销后返回信息
        blacklist.revoke_token(token, reason="test_reason")
        info = blacklist.get_revocation_info(token)

        assert info is not None
        assert info.reason == "test_reason"

    def test_cleanup(self, blacklist):
        """测试清理过期记录"""
        cleaned = blacklist.cleanup()
        # InMemoryTokenStore 会返回清理的数量
        assert isinstance(cleaned, int)

    def test_revoke_without_jwt_manager(self):
        """测试无 JWTManager 时仍可按哈希撤销"""
        store = InMemoryTokenStore()
        blacklist = TokenBlacklist(store=store, jwt_manager=None)
        token = "raw-token-value"
        assert blacklist.revoke_token(token, reason="manual_revoke") is True
        assert blacklist.is_revoked(token) is True

    def test_is_revoked_invalid_token_not_in_store(self, blacklist):
        """测试无效 token 且不在黑名单时返回 False"""
        assert blacklist.is_revoked("invalid.token.value") is False


class TestGlobalBlacklist:
    """全局黑名单配置测试"""

    def test_configure_and_get(self):
        """测试配置和获取全局黑名单"""
        jwt_manager = JWTManager(secret_key="global-test")

        blacklist = configure_token_blacklist(jwt_manager=jwt_manager)

        assert blacklist is not None
        assert get_token_blacklist() is blacklist

    def test_configure_with_custom_store(self):
        """测试使用自定义存储"""
        custom_store = InMemoryTokenStore()
        jwt_manager = JWTManager(secret_key="custom-store-test")

        blacklist = configure_token_blacklist(
            store=custom_store,
            jwt_manager=jwt_manager,
        )

        assert blacklist is not None

    def test_default_store(self):
        """测试默认存储"""
        blacklist = configure_token_blacklist()

        # 应该使用内存存储
        assert blacklist is not None

    def test_reconfigure_overwrites_global_instance(self):
        """测试重新配置会覆盖全局实例"""
        first = configure_token_blacklist()
        second = configure_token_blacklist()
        assert first is not second
        assert get_token_blacklist() is second
