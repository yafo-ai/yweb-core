"""auth_api/user_api/oidc_api 路由补充测试（二）"""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.auth.api import create_auth_router, create_oidc_router, create_user_router
from yweb.exceptions import register_exception_handlers


class SampleRateLimiter:
    """限流器桩"""

    block_minutes = 2

    def __init__(self, blocked: bool = False, was_blocked_after_fail: bool = False):
        self.blocked = blocked
        self.was_blocked_after_fail = was_blocked_after_fail
        self.reset_called = False

    def is_blocked(self, _ip):
        return self.blocked

    def get_block_remaining_seconds(self, _ip):
        return 61

    def record_failure(self, _ip):
        if self.was_blocked_after_fail:
            return True, 0
        return False, 1

    def reset(self, _ip):
        self.reset_called = True
        return True


class SampleUser:
    """用户对象桩"""

    def __init__(self, user_id: int, username: str, is_active: bool = True):
        self.id = user_id
        self.username = username
        self.name = username
        self.email = f"{username}@example.com"
        self.phone = None
        self.status = is_active
        self.created_at = "2026-01-01 00:00:00"
        self.last_login_at = None
        self.roles = []
        self.password_hash = ""

    def update(self, *_args, **_kwargs):
        return True


class SampleAuthService:
    """认证服务桩"""

    def __init__(self, mode: str = "ok"):
        self.mode = mode
        self.rate_limiter = SampleRateLimiter(
            blocked=(mode == "ip_blocked"),
            was_blocked_after_fail=(mode == "fail_then_block"),
        )

    def authenticate(self, username, password):
        if self.mode == "auth_exception":
            raise RuntimeError("db down")
        if self.mode in ("auth_fail", "fail_then_block"):
            return None
        if username == "admin" and password == "123456":
            return SampleUser(1, "admin")
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


class SampleJwtManager:
    """JWT 管理器桩"""

    def __init__(self, refresh_result=None):
        self.refresh_result = refresh_result

    def refresh_tokens(self, _refresh_token, user_getter=None):
        _ = user_getter
        return self.refresh_result


class SampleOidcManager:
    """OIDC 管理器桩"""

    def get_discovery_document(self, base_url: str):
        return {"issuer": base_url}

    def get_jwks(self):
        return {"keys": [{"kid": "k1"}]}

    def get_userinfo_claims(self, user_id: str, scope: str):
        _ = scope
        if str(user_id) == "404":
            return None
        return {"sub": str(user_id)}


class SampleOauth2Validator:
    """OIDC token 验证桩"""

    def __init__(self, valid=True, sub="1"):
        self.valid = valid
        self.sub = sub

    def validate_token(self, _token: str):
        if not self.valid:
            return False, {}
        return True, {"sub": self.sub, "scope": "openid"}


class SampleUserModel:
    """用户模型桩"""

    users = {
        1: SampleUser(1, "alice"),
        2: SampleUser(2, "bob", is_active=False),
    }

    @classmethod
    def search_with_roles(cls, keyword=None, is_active=None, role_code=None, page=1, page_size=10):
        _ = (keyword, is_active, role_code, page, page_size)
        return type(
            "Page",
            (),
            {
                "rows": list(cls.users.values()),
                "total_records": len(cls.users),
                "page": 1,
                "page_size": 10,
                "total_pages": 1,
                "has_prev": False,
                "has_next": False,
            },
        )()

    @classmethod
    def get(cls, user_id):
        return cls.users.get(user_id)

    @classmethod
    def create_user(cls, username, password, email, phone, name, is_active):
        _ = (password, email, phone, name, is_active)
        if username == "dup":
            raise ValueError("用户名已存在")
        new_id = max(cls.users.keys()) + 1
        user = SampleUser(new_id, username)
        cls.users[new_id] = user
        return user


