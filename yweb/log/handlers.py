"""自定义日志处理器模块

提供增强的日志文件轮转功能：
- 支持按时间（每天午夜）轮转
- 支持按文件大小轮转
- 自动创建日志目录
- 保留指定数量的历史文件
- 支持按天数自动清理旧日志
- 支持按总大小自动清理旧日志
- 支持写缓存（批量写入、ERROR立即落盘）

使用示例:
    from yweb.log import TimeAndSizeRotatingFileHandler, BufferedRotatingFileHandler
    import logging
    
    # 基本处理器（无缓存）
    handler = TimeAndSizeRotatingFileHandler(
        filename="logs/app_{date}.log",
        maxBytes=10*1024*1024,
        backupCount=5,
    )
    
    # 带写缓存的处理器（高性能场景）
    buffered_handler = BufferedRotatingFileHandler(
        filename="logs/app_{date}.log",
        maxBytes=10*1024*1024,
        backupCount=5,
        bufferCapacity=100,      # 缓存100条后刷新
        flushInterval=5.0,       # 或每5秒刷新
        flushLevel=logging.ERROR # ERROR及以上立即刷新
    )
    
    logger = logging.getLogger('my_app')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
"""

import atexit
import logging
import os
import re
import time
import threading
import weakref
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
from typing import List, Tuple, Optional


