"""日志清理功能测试

测试日志文件的自动清理功能：
- 按天数清理旧日志
- 按总大小清理旧日志
"""

import pytest
import os
import logging
from datetime import datetime, timedelta

from yweb.log import TimeAndSizeRotatingFileHandler, DailyRotatingFileHandler


class TestLogCleanupByRetentionDays:
    """按天数清理日志测试"""
    
    def test_cleanup_old_logs_by_days(self, log_dir):
        """测试按天数清理旧日志"""
        # 创建一些模拟的旧日志文件
        today = datetime.now()
        
        # 创建不同日期的日志文件
        old_files = []
        for days_ago in [1, 5, 10, 15, 20]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"cleanup_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write(f"Log from {date_str}\n" * 100)
            old_files.append((filename, days_ago))
        
        # 创建处理器，设置保留7天
        log_file = os.path.join(log_dir, "cleanup_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxRetentionDays=7  # 保留最近7天
        )
        
        # 检查结果：超过7天的文件应该被删除
        for filename, days_ago in old_files:
            if days_ago > 7:
                assert not os.path.exists(filename), f"文件 {filename} 应该被删除（{days_ago}天前）"
            else:
                assert os.path.exists(filename), f"文件 {filename} 应该保留（{days_ago}天前）"
        
        handler.close()
    
    def test_cleanup_preserves_current_file(self, log_dir):
        """测试清理时保留当前正在写入的文件"""
        log_file = os.path.join(log_dir, "preserve_test_{date}.log")
        
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxRetentionDays=1  # 只保留1天
        )
        
        # 写入一些日志
        logger = logging.getLogger("test_preserve")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        logger.info("Test message")
        handler.flush()
        
        # 当前文件应该存在
        assert os.path.exists(handler.baseFilename)
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_no_cleanup_when_retention_days_zero(self, log_dir):
        """测试保留天数为0时不清理"""
        today = datetime.now()
        
        # 创建一个30天前的文件
        old_date = today - timedelta(days=30)
        date_str = old_date.strftime("%Y-%m-%d")
        old_file = os.path.join(log_dir, f"no_cleanup_test_{date_str}.log")
        with open(old_file, 'w') as f:
            f.write("Old log content\n")
        
        # 创建处理器，保留天数为0（不限制）
        log_file = os.path.join(log_dir, "no_cleanup_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxRetentionDays=0  # 不限制
        )
        
        # 旧文件应该保留
        assert os.path.exists(old_file)
        
        handler.close()


