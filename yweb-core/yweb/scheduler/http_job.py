"""HTTP 任务

提供 HTTP 调用任务支持，可定时调用外部 API。

使用示例:
    from yweb.scheduler import HttpJob, Scheduler, cron
    
    # 方式1: 继承 HttpJob
    class WebhookJob(HttpJob):
        code = "WEBHOOK"
        trigger = cron("0 8 * * *")
        url = "https://api.example.com/webhook"
        method = "POST"
        headers = {"Authorization": "Bearer xxx"}
        
        def get_body(self, context):
            return {"event": "daily_report"}
    
    # 方式2: 动态添加
    scheduler.add_http_job(
        url="https://api.example.com/sync",
        trigger=cron("*/5 * * * *"),
        code="SYNC_API",
        method="GET",
    )
"""

import json
import logging
from dataclasses import dataclass, field
from typing import Optional, Dict, Any, Union, ClassVar
from datetime import datetime

from .job import Job
from .context import JobContext

logger = logging.getLogger(__name__)


@dataclass
class HttpResponse:
    """HTTP 响应数据类"""
    
    status_code: int
    body: Optional[str] = None
    headers: Dict[str, str] = field(default_factory=dict)
    elapsed_ms: int = 0
    
    @property
    def ok(self) -> bool:
        """是否成功（2xx 状态码）"""
        return 200 <= self.status_code < 300
    
    def json(self) -> Any:
        """解析 JSON 响应"""
        if self.body:
            return json.loads(self.body)
        return None
    
    def __repr__(self) -> str:
        return f"HttpResponse(status={self.status_code}, ok={self.ok})"


class HttpJob(Job):
    """HTTP 任务基类
    
    用于定时调用 HTTP API 的任务。
    
    类属性:
        url: 请求 URL（必须）
        method: HTTP 方法（默认 GET）
        headers: 请求头
        timeout: 超时时间（秒，默认 30）
        success_codes: 成功状态码列表（默认 [200, 201, 202, 204]）
        retry_codes: 需要重试的状态码（默认 [429, 500, 502, 503, 504]）
    
    Examples:
        # 简单 GET 请求
        class HealthCheckJob(HttpJob):
            code = "HEALTH_CHECK"
            trigger = interval(minutes=1)
            url = "https://api.example.com/health"
        
        # POST 请求
        class WebhookJob(HttpJob):
            code = "WEBHOOK"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com/webhook"
            method = "POST"
            headers = {"Content-Type": "application/json"}
            max_retries = 3
            
            def get_body(self, context):
                return {"timestamp": context.scheduled_time.isoformat()}
    """
    
    # HTTP 配置
    url: ClassVar[str] = ""
    method: ClassVar[str] = "GET"
    headers: ClassVar[Dict[str, str]] = {}
    timeout: ClassVar[int] = 30
    
    # 响应配置
    success_codes: ClassVar[list] = [200, 201, 202, 204]
    retry_codes: ClassVar[list] = [429, 500, 502, 503, 504]
    
    def __init__(self):
        """初始化 HTTP 任务"""
        super().__init__()
        
        if not self.url:
            raise ValueError(f"{self.__class__.__name__} must define 'url'")
    
    async def execute(self, context: JobContext) -> HttpResponse:
        """执行 HTTP 请求
        
        Args:
            context: 任务执行上下文
        
        Returns:
            HttpResponse 响应对象
        
        Raises:
            HttpJobError: HTTP 请求失败
        """
        import aiohttp
        
        url = self.get_url(context)
        method = self.get_method(context)
        headers = self.get_headers(context)
        body = self.get_body(context)
        
        logger.info(f"[{context.run_id}] HTTP {method} {url}")
        
        start_time = datetime.now()
        
        try:
            async with aiohttp.ClientSession() as session:
                kwargs = {
                    "method": method,
                    "url": url,
                    "headers": headers,
                    "timeout": aiohttp.ClientTimeout(total=self.timeout),
                }
                
                if body is not None:
                    if isinstance(body, dict):
                        kwargs["json"] = body
                    else:
                        kwargs["data"] = body
                
                async with session.request(**kwargs) as resp:
                    elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
                    response_body = await resp.text()
                    
                    response = HttpResponse(
                        status_code=resp.status,
                        body=response_body,
                        headers=dict(resp.headers),
                        elapsed_ms=elapsed_ms,
                    )
                    
                    logger.info(
                        f"[{context.run_id}] HTTP response: "
                        f"status={resp.status}, elapsed={elapsed_ms}ms"
                    )
                    
                    # 检查是否成功
                    if resp.status not in self.success_codes:
                        if resp.status in self.retry_codes:
                            raise HttpRetryError(
                                f"HTTP {resp.status}: {response_body[:200]}",
                                response=response
                            )
                        else:
                            raise HttpJobError(
                                f"HTTP {resp.status}: {response_body[:200]}",
                                response=response
                            )
                    
                    return response
                    
        except aiohttp.ClientError as e:
            elapsed_ms = int((datetime.now() - start_time).total_seconds() * 1000)
            logger.error(f"[{context.run_id}] HTTP error: {e}")
            raise HttpRetryError(str(e))
    
    def get_url(self, context: JobContext) -> str:
        """获取请求 URL（可覆盖以动态生成）
        
        Args:
            context: 任务执行上下文
        
        Returns:
            请求 URL
        """
        return self.url
    
    def get_method(self, context: JobContext) -> str:
        """获取 HTTP 方法（可覆盖以动态生成）
        
        Args:
            context: 任务执行上下文
        
        Returns:
            HTTP 方法
        """
        return self.method
    
    def get_headers(self, context: JobContext) -> Dict[str, str]:
        """获取请求头（可覆盖以动态生成）
        
        Args:
            context: 任务执行上下文
        
        Returns:
            请求头字典
        """
        return self.headers.copy()
    
    def get_body(self, context: JobContext) -> Optional[Union[Dict, str, bytes]]:
        """获取请求体（可覆盖以动态生成）
        
        Args:
            context: 任务执行上下文
        
        Returns:
            请求体（字典、字符串或字节）
        """
        return None
    
    async def on_success(self, context: JobContext, result: HttpResponse) -> None:
        """HTTP 请求成功回调
        
        Args:
            context: 任务执行上下文
            result: HTTP 响应
        """
        logger.debug(
            f"[{context.run_id}] HTTP job success: "
            f"status={result.status_code}"
        )
    
    async def on_error(self, context: JobContext, error: Exception) -> None:
        """HTTP 请求失败回调
        
        Args:
            context: 任务执行上下文
            error: 异常对象
        """
        logger.error(f"[{context.run_id}] HTTP job failed: {error}")