class TimeAndSizeRotatingFileHandler(RotatingFileHandler):
    """时间和大小双重轮转的日志处理器
    
    结合时间和大小两种轮转策略：
    1. 每天午夜自动轮转日志文件（生成新的日期文件）
    2. 当单个日志文件超过指定大小时，进行序号轮转
    3. 支持保留指定数量的历史文件
    4. 支持按天数自动清理旧日志文件
    5. 支持按总大小自动清理旧日志文件
    
    文件命名规则：
    - 基本文件名使用 {date} 占位符，如 "app_{date}.log"
    - 运行时替换为实际日期，如 "app_2026-01-09.log"
    - 大小轮转时添加序号，如 "app_2026-01-09.1.log"
    
    Args:
        filename: 日志文件名模板，使用 {date} 作为日期占位符
        maxBytes: 单个文件最大字节数，0表示不限制大小
        backupCount: 保留的备份文件数量（同一天内的序号备份）
        encoding: 文件编码
        delay: 是否延迟打开文件
        when: 时间轮转策略，目前仅支持 "midnight"
        interval: 轮转间隔（天数）
        maxRetentionDays: 日志保留天数，0表示不限制，超过天数的旧日志将被删除
        maxTotalBytes: 日志文件总大小限制，0表示不限制，超过限制时删除最旧的日志
    
    使用示例:
        # 基本使用
        handler = TimeAndSizeRotatingFileHandler(
            filename="logs/app_{date}.log",
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
        
        # 完整配置（包含清理策略）
        handler = TimeAndSizeRotatingFileHandler(
            filename="logs/myapp_{date}.log",
            maxBytes=50*1024*1024,  # 50MB
            backupCount=10,
            encoding='utf-8',
            delay=False,
            when='midnight',
            interval=1,
            maxRetentionDays=30,          # 保留最近30天
            maxTotalBytes=1024*1024*1024  # 总大小限制1GB
        )
    """
    
    def __init__(
        self, 
        filename: str, 
        maxBytes: int = 0, 
        backupCount: int = 0, 
        encoding: str = None, 
        delay: bool = False, 
        when: str = "midnight", 
        interval: int = 1,
        maxRetentionDays: int = 0,
        maxTotalBytes: int = 0
    ):
        # 保存原始文件名模板，用于生成新的带日期的文件名
        self.filename_template = filename
        
        # 使用当前日期生成初始文件名
        current_date = datetime.now().strftime("%Y-%m-%d")
        initial_filename = filename.replace("{date}", current_date)
        
        # 确保日志目录存在
        log_dir = os.path.dirname(initial_filename)
        if log_dir and not os.path.exists(log_dir):
            try:
                os.makedirs(log_dir, exist_ok=True)
            except OSError as e:
                print(f"警告：无法创建日志目录 {log_dir}: {e}")
        
        # 调用父类初始化
        try:
            super().__init__(
                initial_filename, 
                mode='a', 
                maxBytes=maxBytes, 
                backupCount=backupCount, 
                encoding=encoding, 
                delay=delay
            )
        except (OSError, IOError) as e:
            print(f"警告：无法创建日志文件 {initial_filename}: {e}")
            # 使用空设备避免程序崩溃
            super().__init__(
                os.devnull, 
                mode='a', 
                maxBytes=0, 
                backupCount=0, 
                encoding=encoding, 
                delay=True
            )
        
        # 时间轮转相关属性
        self.when = when
        self.interval = interval
        self.rollover_at = self._compute_rollover_time()
        
        # 用于跟踪当天的文件序号
        self.current_date = current_date
        self.daily_sequence = self._find_max_daily_sequence(current_date)
        
        # 日志清理相关属性
        self.maxRetentionDays = maxRetentionDays
        self.maxTotalBytes = maxTotalBytes
        
        # 启动时执行一次清理
        self._cleanup_old_logs()
    
    def _compute_rollover_time(self) -> float:
        """计算下次轮转时间（午夜）"""
        if self.when == "midnight":
            # 计算明天的午夜时间
            tomorrow = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            return tomorrow.timestamp() + 86400  # 加一天的秒数
        return 0
    
    def _find_max_daily_sequence(self, date_str: str) -> int:
        """查找指定日期的最大日志序号
        
        Args:
            date_str: 日期字符串，格式为 YYYY-MM-DD
            
        Returns:
            int: 最大的序号，如果没有找到则返回0
        """
        max_seq = 0
        if self.backupCount <= 0:
            return max_seq
            
        log_dir = os.path.dirname(self.baseFilename)
        if not log_dir:
            log_dir = "."
        
        base_name = os.path.basename(self.baseFilename)
        base_name_without_ext, ext = os.path.splitext(base_name)
        
        try:
            for filename in os.listdir(log_dir):
                # 匹配模式: {base_name_without_ext}.{sequence}{ext}
                if filename.startswith(f"{base_name_without_ext}.") and filename.endswith(ext):
                    # 提取序号部分
                    middle_part = filename[len(base_name_without_ext)+1:-len(ext)]
                    if middle_part.isdigit():
                        try:
                            seq = int(middle_part)
                            max_seq = max(max_seq, seq)
                        except ValueError:
                            continue
        except OSError:
            pass
        
        return max_seq
    
    def shouldRollover(self, record) -> int:
        """判断是否需要轮转日志文件
        
        检查条件：
        1. 如果到了午夜时间，需要轮转
        2. 如果文件大小超过限制，需要轮转
        
        Returns:
            int: 1表示需要轮转，0表示不需要
        """
        # 检查是否到了时间轮转点
        current_time = time.time()
        if current_time >= self.rollover_at:
            return 1
        
        # 检查文件大小是否超过限制
        if self.maxBytes > 0:
            msg = "%s\n" % self.format(record)
            if self.stream is None:
                self.stream = self._open()
            if self.stream.tell() + len(msg) >= self.maxBytes:
                return 1
        
        return 0
    
    def doRollover(self):
        """执行日志轮转
        
        根据情况执行不同的轮转策略：
        - 新的一天：创建新的日期文件
        - 同一天文件过大：创建带序号的备份文件
        """
        if self.stream:
            self.stream.close()
            self.stream = None
        
        # 获取当前日期
        now = datetime.now()
        current_date = now.strftime("%Y-%m-%d")
        
        # 检查是否是新的一天
        is_new_day = current_date != self.current_date
        
        # 生成新的文件名
        new_filename = self.filename_template.replace("{date}", current_date)
        
        if is_new_day:
            # 新的一天，直接轮转到新的日志文件
            self.current_date = current_date
            self.daily_sequence = self._find_max_daily_sequence(current_date)
            self.rollover_at = self._compute_rollover_time()
        else:
            # 同一天内，因为文件大小而轮转
            self.daily_sequence += 1
            
            if self.backupCount > 0:
                base_name, ext = os.path.splitext(self.baseFilename)
                
                # 删除超出保留数量的旧文件
                for i in range(self.backupCount - 1, 0, -1):
                    sfn = f"{base_name}.{i}{ext}"
                    dfn = f"{base_name}.{i+1}{ext}"
                    if os.path.exists(sfn):
                        if os.path.exists(dfn):
                            os.remove(dfn)
                        os.rename(sfn, dfn)
                
                # 重命名当前文件
                dfn = f"{base_name}.1{ext}"
                if os.path.exists(dfn):
                    os.remove(dfn)
                
                if os.path.exists(self.baseFilename):
                    os.rename(self.baseFilename, dfn)
        
        # 更新基础文件名为新的日期文件
        self.baseFilename = new_filename
        
        # 重新打开日志文件
        if not self.delay:
            self.stream = self._open()
        
        # 执行日志清理
        self._cleanup_old_logs()
    
    def _get_log_file_pattern(self) -> str:
        """获取日志文件的匹配模式
        
        根据文件名模板生成正则表达式模式，用于匹配所有相关的日志文件。
        
        Returns:
            str: 正则表达式模式
        """
        # 从模板中提取基本文件名（不含路径和日期）
        basename = os.path.basename(self.filename_template)
        # 先分割扩展名（在转义之前）
        name_part, ext = os.path.splitext(basename)
        # 将 {date} 替换为日期正则表达式
        name_part = name_part.replace("{date}", r"(\d{4}-\d{2}-\d{2})")
        # 转义其他特殊字符（主要是扩展名中的点）
        ext_escaped = ext.replace(".", r"\.")
        # 添加可选的序号部分 (.1, .2, etc.)
        pattern = f"^{name_part}(?:\\.(\\d+))?{ext_escaped}$"
        return pattern
    
    def _get_all_log_files(self) -> List[Tuple[str, datetime, int]]:
        """获取所有相关的日志文件
        
        Returns:
            List[Tuple[str, datetime, int]]: 列表，每个元素为 (文件路径, 日期, 文件大小)
        """
        log_dir = os.path.dirname(self.baseFilename)
        if not log_dir:
            log_dir = "."
        
        if not os.path.exists(log_dir):
            return []
        
        pattern = self._get_log_file_pattern()
        regex = re.compile(pattern)
        
        log_files = []
        try:
            for filename in os.listdir(log_dir):
                match = regex.match(filename)
                if match:
                    filepath = os.path.join(log_dir, filename)
                    try:
                        # 提取日期
                        date_str = match.group(1)
                        file_date = datetime.strptime(date_str, "%Y-%m-%d")
                        # 获取文件大小
                        file_size = os.path.getsize(filepath)
                        log_files.append((filepath, file_date, file_size))
                    except (ValueError, OSError):
                        continue
        except OSError:
            pass
        
        # 按日期排序（最旧的在前）
        log_files.sort(key=lambda x: (x[1], x[0]))
        return log_files
    
    def _cleanup_old_logs(self) -> None:
        """清理旧日志文件
        
        根据配置的保留天数和总大小限制，删除旧的日志文件。
        清理策略：
        1. 先按天数清理：删除超过 maxRetentionDays 天的日志
        2. 再按总大小清理：如果总大小超过 maxTotalBytes，删除最旧的日志
        """
        if self.maxRetentionDays <= 0 and self.maxTotalBytes <= 0:
            return
        
        log_files = self._get_all_log_files()
        if not log_files:
            return
        
        deleted_files = set()
        
        # 1. 按天数清理
        if self.maxRetentionDays > 0:
            cutoff_date = datetime.now() - timedelta(days=self.maxRetentionDays)
            for filepath, file_date, _ in log_files:
                if file_date < cutoff_date:
                    try:
                        # 不删除当前正在写入的文件
                        if filepath != self.baseFilename:
                            os.remove(filepath)
                            deleted_files.add(filepath)
                    except OSError:
                        pass
        
        # 2. 按总大小清理
        if self.maxTotalBytes > 0:
            # 重新获取文件列表（排除已删除的）
            remaining_files = [
                (fp, fd, fs) for fp, fd, fs in log_files 
                if fp not in deleted_files
            ]
            
            # 计算当前总大小
            total_size = sum(fs for _, _, fs in remaining_files)
            
            # 从最旧的文件开始删除，直到总大小在限制内
            for filepath, _, file_size in remaining_files:
                if total_size <= self.maxTotalBytes:
                    break
                # 不删除当前正在写入的文件
                if filepath != self.baseFilename:
                    try:
                        os.remove(filepath)
                        total_size -= file_size
                        deleted_files.add(filepath)
                    except OSError:
                        pass
    
    def get_total_log_size(self) -> int:
        """获取所有日志文件的总大小
        
        Returns:
            int: 总大小（字节）
        """
        log_files = self._get_all_log_files()
        return sum(fs for _, _, fs in log_files)
    
    def get_log_file_count(self) -> int:
        """获取日志文件数量
        
        Returns:
            int: 文件数量
        """
        return len(self._get_all_log_files())
    
    def get_oldest_log_date(self) -> Optional[datetime]:
        """获取最旧日志文件的日期
        
        Returns:
            Optional[datetime]: 最旧日志的日期，如果没有日志则返回 None
        """
        log_files = self._get_all_log_files()
        if not log_files:
            return None
        return log_files[0][1]


