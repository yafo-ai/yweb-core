"""service/setup 模块补充测试"""

from types import SimpleNamespace

import pytest

from yweb.auth.service import BaseAuthService
from yweb.auth.setup import (
    AuthSetup,
    _create_auth_dependencies,
    _create_jwt_manager,
    _create_user_getter,
    _detect_table_prefix,
    _resolve_login_record_model,
)
from yweb.exceptions import AuthenticationException


class UserObj:
    """用户对象桩"""

    def __init__(self, user_id=1, username="u1", is_active=True, password_hash="hashed", roles=None):
        self.id = user_id
        self.username = username
        self.is_active = is_active
        self.password_hash = password_hash
        self.email = f"{username}@example.com"
        self.roles = roles or []
        self.last_login_at = None
        self.updated = False
        self.failed_login_attempts = 0
        self.can_login = True
        self.is_locked = False

    def update(self):
        self.updated = True

    def reset_failed_attempts(self):
        self.failed_login_attempts = 0

    def record_failed_login(self, max_attempts=20, lock_duration_minutes=30):
        _ = lock_duration_minutes
        self.failed_login_attempts += 1
        if self.failed_login_attempts >= max_attempts:
            self.is_locked = True
            self.can_login = False
            return True
        return False


class UserModelObj:
    """用户模型桩"""

    users_by_name = {}
    users_by_id = {}

    @classmethod
    def get_by_username(cls, username):
        return cls.users_by_name.get(username)

    @classmethod
    def get(cls, user_id):
        return cls.users_by_id.get(user_id)


class JWTManagerObj:
    """JWT 管理器桩"""

    def __init__(self):
        self.last_access_payload = None
        self.last_refresh_payload = None
        self.verify_result = None

    def create_access_token(self, payload):
        self.last_access_payload = payload
        return "access-token"

    def create_refresh_token(self, payload):
        self.last_refresh_payload = payload
        return "refresh-token"

    def verify_token(self, token, raise_on_expired=False):
        _ = token
        _ = raise_on_expired
        return self.verify_result


class BlacklistObj:
    """黑名单桩"""

    def __init__(self, revoked=None):
        self.revoked = set(revoked or [])
        self.revoked_all = []

    def is_revoked(self, token):
        return token in self.revoked

    def revoke_all_user_tokens(self, user_id, reason=""):
        self.revoked_all.append((user_id, reason))


class LoginRecordModelObj:
    """登录记录模型桩"""

    records = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs

    @classmethod
    def create_record(cls, record):
        cls.records.append(record.kwargs)
        return record


class AuditServiceObj:
    """审计服务桩"""

    def __init__(self):
        self.items = []

    def record_login(self, **kwargs):
        self.items.append(kwargs)


class TestBaseAuthServiceExtra:
    """BaseAuthService 补充分支"""

    def test_authenticate_and_failure_reason(self, monkeypatch):
        import yweb.auth.password as pwd_mod

        user = UserObj(user_id=1, username="alice", is_active=True, password_hash="hash")
        UserModelObj.users_by_name = {"alice": user}
        UserModelObj.users_by_id = {1: user}

        jwt_mgr = JWTManagerObj()
        service = BaseAuthService(user_model=UserModelObj, jwt_manager=jwt_mgr)

        monkeypatch.setattr(pwd_mod.PasswordHelper, "verify", lambda p, h: p == "ok" and h == "hash")
        assert service.authenticate("alice", "ok").username == "alice"
        assert service.authenticate("alice", "bad") is None
        assert service.authenticate("nouser", "ok") is None

        user.is_active = False
        if hasattr(user, "can_login"):
            delattr(user, "can_login")
        assert service.authenticate("alice", "ok") is None
        assert service.get_failure_reason("alice") == "账户已禁用"
        assert service.get_failure_reason("nouser") == "用户不存在"

    def test_token_ops_refresh_and_logout(self):
        role = SimpleNamespace(code="admin")
        user = UserObj(user_id=1, username="alice", roles=[role], is_active=True)
        UserModelObj.users_by_name = {"alice": user}
        UserModelObj.users_by_id = {1: user}

        jwt_mgr = JWTManagerObj()
        blacklist = BlacklistObj(revoked={"revoked-token"})
        service = BaseAuthService(user_model=UserModelObj, jwt_manager=jwt_mgr, token_blacklist=blacklist)

        acc = service.create_access_token(user)
        ref = service.create_refresh_token(user)
        assert acc == "access-token"
        assert ref == "refresh-token"
        assert jwt_mgr.last_access_payload.roles == ["admin"]

        # 黑名单令牌直接失败
        assert service.verify_token("revoked-token") is None

        # 刷新流程：token_type 必须为 refresh
        jwt_mgr.verify_result = SimpleNamespace(user_id=1, token_type="access")
        assert service.refresh_token("r1") is None
        jwt_mgr.verify_result = SimpleNamespace(user_id=1, token_type="refresh")
        assert service.refresh_token("r1") == "access-token"

        service.logout(1)
        assert blacklist.revoked_all == [(1, "user_logout")]

    def test_verify_token_handles_exceptions(self):
        user = UserObj(user_id=1, username="alice", is_active=True)
        UserModelObj.users_by_name = {"alice": user}
        UserModelObj.users_by_id = {1: user}

        class BrokenJWT(JWTManagerObj):
            def verify_token(self, token, raise_on_expired=False):
                _ = token
                _ = raise_on_expired
                raise RuntimeError("decode error")

        service = BaseAuthService(user_model=UserModelObj, jwt_manager=BrokenJWT())
        assert service.verify_token("any-token") is None

    def test_lock_unlock_update_last_login_and_hooks(self):
        user = UserObj(user_id=1, username="alice", roles=[SimpleNamespace(code="admin")], is_active=True)
        UserModelObj.users_by_name = {"alice": user}
        UserModelObj.users_by_id = {1: user}
        LoginRecordModelObj.records = []
        audit = AuditServiceObj()

        service = BaseAuthService(
            user_model=UserModelObj,
            jwt_manager=JWTManagerObj(),
            login_record_model=LoginRecordModelObj,
            audit_service=audit,
            max_login_attempts=2,
        )

        service.lock_user(1)
        assert user.is_active is False
        service.unlock_user(1)
        assert user.is_active is True

        service.update_last_login(1, ip_address="127.0.0.1", user_agent="pytest", status="success")
        assert user.updated is True
        assert len(LoginRecordModelObj.records) == 1
        assert len(audit.items) == 1

        # 成功钩子重置失败计数
        user.failed_login_attempts = 3
        service.on_authenticate_success(user)
        assert user.failed_login_attempts == 0

        # 失败钩子触发锁定
        service.on_authenticate_failure("alice", ip_address="127.0.0.1", reason="密码错误")
        service.on_authenticate_failure("alice", ip_address="127.0.0.1", reason="密码错误")
        assert user.is_locked is True


