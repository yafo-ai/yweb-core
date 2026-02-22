"""dependencies/audit/api_key 模块补充测试"""

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from yweb.auth.api_key import APIKeyData, APIKeyAuthProvider, APIKeyManager, get_api_key_from_request, require_api_key_scopes
from yweb.auth.audit import LoginAuditService
from yweb.auth.dependencies import RoleChecker, require_roles


class QueryFieldObj:
    """查询字段桩"""

    def __init__(self, name: str):
        self.name = name

    def __eq__(self, other):
        return ("eq", self.name, other)

    def __ge__(self, other):
        return ("ge", self.name, other)

    def __lt__(self, other):
        return ("lt", self.name, other)

    def desc(self):
        return ("desc", self.name)


class AuditQueryObj:
    """审计查询链路桩"""

    def __init__(self, rows=None, count_value=None):
        self._rows = rows or []
        self._count_value = count_value
        self.deleted = False

    def filter(self, *_conditions):
        return self

    def order_by(self, *_args):
        return self

    def offset(self, _v):
        return self

    def limit(self, _v):
        return self

    def all(self):
        return self._rows

    def first(self):
        return self._rows[0] if self._rows else None

    def count(self):
        if self._count_value is not None:
            return self._count_value
        return len(self._rows)

    def with_entities(self, *_args):
        return self

    def group_by(self, *_args):
        return self

    def delete(self):
        self.deleted = True
        return True


class LoginRecordModelObj:
    """登录记录模型桩"""

    user_id = QueryFieldObj("user_id")
    username = QueryFieldObj("username")
    status = QueryFieldObj("status")
    login_at = QueryFieldObj("login_at")
    ip_address = QueryFieldObj("ip_address")
    id = QueryFieldObj("id")
    query = AuditQueryObj()

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.add_called = False

    def add(self, _commit):
        self.add_called = True


class TestDependenciesExtra:
    """dependencies 补充测试"""

    def test_role_checker_all_branches(self):
        checker = RoleChecker(["admin"])

        with pytest.raises(HTTPException) as e1:
            checker(token=None, jwt_manager=None)
        assert e1.value.status_code == 401

        bad_jwt = SimpleNamespace(verify_token=lambda _token: None)
        with pytest.raises(HTTPException) as e2:
            checker(token="abc", jwt_manager=bad_jwt)
        assert e2.value.status_code == 401

        no_role_jwt = SimpleNamespace(verify_token=lambda _token: SimpleNamespace(roles=["user"]))
        with pytest.raises(HTTPException) as e3:
            checker(token="abc", jwt_manager=no_role_jwt)
        assert e3.value.status_code == 403

        ok_jwt = SimpleNamespace(verify_token=lambda _token: SimpleNamespace(roles=["admin", "user"]))
        assert checker(token="abc", jwt_manager=ok_jwt) is True

    @pytest.mark.asyncio
    async def test_require_roles_decorator_passthrough(self):
        @require_roles("admin", "manager")
        async def endpoint(**kwargs):
            return {"ok": True, "kwargs": kwargs}

        result = await endpoint(user="alice")
        assert result["ok"] is True
        assert result["kwargs"]["user"] == "alice"


class TestAuditServiceExtra:
    """audit 补充测试"""

    def test_record_login_success_and_failure_helpers(self):
        service = LoginAuditService(LoginRecordModelObj)
        success = service.record_success(user_id=1, username="alice", ip_address="127.0.0.1")
        failure = service.record_failure(username="alice", ip_address="127.0.0.1", failure_reason="bad_pwd")
        assert success.status == "success"
        assert failure.status == "failed"
        assert failure.failure_reason == "bad_pwd"
        assert success.add_called is True
        assert isinstance(success.login_at, datetime)

    def test_query_related_methods(self):
        rows = [SimpleNamespace(id=1), SimpleNamespace(id=2)]
        LoginRecordModelObj.query = AuditQueryObj(rows=rows, count_value=2)
        service = LoginAuditService(LoginRecordModelObj)

        history = service.get_user_login_history(user_id=1, limit=10, offset=0, status="success")
        assert len(history) == 2

        failures = service.get_recent_failures(username="alice", minutes=5, ip_address="127.0.0.1")
        assert failures == 2

        ip_history = service.get_ip_login_history(ip_address="127.0.0.1", limit=5, hours=1)
        assert len(ip_history) == 2

        last_login = service.get_last_successful_login(user_id=1)
        assert last_login.id == 1

    def test_count_and_cleanup_methods(self):
        LoginRecordModelObj.query = AuditQueryObj(rows=[("success", 5), ("failed", 2)])
        service = LoginAuditService(LoginRecordModelObj)
        stats = service.count_logins_by_status(user_id=1, days=7)
        assert stats["success"] == 5
        assert stats["failed"] == 2

        q_keep = AuditQueryObj(rows=[], count_value=3)
        LoginRecordModelObj.query = q_keep
        deleted1 = service.cleanup_old_records(days=90, keep_failures=True)
        assert deleted1 == 3
        assert q_keep.deleted is True

        q_all = AuditQueryObj(rows=[], count_value=4)
        LoginRecordModelObj.query = q_all
        deleted2 = service.cleanup_old_records(days=30, keep_failures=False)
        assert deleted2 == 4
        assert q_all.deleted is True


class TestApiKeyExtra:
    """api_key 补充测试"""

    @pytest.mark.asyncio
    async def test_require_api_key_scopes_decorator_forbidden_and_success(self):
        @require_api_key_scopes("admin")
        async def endpoint(*, request):
            return {"ok": True}

        req1 = SimpleNamespace(state=SimpleNamespace(api_key_data=APIKeyData(scopes=["read"])))
        with pytest.raises(HTTPException) as ex:
            await endpoint(request=req1)
        assert ex.value.status_code == 403

        req2 = SimpleNamespace(state=SimpleNamespace(api_key_data=APIKeyData(scopes=["admin"])))
        result = await endpoint(request=req2)
        assert result["ok"] is True

    @pytest.mark.asyncio
    async def test_require_api_key_scopes_without_api_key_data_passthrough(self):
        @require_api_key_scopes("admin")
        async def endpoint(*, request):
            return {"ok": True}

        req = SimpleNamespace(state=SimpleNamespace())
        result = await endpoint(request=req)
        assert result["ok"] is True

    def test_get_api_key_from_request_cookie_fallback(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "query_string": b"",
        }
        req = Request(scope)
        req._cookies = {"api_key_cookie": "cookie-key"}
        key = get_api_key_from_request(req, header_name="X-API-Key", query_name="api_key", cookie_name="api_key_cookie")
        assert key == "cookie-key"

    def test_get_api_key_from_request_header_has_priority(self):
        scope = {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"x-api-key", b"header-key")],
            "query_string": b"api_key=query-key",
        }
        req = Request(scope)
        req._cookies = {"api_key_cookie": "cookie-key"}
        key = get_api_key_from_request(req, header_name="X-API-Key", query_name="api_key", cookie_name="api_key_cookie")
        assert key == "header-key"

    def test_api_key_provider_revoke_token(self):
        manager = APIKeyManager(secret_key="k", prefix="pref")
        revoked = {"key_id": None}
        manager.set_key_store(
            getter=lambda _k: None,
            revoker=lambda key_id: revoked.update({"key_id": key_id}) or True,
        )
        provider = APIKeyAuthProvider(api_key_manager=manager, user_getter=lambda _uid: None)

        assert provider.revoke_token("bad-format") is False
        assert provider.revoke_token("pref_abcd1234_random") is True
        assert revoked["key_id"] == "abcd1234"