class TestLogCleanupByTotalSize:
    """按总大小清理日志测试"""
    
    def test_cleanup_by_total_size(self, log_dir):
        """测试按总大小清理旧日志"""
        today = datetime.now()
        
        # 创建多个日志文件，每个1KB
        file_size = 1024  # 1KB
        total_files = 10
        
        created_files = []
        for days_ago in range(total_files, 0, -1):
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"size_cleanup_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * file_size)
            created_files.append(filename)
        
        # 创建处理器，总大小限制为5KB
        log_file = os.path.join(log_dir, "size_cleanup_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxTotalBytes=5 * 1024  # 5KB限制
        )
        
        # 计算剩余文件总大小
        total_size = handler.get_total_log_size()
        
        # 总大小应该不超过限制（或接近限制）
        assert total_size <= 6 * 1024, f"总大小 {total_size} 应该不超过限制"
        
        handler.close()
    
    def test_cleanup_deletes_oldest_first(self, log_dir):
        """测试清理时优先删除最旧的文件"""
        today = datetime.now()
        
        # 创建文件，确保最旧的在前
        dates_and_files = []
        for days_ago in [10, 5, 3, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"oldest_first_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * 1024)  # 1KB
            dates_and_files.append((days_ago, filename))
        
        # 创建处理器，总大小限制为2KB
        log_file = os.path.join(log_dir, "oldest_first_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxTotalBytes=2 * 1024  # 2KB限制
        )
        
        # 最旧的文件应该被删除，最新的应该保留
        for days_ago, filename in dates_and_files:
            if days_ago >= 5:  # 较旧的文件应该被删除
                assert not os.path.exists(filename), f"文件 {filename} 应该被删除"
        
        handler.close()
    
    def test_no_cleanup_when_total_size_zero(self, log_dir):
        """测试总大小限制为0时不清理"""
        today = datetime.now()
        
        # 创建多个大文件
        for days_ago in [5, 3, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"no_size_cleanup_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * 10240)  # 10KB
        
        # 创建处理器，总大小限制为0（不限制）
        log_file = os.path.join(log_dir, "no_size_cleanup_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxTotalBytes=0  # 不限制
        )
        
        # 所有文件应该保留
        file_count = handler.get_log_file_count()
        assert file_count >= 3, f"文件数量应该至少为3，实际为 {file_count}"
        
        handler.close()


class TestCombinedCleanup:
    """组合清理策略测试"""
    
    def test_retention_days_and_total_size(self, log_dir):
        """测试同时使用天数和大小限制"""
        today = datetime.now()
        
        # 创建文件
        for days_ago in [20, 15, 10, 5, 3, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"combined_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * 2048)  # 2KB
        
        # 创建处理器，保留7天且总大小限制5KB
        log_file = os.path.join(log_dir, "combined_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            maxRetentionDays=7,     # 保留7天
            maxTotalBytes=5 * 1024  # 5KB限制
        )
        
        # 检查结果
        # 1. 超过7天的文件应该被删除
        for days_ago in [20, 15, 10]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"combined_test_{date_str}.log")
            assert not os.path.exists(filename), f"超过7天的文件应该被删除: {filename}"
        
        # 2. 总大小应该在限制内
        total_size = handler.get_total_log_size()
        assert total_size <= 6 * 1024, f"总大小 {total_size} 应该不超过限制"
        
        handler.close()


class TestLogFileUtilities:
    """日志文件工具方法测试"""
    
    def test_get_total_log_size(self, log_dir):
        """测试获取日志总大小"""
        today = datetime.now()
        
        # 创建已知大小的文件
        expected_total = 0
        for days_ago in [3, 2, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"total_size_test_{date_str}.log")
            size = days_ago * 1024  # 不同大小
            with open(filename, 'w') as f:
                f.write("x" * size)
            expected_total += size
        
        log_file = os.path.join(log_dir, "total_size_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 写入当前文件
        logger = logging.getLogger("test_total_size")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.info("Test")
        handler.flush()
        
        total_size = handler.get_total_log_size()
        assert total_size >= expected_total, f"总大小应该至少为 {expected_total}"
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_get_log_file_count(self, log_dir):
        """测试获取日志文件数量"""
        today = datetime.now()
        
        # 创建多个文件
        file_count = 5
        for days_ago in range(1, file_count + 1):
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"file_count_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("content")
        
        log_file = os.path.join(log_dir, "file_count_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 写入当前文件
        logger = logging.getLogger("test_file_count")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.info("Test")
        handler.flush()
        
        count = handler.get_log_file_count()
        assert count >= file_count, f"文件数量应该至少为 {file_count}，实际为 {count}"
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_get_oldest_log_date(self, log_dir):
        """测试获取最旧日志日期"""
        today = datetime.now()
        oldest_days_ago = 10
        
        # 创建文件
        for days_ago in [oldest_days_ago, 5, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"oldest_date_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("content")
        
        log_file = os.path.join(log_dir, "oldest_date_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        oldest_date = handler.get_oldest_log_date()
        expected_oldest = (today - timedelta(days=oldest_days_ago)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        
        assert oldest_date is not None
        assert oldest_date.date() == expected_oldest.date()
        
        handler.close()


class TestDailyRotatingHandlerWithCleanup:
    """DailyRotatingFileHandler 清理功能测试"""
    
    def test_daily_handler_with_retention_days(self, log_dir):
        """测试 DailyRotatingFileHandler 的保留天数功能"""
        today = datetime.now()
        
        # 创建旧文件
        for days_ago in [15, 10, 5, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"daily_retention_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("content")
        
        log_file = os.path.join(log_dir, "daily_retention_test_{date}.log")
        handler = DailyRotatingFileHandler(
            filename=log_file,
            maxRetentionDays=7  # 保留7天
        )
        
        # 超过7天的文件应该被删除
        for days_ago in [15, 10]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"daily_retention_test_{date_str}.log")
            assert not os.path.exists(filename), f"文件应该被删除: {filename}"
        
        handler.close()
    
    def test_daily_handler_with_total_size(self, log_dir):
        """测试 DailyRotatingFileHandler 的总大小限制功能"""
        today = datetime.now()
        
        # 创建多个文件
        for days_ago in [5, 4, 3, 2, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"daily_size_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * 2048)  # 2KB
        
        log_file = os.path.join(log_dir, "daily_size_test_{date}.log")
        handler = DailyRotatingFileHandler(
            filename=log_file,
            maxTotalBytes=5 * 1024  # 5KB
        )
        
        # 总大小应该在限制内
        total_size = handler.get_total_log_size()
        assert total_size <= 6 * 1024
        
        handler.close()


class TestCleanupOnRollover:
    """轮转时清理测试"""
    
    def test_cleanup_triggered_on_size_rollover(self, log_dir):
        """测试大小轮转时触发清理"""
        today = datetime.now()
        
        # 创建旧文件
        for days_ago in [10, 5]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"rollover_cleanup_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("x" * 1024)
        
        log_file = os.path.join(log_dir, "rollover_cleanup_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=500,  # 很小的限制以触发轮转
            backupCount=3,
            maxRetentionDays=3  # 保留3天
        )
        
        logger = logging.getLogger("test_rollover_cleanup")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入大量日志以触发轮转
        for i in range(100):
            logger.info(f"Message {i}: " + "x" * 100)
        
        handler.flush()
        
        # 检查旧文件是否被清理
        for days_ago in [10, 5]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"rollover_cleanup_test_{date_str}.log")
            assert not os.path.exists(filename), f"旧文件应该被清理: {filename}"
        
        logger.removeHandler(handler)
        handler.close()


class TestLoggingSettingsWithCleanup:
    """LoggingSettings 清理配置测试"""
    
    def test_logging_settings_cleanup_config(self):
        """测试 LoggingSettings 的清理配置项"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings(
            max_retention_days=30,
            max_total_size="1GB"
        )
        
        assert settings.max_retention_days == 30
        assert settings.max_total_size == "1GB"
        assert settings.parsed_max_total_size == 1024 * 1024 * 1024
    
    def test_logging_settings_sql_cleanup_config(self):
        """测试 LoggingSettings 的 SQL 日志清理配置项"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings(
            sql_log_max_retention_days=7,
            sql_log_max_total_size="500MB"
        )
        
        assert settings.sql_log_max_retention_days == 7
        assert settings.sql_log_max_total_size == "500MB"
        assert settings.parsed_sql_log_max_total_size == 500 * 1024 * 1024
    
    def test_logging_settings_default_values(self):
        """测试 LoggingSettings 的默认值"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings()
        
        # 默认不限制
        assert settings.max_retention_days == 0
        assert settings.max_total_size == "0"
        assert settings.parsed_max_total_size == 0
        assert settings.sql_log_max_retention_days == 0
        assert settings.parsed_sql_log_max_total_size == 0


class TestFilePatternMatching:
    """文件模式匹配测试"""
    
    def test_pattern_matches_date_files(self, log_dir):
        """测试模式匹配带日期的文件"""
        today = datetime.now()
        
        # 创建符合模式的文件
        for days_ago in [3, 2, 1]:
            date = today - timedelta(days=days_ago)
            date_str = date.strftime("%Y-%m-%d")
            filename = os.path.join(log_dir, f"pattern_test_{date_str}.log")
            with open(filename, 'w') as f:
                f.write("content")
        
        # 创建不符合模式的文件
        other_file = os.path.join(log_dir, "other_file.log")
        with open(other_file, 'w') as f:
            f.write("content")
        
        log_file = os.path.join(log_dir, "pattern_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5
        )
        
        # 写入当前文件
        logger = logging.getLogger("test_pattern")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        logger.info("Test")
        handler.flush()
        
        # 获取匹配的文件数量（应该只包含符合模式的文件）
        file_count = handler.get_log_file_count()
        assert file_count >= 3  # 3个旧文件 + 1个当前文件
        assert file_count <= 5  # 不应该包含其他文件
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_pattern_matches_backup_files(self, log_dir):
        """测试模式匹配带序号的备份文件"""
        today = datetime.now()
        date_str = today.strftime("%Y-%m-%d")
        
        # 创建主文件和备份文件
        main_file = os.path.join(log_dir, f"backup_pattern_test_{date_str}.log")
        with open(main_file, 'w') as f:
            f.write("main content")
        
        for i in range(1, 4):
            backup_file = os.path.join(log_dir, f"backup_pattern_test_{date_str}.{i}.log")
            with open(backup_file, 'w') as f:
                f.write(f"backup {i} content")
        
        log_file = os.path.join(log_dir, "backup_pattern_test_{date}.log")
        handler = TimeAndSizeRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            delay=True  # 延迟打开文件，避免文件锁问题
        )
        
        # 获取文件列表
        log_files = handler._get_all_log_files()
        
        # 应该包含主文件和备份文件（4个：1个主文件 + 3个备份）
        assert len(log_files) >= 4, f"应该至少有4个文件，实际有 {len(log_files)} 个"
        
        handler.close()
