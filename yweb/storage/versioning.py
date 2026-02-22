# -*- coding: utf-8 -*-
"""
文件版本管理模块

提供文件版本控制功能：
- 自动保存文件历史版本
- 查看版本列表
- 恢复到指定版本
- 版本比较

使用示例:
    class VersionedStorage(VersionedStorageMixin, LocalStorage):
        pass
    
    storage = VersionedStorage('/data', enable_versioning=True)
    
    # 保存会自动创建版本
    storage.save('doc.txt', b'v1', version_message='初始版本')
    storage.save('doc.txt', b'v2', version_message='更新内容')
    
    # 查看版本
    versions = storage.list_versions('doc.txt')
    
    # 恢复版本
    storage.restore_version('doc.txt', versions[1].version_id)
"""

import hashlib
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List, Dict, Any, Union, BinaryIO

logger = logging.getLogger(__name__)


@dataclass
class FileVersion:
    """文件版本信息
    
    Attributes:
        version_id: 版本ID（格式：时间戳_哈希前缀）
        path: 文件路径
        size: 文件大小（字节）
        etag: 内容哈希（SHA256 前16位）
        created_at: 创建时间
        created_by: 创建者标识
        message: 版本说明
        is_current: 是否为当前版本
    """
    version_id: str
    path: str
    size: int
    etag: str
    created_at: datetime
    created_by: Optional[str] = None
    message: Optional[str] = None
    is_current: bool = False
    
    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            'version_id': self.version_id,
            'path': self.path,
            'size': self.size,
            'etag': self.etag,
            'created_at': self.created_at.isoformat(),
            'created_by': self.created_by,
            'message': self.message,
            'is_current': self.is_current,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> 'FileVersion':
        """从字典创建"""
        created_at = data['created_at']
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        
        return cls(
            version_id=data['version_id'],
            path=data['path'],
            size=data['size'],
            etag=data['etag'],
            created_at=created_at,
            created_by=data.get('created_by'),
            message=data.get('message'),
            is_current=data.get('is_current', False),
        )


