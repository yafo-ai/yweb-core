# -*- coding: utf-8 -*-
"""
本地文件系统存储后端

将文件存储在本地文件系统中，适用于：
- 开发环境
- 小规模部署
- 文件需要直接访问的场景

特点：
- 直接使用文件系统存储
- 支持路径安全检查（防止路径穿越攻击）
- 自动创建目录
- 可配置文件权限
"""

import os
import shutil
import hashlib
import mimetypes
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Union, BinaryIO

from ..base import StorageBackend, FileInfo
from ..exceptions import StorageError


class LocalStorage(StorageBackend):
    """本地文件系统存储后端
    
    Args:
        base_path: 存储根目录（绝对路径）
        base_url: 访问URL前缀，用于 get_url() 方法
        create_dirs: 是否自动创建根目录，默认 True
        permissions: 文件权限，默认 0o644
        dir_permissions: 目录权限，默认 0o755
    
    Example:
        # 创建存储实例
        storage = LocalStorage(
            base_path="/data/uploads",
            base_url="https://example.com/files",
        )
        
        # 保存文件
        storage.save("images/avatar.jpg", file_content)
        
        # 读取文件
        with storage.read("images/avatar.jpg") as f:
            content = f.read()
        
        # 获取访问URL
        url = storage.get_url("images/avatar.jpg")
        # -> https://example.com/files/images/avatar.jpg
        
        # 获取绝对路径（用于其他程序直接访问）
        abs_path = storage.get_absolute_path("images/avatar.jpg")
        # -> /data/uploads/images/avatar.jpg
    
    Note:
        - 所有路径操作都会进行安全检查，防止路径穿越攻击
        - 存储路径使用正斜杠 (/)，会自动转换为系统路径分隔符
    """
    
    def __init__(
        self,
        base_path: str,
        base_url: Optional[str] = None,
        create_dirs: bool = True,
        permissions: int = 0o644,
        dir_permissions: int = 0o755,
    ):
        self.base_path = Path(base_path).resolve()
        self.base_url = base_url.rstrip('/') if base_url else None
        self.permissions = permissions
        self.dir_permissions = dir_permissions
        
        if create_dirs:
            self.base_path.mkdir(parents=True, exist_ok=True)
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        content_type: Optional[str] = None,
        metadata: Optional[dict] = None,
        overwrite: bool = True,
    ) -> str:
        """保存文件到本地文件系统
        
        Args:
            path: 存储路径（相对于 base_path）
            content: 文件内容（字节或文件对象）
            content_type: MIME类型（本地存储不使用，保留接口兼容）
            metadata: 自定义元数据（本地存储不持久化，保留接口兼容）
            overwrite: 是否覆盖已存在的文件
            
        Returns:
            str: 存储路径
            
        Raises:
            FileExistsError: overwrite=False 且文件已存在
            StorageError: 路径非法
        """
        full_path = self._resolve_path(path)
        
        # 检查是否已存在
        if not overwrite and full_path.exists():
            raise FileExistsError(f"文件已存在: {path}")
        
        # 创建目录
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 写入文件
        if isinstance(content, bytes):
            full_path.write_bytes(content)
        else:
            with open(full_path, 'wb') as f:
                shutil.copyfileobj(content, f)
        
        # 设置权限（仅在非 Windows 系统上）
        if os.name != 'nt':
            try:
                os.chmod(full_path, self.permissions)
            except OSError:
                pass  # 忽略权限设置失败
        
        # 规范化返回路径（使用正斜杠）
        return self._normalize_path(path)
    
    def read(self, path: str) -> BinaryIO:
        """读取文件
        
        Args:
            path: 文件路径
            
        Returns:
            BinaryIO: 文件对象
            
        Raises:
            FileNotFoundError: 文件不存在
            StorageError: 路径非法
        
        Note:
            返回的文件对象需要调用者负责关闭，建议使用 with 语句。
        """
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise FileNotFoundError(f"路径不是文件: {path}")
        
        return open(full_path, 'rb')
    
    def read_bytes(self, path: str) -> bytes:
        """读取文件内容为字节
        
        Args:
            path: 文件路径
            
        Returns:
            bytes: 文件内容
            
        Raises:
            FileNotFoundError: 文件不存在
            StorageError: 路径非法
        """
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise FileNotFoundError(f"路径不是文件: {path}")
        
        return full_path.read_bytes()
    
    def delete(self, path: str) -> bool:
        """删除文件或目录
        
        Args:
            path: 文件或目录路径
            
        Returns:
            bool: 是否删除成功（不存在返回 False）
            
        Note:
            如果是目录，会递归删除所有内容。
        """
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            return False
        
        try:
            if full_path.is_dir():
                shutil.rmtree(full_path)
            else:
                full_path.unlink()
            return True
        except OSError:
            return False
    
    def exists(self, path: str) -> bool:
        """检查文件是否存在
        
        Args:
            path: 文件路径
            
        Returns:
            bool: 文件是否存在
        """
        try:
            full_path = self._resolve_path(path)
            return full_path.exists() and full_path.is_file()
        except StorageError:
            return False
    
    def get_info(self, path: str) -> FileInfo:
        """获取文件信息
        
        Args:
            path: 文件路径
            
        Returns:
            FileInfo: 文件元信息
            
        Raises:
            FileNotFoundError: 文件不存在
            StorageError: 路径非法
        """
        full_path = self._resolve_path(path)
        
        if not full_path.exists():
            raise FileNotFoundError(f"文件不存在: {path}")
        
        if not full_path.is_file():
            raise FileNotFoundError(f"路径不是文件: {path}")
        
        stat = full_path.stat()
        content_type, _ = mimetypes.guess_type(str(full_path))
        
        # 计算 ETag（使用 MD5）
        etag = self._calculate_etag(full_path)
        
        # 规范化路径
        normalized_path = self._normalize_path(path)
        
        return FileInfo(
            path=normalized_path,
            size=stat.st_size,
            created_at=datetime.fromtimestamp(stat.st_ctime),
            modified_at=datetime.fromtimestamp(stat.st_mtime),
            content_type=content_type,
            etag=etag,
        )
    
    def list(
        self,
        prefix: str = "",
        recursive: bool = True,
        limit: Optional[int] = None,
    ) -> List[FileInfo]:
        """列出文件
        
        Args:
            prefix: 路径前缀（目录）
            recursive: 是否递归列出子目录中的文件
            limit: 最大返回数量
            
        Returns:
            List[FileInfo]: 文件信息列表
        """
        if prefix:
            try:
                base = self._resolve_path(prefix)
            except StorageError:
                return []
        else:
            base = self.base_path
        
        if not base.exists():
            return []
        
        # 如果 prefix 指向的是文件，直接返回该文件
        if base.is_file():
            try:
                return [self.get_info(prefix)]
            except Exception:
                return []
        
        results = []
        
        # 选择遍历方式
        if recursive:
            iterator = base.rglob('*')
        else:
            iterator = base.glob('*')
        
        for full_path in iterator:
            if full_path.is_file():
                # 计算相对路径
                try:
                    relative_path = full_path.relative_to(self.base_path)
                    # 转换为正斜杠路径
                    path_str = relative_path.as_posix()
                    results.append(self.get_info(path_str))
                except (ValueError, Exception):
                    continue
                
                if limit and len(results) >= limit:
                    break
        
        return results
    
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
            expires: 过期时间（本地存储不使用，保留接口兼容）
            download: 是否强制下载（本地存储不使用，保留接口兼容）
            filename: 下载文件名（本地存储不使用，保留接口兼容）
            
        Returns:
            str: 访问URL
            
        Raises:
            NotImplementedError: 未配置 base_url
            FileNotFoundError: 文件不存在
        
        Note:
            本地存储的 URL 是静态的，不支持过期时间和下载设置。
            如需这些功能，请使用 SecureURLGenerator。
        """
        if not self.base_url:
            raise NotImplementedError("未配置 base_url，无法生成访问URL")
        
        # 确保文件存在
        if not self.exists(path):
            raise FileNotFoundError(f"文件不存在: {path}")
        
        normalized_path = self._normalize_path(path)
        return f"{self.base_url}/{normalized_path}"
    
    # ==================== 本地存储特有方法 ====================
    
    def get_absolute_path(self, path: str) -> str:
        """获取文件的绝对路径
        
        Args:
            path: 相对路径
            
        Returns:
            str: 绝对路径
            
        Note:
            此方法用于需要直接访问文件系统的场景，
            如传递给其他程序或库。
        """
        full_path = self._resolve_path(path)
        return str(full_path)
    
    def get_relative_path(self, absolute_path: str) -> str:
        """将绝对路径转换为相对路径
        
        Args:
            absolute_path: 绝对路径
            
        Returns:
            str: 相对路径（使用正斜杠）
            
        Raises:
            StorageError: 路径不在存储目录内
        """
        try:
            abs_path = Path(absolute_path).resolve()
            relative = abs_path.relative_to(self.base_path)
            return relative.as_posix()
        except ValueError:
            raise StorageError(f"路径不在存储目录内: {absolute_path}")
    
    def ensure_directory(self, path: str) -> str:
        """确保目录存在
        
        Args:
            path: 目录路径
            
        Returns:
            str: 目录路径
        """
        full_path = self._resolve_path(path)
        full_path.mkdir(parents=True, exist_ok=True)
        
        if os.name != 'nt':
            try:
                os.chmod(full_path, self.dir_permissions)
            except OSError:
                pass
        
        return self._normalize_path(path)
    
    def get_stats(self) -> dict:
        """获取存储统计信息
        
        Returns:
            dict: 包含以下字段：
                - base_path: 存储根目录
                - file_count: 文件数量
                - total_size: 总大小（字节）
                - exists: 根目录是否存在
        """
        if not self.base_path.exists():
            return {
                'base_path': str(self.base_path),
                'file_count': 0,
                'total_size': 0,
                'exists': False,
            }
        
        file_count = 0
        total_size = 0
        
        for full_path in self.base_path.rglob('*'):
            if full_path.is_file():
                file_count += 1
                try:
                    total_size += full_path.stat().st_size
                except OSError:
                    pass
        
        return {
            'base_path': str(self.base_path),
            'file_count': file_count,
            'total_size': total_size,
            'exists': True,
        }
    
    # ==================== 私有方法 ====================
    
    def _resolve_path(self, path: str) -> Path:
        """解析并验证路径（防止路径穿越攻击）
        
        Args:
            path: 相对路径
            
        Returns:
            Path: 绝对路径对象
            
        Raises:
            StorageError: 路径非法（路径穿越尝试）
        """
        # 规范化路径：移除开头斜杠，转换为正斜杠
        clean_path = self._normalize_path(path)
        
        # 构建完整路径
        full_path = (self.base_path / clean_path).resolve()
        
        # 安全检查：确保路径在 base_path 内
        try:
            full_path.relative_to(self.base_path)
        except ValueError:
            raise StorageError(f"非法路径（路径穿越）: {path}")
        
        return full_path
    
    def _normalize_path(self, path: str) -> str:
        """规范化路径
        
        - 移除开头的斜杠
        - 转换反斜杠为正斜杠
        - 移除连续的斜杠
        """
        # 转换为正斜杠
        path = path.replace('\\', '/')
        # 移除开头的斜杠
        path = path.lstrip('/')
        # 移除连续的斜杠
        while '//' in path:
            path = path.replace('//', '/')
        return path
    
    def _calculate_etag(self, full_path: Path, chunk_size: int = 8192) -> str:
        """计算文件的 ETag（MD5）
        
        对于大文件，使用分块读取以避免内存问题。
        """
        md5 = hashlib.md5()
        with open(full_path, 'rb') as f:
            for chunk in iter(lambda: f.read(chunk_size), b''):
                md5.update(chunk)
        return md5.hexdigest()


__all__ = ["LocalStorage"]
