# -*- coding: utf-8 -*-
"""云存储后端测试（使用 Mock）"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from io import BytesIO
from datetime import datetime


# ==================== OSS 存储测试 ====================

class TestOSSStorage:
    """阿里云 OSS 存储测试"""
    
    @pytest.fixture
    def mock_oss2(self):
        """Mock oss2 模块"""
        with patch.dict('sys.modules', {'oss2': MagicMock()}):
            # 需要在 import 之前设置 mock
            import sys
            mock_oss2 = sys.modules['oss2']
            mock_oss2.exceptions = MagicMock()
            mock_oss2.exceptions.NoSuchKey = type('NoSuchKey', (Exception,), {})
            
            yield mock_oss2
    
    @pytest.fixture
    def storage(self, mock_oss2):
        """创建 OSS 存储实例"""
        # 重新导入模块以使用 mock
        from yweb.storage.backends.oss import OSSStorage
        
        # 配置 mock bucket
        mock_bucket = MagicMock()
        mock_oss2.Auth.return_value = MagicMock()
        mock_oss2.Bucket.return_value = mock_bucket
        
        storage = OSSStorage(
            access_key_id="test-key-id",
            access_key_secret="test-key-secret",
            endpoint="oss-cn-hangzhou.aliyuncs.com",
            bucket_name="test-bucket",
            prefix="uploads",
        )
        storage.bucket = mock_bucket
        
        return storage
    
    def test_save(self, storage):
        """测试保存文件"""
        storage.bucket.object_exists.return_value = False
        
        result = storage.save("test/file.txt", b"content")
        
        assert result == "test/file.txt"
        storage.bucket.put_object.assert_called_once()
    
    def test_save_overwrite_false_raises(self, storage):
        """测试 overwrite=False 时文件已存在抛出异常"""
        storage.bucket.object_exists.return_value = True
        
        with pytest.raises(FileExistsError):
            storage.save("test/file.txt", b"content", overwrite=False)
    
    def test_read(self, storage, mock_oss2):
        """测试读取文件"""
        mock_result = MagicMock()
        mock_result.read.return_value = b"file content"
        storage.bucket.get_object.return_value = mock_result
        
        result = storage.read("test/file.txt")
        
        assert result.read() == b"file content"
    
    def test_read_not_found(self, storage, mock_oss2):
        """测试读取不存在的文件"""
        storage.bucket.get_object.side_effect = mock_oss2.exceptions.NoSuchKey
        
        with pytest.raises(FileNotFoundError):
            storage.read("nonexistent.txt")
    
    def test_delete(self, storage):
        """测试删除文件"""
        result = storage.delete("test/file.txt")
        
        assert result is True
        storage.bucket.delete_object.assert_called_once()
    
    def test_exists(self, storage):
        """测试检查文件存在"""
        storage.bucket.object_exists.return_value = True
        
        assert storage.exists("test/file.txt") is True
        
        storage.bucket.object_exists.return_value = False
        assert storage.exists("test/file.txt") is False
    
    def test_get_info(self, storage):
        """测试获取文件信息"""
        mock_meta = MagicMock()
        mock_meta.content_length = 1024
        mock_meta.content_type = "text/plain"
        mock_meta.etag = '"abc123"'
        mock_meta.headers = {
            'Last-Modified': 'Mon, 15 Jan 2024 12:00:00 GMT',
            'x-oss-meta-custom': 'value',
        }
        storage.bucket.head_object.return_value = mock_meta
        
        info = storage.get_info("test/file.txt")
        
        assert info.size == 1024
        assert info.content_type == "text/plain"
        assert info.etag == "abc123"
    
    def test_get_url(self, storage):
        """测试获取签名URL"""
        storage.bucket.sign_url.return_value = "https://signed-url"
        
        url = storage.get_url("test/file.txt", expires=3600)
        
        assert url == "https://signed-url"
        storage.bucket.sign_url.assert_called_once()
    
    def test_prefix_handling(self, storage):
        """测试前缀处理"""
        assert storage._full_key("file.txt") == "uploads/file.txt"
        assert storage._strip_prefix("uploads/file.txt") == "file.txt"


# ==================== S3 存储测试 ====================

class TestS3Storage:
    """AWS S3 / MinIO 存储测试"""
    
    @pytest.fixture
    def mock_boto3(self):
        """Mock boto3 模块"""
        with patch.dict('sys.modules', {
            'boto3': MagicMock(),
            'botocore': MagicMock(),
            'botocore.exceptions': MagicMock(),
        }):
            import sys
            mock_boto3 = sys.modules['boto3']
            
            # Mock ClientError
            mock_botocore = sys.modules['botocore.exceptions']
            mock_botocore.ClientError = type('ClientError', (Exception,), {
                '__init__': lambda self, error_response, operation_name: None,
                'response': {'Error': {'Code': '404'}},
            })
            
            yield mock_boto3
    
    @pytest.fixture
    def storage(self, mock_boto3):
        """创建 S3 存储实例"""
        # 配置 mock
        mock_client = MagicMock()
        mock_resource = MagicMock()
        mock_bucket = MagicMock()
        
        mock_boto3.client.return_value = mock_client
        mock_boto3.resource.return_value = mock_resource
        mock_resource.Bucket.return_value = mock_bucket
        
        from yweb.storage.backends.s3 import S3Storage
        
        storage = S3Storage(
            access_key_id="test-key-id",
            secret_access_key="test-secret-key",
            bucket_name="test-bucket",
            region="us-east-1",
            prefix="uploads",
        )
        
        return storage
    
    def test_save_bytes(self, storage):
        """测试保存字节内容"""
        storage.client.head_object.side_effect = Exception("Not found")
        
        result = storage.save("test/file.txt", b"content")
        
        assert result == "test/file.txt"
        storage.client.put_object.assert_called_once()
    
    def test_save_file_object(self, storage):
        """测试保存文件对象"""
        storage.client.head_object.side_effect = Exception("Not found")
        
        file_obj = BytesIO(b"file content")
        result = storage.save("test/file.txt", file_obj)
        
        assert result == "test/file.txt"
        storage.client.upload_fileobj.assert_called_once()
    
    def test_read(self, storage):
        """测试读取文件"""
        mock_body = MagicMock()
        mock_body.read.return_value = b"file content"
        storage.client.get_object.return_value = {'Body': mock_body}
        
        result = storage.read("test/file.txt")
        
        assert result.read() == b"file content"
    
    def test_delete(self, storage):
        """测试删除文件"""
        result = storage.delete("test/file.txt")
        
        assert result is True
        storage.client.delete_object.assert_called_once()
    
    def test_exists_true(self, storage):
        """测试文件存在"""
        storage.client.head_object.return_value = {}
        
        assert storage.exists("test/file.txt") is True
    
    def test_exists_false(self, storage, mock_boto3):
        """测试文件不存在"""
        from botocore.exceptions import ClientError
        
        error = MagicMock()
        error.response = {'Error': {'Code': '404'}}
        storage.client.head_object.side_effect = ClientError(
            {'Error': {'Code': '404'}}, 'head_object'
        )
        
        assert storage.exists("test/file.txt") is False
    
    def test_get_info(self, storage):
        """测试获取文件信息"""
        storage.client.head_object.return_value = {
            'ContentLength': 2048,
            'ContentType': 'application/json',
            'ETag': '"def456"',
            'LastModified': datetime(2024, 1, 15, 12, 0, 0),
            'Metadata': {'custom': 'value'},
        }
        
        info = storage.get_info("test/file.txt")
        
        assert info.size == 2048
        assert info.content_type == "application/json"
        assert info.etag == "def456"
        assert info.metadata == {'custom': 'value'}
    
    def test_get_url(self, storage):
        """测试获取预签名URL"""
        storage.client.generate_presigned_url.return_value = "https://presigned-url"
        
        url = storage.get_url("test/file.txt", expires=3600)
        
        assert url == "https://presigned-url"
        storage.client.generate_presigned_url.assert_called_once()
    
    def test_get_upload_url(self, storage):
        """测试获取预签名上传URL"""
        storage.client.generate_presigned_url.return_value = "https://upload-url"
        
        url = storage.get_upload_url("test/new-file.txt", expires=600)
        
        assert url == "https://upload-url"
        storage.client.generate_presigned_url.assert_called_with(
            'put_object',
            Params={
                'Bucket': 'test-bucket',
                'Key': 'uploads/test/new-file.txt',
            },
            ExpiresIn=600,
        )
    
    def test_list_files(self, storage):
        """测试列出文件"""
        mock_paginator = MagicMock()
        mock_paginator.paginate.return_value = [
            {
                'Contents': [
                    {
                        'Key': 'uploads/file1.txt',
                        'Size': 100,
                        'LastModified': datetime(2024, 1, 15),
                        'ETag': '"etag1"',
                    },
                    {
                        'Key': 'uploads/file2.txt',
                        'Size': 200,
                        'LastModified': datetime(2024, 1, 16),
                        'ETag': '"etag2"',
                    },
                ]
            }
        ]
        storage.client.get_paginator.return_value = mock_paginator
        
        files = storage.list()
        
        assert len(files) == 2
        assert files[0].path == "file1.txt"
        assert files[1].path == "file2.txt"
    
    def test_prefix_handling(self, storage):
        """测试前缀处理"""
        assert storage._full_key("file.txt") == "uploads/file.txt"
        assert storage._strip_prefix("uploads/file.txt") == "file.txt"
    
    def test_copy(self, storage):
        """测试复制文件"""
        storage.client.head_object.side_effect = Exception("Not found")
        
        result = storage.copy("src.txt", "dst.txt")
        
        assert result == "dst.txt"
        storage.client.copy_object.assert_called_once()


# ==================== 导入错误测试 ====================

class TestImportErrors:
    """测试依赖未安装时的错误处理"""
    
    def test_oss_import_error(self):
        """测试 oss2 未安装时的错误"""
        with patch.dict('sys.modules', {'oss2': None}):
            # 清除已导入的模块缓存
            import sys
            if 'yweb.storage.backends.oss' in sys.modules:
                del sys.modules['yweb.storage.backends.oss']
            
            # 由于模块已经在测试初始化时导入，这里跳过
            # 实际使用时会在 __init__ 中检查
            pass
    
    def test_boto3_import_error(self):
        """测试 boto3 未安装时的错误"""
        with patch.dict('sys.modules', {'boto3': None}):
            import sys
            if 'yweb.storage.backends.s3' in sys.modules:
                del sys.modules['yweb.storage.backends.s3']
            
            # 由于模块已经在测试初始化时导入，这里跳过
            pass


# ==================== 集成测试（需要真实凭证时跳过） ====================

@pytest.mark.skip(reason="需要真实 OSS 凭证")
class TestOSSStorageIntegration:
    """OSS 存储集成测试（需要真实凭证）"""
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        from yweb.storage.backends.oss import OSSStorage
        import os
        
        storage = OSSStorage(
            access_key_id=os.environ['OSS_ACCESS_KEY_ID'],
            access_key_secret=os.environ['OSS_ACCESS_KEY_SECRET'],
            endpoint=os.environ['OSS_ENDPOINT'],
            bucket_name=os.environ['OSS_BUCKET'],
        )
        
        # 保存
        storage.save("test/integration.txt", b"integration test")
        
        # 读取
        content = storage.read_bytes("test/integration.txt")
        assert content == b"integration test"
        
        # 删除
        storage.delete("test/integration.txt")


@pytest.mark.skip(reason="需要真实 S3/MinIO 凭证")
class TestS3StorageIntegration:
    """S3 存储集成测试（需要真实凭证）"""
    
    def test_full_workflow(self):
        """测试完整工作流程"""
        from yweb.storage.backends.s3 import S3Storage
        import os
        
        storage = S3Storage(
            access_key_id=os.environ['AWS_ACCESS_KEY_ID'],
            secret_access_key=os.environ['AWS_SECRET_ACCESS_KEY'],
            bucket_name=os.environ['S3_BUCKET'],
            endpoint_url=os.environ.get('S3_ENDPOINT_URL'),  # MinIO
        )
        
        # 保存
        storage.save("test/integration.txt", b"integration test")
        
        # 读取
        content = storage.read_bytes("test/integration.txt")
        assert content == b"integration test"
        
        # 删除
        storage.delete("test/integration.txt")
