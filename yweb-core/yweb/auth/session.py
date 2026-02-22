"""Session 认证模块

提供传统的 Cookie-Session 认证方式。

支持功能：
- Session 创建和管理
- 多种存储后端（内存、Redis、数据库）
- Session 过期和续期
- 并发会话控制

使用示例:
    from yweb.auth.session import SessionManager, SessionAuthProvider
    
    # 创建 Session 管理器
    session_manager = SessionManager(
        secret_key="your-secret-key",
        expire_minutes=30,
    )
    
    # 创建会话
    session = session_manager.create_session(user_id=1)
    
    # 验证会话
    session = session_manager.get_session(session.session_id)
    
    # 在 FastAPI 中使用
    @app.post("/login")
    def login(response: Response):
        session = session_manager.create_session(user_id=1)
        response.set_cookie(
            key="session_id",
            value=session.session_id,
            httponly=True,
            secure=True,
        )
        return {"message": "Logged in"}
"""

import secrets
import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Optional, Any, Dict, List, Callable

from fastapi import Depends, HTTPException, status, Request, Response
from fastapi.security import APIKeyCookie

from .base import AuthProvider, AuthType, UserIdentity, AuthResult


@dataclass
class Session:
    """会话对象
    
    Attributes:
        session_id: 会话 ID
        user_id: 用户 ID
        created_at: 创建时间
        expires_at: 过期时间
        last_accessed_at: 最后访问时间
        ip_address: 客户端 IP
        user_agent: 客户端 User-Agent
        data: 会话数据
        is_active: 是否激活
    """
    session_id: str
    user_id: Any
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    expires_at: Optional[datetime] = None
    last_accessed_at: Optional[datetime] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    data: Dict[str, Any] = field(default_factory=dict)
    is_active: bool = True
    
    # MFA 状态
    mfa_verified: bool = False
    mfa_verified_at: Optional[datetime] = None
    
    def is_expired(self) -> bool:
        """检查是否过期"""
        if self.expires_at is None:
            return False
        return datetime.now(timezone.utc) > self.expires_at
    
    def is_valid(self) -> bool:
        """检查是否有效"""
        return self.is_active and not self.is_expired()
    
    def touch(self):
        """更新最后访问时间"""
        self.last_accessed_at = datetime.now(timezone.utc)
    
    def set_data(self, key: str, value: Any):
        """设置会话数据"""
        self.data[key] = value
    
    def get_data(self, key: str, default: Any = None) -> Any:
        """获取会话数据"""
        return self.data.get(key, default)
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "last_accessed_at": self.last_accessed_at.isoformat() if self.last_accessed_at else None,
            "ip_address": self.ip_address,
            "is_active": self.is_active,
            "mfa_verified": self.mfa_verified,
        }


def generate_session_id(length: int = 32) -> str:
    """生成会话 ID"""
    return secrets.token_urlsafe(length)


