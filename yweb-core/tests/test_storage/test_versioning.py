# -*- coding: utf-8 -*-
"""文件版本管理测试"""

import pytest
import tempfile
import shutil
import time
from datetime import datetime

from yweb.storage.versioning import FileVersion, VersionedStorageMixin
from yweb.storage import LocalStorage


# ==================== FileVersion 测试 ====================

class TestFileVersion:
    """FileVersion 数据类测试"""
    
    def test_create_version(self):
        """测试创建版本"""
        version = FileVersion(
            version_id="20240115_abc123",
            path="test/file.txt",
            size=1024,
            etag="abc123def456",
            created_at=datetime.now(),
            message="Initial version",
            is_current=True,
        )
        
        assert version.version_id == "20240115_abc123"
        assert version.path == "test/file.txt"
        assert version.size == 1024
        assert version.is_current is True
    
    def test_to_dict(self):
        """测试转换为字典"""
        version = FileVersion(
            version_id="v1",
            path="file.txt",
            size=100,
            etag="abc",
            created_at=datetime(2024, 1, 15, 12, 0, 0),
            created_by="user1",
            message="Test",
            is_current=True,
        )
        
        data = version.to_dict()
        
        assert data['version_id'] == "v1"
        assert data['path'] == "file.txt"
        assert data['size'] == 100
        assert data['created_by'] == "user1"
        assert data['is_current'] is True
    
    def test_from_dict(self):
        """测试从字典创建"""
        data = {
            'version_id': 'v1',
            'path': 'file.txt',
            'size': 100,
            'etag': 'abc',
            'created_at': '2024-01-15T12:00:00',
            'created_by': 'user1',
            'message': 'Test',
            'is_current': True,
        }
        
        version = FileVersion.from_dict(data)
        
        assert version.version_id == "v1"
        assert version.path == "file.txt"
        assert version.created_by == "user1"
        assert isinstance(version.created_at, datetime)


# ==================== VersionedStorageMixin 测试 ====================

class VersionedLocalStorage(VersionedStorageMixin, LocalStorage):
    """用于测试的版本化本地存储"""
    pass


