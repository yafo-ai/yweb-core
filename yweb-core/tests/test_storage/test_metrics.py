# -*- coding: utf-8 -*-
"""监控指标测试"""

import pytest
import time
import tempfile
import shutil
import threading

from yweb.storage.metrics import (
    OperationType,
    OperationMetrics,
    StorageMetrics,
    MetricsCollector,
    InstrumentedStorageMixin,
)
from yweb.storage import LocalStorage


# ==================== OperationMetrics 测试 ====================

class TestOperationMetrics:
    """操作指标测试"""
    
    def test_initial_values(self):
        """测试初始值"""
        metrics = OperationMetrics()
        
        assert metrics.count == 0
        assert metrics.success_count == 0
        assert metrics.error_count == 0
        assert metrics.total_bytes == 0
        assert metrics.total_duration_ms == 0
    
    def test_record_success(self):
        """测试记录成功操作"""
        metrics = OperationMetrics()
        
        metrics.record(success=True, duration_ms=10.5, bytes_count=1024)
        
        assert metrics.count == 1
        assert metrics.success_count == 1
        assert metrics.error_count == 0
        assert metrics.total_bytes == 1024
        assert metrics.total_duration_ms == 10.5
    
    def test_record_failure(self):
        """测试记录失败操作"""
        metrics = OperationMetrics()
        
        metrics.record(success=False, duration_ms=5.0)
        
        assert metrics.count == 1
        assert metrics.success_count == 0
        assert metrics.error_count == 1
    
    def test_multiple_records(self):
        """测试多次记录"""
        metrics = OperationMetrics()
        
        metrics.record(success=True, duration_ms=10, bytes_count=100)
        metrics.record(success=True, duration_ms=20, bytes_count=200)
        metrics.record(success=False, duration_ms=5)
        
        assert metrics.count == 3
        assert metrics.success_count == 2
        assert metrics.error_count == 1
        assert metrics.total_bytes == 300
        assert metrics.total_duration_ms == 35
    
    def test_avg_duration(self):
        """测试平均耗时"""
        metrics = OperationMetrics()
        
        metrics.record(success=True, duration_ms=10)
        metrics.record(success=True, duration_ms=20)
        metrics.record(success=True, duration_ms=30)
        
        assert metrics.avg_duration_ms == 20
    
    def test_avg_duration_empty(self):
        """测试空指标的平均耗时"""
        metrics = OperationMetrics()
        assert metrics.avg_duration_ms == 0
    
    def test_success_rate(self):
        """测试成功率"""
        metrics = OperationMetrics()
        
        metrics.record(success=True, duration_ms=10)
        metrics.record(success=True, duration_ms=10)
        metrics.record(success=False, duration_ms=10)
        metrics.record(success=False, duration_ms=10)
        
        assert metrics.success_rate == 0.5
    
    def test_min_max_duration(self):
        """测试最小/最大耗时"""
        metrics = OperationMetrics()
        
        metrics.record(success=True, duration_ms=10)
        metrics.record(success=True, duration_ms=5)
        metrics.record(success=True, duration_ms=20)
        
        assert metrics.min_duration_ms == 5
        assert metrics.max_duration_ms == 20
    
    def test_to_dict(self):
        """测试转换为字典"""
        metrics = OperationMetrics()
        metrics.record(success=True, duration_ms=10, bytes_count=100)
        
        data = metrics.to_dict()
        
        assert data['count'] == 1
        assert data['success_count'] == 1
        assert data['success_rate'] == 1.0
        assert data['total_bytes'] == 100
    
    def test_reset(self):
        """测试重置"""
        metrics = OperationMetrics()
        metrics.record(success=True, duration_ms=10, bytes_count=100)
        
        metrics.reset()
        
        assert metrics.count == 0
        assert metrics.total_bytes == 0


# ==================== StorageMetrics 测试 ====================

