"""oauth2/provider 与 oidc 模块补充测试"""

import pytest

from yweb.auth.base import AuthType
from yweb.auth.oauth2.provider import OAuth2AuthProvider
from yweb.auth.oidc import OIDCAuthProvider, OIDCClaims, OIDCManager
from yweb.auth.oauth2.token import OAuth2Token, TokenType


class OAuth2ManagerStub:
    """OAuth2 manager 测试桩"""

    def client_credentials_token(self, client_id, client_secret, scope):
        if client_id == "ok" and client_secret == "sec":
            return True, OAuth2Token(access_token="acc1", scope=scope, client_id="ok")
        return False, {"error": "invalid_client", "error_description": "bad client"}

    def exchange_code(self, code, client_id, client_secret, redirect_uri, code_verifier):
        _ = (client_secret, redirect_uri, code_verifier)
        if code == "code-ok" and client_id == "ok":
            return True, OAuth2Token(access_token="acc2", refresh_token="ref2", user_id=1, client_id="ok")
        return False, {"error": "invalid_grant", "error_description": "bad code"}

    def refresh_token(self, refresh_token, client_id, client_secret, scope):
        _ = (client_secret, scope)
        if refresh_token == "ref-ok" and client_id == "ok":
            return True, OAuth2Token(access_token="acc3", refresh_token="ref3", user_id=1, client_id="ok")
        return False, {"error": "invalid_grant", "error_description": "bad refresh"}

    def device_code_token(self, device_code, client_id):
        if device_code == "pending":
            return False, {"error": "authorization_pending"}
        if device_code == "slow":
            return False, {"error": "slow_down"}
        if device_code == "expired":
            return False, {"error": "expired_token"}
        if device_code == "denied":
            return False, {"error": "access_denied"}
        if device_code == "ok" and client_id == "ok":
            return True, OAuth2Token(access_token="acc4", client_id="ok")
        return False, {"error": "server_error", "error_description": "unknown"}

    def validate_token(self, token):
        if token == "ok-token":
            return True, OAuth2Token(access_token=token, user_id=1, client_id="ok", scope="read write")
        return False, "invalid"

    def revoke_token(self, token):
        return token == "ok-token"


