# -*- coding: utf-8 -*-
"""存储管理器测试"""

import pytest
import tempfile
import shutil

from yweb.storage import (
    StorageManager,
    MemoryStorage,
    LocalStorage,
    StorageNotFoundError,
    StorageConfigError,
)


class TestStorageManagerBasic:
    """存储管理器基本功能测试"""
    
    def setup_method(self):
        """每个测试前重置管理器"""
        StorageManager.reset_all()
    
    def teardown_method(self):
        """每个测试后重置管理器"""
        StorageManager.reset_all()
    
    def test_register_and_get(self):
        """测试注册和获取后端"""
        storage = MemoryStorage()
        StorageManager.register('memory', storage)
        
        result = StorageManager.get('memory')
        assert result is storage
    
    def test_register_with_default(self):
        """测试注册为默认后端"""
        storage1 = MemoryStorage()
        storage2 = MemoryStorage()
        
        StorageManager.register('storage1', storage1)
        StorageManager.register('storage2', storage2, default=True)
        
        assert StorageManager.get() is storage2
        assert StorageManager.get_default_name() == 'storage2'
    
    def test_first_registered_is_default(self):
        """测试第一个注册的成为默认后端"""
        storage1 = MemoryStorage()
        storage2 = MemoryStorage()
        
        StorageManager.register('storage1', storage1)
        StorageManager.register('storage2', storage2)
        
        assert StorageManager.get() is storage1
    
    def test_get_nonexistent_raises(self):
        """测试获取不存在的后端抛出异常"""
        with pytest.raises(StorageNotFoundError):
            StorageManager.get('nonexistent')
    
    def test_get_without_any_registered_raises(self):
        """测试未注册任何后端时获取抛出异常"""
        with pytest.raises(StorageNotFoundError):
            StorageManager.get()
    
    def test_unregister(self):
        """测试注销后端"""
        storage = MemoryStorage()
        StorageManager.register('memory', storage)
        
        result = StorageManager.unregister('memory')
        assert result is True
        
        with pytest.raises(StorageNotFoundError):
            StorageManager.get('memory')
    
    def test_unregister_nonexistent(self):
        """测试注销不存在的后端"""
        result = StorageManager.unregister('nonexistent')
        assert result is False
    
    def test_unregister_default_selects_new(self):
        """测试注销默认后端后选择新的默认"""
        storage1 = MemoryStorage()
        storage2 = MemoryStorage()
        
        StorageManager.register('storage1', storage1)
        StorageManager.register('storage2', storage2)
        
        StorageManager.unregister('storage1')
        
        assert StorageManager.get() is storage2
    
    def test_set_default(self):
        """测试设置默认后端"""
        storage1 = MemoryStorage()
        storage2 = MemoryStorage()
        
        StorageManager.register('storage1', storage1)
        StorageManager.register('storage2', storage2)
        
        StorageManager.set_default('storage2')
        
        assert StorageManager.get() is storage2
    
    def test_set_default_nonexistent_raises(self):
        """测试设置不存在的后端为默认抛出异常"""
        with pytest.raises(StorageNotFoundError):
            StorageManager.set_default('nonexistent')
    
    def test_list_backends(self):
        """测试列出所有后端"""
        StorageManager.register('memory', MemoryStorage())
        
        temp_dir = tempfile.mkdtemp()
        try:
            StorageManager.register('local', LocalStorage(temp_dir))
            
            backends = StorageManager.list_backends()
            
            assert 'memory' in backends
            assert 'local' in backends
            assert backends['memory'] == 'MemoryStorage'
            assert backends['local'] == 'LocalStorage'
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_has_backend(self):
        """测试检查后端是否存在"""
        StorageManager.register('memory', MemoryStorage())
        
        assert StorageManager.has_backend('memory') is True
        assert StorageManager.has_backend('nonexistent') is False


