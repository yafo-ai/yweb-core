"""统一认证接口测试

测试 AuthProvider、AuthManager、UserIdentity 等基础类
"""

import pytest
from yweb.auth.base import (
    AuthProvider,
    AuthManager,
    AuthType,
    UserIdentity,
    AuthResult,
)


class TestUserIdentity:
    """UserIdentity 测试"""
    
    def test_create_user_identity(self):
        """测试创建用户身份"""
        identity = UserIdentity(
            user_id=1,
            username="testuser",
            email="test@example.com",
            roles=["admin", "user"],
            permissions=["read", "write"],
        )
        
        assert identity.user_id == 1
        assert identity.username == "testuser"
        assert identity.email == "test@example.com"
    
    def test_has_role(self):
        """测试角色检查"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            roles=["admin", "user"],
        )
        
        assert identity.has_role("admin") is True
        assert identity.has_role("guest") is False
    
    def test_has_any_role(self):
        """测试任一角色检查"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            roles=["admin"],
        )
        
        assert identity.has_any_role(["admin", "superuser"]) is True
        assert identity.has_any_role(["guest", "visitor"]) is False
    
    def test_has_all_roles(self):
        """测试所有角色检查"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            roles=["admin", "user"],
        )
        
        assert identity.has_all_roles(["admin", "user"]) is True
        assert identity.has_all_roles(["admin", "superuser"]) is False
    
    def test_has_permission(self):
        """测试权限检查"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            permissions=["read", "write"],
        )
        
        assert identity.has_permission("read") is True
        assert identity.has_permission("delete") is False
    
    def test_to_dict(self):
        """测试转换为字典"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            auth_type=AuthType.JWT,
        )
        
        data = identity.to_dict()
        
        assert data["user_id"] == 1
        assert data["username"] == "test"
        assert data["auth_type"] == "jwt"
        assert "auth_time" in data

    def test_has_any_permission(self):
        """测试任一权限检查"""
        identity = UserIdentity(
            user_id=1,
            username="test",
            permissions=["read", "write"],
        )
        assert identity.has_any_permission(["write", "delete"]) is True
        assert identity.has_any_permission(["delete", "admin"]) is False


class TestAuthResult:
    """AuthResult 测试"""
    
    def test_ok_result(self):
        """测试成功结果"""
        identity = UserIdentity(user_id=1, username="test")
        result = AuthResult.ok(identity, extra_key="extra_value")
        
        assert result.success is True
        assert result.identity == identity
        assert result.extra.get("extra_key") == "extra_value"
    
    def test_fail_result(self):
        """测试失败结果"""
        result = AuthResult.fail("Invalid credentials", "AUTH_FAILED")
        
        assert result.success is False
        assert result.error == "Invalid credentials"
        assert result.error_code == "AUTH_FAILED"

    def test_fail_result_default_error_code(self):
        """测试失败结果默认错误码"""
        result = AuthResult.fail("Any error")
        assert result.success is False
        assert result.error_code == "AUTH_FAILED"
    
    def test_require_mfa_result(self):
        """测试需要 MFA 的结果"""
        result = AuthResult.require_mfa("temp-token-123")
        
        assert result.success is False
        assert result.requires_mfa is True
        assert result.mfa_token == "temp-token-123"


class MockAuthProvider(AuthProvider):
    """模拟认证提供者"""
    
    def __init__(self, auth_type: AuthType = AuthType.JWT):
        self._auth_type = auth_type
        self.users = {
            "valid_user": {"id": 1, "username": "valid_user"},
        }
    
    @property
    def auth_type(self) -> AuthType:
        return self._auth_type
    
    def authenticate(self, credentials):
        if isinstance(credentials, dict):
            username = credentials.get("username")
            password = credentials.get("password")
        else:
            return AuthResult.fail("Invalid credentials format")
        
        if username in self.users and password == "valid_password":
            user = self.users[username]
            identity = UserIdentity(
                user_id=user["id"],
                username=user["username"],
                auth_type=self._auth_type,
            )
            return AuthResult.ok(identity)
        
        return AuthResult.fail("Invalid credentials")
    
    def validate_token(self, token: str):
        if token == "valid_token":
            identity = UserIdentity(
                user_id=1,
                username="valid_user",
                auth_type=self._auth_type,
            )
            return AuthResult.ok(identity)
        return AuthResult.fail("Invalid token")


class TestAuthManager:
    """AuthManager 测试"""
    
    @pytest.fixture
    def auth_manager(self):
        """创建独立的认证管理器"""
        manager = AuthManager()
        
        jwt_provider = MockAuthProvider(AuthType.JWT)
        api_key_provider = MockAuthProvider(AuthType.API_KEY)
        
        manager.register_provider("jwt", jwt_provider, is_default=True)
        manager.register_provider("api_key", api_key_provider)
        
        return manager
    
    def test_register_provider(self, auth_manager):
        """测试注册提供者"""
        providers = auth_manager.list_providers()
        
        assert "jwt" in providers
        assert "api_key" in providers
    
    def test_get_provider(self, auth_manager):
        """测试获取提供者"""
        provider = auth_manager.get_provider("jwt")
        
        assert provider is not None
        assert provider.auth_type == AuthType.JWT
    
    def test_get_default_provider(self, auth_manager):
        """测试获取默认提供者"""
        provider = auth_manager.get_default_provider()
        
        assert provider is not None
        assert provider.auth_type == AuthType.JWT
    
    def test_authenticate(self, auth_manager):
        """测试使用指定提供者认证"""
        result = auth_manager.authenticate("jwt", {
            "username": "valid_user",
            "password": "valid_password",
        })
        
        assert result.success is True
        assert result.identity.username == "valid_user"
    
    def test_authenticate_default(self, auth_manager):
        """测试使用默认提供者认证"""
        result = auth_manager.authenticate_default({
            "username": "valid_user",
            "password": "valid_password",
        })
        
        assert result.success is True
    
    def test_authenticate_invalid(self, auth_manager):
        """测试认证失败"""
        result = auth_manager.authenticate("jwt", {
            "username": "valid_user",
            "password": "wrong_password",
        })
        
        assert result.success is False
    
    def test_authenticate_unknown_provider(self, auth_manager):
        """测试使用不存在的提供者"""
        result = auth_manager.authenticate("unknown", {})
        
        assert result.success is False
        assert result.error_code == "PROVIDER_NOT_FOUND"
    
    def test_validate_token_specific_provider(self, auth_manager):
        """测试使用指定提供者验证 Token"""
        result = auth_manager.validate_token("valid_token", provider_name="jwt")
        
        assert result.success is True

    def test_validate_token_unknown_provider(self, auth_manager):
        """测试验证 Token 时提供者不存在"""
        result = auth_manager.validate_token("valid_token", provider_name="unknown")
        assert result.success is False
        assert result.error_code == "PROVIDER_NOT_FOUND"
    
    def test_validate_token_try_all(self, auth_manager):
        """测试尝试所有提供者验证 Token"""
        result = auth_manager.validate_token("valid_token")
        
        assert result.success is True

    def test_validate_token_invalid_for_all_providers(self, auth_manager):
        """测试所有提供者都无法验证 Token"""
        result = auth_manager.validate_token("bad_token")
        assert result.success is False
        assert result.error_code == "INVALID_TOKEN"
    
    def test_unregister_provider(self, auth_manager):
        """测试注销提供者"""
        auth_manager.unregister_provider("api_key")
        
        assert "api_key" not in auth_manager.list_providers()
        assert auth_manager.get_provider("api_key") is None

    def test_unregister_default_provider_fallback(self, auth_manager):
        """测试注销默认提供者后默认值回退"""
        auth_manager.unregister_provider("jwt")
        default_provider = auth_manager.get_default_provider()
        assert default_provider is not None
        assert default_provider.auth_type == AuthType.API_KEY

    def test_authenticate_default_without_provider(self):
        """测试无默认提供者时的默认认证行为"""
        manager = AuthManager()
        result = manager.authenticate_default({"username": "x", "password": "y"})
        assert result.success is False
        assert result.error_code == "NO_DEFAULT_PROVIDER"