class TestOAuth2AuthProviderExtra:
    """OAuth2AuthProvider 补充分支"""

    @pytest.fixture
    def provider(self):
        user_getter = lambda user_id: type("UserObj", (), {"username": "u1", "email": "u1@example.com", "roles": ["admin"]})() if user_id == 1 else None
        return OAuth2AuthProvider(oauth2_manager=OAuth2ManagerStub(), user_getter=user_getter)

    def test_authenticate_invalid_format_and_unsupported_grant(self, provider):
        r1 = provider.authenticate("bad")
        assert r1.success is False
        assert r1.error_code == "INVALID_CREDENTIALS"

        r2 = provider.authenticate({"grant_type": "unknown"})
        assert r2.success is False
        assert r2.error_code == "UNSUPPORTED_GRANT"

    def test_grant_flows_success_and_failure(self, provider):
        cc_ok = provider.authenticate({"grant_type": "client_credentials", "client_id": "ok", "client_secret": "sec", "scope": "read"})
        assert cc_ok.success is True
        assert cc_ok.identity.auth_type == AuthType.OAUTH2

        cc_fail = provider.authenticate({"grant_type": "client_credentials", "client_id": "ok"})
        assert cc_fail.success is False
        assert cc_fail.error_code == "MISSING_CREDENTIALS"

        code_ok = provider.authenticate({"grant_type": "authorization_code", "code": "code-ok", "client_id": "ok", "redirect_uri": "http://cb"})
        assert code_ok.success is True
        assert code_ok.extra["refresh_token"] == "ref2"

        code_fail = provider.authenticate({"grant_type": "authorization_code", "code": "bad", "client_id": "ok", "redirect_uri": "http://cb"})
        assert code_fail.success is False
        assert code_fail.error_code == "invalid_grant"

        rf_ok = provider.authenticate({"grant_type": "refresh_token", "refresh_token": "ref-ok", "client_id": "ok"})
        assert rf_ok.success is True
        rf_fail = provider.authenticate({"grant_type": "refresh_token", "refresh_token": "bad", "client_id": "ok"})
        assert rf_fail.success is False

    def test_device_code_error_mappings(self, provider):
        p = provider.authenticate({"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "pending", "client_id": "ok"})
        assert p.error_code == "AUTHORIZATION_PENDING"
        s = provider.authenticate({"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "slow", "client_id": "ok"})
        assert s.error_code == "SLOW_DOWN"
        e = provider.authenticate({"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "expired", "client_id": "ok"})
        assert e.error_code == "EXPIRED_TOKEN"
        d = provider.authenticate({"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "denied", "client_id": "ok"})
        assert d.error_code == "ACCESS_DENIED"
        g = provider.authenticate(
            {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "unknown", "client_id": "ok"}
        )
        assert g.error_code == "server_error"

    def test_device_code_success_and_username_fallback_to_client_id(self):
        provider = OAuth2AuthProvider(oauth2_manager=OAuth2ManagerStub(), user_getter=lambda _uid: None)
        result = provider.authenticate(
            {"grant_type": "urn:ietf:params:oauth:grant-type:device_code", "device_code": "ok", "client_id": "ok"}
        )
        assert result.success is True
        assert result.identity.username == "ok"

    def test_validate_token_refresh_token_and_revoke(self, provider):
        ok = provider.validate_token("ok-token")
        assert ok.success is True
        assert ok.identity.permissions == ["read", "write"]

        bad = provider.validate_token("bad-token")
        assert bad.success is False
        assert bad.error_code == "INVALID_TOKEN"

        refresh = provider.refresh_token("any")
        assert refresh.success is False
        assert refresh.error_code == "NOT_SUPPORTED"

        assert provider.revoke_token("ok-token") is True
        assert provider.revoke_token("bad-token") is False


class TestOidcExtra:
    """OIDC 模块补充分支"""

    def test_oidc_claims_to_dict(self):
        claims = OIDCClaims(
            sub="1",
            iss="https://issuer",
            aud="client",
            exp=9999999999,
            iat=1,
            name="alice",
            email="alice@example.com",
            extra={"x_custom": "v"},
        )
        data = claims.to_dict()
        assert data["sub"] == "1"
        assert data["name"] == "alice"
        assert data["x_custom"] == "v"
        with_empty = claims.to_dict(include_empty=True)
        assert "phone_number" in with_empty

    def test_oidc_manager_create_verify_and_helpers(self):
        manager = OIDCManager(
            issuer="https://issuer.example.com",
            secret_key="test-secret",
            algorithm="HS256",
            id_token_expire_minutes=5,
            user_claims_getter=lambda _uid: {
                "name": "Alice",
                "email": "alice@example.com",
                "email_verified": True,
                "preferred_username": "alice",
            },
        )
        manager.set_user_claims_getter(lambda _uid: {"name": "Alice", "email": "alice@example.com"})
        manager.set_keys(private_key="priv", public_key="pub", jwks={"keys": [{"kid": "1"}]})

        token = manager.create_id_token(
            user_id=1,
            client_id="client-1",
            scope="openid profile email",
            nonce="n1",
            extra_claims={"custom": "ok"},
        )
        verified = manager.verify_id_token(token, client_id="client-1", nonce="n1")
        assert verified is not None
        assert verified["sub"] == "1"
        assert verified["custom"] == "ok"
        assert manager._compute_hash("access-1")

        assert manager.verify_id_token(token, client_id="client-1", nonce="wrong") is None
        assert manager._get_signing_key() == "test-secret"
        assert manager._get_verification_key() == "test-secret"
        assert manager.get_jwks() == {"keys": [{"kid": "1"}]}
        discovery = manager.get_discovery_document("https://sso.example.com/")
        assert discovery["issuer"] == "https://issuer.example.com"
        assert discovery["token_endpoint"].endswith("/oauth2/token")
        userinfo = manager.get_userinfo(1, ["openid", "profile"])
        assert userinfo["sub"] == "1"

    def test_oidc_manager_default_jwks_without_public_key(self):
        manager = OIDCManager(
            issuer="https://issuer.example.com",
            secret_key="test-secret",
            algorithm="HS256",
        )
        assert manager.get_jwks() == {"keys": []}

    def test_oidc_auth_provider(self):
        manager = OIDCManager(
            issuer="https://issuer.example.com",
            secret_key="test-secret",
            algorithm="HS256",
        )
        id_token = manager.create_id_token(user_id=1, client_id="client-1", scope="openid", nonce="n2")

        provider = OIDCAuthProvider(
            oidc_manager=manager,
            user_getter=lambda _uid: type("UserObj", (), {"roles": ["user"]})(),
        )

        bad = provider.authenticate(123)
        assert bad.success is False
        assert bad.error_code == "INVALID_CREDENTIALS"

        missing = provider.authenticate({})
        assert missing.success is False
        assert missing.error_code == "ID_TOKEN_REQUIRED"

        ok = provider.authenticate({"id_token": id_token, "client_id": "client-1", "nonce": "n2"})
        assert ok.success is True
        assert ok.identity.auth_type == AuthType.OIDC
        assert ok.identity.roles == ["user"]

        invalid = provider.authenticate({"id_token": id_token, "client_id": "client-1", "nonce": "bad"})
        assert invalid.success is False
        assert invalid.error_code == "INVALID_ID_TOKEN"

        # validate_token 仅接收 token 字符串，无法传 client_id，当前实现会失败
        valid2 = provider.validate_token(id_token)
        assert valid2.success is False

    def test_oauth2_token_response_coverage(self):
        token = OAuth2Token(
            access_token="acc",
            token_type=TokenType.BEARER,
            expires_in=120,
            refresh_token="ref",
            scope="read write",
            id_token="id-token",
            client_id="c1",
            user_id=1,
        )
        resp = token.to_response()
        assert resp["access_token"] == "acc"
        assert resp["refresh_token"] == "ref"
        assert resp["id_token"] == "id-token"
