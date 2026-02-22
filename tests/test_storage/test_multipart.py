# -*- coding: utf-8 -*-
"""分片上传测试"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from io import BytesIO

from yweb.storage.multipart import (
    UploadPart,
    MultipartUpload,
    MemoryMultipartStore,
    MultipartUploadMixin,
)
from yweb.storage import LocalStorage
from yweb.storage.exceptions import (
    UploadNotFound,
    UploadExpired,
    PartNumberInvalid,
    PartVerificationFailed,
    MultipartUploadError,
)


# ==================== 数据类测试 ====================

class TestUploadPart:
    """UploadPart 数据类测试"""
    
    def test_create_upload_part(self):
        """测试创建分片"""
        part = UploadPart(
            part_number=1,
            etag="abc123",
            size=1024,
        )
        
        assert part.part_number == 1
        assert part.etag == "abc123"
        assert part.size == 1024
        assert isinstance(part.uploaded_at, datetime)
    
    def test_to_dict(self):
        """测试转换为字典"""
        part = UploadPart(part_number=1, etag="abc", size=100)
        data = part.to_dict()
        
        assert data['part_number'] == 1
        assert data['etag'] == "abc"
        assert data['size'] == 100
        assert 'uploaded_at' in data


class TestMultipartUpload:
    """MultipartUpload 数据类测试"""
    
    def test_create_upload(self):
        """测试创建上传任务"""
        upload = MultipartUpload(
            upload_id="test-id",
            path="test/file.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )
        
        assert upload.upload_id == "test-id"
        assert upload.path == "test/file.txt"
        assert upload.total_size == 0
        assert upload.part_count == 0
    
    def test_total_size(self):
        """测试总大小计算"""
        upload = MultipartUpload(
            upload_id="test-id",
            path="test/file.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
            parts=[
                UploadPart(part_number=1, etag="a", size=100),
                UploadPart(part_number=2, etag="b", size=200),
            ],
        )
        
        assert upload.total_size == 300
        assert upload.part_count == 2
    
    def test_is_expired(self):
        """测试过期检查"""
        # 未过期
        upload = MultipartUpload(
            upload_id="test-id",
            path="test/file.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
        )
        assert upload.is_expired() is False
        
        # 已过期
        upload_expired = MultipartUpload(
            upload_id="test-id",
            path="test/file.txt",
            created_at=datetime.now() - timedelta(hours=48),
            expires_at=datetime.now() - timedelta(hours=24),
        )
        assert upload_expired.is_expired() is True
    
    def test_to_dict(self):
        """测试转换为字典"""
        upload = MultipartUpload(
            upload_id="test-id",
            path="test/file.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=24),
            content_type="text/plain",
        )
        data = upload.to_dict()
        
        assert data['upload_id'] == "test-id"
        assert data['path'] == "test/file.txt"
        assert data['content_type'] == "text/plain"


# ==================== 内存存储测试 ====================

class TestMemoryMultipartStore:
    """内存分片存储测试"""
    
    @pytest.fixture
    def store(self):
        return MemoryMultipartStore()
    
    def test_save_and_get(self, store):
        """测试保存和获取"""
        upload = MultipartUpload(
            upload_id="test-id",
            path="test.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        store.save(upload)
        result = store.get("test-id")
        
        assert result is not None
        assert result.upload_id == "test-id"
    
    def test_get_nonexistent(self, store):
        """测试获取不存在的任务"""
        result = store.get("nonexistent")
        assert result is None
    
    def test_delete(self, store):
        """测试删除"""
        upload = MultipartUpload(
            upload_id="test-id",
            path="test.txt",
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(hours=1),
        )
        store.save(upload)
        
        store.delete("test-id")
        
        assert store.get("test-id") is None
    
    def test_list_all(self, store):
        """测试列出所有"""
        for i in range(3):
            store.save(MultipartUpload(
                upload_id=f"id-{i}",
                path=f"test{i}.txt",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1),
            ))
        
        uploads = store.list_all()
        assert len(uploads) == 3
    
    def test_clear(self, store):
        """测试清空"""
        for i in range(3):
            store.save(MultipartUpload(
                upload_id=f"id-{i}",
                path=f"test{i}.txt",
                created_at=datetime.now(),
                expires_at=datetime.now() + timedelta(hours=1),
            ))
        
        store.clear()
        
        assert len(store.list_all()) == 0


# ==================== Mixin 测试 ====================

class MultipartLocalStorage(MultipartUploadMixin, LocalStorage):
    """用于测试的分片上传存储类"""
    pass


class TestMultipartUploadMixin:
    """分片上传 Mixin 测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def storage(self, temp_dir):
        """创建存储实例"""
        return MultipartLocalStorage(temp_dir)
    
    def test_init_multipart_upload(self, storage):
        """测试初始化上传"""
        upload_id = storage.init_multipart_upload(
            path="test/large-file.zip",
            content_type="application/zip",
        )
        
        assert upload_id is not None
        assert len(upload_id) == 36  # UUID 长度
    
    def test_upload_part(self, storage):
        """测试上传分片"""
        upload_id = storage.init_multipart_upload("test/file.zip")
        
        part = storage.upload_part(upload_id, 1, b"part1 content")
        
        assert part.part_number == 1
        assert part.size == 13
        assert part.etag is not None
    
    def test_upload_multiple_parts(self, storage):
        """测试上传多个分片"""
        upload_id = storage.init_multipart_upload("test/file.zip")
        
        storage.upload_part(upload_id, 1, b"part1")
        storage.upload_part(upload_id, 2, b"part2")
        storage.upload_part(upload_id, 3, b"part3")
        
        parts = storage.list_parts(upload_id)
        
        assert len(parts) == 3
        assert parts[0].part_number == 1
        assert parts[1].part_number == 2
        assert parts[2].part_number == 3
    
    def test_upload_part_reupload(self, storage):
        """测试重新上传同一分片"""
        upload_id = storage.init_multipart_upload("test/file.zip")
        
        # 第一次上传
        part1 = storage.upload_part(upload_id, 1, b"original")
        
        # 重新上传
        part2 = storage.upload_part(upload_id, 1, b"updated content")
        
        # 应该只有一个分片记录，且是最新的
        parts = storage.list_parts(upload_id)
        assert len(parts) == 1
        assert parts[0].etag == part2.etag
    
    def test_complete_multipart_upload(self, storage):
        """测试完成上传"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        storage.upload_part(upload_id, 1, b"Hello ")
        storage.upload_part(upload_id, 2, b"World!")
        
        path = storage.complete_multipart_upload(upload_id)
        
        # 验证最终文件
        assert storage.exists("test/file.txt")
        content = storage.read_bytes("test/file.txt")
        assert content == b"Hello World!"
    
    def test_complete_with_verification(self, storage):
        """测试带验证的完成上传"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        part1 = storage.upload_part(upload_id, 1, b"Part1")
        part2 = storage.upload_part(upload_id, 2, b"Part2")
        
        # 提供正确的分片信息
        parts = [
            {'part_number': 1, 'etag': part1.etag},
            {'part_number': 2, 'etag': part2.etag},
        ]
        
        path = storage.complete_multipart_upload(upload_id, parts=parts)
        
        assert storage.exists("test/file.txt")
    
    def test_complete_verification_failed(self, storage):
        """测试验证失败"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        storage.upload_part(upload_id, 1, b"Part1")
        
        # 提供错误的 etag
        parts = [
            {'part_number': 1, 'etag': 'wrong-etag'},
        ]
        
        with pytest.raises(PartVerificationFailed):
            storage.complete_multipart_upload(upload_id, parts=parts)
    
    def test_complete_no_parts_error(self, storage):
        """测试没有分片时完成上传报错"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        with pytest.raises(MultipartUploadError):
            storage.complete_multipart_upload(upload_id)
    
    def test_abort_multipart_upload(self, storage):
        """测试取消上传"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        storage.upload_part(upload_id, 1, b"Part1")
        
        result = storage.abort_multipart_upload(upload_id)
        
        assert result is True
        
        # 上传任务应该不存在了
        with pytest.raises(UploadNotFound):
            storage.list_parts(upload_id)
    
    def test_list_parts(self, storage):
        """测试列出分片"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        storage.upload_part(upload_id, 2, b"Part2")
        storage.upload_part(upload_id, 1, b"Part1")
        storage.upload_part(upload_id, 3, b"Part3")
        
        parts = storage.list_parts(upload_id)
        
        # 应该按序号排序
        assert len(parts) == 3
        assert parts[0].part_number == 1
        assert parts[1].part_number == 2
        assert parts[2].part_number == 3
    
    def test_get_upload_info(self, storage):
        """测试获取上传任务信息"""
        upload_id = storage.init_multipart_upload(
            path="test/file.txt",
            content_type="text/plain",
            metadata={'key': 'value'},
        )
        
        storage.upload_part(upload_id, 1, b"Part1")
        
        info = storage.get_upload_info(upload_id)
        
        assert info.upload_id == upload_id
        assert info.path == "test/file.txt"
        assert info.content_type == "text/plain"
        assert info.metadata == {'key': 'value'}
        assert info.part_count == 1
    
    def test_list_uploads(self, storage):
        """测试列出所有上传任务"""
        storage.init_multipart_upload("path1/file1.txt")
        storage.init_multipart_upload("path1/file2.txt")
        storage.init_multipart_upload("path2/file3.txt")
        
        # 列出所有
        all_uploads = storage.list_uploads()
        assert len(all_uploads) == 3
        
        # 按前缀过滤
        filtered = storage.list_uploads("path1/")
        assert len(filtered) == 2
    
    def test_upload_not_found(self, storage):
        """测试上传任务不存在"""
        with pytest.raises(UploadNotFound):
            storage.upload_part("nonexistent-id", 1, b"content")
    
    def test_part_number_invalid(self, storage):
        """测试分片序号无效"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        with pytest.raises(PartNumberInvalid):
            storage.upload_part(upload_id, 0, b"content")  # 序号太小
        
        with pytest.raises(PartNumberInvalid):
            storage.upload_part(upload_id, 10001, b"content")  # 序号太大


class TestMultipartUploadExpiry:
    """分片上传过期测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def storage(self, temp_dir):
        return MultipartLocalStorage(temp_dir, multipart_expires=1)  # 1秒过期
    
    def test_upload_expired(self, storage):
        """测试上传任务过期"""
        import time
        
        upload_id = storage.init_multipart_upload("test/file.txt", expires_in=1)
        
        # 等待过期
        time.sleep(1.5)
        
        with pytest.raises(UploadExpired):
            storage.upload_part(upload_id, 1, b"content")
    
    def test_cleanup_expired(self, storage):
        """测试清理过期任务"""
        import time
        
        # 创建一个立即过期的任务
        storage.init_multipart_upload("test/file.txt", expires_in=1)
        
        time.sleep(1.5)
        
        # 清理过期任务
        count = storage.cleanup_expired_uploads()
        
        assert count == 1


