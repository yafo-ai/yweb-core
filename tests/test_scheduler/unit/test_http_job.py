"""HttpJob 测试

测试 HTTP 任务功能。
"""

import pytest
from unittest.mock import Mock, AsyncMock, patch

from yweb.scheduler import HttpJob, cron, interval, JobContext
from yweb.scheduler.http_job import (
    HttpJobConfig, 
    HttpResponse, 
    HttpJobError, 
    HttpRetryError,
    create_http_job_class,
)


class TestHttpResponse:
    """HttpResponse 测试"""
    
    def test_ok_response(self):
        """测试成功响应"""
        response = HttpResponse(
            status_code=200,
            body='{"status": "ok"}',
            headers={"content-type": "application/json"},
        )
        
        assert response.ok == True
        assert response.status_code == 200
    
    def test_not_ok_response(self):
        """测试失败响应"""
        response = HttpResponse(status_code=500)
        
        assert response.ok == False
    
    def test_json_parsing(self):
        """测试 JSON 解析"""
        response = HttpResponse(
            status_code=200,
            body='{"key": "value"}',
        )
        
        data = response.json()
        assert data == {"key": "value"}
    
    def test_repr(self):
        """测试字符串表示"""
        response = HttpResponse(status_code=200)
        repr_str = repr(response)
        
        assert "200" in repr_str
        assert "ok=True" in repr_str


class TestHttpJobClass:
    """HttpJob 类测试"""
    
    def test_simple_http_job(self):
        """测试简单 HTTP 任务定义"""
        class SimpleHttpJob(HttpJob):
            code = "SIMPLE_HTTP"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com/test"
        
        job = SimpleHttpJob()
        assert job.code == "SIMPLE_HTTP"
        assert job.url == "https://api.example.com/test"
        assert job.method == "GET"
    
    def test_http_job_with_config(self):
        """测试完整配置的 HTTP 任务"""
        class FullHttpJob(HttpJob):
            code = "FULL_HTTP"
            trigger = interval(hours=1)
            url = "https://api.example.com/webhook"
            method = "POST"
            headers = {"Authorization": "Bearer token"}
            timeout = 60
            success_codes = [200, 201]
            retry_codes = [500, 502, 503]
        
        job = FullHttpJob()
        assert job.method == "POST"
        assert job.headers["Authorization"] == "Bearer token"
        assert job.timeout == 60
        assert 200 in job.success_codes
    
    def test_http_job_without_url_raises(self):
        """测试缺少 URL 抛出错误"""
        class NoUrlJob(HttpJob):
            code = "NO_URL"
            trigger = cron("0 8 * * *")
        
        with pytest.raises(ValueError) as exc_info:
            NoUrlJob()
        
        assert "url" in str(exc_info.value).lower()
    
    def test_get_url(self):
        """测试获取 URL 方法"""
        class UrlJob(HttpJob):
            code = "URL_JOB"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com"
        
        job = UrlJob()
        context = JobContext(job_id="test", job_code="URL_JOB", job_name="test")
        
        assert job.get_url(context) == "https://api.example.com"
    
    def test_get_headers(self):
        """测试获取请求头方法"""
        class HeaderJob(HttpJob):
            code = "HEADER_JOB"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com"
            headers = {"X-Custom": "value"}
        
        job = HeaderJob()
        context = JobContext(job_id="test", job_code="HEADER_JOB", job_name="test")
        
        headers = job.get_headers(context)
        assert headers["X-Custom"] == "value"
    
    def test_get_body_default_none(self):
        """测试默认请求体为 None"""
        class BodyJob(HttpJob):
            code = "BODY_JOB"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com"
        
        job = BodyJob()
        context = JobContext(job_id="test", job_code="BODY_JOB", job_name="test")
        
        assert job.get_body(context) is None
    
    def test_custom_get_body(self):
        """测试自定义请求体"""
        class CustomBodyJob(HttpJob):
            code = "CUSTOM_BODY"
            trigger = cron("0 8 * * *")
            url = "https://api.example.com"
            
            def get_body(self, context):
                return {"timestamp": "2026-01-21"}
        
        job = CustomBodyJob()
        context = JobContext(job_id="test", job_code="CUSTOM_BODY", job_name="test")
        
        body = job.get_body(context)
        assert body == {"timestamp": "2026-01-21"}


class TestHttpJobConfig:
    """HttpJobConfig 测试"""
    
    def test_config_defaults(self):
        """测试配置默认值"""
        config = HttpJobConfig(url="https://example.com")
        
        assert config.url == "https://example.com"
        assert config.method == "GET"
        assert config.headers == {}
        assert config.body is None
        assert config.timeout == 30
        assert 200 in config.success_codes
    
    def test_config_custom(self):
        """测试自定义配置"""
        config = HttpJobConfig(
            url="https://api.example.com",
            method="POST",
            headers={"Content-Type": "application/json"},
            body={"key": "value"},
            timeout=60,
        )
        
        assert config.method == "POST"
        assert config.body == {"key": "value"}
        assert config.timeout == 60


class TestCreateHttpJobClass:
    """动态创建 HttpJob 类测试"""
    
    def test_create_basic(self):
        """测试基本创建"""
        config = HttpJobConfig(url="https://example.com")
        trigger = cron("0 8 * * *")
        
        job_class = create_http_job_class(
            config=config,
            code="DYNAMIC_HTTP",
            trigger=trigger,
            name="动态 HTTP 任务",
        )
        
        job = job_class()
        assert job.code == "DYNAMIC_HTTP"
        assert job.url == "https://example.com"
    
    def test_create_with_body(self):
        """测试带请求体的创建"""
        config = HttpJobConfig(
            url="https://example.com",
            method="POST",
            body={"action": "sync"},
        )
        trigger = cron("0 8 * * *")
        
        job_class = create_http_job_class(
            config=config,
            code="BODY_HTTP",
            trigger=trigger,
        )
        
        job = job_class()
        context = JobContext(job_id="test", job_code="BODY_HTTP", job_name="test")
        
        assert job.get_body(context) == {"action": "sync"}


class TestSchedulerHttpJobIntegration:
    """Scheduler 与 HttpJob 集成测试"""
    
    def test_add_http_job_method_exists(self):
        """测试 add_http_job 方法存在"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        assert hasattr(scheduler, 'add_http_job')
        assert callable(scheduler.add_http_job)
    
    def test_add_http_job(self):
        """测试添加 HTTP 任务"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        code = scheduler.add_http_job(
            url="https://api.example.com/health",
            trigger=interval(minutes=5),
            code="HEALTH_CHECK",
            method="GET",
        )
        
        assert code == "HEALTH_CHECK"
        assert "HEALTH_CHECK" in scheduler._jobs
    
    def test_add_http_job_auto_code(self):
        """测试自动生成任务编码"""
        from yweb.scheduler import Scheduler
        
        scheduler = Scheduler()
        
        code = scheduler.add_http_job(
            url="https://api.example.com/sync",
            trigger=interval(hours=1),
        )
        
        # 应该从 URL 生成 code
        assert "API_EXAMPLE_COM" in code.upper()
