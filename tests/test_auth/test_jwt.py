"""JWT 模块测试

测试 JWT Token 的创建、验证和刷新功能
"""

import pytest
from types import SimpleNamespace
from datetime import timedelta

from yweb.auth import (
    JWTManager,
    TokenPayload,
    TokenData,
    create_jwt_token,
    verify_jwt_token,
)


class TestJWTManager:
    """JWTManager 类测试"""
    
    def test_create_jwt_manager(self, jwt_secret_key):
        """测试创建 JWT 管理器"""
        manager = JWTManager(
            secret_key=jwt_secret_key,
            algorithm="HS256",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7
        )
        
        assert manager.secret_key == jwt_secret_key
        assert manager.algorithm == "HS256"
        assert manager.access_token_expire_minutes == 30
        assert manager.refresh_token_expire_days == 7

    def test_init_with_invalid_access_expire_raises(self, jwt_secret_key):
        """测试无效 access 过期时间会抛出异常"""
        with pytest.raises(ValueError, match="access_token_expire_minutes"):
            JWTManager(secret_key=jwt_secret_key, access_token_expire_minutes=0)

    def test_init_with_invalid_refresh_expire_raises(self, jwt_secret_key):
        """测试无效 refresh 过期时间会抛出异常"""
        with pytest.raises(ValueError, match="refresh_token_expire_days"):
            JWTManager(secret_key=jwt_secret_key, refresh_token_expire_days=0)

    def test_init_with_invalid_sliding_days_raises(self, jwt_secret_key):
        """测试滑动过期阈值不合法会抛出异常"""
        with pytest.raises(ValueError, match="refresh_token_sliding_days"):
            JWTManager(
                secret_key=jwt_secret_key,
                refresh_token_expire_days=7,
                refresh_token_sliding_days=7,
            )
    
    def test_create_access_token_with_payload(self, jwt_manager, sample_token_payload):
        """测试使用 TokenPayload 创建访问令牌"""
        token = jwt_manager.create_access_token(sample_token_payload)
        
        assert token is not None
        assert isinstance(token, str)
        assert len(token) > 0
        # JWT 格式：header.payload.signature
        assert token.count('.') == 2
    
    def test_create_access_token_with_dict(self, jwt_manager):
        """测试使用字典创建访问令牌"""
        payload = {
            "sub": "testuser",
            "user_id": 1,
            "username": "testuser",
            "roles": ["admin"]
        }
        token = jwt_manager.create_access_token(payload)
        
        assert token is not None
        assert token.count('.') == 2
    
    def test_create_refresh_token(self, jwt_manager, sample_token_payload):
        """测试创建刷新令牌"""
        token = jwt_manager.create_refresh_token(sample_token_payload)
        
        assert token is not None
        assert isinstance(token, str)
        assert token.count('.') == 2
    
    def test_verify_access_token(self, jwt_manager, sample_token_payload):
        """测试验证访问令牌"""
        token = jwt_manager.create_access_token(sample_token_payload)
        token_data = jwt_manager.verify_token(token)
        
        assert token_data is not None
        assert isinstance(token_data, TokenData)
        assert token_data.sub == sample_token_payload.sub
        assert token_data.user_id == sample_token_payload.user_id
        assert token_data.username == sample_token_payload.username
        assert token_data.token_type == "access"
    
    def test_verify_refresh_token(self, jwt_manager, sample_token_payload):
        """测试验证刷新令牌"""
        token = jwt_manager.create_refresh_token(sample_token_payload)
        token_data = jwt_manager.verify_token(token)
        
        assert token_data is not None
        assert token_data.token_type == "refresh"
        assert token_data.user_id == sample_token_payload.user_id
    
    def test_verify_invalid_token(self, jwt_manager):
        """测试验证无效令牌"""
        invalid_token = "invalid.token.here"
        token_data = jwt_manager.verify_token(invalid_token)
        
        assert token_data is None
    
    def test_verify_token_with_wrong_secret(self, sample_token_payload):
        """测试使用错误密钥验证令牌"""
        manager1 = JWTManager(secret_key="secret1")
        manager2 = JWTManager(secret_key="secret2")
        
        token = manager1.create_access_token(sample_token_payload)
        token_data = manager2.verify_token(token)
        
        assert token_data is None
    
    def test_decode_token(self, jwt_manager, sample_token_payload):
        """测试解码令牌"""
        token = jwt_manager.create_access_token(sample_token_payload)
        decoded = jwt_manager.decode_token(token)
        
        assert decoded is not None
        assert isinstance(decoded, dict)
        assert decoded["sub"] == sample_token_payload.sub
        assert decoded["user_id"] == sample_token_payload.user_id
        assert "exp" in decoded
        assert "iat" in decoded
    
    def test_get_token_type(self, jwt_manager, sample_token_payload):
        """测试获取令牌类型"""
        access_token = jwt_manager.create_access_token(sample_token_payload)
        refresh_token = jwt_manager.create_refresh_token(sample_token_payload)
        
        assert jwt_manager.get_token_type(access_token) == "access"
        assert jwt_manager.get_token_type(refresh_token) == "refresh"
    
    def test_is_token_expired(self, jwt_secret_key, sample_token_payload):
        """测试令牌是否过期"""
        # 创建一个正常的管理器
        manager = JWTManager(
            secret_key=jwt_secret_key,
            access_token_expire_minutes=30
        )
        
        # 使用自定义过期时间创建令牌（负值表示已过期）
        token = manager.create_access_token(
            sample_token_payload,
            expires_delta=timedelta(seconds=-1)  # 已过期
        )
        
        assert manager.is_token_expired(token) == True
    
    def test_token_with_custom_expire(self, jwt_manager, sample_token_payload):
        """测试自定义过期时间的令牌"""
        token = jwt_manager.create_access_token(
            sample_token_payload,
            expires_delta=timedelta(hours=1)
        )
        
        token_data = jwt_manager.verify_token(token)
        assert token_data is not None
        assert jwt_manager.is_token_expired(token) == False
    
    def test_token_contains_roles(self, jwt_manager, sample_token_payload):
        """测试令牌包含角色信息"""
        token = jwt_manager.create_access_token(sample_token_payload)
        token_data = jwt_manager.verify_token(token)
        
        assert token_data.roles == ["user", "admin"]

    def test_get_remaining_seconds_for_invalid_token(self, jwt_manager):
        """测试无效 Token 的剩余秒数"""
        assert jwt_manager.get_remaining_seconds("invalid.token.here") is None

    def test_refresh_tokens_rejects_access_token(self, jwt_manager, sample_token_payload):
        """测试 refresh_tokens 不能接收 access token"""
        access_token = jwt_manager.create_access_token(sample_token_payload)
        result = jwt_manager.refresh_tokens(access_token)
        assert result is None

    def test_refresh_tokens_success_without_user_getter(self, jwt_manager, sample_token_payload):
        """测试使用 refresh token 成功换取新 access token"""
        refresh_token = jwt_manager.create_refresh_token(sample_token_payload)
        result = jwt_manager.refresh_tokens(refresh_token)
        assert result is not None
        assert result["token_type"] == "bearer"
        assert isinstance(result["access_token"], str)
        assert result["refresh_token_renewed"] is False

    def test_refresh_tokens_returns_none_when_user_not_found(self, jwt_manager, sample_token_payload):
        """测试用户获取失败时 refresh_tokens 返回 None"""
        refresh_token = jwt_manager.create_refresh_token(sample_token_payload)
        result = jwt_manager.refresh_tokens(refresh_token, user_getter=lambda _: None)
        assert result is None

    def test_refresh_tokens_returns_none_when_user_inactive(self, jwt_manager, sample_token_payload):
        """测试用户被禁用时 refresh_tokens 返回 None"""
        refresh_token = jwt_manager.create_refresh_token(sample_token_payload)
        inactive_user = SimpleNamespace(id=1, username="user1", is_active=False)
        result = jwt_manager.refresh_tokens(refresh_token, user_getter=lambda _: inactive_user)
        assert result is None

    def test_refresh_from_refresh_token_compat_api(self, jwt_manager, sample_token_payload):
        """测试兼容 API 可返回新的 access token"""
        refresh_token = jwt_manager.create_refresh_token(sample_token_payload)
        new_access_token = jwt_manager.refresh_from_refresh_token(refresh_token)
        assert isinstance(new_access_token, str)
        token_data = jwt_manager.verify_token(new_access_token)
        assert token_data is not None
        assert token_data.token_type == "access"