class TestSetupExtra:
    """setup 模块补充分支"""

    def test_detect_prefix_and_resolve_login_record_model(self):
        model_a = SimpleNamespace(__tablename__="sys_user")
        model_b = SimpleNamespace(__tablename__="user")
        model_c = SimpleNamespace(__tablename__="account")
        assert _detect_table_prefix(model_a) == "sys_"
        assert _detect_table_prefix(model_b) == ""
        assert _detect_table_prefix(model_c) == ""

        class DummyUser:
            __tablename__ = "sys_user"

        dynamic_cls = _resolve_login_record_model(True, DummyUser, None)
        assert dynamic_cls.__tablename__ == "sys_login_record"

        with pytest.raises(ValueError):
            _resolve_login_record_model("bad", DummyUser, None)

    def test_create_jwt_manager_and_user_getter(self):
        jwt1 = _create_jwt_manager(
            {
                "secret_key": "k",
                "algorithm": "HS256",
                "access_token_expire_minutes": 30,
                "refresh_token_expire_days": 7,
                "refresh_token_sliding_days": 2,
            }
        )
        assert jwt1.algorithm == "HS256"

        jwt2 = _create_jwt_manager(
            SimpleNamespace(
                secret_key="k2",
                algorithm="HS256",
                access_token_expire_minutes=10,
                refresh_token_expire_days=5,
                refresh_token_sliding_days=1,
            )
        )
        assert jwt2.secret_key == "k2"

        with pytest.raises(ValueError):
            _create_jwt_manager(123)

        class UM:
            @staticmethod
            def get(uid):
                if uid == 1:
                    return SimpleNamespace(id=1, is_active=True)
                if uid == 2:
                    return SimpleNamespace(id=2, is_active=False)
                return None

        user_getter, cached = _create_user_getter(UM, active_field="is_active", cache_ttl=0)
        assert cached is None
        assert user_getter(1).id == 1
        assert user_getter(2) is None
        assert user_getter(3) is None

        # 关闭活跃状态检查时，inactive 用户也返回
        user_getter2, _ = _create_user_getter(UM, active_field=None, cache_ttl=0)
        assert user_getter2(2).id == 2

    def test_create_auth_dependencies(self):
        class J:
            @staticmethod
            def verify_token(token, raise_on_expired=False):
                _ = raise_on_expired
                if token == "good":
                    return SimpleNamespace(user_id=1, token_type="access")
                if token == "refresh":
                    return SimpleNamespace(user_id=1, token_type="refresh")
                return None

        def user_getter(uid):
            if uid == 1:
                return SimpleNamespace(id=1)
            return None

        dep_required, dep_optional = _create_auth_dependencies(J(), user_getter, "/auth/token")
        assert dep_required(token="good").id == 1
        assert dep_optional(token="good").id == 1
        assert dep_optional(token="bad") is None
        assert dep_optional(token=None) is None

        with pytest.raises(AuthenticationException):
            dep_required(token=None)
        with pytest.raises(AuthenticationException):
            dep_required(token="bad")
        with pytest.raises(AuthenticationException):
            dep_required(token="refresh")

    def test_authsetup_helpers(self):
        setup = AuthSetup(
            get_current_user=lambda: None,
            get_current_user_optional=lambda: None,
            jwt_manager=JWTManagerObj(),
            user_getter=lambda _u: None,
        )
        assert setup.invalidate_user_cache(1) is False
        assert setup.invalidate_users_cache([1, 2]) == 0
        assert setup.get_user_cache_stats() == {}

        with pytest.raises(RuntimeError):
            setup.create_auth_service()

    def test_authsetup_create_auth_service_success(self):
        setup = AuthSetup(
            get_current_user=lambda: None,
            get_current_user_optional=lambda: None,
            jwt_manager=JWTManagerObj(),
            user_getter=lambda _u: None,
            _user_model=UserModelObj,
        )
        svc = setup.create_auth_service()
        assert isinstance(svc, BaseAuthService)
