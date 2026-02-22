"""触发器函数测试

测试 cron(), interval(), once() 触发器的创建和解析。
"""

import pytest
from datetime import datetime, timedelta

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger

from yweb.scheduler import cron, interval, once


class TestCronTrigger:
    """Cron 触发器测试"""
    
    def test_cron_expression_5_parts(self):
        """测试5位 Cron 表达式"""
        # 分 时 日 月 周
        trigger = cron("0 8 * * *")  # 每天8点
        
        assert isinstance(trigger, CronTrigger)
        next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 1, 7, 30, 0))
        assert next_run.hour == 8
        assert next_run.minute == 0
        assert next_run.second == 0
    
    def test_cron_expression_6_parts(self):
        """测试6位 Cron 表达式"""
        # 秒 分 时 日 月 周
        trigger = cron("30 0 8 * * *")  # 每天8:00:30
        
        assert isinstance(trigger, CronTrigger)
        next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 1, 7, 59, 0))
        assert next_run.hour == 8
        assert next_run.minute == 0
        assert next_run.second == 30
    
    def test_cron_every_5_minutes(self):
        """测试每5分钟执行"""
        trigger = cron("*/5 * * * *")
        
        assert isinstance(trigger, CronTrigger)
        next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 1, 8, 2, 10))
        assert next_run.minute == 5
        assert next_run.second == 0
    
    def test_cron_workdays(self):
        """测试工作日执行"""
        trigger = cron("0 9 * * 1-5")  # 工作日9点
        
        assert isinstance(trigger, CronTrigger)
        # 2026-01-03 是周六，下一次应在工作日
        next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 3, 10, 0, 0))
        assert next_run.weekday() < 5
        assert next_run.hour == 9
    
    def test_cron_with_kwargs(self):
        """测试关键字参数方式"""
        trigger = cron(hour=8, minute=30)
        
        assert isinstance(trigger, CronTrigger)
        next_run = trigger.get_next_fire_time(None, datetime(2026, 1, 1, 8, 0, 0))
        assert next_run.hour == 8
        assert next_run.minute == 30
    
    def test_cron_with_day_of_week(self):
        """测试指定星期"""
        trigger = cron(hour=9, day_of_week="mon,wed,fri")
        
        assert isinstance(trigger, CronTrigger)
    
    def test_cron_with_timezone(self):
        """测试指定时区"""
        trigger = cron("0 8 * * *", timezone="Asia/Shanghai")
        
        assert isinstance(trigger, CronTrigger)
        assert str(trigger.timezone) == "Asia/Shanghai"
    
    def test_cron_invalid_expression(self):
        """测试无效表达式"""
        with pytest.raises(ValueError) as exc_info:
            cron("0 8 *")  # 只有3部分，无效
        
        assert "Invalid cron expression" in str(exc_info.value)


class TestIntervalTrigger:
    """间隔触发器测试"""
    
    def test_interval_seconds(self):
        """测试秒间隔"""
        trigger = interval(seconds=30)
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 30
    
    def test_interval_minutes(self):
        """测试分钟间隔"""
        trigger = interval(minutes=5)
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 5 * 60
    
    def test_interval_hours(self):
        """测试小时间隔"""
        trigger = interval(hours=1)
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 3600
    
    def test_interval_days(self):
        """测试天数间隔"""
        trigger = interval(days=1)
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 86400
    
    def test_interval_weeks(self):
        """测试周数间隔"""
        trigger = interval(weeks=1)
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 7 * 86400
    
    def test_interval_combined(self):
        """测试组合间隔"""
        trigger = interval(hours=1, minutes=30)  # 1小时30分钟
        
        assert isinstance(trigger, IntervalTrigger)
        assert trigger.interval.total_seconds() == 90 * 60
    
    def test_interval_with_start_date(self):
        """测试指定开始时间"""
        start = datetime(2026, 1, 22, 0, 0, 0)
        trigger = interval(minutes=5, start_date=start)
        
        assert isinstance(trigger, IntervalTrigger)
    
    def test_interval_with_end_date(self):
        """测试指定结束时间"""
        end = datetime(2026, 12, 31, 23, 59, 59)
        trigger = interval(hours=1, end_date=end)
        
        assert isinstance(trigger, IntervalTrigger)


class TestOnceTrigger:
    """一次性触发器测试"""
    
    def test_once_with_datetime(self):
        """测试 datetime 对象"""
        run_date = datetime(2026, 12, 31, 23, 59, 59)
        trigger = once(run_date=run_date)
        
        assert isinstance(trigger, DateTrigger)
    
    def test_once_with_string(self):
        """测试字符串时间"""
        trigger = once("2026-12-31 23:59:59")
        
        assert isinstance(trigger, DateTrigger)
    
    def test_once_future_date(self):
        """测试未来时间"""
        future = datetime.now() + timedelta(hours=1)
        trigger = once(run_date=future)
        
        assert isinstance(trigger, DateTrigger)
    
    def test_once_with_timezone(self):
        """测试指定时区"""
        trigger = once("2026-12-31 23:59:59", timezone="Asia/Shanghai")
        
        assert isinstance(trigger, DateTrigger)
    
    def test_once_without_run_date(self):
        """测试缺少 run_date 参数"""
        with pytest.raises(ValueError) as exc_info:
            once()
        
        assert "run_date is required" in str(exc_info.value)
