"""当前用户追踪中间件

自动从 JWT Token 解析 user_id 并存入 ContextVar，
配合 CurrentUserPlugin 实现历史记录自动审计。

使用示例:
    from fastapi import FastAPI
    from yweb.middleware import CurrentUserMiddleware
    from yweb.auth import JWTManager
    
    app = FastAPI()
    jwt_manager = JWTManager(secret_key="your-secret-key")
    
    # 添加中间件
    app.add_middleware(
        CurrentUserMiddleware,
        jwt_manager=jwt_manager,
        skip_paths=["/login", "/docs"]
    )
    
    # API 代码无需任何改动
    @app.post("/articles")
    def create_article(title: str):
        article = Article(title=title)
        article.add(commit=True)  # user_id 自动追踪！
        return {"id": article.id}
"""

from contextvars import ContextVar
from typing import Callable, List, Optional, Union

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


# ContextVar 用于在中间件层存储 user_id（无需 session）
_current_user_id_var: ContextVar[Optional[Union[int, str]]] = ContextVar(
    'current_user_id', default=None
)


def set_current_user_id(user_id: Optional[Union[int, str]]) -> None:
    """设置当前用户 ID（ContextVar 方式，用于中间件）"""
    _current_user_id_var.set(user_id)


def get_current_user_id() -> Optional[Union[int, str]]:
    """获取当前用户 ID（ContextVar 方式）"""
    return _current_user_id_var.get()


def clear_current_user_id() -> None:
    """清除当前用户 ID（ContextVar 方式）"""
    _current_user_id_var.set(None)