class DailyRotatingFileHandler(TimeAndSizeRotatingFileHandler):
    """每日轮转的日志处理器（简化版）
    
    只按日期轮转，不按大小轮转的简化版本。
    
    使用示例:
        handler = DailyRotatingFileHandler(
            filename="logs/app_{date}.log",
            maxRetentionDays=30,  # 保留最近30天的日志
            encoding='utf-8'
        )
    """
    
    def __init__(
        self, 
        filename: str, 
        backupCount: int = 0, 
        encoding: str = None, 
        delay: bool = False,
        maxRetentionDays: int = 0,
        maxTotalBytes: int = 0
    ):
        super().__init__(
            filename=filename,
            maxBytes=0,  # 不按大小轮转
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            when='midnight',
            interval=1,
            maxRetentionDays=maxRetentionDays,
            maxTotalBytes=maxTotalBytes
        )


# 全局注册表，用于在程序退出时刷新所有缓冲处理器
_buffered_handlers: List[weakref.ref] = []
_handlers_lock = threading.Lock()


def _flush_all_buffered_handlers():
    """程序退出时刷新所有缓冲处理器"""
    with _handlers_lock:
        for ref in _buffered_handlers:
            handler = ref()
            if handler is not None:
                try:
                    handler.flush()
                except Exception:
                    pass


