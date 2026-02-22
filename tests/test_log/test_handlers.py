"""日志处理器测试

测试自定义日志处理器的功能
"""

import pytest
import os
import logging
import time
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from yweb.log import (
    TimeAndSizeRotatingFileHandler,
    DailyRotatingFileHandler,
)


class TestTimeAndSizeRotatingFileHandler:
    """TimeAndSizeRotatingFileHandler 测试"""
    
    def test_create_handler(self, log_dir):
        """测试创建处理器"""
        log_file = os.path.join(log_dir, "test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,  # 1MB
            backupCount=5
        )
        
        assert handler is not None
        # 关键配置应被正确保存，避免“仅创建成功”式浅层测试
        assert handler.maxBytes == 1024 * 1024
        assert handler.backupCount == 5
        assert "{date}" in handler.filename_template
        assert "{date}" not in handler.baseFilename
        handler.close()
    
    def test_handler_creates_file(self, log_dir):
        """测试处理器创建日志文件"""
        log_file = os.path.join(log_dir, "create_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 创建一个 logger 并写入日志
        logger = logging.getLogger("test_create")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        logger.info("Test message")
        handler.flush()
        
        # 检查是否创建了带日期的文件
        files = os.listdir(log_dir)
        assert any("create_test_" in f and f.endswith(".log") for f in files)
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_handler_writes_message(self, log_dir):
        """测试处理器写入消息"""
        log_file = os.path.join(log_dir, "write_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        logger = logging.getLogger("test_write")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        test_message = "This is a test log message"
        logger.info(test_message)
        handler.flush()
        
        # 查找创建的文件并验证内容
        files = [f for f in os.listdir(log_dir) if f.startswith("write_test_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            content = f.read()
            assert test_message in content
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_size_rotation(self, log_dir):
        """测试按大小轮转"""
        log_file = os.path.join(log_dir, "size_rotation_{date}.log")
        
        # 设置很小的文件大小限制
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=500,  # 500 bytes
            backupCount=3
        )
        
        logger = logging.getLogger("test_size_rotation")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        # 写入足够多的消息触发轮转
        for i in range(100):
            logger.info(f"Log message number {i}: " + "x" * 50)
        
        handler.flush()
        
        # 检查是否有备份文件
        backup_files = [f for f in os.listdir(log_dir) if f.startswith("size_rotation_")]
        
        # 应该有多个文件（原始 + 备份）
        assert len(backup_files) >= 1
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_backup_count_limit(self, log_dir):
        """测试备份数量限制"""
        log_file = os.path.join(log_dir, "backup_limit_{date}.log")
        backup_count = 2
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=200,
            backupCount=backup_count
        )
        
        logger = logging.getLogger("test_backup_limit")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        # 写入大量消息
        for i in range(100):
            logger.info(f"Message {i}: " + "x" * 100)
        
        handler.flush()
        
        # 备份文件数量不应超过 backup_count
        backup_files = [f for f in os.listdir(log_dir) 
                       if f.startswith("backup_limit_") and ".log." in f]
        
        assert len(backup_files) <= backup_count
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_encoding_support(self, log_dir):
        """测试编码支持"""
        log_file = os.path.join(log_dir, "encoding_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            encoding="utf-8"
        )
        
        logger = logging.getLogger("test_encoding")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        # 写入中文消息
        logger.info("这是中文日志消息")
        logger.info("日志测试：成功！")
        handler.flush()
        
        # 查找创建的文件并验证内容
        files = [f for f in os.listdir(log_dir) if f.startswith("encoding_test_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r', encoding='utf-8') as f:
            content = f.read()
            assert "中文" in content
        
        logger.removeHandler(handler)
        handler.close()


class TestDailyRotatingFileHandler:
    """DailyRotatingFileHandler 测试"""
    
    def test_create_handler(self, log_dir):
        """测试创建处理器"""
        log_file = os.path.join(log_dir, "daily_{date}.log")
        
        handler = DailyRotatingFileHandler(
            filename=log_file,
            backupCount=7
        )
        
        assert handler is not None
        assert handler.maxBytes == 0
        assert handler.backupCount == 7
        assert "{date}" in handler.filename_template
        assert "{date}" not in handler.baseFilename
        handler.close()
    
    def test_handler_writes_message(self, log_dir):
        """测试处理器写入消息"""
        log_file = os.path.join(log_dir, "daily_write_{date}.log")
        
        handler = DailyRotatingFileHandler(
            filename=log_file,
            backupCount=7
        )
        
        logger = logging.getLogger("test_daily_write")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        logger.info("Daily log message")
        handler.flush()
        
        # 查找创建的文件并验证内容
        files = [f for f in os.listdir(log_dir) if f.startswith("daily_write_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            content = f.read()
            assert "Daily log message" in content
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_date_in_filename(self, log_dir):
        """测试文件名包含日期"""
        log_file = os.path.join(log_dir, "dated_{date}.log")
        
        handler = DailyRotatingFileHandler(
            filename=log_file,
            backupCount=7
        )
        
        logger = logging.getLogger("test_dated")
        logger.setLevel(logging.DEBUG)
        logger.addHandler(handler)
        
        logger.info("Test message")
        handler.flush()
        
        # 检查是否创建了带日期的文件
        files = os.listdir(log_dir)
        dated_files = [f for f in files if f.startswith("dated_") and f.endswith(".log")]
        
        assert len(dated_files) >= 1
        # 检查文件名包含日期格式 (YYYY-MM-DD)
        from datetime import datetime
        today = datetime.now().strftime("%Y-%m-%d")
        assert any(today in f for f in dated_files)
        
        logger.removeHandler(handler)
        handler.close()


class TestLoggerSetup:
    """日志设置测试"""
    
    def test_setup_logger(self, log_dir):
        """测试设置日志器"""
        from yweb.log import setup_logger
        import os
        
        log_file = os.path.join(log_dir, "setup_test.log")
        
        logger = setup_logger(
            name="test_setup",
            level="DEBUG",
            log_file=log_file,
            console=False
        )
        
        assert logger is not None
        assert logger.level == logging.DEBUG
        
        # 清理：关闭所有处理器以释放文件锁
        for handler in logger.handlers[:]:
            handler.close()
            logger.removeHandler(handler)
    
    def test_get_logger(self):
        """测试获取日志器"""
        from yweb.log import get_logger
        
        # 测试显式指定名称（自动添加 yweb 前缀）
        logger1 = get_logger("module1")
        logger2 = get_logger("module2")
        
        assert logger1 is not None
        assert logger2 is not None
        assert logger1 is not logger2
        # 验证自动添加了 yweb 前缀
        assert logger1.name == "yweb.module1"
        assert logger2.name == "yweb.module2"
    
    def test_get_logger_auto_infer(self):
        """测试自动推断模块名"""
        from yweb.log import get_logger
        
        # 无参数调用，应该自动从调用栈获取 __name__
        logger = get_logger()
        
        assert logger is not None
        # 在测试文件中调用，应该得到测试模块的名称
        assert logger.name == __name__
    
    def test_get_logger_with_prefix(self):
        """测试已有 yweb 前缀不重复添加"""
        from yweb.log import get_logger
        
        logger = get_logger("yweb.custom")
        
        assert logger.name == "yweb.custom"
    
    def test_get_logger_external_module(self):
        """测试外部模块名不添加前缀"""
        from yweb.log import get_logger
        
        # 包含点号的外部模块名不添加前缀
        logger = get_logger("sqlalchemy.engine")
        
        assert logger.name == "sqlalchemy.engine"
    
    def test_api_logger(self):
        """测试 API 日志器"""
        from yweb.log import api_logger
        
        assert api_logger is not None
        assert "api" in api_logger.name.lower() or "yweb" in api_logger.name.lower()
    
    def test_auth_logger(self):
        """测试认证日志器"""
        from yweb.log import auth_logger
        
        assert auth_logger is not None
        assert "auth" in auth_logger.name.lower() or "yweb" in auth_logger.name.lower()
    
    def test_sql_logger(self):
        """测试 SQL 日志器"""
        from yweb.log import sql_logger
        
        assert sql_logger is not None


class TestLoggerMultipleHandlers:
    """多处理器测试"""
    
    def test_console_and_file_handlers(self, log_dir):
        """测试同时使用控制台和文件处理器"""
        log_file = os.path.join(log_dir, "multi_handler_{date}.log")
        
        logger = logging.getLogger("test_multi_handler")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        
        # 添加文件处理器
        file_handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        file_handler.setLevel(logging.INFO)
        logger.addHandler(file_handler)
        
        # 添加控制台处理器
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        logger.addHandler(console_handler)
        
        # 写入日志
        logger.debug("Debug message")  # 只输出到控制台
        logger.info("Info message")    # 输出到两者
        
        file_handler.flush()
        
        # 查找创建的文件并验证内容
        files = [f for f in os.listdir(log_dir) if f.startswith("multi_handler_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            content = f.read()
            assert "Info message" in content
            assert "Debug message" not in content  # 文件处理器级别是 INFO
        
        logger.removeHandler(file_handler)
        logger.removeHandler(console_handler)
        file_handler.close()


class TestDateChangeRollover:
    """日期切换自动轮转测试
    
    测试当日期变化时（跨午夜），日志系统是否自动创建新的日期文件
    """
    
    def test_date_change_creates_new_file(self, log_dir):
        """测试日期变化时自动创建新日期文件"""
        today = datetime.now()
        tomorrow = today + timedelta(days=1)
        
        today_str = today.strftime("%Y-%m-%d")
        tomorrow_str = tomorrow.strftime("%Y-%m-%d")
        
        log_file = os.path.join(log_dir, "date_change_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        logger = logging.getLogger("test_date_change")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入今天的日志
        logger.info("Message from today")
        handler.flush()
        
        # 验证今天的文件存在
        today_file = os.path.join(log_dir, f"date_change_test_{today_str}.log")
        assert os.path.exists(today_file), f"今天的日志文件应该存在: {today_file}"
        
        # 模拟日期变化：直接修改 rollover_at 为过去的时间，触发轮转
        handler.rollover_at = time.time() - 1  # 设置为过去的时间
        handler.current_date = today_str  # 确保当前日期是今天
        
        # 使用 patch 模拟明天的日期
        with patch('yweb.log.handlers.datetime') as mock_datetime:
            mock_datetime.now.return_value = tomorrow
            mock_datetime.strptime = datetime.strptime
            
            # 写入新日志，这应该触发日期轮转
            logger.info("Message from tomorrow")
            handler.flush()
        
        # 验证明天的文件被创建
        tomorrow_file = os.path.join(log_dir, f"date_change_test_{tomorrow_str}.log")
        assert os.path.exists(tomorrow_file), f"明天的日志文件应该被创建: {tomorrow_file}"
        
        # 验证两个文件内容
        with open(today_file, 'r') as f:
            today_content = f.read()
            assert "Message from today" in today_content
        
        with open(tomorrow_file, 'r') as f:
            tomorrow_content = f.read()
            assert "Message from tomorrow" in tomorrow_content
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_rollover_at_midnight_calculation(self, log_dir):
        """测试午夜轮转时间计算"""
        log_file = os.path.join(log_dir, "midnight_calc_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            when='midnight'
        )
        
        # 验证 rollover_at 是明天午夜的时间戳
        now = datetime.now()
        tomorrow_midnight = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
        expected_rollover = tomorrow_midnight.timestamp()
        
        # 允许1秒的误差
        assert abs(handler.rollover_at - expected_rollover) < 1, \
            f"rollover_at 应该接近明天午夜，期望: {expected_rollover}，实际: {handler.rollover_at}"
        
        handler.close()
    
    def test_should_rollover_on_time(self, log_dir):
        """测试 shouldRollover 在时间到达时返回 True"""
        log_file = os.path.join(log_dir, "should_rollover_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        logger = logging.getLogger("test_should_rollover")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入一条日志确保文件被创建
        logger.info("Initial message")
        handler.flush()
        
        # 创建一个模拟的日志记录
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="Test",
            args=(),
            exc_info=None
        )
        
        # 正常情况下不应该轮转
        assert handler.shouldRollover(record) == 0, "正常情况下不应该需要轮转"
        
        # 设置 rollover_at 为过去的时间
        handler.rollover_at = time.time() - 100
        
        # 现在应该需要轮转
        assert handler.shouldRollover(record) == 1, "时间到达后应该需要轮转"
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_current_date_tracking(self, log_dir):
        """测试当前日期跟踪"""
        log_file = os.path.join(log_dir, "date_tracking_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 验证 current_date 是今天的日期
        today_str = datetime.now().strftime("%Y-%m-%d")
        assert handler.current_date == today_str, \
            f"current_date 应该是今天: {today_str}，实际: {handler.current_date}"
        
        handler.close()
    
    def test_filename_template_preserved(self, log_dir):
        """测试文件名模板被保留"""
        log_file = os.path.join(log_dir, "template_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 验证文件名模板被保留
        assert handler.filename_template == log_file
        assert "{date}" in handler.filename_template
        
        # 验证实际文件名包含日期
        today_str = datetime.now().strftime("%Y-%m-%d")
        assert today_str in handler.baseFilename
        assert "{date}" not in handler.baseFilename
        
        handler.close()
    
    def test_multiple_days_simulation(self, log_dir):
        """测试模拟多天日志记录"""
        log_file = os.path.join(log_dir, "multi_day_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            delay=True  # 延迟打开避免文件锁
        )
        
        logger = logging.getLogger("test_multi_day")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 模拟3天的日志
        base_date = datetime.now()
        created_files = []
        
        for day_offset in range(3):
            test_date = base_date + timedelta(days=day_offset)
            date_str = test_date.strftime("%Y-%m-%d")
            
            # 强制设置日期为模拟日期
            handler.current_date = (base_date + timedelta(days=day_offset - 1)).strftime("%Y-%m-%d") if day_offset > 0 else date_str
            handler.rollover_at = time.time() - 1 if day_offset > 0 else time.time() + 86400
            
            with patch('yweb.log.handlers.datetime') as mock_datetime:
                mock_datetime.now.return_value = test_date
                mock_datetime.strptime = datetime.strptime
                
                logger.info(f"Log message for day {day_offset + 1}")
                handler.flush()
            
            expected_file = os.path.join(log_dir, f"multi_day_{date_str}.log")
            created_files.append((expected_file, day_offset + 1))
        
        # 验证所有日期的文件都被创建
        for filepath, day_num in created_files:
            assert os.path.exists(filepath), f"第 {day_num} 天的日志文件应该存在: {filepath}"
        
        logger.removeHandler(handler)
        handler.close()
