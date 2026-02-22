# -*- coding: utf-8 -*-
"""内存存储后端测试"""

import pytest
import threading
from io import BytesIO

from yweb.storage import MemoryStorage, FileInfo, StorageQuotaExceeded


class TestMemoryStorageBasic:
    """内存存储基本功能测试"""
    
    def setup_method(self):
        """每个测试方法前创建新的存储实例"""
        self.storage = MemoryStorage(max_size=1024 * 1024)  # 1MB
    
    def test_save_and_read_bytes(self):
        """测试保存和读取字节内容"""
        content = b"Hello, World!"
        path = "test/hello.txt"
        
        # 保存
        result = self.storage.save(path, content)
        assert result == path
        
        # 读取
        data = self.storage.read_bytes(path)
        assert data == content
    
    def test_save_and_read_file_object(self):
        """测试保存和读取文件对象"""
        content = b"File content"
        path = "test/file.txt"
        
        # 保存文件对象
        file_obj = BytesIO(content)
        self.storage.save(path, file_obj)
        
        # 读取为文件对象
        with self.storage.read(path) as f:
            data = f.read()
        assert data == content
    
    def test_save_with_content_type(self):
        """测试保存时指定内容类型"""
        content = b"<html></html>"
        path = "test/index.html"
        
        self.storage.save(path, content, content_type="text/html")
        
        info = self.storage.get_info(path)
        assert info.content_type == "text/html"
    
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
    
    def test_delete(self):
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
    
    def test_read_bytes_nonexistent_raises(self):
        """测试读取不存在文件的字节抛出异常"""
        with pytest.raises(FileNotFoundError):
            self.storage.read_bytes("nonexistent.txt")


class TestMemoryStorageFileInfo:
    """文件信息测试"""
    
    def setup_method(self):
        self.storage = MemoryStorage()
    
    def test_get_info(self):
        """测试获取文件信息"""
        content = b"Hello, World!"
        path = "test/hello.txt"
        
        self.storage.save(path, content, content_type="text/plain")
        
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
    
    def test_file_info_filename(self):
        """测试文件名属性"""
        info = FileInfo(path="dir/subdir/file.txt", size=100)
        assert info.filename == "file.txt"
    
    def test_file_info_extension(self):
        """测试扩展名属性"""
        info = FileInfo(path="dir/file.tar.gz", size=100)
        assert info.extension == "gz"
    
    def test_file_info_directory(self):
        """测试目录属性"""
        info = FileInfo(path="dir/subdir/file.txt", size=100)
        assert info.directory == "dir/subdir"
    
    def test_auto_content_type_detection(self):
        """测试自动内容类型检测"""
        self.storage.save("test.jpg", b"fake image")
        info = self.storage.get_info("test.jpg")
        assert info.content_type == "image/jpeg"
        
        self.storage.save("test.pdf", b"fake pdf")
        info = self.storage.get_info("test.pdf")
        assert info.content_type == "application/pdf"


class TestMemoryStorageList:
    """文件列表测试"""
    
    def setup_method(self):
        self.storage = MemoryStorage()
        # 创建测试文件
        self.storage.save("dir1/file1.txt", b"1")
        self.storage.save("dir1/file2.txt", b"2")
        self.storage.save("dir1/subdir/file3.txt", b"3")
        self.storage.save("dir2/file4.txt", b"4")
    
    def test_list_all(self):
        """测试列出所有文件"""
        files = self.storage.list()
        assert len(files) == 4
    
    def test_list_with_prefix(self):
        """测试按前缀列出文件"""
        files = self.storage.list(prefix="dir1/")
        assert len(files) == 3
        
        files = self.storage.list(prefix="dir2/")
        assert len(files) == 1
    
    def test_list_non_recursive(self):
        """测试非递归列出文件"""
        files = self.storage.list(prefix="dir1/", recursive=False)
        assert len(files) == 2  # 只有 file1.txt 和 file2.txt
    
    def test_list_with_limit(self):
        """测试限制返回数量"""
        files = self.storage.list(limit=2)
        assert len(files) == 2


