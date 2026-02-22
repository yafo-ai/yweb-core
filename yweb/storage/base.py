# -*- coding: utf-8 -*-
"""
存储模块基础定义

包含:
- FileInfo: 文件元信息数据类
- StorageBackend: 存储后端抽象基类
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import BinaryIO, List, Optional, Union, Dict, Any
from io import BytesIO


@dataclass
class FileInfo:
    """文件元信息
    
    存储文件的各种元数据，包括路径、大小、时间戳等。
    
    Attributes:
        path: 存储路径（相对路径）
        size: 文件大小（字节）
        created_at: 创建时间
        modified_at: 修改时间
        content_type: MIME类型
        etag: ETag（用于缓存验证）
        metadata: 自定义元数据
    
    Example:
        info = FileInfo(
            path="images/avatar.jpg",
            size=1024,
            content_type="image/jpeg",
        )
        print(info.filename)   # avatar.jpg
        print(info.extension)  # jpg
    """
    
    path: str
    size: int
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    content_type: Optional[str] = None
    etag: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def filename(self) -> str:
        """获取文件名（不含目录）"""
        return self.path.split('/')[-1]
    
    @property
    def extension(self) -> str:
        """获取文件扩展名（不含点号）"""
        name = self.filename
        if '.' in name:
            return name.rsplit('.', 1)[-1].lower()
        return ''
    
    @property
    def directory(self) -> str:
        """获取目录路径"""
        parts = self.path.rsplit('/', 1)
        return parts[0] if len(parts) > 1 else ''
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'path': self.path,
            'filename': self.filename,
            'size': self.size,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'modified_at': self.modified_at.isoformat() if self.modified_at else None,
            'content_type': self.content_type,
            'etag': self.etag,
            'metadata': self.metadata,
        }


class StorageBackend(ABC):
    """存储后端抽象基类
    
    所有存储后端必须实现此接口，保证统一的操作方式。
    
    必须实现的方法:
        - save(): 保存文件
        - read(): 读取文件
        - delete(): 删除文件
        - exists(): 检查文件是否存在
        - get_info(): 获取文件信息
        - list(): 列出文件
    
    可选实现的方法:
        - read_bytes(): 读取文件内容为字节
        - get_url(): 获取文件访问URL
        - copy(): 复制文件
        - move(): 移动文件
        - get_size(): 获取文件大小
    
    Example:
        class MyStorage(StorageBackend):
            def save(self, path, content, **kwargs):
                # 实现保存逻辑
                pass
            # ... 实现其他必要方法
    """
    
    # ==================== 必须实现的方法 ====================
    
    @abstractmethod
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件
        
        Args:
            path: 存储路径（相对路径）
            content: 文件内容（文件对象或字节）
            content_type: MIME类型，不指定则自动检测
            metadata: 自定义元数据
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 实际存储路径
            
        Raises:
            FileExistsError: overwrite=False 且文件已存在
            StorageError: 存储失败
        """
        pass
    
    @abstractmethod
    def read(self, path: str) -> BinaryIO:
        """读取文件，返回文件对象
        
        Args:
            path: 文件路径
            
        Returns:
            BinaryIO: 可读取的文件对象
            
        Raises:
            FileNotFoundError: 文件不存在
        
        Note:
            返回的文件对象需要调用者负责关闭，建议使用 with 语句。
        """
        pass
    
    @abstractmethod
    def delete(self, path: str) -> bool:
        """删除文件
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 是否删除成功（文件不存在时返回 False）
        """
        pass
    
    @abstractmethod
    def exists(self, path: str) -> bool:
        """检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 文件是否存在
        """
        pass
    
    @abstractmethod
    def get_info(self, path: str) -> FileInfo:
        """获取文件信息
        
        Args:
            path: 文件路径
            
        Returns:
            FileInfo: 文件元信息
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        pass
    
    @abstractmethod
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """列出文件
        
        Args:
            prefix: 路径前缀（目录），如 "images/"
            recursive: 是否递归列出子目录中的文件
            limit: 最大返回数量
            
        Returns:
            List[FileInfo]: 文件信息列表
        """
        pass
    
    # ==================== 可选实现的方法 ====================
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件内容为字节
        
        Args:
            path: 文件路径
            
        Returns:
            bytes: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        f = self.read(path)
        try:
            return f.read()
        finally:
            f.close()
    
    def get_url(
        self,
        path: str,
        expires: int = 3600,
        download: bool = False,
        filename: Optional[str] = None,
    ) -> str:
        """获取文件访问URL
        
        Args:
            path: 文件路径
            expires: 过期时间（秒）
            download: 是否强制下载（设置 Content-Disposition）
            filename: 下载时的文件名
            
        Returns:
            str: 访问URL
            
        Raises:
            NotImplementedError: 后端不支持URL访问
            FileNotFoundError: 文件不存在
        """
        raise NotImplementedError(f"{self.__class__.__name__} 不支持 get_url")
    
    def copy(self, src: str, dst: str, overwrite: bool = True) -> str:
        """复制文件
        
        Args:
            src: 源文件路径
            dst: 目标文件路径
            overwrite: 是否覆盖已存在的目标文件
            
        Returns:
            str: 目标文件路径
            
        Raises:
            FileNotFoundError: 源文件不存在
            FileExistsError: overwrite=False 且目标文件已存在
        """
        content = self.read(src)
        try:
            info = self.get_info(src)
            return self.save(
                dst,
                content,
                content_type=info.content_type,
                metadata=info.metadata,
                overwrite=overwrite,
            )
        finally:
            content.close()
    
    def move(self, src: str, dst: str, overwrite: bool = True) -> str:
        """移动文件
        
        Args:
            src: 源文件路径
            dst: 目标文件路径
            overwrite: 是否覆盖已存在的目标文件
            
        Returns:
            str: 目标文件路径
            
        Raises:
            FileNotFoundError: 源文件不存在
            FileExistsError: overwrite=False 且目标文件已存在
        """
        result = self.copy(src, dst, overwrite=overwrite)
        self.delete(src)
        return result
    
    def get_size(self, path: str) -> int:
        """获取文件大小
        
        Args:
            path: 文件路径
            
        Returns:
            int: 文件大小（字节）
            
        Raises:
            FileNotFoundError: 文件不存在
        """
        return self.get_info(path).size


# ==================== 导出 ====================

__all__ = [
    "FileInfo",
    "StorageBackend",
]