class TestMultipartUploadLargeFile:
    """大文件分片上传测试"""
    
    @pytest.fixture
    def temp_dir(self):
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    def storage(self, temp_dir):
        return MultipartLocalStorage(temp_dir)
    
    def test_large_file_upload(self, storage):
        """测试大文件分片上传"""
        upload_id = storage.init_multipart_upload("test/large-file.bin")
        
        # 模拟大文件分片（每片 1KB）
        chunk_size = 1024
        total_parts = 10
        
        for i in range(1, total_parts + 1):
            chunk = bytes([i % 256] * chunk_size)
            storage.upload_part(upload_id, i, chunk)
        
        # 完成上传
        path = storage.complete_multipart_upload(upload_id)
        
        # 验证文件大小
        info = storage.get_info(path)
        assert info.size == chunk_size * total_parts
    
    def test_out_of_order_parts(self, storage):
        """测试乱序上传分片"""
        upload_id = storage.init_multipart_upload("test/file.txt")
        
        # 乱序上传
        storage.upload_part(upload_id, 3, b"CCC")
        storage.upload_part(upload_id, 1, b"AAA")
        storage.upload_part(upload_id, 2, b"BBB")
        
        # 完成上传
        path = storage.complete_multipart_upload(upload_id)
        
        # 验证内容按序号合并
        content = storage.read_bytes(path)
        assert content == b"AAABBBCCC"
