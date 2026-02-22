"""oauth2_api 路由补充测试（二）"""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.auth.api import create_oauth2_router


class SampleOAuth2Client:
    """OAuth2 客户端桩"""

    def __init__(self, require_pkce: bool = False):
        self.require_pkce = require_pkce
        self.client_name = "sample-client"
        self.default_scopes = ["openid"]

    def validate_redirect_uri(self, redirect_uri: str) -> bool:
        return redirect_uri == "https://client.example.com/callback"


class SampleTokenResult:
    """Token 成功结果桩"""

    def __init__(self, access_token: str = "token-1"):
        self.access_token = access_token

    def to_response(self):
        return {
            "access_token": self.access_token,
            "token_type": "bearer",
            "expires_in": 3600,
        }


class SampleOAuth2Manager:
    """OAuth2 管理器桩"""

    def get_client(self, client_id: str):
        if client_id == "missing":
            return None
        if client_id == "pkce-client":
            return SampleOAuth2Client(require_pkce=True)
        return SampleOAuth2Client()

    def create_authorization_code(self, **_kwargs):
        return "auth-code-xyz"

    def exchange_code(self, code, client_id, client_secret, redirect_uri, code_verifier):
        _ = (client_secret, redirect_uri, code_verifier)
        if code == "ok-code" and client_id == "client-a":
            return True, SampleTokenResult("access-from-code")
        return False, {"error": "invalid_grant"}

    def client_credentials_token(self, client_id, client_secret, scope):
        _ = scope
        if client_id == "client-a" and client_secret == "secret-a":
            return True, SampleTokenResult("access-from-client")
        return False, {"error": "invalid_client", "error_description": "client auth failed"}

    def refresh_token(self, refresh_token, client_id, client_secret, scope):
        _ = (client_id, client_secret, scope)
        if refresh_token == "ok-refresh":
            return True, SampleTokenResult("access-from-refresh")
        return False, {"error": "invalid_grant"}

    def device_code_token(self, device_code, client_id):
        _ = client_id
        if device_code == "ok-device-code":
            return True, SampleTokenResult("access-from-device")
        return False, {"error": "authorization_pending"}

    def validate_client(self, client_id, client_secret):
        if client_id == "bad-client":
            return False, "invalid client"
        if not client_secret:
            return False, "missing secret"
        return True, "ok"

    def revoke_token(self, token, token_type_hint):
        _ = (token, token_type_hint)
        return True

    def introspect_token(self, token):
        return {"active": token == "active-token", "sub": "100"}

    def create_device_code(self, client_id, scope, verification_uri):
        _ = (client_id, scope, verification_uri)
        return True, SimpleNamespace(
            device_code="dev-code-1",
            user_code="ABCD-1234",
            verification_uri="/oauth2/device",
            verification_uri_complete="/oauth2/device?user_code=ABCD-1234",
            expires_in=1200,
            interval=5,
        )

    def authorize_device(self, user_code, user_id, approve):
        if not approve:
            return False, "denied"
        return True, f"authorized:{user_code}:{user_id}"


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(create_oauth2_router(SampleOAuth2Manager(), prefix="/oauth2"))
    return TestClient(app)


class TestOAuth2ApiRoutesExtraMore:
    """oauth2_api 补充分支"""

    def test_authorize_invalid_redirect_uri(self, client):
        resp = client.get(
            "/oauth2/authorize",
            params={
                "response_type": "code",
                "client_id": "client-a",
                "redirect_uri": "https://evil.example.com/callback",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_request"

    def test_authorize_unsupported_response_type_redirects(self, client):
        resp = client.get(
            "/oauth2/authorize",
            params={
                "response_type": "token",
                "client_id": "client-a",
                "redirect_uri": "https://client.example.com/callback",
                "state": "s1",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert "unsupported_response_type" in resp.headers["location"]

    def test_authorize_pkce_required_redirects(self, client):
        resp = client.get(
            "/oauth2/authorize",
            params={
                "response_type": "code",
                "client_id": "pkce-client",
                "redirect_uri": "https://client.example.com/callback",
                "state": "s2",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 307
        assert "PKCE+required" in resp.headers["location"]

    def test_authorize_submit_approve_redirects_with_code(self, client):
        resp = client.post(
            "/oauth2/authorize",
            data={
                "client_id": "client-a",
                "redirect_uri": "https://client.example.com/callback",
                "user_id": 1,
                "approve": "true",
                "state": "xyz",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "code=auth-code-xyz" in resp.headers["location"]
        assert "state=xyz" in resp.headers["location"]

    def test_token_authorization_code_success(self, client):
        resp = client.post(
            "/oauth2/token",
            data={
                "grant_type": "authorization_code",
                "code": "ok-code",
                "client_id": "client-a",
                "client_secret": "secret-a",
                "redirect_uri": "https://client.example.com/callback",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "access-from-code"

    def test_token_client_credentials_invalid_client_returns_401(self, client):
        resp = client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "client-a",
                "client_secret": "bad-secret",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    def test_token_refresh_invalid_grant_returns_401(self, client):
        resp = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "bad-refresh",
                "client_id": "client-a",
                "client_secret": "secret-a",
            },
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_grant"

    def test_token_device_pending_returns_400(self, client):
        resp = client.post(
            "/oauth2/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                "device_code": "pending-code",
                "client_id": "client-a",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "authorization_pending"

    def test_revoke_success_returns_200_empty_body(self, client):
        resp = client.post(
            "/oauth2/revoke",
            data={
                "token": "t1",
                "client_id": "client-a",
                "client_secret": "secret-a",
            },
        )
        assert resp.status_code == 200
        assert resp.json() == {}

    def test_introspect_invalid_client_and_success(self, client):
        bad_resp = client.post(
            "/oauth2/introspect",
            data={
                "token": "active-token",
                "client_id": "bad-client",
                "client_secret": "x",
            },
        )
        assert bad_resp.status_code == 401

        ok_resp = client.post(
            "/oauth2/introspect",
            data={
                "token": "active-token",
                "client_id": "client-a",
                "client_secret": "secret-a",
            },
        )
        assert ok_resp.status_code == 200
        assert ok_resp.json()["active"] is True

    def test_device_code_page_and_authorize(self, client):
        device_code_resp = client.post("/oauth2/device/code", data={"client_id": "client-a", "scope": "openid"})
        assert device_code_resp.status_code == 200
        assert device_code_resp.json()["device_code"] == "dev-code-1"

        verify_page_resp = client.get("/oauth2/device", params={"user_code": "ABCD-1234"})
        assert verify_page_resp.status_code == 200
        assert verify_page_resp.json()["user_code"] == "ABCD-1234"

        denied_resp = client.post(
            "/oauth2/device/authorize",
            data={"user_code": "ABCD-1234", "user_id": 1, "approve": "false"},
        )
        assert denied_resp.status_code == 400

        approved_resp = client.post(
            "/oauth2/device/authorize",
            data={"user_code": "ABCD-1234", "user_id": 1, "approve": "true"},
        )
        assert approved_resp.status_code == 200
        assert "authorized:ABCD-1234:1" in approved_resp.json()["message"]

    def test_authorization_server_metadata(self, client):
        resp = client.get("/oauth2/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        data = resp.json()
        assert data["authorization_endpoint"].endswith("/oauth2/authorize")
        assert "client_secret_post" in data["token_endpoint_auth_methods_supported"]
