"""auth api 路由补充测试（三）：边界与剩余分支"""

from base64 import b64encode
from datetime import datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.auth.api import create_auth_router, create_login_record_router, create_oauth2_router, create_user_router
from yweb.exceptions import register_exception_handlers


class AuthUserObj:
    """认证用户桩"""

    def __init__(self, user_id: int, username: str):
        self.id = user_id
        self.username = username
        self.email = f"{username}@example.com"
        self.phone = None
        self.is_active = True


class AuthServiceNoLimiterStub:
    """无限流认证服务桩"""

    rate_limiter = None

    def authenticate(self, username: str, password: str):
        if username == "ok" and password == "123456":
            return AuthUserObj(1, "ok")
        return None

    def get_failure_reason(self, _username):
        return "bad_credentials"

    def on_authenticate_failure(self, *_args, **_kwargs):
        return None

    def on_authenticate_success(self, *_args, **_kwargs):
        return None

    def create_access_token(self, user):
        return f"acc-{user.id}"

    def create_refresh_token(self, user):
        return f"ref-{user.id}"

    def update_last_login(self, *_args, **_kwargs):
        return None

    def logout(self, _user_id):
        return None

    def lock_user(self, _user_id):
        return None


class JwtRefreshStub:
    """刷新令牌桩"""

    def refresh_tokens(self, _refresh_token, user_getter=None):
        _ = user_getter
        return {"access_token": "new-access", "refresh_token": "new-refresh", "token_type": "bearer"}


class QueryField:
    """查询字段桩"""

    def __init__(self, name):
        self.name = name

    def ilike(self, pattern):
        return ("ilike", self.name, pattern.strip("%").lower())

    def __eq__(self, other):
        return ("eq", self.name, other)

    def desc(self):
        return ("desc", self.name)


