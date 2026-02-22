# -*- coding: utf-8 -*-
"""
存储监控指标模块

提供存储操作的性能监控和统计功能：
- 操作计数（成功/失败）
- 耗时统计
- 数据量统计
- 外部监控系统集成（Prometheus 等）

使用示例:
    class InstrumentedStorage(InstrumentedStorageMixin, LocalStorage):
        pass
    
    storage = InstrumentedStorage('/data', metrics_name='main-storage')
    
    # 获取指标
    collector = MetricsCollector()
    metrics = collector.get_all()
    
    # 集成 Prometheus
    collector.on_operation(prometheus_callback)
"""

import time
import threading
import logging
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, Optional, Callable, List, Any, Union, BinaryIO

logger = logging.getLogger(__name__)


class OperationType(Enum):
    """存储操作类型"""
    SAVE = "save"
    READ = "read"
    READ_BYTES = "read_bytes"
    DELETE = "delete"
    EXISTS = "exists"
    GET_INFO = "get_info"
    LIST = "list"
    GET_URL = "get_url"
    COPY = "copy"
    MOVE = "move"


@dataclass
class OperationMetrics:
    """单个操作类型的指标
    
    Attributes:
        count: 总操作次数
        success_count: 成功次数
        error_count: 失败次数
        total_bytes: 处理的总字节数
        total_duration_ms: 总耗时（毫秒）
        min_duration_ms: 最小耗时
        max_duration_ms: 最大耗时
    """
    count: int = 0
    success_count: int = 0
    error_count: int = 0
    total_bytes: int = 0
    total_duration_ms: float = 0
    min_duration_ms: float = float('inf')
    max_duration_ms: float = 0
    
    @property
    def avg_duration_ms(self) -> float:
        """平均耗时"""
        return self.total_duration_ms / self.count if self.count else 0
    
    @property
    def success_rate(self) -> float:
        """成功率"""
        return self.success_count / self.count if self.count else 1.0
    
    @property
    def error_rate(self) -> float:
        """错误率"""
        return self.error_count / self.count if self.count else 0
    
    def record(self, success: bool, duration_ms: float, bytes_count: int = 0) -> None:
        """记录一次操作"""
        self.count += 1
        self.total_duration_ms += duration_ms
        self.total_bytes += bytes_count
        
        if success:
            self.success_count += 1
        else:
            self.error_count += 1
        
        # 更新最小/最大耗时
        if duration_ms < self.min_duration_ms:
            self.min_duration_ms = duration_ms
        if duration_ms > self.max_duration_ms:
            self.max_duration_ms = duration_ms
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'count': self.count,
            'success_count': self.success_count,
            'error_count': self.error_count,
            'success_rate': round(self.success_rate, 4),
            'total_bytes': self.total_bytes,
            'total_duration_ms': round(self.total_duration_ms, 2),
            'avg_duration_ms': round(self.avg_duration_ms, 2),
            'min_duration_ms': round(self.min_duration_ms, 2) if self.count else 0,
            'max_duration_ms': round(self.max_duration_ms, 2),
        }
    
    def reset(self) -> None:
        """重置指标"""
        self.count = 0
        self.success_count = 0
        self.error_count = 0
        self.total_bytes = 0
        self.total_duration_ms = 0
        self.min_duration_ms = float('inf')
        self.max_duration_ms = 0


@dataclass
class StorageMetrics:
    """存储后端指标
    
    Attributes:
        backend_name: 后端名称
        operations: 各操作类型的指标
        start_time: 开始统计时间
    """
    backend_name: str
    operations: Dict[str, OperationMetrics] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    _lock: threading.RLock = field(default_factory=threading.RLock, repr=False)
    
    def record(
        self,
        operation: OperationType,
        success: bool,
        duration_ms: float,
        bytes_count: int = 0,
    ) -> None:
        """记录操作指标
        
        Args:
            operation: 操作类型
            success: 是否成功
            duration_ms: 耗时（毫秒）
            bytes_count: 处理的字节数
        """
        op_name = operation.value
        
        with self._lock:
            if op_name not in self.operations:
                self.operations[op_name] = OperationMetrics()
            
            self.operations[op_name].record(success, duration_ms, bytes_count)
    
    @property
    def uptime_seconds(self) -> float:
        """运行时间（秒）"""
        return time.time() - self.start_time
    
    @property
    def total_operations(self) -> int:
        """总操作数"""
        return sum(m.count for m in self.operations.values())
    
    @property
    def total_errors(self) -> int:
        """总错误数"""
        return sum(m.error_count for m in self.operations.values())
    
    def to_dict(self) -> dict:
        """转换为字典"""
        with self._lock:
            return {
                'backend': self.backend_name,
                'uptime_seconds': round(self.uptime_seconds, 2),
                'total_operations': self.total_operations,
                'total_errors': self.total_errors,
                'operations': {
                    name: m.to_dict()
                    for name, m in sorted(self.operations.items())
                }
            }
    
    def reset(self) -> None:
        """重置所有指标"""
        with self._lock:
            self.operations.clear()
            self.start_time = time.time()


