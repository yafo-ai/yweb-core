# -*- coding: utf-8 -*-
"""
存储后端模块

提供多种存储后端实现：
- MemoryStorage: 内存存储（临时文件、测试）
- LocalStorage: 本地文件系统存储
- OSSStorage: 阿里云 OSS 存储（需要 oss2）
- S3Storage: AWS S3 / MinIO 存储（需要 boto3）

使用示例:
    from yweb.storage.backends import MemoryStorage, LocalStorage
    
    # 内存存储
    memory = MemoryStorage(max_size=100*1024*1024)
    
    # 本地存储
    local = LocalStorage('/data/uploads')
"""

# 内置后端（始终可用）
from .memory import MemoryStorage
from .local import LocalStorage

__all__ = [
    'MemoryStorage',
    'LocalStorage',
]


# 延迟导入可选后端
def __getattr__(name: str):
    """延迟导入可选后端"""
    if name == 'OSSStorage':
        try:
            from .oss import OSSStorage
            return OSSStorage
        except ImportError as e:
            raise ImportError(
                f"使用 OSSStorage 需要安装 oss2: pip install oss2\n"
                f"原始错误: {e}"
            )
    
    if name == 'S3Storage':
        try:
            from .s3 import S3Storage
            return S3Storage
        except ImportError as e:
            raise ImportError(
                f"使用 S3Storage 需要安装 boto3: pip install boto3\n"
                f"原始错误: {e}"
            )
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
