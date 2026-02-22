# -*- coding: utf-8 -*-
"""
yweb-storage 虚拟文件系统模块

提供统一的文件存储抽象，支持多种存储后端（内存、本地、OSS、S3等），
以及安全的文件访问机制（Token、签名URL）。

基本使用:
    from yweb.storage import StorageManager, LocalStorage
    
    # 注册存储后端
    StorageManager.register('local', LocalStorage('/data/uploads'), default=True)
    
    # 使用存储
    storage = StorageManager.get()
    storage.save('images/avatar.jpg', file_content)
    content = storage.read('images/avatar.jpg')

配置初始化:
    from yweb.storage import StorageManager
    
    StorageManager.configure({
        'backends': {
            'local': {'type': 'local', 'base_path': '/data/uploads'},
            'temp': {'type': 'memory', 'max_size': 50*1024*1024},
        },
        'default': 'local'
    })

安全访问 (Phase 2):
    from yweb.storage import SecureURLGenerator
    
    secure_url = SecureURLGenerator(secret_key="your-secret-key")
    url = secure_url.generate("private/file.pdf", expires_in=3600, user_id=123)
"""

# 版本
__version__ = "0.1.0"

# ==================== 核心类 ====================

from .base import StorageBackend, FileInfo
from .manager import StorageManager

# ==================== 内置后端 ====================

from .backends.memory import MemoryStorage
from .backends.local import LocalStorage

# ==================== 异常 ====================

from .exceptions import (
    StorageError,
    StorageConfigError,
    StorageNotFoundError,
    StorageQuotaExceeded,
    InvalidFileError,
    InvalidFileType,
    FileTooLarge,
    FileTooSmall,
    FileValidationError,
)

# ==================== 配置 ====================

from .config import (
    StorageConfig,
    MemoryStorageConfig,
    LocalStorageConfig,
    validate_config,
)

# ==================== 验证 ====================

from .validators import (
    FileValidator,
    FileValidationConfig,
    ValidationResult,
    ValidatedStorageMixin,
)

# ==================== 分片上传 ====================

from .multipart import (
    MultipartUploadMixin,
    MultipartUpload,
    UploadPart,
)

# ==================== 监控指标 ====================

from .metrics import (
    MetricsCollector,
    InstrumentedStorageMixin,
    OperationType,
    StorageMetrics,
)

# ==================== 版本管理 ====================

from .versioning import (
    FileVersion,
    VersionedStorageMixin,
)


__all__ = [
    # 版本
    '__version__',
    
    # 基类
    'StorageBackend',
    'FileInfo',
    
    # 管理器
    'StorageManager',
    
    # 内置后端
    'MemoryStorage',
    'LocalStorage',
    
    # 异常
    'StorageError',
    'StorageConfigError',
    'StorageNotFoundError',
    'StorageQuotaExceeded',
    'InvalidFileError',
    'InvalidFileType',
    'FileTooLarge',
    'FileTooSmall',
    'FileValidationError',
    
    # 配置
    'StorageConfig',
    'MemoryStorageConfig',
    'LocalStorageConfig',
    'validate_config',
    
    # 验证
    'FileValidator',
    'FileValidationConfig',
    'ValidationResult',
    'ValidatedStorageMixin',
    
    # 分片上传
    'MultipartUploadMixin',
    'MultipartUpload',
    'UploadPart',
    
    # 监控指标
    'MetricsCollector',
    'InstrumentedStorageMixin',
    'OperationType',
    'StorageMetrics',
    
    # 版本管理
    'FileVersion',
    'VersionedStorageMixin',
]


# ==================== 延迟导入（可选后端） ====================

def __getattr__(name: str):
    """延迟导入可选组件
    
    支持：
    - OSSStorage: 阿里云 OSS (需要 oss2)
    - S3Storage: AWS S3 / MinIO (需要 boto3)
    - SecureURLGenerator: 安全URL生成器 (Phase 2)
    - RedisTokenStore: Redis Token存储 (Phase 2, 需要 redis)
    """
    # 可选后端
    if name == 'OSSStorage':
        try:
            from .backends.oss import OSSStorage
            return OSSStorage
        except ImportError as e:
            raise ImportError(
                f"使用 OSSStorage 需要安装 oss2: pip install oss2\n"
                f"原始错误: {e}"
            )
    
    if name == 'S3Storage':
        try:
            from .backends.s3 import S3Storage
            return S3Storage
        except ImportError as e:
            raise ImportError(
                f"使用 S3Storage 需要安装 boto3: pip install boto3\n"
                f"原始错误: {e}"
            )
    
    # Phase 2 组件
    if name == 'SecureURLGenerator':
        from .secure_url import SecureURLGenerator
        return SecureURLGenerator
    
    if name == 'SecureURL':
        from .secure_url import SecureURL
        return SecureURL
    
    if name == 'TokenStore':
        from .secure_url import TokenStore
        return TokenStore
    
    if name == 'MemoryTokenStore':
        from .secure_url import MemoryTokenStore
        return MemoryTokenStore
    
    if name == 'RedisTokenStore':
        try:
            from .secure_url import RedisTokenStore
            return RedisTokenStore
        except ImportError as e:
            raise ImportError(
                f"使用 RedisTokenStore 需要安装 redis: pip install redis\n"
                f"原始错误: {e}"
            )
    
    # 配置类
    if name == 'OSSStorageConfig':
        from .config import OSSStorageConfig
        return OSSStorageConfig
    
    if name == 'S3StorageConfig':
        from .config import S3StorageConfig
        return S3StorageConfig
    
    if name == 'SecureURLConfig':
        from .config import SecureURLConfig
        return SecureURLConfig
    
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