class MetricsCollector:
    """指标收集器（单例）
    
    管理所有存储后端的指标，支持注册回调函数用于外部监控集成。
    
    Example:
        collector = MetricsCollector()
        
        # 获取所有指标
        all_metrics = collector.get_all()
        
        # 注册 Prometheus 回调
        collector.on_operation(prometheus_callback)
    """
    
    _instance: Optional['MetricsCollector'] = None
    _lock = threading.Lock()
    
    def __new__(cls) -> 'MetricsCollector':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._metrics: Dict[str, StorageMetrics] = {}
                    instance._callbacks: List[Callable] = []
                    instance._metrics_lock = threading.RLock()
                    cls._instance = instance
        return cls._instance
    
    def get_or_create(self, backend_name: str) -> StorageMetrics:
        """获取或创建后端指标
        
        Args:
            backend_name: 后端名称
            
        Returns:
            StorageMetrics: 后端指标对象
        """
        with self._metrics_lock:
            if backend_name not in self._metrics:
                self._metrics[backend_name] = StorageMetrics(backend_name)
            return self._metrics[backend_name]
    
    def get(self, backend_name: str) -> Optional[StorageMetrics]:
        """获取指定后端的指标
        
        Args:
            backend_name: 后端名称
            
        Returns:
            Optional[StorageMetrics]: 指标对象，不存在返回 None
        """
        with self._metrics_lock:
            return self._metrics.get(backend_name)
    
    def get_all(self) -> Dict[str, dict]:
        """获取所有后端的指标
        
        Returns:
            Dict[str, dict]: 所有后端的指标字典
        """
        with self._metrics_lock:
            return {
                name: m.to_dict()
                for name, m in sorted(self._metrics.items())
            }
    
    def list_backends(self) -> List[str]:
        """列出所有被监控的后端名称"""
        with self._metrics_lock:
            return list(self._metrics.keys())
    
    def on_operation(self, callback: Callable) -> None:
        """注册操作回调
        
        回调函数签名：
            def callback(backend: str, operation: str, success: bool, duration_ms: float, **extra)
        
        Args:
            callback: 回调函数
        """
        self._callbacks.append(callback)
    
    def remove_callback(self, callback: Callable) -> bool:
        """移除回调函数"""
        try:
            self._callbacks.remove(callback)
            return True
        except ValueError:
            return False
    
    def notify(
        self,
        backend: str,
        operation: str,
        success: bool,
        duration_ms: float,
        **extra: Any,
    ) -> None:
        """通知所有回调
        
        Args:
            backend: 后端名称
            operation: 操作类型
            success: 是否成功
            duration_ms: 耗时
            **extra: 额外信息（path, size 等）
        """
        for callback in self._callbacks:
            try:
                callback(backend, operation, success, duration_ms, **extra)
            except Exception as e:
                logger.warning(f"Metrics callback error: {e}")
    
    def reset(self, backend_name: Optional[str] = None) -> None:
        """重置指标
        
        Args:
            backend_name: 指定后端名称，None 则重置所有
        """
        with self._metrics_lock:
            if backend_name:
                if backend_name in self._metrics:
                    self._metrics[backend_name].reset()
            else:
                for m in self._metrics.values():
                    m.reset()
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        with cls._lock:
            cls._instance = None