class TestTokenPayload:
    """TokenPayload 数据类测试"""
    
    def test_create_token_payload(self):
        """测试创建 TokenPayload"""
        payload = TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser",
            email="test@example.com",
            roles=["admin"]
        )
        
        assert payload.sub == "testuser"
        assert payload.user_id == 1
        assert payload.username == "testuser"
        assert payload.email == "test@example.com"
        assert payload.roles == ["admin"]
        assert payload.token_type == "access"
    
    def test_token_payload_default_values(self):
        """测试 TokenPayload 默认值"""
        payload = TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser"
        )
        
        assert payload.email is None
        assert payload.roles == []
        assert payload.token_type == "access"
        assert payload.extra == {}
    
    def test_token_payload_with_extra(self):
        """测试带额外数据的 TokenPayload"""
        payload = TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser",
            extra={"department": "IT", "level": 5}
        )
        
        assert payload.extra["department"] == "IT"
        assert payload.extra["level"] == 5


class TestConvenienceFunctions:
    """便捷函数测试"""
    
    def test_create_jwt_token_function(self, jwt_secret_key):
        """测试 create_jwt_token 便捷函数"""
        data = {
            "sub": "testuser",
            "user_id": 1
        }
        
        token = create_jwt_token(
            data=data,
            secret_key=jwt_secret_key,
            algorithm="HS256",
            expires_minutes=30
        )
        
        assert token is not None
        assert token.count('.') == 2
    
    def test_verify_jwt_token_function(self, jwt_secret_key):
        """测试 verify_jwt_token 便捷函数"""
        data = {
            "sub": "testuser",
            "user_id": 1
        }
        
        token = create_jwt_token(data, jwt_secret_key)
        decoded = verify_jwt_token(token, jwt_secret_key)
        
        assert decoded is not None
        assert decoded["sub"] == "testuser"
        assert decoded["user_id"] == 1
    
    def test_verify_jwt_token_invalid(self, jwt_secret_key):
        """测试验证无效令牌的便捷函数"""
        decoded = verify_jwt_token("invalid.token", jwt_secret_key)
        
        assert decoded is None


class TestJWTEdgeCases:
    """JWT 边界情况测试"""
    
    def test_empty_roles(self, jwt_manager):
        """测试空角色列表"""
        payload = TokenPayload(
            sub="testuser",
            user_id=1,
            username="testuser",
            roles=[]
        )
        
        token = jwt_manager.create_access_token(payload)
        token_data = jwt_manager.verify_token(token)
        
        assert token_data.roles == []
    
    def test_special_characters_in_username(self, jwt_manager):
        """测试用户名包含特殊字符"""
        payload = TokenPayload(
            sub="test@user.com",
            user_id=1,
            username="test@user.com",
            email="test@user.com"
        )
        
        token = jwt_manager.create_access_token(payload)
        token_data = jwt_manager.verify_token(token)
        
        assert token_data.username == "test@user.com"
    
    def test_unicode_in_payload(self, jwt_manager):
        """测试载荷中的 Unicode 字符"""
        payload = TokenPayload(
            sub="测试用户",
            user_id=1,
            username="测试用户",
            extra={"description": "这是中文描述"}
        )
        
        token = jwt_manager.create_access_token(payload)
        decoded = jwt_manager.decode_token(token)
        
        assert decoded["sub"] == "测试用户"
        assert decoded["username"] == "测试用户"