# 注册退出时的清理函数
atexit.register(_flush_all_buffered_handlers)


class BufferedRotatingFileHandler(TimeAndSizeRotatingFileHandler):
    """带写缓存的日志处理器
    
    在 TimeAndSizeRotatingFileHandler 基础上增加写缓存功能：
    1. 批量写入：累积指定数量的日志后一次性写入
    2. 定时刷新：后台线程定期刷新缓冲区
    3. 级别刷新：ERROR/CRITICAL 级别日志立即落盘
    4. 优雅关闭：程序退出时确保所有日志落盘
    
    Args:
        filename: 日志文件名模板
        maxBytes: 单个文件最大字节数
        backupCount: 备份文件数量
        encoding: 文件编码
        delay: 是否延迟打开文件
        when: 时间轮转策略
        interval: 轮转间隔
        maxRetentionDays: 日志保留天数
        maxTotalBytes: 日志总大小限制
        bufferCapacity: 缓冲区容量（条数），达到后刷新，默认100
        flushInterval: 刷新间隔（秒），默认5秒
        flushLevel: 触发立即刷新的日志级别，默认 ERROR
    
    使用示例:
        # 高性能场景：批量写入
        handler = BufferedRotatingFileHandler(
            filename="logs/app_{date}.log",
            maxBytes=10*1024*1024,
            backupCount=5,
            bufferCapacity=100,       # 每100条刷新
            flushInterval=5.0,        # 或每5秒刷新
            flushLevel=logging.ERROR  # ERROR立即刷新
        )
        
        # 适中配置
        handler = BufferedRotatingFileHandler(
            filename="logs/app_{date}.log",
            bufferCapacity=50,
            flushInterval=3.0
        )
    """
    
    def __init__(
        self,
        filename: str,
        maxBytes: int = 0,
        backupCount: int = 0,
        encoding: str = None,
        delay: bool = False,
        when: str = "midnight",
        interval: int = 1,
        maxRetentionDays: int = 0,
        maxTotalBytes: int = 0,
        bufferCapacity: int = 100,
        flushInterval: float = 5.0,
        flushLevel: int = logging.ERROR
    ):
        # 先调用父类初始化
        super().__init__(
            filename=filename,
            maxBytes=maxBytes,
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            when=when,
            interval=interval,
            maxRetentionDays=maxRetentionDays,
            maxTotalBytes=maxTotalBytes
        )
        
        # 缓冲区配置
        self.bufferCapacity = bufferCapacity
        self.flushInterval = flushInterval
        self.flushLevel = flushLevel
        
        # 缓冲区
        self._buffer: List[str] = []
        self._buffer_lock = threading.Lock()
        self._last_flush_time = time.time()
        
        # 后台刷新线程
        self._flush_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._start_flush_thread()
        
        # 注册到全局处理器列表
        with _handlers_lock:
            _buffered_handlers.append(weakref.ref(self))
    
    def _start_flush_thread(self):
        """启动后台刷新线程"""
        self._stop_event.clear()
        self._flush_thread = threading.Thread(
            target=self._flush_worker,
            name=f"LogFlushThread-{id(self)}",
            daemon=True
        )
        self._flush_thread.start()
    
    def _flush_worker(self):
        """后台刷新工作线程"""
        while not self._stop_event.is_set():
            try:
                # 等待指定间隔或被唤醒
                self._stop_event.wait(timeout=self.flushInterval)
                
                if self._stop_event.is_set():
                    break
                
                # 检查是否需要定时刷新
                with self._buffer_lock:
                    if self._buffer and (time.time() - self._last_flush_time >= self.flushInterval):
                        self._flush_buffer_unsafe()
                        
            except Exception:
                # 忽略刷新线程中的异常，避免线程崩溃
                pass
    
    def emit(self, record):
        """处理日志记录
        
        重写 emit 方法，将日志先写入缓冲区。
        如果是 ERROR 及以上级别，立即刷新。
        """
        try:
            msg = self.format(record)
            
            with self._buffer_lock:
                self._buffer.append(msg)
                
                # 检查是否需要立即刷新
                should_flush = (
                    # 达到缓冲区容量
                    len(self._buffer) >= self.bufferCapacity or
                    # ERROR 及以上级别立即刷新
                    record.levelno >= self.flushLevel
                )
                
                if should_flush:
                    self._flush_buffer_unsafe()
                    
        except Exception:
            self.handleError(record)
    
    def _flush_buffer_unsafe(self):
        """刷新缓冲区（非线程安全，调用者需持有锁）
        
        将缓冲区中的日志批量写入文件。
        """
        if not self._buffer:
            return
        
        try:
            # 检查是否需要轮转（使用第一条记录模拟检查）
            # 注意：这里简化处理，实际轮转在写入时由父类处理
            
            # 确保流已打开
            if self.stream is None:
                self.stream = self._open()
            
            # 批量写入
            for msg in self._buffer:
                # 检查是否需要轮转（按时间）
                current_time = time.time()
                if current_time >= self.rollover_at:
                    # 需要时间轮转
                    if self.stream:
                        self.stream.close()
                        self.stream = None
                    self.doRollover()
                    if self.stream is None:
                        self.stream = self._open()
                
                # 检查是否需要轮转（按大小）
                if self.maxBytes > 0 and self.stream:
                    self.stream.seek(0, 2)  # 移到文件末尾
                    if self.stream.tell() + len(msg) + 1 >= self.maxBytes:
                        if self.stream:
                            self.stream.close()
                            self.stream = None
                        self.doRollover()
                        if self.stream is None:
                            self.stream = self._open()
                
                # 写入日志
                if self.stream:
                    self.stream.write(msg + self.terminator)
            
            # 刷新文件流
            if self.stream:
                self.stream.flush()
            
            # 清空缓冲区
            self._buffer.clear()
            self._last_flush_time = time.time()
            
        except Exception:
            # 写入失败时尝试保留日志（可选：写入备用位置）
            pass
    
    def flush(self):
        """刷新缓冲区
        
        线程安全的刷新方法。
        """
        with self._buffer_lock:
            self._flush_buffer_unsafe()
        
        # 调用父类刷新
        super().flush()
    
    def close(self):
        """关闭处理器
        
        停止后台线程并刷新所有剩余日志。
        """
        # 停止后台刷新线程
        self._stop_event.set()
        if self._flush_thread and self._flush_thread.is_alive():
            self._flush_thread.join(timeout=2.0)
        
        # 刷新剩余日志
        self.flush()
        
        # 从全局列表中移除
        with _handlers_lock:
            _buffered_handlers[:] = [
                ref for ref in _buffered_handlers 
                if ref() is not None and ref() is not self
            ]
        
        # 调用父类关闭
        super().close()
    
    def get_buffer_size(self) -> int:
        """获取当前缓冲区大小
        
        Returns:
            int: 缓冲区中的日志条数
        """
        with self._buffer_lock:
            return len(self._buffer)
    
    def get_buffer_stats(self) -> dict:
        """获取缓冲区统计信息
        
        Returns:
            dict: 包含缓冲区大小、容量、上次刷新时间等信息
        """
        with self._buffer_lock:
            return {
                "buffer_size": len(self._buffer),
                "buffer_capacity": self.bufferCapacity,
                "flush_interval": self.flushInterval,
                "flush_level": logging.getLevelName(self.flushLevel),
                "last_flush_time": self._last_flush_time,
                "seconds_since_flush": time.time() - self._last_flush_time,
            }


class BufferedDailyRotatingFileHandler(BufferedRotatingFileHandler):
    """带写缓存的每日轮转处理器
    
    结合 DailyRotatingFileHandler 和 BufferedRotatingFileHandler 的功能。
    
    使用示例:
        handler = BufferedDailyRotatingFileHandler(
            filename="logs/app_{date}.log",
            maxRetentionDays=30,
            bufferCapacity=100,
            flushInterval=5.0
        )
    """
    
    def __init__(
        self,
        filename: str,
        backupCount: int = 0,
        encoding: str = None,
        delay: bool = False,
        maxRetentionDays: int = 0,
        maxTotalBytes: int = 0,
        bufferCapacity: int = 100,
        flushInterval: float = 5.0,
        flushLevel: int = logging.ERROR
    ):
        super().__init__(
            filename=filename,
            maxBytes=0,  # 不按大小轮转
            backupCount=backupCount,
            encoding=encoding,
            delay=delay,
            when='midnight',
            interval=1,
            maxRetentionDays=maxRetentionDays,
            maxTotalBytes=maxTotalBytes,
            bufferCapacity=bufferCapacity,
            flushInterval=flushInterval,
            flushLevel=flushLevel
        )