class InstrumentedStorageMixin:
    """带监控指标的存储Mixin
    
    为存储后端自动添加操作监控功能。
    
    Example:
        class InstrumentedLocalStorage(InstrumentedStorageMixin, LocalStorage):
            pass
        
        storage = InstrumentedLocalStorage('/data', metrics_name='uploads')
        storage.save('test.txt', b'content')
        
        # 查看指标
        print(storage.get_metrics())
    """
    
    def __init__(
        self,
        *args,
        metrics_name: Optional[str] = None,
        enable_logging: bool = True,
        **kwargs,
    ):
        """初始化
        
        Args:
            *args: 传递给父类的参数
            metrics_name: 指标名称，默认使用类名
            enable_logging: 是否启用日志记录
            **kwargs: 传递给父类的参数
        """
        super().__init__(*args, **kwargs)
        self._metrics_name = metrics_name or self.__class__.__name__
        self._enable_logging = enable_logging
        self._collector = MetricsCollector()
        self._storage_metrics = self._collector.get_or_create(self._metrics_name)
    
    @contextmanager
    def _track_operation(
        self,
        operation: OperationType,
        path: str = "",
        size: int = 0,
    ):
        """跟踪操作的上下文管理器
        
        Args:
            operation: 操作类型
            path: 文件路径
            size: 数据大小
        """
        start = time.perf_counter()
        success = True
        error: Optional[Exception] = None
        
        try:
            yield
        except Exception as e:
            success = False
            error = e
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            
            # 记录指标
            self._storage_metrics.record(operation, success, duration_ms, size)
            
            # 结构化日志
            if self._enable_logging:
                log_data = {
                    'backend': self._metrics_name,
                    'operation': operation.value,
                    'path': path,
                    'success': success,
                    'duration_ms': round(duration_ms, 2),
                }
                if size:
                    log_data['bytes'] = size
                if error:
                    log_data['error'] = str(error)
                    log_data['error_type'] = type(error).__name__
                
                if success:
                    logger.debug(f"Storage operation: {operation.value}", extra=log_data)
                else:
                    logger.warning(f"Storage operation failed: {operation.value}", extra=log_data)
            
            # 通知外部监控
            self._collector.notify(
                self._metrics_name,
                operation.value,
                success,
                duration_ms,
                path=path,
                size=size,
                error=str(error) if error else None,
            )
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        **kwargs,
    ) -> str:
        """保存文件（带监控）"""
        size = len(content) if isinstance(content, bytes) else 0
        with self._track_operation(OperationType.SAVE, path, size):
            return super().save(path, content, **kwargs)
    
    def read(self, path: str) -> BinaryIO:
        """读取文件（带监控）"""
        with self._track_operation(OperationType.READ, path):
            return super().read(path)
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件字节（带监控）"""
        with self._track_operation(OperationType.READ_BYTES, path):
            return super().read_bytes(path)
    
    def delete(self, path: str) -> bool:
        """删除文件（带监控）"""
        with self._track_operation(OperationType.DELETE, path):
            return super().delete(path)
    
    def exists(self, path: str) -> bool:
        """检查文件存在（带监控）"""
        with self._track_operation(OperationType.EXISTS, path):
            return super().exists(path)
    
    def get_info(self, path: str):
        """获取文件信息（带监控）"""
        with self._track_operation(OperationType.GET_INFO, path):
            return super().get_info(path)
    
    def list(self, prefix: str = "", **kwargs):
        """列出文件（带监控）"""
        with self._track_operation(OperationType.LIST, prefix):
            return super().list(prefix, **kwargs)
    
    def get_url(self, path: str, **kwargs) -> str:
        """获取URL（带监控）"""
        with self._track_operation(OperationType.GET_URL, path):
            return super().get_url(path, **kwargs)
    
    def copy(self, src: str, dst: str, **kwargs) -> str:
        """复制文件（带监控）"""
        with self._track_operation(OperationType.COPY, f"{src} -> {dst}"):
            return super().copy(src, dst, **kwargs)
    
    def move(self, src: str, dst: str, **kwargs) -> str:
        """移动文件（带监控）"""
        with self._track_operation(OperationType.MOVE, f"{src} -> {dst}"):
            return super().move(src, dst, **kwargs)
    
    def get_metrics(self) -> dict:
        """获取当前后端的指标"""
        return self._storage_metrics.to_dict()
    
    def reset_metrics(self) -> None:
        """重置当前后端的指标"""
        self._storage_metrics.reset()


__all__ = [
    'OperationType',
    'OperationMetrics',
    'StorageMetrics',
    'MetricsCollector',
    'InstrumentedStorageMixin',
]