class VersionedStorageMixin:
    """版本管理Mixin
    
    为存储后端添加文件版本控制能力。
    
    每次保存文件时，如果内容发生变化，会自动创建新版本。
    版本文件存储在 `_versions/{path}/{version_id}` 路径下。
    
    Args:
        enable_versioning: 是否启用版本控制
        max_versions: 每个文件最大保留版本数
    
    Example:
        class VersionedLocalStorage(VersionedStorageMixin, LocalStorage):
            pass
        
        storage = VersionedLocalStorage('/data', max_versions=50)
        
        # 保存时附加版本信息
        storage.save('readme.txt', b'Hello', version_message='Initial version')
        storage.save('readme.txt', b'Hello World', version_message='Add greeting')
        
        # 查看版本历史
        for v in storage.list_versions('readme.txt'):
            print(f"{v.version_id}: {v.message}")
        
        # 恢复到旧版本
        storage.restore_version('readme.txt', 'old_version_id')
    """
    
    DEFAULT_MAX_VERSIONS = 100
    
    def __init__(
        self,
        *args,
        enable_versioning: bool = True,
        max_versions: int = DEFAULT_MAX_VERSIONS,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._versioning_enabled = enable_versioning
        self._max_versions = max_versions
    
    def save(
        self,
        path: str,
        content: Union[BinaryIO, bytes],
        version_message: Optional[str] = None,
        created_by: Optional[str] = None,
        skip_versioning: bool = False,
        **kwargs,
    ) -> str:
        """保存文件（自动创建版本）
        
        Args:
            path: 文件路径
            content: 文件内容
            version_message: 版本说明
            created_by: 创建者标识
            skip_versioning: 是否跳过版本控制
            **kwargs: 传递给父类的参数
            
        Returns:
            str: 保存的路径
        """
        # 如果禁用版本控制或要跳过
        if not self._versioning_enabled or skip_versioning:
            return super().save(path, content, **kwargs)
        
        # 内部版本文件不需要版本控制
        if path.startswith('_versions/'):
            return super().save(path, content, **kwargs)
        
        # 读取内容
        if isinstance(content, bytes):
            data = content
        else:
            pos = content.tell()
            data = content.read()
            content.seek(pos)
        
        # 计算哈希
        etag = hashlib.sha256(data).hexdigest()[:16]
        
        # 检查内容是否有变化
        try:
            current = self.get_current_version(path)
            if current and current.etag == etag:
                # 内容未变化，不创建新版本
                logger.debug(f"内容未变化，跳过版本创建: {path}")
                return path
        except FileNotFoundError:
            pass
        
        # 生成版本ID
        timestamp = datetime.now().strftime('%Y%m%d%H%M%S')
        version_id = f"{timestamp}_{etag[:8]}"
        
        # 保存版本文件
        version_path = self._version_path(path, version_id)
        super().save(version_path, data, **kwargs)
        
        # 保存当前文件
        result = super().save(path, data, **kwargs)
        
        # 创建版本记录
        version = FileVersion(
            version_id=version_id,
            path=path,
            size=len(data),
            etag=etag,
            created_at=datetime.now(),
            created_by=created_by,
            message=version_message,
            is_current=True,
        )
        
        # 更新版本元数据
        self._add_version(path, version)
        
        logger.info(f"创建新版本: {path} -> {version_id}")
        return result
    
    def list_versions(self, path: str) -> List[FileVersion]:
        """列出文件的所有版本
        
        Args:
            path: 文件路径
            
        Returns:
            List[FileVersion]: 版本列表（按时间倒序）
        """
        metadata_path = self._metadata_path(path)
        
        try:
            data = super().read_bytes(metadata_path)
            versions_data = json.loads(data.decode('utf-8'))
            return [FileVersion.from_dict(v) for v in versions_data]
        except FileNotFoundError:
            return []
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning(f"版本元数据损坏: {path}, error={e}")
            return []
    
    def get_version(self, path: str, version_id: str) -> bytes:
        """获取指定版本的内容
        
        Args:
            path: 文件路径
            version_id: 版本ID
            
        Returns:
            bytes: 文件内容
            
        Raises:
            FileNotFoundError: 版本不存在
        """
        version_path = self._version_path(path, version_id)
        return super().read_bytes(version_path)
    
    def get_current_version(self, path: str) -> Optional[FileVersion]:
        """获取当前版本信息
        
        Args:
            path: 文件路径
            
        Returns:
            Optional[FileVersion]: 当前版本，不存在返回 None
        """
        versions = self.list_versions(path)
        for v in versions:
            if v.is_current:
                return v
        return None
    
    def get_version_info(self, path: str, version_id: str) -> Optional[FileVersion]:
        """获取指定版本的信息
        
        Args:
            path: 文件路径
            version_id: 版本ID
            
        Returns:
            Optional[FileVersion]: 版本信息
        """
        versions = self.list_versions(path)
        return next((v for v in versions if v.version_id == version_id), None)
    
    def restore_version(
        self,
        path: str,
        version_id: str,
        message: Optional[str] = None,
        created_by: Optional[str] = None,
    ) -> str:
        """恢复到指定版本
        
        将指定版本的内容保存为新的当前版本。
        
        Args:
            path: 文件路径
            version_id: 要恢复的版本ID
            message: 新版本的说明
            created_by: 创建者标识
            
        Returns:
            str: 保存的路径
            
        Raises:
            FileNotFoundError: 版本不存在
        """
        # 获取版本内容
        content = self.get_version(path, version_id)
        
        # 保存为新版本
        restore_message = message or f"Restored from version {version_id}"
        
        return self.save(
            path,
            content,
            version_message=restore_message,
            created_by=created_by,
        )
    
    def delete_version(self, path: str, version_id: str) -> bool:
        """删除指定版本
        
        不能删除当前版本。
        
        Args:
            path: 文件路径
            version_id: 版本ID
            
        Returns:
            bool: 是否删除成功
            
        Raises:
            ValueError: 尝试删除当前版本
        """
        versions = self.list_versions(path)
        version = next((v for v in versions if v.version_id == version_id), None)
        
        if not version:
            return False
        
        if version.is_current:
            raise ValueError("不能删除当前版本")
        
        # 删除版本文件
        version_path = self._version_path(path, version_id)
        try:
            super().delete(version_path)
        except FileNotFoundError:
            pass
        
        # 更新元数据
        versions = [v for v in versions if v.version_id != version_id]
        self._save_versions_metadata(path, versions)
        
        logger.info(f"删除版本: {path} -> {version_id}")
        return True
    
    def delete_all_versions(self, path: str) -> int:
        """删除文件的所有版本
        
        Args:
            path: 文件路径
            
        Returns:
            int: 删除的版本数
        """
        versions = self.list_versions(path)
        count = 0
        
        for version in versions:
            version_path = self._version_path(path, version.version_id)
            try:
                super().delete(version_path)
                count += 1
            except FileNotFoundError:
                pass
        
        # 删除元数据
        metadata_path = self._metadata_path(path)
        try:
            super().delete(metadata_path)
        except FileNotFoundError:
            pass
        
        logger.info(f"删除所有版本: {path}, count={count}")
        return count
    
    def compare_versions(
        self,
        path: str,
        version_id1: str,
        version_id2: str,
    ) -> Dict[str, Any]:
        """比较两个版本
        
        Args:
            path: 文件路径
            version_id1: 第一个版本ID
            version_id2: 第二个版本ID
            
        Returns:
            dict: 比较结果
        """
        v1_info = self.get_version_info(path, version_id1)
        v2_info = self.get_version_info(path, version_id2)
        
        if not v1_info or not v2_info:
            raise FileNotFoundError("版本不存在")
        
        v1_content = self.get_version(path, version_id1)
        v2_content = self.get_version(path, version_id2)
        
        return {
            'version1': v1_info.to_dict(),
            'version2': v2_info.to_dict(),
            'same_content': v1_info.etag == v2_info.etag,
            'size_diff': v2_info.size - v1_info.size,
            'time_diff_seconds': (v2_info.created_at - v1_info.created_at).total_seconds(),
        }
    
    # ==================== 私有方法 ====================
    
    def _version_path(self, path: str, version_id: str) -> str:
        """获取版本文件路径"""
        # 移除路径开头的斜杠
        clean_path = path.lstrip('/')
        return f"_versions/{clean_path}/{version_id}"
    
    def _metadata_path(self, path: str) -> str:
        """获取版本元数据路径"""
        clean_path = path.lstrip('/')
        return f"_versions/{clean_path}/_metadata.json"
    
    def _add_version(self, path: str, version: FileVersion) -> None:
        """添加版本记录"""
        versions = self.list_versions(path)
        
        # 将之前的版本标记为非当前
        for v in versions:
            v.is_current = False
        
        # 添加新版本到开头
        versions.insert(0, version)
        
        # 限制版本数量
        if len(versions) > self._max_versions:
            # 删除最老的版本文件
            for old in versions[self._max_versions:]:
                try:
                    old_path = self._version_path(path, old.version_id)
                    super().delete(old_path)
                    logger.debug(f"删除旧版本: {old.version_id}")
                except Exception:
                    pass
            versions = versions[:self._max_versions]
        
        self._save_versions_metadata(path, versions)
    
    def _save_versions_metadata(self, path: str, versions: List[FileVersion]) -> None:
        """保存版本元数据"""
        metadata_path = self._metadata_path(path)
        data = json.dumps(
            [v.to_dict() for v in versions],
            ensure_ascii=False,
            indent=2,
        )
        super().save(metadata_path, data.encode('utf-8'))


__all__ = [
    'FileVersion',
    'VersionedStorageMixin',
]
