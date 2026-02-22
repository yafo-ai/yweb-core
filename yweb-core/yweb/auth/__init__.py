"""认证模块

提供多种认证方式的实现，包括：
- JWT Token 认证
- API Key 认证
- OAuth 2.0 认证
- OpenID Connect (OIDC)
- Session 认证
- LDAP/Active Directory 认证
- 多因素认证 (MFA/2FA)

使用示例:

1. JWT 认证（原有功能）:
    from yweb.auth import JWTManager, TokenPayload, create_auth_dependency
    
    jwt_manager = JWTManager(secret_key="your-secret-key")
    get_current_user = create_auth_dependency(jwt_manager, user_getter=get_user)
    
    @app.get("/me")
    def get_me(user = Depends(get_current_user)):
        return user

2. API Key 认证:
    from yweb.auth import APIKeyManager, APIKeyAuthProvider
    
    api_key_manager = APIKeyManager(secret_key="your-secret-key", prefix="yweb")
    key_data = api_key_manager.generate_key(user_id=1, name="My Key")
    
    get_api_key_user = api_key_manager.create_dependency(user_getter=get_user)
    
    @app.get("/api/data")
    def get_data(user = Depends(get_api_key_user)):
        return {"user": user.username}

3. OAuth 2.0 认证:
    from yweb.auth.oauth2 import OAuth2Manager
    from yweb.auth.api import create_oauth2_router
    
    oauth2_manager = OAuth2Manager(secret_key="your-secret-key")
    router = create_oauth2_router(oauth2_manager)
    app.include_router(router, prefix="/oauth2")

4. OIDC 认证:
    from yweb.auth.oidc import OIDCManager
    from yweb.auth.api import create_oidc_router
    
    oidc_manager = OIDCManager(issuer="https://sso.example.com", secret_key="xxx")
    router = create_oidc_router(oidc_manager)
    app.include_router(router)

5. Session 认证:
    from yweb.auth import SessionManager, set_session_cookie
    
    session_manager = SessionManager(secret_key="your-secret-key")
    
    @app.post("/login")
    def login(response: Response, username: str, password: str):
        user = authenticate_user(username, password)
        session = session_manager.create_session(user_id=user.id)
        set_session_cookie(response, session)
        return {"message": "Logged in"}

6. LDAP/AD 认证:
    from yweb.auth import LDAPManager, LDAPAuthProvider
    
    ldap_manager = LDAPManager(
        server="ldap://ldap.example.com:389",
        base_dn="dc=example,dc=com",
    )
    result, user = ldap_manager.authenticate("john", "password")

7. MFA/2FA:
    from yweb.auth.mfa import MFAManager, TOTPProvider
    
    totp_provider = TOTPProvider(issuer="MyApp")
    setup_data = totp_provider.setup(user_id=1, username="john")
    # 用户扫描 setup_data.uri 生成的二维码
    
    result = totp_provider.verify(user_id=1, code="123456")

8. 统一认证管理:
    from yweb.auth import AuthManager, AuthProvider
    
    auth_manager = AuthManager()
    auth_manager.register_provider("jwt", jwt_provider)
    auth_manager.register_provider("api_key", api_key_provider)
    
    result = auth_manager.authenticate("jwt", credentials)
"""

from .jwt import (
    JWTManager,
    create_jwt_token,
    verify_jwt_token,
    JOSE_AVAILABLE,
)

from .schemas import (
    TokenPayload,
    TokenResponse,
    TokenData,
)

from .dependencies import (
    oauth2_scheme,
    http_bearer,
    AuthDependency,
    create_auth_dependency,
    require_roles,
    RoleChecker,
    get_token_from_header,
)

# 统一认证接口
from .base import (
    AuthProvider,
    AuthManager,
    AuthType,
    UserIdentity,
    AuthResult,
)

# API Key 认证
from .api_key import (
    APIKeyManager,
    APIKeyData,
    APIKeyAuthProvider,
    api_key_header_scheme,
    api_key_query_scheme,
    get_api_key_from_request,
    require_api_key_scopes,
)

# Session 认证
from .session import (
    Session,
    SessionManager,
    SessionAuthProvider,
    set_session_cookie,
    clear_session_cookie,
)

# LDAP 认证
from .ldap import (
    LDAPManager,
    LDAPConfig,
    LDAPUser,
    LDAPType,
    LDAPAuthProvider,
    create_openldap_config,
    create_active_directory_config,
    LDAP3_AVAILABLE,
)

# OIDC (需要单独导入子模块)
from .oidc import (
    OIDCManager,
    OIDCClaims,
    OIDCAuthProvider,
    OIDC_SCOPES,
)
from .api import create_oidc_router