class TestMemoryStorageCapacity:
    """容量管理测试"""
    
    def test_quota_exceeded_single_file(self):
        """测试单个文件超过配额"""
        storage = MemoryStorage(max_size=100)
        
        with pytest.raises(StorageQuotaExceeded):
            storage.save("large.txt", b"x" * 200)
    
    def test_auto_cleanup_lru(self):
        """测试 LRU 自动清理"""
        storage = MemoryStorage(max_size=100, auto_cleanup=True)
        
        # 保存文件直到接近限制
        storage.save("file1.txt", b"x" * 40)
        storage.save("file2.txt", b"x" * 40)
        
        # 访问 file1 使其变为最近访问
        storage.read_bytes("file1.txt")
        
        # 保存新文件，应该淘汰 file2
        storage.save("file3.txt", b"x" * 40)
        
        assert storage.exists("file1.txt")
        assert not storage.exists("file2.txt")
        assert storage.exists("file3.txt")
    
    def test_no_auto_cleanup(self):
        """测试禁用自动清理"""
        storage = MemoryStorage(max_size=100, auto_cleanup=False)
        
        storage.save("file1.txt", b"x" * 40)
        storage.save("file2.txt", b"x" * 40)
        
        with pytest.raises(StorageQuotaExceeded):
            storage.save("file3.txt", b"x" * 40)
    
    def test_max_files_limit(self):
        """测试最大文件数限制"""
        storage = MemoryStorage(max_files=3, auto_cleanup=True)
        
        storage.save("file1.txt", b"1")
        storage.save("file2.txt", b"2")
        storage.save("file3.txt", b"3")
        
        # 保存新文件，应该淘汰最老的
        storage.save("file4.txt", b"4")
        
        assert not storage.exists("file1.txt")
        assert storage.exists("file4.txt")


class TestMemoryStorageStats:
    """统计信息测试"""
    
    def test_get_stats(self):
        """测试获取统计信息"""
        storage = MemoryStorage(max_size=1024 * 1024, max_files=100)
        
        storage.save("file1.txt", b"x" * 100)
        storage.save("file2.txt", b"x" * 200)
        
        stats = storage.get_stats()
        
        assert stats['file_count'] == 2
        assert stats['total_size'] == 300
        assert stats['max_size'] == 1024 * 1024
        assert stats['max_files'] == 100
        assert 0 < stats['usage_percent'] < 1
    
    def test_clear(self):
        """测试清空存储"""
        storage = MemoryStorage()
        
        storage.save("file1.txt", b"1")
        storage.save("file2.txt", b"2")
        
        storage.clear()
        
        stats = storage.get_stats()
        assert stats['file_count'] == 0
        assert stats['total_size'] == 0


class TestMemoryStorageThreadSafety:
    """线程安全测试"""
    
    def test_concurrent_operations(self):
        """测试并发操作"""
        storage = MemoryStorage(max_size=10 * 1024 * 1024)
        errors = []
        
        def writer(thread_id):
            try:
                for i in range(50):
                    path = f"thread{thread_id}/file{i}.txt"
                    storage.save(path, f"content-{thread_id}-{i}".encode())
            except Exception as e:
                errors.append(e)
        
        def reader(thread_id):
            try:
                for i in range(50):
                    path = f"thread{thread_id}/file{i}.txt"
                    if storage.exists(path):
                        storage.read_bytes(path)
            except Exception as e:
                errors.append(e)
        
        threads = []
        for i in range(5):
            threads.append(threading.Thread(target=writer, args=(i,)))
            threads.append(threading.Thread(target=reader, args=(i,)))
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        
        assert len(errors) == 0, f"并发操作出错: {errors}"


class TestMemoryStorageCopyMove:
    """复制和移动测试"""
    
    def setup_method(self):
        self.storage = MemoryStorage()
    
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


class TestMemoryStoragePathNormalization:
    """路径规范化测试"""
    
    def setup_method(self):
        self.storage = MemoryStorage()
    
    def test_leading_slash_removed(self):
        """测试移除开头的斜杠"""
        self.storage.save("/test/file.txt", b"content")
        
        # 路径会被规范化，所以两种写法都能访问到同一个文件
        assert self.storage.exists("test/file.txt")
        assert self.storage.exists("/test/file.txt")  # 也会被规范化
        
        # 内部存储使用规范化后的路径
        assert "test/file.txt" in self.storage.list_paths()
