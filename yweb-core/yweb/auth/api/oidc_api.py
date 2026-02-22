"""OIDC 路由

提供 OpenID Connect 标准端点。

端点列表：
    GET  /.well-known/openid-configuration  - OIDC Discovery
    GET  /.well-known/jwks.json             - JWKS 公钥
    GET  /userinfo                          - 用户信息
    POST /userinfo                          - 用户信息

使用示例::

    from yweb.auth.api import create_oidc_router

    router = create_oidc_router(oidc_manager)
    app.include_router(router)
"""

from typing import Any, Callable

from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import JSONResponse

from ..oidc import OIDCManager


def create_oidc_router(
    oidc_manager: OIDCManager,
    oauth2_manager: Any = None,
    get_current_user_token: Callable = None,
    prefix: str = "",
) -> APIRouter:
    """创建 OIDC 路由

    Args:
        oidc_manager: OIDC 管理器
        oauth2_manager: OAuth 2.0 管理器（用于验证访问令牌）
        get_current_user_token: 获取当前用户 Token 的依赖函数
        prefix: 路由前缀

    Returns:
        APIRouter: FastAPI 路由
    """
    router = APIRouter(prefix=prefix, tags=["OIDC"])

    @router.get("/.well-known/openid-configuration")
    async def openid_configuration(request: Request):
        """OIDC Discovery 端点"""
        base_url = str(request.base_url).rstrip("/")
        return oidc_manager.get_discovery_document(base_url)

    @router.get("/.well-known/jwks.json")
    async def jwks():
        """JWKS 端点"""
        return oidc_manager.get_jwks()

    @router.get("/userinfo")
    @router.post("/userinfo")
    async def userinfo(request: Request):
        """UserInfo 端点"""
        # 从请求中获取访问令牌
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Bearer token required",
                headers={"WWW-Authenticate": "Bearer"},
            )

        access_token = auth_header[7:]

        # 验证访问令牌
        if not oauth2_manager:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OAuth2 manager not configured",
            )

        is_valid, result = oauth2_manager.validate_token(access_token)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired token",
                headers={"WWW-Authenticate": "Bearer"},
            )

        # 获取用户信息
        user_id = result.get("sub") or result.get("user_id")
        scope = result.get("scope", "")

        claims = oidc_manager.get_userinfo_claims(
            user_id=user_id,
            scope=scope,
        )

        if not claims:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        return JSONResponse(content=claims)

    return router
