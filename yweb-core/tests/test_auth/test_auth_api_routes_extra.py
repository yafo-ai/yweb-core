"""auth/api 路由补充测试

补齐以下模块的关键路由与分支：
- auth_api
- login_record_api
- oauth2_api
- oidc_api
- user_api
"""

from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from yweb.auth.api import (
    create_auth_router,
    create_login_record_router,
    create_oauth2_router,
    create_oidc_router,
    create_user_router,
)
from yweb.exceptions import register_exception_handlers


class SampleUserObj:
    """测试用户对象"""

    def __init__(
        self,
        user_id: int,
        username: str,
        name: str = "name",
        email: str | None = "u@example.com",
        phone: str | None = None,
        status: bool = True,
        roles=None,
    ):
        self.id = user_id
        self.username = username
        self.name = name
        self.email = email
        self.phone = phone
        self.status = status
        self.created_at = "2026-01-01 00:00:00"
        self.last_login_at = None
        self.roles = roles or []
        self.password_hash = ""

    def update(self, *_args, **_kwargs):
        return True


class RoleObj:
    """测试角色对象"""

    def __init__(self, code: str, name: str):
        self.code = code
        self.name = name


class TokenBlacklistStub:
    """刷新令牌黑名单桩"""

    def __init__(self, revoked_tokens=None):
        self.revoked_tokens = set(revoked_tokens or [])

    def is_revoked(self, token: str) -> bool:
        return token in self.revoked_tokens


class JWTManagerStub:
    """JWT 管理器桩"""

    def __init__(self, refresh_result=None):
        self.refresh_result = refresh_result

    def refresh_tokens(self, refresh_token: str, user_getter=None):
        _ = user_getter
        if self.refresh_result is not None:
            return self.refresh_result
        if refresh_token == "ok-refresh":
            return {
                "access_token": "new-access",
                "refresh_token": "new-refresh",
                "token_type": "bearer",
            }
        return None


class RateLimiterStub:
    """登录限流桩"""

    block_minutes = 1

    def is_blocked(self, _ip):
        return False

    def get_block_remaining_seconds(self, _ip):
        return 0

    def record_failure(self, _ip):
        return False, 2

    def reset(self, _ip):
        return True


class AuthServiceStub:
    """认证服务桩"""

    def __init__(self):
        self.rate_limiter = RateLimiterStub()
        self.logout_called_with = None
        self.kick_called_with = None

    def authenticate(self, username: str, password: str):
        if username == "admin" and password == "123456":
            return SampleUserObj(1, "admin", "管理员")
        return None

    def get_failure_reason(self, _username: str):
        return "bad_credentials"

    def on_authenticate_failure(self, *_args, **_kwargs):
        return None

    def on_authenticate_success(self, *_args, **_kwargs):
        return None

    def create_access_token(self, user):
        return f"access-{user.id}"

    def create_refresh_token(self, user):
        return f"refresh-{user.id}"

    def update_last_login(self, *_args, **_kwargs):
        return None

    def logout(self, user_id: int):
        self.logout_called_with = user_id

    def lock_user(self, user_id: int):
        self.kick_called_with = user_id


class QueryFieldStub:
    """登录记录查询字段桩"""

    def __init__(self, name: str):
        self.name = name

    def ilike(self, pattern: str):
        return ("ilike", self.name, pattern.strip("%").lower())

    def __eq__(self, other):
        return ("eq", self.name, other)

    def desc(self):
        return ("desc", self.name)