class SessionManager:
    """Session 管理器
    
    提供会话的创建、验证、续期和销毁功能。
    
    Args:
        secret_key: 密钥（用于签名）
        expire_minutes: 会话过期时间（分钟）
        max_sessions_per_user: 每用户最大会话数（0 表示不限制）
        auto_renew: 是否自动续期
        renew_threshold_minutes: 续期阈值（剩余时间少于此值时续期）
        cookie_name: Cookie 名称
    """
    
    def __init__(
        self,
        secret_key: str,
        expire_minutes: int = 30,
        max_sessions_per_user: int = 0,
        auto_renew: bool = True,
        renew_threshold_minutes: int = 10,
        cookie_name: str = "session_id",
    ):
        self.secret_key = secret_key
        self.expire_seconds = expire_minutes * 60
        self.max_sessions_per_user = max_sessions_per_user
        self.auto_renew = auto_renew
        self.renew_threshold_seconds = renew_threshold_minutes * 60
        self.cookie_name = cookie_name
        
        # 内存存储（默认，生产环境应替换为 Redis 或数据库）
        self._sessions: Dict[str, Session] = {}
        self._user_sessions: Dict[Any, List[str]] = {}  # user_id -> [session_ids]
        
        # 存储回调
        self._session_store: Optional[Callable[[Session], bool]] = None
        self._session_getter: Optional[Callable[[str], Optional[Session]]] = None
        self._session_deleter: Optional[Callable[[str], bool]] = None
        self._user_sessions_getter: Optional[Callable[[Any], List[Session]]] = None
    
    def set_stores(
        self,
        store: Callable[[Session], bool] = None,
        getter: Callable[[str], Optional[Session]] = None,
        deleter: Callable[[str], bool] = None,
        user_sessions_getter: Callable[[Any], List[Session]] = None,
    ) -> "SessionManager":
        """设置存储回调
        
        Args:
            store: 存储会话
            getter: 根据 session_id 获取会话
            deleter: 删除会话
            user_sessions_getter: 获取用户的所有会话
            
        Returns:
            self: 支持链式调用
        """
        if store:
            self._session_store = store
        if getter:
            self._session_getter = getter
        if deleter:
            self._session_deleter = deleter
        if user_sessions_getter:
            self._user_sessions_getter = user_sessions_getter
        return self
    
    def create_session(
        self,
        user_id: Any,
        ip_address: str = None,
        user_agent: str = None,
        data: Dict[str, Any] = None,
        expire_seconds: int = None,
    ) -> Session:
        """创建会话
        
        Args:
            user_id: 用户 ID
            ip_address: 客户端 IP
            user_agent: 客户端 User-Agent
            data: 会话数据
            expire_seconds: 自定义过期时间
            
        Returns:
            Session: 会话对象
        """
        # 检查并发会话限制
        if self.max_sessions_per_user > 0:
            self._enforce_session_limit(user_id)
        
        session_id = generate_session_id()
        expire_time = expire_seconds or self.expire_seconds
        
        now = datetime.now(timezone.utc)
        session = Session(
            session_id=session_id,
            user_id=user_id,
            created_at=now,
            expires_at=now + timedelta(seconds=expire_time),
            last_accessed_at=now,
            ip_address=ip_address,
            user_agent=user_agent,
            data=data or {},
        )
        
        # 保存
        self._save_session(session)
        
        # 记录用户会话
        if user_id not in self._user_sessions:
            self._user_sessions[user_id] = []
        self._user_sessions[user_id].append(session_id)
        
        return session
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            Session: 会话对象，或 None
        """
        session = self._get_session(session_id)
        
        if not session:
            return None
        
        if not session.is_valid():
            self.destroy_session(session_id)
            return None
        
        # 更新访问时间
        session.touch()
        
        # 自动续期
        if self.auto_renew and session.expires_at:
            remaining = (session.expires_at - datetime.now(timezone.utc)).total_seconds()
            if remaining < self.renew_threshold_seconds:
                session.expires_at = datetime.now(timezone.utc) + timedelta(seconds=self.expire_seconds)
        
        self._save_session(session)
        return session
    
    def validate_session(self, session_id: str) -> tuple:
        """验证会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            tuple: (is_valid, session_or_error)
        """
        session = self.get_session(session_id)
        
        if not session:
            return False, "Session not found or expired"
        
        return True, session
    
    def destroy_session(self, session_id: str) -> bool:
        """销毁会话
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否成功
        """
        session = self._get_session(session_id)
        if session:
            # 从用户会话列表中移除
            if session.user_id in self._user_sessions:
                if session_id in self._user_sessions[session.user_id]:
                    self._user_sessions[session.user_id].remove(session_id)
        
        return self._delete_session(session_id)
    
    def destroy_all_sessions(self, user_id: Any) -> int:
        """销毁用户的所有会话
        
        Args:
            user_id: 用户 ID
            
        Returns:
            int: 销毁的会话数量
        """
        sessions = self.get_user_sessions(user_id)
        count = 0
        
        for session in sessions:
            if self.destroy_session(session.session_id):
                count += 1
        
        return count
    
    def get_user_sessions(self, user_id: Any) -> List[Session]:
        """获取用户的所有会话
        
        Args:
            user_id: 用户 ID
            
        Returns:
            List[Session]: 会话列表
        """
        if self._user_sessions_getter:
            return self._user_sessions_getter(user_id)
        
        session_ids = self._user_sessions.get(user_id, [])
        sessions = []
        
        for session_id in session_ids:
            session = self._get_session(session_id)
            if session and session.is_valid():
                sessions.append(session)
        
        return sessions
    
    def set_mfa_verified(self, session_id: str) -> bool:
        """标记会话已通过 MFA 验证
        
        Args:
            session_id: 会话 ID
            
        Returns:
            bool: 是否成功
        """
        session = self._get_session(session_id)
        if not session:
            return False
        
        session.mfa_verified = True
        session.mfa_verified_at = datetime.now(timezone.utc)
        return self._save_session(session)
    
    def _enforce_session_limit(self, user_id: Any):
        """强制执行会话数量限制"""
        sessions = self.get_user_sessions(user_id)
        
        if len(sessions) >= self.max_sessions_per_user:
            # 销毁最旧的会话
            sessions.sort(key=lambda s: s.created_at)
            excess = len(sessions) - self.max_sessions_per_user + 1
            for i in range(excess):
                self.destroy_session(sessions[i].session_id)
    
    def _save_session(self, session: Session) -> bool:
        """保存会话"""
        if self._session_store:
            return self._session_store(session)
        self._sessions[session.session_id] = session
        return True
    
    def _get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        if self._session_getter:
            return self._session_getter(session_id)
        return self._sessions.get(session_id)
    
    def _delete_session(self, session_id: str) -> bool:
        """删除会话"""
        if self._session_deleter:
            return self._session_deleter(session_id)
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False
    
    def create_dependency(
        self,
        user_getter: Callable[[Any], Optional[Any]],
        auto_error: bool = True,
        require_mfa: bool = False,
    ) -> Callable:
        """创建 FastAPI 依赖
        
        Args:
            user_getter: 根据 user_id 获取用户的函数
            auto_error: 认证失败是否自动抛出异常
            require_mfa: 是否要求 MFA 验证
            
        Returns:
            FastAPI 依赖函数
        """
        cookie_scheme = APIKeyCookie(name=self.cookie_name, auto_error=False)
        
        async def get_current_user(
            request: Request,
            session_id: Optional[str] = Depends(cookie_scheme),
        ):
            if not session_id:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="Not authenticated",
                    )
                return None
            
            # 验证会话
            is_valid, result = self.validate_session(session_id)
            if not is_valid:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=result,
                    )
                return None
            
            session = result
            
            # 检查 MFA
            if require_mfa and not session.mfa_verified:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_403_FORBIDDEN,
                        detail="MFA verification required",
                    )
                return None
            
            # 获取用户
            user = user_getter(session.user_id)
            if not user:
                if auto_error:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail="User not found",
                    )
                return None
            
            # 将会话附加到 request.state
            request.state.session = session
            
            return user
        
        return get_current_user


class SessionAuthProvider(AuthProvider):
    """Session 认证提供者
    
    实现 AuthProvider 接口，用于统一认证管理。
    """
    
    def __init__(
        self,
        session_manager: SessionManager,
        user_getter: Callable[[Any], Optional[Any]] = None,
    ):
        self.session_manager = session_manager
        self.user_getter = user_getter
    
    @property
    def auth_type(self) -> AuthType:
        return AuthType.SESSION
    
    def authenticate(self, credentials: Any) -> AuthResult:
        """验证凭证并创建会话
        
        credentials 应该是一个包含已验证用户信息的字典：
        {
            "user_id": 1,
            "ip_address": "127.0.0.1",
            "user_agent": "Mozilla/5.0...",
        }
        """
        if not isinstance(credentials, dict):
            return AuthResult.fail("Invalid credentials format", "INVALID_CREDENTIALS")
        
        user_id = credentials.get("user_id")
        if not user_id:
            return AuthResult.fail("User ID required", "USER_ID_REQUIRED")
        
        # 创建会话
        session = self.session_manager.create_session(
            user_id=user_id,
            ip_address=credentials.get("ip_address"),
            user_agent=credentials.get("user_agent"),
            data=credentials.get("data"),
        )
        
        # 获取用户信息
        user = None
        username = str(user_id)
        email = None
        roles = []
        
        if self.user_getter:
            user = self.user_getter(user_id)
            if user:
                username = getattr(user, "username", str(user_id))
                email = getattr(user, "email", None)
                roles = getattr(user, "roles", [])
        
        identity = UserIdentity(
            user_id=user_id,
            username=username,
            email=email,
            roles=roles,
            auth_type=AuthType.SESSION,
            session_id=session.session_id,
        )
        
        return AuthResult.ok(
            identity,
            session_id=session.session_id,
            expires_at=session.expires_at.isoformat() if session.expires_at else None,
        )
    
    def validate_token(self, token: str) -> AuthResult:
        """验证会话"""
        is_valid, result = self.session_manager.validate_session(token)
        
        if not is_valid:
            return AuthResult.fail(result, "INVALID_SESSION")
        
        session = result
        
        # 获取用户信息
        user = None
        username = str(session.user_id)
        email = None
        roles = []
        
        if self.user_getter:
            user = self.user_getter(session.user_id)
            if user:
                username = getattr(user, "username", str(session.user_id))
                email = getattr(user, "email", None)
                roles = getattr(user, "roles", [])
        
        identity = UserIdentity(
            user_id=session.user_id,
            username=username,
            email=email,
            roles=roles,
            auth_type=AuthType.SESSION,
            session_id=session.session_id,
            mfa_verified=session.mfa_verified,
        )
        
        return AuthResult.ok(identity)
    
    def revoke_token(self, token: str) -> bool:
        """销毁会话"""
        return self.session_manager.destroy_session(token)
    
    def logout(self, identity: UserIdentity) -> bool:
        """登出"""
        if identity.session_id:
            return self.session_manager.destroy_session(identity.session_id)
        return False


def set_session_cookie(
    response: Response,
    session: Session,
    cookie_name: str = "session_id",
    httponly: bool = True,
    secure: bool = True,
    samesite: str = "lax",
    path: str = "/",
):
    """设置会话 Cookie
    
    Args:
        response: FastAPI Response 对象
        session: 会话对象
        cookie_name: Cookie 名称
        httponly: 是否 HttpOnly
        secure: 是否仅 HTTPS
        samesite: SameSite 属性
        path: Cookie 路径
    """
    max_age = None
    if session.expires_at:
        remaining = session.expires_at - datetime.now(timezone.utc)
        max_age = int(remaining.total_seconds())
    
    response.set_cookie(
        key=cookie_name,
        value=session.session_id,
        httponly=httponly,
        secure=secure,
        samesite=samesite,
        path=path,
        max_age=max_age,
    )


def clear_session_cookie(
    response: Response,
    cookie_name: str = "session_id",
    path: str = "/",
):
    """清除会话 Cookie
    
    Args:
        response: FastAPI Response 对象
        cookie_name: Cookie 名称
        path: Cookie 路径
    """
    response.delete_cookie(
        key=cookie_name,
        path=path,
    )