class HttpJobError(Exception):
    """HTTP 任务错误（不重试）"""
    
    def __init__(self, message: str, response: Optional[HttpResponse] = None):
        super().__init__(message)
        self.response = response


class HttpRetryError(Exception):
    """HTTP 任务错误（需要重试）"""
    
    def __init__(self, message: str, response: Optional[HttpResponse] = None):
        super().__init__(message)
        self.response = response


@dataclass
class HttpJobConfig:
    """HTTP 任务配置（用于动态创建）"""
    
    url: str
    method: str = "GET"
    headers: Dict[str, str] = field(default_factory=dict)
    body: Optional[Union[Dict, str]] = None
    timeout: int = 30
    success_codes: list = field(default_factory=lambda: [200, 201, 202, 204])
    retry_codes: list = field(default_factory=lambda: [429, 500, 502, 503, 504])


def create_http_job_class(
    config: HttpJobConfig,
    code: str,
    trigger,
    name: Optional[str] = None,
    description: Optional[str] = None,
    max_retries: int = 0,
) -> type:
    """动态创建 HttpJob 类
    
    Args:
        config: HTTP 配置
        code: 任务编码
        trigger: 触发器
        name: 任务名称
        description: 任务描述
        max_retries: 最大重试次数
    
    Returns:
        HttpJob 子类
    """
    class DynamicHttpJob(HttpJob):
        pass
    
    DynamicHttpJob.code = code
    DynamicHttpJob.trigger = trigger
    DynamicHttpJob.name = name
    DynamicHttpJob.description = description
    DynamicHttpJob.url = config.url
    DynamicHttpJob.method = config.method
    DynamicHttpJob.headers = config.headers
    DynamicHttpJob.timeout = config.timeout
    DynamicHttpJob.success_codes = config.success_codes
    DynamicHttpJob.retry_codes = config.retry_codes
    DynamicHttpJob.max_retries = max_retries
    
    # 如果有固定的 body
    if config.body is not None:
        original_body = config.body
        DynamicHttpJob.get_body = lambda self, ctx: original_body
    
    return DynamicHttpJob
