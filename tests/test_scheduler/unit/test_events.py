"""事件类测试

测试任务执行过程中的事件类。
"""

import pytest
from datetime import datetime

from yweb.scheduler.events import (
    JobEvent,
    JobExecutedEvent,
    JobErrorEvent,
    JobRetryEvent,
    JobMissedEvent,
    JobPausedEvent,
    JobResumedEvent,
)


class TestJobEvent:
    """JobEvent 基类测试"""
    
    def test_basic_event(self):
        """测试基本事件创建"""
        event = JobEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
        )
        
        assert event.job_id == "job_123"
        assert event.job_code == "DAILY_REPORT"
        assert event.job_name == "每日报表"
        assert event.run_id == "run_abc123"
        assert event.attempt == 1
        assert event.trigger_type == "scheduled"
    
    def test_event_with_times(self):
        """测试带时间的事件"""
        scheduled = datetime(2026, 1, 21, 8, 0, 0)
        started = datetime(2026, 1, 21, 8, 0, 1)
        
        event = JobEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            scheduled_time=scheduled,
            start_time=started,
        )
        
        assert event.scheduled_time == scheduled
        assert event.start_time == started


class TestJobExecutedEvent:
    """JobExecutedEvent 测试"""
    
    def test_executed_event(self):
        """测试执行成功事件"""
        event = JobExecutedEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            duration_ms=1500,
            result={"status": "ok"},
        )
        
        assert event.duration_ms == 1500
        assert event.result == {"status": "ok"}
    
    def test_executed_event_with_end_time(self):
        """测试带结束时间的成功事件"""
        started = datetime(2026, 1, 21, 8, 0, 0)
        ended = datetime(2026, 1, 21, 8, 0, 2)
        
        event = JobExecutedEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            start_time=started,
            end_time=ended,
            duration_ms=2000,
        )
        
        assert event.start_time == started
        assert event.end_time == ended
        assert event.duration_ms == 2000


class TestJobErrorEvent:
    """JobErrorEvent 测试"""
    
    def test_error_event(self):
        """测试执行失败事件"""
        event = JobErrorEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            error="Database connection failed",
            duration_ms=500,
        )
        
        assert event.error == "Database connection failed"
        assert event.duration_ms == 500
    
    def test_error_event_with_traceback(self):
        """测试带堆栈的失败事件"""
        event = JobErrorEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            error="ValueError: invalid value",
            traceback="Traceback (most recent call last):\n  File ...\nValueError: invalid value",
        )
        
        assert event.error == "ValueError: invalid value"
        assert "Traceback" in event.traceback
    
    def test_error_event_with_exception(self):
        """测试带异常对象的失败事件"""
        exc = ValueError("invalid value")
        
        event = JobErrorEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            error=str(exc),
            exception=exc,
        )
        
        assert event.exception is exc
        assert isinstance(event.exception, ValueError)


class TestJobRetryEvent:
    """JobRetryEvent 测试"""
    
    def test_retry_event(self):
        """测试重试事件"""
        next_retry = datetime(2026, 1, 21, 8, 1, 0)
        
        event = JobRetryEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            error="Connection timeout",
            attempt=2,
            max_retries=3,
            next_retry_time=next_retry,
        )
        
        assert event.error == "Connection timeout"
        assert event.attempt == 2
        assert event.max_retries == 3
        assert event.next_retry_time == next_retry


class TestJobMissedEvent:
    """JobMissedEvent 测试"""
    
    def test_missed_event(self):
        """测试错过执行事件"""
        scheduled = datetime(2026, 1, 21, 8, 0, 0)
        
        event = JobMissedEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc123",
            scheduled_time=scheduled,
        )
        
        assert event.scheduled_time == scheduled


class TestJobPausedEvent:
    """JobPausedEvent 测试"""
    
    def test_paused_event(self):
        """测试暂停事件"""
        event = JobPausedEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="",
        )
        
        assert event.job_code == "DAILY_REPORT"


class TestJobResumedEvent:
    """JobResumedEvent 测试"""
    
    def test_resumed_event(self):
        """测试恢复事件"""
        event = JobResumedEvent(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="",
        )
        
        assert event.job_code == "DAILY_REPORT"
