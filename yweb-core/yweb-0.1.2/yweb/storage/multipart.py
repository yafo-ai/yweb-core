# -*- coding: utf-8 -*-
"""
分片上传模块

提供大文件分片上传功能：
- 初始化上传任务
- 上传分片
- 完成/取消上传
- 分片列表查询

使用示例:
    class MultipartStorage(MultipartUploadMixin, LocalStorage):
        pass
    
    storage = MultipartStorage('/data/uploads')
    
    # 初始化上传
    upload_id = storage.init_multipart_upload('large-file.zip')
    
    # 上传分片
    storage.upload_part(upload_id, 1, chunk1)
    storage.upload_part(upload_id, 2, chunk2)
    
    # 完成上传
    path = storage.complete_multipart_upload(upload_id)
"""

import hashlib
import logging
import uuid
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any, Union

from .exceptions import (
    MultipartUploadError,
    UploadNotFound,
    UploadExpired,
    PartNumberInvalid,
    PartVerificationFailed,
)

logger = logging.getLogger(__name__)


@dataclass
class UploadPart:
    """上传分片
    
    Attributes:
        part_number: 分片序号（1-10000）
        etag: 分片内容的 MD5 哈希
        size: 分片大小（字节）
        uploaded_at: 上传时间
    """
    part_number: int
    etag: str
    size: int
    uploaded_at: datetime = field(default_factory=datetime.now)
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'part_number': self.part_number,
            'etag': self.etag,
            'size': self.size,
            'uploaded_at': self.uploaded_at.isoformat(),
        }


@dataclass
class MultipartUpload:
    """分片上传任务
    
    Attributes:
        upload_id: 上传任务ID
        path: 目标文件路径
        content_type: MIME类型
        metadata: 自定义元数据
        created_at: 创建时间
        expires_at: 过期时间
        parts: 已上传的分片列表
    """
    upload_id: str
    path: str
    created_at: datetime
    expires_at: datetime
    content_type: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    parts: List[UploadPart] = field(default_factory=list)
    
    @property
    def total_size(self) -> int:
        """已上传的总大小"""
        return sum(p.size for p in self.parts)
    
    @property
    def part_count(self) -> int:
        """已上传的分片数"""
        return len(self.parts)
    
    def is_expired(self) -> bool:
        """是否已过期"""
        return datetime.now() > self.expires_at
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'upload_id': self.upload_id,
            'path': self.path,
            'content_type': self.content_type,
            'metadata': self.metadata,
            'created_at': self.created_at.isoformat(),
            'expires_at': self.expires_at.isoformat(),
            'parts': [p.to_dict() for p in self.parts],
            'total_size': self.total_size,
            'part_count': self.part_count,
        }


class MultipartUploadStore:
    """分片上传存储接口
    
    管理分片上传任务的元数据。
    默认使用内存存储，生产环境建议使用 Redis。
    """
    
    def save(self, upload: MultipartUpload) -> None:
        """保存上传任务"""
        raise NotImplementedError
    
    def get(self, upload_id: str) -> Optional[MultipartUpload]:
        """获取上传任务"""
        raise NotImplementedError
    
    def delete(self, upload_id: str) -> None:
        """删除上传任务"""
        raise NotImplementedError
    
    def list_all(self) -> List[MultipartUpload]:
        """列出所有上传任务"""
        raise NotImplementedError


class MemoryMultipartStore(MultipartUploadStore):
    """内存分片上传存储
    
    适用于开发和测试环境。
    
    Note:
        - 重启后数据丢失
        - 不适合多进程/多实例部署
    """
    
    def __init__(self):
        self._store: Dict[str, MultipartUpload] = {}
        self._lock = threading.RLock()
    
    def save(self, upload: MultipartUpload) -> None:
        with self._lock:
            self._store[upload.upload_id] = upload
    
    def get(self, upload_id: str) -> Optional[MultipartUpload]:
        with self._lock:
            return self._store.get(upload_id)
    
    def delete(self, upload_id: str) -> None:
        with self._lock:
            self._store.pop(upload_id, None)
    
    def list_all(self) -> List[MultipartUpload]:
        with self._lock:
            return list(self._store.values())
    
    def clear(self) -> None:
        """清空所有任务（仅用于测试）"""
        with self._lock:
            self._store.clear()