# Token 撤销/黑名单
from .token_store import (
    TokenStore,
    InMemoryTokenStore,
    RedisTokenStore,
    TokenBlacklist,
    RevokedTokenInfo,
    get_token_blacklist,
    configure_token_blacklist,
)

# 登录审计
from .audit import (
    LoginAuditService,
    LoginStatus,
    LoginFailureReason,
    LoginAttempt,
)

# 用户安全 Mixins
from .mixins import (
    LockableMixin,
    PasswordMixin,
    LastLoginMixin,
    FullUserMixin,
)

# 密码工具 (新增)
from .password import (
    PasswordHelper,
    hash_password,
    verify_password,
    needs_rehash,
    PasswordTooShortError,
    PasswordTooLongError,
)

# 抽象模型 + 角色 Mixin
from .models import (
    AbstractUser,
    AbstractSimpleRole,
    AbstractLoginRecord,
    RoleMixin,
)

# 认证服务 (新增)
from .service import (
    AbstractAuthService,
    BaseAuthService,
)

# 认证验证器 (新增) — 邮箱/手机号验证请用 yweb.validators
from .validators import (
    ValidationError,
    PasswordStrength,
    PasswordValidator,
    UsernameValidator,
)

# 一站式设置 (新增)
from .setup import (
    setup_auth,
    AuthSetup,
)

# IP 频率限制
from .rate_limiter import (
    LoginRateLimiter,
)

# 预置路由工厂（已迁移至 auth/api/ 子目录）
from .api import (
    create_user_router,
    create_login_record_router,
    create_auth_router,
)

__all__ = [
    # JWT (原有)
    "JWTManager",
    "create_jwt_token",
    "verify_jwt_token",
    "JOSE_AVAILABLE",
    
    # Schemas (原有)
    "TokenPayload",
    "TokenResponse",
    "TokenData",
    
    # Dependencies (原有)
    "oauth2_scheme",
    "http_bearer",
    "AuthDependency",
    "create_auth_dependency",
    "require_roles",
    "RoleChecker",
    "get_token_from_header",
    
    # 统一认证接口 (新增)
    "AuthProvider",
    "AuthManager",
    "AuthType",
    "UserIdentity",
    "AuthResult",
    
    # API Key (新增)
    "APIKeyManager",
    "APIKeyData",
    "APIKeyAuthProvider",
    "api_key_header_scheme",
    "api_key_query_scheme",
    "get_api_key_from_request",
    "require_api_key_scopes",
    
    # Session (新增)
    "Session",
    "SessionManager",
    "SessionAuthProvider",
    "set_session_cookie",
    "clear_session_cookie",
    
    # LDAP (新增)
    "LDAPManager",
    "LDAPConfig",
    "LDAPUser",
    "LDAPType",
    "LDAPAuthProvider",
    "create_openldap_config",
    "create_active_directory_config",
    "LDAP3_AVAILABLE",
    
    # OIDC (新增)
    "OIDCManager",
    "OIDCClaims",
    "OIDCAuthProvider",
    "OIDC_SCOPES",
    "create_oidc_router",
    
    # Token 撤销/黑名单
    "TokenStore",
    "InMemoryTokenStore",
    "RedisTokenStore",
    "TokenBlacklist",
    "RevokedTokenInfo",
    "get_token_blacklist",
    "configure_token_blacklist",
    
    # 登录审计
    "LoginAuditService",
    "LoginStatus",
    "LoginFailureReason",
    "LoginAttempt",
    
    # IP 频率限制
    "LoginRateLimiter",
    
    # 用户安全 Mixins
    "LockableMixin",
    "PasswordMixin",
    "LastLoginMixin",
    "FullUserMixin",
    
    # 密码工具 (新增)
    "PasswordHelper",
    "hash_password",
    "verify_password",
    "needs_rehash",
    "PasswordTooShortError",
    "PasswordTooLongError",
    
    # 抽象模型 + 角色 Mixin
    "AbstractUser",
    "AbstractSimpleRole",
    "AbstractLoginRecord",
    "RoleMixin",
    
    # 认证服务 (新增)
    "AbstractAuthService",
    "BaseAuthService",
    
    # 认证验证器 (新增) — 邮箱/手机号验证请用 yweb.validators
    "ValidationError",
    "PasswordStrength",
    "PasswordValidator",
    "UsernameValidator",
    
    # 一站式设置 (新增)
    "setup_auth",
    "AuthSetup",
    
    # 预置路由工厂 (新增)
    "create_user_router",
    "create_login_record_router",
    "create_auth_router",
]
