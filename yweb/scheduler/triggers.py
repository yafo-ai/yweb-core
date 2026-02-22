"""触发器快捷函数

提供简洁的触发器创建函数。

使用示例:
    from yweb.scheduler import cron, interval, once
    
    # Cron 表达式
    cron("0 8 * * *")           # 每天 8:00
    cron(hour=8, minute=0)       # 每天 8:00（关键字参数）
    
    # 时间间隔
    interval(minutes=30)         # 每30分钟
    interval(hours=1)            # 每小时
    
    # 一次性任务
    once("2026-12-31 23:59:59")  # 指定时间
    once(run_date=datetime.now() + timedelta(hours=1))  # 1小时后
"""

from datetime import datetime
from typing import Optional, Union
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.date import DateTrigger


def cron(
    expression: Optional[str] = None,
    *,
    year: Optional[Union[int, str]] = None,
    month: Optional[Union[int, str]] = None,
    day: Optional[Union[int, str]] = None,
    week: Optional[Union[int, str]] = None,
    day_of_week: Optional[Union[int, str]] = None,
    hour: Optional[Union[int, str]] = None,
    minute: Optional[Union[int, str]] = None,
    second: Optional[Union[int, str]] = None,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    timezone: Optional[str] = None,
) -> CronTrigger:
    """创建 Cron 触发器
    
    支持两种方式：
    1. Cron 表达式字符串：cron("0 8 * * *")
    2. 关键字参数：cron(hour=8, minute=0)
    
    Args:
        expression: Cron 表达式（5位或6位）
            - 5位: 分 时 日 月 周
            - 6位: 秒 分 时 日 月 周
        year: 年
        month: 月 (1-12)
        day: 日 (1-31)
        week: 周 (1-53)
        day_of_week: 星期 (0-6 或 mon,tue,wed,thu,fri,sat,sun)
        hour: 时 (0-23)
        minute: 分 (0-59)
        second: 秒 (0-59)
        start_date: 开始日期
        end_date: 结束日期
        timezone: 时区
    
    Returns:
        CronTrigger 实例
    
    Examples:
        # Cron 表达式
        cron("0 8 * * *")           # 每天 8:00
        cron("*/5 * * * *")         # 每5分钟
        cron("0 9-17 * * 1-5")      # 工作日 9:00-17:00 每小时
        
        # 关键字参数
        cron(hour=8, minute=0)                    # 每天 8:00
        cron(day_of_week="mon-fri", hour=9)       # 工作日 9:00
        cron(day=1, hour=0, minute=0)             # 每月1号 0:00
    """
    if expression:
        # 解析 Cron 表达式
        parts = expression.split()
        if len(parts) == 5:
            # 5位: 分 时 日 月 周
            minute, hour, day, month, day_of_week = parts
            second = "0"
        elif len(parts) == 6:
            # 6位: 秒 分 时 日 月 周
            second, minute, hour, day, month, day_of_week = parts
        else:
            raise ValueError(f"Invalid cron expression: {expression}. Expected 5 or 6 parts.")
        
        return CronTrigger(
            second=second,
            minute=minute,
            hour=hour,
            day=day,
            month=month,
            day_of_week=day_of_week,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )
    else:
        # 使用关键字参数
        return CronTrigger(
            year=year,
            month=month,
            day=day,
            week=week,
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            second=second or 0,
            start_date=start_date,
            end_date=end_date,
            timezone=timezone,
        )


def interval(
    weeks: int = 0,
    days: int = 0,
    hours: int = 0,
    minutes: int = 0,
    seconds: int = 0,
    start_date: Optional[Union[str, datetime]] = None,
    end_date: Optional[Union[str, datetime]] = None,
    timezone: Optional[str] = None,
) -> IntervalTrigger:
    """创建间隔触发器
    
    Args:
        weeks: 周数
        days: 天数
        hours: 小时数
        minutes: 分钟数
        seconds: 秒数
        start_date: 开始日期
        end_date: 结束日期
        timezone: 时区
    
    Returns:
        IntervalTrigger 实例
    
    Examples:
        interval(seconds=30)            # 每30秒
        interval(minutes=5)             # 每5分钟
        interval(hours=1)               # 每小时
        interval(days=1)                # 每天
        interval(weeks=1)               # 每周
        interval(minutes=5, start_date="2026-01-22 00:00:00")  # 指定开始时间
    """
    return IntervalTrigger(
        weeks=weeks,
        days=days,
        hours=hours,
        minutes=minutes,
        seconds=seconds,
        start_date=start_date,
        end_date=end_date,
        timezone=timezone,
    )


def once(
    run_date: Optional[Union[str, datetime]] = None,
    timezone: Optional[str] = None,
) -> DateTrigger:
    """创建一次性触发器
    
    Args:
        run_date: 执行时间（字符串或 datetime 对象）
        timezone: 时区
    
    Returns:
        DateTrigger 实例
    
    Examples:
        once("2026-12-31 23:59:59")                           # 指定时间字符串
        once(datetime(2026, 12, 31, 23, 59, 59))              # datetime 对象
        once(run_date=datetime.now() + timedelta(hours=1))   # 1小时后
    """
    if run_date is None:
        raise ValueError("run_date is required for once trigger")
    
    return DateTrigger(
        run_date=run_date,
        timezone=timezone,
    )
