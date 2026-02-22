"""OAuth 2.0 端点路由

提供标准的 OAuth 2.0 端点实现。

端点列表：
    GET  /authorize                               - 授权端点
    POST /authorize                               - 处理授权提交
    POST /token                                   - Token 端点
    POST /revoke                                  - Token 撤销
    POST /introspect                              - Token 内省
    POST /device/code                             - 设备码
    GET  /device                                  - 设备验证页面
    POST /device/authorize                        - 设备授权确认
    GET  /.well-known/oauth-authorization-server  - 授权服务器元数据

使用示例::

    from yweb.auth.api import create_oauth2_router

    router = create_oauth2_router(oauth2_manager)
    app.include_router(router, prefix="/oauth2")
"""

from typing import Optional, Callable, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, status, Request, Form, Query
from fastapi.responses import RedirectResponse, JSONResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel

from ..oauth2.manager import OAuth2Manager


class TokenRequest(BaseModel):
    """Token 请求"""
    grant_type: str
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    code_verifier: Optional[str] = None
    device_code: Optional[str] = None


class TokenResponse(BaseModel):
    """Token 响应"""
    access_token: str
    token_type: str
    expires_in: int
    refresh_token: Optional[str] = None
    scope: Optional[str] = None
    id_token: Optional[str] = None


class ErrorResponse(BaseModel):
    """错误响应"""
    error: str
    error_description: Optional[str] = None
    error_uri: Optional[str] = None


class DeviceCodeResponse(BaseModel):
    """设备码响应"""
    device_code: str
    user_code: str
    verification_uri: str
    verification_uri_complete: Optional[str] = None
    expires_in: int
    interval: int


class IntrospectionResponse(BaseModel):
    """Token 内省响应"""
    active: bool
    scope: Optional[str] = None
    client_id: Optional[str] = None
    username: Optional[str] = None
    token_type: Optional[str] = None
    exp: Optional[int] = None
    iat: Optional[int] = None
    sub: Optional[str] = None


