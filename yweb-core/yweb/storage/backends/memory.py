# -*- coding: utf-8 -*-
"""
内存存储后端

将文件存储在内存中，适用于：
- 临时文件处理
- 单元测试
- 文件上传预处理（验证后再存储到持久化后端）

特点：
- 数据存储在内存中，重启后丢失
- 支持 LRU 淘汰策略
- 线程安全
"""

import threading
import mimetypes
import hashlib
from io import BytesIO
from datetime import datetime
from typing import Dict, Optional, List, Union, BinaryIO
from collections import OrderedDict

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageQuotaExceeded


class MemoryStorage(StorageBackend):
    """内存存储后端
    
    将文件存储在内存中，支持 LRU 淘汰策略和容量限制。
    
    Args:
        max_size: 最大存储大小（字节），默认 100MB
        max_files: 最大文件数量，默认 10000
        auto_cleanup: 是否自动清理超出限制的文件，默认 True
    
    Example:
        # 创建存储实例
        storage = MemoryStorage(max_size=100*1024*1024)  # 100MB
        
        # 保存文件
        storage.save("temp/upload.jpg", file_content)
        
        # 读取文件
        with storage.read("temp/upload.jpg") as f:
            content = f.read()
        
        # 获取统计信息
        stats = storage.get_stats()
        print(f"使用率: {stats['usage_percent']:.1f}%")
    
    Note:
        - 当存储空间不足时，会自动淘汰最久未访问的文件（LRU策略）
        - 如果单个文件大小超过 max_size，将抛出 StorageQuotaExceeded 异常
    """
    
    def __init__(
        self,
        max_size: int = 100 * 1024 * 1024,  # 默认100MB
        max_files: int = 10000,              # 最大文件数
        auto_cleanup: bool = True,           # 自动清理
    ):
        self._files: OrderedDict[str, bytes] = OrderedDict()
        self._metadata: Dict[str, FileInfo] = {}
        self._lock = threading.RLock()
        self._max_size = max_size
        self._max_files = max_files
        self._current_size = 0
        self._auto_cleanup = auto_cleanup
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件到内存
        
        Args:
            path: 存储路径
            content: 文件内容（字节或文件对象）
            content_type: MIME类型，不指定则自动检测
            metadata: 自定义元数据
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 存储路径
            
        Raises:
            FileExistsError: overwrite=False 且文件已存在
            StorageQuotaExceeded: 存储空间不足
        """
        # 规范化路径
        path = self._normalize_path(path)
        
        # 读取内容
        if isinstance(content, bytes):
            data = content
        else:
            data = content.read()
        
        # 检查单个文件是否超过最大限制
        if len(data) > self._max_size:
            raise StorageQuotaExceeded(
                message=f"文件大小 {len(data)} 超过最大限制 {self._max_size}",
                current=len(data),
                limit=self._max_size,
            )
        
        with self._lock:
            # 检查是否已存在
            if not overwrite and path in self._files:
                raise FileExistsError(f"文件已存在: {path}")
            
            # 如果是覆盖，先减去原文件大小
            if path in self._files:
                self._current_size -= len(self._files[path])
            
            # 检查容量，必要时清理
            if self._auto_cleanup:
                while (self._current_size + len(data) > self._max_size or 
                       len(self._files) >= self._max_files):
                    if not self._files:
                        raise StorageQuotaExceeded(
                            message="内存存储空间不足",
                            current=self._current_size + len(data),
                            limit=self._max_size,
                        )
                    self._evict_oldest()
            else:
                # 不自动清理时直接检查
                if self._current_size + len(data) > self._max_size:
                    raise StorageQuotaExceeded(
                        message="内存存储空间不足",
                        current=self._current_size + len(data),
                        limit=self._max_size,
                    )
                if len(self._files) >= self._max_files:
                    raise StorageQuotaExceeded(
                        message=f"文件数量超过限制 {self._max_files}",
                        current=len(self._files),
                        limit=self._max_files,
                    )
            
            # 存储文件
            self._files[path] = data
            self._files.move_to_end(path)  # LRU: 移到末尾
            
            # 计算 ETag
            etag = hashlib.md5(data).hexdigest()
            
            # 获取或创建时间
            now = datetime.now()
            existing = self._metadata.get(path)
            created_at = existing.created_at if existing else now
            
            # 存储元信息
            self._metadata[path] = FileInfo(
                path=path,
                size=len(data),
                created_at=created_at,
                modified_at=now,
                content_type=content_type or self._guess_content_type(path),
                etag=etag,
                metadata=metadata or {},
            )
            
            self._current_size += len(data)
        
        return path
    
    def read(self, path: str) -> BinaryIO:
        """读取文件
        
        Args:
            path: 文件路径
            
        Returns:
            BinaryIO: 文件对象（BytesIO）
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        path = self._normalize_path(path)
        
        with self._lock:
            if path not in self._files:
                raise FileNotFoundError(f"文件不存在: {path}")
            
            # LRU: 访问后移到末尾
            self._files.move_to_end(path)
            
            # 返回副本，避免外部修改
            return BytesIO(self._files[path])
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件内容为字节
        
        Args:
            path: 文件路径
            
        Returns:
            bytes: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        path = self._normalize_path(path)
        
        with self._lock:
            if path not in self._files:
                raise FileNotFoundError(f"文件不存在: {path}")
            
            # LRU: 访问后移到末尾
            self._files.move_to_end(path)
            
            return self._files[path]
    
    def delete(self, path: str) -> bool:
        """删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 是否删除成功（文件不存在返回 False）
        """
        path = self._normalize_path(path)
        
        with self._lock:
            if path not in self._files:
                return False
            
            self._current_size -= len(self._files[path])
            del self._files[path]
            del self._metadata[path]
            return True
    
    def exists(self, path: str) -> bool:
        """检查文件是否存在
        
        Args:
            path: 文件路径（会自动规范化）
            
        Returns:
            bool: 文件是否存在
        
        Note:
            路径会自动规范化，所以 "/test/file.txt" 和 "test/file.txt" 是等价的。
        """
        normalized = self._normalize_path(path)
        return normalized in self._files
    
    def get_info(self, path: str) -> FileInfo:
        """获取文件信息
        
        Args:
            path: 文件路径
            
        Returns:
            FileInfo: 文件元信息
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        path = self._normalize_path(path)
        
        with self._lock:
            if path not in self._metadata:
                raise FileNotFoundError(f"文件不存在: {path}")
            return self._metadata[path]
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """列出文件
        
        Args:
            prefix: 路径前缀（目录）
            recursive: 是否递归列出子目录
            limit: 最大返回数量
            
        Returns:
            List[FileInfo]: 文件信息列表
        """
        prefix = self._normalize_path(prefix)
        
        with self._lock:
            results = []
            for path, info in self._metadata.items():
                if path.startswith(prefix):
                    # 非递归时只返回直接子文件
                    if not recursive:
                        relative = path[len(prefix):].lstrip('/')
                        if '/' in relative:
                            continue
                    results.append(info)
                    if limit and len(results) >= limit:
                        break
            return results
    
    # ==================== 内存存储特有方法 ====================
    
    def clear(self) -> None:
        """清空所有文件"""
        with self._lock:
            self._files.clear()
            self._metadata.clear()
            self._current_size = 0
    
    def get_stats(self) -> dict:
        """获取存储统计信息
        
        Returns:
            dict: 包含以下字段：
                - file_count: 文件数量
                - total_size: 当前总大小（字节）
                - max_size: 最大大小（字节）
                - max_files: 最大文件数
                - usage_percent: 使用率（百分比）
        """
        with self._lock:
            return {
                'file_count': len(self._files),
                'total_size': self._current_size,
                'max_size': self._max_size,
                'max_files': self._max_files,
                'usage_percent': (self._current_size / self._max_size * 100) if self._max_size else 0,
            }
    
    def list_paths(self) -> List[str]:
        """列出所有文件路径
        
        Returns:
            List[str]: 文件路径列表
        """
        with self._lock:
            return list(self._files.keys())
    
    # ==================== 私有方法 ====================
    
    def _normalize_path(self, path: str) -> str:
        """规范化路径"""
        # 移除开头的斜杠，统一使用相对路径
        return path.lstrip('/')
    
    def _evict_oldest(self) -> None:
        """淘汰最老的文件（LRU）"""
        if self._files:
            oldest_path = next(iter(self._files))
            self._current_size -= len(self._files[oldest_path])
            del self._files[oldest_path]
            del self._metadata[oldest_path]
    
    def _guess_content_type(self, path: str) -> str:
        """根据文件名猜测 MIME 类型"""
        content_type, _ = mimetypes.guess_type(path)
        return content_type or 'application/octet-stream'


__all__ = ["MemoryStorage"]