class TestStorageManagerConfigure:
    """配置初始化测试"""
    
    def setup_method(self):
        StorageManager.reset_all()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        StorageManager.reset_all()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_configure_memory_backend(self):
        """测试配置内存后端"""
        StorageManager.configure({
            'backends': {
                'temp': {
                    'type': 'memory',
                    'max_size': 50 * 1024 * 1024,
                }
            }
        })
        
        storage = StorageManager.get('temp')
        assert isinstance(storage, MemoryStorage)
    
    def test_configure_local_backend(self):
        """测试配置本地后端"""
        StorageManager.configure({
            'backends': {
                'local': {
                    'type': 'local',
                    'base_path': self.temp_dir,
                }
            }
        })
        
        storage = StorageManager.get('local')
        assert isinstance(storage, LocalStorage)
    
    def test_configure_multiple_backends(self):
        """测试配置多个后端"""
        StorageManager.configure({
            'backends': {
                'temp': {'type': 'memory'},
                'local': {'type': 'local', 'base_path': self.temp_dir},
            },
            'default': 'local'
        })
        
        assert StorageManager.has_backend('temp')
        assert StorageManager.has_backend('local')
        assert StorageManager.get_default_name() == 'local'
    
    def test_configure_with_default(self):
        """测试配置默认后端"""
        StorageManager.configure({
            'backends': {
                'backend1': {'type': 'memory'},
                'backend2': {'type': 'memory'},
            },
            'default': 'backend2'
        })
        
        assert StorageManager.get_default_name() == 'backend2'
    
    def test_configure_unknown_type_raises(self):
        """测试配置未知类型抛出异常"""
        with pytest.raises(StorageConfigError) as exc_info:
            StorageManager.configure({
                'backends': {
                    'unknown': {'type': 'unknown_type'}
                }
            })
        
        assert 'unknown_type' in str(exc_info.value)
    
    def test_configure_missing_type_raises(self):
        """测试配置缺少 type 抛出异常"""
        with pytest.raises(StorageConfigError) as exc_info:
            StorageManager.configure({
                'backends': {
                    'invalid': {'max_size': 100}
                }
            })
        
        assert 'type' in str(exc_info.value)
    
    def test_configure_empty_raises(self):
        """测试空配置抛出异常"""
        with pytest.raises(StorageConfigError):
            StorageManager.configure({})


class TestStorageManagerReset:
    """重置功能测试"""
    
    def setup_method(self):
        StorageManager.reset_all()
    
    def teardown_method(self):
        StorageManager.reset_all()
    
    def test_reset_clears_backends(self):
        """测试重置清除所有后端"""
        StorageManager.register('memory', MemoryStorage())
        
        StorageManager.reset()
        
        assert len(StorageManager.list_backends()) == 0
    
    def test_reset_clears_default(self):
        """测试重置清除默认设置"""
        StorageManager.register('memory', MemoryStorage())
        
        StorageManager.reset()
        
        assert StorageManager.get_default_name() is None
    
    def test_reset_all_clears_backend_classes(self):
        """测试完全重置清除后端类注册"""
        # 先触发后端类注册
        StorageManager.configure({
            'backends': {
                'temp': {'type': 'memory'}
            }
        })
        
        StorageManager.reset_all()
        
        # 重新配置应该重新注册后端类
        StorageManager.configure({
            'backends': {
                'temp': {'type': 'memory'}
            }
        })
        
        assert StorageManager.has_backend('temp')


class TestStorageManagerStats:
    """统计信息测试"""
    
    def setup_method(self):
        StorageManager.reset_all()
    
    def teardown_method(self):
        StorageManager.reset_all()
    
    def test_get_stats(self):
        """测试获取统计信息"""
        StorageManager.register('memory', MemoryStorage(), default=True)
        
        stats = StorageManager.get_stats()
        
        assert stats['default'] == 'memory'
        assert stats['backend_count'] == 1
        assert 'memory' in stats['backends']
        assert stats['backends']['memory']['type'] == 'MemoryStorage'


class TestStorageManagerIntegration:
    """集成测试"""
    
    def setup_method(self):
        StorageManager.reset_all()
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        StorageManager.reset_all()
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        # 配置
        StorageManager.configure({
            'backends': {
                'temp': {'type': 'memory', 'max_size': 1024 * 1024},
                'local': {'type': 'local', 'base_path': self.temp_dir},
            },
            'default': 'local'
        })
        
        # 使用默认后端保存
        storage = StorageManager.get()
        storage.save('file.txt', b'content from local')
        
        # 使用指定后端保存
        temp_storage = StorageManager.get('temp')
        temp_storage.save('temp.txt', b'content from temp')
        
        # 验证
        assert storage.read_bytes('file.txt') == b'content from local'
        assert temp_storage.read_bytes('temp.txt') == b'content from temp'
        
        # 切换默认后端
        StorageManager.set_default('temp')
        assert StorageManager.get() is temp_storage
