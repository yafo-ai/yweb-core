"""性能监控中间件"""
import time
import logging

from yweb.log import get_logger

# 创建默认日志记录器（自动推断为 yweb.middleware.performance）
_default_logger = get_logger()


class PerformanceMonitoringMiddleware:
    """简单的性能监控中间件
    
    用于监控慢请求并记录警告日志。
    
    使用示例:
        from fastapi import FastAPI
        from yweb.middleware import PerformanceMonitoringMiddleware
        
        app = FastAPI()
        app.add_middleware(PerformanceMonitoringMiddleware, slow_request_threshold=1.0)
    """
    
    def __init__(self, app, slow_request_threshold: float = 1.0, logger: logging.Logger = None):
        """初始化性能监控中间件
        
        Args:
            app: FastAPI应用实例
            slow_request_threshold: 慢请求阈值（秒），超过此时间将记录警告
            logger: 自定义日志记录器
        """
        self.app = app
        self.slow_request_threshold = slow_request_threshold
        self.logger = logger or _default_logger
    
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        
        start_time = time.time()
        
        # 自定义send包装器来捕获响应状态码
        async def send_wrapper(message):
            if message.get("type") == "http.response.start":
                # 记录响应时间
                process_time = time.time() - start_time
                if process_time > self.slow_request_threshold:
                    path = scope.get("path", "")
                    method = scope.get("method", "")
                    self.logger.warning(
                        f"Slow request detected: {method} {path} took {process_time:.2f}s"
                    )
            
            await send(message)
        
        await self.app(scope, receive, send_wrapper)