class TestAuthApiRoutesExtraMore:
    """auth_api 补充分支"""

    def _build_client(self, auth_service, jwt_manager=None):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=auth_service,
                jwt_manager=jwt_manager or SampleJwtManager(refresh_result=None),
            ),
            prefix="/auth",
        )
        return TestClient(app, raise_server_exceptions=False)

    def test_login_when_ip_blocked(self):
        client = self._build_client(SampleAuthService(mode="ip_blocked"))
        resp = client.post("/auth/login", json={"username": "admin", "password": "123456"})
        assert resp.status_code == 401
        assert "登录尝试次数过多" in resp.json()["message"]

    def test_login_failed_remaining_attempts(self):
        client = self._build_client(SampleAuthService(mode="auth_fail"))
        resp = client.post("/auth/login", json={"username": "admin", "password": "badbad"})
        assert resp.status_code == 401
        assert "还可尝试" in resp.json()["message"]

    def test_login_failed_then_blocked(self):
        client = self._build_client(SampleAuthService(mode="fail_then_block"))
        resp = client.post("/auth/login", json={"username": "admin", "password": "badbad"})
        assert resp.status_code == 401
        assert "登录尝试次数过多" in resp.json()["message"]

    def test_login_system_exception_raises_500(self):
        client = self._build_client(SampleAuthService(mode="auth_exception"))
        resp = client.post("/auth/login", json={"username": "admin", "password": "123456"})
        assert resp.status_code == 500
        assert resp.json()["status"] == "error"

    def test_login_with_custom_response_builder(self):
        app = FastAPI()
        register_exception_handlers(app)
        app.include_router(
            create_auth_router(
                auth_service=SampleAuthService(mode="ok"),
                jwt_manager=SampleJwtManager(refresh_result=None),
                login_response_builder=lambda user, access, refresh: {
                    "uid": user.id,
                    "access_token": access,
                    "refresh_token": refresh,
                    "token_type": "bearer",
                    "user": {"id": user.id},
                },
            ),
            prefix="/auth",
        )
        client = TestClient(app)
        resp = client.post("/auth/login", json={"username": "admin", "password": "123456"})
        assert resp.status_code == 200
        assert resp.json()["data"]["uid"] == 1

    def test_login_success_resets_rate_limiter(self):
        auth_service = SampleAuthService(mode="ok")
        client = self._build_client(auth_service, SampleJwtManager(refresh_result=None))
        resp = client.post("/auth/login", json={"username": "admin", "password": "123456"})
        assert resp.status_code == 200
        assert auth_service.rate_limiter.reset_called is True

    def test_refresh_invalid_token_returns_401(self):
        client = self._build_client(SampleAuthService(mode="ok"), SampleJwtManager(refresh_result=None))
        resp = client.post("/auth/refresh", json={"refresh_token": "bad-refresh"})
        assert resp.status_code == 401
        assert "刷新令牌无效" in resp.json()["message"]


class TestOidcApiRoutesExtraMore:
    """oidc_api 补充分支"""

    def test_userinfo_without_oauth2_manager_returns_500(self):
        app = FastAPI()
        app.include_router(create_oidc_router(oidc_manager=SampleOidcManager(), oauth2_manager=None, prefix="/oidc"))
        client = TestClient(app)

        resp = client.get("/oidc/userinfo", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 500
        assert "not configured" in resp.json()["detail"]

    def test_userinfo_invalid_token_returns_401(self):
        app = FastAPI()
        app.include_router(
            create_oidc_router(
                oidc_manager=SampleOidcManager(),
                oauth2_manager=SampleOauth2Validator(valid=False),
                prefix="/oidc",
            )
        )
        client = TestClient(app)

        resp = client.get("/oidc/userinfo", headers={"Authorization": "Bearer bad-token"})
        assert resp.status_code == 401
        assert "Invalid or expired token" in resp.json()["detail"]

    def test_userinfo_user_not_found_returns_404(self):
        app = FastAPI()
        app.include_router(
            create_oidc_router(
                oidc_manager=SampleOidcManager(),
                oauth2_manager=SampleOauth2Validator(valid=True, sub="404"),
                prefix="/oidc",
            )
        )
        client = TestClient(app)

        resp = client.get("/oidc/userinfo", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 404
        assert "User not found" in resp.json()["detail"]

    def test_userinfo_post_success(self):
        app = FastAPI()
        app.include_router(
            create_oidc_router(
                oidc_manager=SampleOidcManager(),
                oauth2_manager=SampleOauth2Validator(valid=True, sub="1"),
                prefix="/oidc",
            )
        )
        client = TestClient(app)
        resp = client.post("/oidc/userinfo", headers={"Authorization": "Bearer good-token"})
        assert resp.status_code == 200
        assert resp.json()["sub"] == "1"


class TestUserApiRoutesExtraMore:
    """user_api 补充分支"""

    @pytest.fixture
    def client(self):
        SampleUserModel.users = {
            1: SampleUser(1, "alice"),
            2: SampleUser(2, "bob", is_active=False),
        }
        app = FastAPI()
        app.include_router(create_user_router(SampleUserModel), prefix="/users")
        return TestClient(app)

    def test_update_user_not_found(self, client):
        resp = client.post(
            "/users/update",
            params={"user_id": 999},
            json={"name": "x", "email": None, "phone": None, "status": "active"},
        )
        assert resp.status_code == 404
        assert "用户不存在" in resp.json()["message"]

    def test_enable_disable_user_not_found(self, client):
        enable_resp = client.post("/users/enable", params={"user_id": 999})
        disable_resp = client.post("/users/disable", params={"user_id": 999})
        assert enable_resp.status_code == 404
        assert disable_resp.status_code == 404

    def test_reset_password_bad_request_from_validator(self, client):
        with patch("yweb.auth.validators.PasswordValidator.validate_or_raise", side_effect=ValueError("密码太弱")):
            resp = client.post("/users/reset-password", params={"user_id": 1}, json={"password": "weak"})
        assert resp.status_code == 400
        assert "密码太弱" in resp.json()["message"]

    def test_create_user_duplicate_returns_400(self, client):
        resp = client.post(
            "/users/create",
            json={
                "username": "dup",
                "name": "duplicate",
                "email": "dup@example.com",
                "phone": "13800000000",
                "password": "Passw0rd!",
                "status": "active",
            },
        )
        assert resp.status_code == 400
        assert "用户名已存在" in resp.json()["message"]
