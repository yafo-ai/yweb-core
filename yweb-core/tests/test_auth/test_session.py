"""Session 认证模块测试

测试 Session 的创建、验证、销毁和管理功能
"""

import pytest
from datetime import datetime, timezone, timedelta
from fastapi import FastAPI, Depends, Response
from fastapi.testclient import TestClient

from yweb.auth.session import (
    Session,
    SessionManager,
    SessionAuthProvider,
    set_session_cookie,
    clear_session_cookie,
)
from yweb.auth.base import AuthType


class TestSession:
    """Session 数据类测试"""
    
    def test_create_session(self):
        """测试创建 Session 对象"""
        session = Session(
            session_id="test-session-id",
            user_id=1,
        )
        
        assert session.session_id == "test-session-id"
        assert session.user_id == 1
        assert session.is_active is True
        assert session.mfa_verified is False
    
    def test_session_expiry(self):
        """测试 Session 过期检测"""
        # 未过期
        session = Session(
            session_id="test",
            user_id=1,
            expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
        assert session.is_expired() is False
        assert session.is_valid() is True
        
        # 已过期
        expired_session = Session(
            session_id="test",
            user_id=1,
            expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        )
        assert expired_session.is_expired() is True
        assert expired_session.is_valid() is False
    
    def test_session_data(self):
        """测试 Session 数据存取"""
        session = Session(session_id="test", user_id=1)
        
        session.set_data("key1", "value1")
        session.set_data("key2", {"nested": "data"})
        
        assert session.get_data("key1") == "value1"
        assert session.get_data("key2") == {"nested": "data"}
        assert session.get_data("nonexistent", "default") == "default"


class TestSessionManager:
    """SessionManager 测试"""
    
    @pytest.fixture
    def session_manager(self):
        """创建独立的 Session 管理器（每个测试隔离）"""
        return SessionManager(
            secret_key="test-secret-key",
            expire_minutes=30,
            max_sessions_per_user=3,
        )
    
    def test_create_session(self, session_manager):
        """测试创建 Session"""
        session = session_manager.create_session(
            user_id=1,
            ip_address="127.0.0.1",
        )
        
        assert session is not None
        assert session.user_id == 1
        assert session.ip_address == "127.0.0.1"
        assert session.is_active is True
    
    def test_get_session(self, session_manager):
        """测试获取 Session"""
        session = session_manager.create_session(user_id=1)
        
        retrieved = session_manager.get_session(session.session_id)
        
        assert retrieved is not None
        assert retrieved.session_id == session.session_id
        assert retrieved.user_id == 1
    
    def test_get_nonexistent_session(self, session_manager):
        """测试获取不存在的 Session"""
        result = session_manager.get_session("nonexistent-session-id")
        assert result is None
    
    def test_validate_session(self, session_manager):
        """测试验证 Session"""
        session = session_manager.create_session(user_id=1)
        
        is_valid, result = session_manager.validate_session(session.session_id)
        
        assert is_valid is True
        assert result.session_id == session.session_id

    def test_validate_expired_session(self, session_manager):
        """测试过期 Session 验证失败并被清理"""
        session = session_manager.create_session(user_id=1, expire_seconds=-1)
        is_valid, result = session_manager.validate_session(session.session_id)
        assert is_valid is False
        assert result == "Session not found or expired"
        assert session_manager.get_session(session.session_id) is None
    
    def test_destroy_session(self, session_manager):
        """测试销毁 Session"""
        session = session_manager.create_session(user_id=1)
        
        result = session_manager.destroy_session(session.session_id)
        
        assert result is True
        assert session_manager.get_session(session.session_id) is None
    
    def test_destroy_all_sessions(self, session_manager):
        """测试销毁用户所有 Session"""
        session_manager.create_session(user_id=1)
        session_manager.create_session(user_id=1)
        session_manager.create_session(user_id=1)
        
        count = session_manager.destroy_all_sessions(user_id=1)
        
        assert count == 3
        assert len(session_manager.get_user_sessions(user_id=1)) == 0
    
    def test_max_sessions_per_user(self, session_manager):
        """测试每用户最大 Session 数限制"""
        # 创建超过限制的 Session
        for i in range(5):
            session_manager.create_session(user_id=1)
        
        sessions = session_manager.get_user_sessions(user_id=1)
        
        # 应该只保留最近的 3 个
        assert len(sessions) == 3
    
    def test_set_mfa_verified(self, session_manager):
        """测试设置 MFA 验证状态"""
        session = session_manager.create_session(user_id=1)
        assert session.mfa_verified is False
        
        session_manager.set_mfa_verified(session.session_id)
        
        session = session_manager.get_session(session.session_id)
        assert session.mfa_verified is True
        assert session.mfa_verified_at is not None

    def test_set_mfa_verified_nonexistent_session(self, session_manager):
        """测试对不存在 Session 标记 MFA"""
        assert session_manager.set_mfa_verified("nonexistent") is False


class TestSessionAuthProvider:
    """SessionAuthProvider 测试"""
    
    @pytest.fixture
    def provider(self, mock_user):
        """创建独立的 Provider"""
        manager = SessionManager(secret_key="test-secret")
        
        def user_getter(user_id):
            if user_id == 1:
                return mock_user(id=1, username="testuser")
            return None
        
        return SessionAuthProvider(
            session_manager=manager,
            user_getter=user_getter,
        ), manager
    
    def test_auth_type(self, provider):
        """测试认证类型"""
        auth_provider, _ = provider
        assert auth_provider.auth_type == AuthType.SESSION
    
    def test_authenticate_success(self, provider):
        """测试认证成功（创建会话）"""
        auth_provider, _ = provider
        
        result = auth_provider.authenticate({
            "user_id": 1,
            "ip_address": "127.0.0.1",
        })
        
        assert result.success is True
        assert result.identity.user_id == 1
        assert result.extra.get("session_id") is not None
    
    def test_validate_token_success(self, provider):
        """测试验证会话 Token"""
        auth_provider, manager = provider
        session = manager.create_session(user_id=1)
        
        result = auth_provider.validate_token(session.session_id)
        
        assert result.success is True
        assert result.identity.user_id == 1
    
    def test_logout(self, provider):
        """测试登出"""
        auth_provider, manager = provider
        session = manager.create_session(user_id=1)
        
        # 创建 identity
        result = auth_provider.validate_token(session.session_id)
        
        # 登出
        success = auth_provider.logout(result.identity)
        
        assert success is True
        assert manager.get_session(session.session_id) is None

    def test_authenticate_invalid_credentials_type(self, provider):
        """测试认证凭证类型错误"""
        auth_provider, _ = provider
        result = auth_provider.authenticate("invalid")
        assert result.success is False
        assert result.error_code == "INVALID_CREDENTIALS"

    def test_authenticate_missing_user_id(self, provider):
        """测试认证缺少 user_id"""
        auth_provider, _ = provider
        result = auth_provider.authenticate({"ip_address": "127.0.0.1"})
        assert result.success is False
        assert result.error_code == "USER_ID_REQUIRED"

    def test_validate_token_invalid_session(self, provider):
        """测试验证不存在 Session"""
        auth_provider, _ = provider
        result = auth_provider.validate_token("not-exist")
        assert result.success is False
        assert result.error_code == "INVALID_SESSION"


class TestSessionFastAPIIntegration:
    """Session FastAPI 集成测试"""
    
    @pytest.fixture
    def session_app(self, mock_user):
        """创建带 Session 认证的测试应用"""
        manager = SessionManager(secret_key="test-secret", expire_minutes=30)
        
        def user_getter(user_id):
            if user_id == 1:
                return mock_user(id=1, username="testuser")
            return None
        
        get_session_user = manager.create_dependency(user_getter=user_getter)
        
        app = FastAPI()
        
        @app.post("/login")
        def login(response: Response):
            session = manager.create_session(user_id=1)
            set_session_cookie(response, session)
            return {"message": "logged in", "session_id": session.session_id}
        
        @app.get("/me")
        def get_me(user=Depends(get_session_user)):
            return {"username": user.username}
        
        @app.post("/logout")
        def logout(response: Response):
            clear_session_cookie(response)
            return {"message": "logged out"}
        
        return app, manager
    
    def test_login_sets_cookie(self, session_app):
        """测试登录设置 Cookie"""
        app, _ = session_app
        client = TestClient(app)
        
        response = client.post("/login")
        
        assert response.status_code == 200
        assert "session_id" in response.cookies
    
    def test_authenticated_request(self, session_app):
        """测试认证请求"""
        app, manager = session_app
        
        # 直接创建 session 并使用
        session = manager.create_session(user_id=1)
        
        client = TestClient(app, cookies={"session_id": session.session_id})
        
        # 访问受保护的接口
        response = client.get("/me")
        
        assert response.status_code == 200
        assert response.json()["username"] == "testuser"
    
    def test_unauthenticated_request(self, session_app):
        """测试未认证请求"""
        app, _ = session_app
        client = TestClient(app)
        
        response = client.get("/me")
        
        assert response.status_code == 401

    def test_logout_clears_cookie(self, session_app):
        """测试登出接口清理 Cookie"""
        app, _ = session_app
        client = TestClient(app)
        response = client.post("/logout")
        assert response.status_code == 200
        set_cookie_header = response.headers.get("set-cookie", "")
        assert "session_id=" in set_cookie_header.lower()
