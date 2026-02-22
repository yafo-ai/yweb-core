"""OAuth 2.0 模块测试

测试 OAuth 2.0 核心流程：客户端管理、授权码、Token 管理
"""

import pytest
from yweb.auth.oauth2 import (
    OAuth2Manager,
    OAuth2Client,
    OAuth2Token,
    OAuth2AuthProvider,
    ClientType,
    GrantType,
)
from yweb.auth.base import AuthType


class TestOAuth2Client:
    """OAuth2 客户端测试"""
    
    def test_create_client(self):
        """测试创建客户端"""
        client = OAuth2Client(
            client_id="test-client",
            client_secret="test-secret",
            client_name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
            allowed_scopes=["openid", "profile"],
        )
        
        assert client.client_id == "test-client"
        assert client.client_name == "Test App"
        assert client.is_active is True
    
    def test_validate_redirect_uri(self):
        """测试验证重定向 URI"""
        client = OAuth2Client(
            client_id="test",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        assert client.validate_redirect_uri("http://localhost:8000/callback") is True
        assert client.validate_redirect_uri("http://evil.com/callback") is False
    
    def test_validate_scope(self):
        """测试验证权限范围"""
        client = OAuth2Client(
            client_id="test",
            allowed_scopes=["openid", "profile", "email"],
        )
        
        is_valid, scopes = client.validate_scope("openid profile")
        assert is_valid is True
        assert set(scopes) == {"openid", "profile"}
        
        is_valid, invalid = client.validate_scope("openid admin")
        assert is_valid is False
        assert "admin" in invalid
    
    def test_validate_grant_type(self):
        """测试验证授权类型"""
        client = OAuth2Client(
            client_id="test",
            allowed_grant_types=["authorization_code", "refresh_token"],
        )
        
        assert client.validate_grant_type("authorization_code") is True
        assert client.validate_grant_type("client_credentials") is False
    
    def test_public_client(self):
        """测试公开客户端"""
        client = OAuth2Client(
            client_id="test",
            client_type=ClientType.PUBLIC,
            token_endpoint_auth_method="none",
        )
        
        assert client.is_public() is True
        assert client.requires_secret() is False

    def test_validate_scope_empty_uses_default(self):
        """测试空 scope 使用默认 scope"""
        client = OAuth2Client(
            client_id="test",
            allowed_scopes=["openid", "profile"],
            default_scopes=["profile"],
        )
        is_valid, scopes = client.validate_scope("")
        assert is_valid is True
        assert scopes == ["profile"]

    def test_validate_redirect_uri_with_wildcard(self):
        """测试通配符重定向 URI"""
        client = OAuth2Client(
            client_id="test",
            redirect_uris=["http://localhost:8000/*"],
        )
        assert client.validate_redirect_uri("http://localhost:8000/callback") is True
        assert client.validate_redirect_uri("http://evil.com/callback") is False


class TestOAuth2Manager:
    """OAuth2 管理器测试"""
    
    @pytest.fixture
    def oauth2_manager(self):
        """创建独立的 OAuth2 管理器"""
        manager = OAuth2Manager(
            secret_key="test-secret-key",
            access_token_expire_minutes=30,
            refresh_token_expire_days=7,
        )
        return manager
    
    def test_create_client(self, oauth2_manager):
        """测试创建客户端"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
            allowed_grant_types=["authorization_code", "refresh_token"],
        )
        
        assert client.client_id is not None
        assert client.client_secret is not None
        assert client.client_name == "Test App"
    
    def test_validate_client(self, oauth2_manager):
        """测试验证客户端"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        is_valid, result = oauth2_manager.validate_client(
            client_id=client.client_id,
            client_secret=client.client_secret,
        )
        
        assert is_valid is True
        assert result.client_id == client.client_id
    
    def test_validate_client_wrong_secret(self, oauth2_manager):
        """测试验证客户端（错误密钥）"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        is_valid, error = oauth2_manager.validate_client(
            client_id=client.client_id,
            client_secret="wrong-secret",
        )
        
        assert is_valid is False

    def test_validate_client_not_found(self, oauth2_manager):
        """测试验证不存在的客户端"""
        is_valid, error = oauth2_manager.validate_client("not-exist", "secret")
        assert is_valid is False
        assert error == "Client not found"
    
    def test_authorization_code_flow(self, oauth2_manager):
        """测试授权码流程"""
        # 创建客户端
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        # 创建授权码
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid profile",
        )
        
        assert code is not None
        
        # 交换 Token
        success, token = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        assert success is True
        assert token.access_token is not None
        assert token.refresh_token is not None

    def test_exchange_code_with_wrong_redirect_uri(self, oauth2_manager):
        """测试错误重定向地址无法换取 Token"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        success, error = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/wrong",
        )
        assert success is False
        assert error.get("error") == "invalid_grant"
    
    def test_client_credentials_flow(self, oauth2_manager):
        """测试客户端凭证流程"""
        client = oauth2_manager.create_client(
            name="Service App",
            redirect_uris=[],
            allowed_grant_types=["client_credentials"],
            allowed_scopes=["api.read", "api.write"],  # 设置允许的 scope
        )
        
        success, token = oauth2_manager.client_credentials_token(
            client_id=client.client_id,
            client_secret=client.client_secret,
            scope="api.read",
        )
        
        assert success is True
        assert token.access_token is not None
        # 客户端凭证模式通常不提供刷新令牌
        assert token.refresh_token is None
    
    def test_refresh_token_flow(self, oauth2_manager):
        """测试刷新令牌流程"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        # 先获取初始 Token
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        success, initial_token = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        # 刷新 Token
        success, new_token = oauth2_manager.refresh_token(
            refresh_token=initial_token.refresh_token,
            client_id=client.client_id,
            client_secret=client.client_secret,
        )
        
        assert success is True
        assert new_token.access_token != initial_token.access_token

    def test_refresh_token_invalid_token(self, oauth2_manager):
        """测试无效刷新令牌"""
        client = oauth2_manager.create_client(
            name="Test App",
            redirect_uris=["http://localhost:8000/callback"],
        )
        success, error = oauth2_manager.refresh_token(
            refresh_token="bad-refresh-token",
            client_id=client.client_id,
            client_secret=client.client_secret,
        )
        assert success is False
        assert error.get("error") == "invalid_grant"
    
    def test_validate_token(self, oauth2_manager):
        """测试验证 Token"""
        client = oauth2_manager.create_client(
            name="Test",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        _, token = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        is_valid, result = oauth2_manager.validate_token(token.access_token)
        
        assert is_valid is True
        assert result.user_id == 1
    
    def test_revoke_token(self, oauth2_manager):
        """测试撤销 Token"""
        client = oauth2_manager.create_client(
            name="Test",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        _, token = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        # 撤销
        oauth2_manager.revoke_token(token.access_token)
        
        # 验证应该失败
        is_valid, _ = oauth2_manager.validate_token(token.access_token)
        assert is_valid is False

    def test_introspect_token(self, oauth2_manager):
        """测试 Token 内省"""
        client = oauth2_manager.create_client(
            name="Test",
            redirect_uris=["http://localhost:8000/callback"],
        )
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        _, token = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        active = oauth2_manager.introspect_token(token.access_token)
        inactive = oauth2_manager.introspect_token("invalid-token")
        assert active["active"] is True
        assert active["client_id"] == client.client_id
        assert inactive["active"] is False
    
    def test_code_cannot_be_reused(self, oauth2_manager):
        """测试授权码不能重复使用"""
        client = oauth2_manager.create_client(
            name="Test",
            redirect_uris=["http://localhost:8000/callback"],
        )
        
        code = oauth2_manager.create_authorization_code(
            client_id=client.client_id,
            user_id=1,
            redirect_uri="http://localhost:8000/callback",
            scope="openid",
        )
        
        # 第一次使用
        success1, _ = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        # 第二次使用（应该失败）
        success2, error = oauth2_manager.exchange_code(
            code=code,
            client_id=client.client_id,
            client_secret=client.client_secret,
            redirect_uri="http://localhost:8000/callback",
        )
        
        assert success1 is True
        assert success2 is False


class TestOAuth2AuthProvider:
    """OAuth2 AuthProvider 测试"""
    
    @pytest.fixture
    def provider(self, mock_user):
        """创建独立的 Provider"""
        manager = OAuth2Manager(secret_key="test-secret")
        
        def user_getter(user_id):
            if user_id == 1:
                return mock_user(id=1, username="testuser")
            return None
        
        return OAuth2AuthProvider(
            oauth2_manager=manager,
            user_getter=user_getter,
        ), manager
    
    def test_auth_type(self, provider):
        """测试认证类型"""
        auth_provider, _ = provider
        assert auth_provider.auth_type == AuthType.OAUTH2
    
    def test_authenticate_client_credentials(self, provider):
        """测试客户端凭证认证"""
        auth_provider, manager = provider
        
        client = manager.create_client(
            name="Service",
            redirect_uris=[],
            allowed_grant_types=["client_credentials"],
        )
        
        result = auth_provider.authenticate({
            "grant_type": "client_credentials",
            "client_id": client.client_id,
            "client_secret": client.client_secret,
        })
        
        assert result.success is True
        assert result.extra.get("access_token") is not None

    def test_authenticate_unsupported_grant(self, provider):
        """测试不支持的授权类型"""
        auth_provider, _ = provider
        result = auth_provider.authenticate({"grant_type": "password"})
        assert result.success is False
        assert result.error_code == "UNSUPPORTED_GRANT"

    def test_authenticate_invalid_credentials_format(self, provider):
        """测试错误凭证格式"""
        auth_provider, _ = provider
        result = auth_provider.authenticate("not-a-dict")
        assert result.success is False
        assert result.error_code == "INVALID_CREDENTIALS"

    def test_validate_token_invalid(self, provider):
        """测试验证无效 access token"""
        auth_provider, _ = provider
        result = auth_provider.validate_token("invalid-token")
        assert result.success is False
        assert result.error_code == "INVALID_TOKEN"