class LoginRecordQuery:
    """登录记录查询桩"""

    def __init__(self, rows):
        self.rows = list(rows)

    def with_entities(self, *_args):
        return self

    def order_by(self, *_args):
        return self

    def filter(self, condition):
        op, field, value = condition
        if op == "ilike":
            self.rows = [r for r in self.rows if value in str(getattr(r, field, "")).lower()]
        elif op == "eq":
            self.rows = [r for r in self.rows if getattr(r, field, None) == value]
        return self

    def paginate(self, page, page_size):
        total = len(self.rows)
        start = (page - 1) * page_size
        end = start + page_size
        slice_rows = self.rows[start:end]
        pages = max(1, (total + page_size - 1) // page_size)
        return SimpleNamespace(
            rows=slice_rows,
            total_records=total,
            page=page,
            page_size=page_size,
            total_pages=pages,
            has_prev=page > 1,
            has_next=page < pages,
        )


class OAuth2TokenResult:
    """OAuth2 token 结果桩"""

    def __init__(self, payload):
        self.payload = payload

    def to_response(self):
        return self.payload


class OAuth2Client:
    """OAuth2 client 桩"""

    require_pkce = False
    default_scopes = ["openid"]
    client_name = "client-name"

    def validate_redirect_uri(self, redirect_uri):
        return redirect_uri == "https://client.example.com/callback"


class OAuth2ManagerExtraStub:
    """OAuth2 管理器补充分支桩"""

    def get_client(self, _client_id):
        return OAuth2Client()

    def create_authorization_code(self, **_kwargs):
        return "code-abc"

    def exchange_code(self, **_kwargs):
        return True, OAuth2TokenResult({"access_token": "from-code", "token_type": "bearer", "expires_in": 3600})

    def client_credentials_token(self, client_id, client_secret, scope):
        _ = scope
        if client_id == "basic-client" and client_secret == "basic-secret":
            return True, OAuth2TokenResult({"access_token": "from-basic", "token_type": "bearer", "expires_in": 3600})
        return False, {"error": "invalid_client"}

    def refresh_token(self, refresh_token, client_id, client_secret, scope):
        _ = (refresh_token, client_id, client_secret, scope)
        return False, {"error": "server_error"}

    def device_code_token(self, device_code, client_id):
        _ = (device_code, client_id)
        return False, {"error": "authorization_pending"}

    def validate_client(self, client_id, client_secret):
        _ = (client_id, client_secret)
        return True, "ok"

    def revoke_token(self, token, token_type_hint):
        _ = (token, token_type_hint)
        return True

    def introspect_token(self, token):
        return {"active": token == "active", "sub": "1"}

    def create_device_code(self, client_id, scope, verification_uri):
        _ = (client_id, scope, verification_uri)
        return False, {"error": "invalid_client"}

    def authorize_device(self, user_code, user_id, approve):
        _ = (user_code, user_id, approve)
        return True, "ok"


class UserObj:
    """用户对象桩"""

    def __init__(self, user_id, username, status=True):
        self.id = user_id
        self.username = username
        self.name = username
        self.email = f"{username}@example.com"
        self.phone = None
        self.status = status
        self.created_at = "2026-01-01 00:00:00"
        self.last_login_at = None
        self.roles = []
        self.password_hash = ""

    def update(self, *_args, **_kwargs):
        return True


class UserModelEdgeStub:
    """用户模型边界桩"""

    store = {
        1: UserObj(1, "active_user", status=True),
        2: UserObj(2, "inactive_user", status=False),
    }

    @classmethod
    def search_with_roles(cls, keyword=None, is_active=None, role_code=None, page=1, page_size=10):
        _ = (role_code, page, page_size)
        rows = list(cls.store.values())
        if keyword:
            rows = [u for u in rows if keyword in u.username]
        if is_active is not None:
            rows = [u for u in rows if u.status is is_active]
        return SimpleNamespace(
            rows=rows,
            total_records=len(rows),
            page=1,
            page_size=10,
            total_pages=1,
            has_prev=False,
            has_next=False,
        )

    @classmethod
    def get(cls, user_id):
        return cls.store.get(user_id)

    @classmethod
    def create_user(cls, username, password, email, phone, name, is_active):
        _ = (password, email, phone, name, is_active)
        uid = max(cls.store.keys()) + 1
        u = UserObj(uid, username, status=is_active)
        cls.store[uid] = u
        return u


class TestAuthApiEdgeCases:
    """auth_api 余量分支"""

    def test_login_without_rate_limiter_returns_generic_401(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=AuthServiceNoLimiterStub(),
                jwt_manager=JwtRefreshStub(),
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/login", json={"username": "bad", "password": "123456"})
        assert resp.status_code == 401
        assert resp.json()["message"] == "用户名或密码错误"

    def test_oauth2_password_token_endpoint_success(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=AuthServiceNoLimiterStub(),
                jwt_manager=JwtRefreshStub(),
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/token", data={"username": "ok", "password": "123456"})
        assert resp.status_code == 200
        assert resp.json()["data"]["access_token"] == "acc-1"

    def test_login_uses_custom_response_builder(self):
        app = FastAPI()
        register_exception_handlers(app)

        def builder(user, access_token, refresh_token):
            return {
                "access_token": access_token,
                "refresh_token": refresh_token,
                "token_type": "bearer",
                "user": {"id": user.id, "username": user.username, "custom": True},
            }

        app.include_router(
            create_auth_router(
                auth_service=AuthServiceNoLimiterStub(),
                jwt_manager=JwtRefreshStub(),
                login_response_builder=builder,
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/login", json={"username": "ok", "password": "123456"})
        assert resp.status_code == 200
        assert resp.json()["data"]["user"]["custom"] is True


class TestLoginRecordApiEdgeCases:
    """login_record_api 余量分支"""

    def test_filter_by_ip_and_status(self):
        records = [
            SimpleNamespace(
                username="admin",
                ip_address="192.168.1.100",
                user_agent="pytest",
                created_at=datetime(2026, 1, 1, 8, 0, 0),
                status="failed",
                failure_reason="bad",
            ),
            SimpleNamespace(
                username="alice",
                ip_address="10.0.0.1",
                user_agent="pytest",
                created_at=datetime(2026, 1, 1, 9, 0, 0),
                status="success",
                failure_reason=None,
            ),
        ]
        login_model = SimpleNamespace(
            query=LoginRecordQuery(records),
            username=QueryField("username"),
            ip_address=QueryField("ip_address"),
            user_agent=QueryField("user_agent"),
            created_at=QueryField("created_at"),
            status=QueryField("status"),
            failure_reason=QueryField("failure_reason"),
        )
        app = FastAPI()
        app.include_router(create_login_record_router(login_model), prefix="/records")
        client = TestClient(app)
        resp = client.get("/records/list", params={"ip_address": "192.168", "status": "FAILED"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["total_records"] == 1
        assert data["rows"][0]["ip_address"] == "192.168.1.100"


class TestOAuth2ApiEdgeCases:
    """oauth2_api 余量分支"""

    def _basic_header(self, username: str, password: str):
        raw = f"{username}:{password}".encode("utf-8")
        return {"Authorization": f"Basic {b64encode(raw).decode('utf-8')}"}

    def test_authorize_success_and_submit_without_state(self):
        app = FastAPI()
        app.include_router(create_oauth2_router(OAuth2ManagerExtraStub(), prefix="/oauth2"))
        client = TestClient(app)

        auth_resp = client.get(
            "/oauth2/authorize",
            params={
                "response_type": "code",
                "client_id": "client-a",
                "redirect_uri": "https://client.example.com/callback",
            },
        )
        assert auth_resp.status_code == 200
        assert auth_resp.json()["client_name"] == "client-name"

        submit_resp = client.post(
            "/oauth2/authorize",
            data={
                "client_id": "client-a",
                "redirect_uri": "https://client.example.com/callback",
                "user_id": 1,
                "approve": "true",
            },
            follow_redirects=False,
        )
        assert submit_resp.status_code == 302
        assert "state=" not in submit_resp.headers["location"]

    def test_authorize_unsupported_response_type_redirects(self):
        app = FastAPI()
        app.include_router(create_oauth2_router(OAuth2ManagerExtraStub(), prefix="/oauth2"))
        client = TestClient(app)
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

    def test_token_and_revoke_introspect_with_basic_auth_and_without_client_id(self):
        app = FastAPI()
        app.include_router(create_oauth2_router(OAuth2ManagerExtraStub(), prefix="/oauth2"))
        client = TestClient(app)

        token_resp = client.post(
            "/oauth2/token",
            data={"grant_type": "client_credentials"},
            headers=self._basic_header("basic-client", "basic-secret"),
        )
        assert token_resp.status_code == 200
        assert token_resp.json()["access_token"] == "from-basic"

        server_error_resp = client.post(
            "/oauth2/token",
            data={
                "grant_type": "refresh_token",
                "refresh_token": "r1",
                "client_id": "x",
                "client_secret": "y",
            },
        )
        assert server_error_resp.status_code == 400
        assert server_error_resp.json()["error"] == "server_error"

        revoke_resp = client.post("/oauth2/revoke", data={"token": "t1"})
        assert revoke_resp.status_code == 200
        assert revoke_resp.json() == {}

        revoke_basic_resp = client.post(
            "/oauth2/revoke",
            data={"token": "t2"},
            headers=self._basic_header("basic-client", "basic-secret"),
        )
        assert revoke_basic_resp.status_code == 200

        introspect_basic_resp = client.post(
            "/oauth2/introspect",
            data={"token": "active"},
            headers=self._basic_header("basic-client", "basic-secret"),
        )
        assert introspect_basic_resp.status_code == 200
        assert introspect_basic_resp.json()["active"] is True

        introspect_no_client_resp = client.post("/oauth2/introspect", data={"token": "active"})
        assert introspect_no_client_resp.status_code == 200
        assert introspect_no_client_resp.json()["active"] is True

    def test_device_code_failure_branch(self):
        app = FastAPI()
        app.include_router(create_oauth2_router(OAuth2ManagerExtraStub(), prefix="/oauth2"))
        client = TestClient(app)
        resp = client.post("/oauth2/device/code", data={"client_id": "bad-client"})
        assert resp.status_code == 400
        assert resp.json()["error"] == "invalid_client"


class TestUserApiEdgeCases:
    """user_api 余量分支"""

    def test_list_inactive_and_get_existing_user(self):
        UserModelEdgeStub.store = {
            1: UserObj(1, "active_user", status=True),
            2: UserObj(2, "inactive_user", status=False),
        }
        app = FastAPI()
        app.include_router(create_user_router(UserModelEdgeStub), prefix="/users")
        client = TestClient(app)

        list_resp = client.get("/users/list", params={"status": "inactive"})
        assert list_resp.status_code == 200
        rows = list_resp.json()["data"]["rows"]
        assert len(rows) == 1
        assert rows[0]["username"] == "inactive_user"

        get_resp = client.get("/users/get", params={"user_id": 1})
        assert get_resp.status_code == 200
        assert get_resp.json()["data"]["username"] == "active_user"

    def test_update_only_status_branch(self):
        UserModelEdgeStub.store = {
            1: UserObj(1, "active_user", status=True),
        }
        app = FastAPI()
        app.include_router(create_user_router(UserModelEdgeStub), prefix="/users")
        client = TestClient(app)
        resp = client.post(
            "/users/update",
            params={"user_id": 1},
            json={"name": "", "email": None, "phone": None, "status": "inactive"},
        )
        assert resp.status_code == 200
        data = resp.json()["data"]
        status = data.get("is_active", data.get("status"))
        assert status == "inactive"