class TestStorageMetrics:
    """存储指标测试"""
    
    def test_create(self):
        """测试创建"""
        metrics = StorageMetrics(backend_name="test-backend")
        
        assert metrics.backend_name == "test-backend"
        assert len(metrics.operations) == 0
    
    def test_record_operation(self):
        """测试记录操作"""
        metrics = StorageMetrics(backend_name="test")
        
        metrics.record(OperationType.SAVE, success=True, duration_ms=10, bytes_count=100)
        
        assert 'save' in metrics.operations
        assert metrics.operations['save'].count == 1
    
    def test_record_multiple_operations(self):
        """测试记录多种操作"""
        metrics = StorageMetrics(backend_name="test")
        
        metrics.record(OperationType.SAVE, True, 10, 100)
        metrics.record(OperationType.READ, True, 5)
        metrics.record(OperationType.DELETE, True, 2)
        
        assert len(metrics.operations) == 3
        assert 'save' in metrics.operations
        assert 'read' in metrics.operations
        assert 'delete' in metrics.operations
    
    def test_total_operations(self):
        """测试总操作数"""
        metrics = StorageMetrics(backend_name="test")
        
        metrics.record(OperationType.SAVE, True, 10)
        metrics.record(OperationType.SAVE, True, 10)
        metrics.record(OperationType.READ, True, 5)
        
        assert metrics.total_operations == 3
    
    def test_total_errors(self):
        """测试总错误数"""
        metrics = StorageMetrics(backend_name="test")
        
        metrics.record(OperationType.SAVE, True, 10)
        metrics.record(OperationType.SAVE, False, 10)
        metrics.record(OperationType.READ, False, 5)
        
        assert metrics.total_errors == 2
    
    def test_uptime(self):
        """测试运行时间"""
        metrics = StorageMetrics(backend_name="test")
        
        time.sleep(0.1)
        
        assert metrics.uptime_seconds >= 0.1
    
    def test_to_dict(self):
        """测试转换为字典"""
        metrics = StorageMetrics(backend_name="test")
        metrics.record(OperationType.SAVE, True, 10, 100)
        
        data = metrics.to_dict()
        
        assert data['backend'] == "test"
        assert 'uptime_seconds' in data
        assert 'total_operations' in data
        assert 'operations' in data
    
    def test_reset(self):
        """测试重置"""
        metrics = StorageMetrics(backend_name="test")
        metrics.record(OperationType.SAVE, True, 10, 100)
        
        metrics.reset()
        
        assert len(metrics.operations) == 0


# ==================== MetricsCollector 测试 ====================

class TestMetricsCollector:
    """指标收集器测试"""
    
    @pytest.fixture(autouse=True)
    def reset_collector(self):
        """每个测试前重置收集器"""
        MetricsCollector.reset_instance()
        yield
        MetricsCollector.reset_instance()
    
    def test_singleton(self):
        """测试单例模式"""
        c1 = MetricsCollector()
        c2 = MetricsCollector()
        
        assert c1 is c2
    
    def test_get_or_create(self):
        """测试获取或创建"""
        collector = MetricsCollector()
        
        metrics = collector.get_or_create("backend1")
        
        assert metrics.backend_name == "backend1"
        
        # 再次获取应该返回同一个实例
        metrics2 = collector.get_or_create("backend1")
        assert metrics is metrics2
    
    def test_get_nonexistent(self):
        """测试获取不存在的后端"""
        collector = MetricsCollector()
        
        result = collector.get("nonexistent")
        
        assert result is None
    
    def test_get_all(self):
        """测试获取所有指标"""
        collector = MetricsCollector()
        
        collector.get_or_create("backend1")
        collector.get_or_create("backend2")
        
        all_metrics = collector.get_all()
        
        assert 'backend1' in all_metrics
        assert 'backend2' in all_metrics
    
    def test_list_backends(self):
        """测试列出后端"""
        collector = MetricsCollector()
        
        collector.get_or_create("backend1")
        collector.get_or_create("backend2")
        
        backends = collector.list_backends()
        
        assert 'backend1' in backends
        assert 'backend2' in backends
    
    def test_on_operation_callback(self):
        """测试操作回调"""
        collector = MetricsCollector()
        
        callback_data = []
        
        def callback(backend, operation, success, duration, **extra):
            callback_data.append({
                'backend': backend,
                'operation': operation,
                'success': success,
            })
        
        collector.on_operation(callback)
        collector.notify("test", "save", True, 10.0)
        
        assert len(callback_data) == 1
        assert callback_data[0]['backend'] == "test"
        assert callback_data[0]['operation'] == "save"
    
    def test_remove_callback(self):
        """测试移除回调"""
        collector = MetricsCollector()
        
        def callback(backend, operation, success, duration, **extra):
            pass
        
        collector.on_operation(callback)
        result = collector.remove_callback(callback)
        
        assert result is True
    
    def test_reset_specific_backend(self):
        """测试重置指定后端"""
        collector = MetricsCollector()
        
        m1 = collector.get_or_create("backend1")
        m2 = collector.get_or_create("backend2")
        
        m1.record(OperationType.SAVE, True, 10)
        m2.record(OperationType.SAVE, True, 10)
        
        collector.reset("backend1")
        
        assert m1.total_operations == 0
        assert m2.total_operations == 1


