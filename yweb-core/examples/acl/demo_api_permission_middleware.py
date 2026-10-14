"""
ApiPermissionMiddleware 参考实现

演示如何将 ACL 引擎用于 API 路由权限控制。
此文件是应用层的参考代码，不在框架核心中。

使用方式::

    app.add_middleware(
        ApiPermissionMiddleware,
        acl_service=acl.get_service(),
        identity_provider=expander,
        whitelist={"api/auth/login", "api/auth/refresh"},
    )
"""

import re
from typing import Optional

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse


class ApiPermissionMiddleware(BaseHTTPMiddleware):
    """API 路由权限中间件

    拦截每个请求，检查当前用户对该 API 路由是否有访问权限。
    路由以 resource_type="API_ROUTE" 注册到 ACL 资源树。

    注意：这不是框架内置组件，是应用层的参考实现。
    """

    def __init__(
        self,
        app,
        acl_service,
        identity_provider,
        whitelist: Optional[set[str]] = None,
        required_level: int = 10,
    ):
        super().__init__(app)
        self.acl_service = acl_service
        self.identity_provider = identity_provider
        self.whitelist = whitelist or set()
        self.required_level = required_level

    async def dispatch(self, request: Request, call_next):
        path = self._normalize_path(request.url.path)

        # 白名单直接放行
        if path in self.whitelist:
            return await call_next(request)

        # 获取当前用户
        user = getattr(request.state, "user", None)
        if user is None:
            return JSONResponse(
                status_code=401,
                content={"code": "UNAUTHORIZED", "message": "未登录"},
            )

        # 管理员 bypass
        if getattr(user, "is_admin", False):
            return await call_next(request)

        # 展开身份
        identities = self.identity_provider.get_identities(user)

        # 检查 ACL 权限
        has_perm = self.acl_service.check(
            identities,
            "API_ROUTE",
            path,
            self.required_level,
        )

        if not has_perm:
            return JSONResponse(
                status_code=403,
                content={"code": "PERMISSION_DENIED", "message": f"无权访问: {path}"},
            )

        return await call_next(request)

    @staticmethod
    def _normalize_path(path: str) -> str:
        """规范化路径：去掉尾部斜杠，替换路径参数为 {param}"""
        path = path.rstrip("/")
        path = re.sub(r"/\d+", "/{id}", path)
        return path
