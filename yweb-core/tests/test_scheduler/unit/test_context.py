"""执行上下文测试

测试 JobContext 类的功能。
"""

import pytest
from datetime import datetime

from yweb.scheduler import JobContext


class TestJobContext:
    """JobContext 测试"""
    
    def test_basic_context(self):
        """测试基本上下文创建"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
        )
        
        assert context.job_id == "job_123"
        assert context.job_code == "DAILY_REPORT"
        assert context.job_name == "每日报表"
        assert context.attempt == 1
        assert context.trigger_type == "scheduled"
    
    def test_context_with_run_id(self):
        """测试带执行ID的上下文"""
        context = JobContext(
            job_id="job_123",
            job_code="SYNC_DATA",
            job_name="数据同步",
            run_id="run_20260121_080000_abc123",
        )
        
        assert context.run_id == "run_20260121_080000_abc123"
    
    def test_context_with_description(self):
        """测试带描述的上下文"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            job_description="每天早上8点生成销售报表",
        )
        
        assert context.job_description == "每天早上8点生成销售报表"
    
    def test_context_with_times(self):
        """测试带时间信息的上下文"""
        scheduled = datetime(2026, 1, 21, 8, 0, 0)
        started = datetime(2026, 1, 21, 8, 0, 1)
        
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            scheduled_time=scheduled,
            start_time=started,
        )
        
        assert context.scheduled_time == scheduled
        assert context.start_time == started
    
    def test_context_retry(self):
        """测试重试上下文"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_20260121_080100_xyz789",
            attempt=2,
            trigger_type="retry",
            retry_of="run_20260121_080000_abc123",
        )
        
        assert context.attempt == 2
        assert context.trigger_type == "retry"
        assert context.retry_of == "run_20260121_080000_abc123"
    
    def test_context_manual_trigger(self):
        """测试手动触发上下文"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            trigger_type="manual",
        )
        
        assert context.trigger_type == "manual"
    
    def test_context_run_count(self):
        """测试累计执行次数"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_count=100,
        )
        
        assert context.run_count == 100
    
    def test_context_extra_data(self):
        """测试额外数据"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            extra={"key1": "value1", "key2": 123},
        )
        
        assert context.extra["key1"] == "value1"
        assert context.extra["key2"] == 123
    
    def test_context_str(self):
        """测试字符串表示"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc",
            attempt=1,
        )
        
        str_repr = str(context)
        
        assert "DAILY_REPORT" in str_repr
        assert "run_abc" in str_repr
    
    def test_context_repr(self):
        """测试 repr 表示"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
            run_id="run_abc",
        )
        
        repr_str = repr(context)
        
        assert "DAILY_REPORT" in repr_str
    
    def test_context_default_extra(self):
        """测试 extra 默认值"""
        context = JobContext(
            job_id="job_123",
            job_code="DAILY_REPORT",
            job_name="每日报表",
        )
        
        # 默认应该是空字典
        assert context.extra == {}
        
        # 可以添加数据
        context.extra["test"] = "value"
        assert context.extra["test"] == "value"