# ==================== InstrumentedStorageMixin 测试 ====================

class InstrumentedLocalStorage(InstrumentedStorageMixin, LocalStorage):
    """用于测试的带监控本地存储"""
    pass


class TestInstrumentedStorageMixin:
    """带监控存储 Mixin 测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture(autouse=True)
    def reset_collector(self):
        """每个测试前重置收集器"""
        MetricsCollector.reset_instance()
        yield
        MetricsCollector.reset_instance()
    
    @pytest.fixture
    def storage(self, temp_dir):
        """创建存储实例"""
        return InstrumentedLocalStorage(temp_dir, metrics_name="test-storage")
    
    def test_save_tracked(self, storage):
        """测试保存操作被跟踪"""
        storage.save("test.txt", b"content")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['save']['count'] == 1
        assert metrics['operations']['save']['success_count'] == 1
    
    def test_read_tracked(self, storage):
        """测试读取操作被跟踪"""
        storage.save("test.txt", b"content")
        storage.read("test.txt")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['read']['count'] == 1
    
    def test_delete_tracked(self, storage):
        """测试删除操作被跟踪"""
        storage.save("test.txt", b"content")
        storage.delete("test.txt")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['delete']['count'] == 1
    
    def test_exists_tracked(self, storage):
        """测试存在检查被跟踪"""
        storage.exists("test.txt")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['exists']['count'] == 1
    
    def test_error_tracked(self, storage):
        """测试错误被跟踪"""
        try:
            storage.read("nonexistent.txt")
        except FileNotFoundError:
            pass
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['read']['error_count'] == 1
    
    def test_bytes_tracked(self, storage):
        """测试字节数被跟踪"""
        storage.save("test.txt", b"x" * 1000)
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['save']['total_bytes'] == 1000
    
    def test_duration_tracked(self, storage):
        """测试耗时被跟踪"""
        storage.save("test.txt", b"content")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['save']['total_duration_ms'] > 0
    
    def test_multiple_operations(self, storage):
        """测试多次操作"""
        for i in range(5):
            storage.save(f"file{i}.txt", b"content")
        
        metrics = storage.get_metrics()
        
        assert metrics['operations']['save']['count'] == 5
        assert metrics['total_operations'] == 5
    
    def test_callback_called(self, storage):
        """测试回调被调用"""
        callback_data = []
        
        def callback(backend, operation, success, duration, **extra):
            callback_data.append(operation)
        
        collector = MetricsCollector()
        collector.on_operation(callback)
        
        storage.save("test.txt", b"content")
        
        assert 'save' in callback_data
    
    def test_reset_metrics(self, storage):
        """测试重置指标"""
        storage.save("test.txt", b"content")
        storage.reset_metrics()
        
        metrics = storage.get_metrics()
        
        assert metrics['total_operations'] == 0
    
    def test_custom_metrics_name(self, temp_dir):
        """测试自定义指标名称"""
        storage = InstrumentedLocalStorage(temp_dir, metrics_name="custom-name")
        
        metrics = storage.get_metrics()
        
        assert metrics['backend'] == "custom-name"


class TestInstrumentedStorageThreadSafety:
    """线程安全测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture(autouse=True)
    def reset_collector(self):
        MetricsCollector.reset_instance()
        yield
        MetricsCollector.reset_instance()
    
    def test_concurrent_operations(self, temp_dir):
        """测试并发操作"""
        storage = InstrumentedLocalStorage(temp_dir, metrics_name="concurrent-test")
        
        errors = []
        
        def worker(worker_id):
            try:
                for i in range(10):
                    path = f"worker{worker_id}_file{i}.txt"
                    storage.save(path, f"content-{worker_id}-{i}".encode())
                    storage.read(path)
                    storage.delete(path)
            except Exception as e:
                errors.append(e)
        
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0
        
        metrics = storage.get_metrics()
        
        # 5 workers * 10 iterations * 3 operations
        assert metrics['total_operations'] == 150