class TestVersionedStorageMixin:
    """版本管理 Mixin 测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def storage(self, temp_dir):
        """创建存储实例"""
        return VersionedLocalStorage(temp_dir, enable_versioning=True)
    
    def test_save_creates_version(self, storage):
        """测试保存创建版本"""
        storage.save("test.txt", b"content v1")
        
        versions = storage.list_versions("test.txt")
        
        assert len(versions) == 1
        assert versions[0].is_current is True
    
    def test_multiple_saves_create_versions(self, storage):
        """测试多次保存创建多个版本"""
        storage.save("test.txt", b"v1")
        time.sleep(0.01)  # 确保时间戳不同
        storage.save("test.txt", b"v2")
        time.sleep(0.01)
        storage.save("test.txt", b"v3")
        
        versions = storage.list_versions("test.txt")
        
        assert len(versions) == 3
        # 最新版本在前面
        assert versions[0].is_current is True
        assert versions[1].is_current is False
        assert versions[2].is_current is False
    
    def test_save_same_content_no_new_version(self, storage):
        """测试保存相同内容不创建新版本"""
        storage.save("test.txt", b"same content")
        storage.save("test.txt", b"same content")
        storage.save("test.txt", b"same content")
        
        versions = storage.list_versions("test.txt")
        
        # 内容相同，只有一个版本
        assert len(versions) == 1
    
    def test_save_with_message(self, storage):
        """测试保存带版本说明"""
        storage.save("test.txt", b"content", version_message="Initial commit")
        
        versions = storage.list_versions("test.txt")
        
        assert versions[0].message == "Initial commit"
    
    def test_save_with_created_by(self, storage):
        """测试保存带创建者"""
        storage.save("test.txt", b"content", created_by="user123")
        
        versions = storage.list_versions("test.txt")
        
        assert versions[0].created_by == "user123"
    
    def test_get_version_content(self, storage):
        """测试获取版本内容"""
        storage.save("test.txt", b"version 1")
        time.sleep(0.01)
        storage.save("test.txt", b"version 2")
        
        versions = storage.list_versions("test.txt")
        
        # 获取旧版本内容
        v1_content = storage.get_version("test.txt", versions[1].version_id)
        v2_content = storage.get_version("test.txt", versions[0].version_id)
        
        assert v1_content == b"version 1"
        assert v2_content == b"version 2"
    
    def test_get_current_version(self, storage):
        """测试获取当前版本"""
        storage.save("test.txt", b"v1")
        time.sleep(0.01)
        storage.save("test.txt", b"v2")
        
        current = storage.get_current_version("test.txt")
        
        assert current is not None
        assert current.is_current is True
        
        # 验证当前版本内容
        content = storage.get_version("test.txt", current.version_id)
        assert content == b"v2"
    
    def test_get_current_version_nonexistent(self, storage):
        """测试获取不存在文件的当前版本"""
        result = storage.get_current_version("nonexistent.txt")
        assert result is None
    
    def test_restore_version(self, storage):
        """测试恢复版本"""
        storage.save("test.txt", b"original")
        time.sleep(0.01)
        storage.save("test.txt", b"modified")
        
        versions = storage.list_versions("test.txt")
        old_version_id = versions[1].version_id
        
        # 恢复到旧版本
        storage.restore_version("test.txt", old_version_id, message="Restored")
        
        # 验证当前内容
        content = storage.read_bytes("test.txt")
        assert content == b"original"
        
        # 应该有3个版本
        versions = storage.list_versions("test.txt")
        assert len(versions) == 3
        assert "Restored" in versions[0].message
    
    def test_delete_version(self, storage):
        """测试删除版本"""
        storage.save("test.txt", b"v1")
        time.sleep(0.01)
        storage.save("test.txt", b"v2")
        
        versions = storage.list_versions("test.txt")
        old_version_id = versions[1].version_id
        
        # 删除旧版本
        result = storage.delete_version("test.txt", old_version_id)
        
        assert result is True
        
        # 验证版本被删除
        versions = storage.list_versions("test.txt")
        assert len(versions) == 1
    
    def test_delete_current_version_raises(self, storage):
        """测试删除当前版本抛出异常"""
        storage.save("test.txt", b"content")
        
        versions = storage.list_versions("test.txt")
        current_version_id = versions[0].version_id
        
        with pytest.raises(ValueError):
            storage.delete_version("test.txt", current_version_id)
    
    def test_delete_nonexistent_version(self, storage):
        """测试删除不存在的版本"""
        storage.save("test.txt", b"content")
        
        result = storage.delete_version("test.txt", "nonexistent_id")
        
        assert result is False
    
    def test_delete_all_versions(self, storage):
        """测试删除所有版本"""
        storage.save("test.txt", b"v1")
        time.sleep(0.01)
        storage.save("test.txt", b"v2")
        time.sleep(0.01)
        storage.save("test.txt", b"v3")
        
        count = storage.delete_all_versions("test.txt")
        
        assert count == 3
        
        # 验证版本被删除
        versions = storage.list_versions("test.txt")
        assert len(versions) == 0
    
    def test_list_versions_order(self, storage):
        """测试版本列表顺序"""
        storage.save("test.txt", b"first", version_message="First")
        time.sleep(0.01)
        storage.save("test.txt", b"second", version_message="Second")
        time.sleep(0.01)
        storage.save("test.txt", b"third", version_message="Third")
        
        versions = storage.list_versions("test.txt")
        
        # 最新的在前面
        assert versions[0].message == "Third"
        assert versions[1].message == "Second"
        assert versions[2].message == "First"
    
    def test_get_version_info(self, storage):
        """测试获取版本信息"""
        storage.save("test.txt", b"content", version_message="Test version")
        
        versions = storage.list_versions("test.txt")
        version_id = versions[0].version_id
        
        info = storage.get_version_info("test.txt", version_id)
        
        assert info is not None
        assert info.message == "Test version"
    
    def test_compare_versions(self, storage):
        """测试比较版本"""
        storage.save("test.txt", b"short")
        time.sleep(0.01)
        storage.save("test.txt", b"much longer content")
        
        versions = storage.list_versions("test.txt")
        
        result = storage.compare_versions(
            "test.txt",
            versions[1].version_id,
            versions[0].version_id,
        )
        
        assert result['same_content'] is False
        assert result['size_diff'] > 0  # 新版本更大


class TestVersionedStorageDisabled:
    """版本控制禁用测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_versioning_disabled(self, temp_dir):
        """测试禁用版本控制"""
        storage = VersionedLocalStorage(temp_dir, enable_versioning=False)
        
        storage.save("test.txt", b"v1")
        storage.save("test.txt", b"v2")
        
        # 不应该有版本记录
        versions = storage.list_versions("test.txt")
        assert len(versions) == 0
    
    def test_skip_versioning_flag(self, temp_dir):
        """测试跳过版本控制标志"""
        storage = VersionedLocalStorage(temp_dir, enable_versioning=True)
        
        storage.save("test.txt", b"v1")
        storage.save("test.txt", b"v2", skip_versioning=True)
        
        # 只有一个版本
        versions = storage.list_versions("test.txt")
        assert len(versions) == 1


class TestVersionedStorageMaxVersions:
    """最大版本数限制测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    def test_max_versions_limit(self, temp_dir):
        """测试最大版本数限制"""
        storage = VersionedLocalStorage(temp_dir, max_versions=3)
        
        # 创建5个版本
        for i in range(5):
            storage.save("test.txt", f"version {i}".encode())
            time.sleep(0.01)
        
        versions = storage.list_versions("test.txt")
        
        # 只保留最新的3个
        assert len(versions) == 3
    
    def test_old_versions_deleted(self, temp_dir):
        """测试旧版本被删除"""
        storage = VersionedLocalStorage(temp_dir, max_versions=2)
        
        storage.save("test.txt", b"v1", version_message="First")
        time.sleep(0.01)
        storage.save("test.txt", b"v2", version_message="Second")
        time.sleep(0.01)
        storage.save("test.txt", b"v3", version_message="Third")
        
        versions = storage.list_versions("test.txt")
        
        # 只有最新的2个
        assert len(versions) == 2
        assert versions[0].message == "Third"
        assert versions[1].message == "Second"
