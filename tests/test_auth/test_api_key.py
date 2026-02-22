"""API Key 认证模块测试

测试 API Key 的生成、验证、授权与 FastAPI 集成行为。
"""

import hmac
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pytest
from fastapi import Depends, FastAPI, Request
from fastapi.testclient import TestClient

from yweb.auth.api_key import APIKeyAuthProvider, APIKeyData, APIKeyManager, get_api_key_from_request
from yweb.auth.base import AuthType


def build_manual_key_and_data(
    manager: APIKeyManager,
    *,
    key_id: str,
    user_id: int = 1,
    scopes: Optional[List[str]] = None,
    is_active: bool = True,
    expires_at: Optional[datetime] = None,
) -> Tuple[str, APIKeyData]:
    """构造一个可预测的 API Key 与其存储数据。"""
    full_key = f"{manager.prefix}_{key_id}_manual-random-part"
    key_hash = hmac.new(
        manager.secret_key.encode(),
        full_key.encode(),
        manager.hash_algorithm,
    ).hexdigest()
    key_data = APIKeyData(
        key=full_key,
        key_id=key_id,
        key_hash=key_hash,
        user_id=user_id,
        scopes=scopes or [],
        is_active=is_active,
        expires_at=expires_at,
    )
    return full_key, key_data


