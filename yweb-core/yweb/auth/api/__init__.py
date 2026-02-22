"""认证模块 - API 路由

提供开箱即用的路由工厂函数，按职责拆分到独立文件：

- user_api       用户管理 CRUD
- login_record_api  登录记录查询
- auth_api       认证端点（登录/登出/刷新/踢出）
- oidc_api       OIDC Discovery / UserInfo
- oauth2_api     OAuth 2.0 端点

使用示例::

    from yweb.auth.api import create_user_router, create_auth_router

    user_router = create_user_router(User)
    auth_router = create_auth_router(auth_service, jwt_manager)

    app.include_router(user_router, prefix="/api/v1/users")
    app.include_router(auth_router, prefix="/api/v1/auth")
"""

from .user_api import create_user_router
from .login_record_api import create_login_record_router
from .auth_api import create_auth_router
from .oidc_api import create_oidc_router
from .oauth2_api import create_oauth2_router

__all__ = [
    "create_user_router",
    "create_login_record_router",
    "create_auth_router",
    "create_oidc_router",
    "create_oauth2_router",
]
