"""请求日志记录中间件"""
import json
import time
import logging
import uuid
import asyncio
import atexit
from typing import Optional, Dict, Any, Set, Callable, List
from contextvars import ContextVar
from concurrent.futures import ThreadPoolExecutor

from yweb.log import get_logger

# 创建默认日志记录器（自动推断为 yweb.middleware.request_logging）
_default_logger = get_logger()

from yweb.orm.db_session import db_manager

# 上下文变量用于存储请求信息
request_start_time_var = ContextVar('request_start_time', default=0.0)


class RequestLoggingMiddleware:
    """纯 ASGI 请求日志记录中间件
    
    优化特性：
    1. 使用纯 ASGI 实现，避免 BaseHTTPMiddleware 的死锁问题
    2. 正确处理请求体的读取和转发
    3. 异步日志记录，不阻塞请求处理
    4. 上下文变量管理请求信息
    
    使用示例:
        from fastapi import FastAPI
        from yweb.middleware import RequestLoggingMiddleware
        
        # 方式1：传统参数
        app.add_middleware(
            RequestLoggingMiddleware,
            max_body_size=1024 * 1024 * 5,
            skip_paths=["/health", "/metrics"]
        )
        
        # 方式2：配置对象（推荐）
        app.add_middleware(
            RequestLoggingMiddleware,
            config=settings.middleware,
            logger=my_logger,  # 可选，不传则使用默认
            user_info_getter=get_user_info
        )
    """
    
    # 类级别的线程池（所有实例共享）
    _executor: ThreadPoolExecutor = None
    _executor_lock = asyncio.Lock() if hasattr(asyncio, 'Lock') else None
    
    def __init__(
        self, 
        app, 
        max_body_size: int = None,
        skip_paths: Set[str] = None,
        logger: logging.Logger = None,
        user_info_getter: Callable = None,
        log_filters: List[Callable] = None,
        config: Any = None,
        enable_sensitive_filter: bool = True,
        user_info_timeout: float = 0.5,
        log_thread_workers: int = 2
    ):
        """初始化请求日志记录中间件
        
        Args:
            app: FastAPI应用实例
            max_body_size: 最大请求体记录大小（字节），如果提供 config 则忽略
            skip_paths: 跳过日志记录的路径集合，如果提供 config 则忽略
            logger: 自定义日志记录器
            user_info_getter: 可选的用户信息获取函数，支持同步或异步函数
            log_filters: 日志过滤器列表
            config: 中间件配置对象（MiddlewareSettings），提供后自动提取配置
            enable_sensitive_filter: 是否启用敏感数据过滤（默认启用）
            user_info_timeout: 用户信息获取超时时间（秒），默认0.5秒
            log_thread_workers: 日志写入线程池大小，默认2
        """
        self.app = app
        
        # 如果提供了 config，从中提取配置
        if config is not None:
            # 尝试获取解析后的字节数
            if hasattr(config, 'parsed_request_log_max_body_size'):
                max_body_size = config.parsed_request_log_max_body_size
            elif hasattr(config, 'request_log_max_body_size'):
                # 如果是字符串，需要解析
                from ..utils import parse_file_size
                max_body_size = parse_file_size(config.request_log_max_body_size)
            
            # 获取跳过路径
            if hasattr(config, 'request_log_skip_paths'):
                skip_paths = set(config.request_log_skip_paths)
        
        self.max_body_size = max_body_size or (1024 * 1024 * 5)  # 默认5MB
        self.skip_paths = skip_paths or set()
        self.logger = logger or _default_logger
        self.user_info_getter = user_info_getter
        self.user_info_timeout = user_info_timeout
        
        # 初始化线程池（类级别共享）
        self._init_executor(log_thread_workers)
        
        # 处理日志过滤器
        self.log_filters = log_filters or []
        
        # 如果启用敏感数据过滤，添加默认过滤器
        if enable_sensitive_filter:
            from ..log import log_filter_hook_manager
            self.log_filters.append(log_filter_hook_manager.apply_filters)
    
    @classmethod
    def _init_executor(cls, max_workers: int = 2):
        """初始化类级别的线程池"""
        if cls._executor is None:
            cls._executor = ThreadPoolExecutor(
                max_workers=max_workers, 
                thread_name_prefix="log_writer"
            )
            # 注册退出时关闭线程池
            atexit.register(cls._shutdown_executor)
    
    @classmethod
    def _shutdown_executor(cls):
        """关闭线程池"""
        if cls._executor is not None:
            cls._executor.shutdown(wait=False)
            cls._executor = None
    
    def _should_skip(self, path: str) -> bool:
        """检查是否应该跳过该路径的详细日志记录"""
        if path in self.skip_paths:
            return True
        # 检查路径是否以跳过前缀开头
        for skip_path in self.skip_paths:
            if path.startswith(skip_path):
                return True
        return False
    
    def _parse_body(self, body_bytes: bytes, content_type: str) -> Optional[Any]:
        """解析请求体内容"""
        if not body_bytes:
            return None
            
        # 检查大小限制
        if len(body_bytes) > self.max_body_size:
            body_bytes = body_bytes[:self.max_body_size]
            truncated = True
        else:
            truncated = False
        
        try:
            # 检查是否是JSON内容类型
            if 'application/json' in content_type.lower():
                result = json.loads(body_bytes.decode('utf-8'))
                if truncated:
                    return {"_truncated": True, "_preview": str(result)[:500]}
                return result
            else:
                # 非JSON内容，记录为文本（截断）
                body_text = body_bytes.decode('utf-8', errors='replace')
                if len(body_text) > 500:
                    body_text = body_text[:500] + "..."
                return body_text
        except (json.JSONDecodeError, UnicodeDecodeError):
            # 如果不是有效文本，记录为十六进制预览
            preview = body_bytes[:100].hex()
            return f"[Binary data, preview: {preview}...]" if len(body_bytes) > 100 else f"[Binary data: {preview}]"
    
    async def _get_user_info_with_timeout(self, scope: dict) -> str:
        """带超时控制的用户信息获取
        
        所有异常都被捕获，确保不影响正常请求：
        - 超时返回 "anonymous[timeout]"
        - 异常返回 "anonymous[error]"
        - 无 getter 返回 "anonymous"
        """
        if self.user_info_getter is None:
            return "anonymous"
        
        try:
            # 判断是否是协程函数
            if asyncio.iscoroutinefunction(self.user_info_getter):
                # 异步函数，使用 wait_for 添加超时
                user_info = await asyncio.wait_for(
                    self.user_info_getter(scope),
                    timeout=self.user_info_timeout
                )
            else:
                # 同步函数，在线程池中执行以避免阻塞事件循环
                loop = asyncio.get_event_loop()
                user_info = await asyncio.wait_for(
                    loop.run_in_executor(None, self.user_info_getter, scope),
                    timeout=self.user_info_timeout
                )
            
            return str(user_info) if user_info else "anonymous"
            
        except asyncio.TimeoutError:
            return "anonymous[timeout]"
        except Exception as e:
            # 静默处理所有异常，可选记录警告
            try:
                self.logger.debug(f"Failed to get user info: {type(e).__name__}: {e}")
            except Exception:
                pass
            return "anonymous[error]"
    
    def _write_log_sync(self, log_data: Dict[str, Any]):
        """同步日志写入（在线程池中执行）
        
        所有异常都被捕获，确保不会抛出任何错误
        """
        try:
            request_body_preview = log_data.get('request_body_preview', 'None')
            # 确保request_body_preview是字符串形式
            if isinstance(request_body_preview, dict):
                request_body_str = json.dumps(request_body_preview, ensure_ascii=False)
            else:
                request_body_str = str(request_body_preview) if request_body_preview else 'None'
                
            log_message = (
                f"Process Time: {log_data.get('process_time', 0):.3f}s | "
                f"Request ID: {log_data.get('request_id', '')} | "
                f"User: {log_data.get('user_info', 'anonymous')} | "
                f"Method: {log_data.get('method', '')} | "
                f"URL: {log_data.get('url', '')} | "
                f"Client IP: {log_data.get('client_ip', 'unknown')} | "
                f"Status: {log_data.get('status_code', 0)} | "
                f"Request Body: {request_body_str[:500]} | "
                f"User-Agent: {log_data.get('user_agent', 'unknown')[:100]}"
            )
            
            # 根据状态码决定日志级别
            status_code = log_data.get('status_code', 200)
            if status_code >= 500:
                self.logger.error(log_message)
            elif status_code >= 400:
                self.logger.warning(log_message)
            else:
                self.logger.info(log_message)
                
        except Exception as e:
            # 日志写入失败，静默忽略（可选打印到 stderr）
            try:
                import sys
                print(f"[RequestLogging] Failed to write log: {e}", file=sys.stderr)
            except Exception:
                pass
    
    def _apply_log_filters(self, log_data: Dict[str, Any]) -> Dict[str, Any]:
        """应用日志过滤器，单个过滤器失败不影响其他过滤器和请求"""
        for log_filter in self.log_filters:
            try:
                filtered_data = log_filter(log_data)
                if filtered_data is not None:
                    log_data = filtered_data
            except Exception as e:
                # 过滤器失败，静默忽略，继续使用原数据
                try:
                    self.logger.debug(f"Log filter failed: {type(e).__name__}: {e}")
                except Exception:
                    pass
        return log_data
    
    def _schedule_log(self, log_data: Dict[str, Any]):
        """将日志任务调度到后台线程池（完全非阻塞）
        
        如果调度失败，静默忽略
        """
        try:
            if self._executor is not None:
                self._executor.submit(self._write_log_sync, log_data)
            else:
                # 线程池不可用，回退到同步写入
                self._write_log_sync(log_data)
        except Exception:
            # 调度失败，静默忽略
            pass
    
    async def __call__(self, scope, receive, send):
        """ASGI 接口
        
        错误隔离保证：
        - 用户信息获取失败返回 "anonymous[error]" 或 "anonymous[timeout]"，不影响请求
        - 日志过滤器失败静默忽略，不影响请求
        - 日志写入失败静默忽略，不影响请求
        """
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        
        # 生成请求ID（异常安全）
        try:
            request_id = db_manager._get_request_id()
            if not request_id:
                request_id = "unknown"
        except Exception:
            request_id = "get_request_id_exception"
        
        # 记录开始时间
        start_time = time.time()
        try:
            request_start_time_var.set(start_time)
        except Exception:
            pass
        
        # 获取请求基本信息（异常安全）
        try:
            method = scope.get("method", "")
            path = scope.get("path", "")
            url_path = path.lower()
            
            # 获取 headers
            headers = dict(scope.get("headers", []))
            content_type = headers.get(b"content-type", b"").decode("utf-8", errors="replace")
            user_agent = headers.get(b"user-agent", b"unknown").decode("utf-8", errors="replace")[:200]
            
            # 获取客户端 IP
            client = scope.get("client")
            client_ip = client[0] if client else "unknown"
            
            # 检查是否跳过详细日志
            should_skip_detailed = self._should_skip(url_path)
        except Exception:
            method = scope.get("method", "") if scope else ""
            url_path = scope.get("path", "").lower() if scope else ""
            content_type = ""
            user_agent = "unknown"
            client_ip = "unknown"
            should_skip_detailed = False
        
        # 收集请求体
        body_chunks = []
        body_complete = False
        
        async def receive_wrapper():
            nonlocal body_complete
            message = await receive()
            
            try:
                if message["type"] == "http.request":
                    body = message.get("body", b"")
                    if body and not should_skip_detailed and method in ["POST", "PUT", "PATCH"]:
                        # 只在需要记录时收集请求体
                        total_size = sum(len(c) for c in body_chunks)
                        if total_size < self.max_body_size:
                            body_chunks.append(body)
                    
                    if not message.get("more_body", False):
                        body_complete = True
            except Exception:
                pass
            
            return message
        
        # 捕获响应状态码
        status_code = 200
        
        async def send_wrapper(message):
            nonlocal status_code
            try:
                if message["type"] == "http.response.start":
                    status_code = message.get("status", 200)
            except Exception:
                pass
            await send(message)
        
        # 在请求开始时启动用户信息获取任务（并行执行）
        user_info_task = None
        try:
            if self.user_info_getter is not None:
                user_info_task = asyncio.create_task(
                    self._get_user_info_with_timeout(scope)
                )
        except Exception:
            pass
        
        # 默认用户信息
        user_info = "anonymous"
        
        try:
            # 调用下一个中间件/应用（核心请求处理）
            await self.app(scope, receive_wrapper, send_wrapper)
            
            # 请求完成后，等待用户信息获取结果
            if user_info_task is not None:
                try:
                    user_info = await user_info_task
                except Exception:
                    user_info = "anonymous[error]"
            
            # 以下都是日志相关操作，任何失败都不影响请求
            try:
                # 计算处理时间
                process_time = time.time() - start_time
                
                # 解析请求体
                if should_skip_detailed:
                    request_body_preview = "[SKIPPED_PATH]"
                elif method not in ["POST", "PUT", "PATCH"]:
                    request_body_preview = "[NO_BODY]"
                elif body_chunks:
                    full_body = b"".join(body_chunks)
                    request_body_preview = self._parse_body(full_body, content_type)
                else:
                    request_body_preview = None
                
                # 构造日志数据
                log_data = {
                    'request_id': request_id,
                    'process_time': process_time,
                    'user_info': user_info,
                    'method': method,
                    'url': url_path,
                    'client_ip': client_ip,
                    'status_code': status_code,
                    'request_body_preview': request_body_preview,
                    'user_agent': user_agent,
                }
                
                # 应用日志过滤器（异常安全）
                log_data = self._apply_log_filters(log_data)
                
                # 调度日志到后台线程池（完全非阻塞）
                self._schedule_log(log_data)
                
            except Exception:
                # 日志相关操作失败，静默忽略
                pass
            
        except Exception as e:
            # 请求处理异常，需要记录错误日志然后重新抛出
            
            # 尝试获取用户信息（如果任务还在运行）
            if user_info_task is not None:
                try:
                    # 给一个很短的超时，不要阻塞太久
                    user_info = await asyncio.wait_for(
                        asyncio.shield(user_info_task), 
                        timeout=0.1
                    )
                except Exception:
                    user_info = "anonymous"
            
            # 记录异常日志（异常安全）
            try:
                process_time = time.time() - start_time

                # 获取完整的异常堆栈信息
                import sys
                import traceback
                exc_type, exc_value, exc_traceback = sys.exc_info()
                tb_lines = traceback.format_exception(exc_type, exc_value, exc_traceback)
                full_traceback = "".join(tb_lines)

                # 错误日志需要立即记录（同步），确保不丢失
                self.logger.error(
                    f"Process Time: {process_time:.3f}s | "
                    f"API Request Error - Request ID: {request_id} | "
                    f"User: {user_info} | "
                    f"Method: {method} | "
                    f"URL: {url_path} | "
                    f"Client IP: {client_ip} | "
                    f"Exception: {type(e).__name__}: {str(e)}\n"
                    f"Traceback:\n{full_traceback}"
                )
            except Exception:
                # 日志记录失败也不影响异常传播
                pass

            # 重新抛出异常，让全局异常处理器处理
            raise