def create_oauth2_router(
    oauth2_manager: OAuth2Manager,
    user_authenticator: Callable[[str, str], Optional[Any]] = None,
    get_current_user: Callable = None,
    prefix: str = "",
    tags: list = None,
) -> APIRouter:
    """创建 OAuth 2.0 路由

    Args:
        oauth2_manager: OAuth 2.0 管理器
        user_authenticator: 用户认证函数，接收 (username, password)，返回用户对象
        get_current_user: 获取当前登录用户的依赖函数
        prefix: 路由前缀
        tags: OpenAPI 标签

    Returns:
        APIRouter: FastAPI 路由
    """
    router = APIRouter(prefix=prefix, tags=tags or ["OAuth2"])
    basic_auth = HTTPBasic(auto_error=False)

    def get_client_credentials(
        request: Request,
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        client_id: Optional[str] = Form(None),
        client_secret: Optional[str] = Form(None),
    ) -> tuple:
        """从请求中提取客户端凭证

        支持 HTTP Basic Auth 和表单提交两种方式。
        """
        # 优先使用 HTTP Basic Auth
        if credentials and credentials.username:
            return credentials.username, credentials.password

        # 其次使用表单参数
        if client_id:
            return client_id, client_secret

        return None, None

    @router.get("/authorize")
    async def authorize(
        response_type: str = Query(...),
        client_id: str = Query(...),
        redirect_uri: str = Query(...),
        scope: str = Query(None),
        state: str = Query(None),
        code_challenge: str = Query(None),
        code_challenge_method: str = Query(None),
        nonce: str = Query(None),  # OIDC
    ):
        """授权端点

        用户在此端点登录并授权客户端。
        """
        # 验证客户端
        client = oauth2_manager.get_client(client_id)
        if not client:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_client", "error_description": "Client not found"},
            )

        # 验证重定向 URI
        if not client.validate_redirect_uri(redirect_uri):
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "error_description": "Invalid redirect URI"},
            )

        # 验证 response_type
        if response_type != "code":
            error_params = urlencode({
                "error": "unsupported_response_type",
                "error_description": "Only 'code' response type is supported",
                "state": state or "",
            })
            return RedirectResponse(f"{redirect_uri}?{error_params}")

        # 验证 PKCE（如果客户端要求）
        if client.require_pkce and not code_challenge:
            error_params = urlencode({
                "error": "invalid_request",
                "error_description": "PKCE required",
                "state": state or "",
            })
            return RedirectResponse(f"{redirect_uri}?{error_params}")

        # 返回授权页面需要的信息（由前端处理）
        return {
            "client_id": client_id,
            "client_name": client.client_name,
            "redirect_uri": redirect_uri,
            "scope": scope,
            "state": state,
            "code_challenge": code_challenge,
            "code_challenge_method": code_challenge_method,
            "nonce": nonce,
            "requested_scopes": scope.split() if scope else client.default_scopes,
        }

    @router.post("/authorize")
    async def authorize_submit(
        request: Request,
        client_id: str = Form(...),
        redirect_uri: str = Form(...),
        scope: str = Form(None),
        state: str = Form(None),
        code_challenge: str = Form(None),
        code_challenge_method: str = Form(None),
        nonce: str = Form(None),
        user_id: int = Form(...),  # 在实际应用中，应从会话获取
        approve: bool = Form(True),
    ):
        """处理授权提交"""
        if not approve:
            error_params = urlencode({
                "error": "access_denied",
                "error_description": "User denied the request",
                "state": state or "",
            })
            return RedirectResponse(f"{redirect_uri}?{error_params}", status_code=302)

        # 生成授权码
        code = oauth2_manager.create_authorization_code(
            client_id=client_id,
            user_id=user_id,
            redirect_uri=redirect_uri,
            scope=scope or "",
            code_challenge=code_challenge,
            code_challenge_method=code_challenge_method,
            nonce=nonce,
        )

        # 重定向回客户端
        params = {"code": code}
        if state:
            params["state"] = state

        redirect_url = f"{redirect_uri}?{urlencode(params)}"
        return RedirectResponse(redirect_url, status_code=302)

    @router.post("/token")
    async def token(
        request: Request,
        grant_type: str = Form(...),
        code: str = Form(None),
        redirect_uri: str = Form(None),
        client_id: str = Form(None),
        client_secret: str = Form(None),
        refresh_token: str = Form(None),
        scope: str = Form(None),
        code_verifier: str = Form(None),
        device_code: str = Form(None),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
    ):
        """Token 端点"""
        # 提取客户端凭证
        if credentials and credentials.username:
            client_id = credentials.username
            client_secret = credentials.password

        if grant_type == "authorization_code":
            success, result = oauth2_manager.exchange_code(
                code=code,
                client_id=client_id,
                client_secret=client_secret,
                redirect_uri=redirect_uri,
                code_verifier=code_verifier,
            )
        elif grant_type == "client_credentials":
            success, result = oauth2_manager.client_credentials_token(
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
            )
        elif grant_type == "refresh_token":
            success, result = oauth2_manager.refresh_token(
                refresh_token=refresh_token,
                client_id=client_id,
                client_secret=client_secret,
                scope=scope,
            )
        elif grant_type == "urn:ietf:params:oauth:grant-type:device_code":
            success, result = oauth2_manager.device_code_token(
                device_code=device_code,
                client_id=client_id,
            )
        else:
            return JSONResponse(
                status_code=400,
                content={"error": "unsupported_grant_type"},
            )

        if not success:
            # 设备码特殊错误需要返回正确的状态码
            error = result.get("error", "server_error")
            if error in ("authorization_pending", "slow_down"):
                status_code = 400
            elif error in ("invalid_client", "invalid_grant"):
                status_code = 401
            else:
                status_code = 400

            return JSONResponse(
                status_code=status_code,
                content=result,
            )

        return result.to_response()

    @router.post("/revoke")
    async def revoke(
        token: str = Form(...),
        token_type_hint: str = Form(None),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        client_id: str = Form(None),
        client_secret: str = Form(None),
    ):
        """Token 撤销端点"""
        # 提取客户端凭证
        if credentials and credentials.username:
            client_id = credentials.username
            client_secret = credentials.password

        # 验证客户端
        if client_id:
            is_valid, result = oauth2_manager.validate_client(client_id, client_secret)
            if not is_valid:
                return JSONResponse(
                    status_code=401,
                    content={"error": "invalid_client", "error_description": result},
                )

        # 撤销 Token
        oauth2_manager.revoke_token(token, token_type_hint)

        # RFC 7009: 始终返回 200，即使 Token 无效
        return JSONResponse(status_code=200, content={})

    @router.post("/introspect")
    async def introspect(
        token: str = Form(...),
        token_type_hint: str = Form(None),
        credentials: HTTPBasicCredentials = Depends(basic_auth),
        client_id: str = Form(None),
        client_secret: str = Form(None),
    ):
        """Token 内省端点"""
        # 提取客户端凭证
        if credentials and credentials.username:
            client_id = credentials.username
            client_secret = credentials.password

        # 验证客户端
        if client_id:
            is_valid, result = oauth2_manager.validate_client(client_id, client_secret)
            if not is_valid:
                return JSONResponse(
                    status_code=401,
                    content={"error": "invalid_client", "error_description": result},
                )

        # 内省 Token
        result = oauth2_manager.introspect_token(token)
        return result

    @router.post("/device/code")
    async def device_code(
        client_id: str = Form(...),
        scope: str = Form(None),
    ):
        """设备码端点"""
        # 构建验证 URL（需要根据实际部署配置）
        verification_uri = "/oauth2/device"  # 可配置

        success, result = oauth2_manager.create_device_code(
            client_id=client_id,
            scope=scope or "",
            verification_uri=verification_uri,
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content=result,
            )

        return {
            "device_code": result.device_code,
            "user_code": result.user_code,
            "verification_uri": result.verification_uri,
            "verification_uri_complete": result.verification_uri_complete,
            "expires_in": result.expires_in,
            "interval": result.interval,
        }

    @router.get("/device")
    async def device_verify_page(
        user_code: str = Query(None),
    ):
        """设备验证页面"""
        return {
            "message": "Enter the code shown on your device",
            "user_code": user_code,
        }

    @router.post("/device/authorize")
    async def device_authorize(
        user_code: str = Form(...),
        user_id: int = Form(...),  # 在实际应用中，应从会话获取
        approve: bool = Form(True),
    ):
        """设备授权确认"""
        success, message = oauth2_manager.authorize_device(
            user_code=user_code,
            user_id=user_id,
            approve=approve,
        )

        if not success:
            return JSONResponse(
                status_code=400,
                content={"error": "invalid_request", "error_description": message},
            )

        return {"message": message}

    @router.get("/.well-known/oauth-authorization-server")
    async def authorization_server_metadata(request: Request):
        """OAuth 2.0 授权服务器元数据"""
        base_url = str(request.base_url).rstrip("/")

        return {
            "issuer": base_url,
            "authorization_endpoint": f"{base_url}{prefix}/authorize",
            "token_endpoint": f"{base_url}{prefix}/token",
            "revocation_endpoint": f"{base_url}{prefix}/revoke",
            "introspection_endpoint": f"{base_url}{prefix}/introspect",
            "device_authorization_endpoint": f"{base_url}{prefix}/device/code",
            "response_types_supported": ["code"],
            "grant_types_supported": [
                "authorization_code",
                "client_credentials",
                "refresh_token",
                "urn:ietf:params:oauth:grant-type:device_code",
            ],
            "token_endpoint_auth_methods_supported": [
                "client_secret_basic",
                "client_secret_post",
                "none",
            ],
            "code_challenge_methods_supported": ["plain", "S256"],
        }

    return router