class TestAPIKeyManager:
    """APIKeyManager 测试"""

    @pytest.fixture
    def manager_and_storage(self):
        """创建独立的 API Key 管理器与可观测存储。"""
        manager = APIKeyManager(
            secret_key="test-secret-key",
            prefix="test",
            key_length=16,
        )

        storage = {"by_hash": {}, "by_id": {}}
        updates = []

        def getter(key_or_hash):
            return storage["by_hash"].get(key_or_hash) or storage["by_id"].get(key_or_hash)

        def saver(data):
            storage["by_hash"][data.key_hash] = data
            storage["by_id"][data.key_id] = data
            return True

        def updater(key_id, fields):
            target = storage["by_id"].get(key_id)
            if not target:
                return False
            for field_name, value in fields.items():
                setattr(target, field_name, value)
            updates.append((key_id, fields))
            return True

        def revoker(key_id):
            target = storage["by_id"].get(key_id)
            if not target:
                return False
            target.is_active = False
            return True

        manager.set_key_store(
            getter=getter,
            saver=saver,
            updater=updater,
            revoker=revoker,
        )
        return manager, storage, updates

    def test_generate_key(self, manager_and_storage):
        """测试生成 API Key"""
        manager, _, _ = manager_and_storage
        key_data = manager.generate_key(
            user_id=1,
            name="Test Key",
            scopes=["read", "write"],
        )
        
        assert key_data.key is not None
        assert key_data.key.startswith("test_")
        assert key_data.user_id == 1
        assert key_data.name == "Test Key"
        assert key_data.scopes == ["read", "write"]
        assert key_data.is_active is True

    def test_generate_key_with_expiry(self, manager_and_storage):
        """测试生成带过期时间的 API Key"""
        manager, _, _ = manager_and_storage
        key_data = manager.generate_key(
            user_id=1,
            name="Expiring Key",
            expires_days=30,
        )
        
        assert key_data.expires_at is not None
        assert key_data.is_expired() is False

    def test_validate_key_format(self, manager_and_storage):
        """测试验证 Key 格式"""
        manager, _, _ = manager_and_storage
        full_key, _ = build_manual_key_and_data(manager, key_id="fmt01")

        is_valid, key_id = manager.validate_key_format(full_key)
        assert is_valid is True, f"key={full_key}, prefix={manager.prefix}"
        assert key_id == "fmt01"

    def test_validate_invalid_key_format(self, manager_and_storage):
        """测试验证无效 Key 格式"""
        manager, _, _ = manager_and_storage
        is_valid, _ = manager.validate_key_format("invalid-key")
        assert is_valid is False

        is_valid, _ = manager.validate_key_format("wrong_prefix_xxx_yyy")
        assert is_valid is False

    def test_validate_key_with_pre_stored_data(self, manager_and_storage):
        """测试验证预置存储中的 API Key（避免同源自证）。"""
        manager, storage, _ = manager_and_storage
        full_key, key_data = build_manual_key_and_data(manager, key_id="valid01", scopes=["read"])
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        validated = manager.validate_key(full_key)
        assert validated is not None
        assert validated.user_id == 1
        assert validated.scopes == ["read"]

    def test_validate_key_rejects_tampered_key(self, manager_and_storage):
        """测试同 key_id 下随机串被篡改会验证失败。"""
        manager, storage, _ = manager_and_storage
        full_key, key_data = build_manual_key_and_data(manager, key_id="tamper01", scopes=["read"])
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        tampered = full_key.replace("manual-random-part", "tampered-part")
        assert manager.validate_key(tampered) is None

    def test_validate_key_rejects_inactive_key(self, manager_and_storage):
        """测试禁用的 API Key 会被拒绝。"""
        manager, storage, _ = manager_and_storage
        full_key, key_data = build_manual_key_and_data(
            manager,
            key_id="inactive01",
            scopes=["read"],
            is_active=False,
        )
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        assert manager.validate_key(full_key) is None

    def test_validate_key_rejects_expired_key(self, manager_and_storage):
        """测试过期的 API Key 会被拒绝。"""
        manager, storage, _ = manager_and_storage
        full_key, key_data = build_manual_key_and_data(
            manager,
            key_id="expired01",
            scopes=["read"],
            expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        )
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        assert manager.validate_key(full_key) is None

    def test_validate_key_updates_last_used_at(self, manager_and_storage):
        """测试验证成功后会更新最后使用时间。"""
        manager, storage, updates = manager_and_storage
        full_key, key_data = build_manual_key_and_data(manager, key_id="update01", scopes=["read"])
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        assert key_data.last_used_at is None
        validated = manager.validate_key(full_key)
        assert validated is not None
        assert validated.last_used_at is not None
        assert len(updates) == 1
        assert updates[0][0] == "update01"
        assert "last_used_at" in updates[0][1]

    def test_validate_nonexistent_key(self, manager_and_storage):
        """测试验证不存在的 Key"""
        manager, _, _ = manager_and_storage
        result = manager.validate_key("test_fake_keyid_randompart")
        assert result is None

    def test_revoke_key(self, manager_and_storage):
        """测试撤销 Key 后不可再通过验证。"""
        manager, storage, _ = manager_and_storage
        full_key, key_data = build_manual_key_and_data(manager, key_id="revoke01", scopes=["read"])
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        assert manager.revoke_key("revoke01") is True
        assert manager.validate_key(full_key) is None

    def test_key_scopes(self, manager_and_storage):
        """测试 Key 权限范围"""
        manager, _, _ = manager_and_storage
        _, key_data = build_manual_key_and_data(manager, key_id="scope01", scopes=["read", "write"])

        assert key_data.has_scope("read") is True
        assert key_data.has_scope("write") is True
        assert key_data.has_scope("delete") is False
        assert key_data.has_any_scope(["read", "delete"]) is True

    def test_wildcard_scope(self, manager_and_storage):
        """测试通配符权限"""
        manager, _, _ = manager_and_storage
        _, key_data = build_manual_key_and_data(manager, key_id="wild01", scopes=["*"])

        assert key_data.has_scope("anything") is True
        assert key_data.has_any_scope(["read", "write", "delete"]) is True


