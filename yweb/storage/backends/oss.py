# -*- coding: utf-8 -*-
"""
阿里云 OSS 存储后端

将文件存储在阿里云对象存储服务中，适用于：
- 生产环境
- 大文件存储
- CDN 加速

依赖：pip install oss2
"""

import logging
import mimetypes
from datetime import datetime
from io import BytesIO
from typing import Optional, List, Union, BinaryIO
from urllib.parse import quote

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageError

logger = logging.getLogger(__name__)

# 尝试导入 oss2
try:
    import oss2
    HAS_OSS2 = True
except ImportError:
    HAS_OSS2 = False
    oss2 = None


class OSSStorage(StorageBackend):
    """阿里云 OSS 存储后端
    
    Args:
        access_key_id: 阿里云 Access Key ID
        access_key_secret: 阿里云 Access Key Secret
        endpoint: OSS 端点，如 'oss-cn-hangzhou.aliyuncs.com'
        bucket_name: Bucket 名称
        prefix: 存储前缀（可选）
        internal_endpoint: 内网端点（可选，用于服务器间传输）
        connect_timeout: 连接超时时间（秒）
    
    Example:
        storage = OSSStorage(
            access_key_id="your-key-id",
            access_key_secret="your-key-secret",
            endpoint="oss-cn-hangzhou.aliyuncs.com",
            bucket_name="your-bucket",
            prefix="uploads/",
        )
        
        # 保存文件
        storage.save("images/avatar.jpg", file_content)
        
        # 获取签名URL（1小时有效）
        url = storage.get_url("images/avatar.jpg", expires=3600)
        
        # 获取预签名上传URL（客户端直传）
        upload_url = storage.get_upload_url("images/new.jpg")
    
    Note:
        需要安装 oss2: pip install oss2
    """
    
    def __init__(
        self,
        access_key_id: str,
        access_key_secret: str,
        endpoint: str,
        bucket_name: str,
        prefix: str = "",
        internal_endpoint: Optional[str] = None,
        connect_timeout: int = 30,
    ):
        if not HAS_OSS2:
            raise ImportError(
                "使用 OSSStorage 需要安装 oss2: pip install oss2"
            )
        
        self.prefix = prefix.strip('/') if prefix else ""
        self.endpoint = endpoint
        self.bucket_name = bucket_name
        
        # 创建认证
        auth = oss2.Auth(access_key_id, access_key_secret)
        
        # 创建 Bucket 实例
        self.bucket = oss2.Bucket(
            auth,
            endpoint,
            bucket_name,
            connect_timeout=connect_timeout,
        )
        
        # 内网 Bucket（用于服务器间传输）
        if internal_endpoint:
            self.internal_bucket = oss2.Bucket(
                auth,
                internal_endpoint,
                bucket_name,
                connect_timeout=connect_timeout,
            )
        else:
            self.internal_bucket = None
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件到 OSS
        
        Args:
            path: 存储路径
            content: 文件内容
            content_type: MIME类型，不指定则自动检测
            metadata: 自定义元数据（会添加 x-oss-meta- 前缀）
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 存储路径
            
        Raises:
            FileExistsError: overwrite=False 且文件已存在
            StorageError: 上传失败
        """
        key = self._full_key(path)
        
        # 检查是否已存在
        if not overwrite and self.exists(path):
            raise FileExistsError(f"文件已存在: {path}")
        
        # 自动检测内容类型
        if not content_type:
            content_type, _ = mimetypes.guess_type(path)
        
        # 准备 headers
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        if metadata:
            for k, v in metadata.items():
                headers[f'x-oss-meta-{k}'] = str(v)
        
        try:
            # 上传
            if isinstance(content, bytes):
                self.bucket.put_object(key, content, headers=headers or None)
            else:
                self.bucket.put_object(key, content, headers=headers or None)
            
            return self._normalize_path(path)
        
        except Exception as e:
            logger.error(f"OSS 上传失败: {path}, 错误: {e}")
            raise StorageError(f"上传文件失败: {e}")
    
    def read(self, path: str) -> BinaryIO:
        """读取文件
        
        Args:
            path: 文件路径
            
        Returns:
            BinaryIO: 文件对象（BytesIO）
            
        Raises:
            FileNotFoundError: 文件不存在
            StorageError: 读取失败
        """
        key = self._full_key(path)
        
        try:
            result = self.bucket.get_object(key)
            return BytesIO(result.read())
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"文件不存在: {path}")
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise FileNotFoundError(f"文件不存在: {path}")
            logger.error(f"OSS 读取失败: {path}, 错误: {e}")
            raise StorageError(f"读取文件失败: {e}")
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件内容为字节
        
        Args:
            path: 文件路径
            
        Returns:
            bytes: 文件内容
        """
        key = self._full_key(path)
        
        try:
            result = self.bucket.get_object(key)
            return result.read()
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"文件不存在: {path}")
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise FileNotFoundError(f"文件不存在: {path}")
            logger.error(f"OSS 读取失败: {path}, 错误: {e}")
            raise StorageError(f"读取文件失败: {e}")
    
    def delete(self, path: str) -> bool:
        """删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 是否删除成功
        """
        key = self._full_key(path)
        
        try:
            self.bucket.delete_object(key)
            return True
        except Exception as e:
            logger.warning(f"OSS 删除失败: {path}, 错误: {e}")
            return False
    
    def exists(self, path: str) -> bool:
        """检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 文件是否存在
        """
        key = self._full_key(path)
        return self.bucket.object_exists(key)
    
    def get_info(self, path: str) -> FileInfo:
        """获取文件信息
        
        Args:
            path: 文件路径
            
        Returns:
            FileInfo: 文件元信息
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        key = self._full_key(path)
        
        try:
            meta = self.bucket.head_object(key)
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"文件不存在: {path}")
        except Exception as e:
            if 'NoSuchKey' in str(e):
                raise FileNotFoundError(f"文件不存在: {path}")
            raise StorageError(f"获取文件信息失败: {e}")
        
        # 解析自定义元数据
        metadata = {}
        for k, v in meta.headers.items():
            k_lower = k.lower()
            if k_lower.startswith('x-oss-meta-'):
                metadata[k_lower[11:]] = v
        
        # 解析修改时间
        modified_at = None
        last_modified = meta.headers.get('Last-Modified')
        if last_modified:
            try:
                modified_at = datetime.strptime(
                    last_modified,
                    '%a, %d %b %Y %H:%M:%S GMT'
                )
            except ValueError:
                pass
        
        # 清理 ETag
        etag = meta.etag
        if etag:
            etag = etag.strip('"')
        
        return FileInfo(
            path=self._normalize_path(path),
            size=meta.content_length,
            created_at=None,  # OSS 不提供创建时间
            modified_at=modified_at,
            content_type=meta.content_type,
            etag=etag,
            metadata=metadata,
        )
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """列出文件
        
        Args:
            prefix: 路径前缀
            recursive: 是否递归列出子目录
            limit: 最大返回数量
            
        Returns:
            List[FileInfo]: 文件信息列表
        """
        full_prefix = self._full_key(prefix) if prefix else self.prefix
        if full_prefix:
            full_prefix = full_prefix.rstrip('/') + '/'
        
        # 非递归时使用分隔符
        delimiter = '' if recursive else '/'
        
        results = []
        
        for obj in oss2.ObjectIterator(
            self.bucket,
            prefix=full_prefix,
            delimiter=delimiter,
        ):
            # 跳过目录（前缀）
            if obj.is_prefix():
                continue
            
            # 解析修改时间
            modified_at = None
            if obj.last_modified:
                try:
                    modified_at = datetime.fromtimestamp(obj.last_modified)
                except (ValueError, TypeError):
                    pass
            
            # 清理 ETag
            etag = obj.etag
            if etag:
                etag = etag.strip('"')
            
            results.append(FileInfo(
                path=self._strip_prefix(obj.key),
                size=obj.size,
                modified_at=modified_at,
                etag=etag,
            ))
            
            if limit and len(results) >= limit:
                break
        
        return results
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
        internal: bool = False,
    ) -> str:
        """获取签名URL
        
        Args:
            path: 文件路径
            expires: 过期时间（秒）
            download: 是否强制下载
            filename: 下载时的文件名
            internal: 是否使用内网地址
            
        Returns:
            str: 签名URL
        """
        key = self._full_key(path)
        bucket = self.internal_bucket if internal and self.internal_bucket else self.bucket
        
        params = {}
        if download:
            disposition = 'attachment'
            if filename:
                # URL 编码文件名（支持中文）
                disposition += f"; filename*=UTF-8''{quote(filename)}"
            params['response-content-disposition'] = disposition
        
        return bucket.sign_url('GET', key, expires, params=params or None)
    
    # ==================== OSS 特有方法 ====================
    
    def get_upload_url(
        self,
        path: str,
        expires: int = 3600,
        content_type: Optional[str] = None,
    ) -> str:
        """获取预签名上传URL（用于客户端直传）
        
        Args:
            path: 目标路径
            expires: 过期时间（秒）
            content_type: 内容类型限制
            
        Returns:
            str: 预签名上传URL
        """
        key = self._full_key(path)
        
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        
        return self.bucket.sign_url(
            'PUT',
            key,
            expires,
            headers=headers or None,
        )
    
    def copy(self, src: str, dst: str, overwrite: bool = True) -> str:
        """复制文件（OSS 内部复制）
        
        Args:
            src: 源文件路径
            dst: 目标文件路径
            overwrite: 是否覆盖
            
        Returns:
            str: 目标文件路径
        """
        src_key = self._full_key(src)
        dst_key = self._full_key(dst)
        
        if not overwrite and self.exists(dst):
            raise FileExistsError(f"目标文件已存在: {dst}")
        
        try:
            self.bucket.copy_object(self.bucket_name, src_key, dst_key)
            return self._normalize_path(dst)
        except oss2.exceptions.NoSuchKey:
            raise FileNotFoundError(f"源文件不存在: {src}")
        except Exception as e:
            raise StorageError(f"复制文件失败: {e}")
    
    def get_bucket_info(self) -> dict:
        """获取 Bucket 信息
        
        Returns:
            dict: Bucket 信息
        """
        try:
            info = self.bucket.get_bucket_info()
            return {
                'name': info.name,
                'location': info.location,
                'creation_date': info.creation_date,
                'storage_class': info.storage_class,
            }
        except Exception as e:
            raise StorageError(f"获取 Bucket 信息失败: {e}")
    
    # ==================== 私有方法 ====================
    
    def _full_key(self, path: str) -> str:
        """构建完整的 OSS key"""
        path = self._normalize_path(path)
        if self.prefix:
            return f"{self.prefix}/{path}"
        return path
    
    def _strip_prefix(self, key: str) -> str:
        """从 key 中移除前缀"""
        if self.prefix and key.startswith(self.prefix + '/'):
            return key[len(self.prefix) + 1:]
        return key
    
    def _normalize_path(self, path: str) -> str:
        """规范化路径"""
        return path.lstrip('/')


__all__ = ['OSSStorage']