class MultipartUploadMixin:
    """分片上传Mixin
    
    为存储后端添加分片上传能力。
    
    Example:
        class MultipartLocalStorage(MultipartUploadMixin, LocalStorage):
            pass
        
        storage = MultipartLocalStorage('/data/uploads')
        
        # 初始化上传
        upload_id = storage.init_multipart_upload('large-file.zip')
        
        # 上传分片（每个分片建议 5-100MB）
        for i, chunk in enumerate(chunks, 1):
            storage.upload_part(upload_id, i, chunk)
        
        # 完成上传
        path = storage.complete_multipart_upload(upload_id)
    """
    
    # 分片大小限制
    MIN_PART_SIZE = 5 * 1024 * 1024      # 5MB（最后一个分片可以更小）
    MAX_PART_SIZE = 5 * 1024 * 1024 * 1024  # 5GB
    MAX_PARTS = 10000
    
    def __init__(
        self,
        *args,
        multipart_store: Optional[MultipartUploadStore] = None,
        multipart_expires: int = 86400,  # 默认 24 小时
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._multipart_store = multipart_store or MemoryMultipartStore()
        self._multipart_expires = multipart_expires
    
    def init_multipart_upload(
        self,
        path: str,
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        expires_in: Optional[int] = None,
    ) -> str:
        """初始化分片上传
        
        Args:
            path: 目标文件路径
            content_type: MIME类型
            metadata: 自定义元数据
            expires_in: 上传任务过期时间（秒），默认 24 小时
            
        Returns:
            str: 上传任务ID
        """
        upload_id = str(uuid.uuid4())
        expires = expires_in or self._multipart_expires
        
        upload = MultipartUpload(
            upload_id=upload_id,
            path=path,
            content_type=content_type,
            metadata=metadata or {},
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=expires),
            parts=[],
        )
        
        self._multipart_store.save(upload)
        
        logger.info(f"初始化分片上传: upload_id={upload_id}, path={path}")
        return upload_id
    
    def upload_part(
        self,
        upload_id: str,
        part_number: int,
        content: bytes,
    ) -> UploadPart:
        """上传分片
        
        Args:
            upload_id: 上传任务ID
            part_number: 分片序号（1-10000）
            content: 分片内容
            
        Returns:
            UploadPart: 分片信息
            
        Raises:
            UploadNotFound: 上传任务不存在
            UploadExpired: 上传任务已过期
            PartNumberInvalid: 分片序号无效
        """
        upload = self._get_upload(upload_id)
        
        # 验证分片序号
        if not 1 <= part_number <= self.MAX_PARTS:
            raise PartNumberInvalid(part_number)
        
        # 计算 ETag（MD5）
        etag = hashlib.md5(content).hexdigest()
        
        # 存储分片到临时位置
        part_path = self._get_part_path(upload_id, part_number)
        super().save(part_path, content)
        
        # 创建分片记录
        part = UploadPart(
            part_number=part_number,
            etag=etag,
            size=len(content),
            uploaded_at=datetime.now(),
        )
        
        # 更新或添加分片记录（允许重新上传同一分片）
        upload.parts = [p for p in upload.parts if p.part_number != part_number]
        upload.parts.append(part)
        upload.parts.sort(key=lambda p: p.part_number)
        
        # 保存更新
        self._multipart_store.save(upload)
        
        logger.debug(f"上传分片: upload_id={upload_id}, part={part_number}, size={len(content)}")
        return part
    
    def complete_multipart_upload(
        self,
        upload_id: str,
        parts: Optional[List[dict]] = None,
    ) -> str:
        """完成分片上传
        
        将所有分片合并为最终文件。
        
        Args:
            upload_id: 上传任务ID
            parts: 分片列表用于验证，格式 [{'part_number': 1, 'etag': '...'}, ...]
            
        Returns:
            str: 最终文件路径
            
        Raises:
            UploadNotFound: 上传任务不存在
            UploadExpired: 上传任务已过期
            PartVerificationFailed: 分片验证失败
            MultipartUploadError: 没有上传任何分片
        """
        upload = self._get_upload(upload_id)
        
        if not upload.parts:
            raise MultipartUploadError("没有上传任何分片")
        
        # 验证分片（如果提供了 parts 参数）
        if parts:
            self._verify_parts(upload, parts)
        
        # 按顺序合并分片
        merged_content = b''
        sorted_parts = sorted(upload.parts, key=lambda p: p.part_number)
        
        for part in sorted_parts:
            part_path = self._get_part_path(upload_id, part.part_number)
            try:
                part_content = super().read_bytes(part_path)
                merged_content += part_content
            except FileNotFoundError:
                raise MultipartUploadError(f"分片文件丢失: part_number={part.part_number}")
        
        # 保存最终文件
        result = super().save(
            upload.path,
            merged_content,
            content_type=upload.content_type,
            metadata=upload.metadata,
        )
        
        # 清理临时文件和上传记录
        self._cleanup_upload(upload_id)
        
        logger.info(
            f"完成分片上传: upload_id={upload_id}, path={result}, "
            f"parts={len(sorted_parts)}, size={len(merged_content)}"
        )
        return result
    
    def abort_multipart_upload(self, upload_id: str) -> bool:
        """取消分片上传
        
        删除所有已上传的分片和上传记录。
        
        Args:
            upload_id: 上传任务ID
            
        Returns:
            bool: 是否成功取消
        """
        try:
            self._cleanup_upload(upload_id)
            logger.info(f"取消分片上传: upload_id={upload_id}")
            return True
        except Exception as e:
            logger.warning(f"取消分片上传失败: upload_id={upload_id}, error={e}")
            return False
    
    def list_parts(self, upload_id: str) -> List[UploadPart]:
        """列出已上传的分片
        
        Args:
            upload_id: 上传任务ID
            
        Returns:
            List[UploadPart]: 分片列表
        """
        upload = self._get_upload(upload_id)
        return sorted(upload.parts, key=lambda p: p.part_number)
    
    def get_upload_info(self, upload_id: str) -> MultipartUpload:
        """获取上传任务信息
        
        Args:
            upload_id: 上传任务ID
            
        Returns:
            MultipartUpload: 上传任务信息
        """
        return self._get_upload(upload_id)
    
    def list_uploads(self, path_prefix: str = "") -> List[MultipartUpload]:
        """列出所有进行中的上传任务
        
        Args:
            path_prefix: 路径前缀过滤
            
        Returns:
            List[MultipartUpload]: 上传任务列表
        """
        uploads = self._multipart_store.list_all()
        
        # 过滤已过期的
        active = [u for u in uploads if not u.is_expired()]
        
        # 按路径前缀过滤
        if path_prefix:
            active = [u for u in active if u.path.startswith(path_prefix)]
        
        return active
    
    def cleanup_expired_uploads(self) -> int:
        """清理过期的上传任务
        
        Returns:
            int: 清理的任务数量
        """
        uploads = self._multipart_store.list_all()
        expired = [u for u in uploads if u.is_expired()]
        
        for upload in expired:
            try:
                self._cleanup_upload(upload.upload_id)
            except Exception as e:
                logger.warning(f"清理过期上传失败: {upload.upload_id}, error={e}")
        
        if expired:
            logger.info(f"清理了 {len(expired)} 个过期的上传任务")
        
        return len(expired)
    
    # ==================== 私有方法 ====================
    
    def _get_upload(self, upload_id: str) -> MultipartUpload:
        """获取上传任务（带验证）"""
        upload = self._multipart_store.get(upload_id)
        
        if not upload:
            raise UploadNotFound(upload_id)
        
        if upload.is_expired():
            self._cleanup_upload(upload_id)
            raise UploadExpired(upload_id)
        
        return upload
    
    def _get_part_path(self, upload_id: str, part_number: int) -> str:
        """获取分片临时存储路径"""
        return f"_multipart/{upload_id}/{part_number}"
    
    def _verify_parts(self, upload: MultipartUpload, parts: List[dict]) -> None:
        """验证分片列表"""
        for p in parts:
            part_number = p.get('part_number')
            expected_etag = p.get('etag')
            
            uploaded = next(
                (up for up in upload.parts if up.part_number == part_number),
                None
            )
            
            if not uploaded:
                raise PartVerificationFailed(
                    part_number, expected_etag, "not uploaded"
                )
            
            if uploaded.etag != expected_etag:
                raise PartVerificationFailed(
                    part_number, expected_etag, uploaded.etag
                )
    
    def _cleanup_upload(self, upload_id: str) -> None:
        """清理上传任务"""
        upload = self._multipart_store.get(upload_id)
        
        if upload:
            # 删除所有分片文件
            for part in upload.parts:
                try:
                    part_path = self._get_part_path(upload_id, part.part_number)
                    super().delete(part_path)
                except Exception:
                    pass
            
            # 尝试删除分片目录
            try:
                dir_path = f"_multipart/{upload_id}"
                super().delete(dir_path)
            except Exception:
                pass
        
        # 删除上传记录
        self._multipart_store.delete(upload_id)


__all__ = [
    'UploadPart',
    'MultipartUpload',
    'MultipartUploadStore',
    'MemoryMultipartStore',
    'MultipartUploadMixin',
]
