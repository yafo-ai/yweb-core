"""请求ID中间件

注意：使用纯 ASGI 中间件而非 BaseHTTPMiddleware，
因为 BaseHTTPMiddleware 会在 call_next 时创建新的任务上下文，
导致 ContextVar 的修改无法传播回父上下文，从而导致 session 清理失败。
"""
import uuid
from contextvars import ContextVar
from yweb.orm.db_session import db_manager



class RequestIDMiddleware:
    """请求ID中间件（纯 ASGI 实现）
    
    用于为每个API请求生成唯一ID，可以用作数据库连接标识、日志追踪等。
    请求结束时会自动清理数据库 session，防止连接泄漏。
    
    重要：使用纯 ASGI 中间件而非 BaseHTTPMiddleware，避免上下文隔离问题。
    
    使用示例:
        from fastapi import FastAPI
        from yweb.middleware import RequestIDMiddleware
        
        app = FastAPI()
        app.add_middleware(RequestIDMiddleware)
    """
    
    def __init__(self, app):
        """初始化请求ID中间件
        
        Args:
            app: FastAPI/ASGI 应用实例
        """
        self.app = app
    
    async def __call__(self, scope, receive, send):
        """ASGI 接口"""
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        request_id = db_manager._set_request_id()
        
        # 用于捕获响应状态
        response_started = False
        initial_message = None
        
        async def send_wrapper(message):
            nonlocal response_started, initial_message
            
            if message["type"] == "http.response.start":
                response_started = True
                # 添加 X-Request-ID 响应头
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode()))
                message = {**message, "headers": headers}
                initial_message = message
            
            await send(message)
        
        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # 清理数据库 session，防止连接泄漏
            # 注意：这里在同一个上下文中执行，ContextVar 修改可见
            try:
                from yweb.orm import on_request_end
                on_request_end()
            except ImportError:
                pass


def get_request_id() -> str:
    return db_manager._get_request_id()