class TestAPIKeyAuthProvider:
    """APIKeyAuthProvider 测试"""

    @pytest.fixture
    def provider(self, mock_user):
        """创建独立的 Provider"""
        manager = APIKeyManager(secret_key="test-secret", prefix="test")

        storage = {"by_hash": {}, "by_id": {}}

        def getter(key_or_hash):
            return storage["by_hash"].get(key_or_hash) or storage["by_id"].get(key_or_hash)

        def saver(data):
            storage["by_hash"][data.key_hash] = data
            storage["by_id"][data.key_id] = data
            return True

        def revoker(key_id):
            target = storage["by_id"].get(key_id)
            if not target:
                return False
            target.is_active = False
            return True

        manager.set_key_store(getter=getter, saver=saver, revoker=revoker)

        def user_getter(user_id):
            if user_id == 1:
                return mock_user(id=1, username="testuser", email="test@example.com")
            return None

        return APIKeyAuthProvider(
            api_key_manager=manager,
            user_getter=user_getter,
        ), manager, storage

    def test_auth_type(self, provider):
        """测试认证类型"""
        auth_provider, _, _ = provider
        assert auth_provider.auth_type == AuthType.API_KEY

    def test_authenticate_success(self, provider):
        """测试认证成功（基于预置 Key 数据）。"""
        auth_provider, manager, storage = provider
        full_key, key_data = build_manual_key_and_data(
            manager,
            key_id="authok01",
            user_id=1,
            scopes=["read"],
        )
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        result = auth_provider.authenticate(full_key)
        assert result.success is True
        assert result.identity.user_id == 1
        assert result.identity.username == "testuser"
        assert result.identity.auth_type == AuthType.API_KEY
        assert result.identity.permissions == ["read"]

    def test_authenticate_invalid_key(self, provider):
        """测试无效 Key 认证"""
        auth_provider, _, _ = provider

        result = auth_provider.authenticate("invalid-key")
        assert result.success is False
        assert result.error_code == "INVALID_API_KEY"

    def test_authenticate_with_dict_credentials(self, provider):
        """测试字典格式凭证"""
        auth_provider, manager, storage = provider
        full_key, key_data = build_manual_key_and_data(manager, key_id="dict01", user_id=1)
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        result = auth_provider.authenticate({"api_key": full_key})
        assert result.success is True

    def test_authenticate_missing_api_key(self, provider):
        """测试字典凭证缺少 api_key 字段。"""
        auth_provider, _, _ = provider
        result = auth_provider.authenticate({})
        assert result.success is False
        assert result.error_code == "API_KEY_REQUIRED"

    def test_authenticate_invalid_credentials_type(self, provider):
        """测试不支持的凭证类型。"""
        auth_provider, _, _ = provider
        result = auth_provider.authenticate(12345)
        assert result.success is False
        assert result.error_code == "INVALID_CREDENTIALS"

    def test_authenticate_user_not_found(self, provider):
        """测试 Key 合法但用户不存在。"""
        auth_provider, manager, storage = provider
        full_key, key_data = build_manual_key_and_data(manager, key_id="nouser01", user_id=999)
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        result = auth_provider.authenticate(full_key)
        assert result.success is False
        assert result.error_code == "USER_NOT_FOUND"

    def test_revoke_token(self, provider):
        """测试通过 provider 撤销 token。"""
        auth_provider, manager, storage = provider
        full_key, key_data = build_manual_key_and_data(manager, key_id="revoke02", user_id=1)
        storage["by_hash"][key_data.key_hash] = key_data
        storage["by_id"][key_data.key_id] = key_data

        assert auth_provider.revoke_token(full_key) is True
        result = auth_provider.authenticate(full_key)
        assert result.success is False
        assert result.error_code == "INVALID_API_KEY"