class CurrentUserMiddleware(BaseHTTPMiddleware):
    """当前用户追踪中间件
    
    自动从请求的 JWT Token 解析 user_id 并存入 ContextVar，
    使得后续的数据库操作可以自动记录操作者信息。
    
    工作流程：
    1. 从 Authorization Header 获取 JWT Token
    2. 使用 JWTManager 解析 Token 获取 user_id
    3. 将 user_id 存入 ContextVar
    4. 请求处理完成后清理 ContextVar
    
    Args:
        app: FastAPI/Starlette 应用实例
        jwt_manager: JWTManager 实例，用于解析 Token
        skip_paths: 跳过追踪的路径列表（如登录、注册等无需认证的路径）
        user_id_extractor: 自定义 user_id 提取函数，接收 token_data 返回 user_id
                          默认使用 token_data.user_id
    
    使用示例:
        # 基本用法
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=jwt_manager
        )
        
        # 自定义跳过路径
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=jwt_manager,
            skip_paths=["/login", "/register", "/health", "/docs", "/openapi.json"]
        )
        
        # 自定义 user_id 提取（如果 token 结构不同）
        app.add_middleware(
            CurrentUserMiddleware,
            jwt_manager=jwt_manager,
            user_id_extractor=lambda data: data.sub  # 从 sub 字段提取
        )
    """
    
    # 默认跳过的路径
    DEFAULT_SKIP_PATHS = [
        "/docs",
        "/redoc", 
        "/openapi.json",
        "/health",
        "/ping",
    ]
    
    def __init__(
        self,
        app,
        jwt_manager=None,
        skip_paths: Optional[List[str]] = None,
        user_id_extractor: Optional[Callable] = None,
    ):
        """初始化中间件
        
        Args:
            app: FastAPI/Starlette 应用实例
            jwt_manager: JWTManager 实例（可选，如果不提供则中间件不起作用）
            skip_paths: 跳过追踪的路径列表，会与默认列表合并
            user_id_extractor: 自定义 user_id 提取函数
        """
        super().__init__(app)
        self.jwt_manager = jwt_manager
        
        # 合并默认跳过路径和用户自定义路径
        self.skip_paths = set(self.DEFAULT_SKIP_PATHS)
        if skip_paths:
            self.skip_paths.update(skip_paths)
        
        # user_id 提取函数
        self.user_id_extractor = user_id_extractor or self._default_user_id_extractor
    
    def _default_user_id_extractor(self, token_data) -> Optional[Union[int, str]]:
        """默认的 user_id 提取函数"""
        if token_data is None:
            return None
        return getattr(token_data, 'user_id', None)
    
    def _should_skip(self, path: str) -> bool:
        """判断是否应该跳过该路径"""
        # 精确匹配
        if path in self.skip_paths:
            return True
        
        # 前缀匹配（支持 /docs/xxx 等）
        for skip_path in self.skip_paths:
            if path.startswith(skip_path + "/"):
                return True
        
        return False
    
    def _get_token_from_header(self, request: Request) -> Optional[str]:
        """从请求头获取 JWT Token
        
        支持格式：Authorization: Bearer <token>
        """
        authorization = request.headers.get("Authorization")
        if not authorization:
            return None
        
        parts = authorization.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            return None
        
        return parts[1]
    
    def _extract_user_id(self, token: str) -> Optional[Union[int, str]]:
        """从 Token 中提取 user_id"""
        if not self.jwt_manager:
            return None
        
        try:
            token_data = self.jwt_manager.verify_token(token)
            return self.user_id_extractor(token_data)
        except Exception:
            # Token 无效或过期，返回 None
            return None
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求"""
        path = request.url.path
        
        # 跳过不需要追踪的路径
        if self._should_skip(path):
            return await call_next(request)
        
        # 从 Token 提取 user_id
        user_id = None
        token = self._get_token_from_header(request)
        if token:
            user_id = self._extract_user_id(token)
        
        # 设置 ContextVar
        if user_id is not None:
            set_current_user_id(user_id)
        
        try:
            response = await call_next(request)
            return response
        finally:
            # 请求结束，清理 ContextVar
            clear_current_user_id()


# 简化版中间件（不依赖 JWTManager，手动提取）
class SimpleCurrentUserMiddleware(BaseHTTPMiddleware):
    """简化版当前用户追踪中间件
    
    不依赖 JWTManager，使用自定义的 user_id 提取函数。
    适用于非标准的认证方式。
    
    Args:
        app: FastAPI/Starlette 应用实例
        user_id_getter: 从 Request 获取 user_id 的函数
        skip_paths: 跳过追踪的路径列表
    
    使用示例:
        # 自定义提取逻辑
        def get_user_id_from_request(request: Request) -> Optional[int]:
            # 从自定义 Header 获取
            return request.headers.get("X-User-ID")
        
        app.add_middleware(
            SimpleCurrentUserMiddleware,
            user_id_getter=get_user_id_from_request
        )
    """
    
    def __init__(
        self,
        app,
        user_id_getter: Callable[[Request], Optional[Union[int, str]]],
        skip_paths: Optional[List[str]] = None,
    ):
        super().__init__(app)
        self.user_id_getter = user_id_getter
        self.skip_paths = set(skip_paths or [])
    
    def _should_skip(self, path: str) -> bool:
        """判断是否应该跳过该路径"""
        if path in self.skip_paths:
            return True
        for skip_path in self.skip_paths:
            if path.startswith(skip_path + "/"):
                return True
        return False
    
    async def dispatch(self, request: Request, call_next) -> Response:
        """处理请求"""
        if self._should_skip(request.url.path):
            return await call_next(request)
        
        # 使用自定义函数获取 user_id
        user_id = None
        try:
            user_id = self.user_id_getter(request)
        except Exception:
            pass
        
        if user_id is not None:
            set_current_user_id(user_id)
        
        try:
            response = await call_next(request)
            return response
        finally:
            clear_current_user_id()


__all__ = [
    "CurrentUserMiddleware",
    "SimpleCurrentUserMiddleware",
    # ContextVar 方式（用于中间件层）
    "set_current_user_id",
    "get_current_user_id", 
    "clear_current_user_id",
]
