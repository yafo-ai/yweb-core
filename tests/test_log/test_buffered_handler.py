"""写缓存日志处理器测试

测试 BufferedRotatingFileHandler 的功能：
- 批量写入（按条数/时间间隔）
- ERROR/CRITICAL 立即落盘
- 后台定时刷新
- 优雅关闭
"""

import pytest
import os
import logging
import time
import threading
from datetime import datetime

from yweb.log import BufferedRotatingFileHandler, BufferedDailyRotatingFileHandler


class TestBufferedRotatingFileHandler:
    """BufferedRotatingFileHandler 基本功能测试"""
    
    def test_create_handler(self, log_dir):
        """测试创建处理器"""
        log_file = os.path.join(log_dir, "buffered_test_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            maxBytes=1024 * 1024,
            backupCount=5,
            bufferCapacity=100,
            flushInterval=5.0
        )
        
        assert handler is not None
        assert handler.bufferCapacity == 100
        assert handler.flushInterval == 5.0
        assert handler.flushLevel == logging.ERROR
        
        handler.close()
    
    def test_buffer_accumulation(self, log_dir):
        """测试日志在缓冲区中累积"""
        log_file = os.path.join(log_dir, "buffer_accum_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=50,  # 50条才刷新
            flushInterval=60.0  # 60秒才刷新（测试中不会触发）
        )
        
        logger = logging.getLogger("test_buffer_accum")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入10条日志（不会触发刷新）
        for i in range(10):
            logger.info(f"Message {i}")
        
        # 缓冲区应该有10条
        assert handler.get_buffer_size() == 10
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_flush_on_capacity(self, log_dir):
        """测试达到容量时自动刷新"""
        log_file = os.path.join(log_dir, "flush_capacity_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=10,  # 10条刷新
            flushInterval=60.0,
            flushLevel=logging.CRITICAL  # 只有 CRITICAL 才立即刷新
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_flush_capacity")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入15条日志
        for i in range(15):
            logger.info(f"Message {i}")
        
        # 应该已刷新一次（10条），剩余5条在缓冲区
        assert handler.get_buffer_size() == 5
        
        # 检查文件内容
        handler.flush()
        
        files = [f for f in os.listdir(log_dir) if f.startswith("flush_capacity_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            lines = f.readlines()
            assert len(lines) == 15
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_flush_on_error(self, log_dir):
        """测试 ERROR 级别立即刷新"""
        log_file = os.path.join(log_dir, "flush_error_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=100,  # 容量很大，不会触发
            flushInterval=60.0,
            flushLevel=logging.ERROR  # ERROR 立即刷新
        )
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        logger = logging.getLogger("test_flush_error")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入几条 INFO 日志
        for i in range(5):
            logger.info(f"Info message {i}")
        
        # 缓冲区应该有5条
        assert handler.get_buffer_size() == 5
        
        # 写入一条 ERROR 日志
        logger.error("Error message")
        
        # 应该立即刷新，缓冲区清空
        assert handler.get_buffer_size() == 0
        
        # 检查文件内容
        files = [f for f in os.listdir(log_dir) if f.startswith("flush_error_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            content = f.read()
            assert "Error message" in content
            assert content.count("Info message") == 5
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_flush_on_critical(self, log_dir):
        """测试 CRITICAL 级别立即刷新"""
        log_file = os.path.join(log_dir, "flush_critical_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=100,
            flushInterval=60.0,
            flushLevel=logging.ERROR
        )
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        logger = logging.getLogger("test_flush_critical")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入几条普通日志
        logger.info("Info message")
        logger.warning("Warning message")
        
        # 缓冲区应该有2条
        assert handler.get_buffer_size() == 2
        
        # 写入 CRITICAL 日志
        logger.critical("Critical message")
        
        # 应该立即刷新
        assert handler.get_buffer_size() == 0
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_manual_flush(self, log_dir):
        """测试手动刷新"""
        log_file = os.path.join(log_dir, "manual_flush_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=100,
            flushInterval=60.0
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_manual_flush")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入日志
        logger.info("Test message")
        assert handler.get_buffer_size() == 1
        
        # 手动刷新
        handler.flush()
        assert handler.get_buffer_size() == 0
        
        logger.removeHandler(handler)
        handler.close()
    
    def test_close_flushes_buffer(self, log_dir):
        """测试关闭时刷新所有日志"""
        log_file = os.path.join(log_dir, "close_flush_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=100,
            flushInterval=60.0
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_close_flush")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入日志但不刷新
        for i in range(20):
            logger.info(f"Message {i}")
        
        assert handler.get_buffer_size() == 20
        
        # 关闭处理器
        logger.removeHandler(handler)
        handler.close()
        
        # 检查文件内容
        files = [f for f in os.listdir(log_dir) if f.startswith("close_flush_")]
        assert len(files) >= 1
        
        with open(os.path.join(log_dir, files[0]), 'r') as f:
            lines = f.readlines()
            assert len(lines) == 20


class TestBufferedHandlerTimedFlush:
    """定时刷新测试"""
    
    def test_timed_flush(self, log_dir):
        """测试定时刷新功能"""
        log_file = os.path.join(log_dir, "timed_flush_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=1000,  # 很大的容量
            flushInterval=1.0,    # 1秒刷新
            flushLevel=logging.CRITICAL  # 只有 CRITICAL 立即刷新
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_timed_flush")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入日志
        logger.info("Test message 1")
        logger.info("Test message 2")
        
        # 缓冲区有日志
        assert handler.get_buffer_size() == 2
        
        # 等待定时刷新
        time.sleep(1.5)
        
        # 定时刷新应该已经执行
        assert handler.get_buffer_size() == 0
        
        logger.removeHandler(handler)
        handler.close()


class TestBufferedHandlerStats:
    """统计信息测试"""
    
    def test_get_buffer_stats(self, log_dir):
        """测试获取缓冲区统计信息"""
        log_file = os.path.join(log_dir, "stats_test_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=100,
            flushInterval=5.0,
            flushLevel=logging.ERROR
        )
        
        logger = logging.getLogger("test_stats")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入一些日志
        for i in range(10):
            logger.info(f"Message {i}")
        
        # 获取统计信息
        stats = handler.get_buffer_stats()
        
        assert stats["buffer_size"] == 10
        assert stats["buffer_capacity"] == 100
        assert stats["flush_interval"] == 5.0
        assert stats["flush_level"] == "ERROR"
        assert "last_flush_time" in stats
        assert "seconds_since_flush" in stats
        
        logger.removeHandler(handler)
        handler.close()


class TestBufferedHandlerThreadSafety:
    """线程安全测试"""
    
    def test_concurrent_writes(self, log_dir):
        """测试并发写入"""
        log_file = os.path.join(log_dir, "concurrent_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            bufferCapacity=50,
            flushInterval=1.0
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_concurrent")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 多线程写入
        threads = []
        messages_per_thread = 100
        num_threads = 5
        
        def write_logs(thread_id):
            for i in range(messages_per_thread):
                logger.info(f"Thread-{thread_id}-Message-{i}")
        
        for i in range(num_threads):
            t = threading.Thread(target=write_logs, args=(i,))
            threads.append(t)
            t.start()
        
        for t in threads:
            t.join()
        
        # 刷新并关闭
        logger.removeHandler(handler)
        handler.close()
        
        # 检查文件内容
        files = [f for f in os.listdir(log_dir) if f.startswith("concurrent_")]
        assert len(files) >= 1
        
        total_lines = 0
        for f in files:
            with open(os.path.join(log_dir, f), 'r') as file:
                total_lines += len(file.readlines())
        
        # 所有日志都应该被写入
        assert total_lines == num_threads * messages_per_thread


class TestBufferedDailyRotatingFileHandler:
    """BufferedDailyRotatingFileHandler 测试"""
    
    def test_create_handler(self, log_dir):
        """测试创建处理器"""
        log_file = os.path.join(log_dir, "buffered_daily_{date}.log")
        
        handler = BufferedDailyRotatingFileHandler(
            filename=log_file,
            maxRetentionDays=7,
            bufferCapacity=50,
            flushInterval=3.0
        )
        
        assert handler is not None
        assert handler.bufferCapacity == 50
        assert handler.flushInterval == 3.0
        
        handler.close()
    
    def test_daily_handler_buffering(self, log_dir):
        """测试每日处理器的缓冲功能"""
        log_file = os.path.join(log_dir, "buffered_daily_test_{date}.log")
        
        handler = BufferedDailyRotatingFileHandler(
            filename=log_file,
            bufferCapacity=20,
            flushInterval=60.0
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_buffered_daily")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入日志
        for i in range(15):
            logger.info(f"Daily message {i}")
        
        # 缓冲区有日志
        assert handler.get_buffer_size() == 15
        
        # 写入更多触发刷新
        for i in range(10):
            logger.info(f"More message {i}")
        
        # 应该刷新一次，剩余5条
        assert handler.get_buffer_size() == 5
        
        logger.removeHandler(handler)
        handler.close()


class TestLoggingSettingsWithBuffer:
    """LoggingSettings 缓存配置测试"""
    
    def test_buffer_config_default_disabled(self):
        """测试写缓存默认关闭"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings()
        
        assert settings.buffer_enabled == False
        assert settings.buffer_capacity == 100
        assert settings.buffer_flush_interval == 5.0
        assert settings.buffer_flush_level == "ERROR"
    
    def test_buffer_config_enabled(self):
        """测试启用写缓存配置"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings(
            buffer_enabled=True,
            buffer_capacity=200,
            buffer_flush_interval=10.0,
            buffer_flush_level="WARNING"
        )
        
        assert settings.buffer_enabled == True
        assert settings.buffer_capacity == 200
        assert settings.buffer_flush_interval == 10.0
        assert settings.buffer_flush_level == "WARNING"
    
    def test_sql_buffer_config(self):
        """测试 SQL 日志缓存配置"""
        from yweb.config import LoggingSettings
        
        settings = LoggingSettings(
            sql_log_buffer_enabled=True,
            sql_log_buffer_capacity=50,
            sql_log_buffer_flush_interval=2.0
        )
        
        assert settings.sql_log_buffer_enabled == True
        assert settings.sql_log_buffer_capacity == 50
        assert settings.sql_log_buffer_flush_interval == 2.0


class TestSetupLoggerWithBuffer:
    """setup_logger 缓存集成测试"""
    
    def test_setup_logger_without_buffer(self, log_dir):
        """测试不启用缓存时使用普通处理器"""
        from yweb.log import setup_logger, TimeAndSizeRotatingFileHandler
        
        log_file = os.path.join(log_dir, "no_buffer_{date}.log")
        
        logger = setup_logger(
            name="test_no_buffer",
            level="DEBUG",
            log_file=log_file,
            console=False,
            file_handler_options={
                "maxBytes": 1024 * 1024,
                "backupCount": 5,
                "bufferEnabled": False
            }
        )
        
        # 应该使用普通处理器
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], TimeAndSizeRotatingFileHandler)
        assert not isinstance(logger.handlers[0], BufferedRotatingFileHandler)
        
        for h in logger.handlers:
            h.close()
    
    def test_setup_logger_with_buffer(self, log_dir):
        """测试启用缓存时使用缓冲处理器"""
        from yweb.log import setup_logger
        
        log_file = os.path.join(log_dir, "with_buffer_{date}.log")
        
        logger = setup_logger(
            name="test_with_buffer",
            level="DEBUG",
            log_file=log_file,
            console=False,
            file_handler_options={
                "maxBytes": 1024 * 1024,
                "backupCount": 5,
                "bufferEnabled": True,
                "bufferCapacity": 50,
                "flushInterval": 3.0,
                "flushLevel": logging.ERROR
            }
        )
        
        # 应该使用缓冲处理器
        assert len(logger.handlers) == 1
        assert isinstance(logger.handlers[0], BufferedRotatingFileHandler)
        
        handler = logger.handlers[0]
        assert handler.bufferCapacity == 50
        assert handler.flushInterval == 3.0
        assert handler.flushLevel == logging.ERROR
        
        for h in logger.handlers:
            h.close()


class TestBufferedHandlerWithRotation:
    """缓冲处理器与轮转结合测试"""
    
    def test_buffer_with_size_rotation(self, log_dir):
        """测试缓冲与大小轮转结合"""
        log_file = os.path.join(log_dir, "buffer_rotation_{date}.log")
        
        handler = BufferedRotatingFileHandler(
            filename=log_file,
            maxBytes=500,  # 很小的文件限制
            backupCount=3,
            bufferCapacity=5,
            flushInterval=60.0,
            flushLevel=logging.CRITICAL
        )
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        logger = logging.getLogger("test_buffer_rotation")
        logger.setLevel(logging.DEBUG)
        logger.handlers.clear()
        logger.addHandler(handler)
        
        # 写入大量日志触发轮转
        for i in range(100):
            logger.info(f"Message {i}: " + "x" * 50)
        
        # 刷新并关闭
        logger.removeHandler(handler)
        handler.close()
        
        # 应该有多个文件（轮转产生）
        files = [f for f in os.listdir(log_dir) if "buffer_rotation_" in f]
        assert len(files) >= 1
