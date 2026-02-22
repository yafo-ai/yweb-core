# -*- coding: utf-8 -*-
"""
AWS S3 / MinIO 存储后端

将文件存储在 AWS S3 或兼容服务（如 MinIO）中，适用于：
- 生产环境
- 大文件存储
- 多云部署

依赖：pip install boto3
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

# 尝试导入 boto3
try:
    import boto3
    from botocore.exceptions import ClientError
    HAS_BOTO3 = True
except ImportError:
    HAS_BOTO3 = False
    boto3 = None
    ClientError = Exception


class S3Storage(StorageBackend):
    """AWS S3 / MinIO 存储后端
    
    Args:
        access_key_id: AWS Access Key ID
        secret_access_key: AWS Secret Access Key
        bucket_name: Bucket 名称
        region: AWS 区域，默认 'us-east-1'
        endpoint_url: 自定义端点（MinIO 等）
        prefix: 存储前缀（可选）
    
    Example:
        # AWS S3
        storage = S3Storage(
            access_key_id="your-key-id",
            secret_access_key="your-secret-key",
            bucket_name="your-bucket",
            region="us-west-2",
        )
        
        # MinIO
        storage = S3Storage(
            access_key_id="minioadmin",
            secret_access_key="minioadmin",
            bucket_name="mybucket",
            endpoint_url="http://localhost:9000",
        )
        
        # 保存文件
        storage.save("images/avatar.jpg", file_content)
        
        # 获取签名URL
        url = storage.get_url("images/avatar.jpg", expires=3600)
    
    Note:
        需要安装 boto3: pip install boto3
    """
    
    def __init__(
        self,
        access_key_id: str,
        secret_access_key: str,
        bucket_name: str,
        region: str = 'us-east-1',
        endpoint_url: Optional[str] = None,
        prefix: str = "",
    ):
        if not HAS_BOTO3:
            raise ImportError(
                "使用 S3Storage 需要安装 boto3: pip install boto3"
            )
        
        self.bucket_name = bucket_name
        self.region = region
        self.prefix = prefix.strip('/') if prefix else ""
        self.endpoint_url = endpoint_url
        
        # 创建 S3 客户端
        self.client = boto3.client(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url,
        )
        
        # 创建 S3 资源（用于某些操作）
        self.resource = boto3.resource(
            's3',
            aws_access_key_id=access_key_id,
            aws_secret_access_key=secret_access_key,
            region_name=region,
            endpoint_url=endpoint_url,
        )
        
        self.bucket = self.resource.Bucket(bucket_name)
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件到 S3
        
        Args:
            path: 存储路径
            content: 文件内容
            content_type: MIME类型，不指定则自动检测
            metadata: 自定义元数据
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
        
        # 准备上传参数
        extra_args = {}
        if content_type:
            extra_args['ContentType'] = content_type
        if metadata:
            extra_args['Metadata'] = {k: str(v) for k, v in metadata.items()}
        
        try:
            # 上传
            if isinstance(content, bytes):
                self.client.put_object(
                    Bucket=self.bucket_name,
                    Key=key,
                    Body=content,
                    **extra_args,
                )
            else:
                # 文件对象
                self.client.upload_fileobj(
                    content,
                    self.bucket_name,
                    key,
                    ExtraArgs=extra_args or None,
                )
            
            return self._normalize_path(path)
        
        except Exception as e:
            logger.error(f"S3 上传失败: {path}, 错误: {e}")
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
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return BytesIO(response['Body'].read())
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"文件不存在: {path}")
            logger.error(f"S3 读取失败: {path}, 错误: {e}")
            raise StorageError(f"读取文件失败: {e}")
        except Exception as e:
            logger.error(f"S3 读取失败: {path}, 错误: {e}")
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
            response = self.client.get_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return response['Body'].read()
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"文件不存在: {path}")
            logger.error(f"S3 读取失败: {path}, 错误: {e}")
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
            self.client.delete_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return True
        except Exception as e:
            logger.warning(f"S3 删除失败: {path}, 错误: {e}")
            return False
    
    def exists(self, path: str) -> bool:
        """检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 文件是否存在
        """
        key = self._full_key(path)
        
        try:
            self.client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
            return True
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('404', 'NoSuchKey'):
                return False
            # 其他错误也返回 False
            return False
        except Exception:
            return False
    
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
            response = self.client.head_object(
                Bucket=self.bucket_name,
                Key=key,
            )
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"文件不存在: {path}")
            raise StorageError(f"获取文件信息失败: {e}")
        
        # 解析自定义元数据
        metadata = response.get('Metadata', {})
        
        # 获取修改时间
        modified_at = response.get('LastModified')
        
        # 清理 ETag
        etag = response.get('ETag', '')
        if etag:
            etag = etag.strip('"')
        
        return FileInfo(
            path=self._normalize_path(path),
            size=response.get('ContentLength', 0),
            created_at=None,  # S3 不提供创建时间
            modified_at=modified_at,
            content_type=response.get('ContentType'),
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
        
        results = []
        
        # 准备分页参数
        paginator = self.client.get_paginator('list_objects_v2')
        
        page_config = {
            'Bucket': self.bucket_name,
            'Prefix': full_prefix,
        }
        
        if not recursive:
            page_config['Delimiter'] = '/'
        
        for page in paginator.paginate(**page_config):
            for obj in page.get('Contents', []):
                key = obj['Key']
                
                # 跳过目录占位符
                if key.endswith('/'):
                    continue
                
                # 解析修改时间
                modified_at = obj.get('LastModified')
                
                # 清理 ETag
                etag = obj.get('ETag', '')
                if etag:
                    etag = etag.strip('"')
                
                results.append(FileInfo(
                    path=self._strip_prefix(key),
                    size=obj.get('Size', 0),
                    modified_at=modified_at,
                    etag=etag,
                ))
                
                if limit and len(results) >= limit:
                    return results
        
        return results
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
    ) -> str:
        """获取预签名URL
        
        Args:
            path: 文件路径
            expires: 过期时间（秒）
            download: 是否强制下载
            filename: 下载时的文件名
            
        Returns:
            str: 预签名URL
        """
        key = self._full_key(path)
        
        params = {
            'Bucket': self.bucket_name,
            'Key': key,
        }
        
        if download:
            disposition = 'attachment'
            if filename:
                # URL 编码文件名（支持中文）
                disposition += f"; filename*=UTF-8''{quote(filename)}"
            params['ResponseContentDisposition'] = disposition
        
        return self.client.generate_presigned_url(
            'get_object',
            Params=params,
            ExpiresIn=expires,
        )
    
    # ==================== S3 特有方法 ====================
    
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
        
        params = {
            'Bucket': self.bucket_name,
            'Key': key,
        }
        
        if content_type:
            params['ContentType'] = content_type
        
        return self.client.generate_presigned_url(
            'put_object',
            Params=params,
            ExpiresIn=expires,
        )
    
    def copy(self, src: str, dst: str, overwrite: bool = True) -> str:
        """复制文件（S3 内部复制）
        
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
            copy_source = {
                'Bucket': self.bucket_name,
                'Key': src_key,
            }
            self.client.copy_object(
                Bucket=self.bucket_name,
                Key=dst_key,
                CopySource=copy_source,
            )
            return self._normalize_path(dst)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', '')
            if error_code in ('NoSuchKey', '404'):
                raise FileNotFoundError(f"源文件不存在: {src}")
            raise StorageError(f"复制文件失败: {e}")
    
    def get_bucket_info(self) -> dict:
        """获取 Bucket 信息
        
        Returns:
            dict: Bucket 信息
        """
        try:
            location = self.client.get_bucket_location(
                Bucket=self.bucket_name,
            )
            
            return {
                'name': self.bucket_name,
                'location': location.get('LocationConstraint') or 'us-east-1',
                'endpoint_url': self.endpoint_url,
            }
        except Exception as e:
            raise StorageError(f"获取 Bucket 信息失败: {e}")
    
    # ==================== 私有方法 ====================
    
    def _full_key(self, path: str) -> str:
        """构建完整的 S3 key"""
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


__all__ = ['S3Storage']
