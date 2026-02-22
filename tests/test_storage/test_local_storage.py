# -*- coding: utf-8 -*-
"""本地存储后端测试"""

import os
import pytest
import tempfile
import shutil
from pathlib import Path
from io import BytesIO

from yweb.storage import LocalStorage, FileInfo, StorageError


class TestLocalStorageBasic:
    """本地存储基本功能测试"""
    
    def setup_method(self):
        """创建临时目录"""
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        """清理临时目录"""
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_save_and_read_bytes(self):
        """测试保存和读取字节内容"""
        content = b"Hello, World!"
        path = "test/hello.txt"
        
        result = self.storage.save(path, content)
        assert result == path
        
        data = self.storage.read_bytes(path)
        assert data == content
    
    def test_save_and_read_file_object(self):
        """测试保存和读取文件对象"""
        content = b"File content"
        path = "test/file.txt"
        
        file_obj = BytesIO(content)
        self.storage.save(path, file_obj)
        
        with self.storage.read(path) as f:
            data = f.read()
        assert data == content
    
    def test_auto_create_directories(self):
        """测试自动创建目录"""
        path = "deep/nested/dir/file.txt"
        self.storage.save(path, b"content")
        
        assert self.storage.exists(path)
        
        full_path = Path(self.temp_dir) / path
        assert full_path.exists()
    
    def test_save_overwrite_true(self):
        """测试覆盖保存"""
        path = "test/file.txt"
        
        self.storage.save(path, b"content1")
        self.storage.save(path, b"content2", overwrite=True)
        
        data = self.storage.read_bytes(path)
        assert data == b"content2"
    
    def test_save_overwrite_false_raises(self):
        """测试禁止覆盖时抛出异常"""
        path = "test/file.txt"
        
        self.storage.save(path, b"content1")
        
        with pytest.raises(FileExistsError):
            self.storage.save(path, b"content2", overwrite=False)
    
    def test_delete_file(self):
        """测试删除文件"""
        path = "test/file.txt"
        
        self.storage.save(path, b"content")
        assert self.storage.exists(path)
        
        result = self.storage.delete(path)
        assert result is True
        assert not self.storage.exists(path)
    
    def test_delete_nonexistent(self):
        """测试删除不存在的文件"""
        result = self.storage.delete("nonexistent.txt")
        assert result is False
    
    def test_exists(self):
        """测试文件存在检查"""
        path = "test/file.txt"
        
        assert not self.storage.exists(path)
        
        self.storage.save(path, b"content")
        assert self.storage.exists(path)
    
    def test_read_nonexistent_raises(self):
        """测试读取不存在的文件抛出异常"""
        with pytest.raises(FileNotFoundError):
            self.storage.read("nonexistent.txt")


class TestLocalStoragePathSecurity:
    """路径安全测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_path_traversal_attack_prevented(self):
        """测试路径穿越攻击被阻止"""
        with pytest.raises(StorageError):
            self.storage.save("../outside.txt", b"malicious")
    
    def test_double_dot_in_path_prevented(self):
        """测试双点路径被阻止"""
        with pytest.raises(StorageError):
            self.storage.save("dir/../../etc/passwd", b"malicious")
    
    def test_absolute_path_normalized(self):
        """测试绝对路径被规范化"""
        # 开头的斜杠应该被移除
        self.storage.save("/test/file.txt", b"content")
        
        assert self.storage.exists("test/file.txt")
    
    def test_backslash_normalized(self):
        """测试反斜杠被规范化"""
        self.storage.save("dir\\subdir\\file.txt", b"content")
        
        assert self.storage.exists("dir/subdir/file.txt")


class TestLocalStorageFileInfo:
    """文件信息测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_info(self):
        """测试获取文件信息"""
        content = b"Hello, World!"
        path = "test/hello.txt"
        
        self.storage.save(path, content)
        
        info = self.storage.get_info(path)
        
        assert info.path == path
        assert info.size == len(content)
        assert info.content_type == "text/plain"
        assert info.etag is not None
        assert info.created_at is not None
        assert info.modified_at is not None
    
    def test_get_info_nonexistent_raises(self):
        """测试获取不存在文件的信息抛出异常"""
        with pytest.raises(FileNotFoundError):
            self.storage.get_info("nonexistent.txt")
    
    def test_auto_content_type_detection(self):
        """测试自动内容类型检测"""
        self.storage.save("test.jpg", b"fake image")
        info = self.storage.get_info("test.jpg")
        assert info.content_type == "image/jpeg"
        
        self.storage.save("test.pdf", b"fake pdf")
        info = self.storage.get_info("test.pdf")
        assert info.content_type == "application/pdf"