class LoginRecordQueryStub:
    """登录记录查询链路桩"""

    def __init__(self, rows):
        self._rows = list(rows)

    def with_entities(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def filter(self, condition):
        op, field, value = condition
        if op == "ilike":
            self._rows = [r for r in self._rows if value in str(getattr(r, field, "")).lower()]
        elif op == "eq":
            self._rows = [r for r in self._rows if getattr(r, field, None) == value]
        return self

    def paginate(self, page: int, page_size: int):
        total = len(self._rows)
        start = (page - 1) * page_size
        end = start + page_size
        rows = self._rows[start:end]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return SimpleNamespace(
            rows=rows,
            total_records=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
        )


class OAuth2TokenResultStub:
    """OAuth2 token 成功结果桩"""

    def __init__(self, payload: dict):
        self.payload = payload

    def to_response(self):
        return JSONResponse(status_code=200, content=self.payload)


class OAuth2ClientStub:
    """OAuth2 客户端桩"""

    require_pkce = False
    default_scopes = ["openid"]

    def __init__(self, client_name: str = "demo-client"):
        self.client_name = client_name

    def validate_redirect_uri(self, redirect_uri: str) -> bool:
        return redirect_uri.startswith("https://client.example.com/callback")


class OAuth2ManagerStub:
    """OAuth2 管理器桩"""

    def get_client(self, client_id: str):
        if client_id == "missing":
            return None
        return OAuth2ClientStub()

    def create_authorization_code(self, **_kwargs):
        return "auth-code-123"

    def exchange_code(self, **_kwargs):
        return True, OAuth2TokenResultStub(
            {
                "access_token": "access-token",
                "refresh_token": "refresh-token",
                "token_type": "bearer",
                "expires_in": 3600,
            }
        )

    def client_credentials_token(self, client_id: str, client_secret: str, scope: str | None):
        if client_id == "client-a" and client_secret == "secret-a":
            return True, OAuth2TokenResultStub(
                {"access_token": "cc-token", "token_type": "bearer", "expires_in": 3600, "scope": scope}
            )
        return False, {"error": "invalid_client", "error_description": "bad client secret"}

    def refresh_token(self, **_kwargs):
        return False, {"error": "invalid_grant"}

    def device_code_token(self, **_kwargs):
        return False, {"error": "authorization_pending"}

    def validate_client(self, client_id: str, client_secret: str | None):
        if client_id == "bad-client":
            return False, "invalid"
        if client_secret is None:
            return False, "missing secret"
        return True, "ok"

    def revoke_token(self, _token: str, _token_type_hint: str | None):
        return True

    def introspect_token(self, token: str):
        return {"active": token == "active-token", "sub": "1"}

    def create_device_code(self, **_kwargs):
        return True, SimpleNamespace(
            device_code="dev-code",
            user_code="ABCD-EFGH",
            verification_uri="/oauth2/device",
            verification_uri_complete="/oauth2/device?user_code=ABCD-EFGH",
            expires_in=1200,
            interval=5,
        )

    def authorize_device(self, user_code: str, user_id: int, approve: bool):
        if not approve:
            return False, "denied"
        return True, f"authorized:{user_code}:{user_id}"


class OIDCManagerStub:
    """OIDC 管理器桩"""

    def get_discovery_document(self, base_url: str):
        return {"issuer": base_url, "userinfo_endpoint": f"{base_url}/oidc/userinfo"}

    def get_jwks(self):
        return {"keys": [{"kty": "RSA", "kid": "kid-1"}]}

    def get_userinfo_claims(self, user_id: str, scope: str):
        if str(user_id) == "404":
            return None
        return {"sub": str(user_id), "scope": scope}


class OIDCValidateTokenStub:
    """OIDC Token 校验桩"""

    def validate_token(self, access_token: str):
        if access_token == "good-token":
            return True, {"sub": "1", "scope": "openid profile"}
        return False, {}


class UserModelStub:
    """用户模型桩（用于 user_api 路由测试）"""

    store = {
        1: SampleUserObj(1, "alice", "Alice", status=True, roles=[RoleObj("admin", "管理员")]),
        2: SampleUserObj(2, "bob", "Bob", status=False, roles=[RoleObj("user", "普通用户")]),
    }
    seq = 3

    @classmethod
    def search_with_roles(cls, keyword=None, is_active=None, role_code=None, page=1, page_size=10):
        rows = list(cls.store.values())
        if keyword:
            kw = keyword.lower()
            rows = [
                u
                for u in rows
                if kw in u.username.lower()
                or kw in (u.name or "").lower()
                or kw in (u.email or "").lower()
                or kw in (u.phone or "").lower()
            ]
        if is_active is not None:
            rows = [u for u in rows if u.status is is_active]
        if role_code:
            rows = [u for u in rows if any(r.code == role_code for r in (u.roles or []))]
        total = len(rows)
        start = (page - 1) * page_size
        end = start + page_size
        paged = rows[start:end]
        total_pages = max(1, (total + page_size - 1) // page_size)
        return SimpleNamespace(
            rows=paged,
            total_records=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            has_prev=page > 1,
            has_next=page < total_pages,
        )

    @classmethod
    def get(cls, user_id: int):
        return cls.store.get(user_id)

    @classmethod
    def create_user(cls, username: str, password: str, email: str | None, phone: str | None, name: str, is_active: bool):
        _ = password
        if any(u.username == username for u in cls.store.values()):
            raise ValueError("用户名已存在")
        user = SampleUserObj(cls.seq, username, name=name, email=email, phone=phone, status=is_active)
        cls.store[cls.seq] = user
        cls.seq += 1
        return user


class TestAuthApiRouterExtra:
    """auth_api 路由补充测试"""

    def test_login_refresh_logout_and_kick_success(self):
        app = FastAPI()
        register_exception_handlers(app)
        auth_service = AuthServiceStub()
        jwt_manager = JWTManagerStub()
        app.include_router(
            create_auth_router(
                auth_service=auth_service,
                jwt_manager=jwt_manager,
                enable_kick=True,
            ),
            prefix="/auth",
        )
        client = TestClient(app)

        login_resp = client.post("/auth/login", json={"username": "admin", "password": "123456"})
        assert login_resp.status_code == 200
        assert login_resp.json()["data"]["access_token"] == "access-1"

        refresh_resp = client.post("/auth/refresh", json={"refresh_token": "ok-refresh"})
        assert refresh_resp.status_code == 200
        assert refresh_resp.json()["data"]["refresh_token"] == "new-refresh"

        logout_resp = client.post("/auth/logout", params={"user_id": 1})
        assert logout_resp.status_code == 200
        assert auth_service.logout_called_with == 1

        kick_resp = client.post("/auth/kick", params={"user_id": 1})
        assert kick_resp.status_code == 200
        assert auth_service.kick_called_with == 1

    def test_refresh_revoked_token_returns_401(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=AuthServiceStub(),
                jwt_manager=JWTManagerStub(),
                token_blacklist=TokenBlacklistStub(revoked_tokens={"revoked-refresh"}),
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/refresh", json={"refresh_token": "revoked-refresh"})
        assert resp.status_code == 401
        assert "刷新令牌无效" in resp.json()["message"]

    def test_refresh_invalid_token_returns_401(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=AuthServiceStub(),
                jwt_manager=JWTManagerStub(refresh_result=None),
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/refresh", json={"refresh_token": "bad-refresh"})
        assert resp.status_code == 401
        assert "刷新令牌无效" in resp.json()["message"]

    def test_disable_routes_by_switches(self):
        app = FastAPI()
        app.include_router(
            create_auth_router(
                auth_service=AuthServiceStub(),
                jwt_manager=JWTManagerStub(),
                enable_oauth2_token=False,
                enable_json_login=False,
                enable_refresh=False,
                enable_logout=False,
                enable_kick=False,
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        assert client.post("/auth/token", data={"username": "x", "password": "y"}).status_code == 404
        assert client.post("/auth/login", json={"username": "x", "password": "y"}).status_code == 404
        assert client.post("/auth/refresh", json={"refresh_token": "x"}).status_code == 404
        assert client.post("/auth/logout", params={"user_id": 1}).status_code == 404


class TestLoginRecordApiRouterExtra:
    """login_record_api 路由补充测试"""

    def test_list_login_records_with_filters(self):
        records = [
            SimpleNamespace(
                username="admin",
                ip_address="127.0.0.1",
                user_agent="pytest",
                created_at=datetime(2026, 1, 1, 1, 0, 0),
                status="success",
                failure_reason=None,
            ),
            SimpleNamespace(
                username="bob",
                ip_address="10.0.0.1",
                user_agent="pytest",
                created_at=datetime(2026, 1, 1, 1, 5, 0),
                status="failed",
                failure_reason="bad pwd",
            ),
        ]
        login_record_model = SimpleNamespace(
            query=LoginRecordQueryStub(records),
            username=QueryFieldStub("username"),
            ip_address=QueryFieldStub("ip_address"),
            user_agent=QueryFieldStub("user_agent"),
            created_at=QueryFieldStub("created_at"),
            status=QueryFieldStub("status"),
            failure_reason=QueryFieldStub("failure_reason"),
        )

        app = FastAPI()
        app.include_router(create_login_record_router(login_record_model), prefix="/records")
        client = TestClient(app)
        resp = client.get("/records/list", params={"username": "adm", "status": "SUCCESS", "page": 1, "page_size": 5})

        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["total_records"] == 1
        assert payload["rows"][0]["username"] == "admin"


class TestOAuth2ApiRouterExtra:
    """oauth2_api 路由补充测试"""

    @pytest.fixture
    def oauth2_client(self):
        app = FastAPI()
        app.include_router(create_oauth2_router(OAuth2ManagerStub(), prefix="/oauth2"))
        return TestClient(app)

    def test_authorize_invalid_client(self, oauth2_client):
        resp = oauth2_client.get(
            "/oauth2/authorize",
            params={
                "response_type": "code",
                "client_id": "missing",
                "redirect_uri": "https://client.example.com/callback",
            },
        )
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_client"

    def test_authorize_submit_denied(self, oauth2_client):
        resp = oauth2_client.post(
            "/oauth2/authorize",
            data={
                "client_id": "client-a",
                "redirect_uri": "https://client.example.com/callback",
                "user_id": 1,
                "approve": "false",
            },
            follow_redirects=False,
        )
        assert resp.status_code == 302
        assert "error=access_denied" in resp.headers["location"]

    def test_token_client_credentials_success(self, oauth2_client):
        resp = oauth2_client.post(
            "/oauth2/token",
            data={
                "grant_type": "client_credentials",
                "client_id": "client-a",
                "client_secret": "secret-a",
                "scope": "read write",
            },
        )
        assert resp.status_code == 200
        assert resp.json()["access_token"] == "cc-token"

    def test_token_unsupported_grant_type(self, oauth2_client):
        resp = oauth2_client.post("/oauth2/token", data={"grant_type": "unknown"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "unsupported_grant_type"

    def test_token_refresh_invalid_grant_returns_401(self, oauth2_client):
        resp = oauth2_client.post(
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

    def test_revoke_invalid_client(self, oauth2_client):
        resp = oauth2_client.post(
            "/oauth2/revoke",
            data={"token": "any-token", "client_id": "bad-client", "client_secret": "x"},
        )
        assert resp.status_code == 401
        assert resp.json()["error"] == "invalid_client"

    def test_metadata_endpoint(self, oauth2_client):
        resp = oauth2_client.get("/oauth2/.well-known/oauth-authorization-server")
        assert resp.status_code == 200
        payload = resp.json()
        assert payload["authorization_endpoint"].endswith("/oauth2/authorize")
        assert "client_secret_basic" in payload["token_endpoint_auth_methods_supported"]


class TestOidcApiRouterExtra:
    """oidc_api 路由补充测试"""

    @pytest.fixture
    def oidc_client(self):
        app = FastAPI()
        app.include_router(
            create_oidc_router(
                oidc_manager=OIDCManagerStub(),
                oauth2_manager=OIDCValidateTokenStub(),
                prefix="/oidc",
            )
        )
        return TestClient(app)

    def test_discovery_and_jwks(self, oidc_client):
        discovery_resp = oidc_client.get("/oidc/.well-known/openid-configuration")
        assert discovery_resp.status_code == 200
        assert "issuer" in discovery_resp.json()

        jwks_resp = oidc_client.get("/oidc/.well-known/jwks.json")
        assert jwks_resp.status_code == 200
        assert jwks_resp.json()["keys"][0]["kid"] == "kid-1"

    def test_userinfo_requires_bearer_token(self, oidc_client):
        resp = oidc_client.get("/oidc/userinfo")
        assert resp.status_code == 401
        assert "Bearer token required" in resp.json()["detail"]

    def test_userinfo_success(self, oidc_client):
        resp = oidc_client.get("/oidc/userinfo", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "1"

    def test_userinfo_without_oauth2_manager_returns_500(self):
        app = FastAPI()
        app.include_router(create_oidc_router(oidc_manager=OIDCManagerStub(), oauth2_manager=None, prefix="/oidc"))
        client = TestClient(app)
        resp = client.get("/oidc/userinfo", headers={"Authorization": "Bearer any-token"})
        assert resp.status_code == 500
        assert "OAuth2 manager not configured" in resp.json()["detail"]


class TestUserApiRouterExtra:
    """user_api 路由补充测试"""

    @pytest.fixture
    def user_client(self):
        UserModelStub.store = {
            1: SampleUserObj(1, "alice", "Alice", status=True, roles=[RoleObj("admin", "管理员")]),
            2: SampleUserObj(2, "bob", "Bob", status=False, roles=[RoleObj("user", "普通用户")]),
        }
        UserModelStub.seq = 3

        app = FastAPI()
        app.include_router(create_user_router(UserModelStub), prefix="/users")
        return TestClient(app)

    def test_list_users_and_get_not_found(self, user_client):
        list_resp = user_client.get("/users/list", params={"keyword": "ali", "status": "active", "role": "admin"})
        assert list_resp.status_code == 200
        rows = list_resp.json()["data"]["rows"]
        assert len(rows) == 1
        assert rows[0]["username"] == "alice"

        get_resp = user_client.get("/users/get", params={"user_id": 999})
        assert get_resp.status_code == 404
        assert "用户不存在" in get_resp.json()["message"]

    def test_create_update_enable_disable(self, user_client):
        create_resp = user_client.post(
            "/users/create",
            json={
                "username": "charlie",
                "name": "Charlie",
                "email": "charlie@example.com",
                "phone": "13800000000",
                "password": "Passw0rd!",
                "status": "active",
            },
        )
        assert create_resp.status_code == 200
        created_id = create_resp.json()["data"]["id"]

        duplicate_resp = user_client.post(
            "/users/create",
            json={
                "username": "charlie",
                "name": "Charlie2",
                "email": "charlie2@example.com",
                "phone": "13800000001",
                "password": "Passw0rd!",
                "status": "active",
            },
        )
        assert duplicate_resp.status_code == 400

        update_resp = user_client.post(
            "/users/update",
            params={"user_id": created_id},
            json={"name": "Charlie New", "email": "new@example.com", "phone": "13811111111", "status": "inactive"},
        )
        assert update_resp.status_code == 200
        assert update_resp.json()["data"]["name"] == "Charlie New"

        enable_resp = user_client.post("/users/enable", params={"user_id": created_id})
        assert enable_resp.status_code == 200
        enable_status = enable_resp.json()["data"].get("is_active", enable_resp.json()["data"].get("status"))
        assert enable_status == "active"

        disable_resp = user_client.post("/users/disable", params={"user_id": created_id})
        assert disable_resp.status_code == 200
        disable_status = disable_resp.json()["data"].get("is_active", disable_resp.json()["data"].get("status"))
        assert disable_status == "inactive"

    def test_reset_password_success_and_not_found(self, user_client):
        with patch("yweb.auth.validators.PasswordValidator.validate_or_raise") as mock_validate, patch(
            "yweb.auth.password.PasswordHelper.hash", return_value="hashed-password"
        ) as mock_hash:
            ok_resp = user_client.post("/users/reset-password", params={"user_id": 1}, json={"password": "StrongPass123!"})
            assert ok_resp.status_code == 200
            assert ok_resp.json()["data"]["id"] == 1
            mock_validate.assert_called_once()
            mock_hash.assert_called_once()

        not_found_resp = user_client.post("/users/reset-password", params={"user_id": 999}, json={"password": "StrongPass123!"})
        assert not_found_resp.status_code == 404