class TestAPIKeyFastAPIIntegration:
    """API Key FastAPI 集成测试"""

    @pytest.fixture
    def api_key_app(self, mock_user):
        """创建带 API Key 认证的测试应用"""
        manager = APIKeyManager(secret_key="test-secret", prefix="test")
        storage = {"by_hash": {}, "by_id": {}}

        def getter(key_or_hash):
            return storage["by_hash"].get(key_or_hash) or storage["by_id"].get(key_or_hash)

        def saver(data):
            storage["by_hash"][data.key_hash] = data
            storage["by_id"][data.key_id] = data
            return True

        manager.set_key_store(getter=getter, saver=saver)

        read_key, read_key_data = build_manual_key_and_data(
            manager,
            key_id="read01",
            user_id=1,
            scopes=["read"],
        )
        storage["by_hash"][read_key_data.key_hash] = read_key_data
        storage["by_id"][read_key_data.key_id] = read_key_data

        write_key, write_key_data = build_manual_key_and_data(
            manager,
            key_id="write01",
            user_id=1,
            scopes=["write"],
        )
        storage["by_hash"][write_key_data.key_hash] = write_key_data
        storage["by_id"][write_key_data.key_id] = write_key_data

        def user_getter(user_id):
            if user_id == 1:
                return mock_user(id=1, username="testuser")
            return None

        get_read_user = manager.create_dependency(
            user_getter=user_getter,
            header_name="X-API-Key",
            required_scopes=["read"],
        )
        get_write_user = manager.create_dependency(
            user_getter=user_getter,
            header_name="X-API-Key",
            required_scopes=["write"],
        )
        get_optional_user = manager.create_dependency(
            user_getter=user_getter,
            header_name="X-API-Key",
            cookie_name="api_key_cookie",
            auto_error=False,
        )

        app = FastAPI()

        @app.get("/read-data")
        def get_read_data(user=Depends(get_read_user)):
            return {"user": user.username}

        @app.get("/write-data")
        def get_write_data(user=Depends(get_write_user)):
            return {"user": user.username}

        @app.get("/optional-data")
        def get_optional_data(user=Depends(get_optional_user)):
            if user is None:
                return {"guest": True}
            return {"guest": False, "user": user.username}

        @app.get("/extract")
        async def extract_api_key(request: Request):
            return {"api_key": get_api_key_from_request(request, cookie_name="api_key_cookie")}

        return app, {"read": read_key, "write": write_key}

    def test_api_key_header_auth(self, api_key_app):
        """测试通过 Header 认证"""
        app, api_keys = api_key_app
        client = TestClient(app)

        response = client.get("/read-data", headers={"X-API-Key": api_keys["read"]})

        assert response.status_code == 200
        assert response.json()["user"] == "testuser"

    def test_api_key_query_auth(self, api_key_app):
        """测试通过 Query 参数认证"""
        app, api_keys = api_key_app
        client = TestClient(app)

        response = client.get(f"/read-data?api_key={api_keys['read']}")

        assert response.status_code == 200

    def test_missing_api_key_returns_401(self, api_key_app):
        """测试缺少 API Key"""
        app, _ = api_key_app
        client = TestClient(app)

        response = client.get("/read-data")

        assert response.status_code == 401
        assert response.json()["detail"] == "API Key required"

    def test_invalid_api_key_returns_401(self, api_key_app):
        """测试无效 API Key。"""
        app, _ = api_key_app
        client = TestClient(app)
        response = client.get("/read-data", headers={"X-API-Key": "test_invalid_xxx"})
        assert response.status_code == 401
        assert response.json()["detail"] == "Invalid or expired API Key"

    def test_insufficient_scope_returns_403(self, api_key_app):
        """测试权限不足返回 403。"""
        app, api_keys = api_key_app
        client = TestClient(app)
        response = client.get("/read-data", headers={"X-API-Key": api_keys["write"]})
        assert response.status_code == 403
        assert "required scopes" in response.json()["detail"]

    def test_header_has_priority_over_query(self, api_key_app):
        """测试 Header 优先于 Query 参数。"""
        app, api_keys = api_key_app
        client = TestClient(app)
        response = client.get(
            f"/read-data?api_key=test_invalid_xxx",
            headers={"X-API-Key": api_keys["read"]},
        )
        assert response.status_code == 200

    def test_cookie_auth_when_header_absent(self, api_key_app):
        """测试 Header 缺失时可从 Cookie 读取。"""
        app, api_keys = api_key_app
        client = TestClient(app)
        response = client.get(
            "/optional-data",
            cookies={"api_key_cookie": api_keys["read"]},
        )
        assert response.status_code == 200
        assert response.json()["guest"] is False
        assert response.json()["user"] == "testuser"

    def test_auto_error_false_returns_guest(self, api_key_app):
        """测试 auto_error=False 时缺失凭证不抛错。"""
        app, _ = api_key_app
        client = TestClient(app)
        response = client.get("/optional-data")
        assert response.status_code == 200
        assert response.json() == {"guest": True}

    def test_get_api_key_from_request_priority(self, api_key_app):
        """测试提取优先级：Header > Query > Cookie。"""
        app, api_keys = api_key_app
        client = TestClient(app)
        response = client.get(
            f"/extract?api_key=test_query_key",
            headers={"X-API-Key": api_keys["read"]},
            cookies={"api_key_cookie": "test_cookie_key"},
        )
        assert response.status_code == 200
        assert response.json()["api_key"] == api_keys["read"]