class TestLocalStorageList:
    """文件列表测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
        
        # 创建测试文件
        self.storage.save("dir1/file1.txt", b"1")
        self.storage.save("dir1/file2.txt", b"2")
        self.storage.save("dir1/subdir/file3.txt", b"3")
        self.storage.save("dir2/file4.txt", b"4")
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_list_all(self):
        """测试列出所有文件"""
        files = self.storage.list()
        assert len(files) == 4
    
    def test_list_with_prefix(self):
        """测试按前缀列出文件"""
        files = self.storage.list(prefix="dir1")
        assert len(files) == 3
        
        files = self.storage.list(prefix="dir2")
        assert len(files) == 1
    
    def test_list_non_recursive(self):
        """测试非递归列出文件"""
        files = self.storage.list(prefix="dir1", recursive=False)
        assert len(files) == 2  # 只有 file1.txt 和 file2.txt
    
    def test_list_with_limit(self):
        """测试限制返回数量"""
        files = self.storage.list(limit=2)
        assert len(files) == 2
    
    def test_list_empty_prefix(self):
        """测试空前缀返回所有文件"""
        files = self.storage.list(prefix="nonexistent")
        assert len(files) == 0


class TestLocalStorageURL:
    """URL 生成测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_url_without_base_url_raises(self):
        """测试未配置 base_url 时抛出异常"""
        storage = LocalStorage(self.temp_dir)
        storage.save("file.txt", b"content")
        
        with pytest.raises(NotImplementedError):
            storage.get_url("file.txt")
    
    def test_get_url_with_base_url(self):
        """测试配置 base_url 后生成 URL"""
        storage = LocalStorage(
            self.temp_dir,
            base_url="https://example.com/files"
        )
        storage.save("test/file.txt", b"content")
        
        url = storage.get_url("test/file.txt")
        assert url == "https://example.com/files/test/file.txt"
    
    def test_get_url_nonexistent_raises(self):
        """测试获取不存在文件的 URL 抛出异常"""
        storage = LocalStorage(
            self.temp_dir,
            base_url="https://example.com/files"
        )
        
        with pytest.raises(FileNotFoundError):
            storage.get_url("nonexistent.txt")


class TestLocalStorageSpecialMethods:
    """特殊方法测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_get_absolute_path(self):
        """测试获取绝对路径"""
        self.storage.save("test/file.txt", b"content")
        
        abs_path = self.storage.get_absolute_path("test/file.txt")
        
        assert os.path.isabs(abs_path)
        assert os.path.exists(abs_path)
    
    def test_get_relative_path(self):
        """测试获取相对路径"""
        self.storage.save("test/file.txt", b"content")
        
        abs_path = self.storage.get_absolute_path("test/file.txt")
        rel_path = self.storage.get_relative_path(abs_path)
        
        assert rel_path == "test/file.txt"
    
    def test_get_relative_path_outside_raises(self):
        """测试获取存储目录外路径的相对路径抛出异常"""
        with pytest.raises(StorageError):
            self.storage.get_relative_path("/etc/passwd")
    
    def test_ensure_directory(self):
        """测试确保目录存在"""
        self.storage.ensure_directory("new/nested/dir")
        
        dir_path = Path(self.temp_dir) / "new/nested/dir"
        assert dir_path.exists()
        assert dir_path.is_dir()
    
    def test_get_stats(self):
        """测试获取统计信息"""
        self.storage.save("file1.txt", b"x" * 100)
        self.storage.save("file2.txt", b"x" * 200)
        
        stats = self.storage.get_stats()
        
        assert stats['exists'] is True
        assert stats['file_count'] == 2
        assert stats['total_size'] == 300
        assert stats['base_path'] == self.temp_dir


class TestLocalStorageCopyMove:
    """复制和移动测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_copy(self):
        """测试复制文件"""
        content = b"Hello, World!"
        self.storage.save("src.txt", content)
        
        result = self.storage.copy("src.txt", "dst.txt")
        
        assert result == "dst.txt"
        assert self.storage.exists("src.txt")
        assert self.storage.exists("dst.txt")
        assert self.storage.read_bytes("dst.txt") == content
    
    def test_move(self):
        """测试移动文件"""
        content = b"Hello, World!"
        self.storage.save("src.txt", content)
        
        result = self.storage.move("src.txt", "dst.txt")
        
        assert result == "dst.txt"
        assert not self.storage.exists("src.txt")
        assert self.storage.exists("dst.txt")
        assert self.storage.read_bytes("dst.txt") == content
    
    def test_copy_to_different_directory(self):
        """测试复制到不同目录"""
        self.storage.save("dir1/file.txt", b"content")
        
        self.storage.copy("dir1/file.txt", "dir2/file.txt")
        
        assert self.storage.exists("dir1/file.txt")
        assert self.storage.exists("dir2/file.txt")


class TestLocalStorageDirectoryDeletion:
    """目录删除测试"""
    
    def setup_method(self):
        self.temp_dir = tempfile.mkdtemp()
        self.storage = LocalStorage(self.temp_dir)
    
    def teardown_method(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)
    
    def test_delete_directory(self):
        """测试删除目录（递归）"""
        self.storage.save("dir/file1.txt", b"1")
        self.storage.save("dir/subdir/file2.txt", b"2")
        
        # 删除整个目录
        result = self.storage.delete("dir")
        
        assert result is True
        assert not self.storage.exists("dir/file1.txt")
        assert not self.storage.exists("dir/subdir/file2.txt")


class TestLocalStorageInitialization:
    """初始化测试"""
    
    def test_create_dirs_true(self):
        """测试自动创建目录"""
        temp_dir = tempfile.mkdtemp()
        target_dir = os.path.join(temp_dir, "new", "storage")
        
        try:
            storage = LocalStorage(target_dir, create_dirs=True)
            assert os.path.exists(target_dir)
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
    
    def test_create_dirs_false_existing(self):
        """测试 create_dirs=False 但目录存在"""
        temp_dir = tempfile.mkdtemp()
        
        try:
            storage = LocalStorage(temp_dir, create_dirs=False)
            storage.save("file.txt", b"content")
            assert storage.exists("file.txt")
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
