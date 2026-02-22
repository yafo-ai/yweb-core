# -*- coding: utf-8 -*-
"""
存储模块配置模型

使用 Pydantic 进行配置验证，支持：
- 类型检查和自动转换
- 环境变量解析
- 启动时配置验证
"""

import os
from typing import Optional, Dict, Any, Literal, Union
from pydantic import BaseModel, Field, field_validator, model_validator


def resolve_env_var(value: str) -> str:
    """解析环境变量
    
    支持格式：${ENV_VAR_NAME}
    
    Args:
        value: 可能包含环境变量引用的字符串
        
    Returns:
        str: 解析后的值
        
    Raises:
        ValueError: 环境变量未设置
    """
    if isinstance(value, str) and value.startswith('${') and value.endswith('}'):
        env_var = value[2:-1]
        resolved = os.environ.get(env_var)
        if resolved is None:
            raise ValueError(f"环境变量未设置: {env_var}")
        return resolved
    return value


class BaseStorageConfig(BaseModel):
    """存储配置基类"""
    
    type: str = Field(..., description="存储后端类型")
    
    model_config = {
        'extra': 'forbid',  # 禁止额外字段
    }


class MemoryStorageConfig(BaseStorageConfig):
    """内存存储配置
    
    Example:
        {
            "type": "memory",
            "max_size": 104857600,  # 100MB
            "max_files": 10000
        }
    """
    
    type: Literal['memory'] = 'memory'
    max_size: int = Field(
        default=100 * 1024 * 1024,
        gt=0,
        description="最大存储大小（字节）",
    )
    max_files: int = Field(
        default=10000,
        gt=0,
        description="最大文件数",
    )
    auto_cleanup: bool = Field(
        default=True,
        description="空间不足时是否自动清理",
    )
    
    @field_validator('max_size')
    @classmethod
    def validate_max_size(cls, v: int) -> int:
        max_allowed = 10 * 1024 * 1024 * 1024  # 10GB
        if v > max_allowed:
            raise ValueError(f"内存存储最大不超过 10GB，当前设置: {v}")
        return v


class LocalStorageConfig(BaseStorageConfig):
    """本地存储配置
    
    Example:
        {
            "type": "local",
            "base_path": "/data/uploads",
            "base_url": "https://example.com/files",
            "create_dirs": true
        }
    
    Note:
        base_path 支持环境变量和用户目录展开：
        - ${HOME}/uploads -> /home/user/uploads
        - ~/uploads -> /home/user/uploads
    """
    
    type: Literal['local'] = 'local'
    base_path: str = Field(..., description="存储根目录")
    base_url: Optional[str] = Field(None, description="访问URL前缀")
    create_dirs: bool = Field(default=True, description="是否自动创建目录")
    permissions: int = Field(default=0o644, description="文件权限")
    dir_permissions: int = Field(default=0o755, description="目录权限")
    
    @field_validator('base_path')
    @classmethod
    def validate_base_path(cls, v: str) -> str:
        # 解析环境变量
        v = resolve_env_var(v)
        # 展开用户目录
        v = os.path.expandvars(v)
        v = os.path.expanduser(v)
        
        # 检查是否为绝对路径
        if not os.path.isabs(v):
            raise ValueError(f"base_path 必须是绝对路径: {v}")
        
        return v
    
    @model_validator(mode='after')
    def validate_path_accessibility(self) -> 'LocalStorageConfig':
        """验证路径可访问性"""
        path = self.base_path
        create_dirs = self.create_dirs
        
        if os.path.exists(path):
            if not os.access(path, os.W_OK):
                raise ValueError(f"目录不可写: {path}")
        elif not create_dirs:
            raise ValueError(f"目录不存在且 create_dirs=False: {path}")
        
        return self


class OSSStorageConfig(BaseStorageConfig):
    """阿里云 OSS 配置
    
    Example:
        {
            "type": "oss",
            "access_key_id": "${OSS_ACCESS_KEY_ID}",
            "access_key_secret": "${OSS_ACCESS_KEY_SECRET}",
            "endpoint": "oss-cn-hangzhou.aliyuncs.com",
            "bucket_name": "my-bucket",
            "prefix": "uploads/"
        }
    
    Note:
        access_key_id 和 access_key_secret 支持环境变量引用。
    """
    
    type: Literal['oss'] = 'oss'
    access_key_id: str = Field(..., min_length=1)
    access_key_secret: str = Field(..., min_length=1)
    endpoint: str = Field(..., description="OSS 端点")
    bucket_name: str = Field(..., min_length=1, max_length=63)
    prefix: str = Field(default="", description="存储前缀")
    internal_endpoint: Optional[str] = Field(None, description="内网端点")
    connect_timeout: int = Field(default=30, gt=0, description="连接超时（秒）")
    
    @field_validator('access_key_id', 'access_key_secret', mode='before')
    @classmethod
    def resolve_credentials(cls, v: str) -> str:
        """解析凭证（支持环境变量）"""
        return resolve_env_var(v)
    
    @field_validator('endpoint')
    @classmethod
    def validate_endpoint(cls, v: str) -> str:
        """验证端点格式"""
        # 基本验证，允许更灵活的格式
        if not v or not isinstance(v, str):
            raise ValueError("endpoint 不能为空")
        return v


class S3StorageConfig(BaseStorageConfig):
    """AWS S3 / MinIO 配置
    
    Example:
        {
            "type": "s3",
            "access_key_id": "${AWS_ACCESS_KEY_ID}",
            "secret_access_key": "${AWS_SECRET_ACCESS_KEY}",
            "bucket_name": "my-bucket",
            "region": "us-east-1",
            "endpoint_url": null  # MinIO 时需要设置
        }
    """
    
    type: Literal['s3'] = 's3'
    access_key_id: str = Field(...)
    secret_access_key: str = Field(...)
    bucket_name: str = Field(...)
    region: str = Field(default='us-east-1')
    endpoint_url: Optional[str] = Field(None, description="自定义端点（MinIO）")
    prefix: str = Field(default="")
    
    @field_validator('access_key_id', 'secret_access_key', mode='before')
    @classmethod
    def resolve_credentials(cls, v: str) -> str:
        """解析凭证（支持环境变量）"""
        return resolve_env_var(v)


class SecureURLConfig(BaseModel):
    """安全URL配置
    
    Example:
        {
            "secret_key": "${STORAGE_SECRET_KEY}",
            "base_url": "/api/files",
            "token_store": "redis",
            "redis_url": "redis://localhost:6379/0"
        }
    """
    
    secret_key: str = Field(..., min_length=32, description="签名密钥（至少32字符）")
    base_url: str = Field(default="/api/files", description="URL前缀")
    token_store: Literal['memory', 'redis'] = Field(default='memory', description="Token存储类型")
    redis_url: Optional[str] = Field(None, description="Redis连接URL")
    default_expires: int = Field(default=3600, gt=0, description="默认过期时间（秒）")
    max_expires: int = Field(default=86400 * 7, gt=0, description="最大过期时间（秒）")
    
    model_config = {
        'extra': 'forbid',
    }
    
    @field_validator('secret_key', mode='before')
    @classmethod
    def resolve_secret_key(cls, v: str) -> str:
        """解析密钥（支持环境变量）"""
        return resolve_env_var(v)
    
    @model_validator(mode='after')
    def validate_redis_config(self) -> 'SecureURLConfig':
        """验证 Redis 配置"""
        if self.token_store == 'redis' and not self.redis_url:
            raise ValueError("使用 Redis Token存储时必须配置 redis_url")
        return self


# 后端配置类型联合
BackendConfig = Union[
    MemoryStorageConfig,
    LocalStorageConfig,
    OSSStorageConfig,
    S3StorageConfig,
]

# 后端类型到配置类的映射
BACKEND_CONFIG_CLASSES: Dict[str, type] = {
    'memory': MemoryStorageConfig,
    'local': LocalStorageConfig,
    'oss': OSSStorageConfig,
    's3': S3StorageConfig,
}


class StorageConfig(BaseModel):
    """完整存储配置
    
    Example:
        {
            "backends": {
                "local": {
                    "type": "local",
                    "base_path": "/data/uploads"
                },
                "temp": {
                    "type": "memory",
                    "max_size": 52428800
                }
            },
            "default": "local",
            "secure_url": {
                "secret_key": "your-secret-key-at-least-32-characters",
                "base_url": "/api/files"
            }
        }
    
    Note:
        - backends: 后端配置字典，键为后端名称
        - default: 默认后端名称，不指定则使用第一个
        - secure_url: 安全URL配置（可选）
    """
    
    backends: Dict[str, Any] = Field(default_factory=dict, description="后端配置")
    default: Optional[str] = Field(None, description="默认后端名称")
    secure_url: Optional[SecureURLConfig] = Field(None, description="安全URL配置")
    
    model_config = {
        'extra': 'forbid',
    }
    
    @field_validator('backends', mode='before')
    @classmethod
    def validate_backends(cls, v: Dict[str, Any]) -> Dict[str, BackendConfig]:
        """验证各后端配置"""
        if not v:
            return {}
        
        validated = {}
        for name, config in v.items():
            if not isinstance(config, dict):
                raise ValueError(f"后端 '{name}' 配置必须是字典")
            
            backend_type = config.get('type')
            if not backend_type:
                raise ValueError(f"后端 '{name}' 未指定 type")
            
            if backend_type not in BACKEND_CONFIG_CLASSES:
                available = list(BACKEND_CONFIG_CLASSES.keys())
                raise ValueError(
                    f"未知的存储后端类型: {backend_type}，可用类型: {available}"
                )
            
            config_class = BACKEND_CONFIG_CLASSES[backend_type]
            try:
                validated[name] = config_class(**config)
            except Exception as e:
                raise ValueError(f"后端 '{name}' 配置错误: {e}")
        
        return validated
    
    @model_validator(mode='after')
    def validate_default_backend(self) -> 'StorageConfig':
        """验证默认后端"""
        if self.default and self.default not in self.backends:
            raise ValueError(f"默认后端 '{self.default}' 未在 backends 中定义")
        
        # 如果未指定默认后端，使用第一个
        if not self.default and self.backends:
            self.default = next(iter(self.backends))
        
        return self
    
    def to_manager_config(self) -> Dict[str, Any]:
        """转换为 StorageManager.configure() 所需的格式
        
        Returns:
            Dict[str, Any]: 可传递给 StorageManager.configure() 的配置
        """
        config = {
            'backends': {},
            'default': self.default,
        }
        
        for name, backend_config in self.backends.items():
            # 转换为字典，排除默认值
            config['backends'][name] = backend_config.model_dump(exclude_defaults=False)
        
        return config


def validate_config(config_dict: Dict[str, Any]) -> StorageConfig:
    """验证配置字典
    
    Args:
        config_dict: 配置字典
        
    Returns:
        StorageConfig: 验证后的配置对象
        
    Raises:
        ValueError: 配置验证失败
        
    Example:
        config = validate_config({
            'backends': {
                'local': {'type': 'local', 'base_path': '/data'}
            }
        })
    """
    return StorageConfig(**config_dict)


__all__ = [
    # 配置类
    'BaseStorageConfig',
    'MemoryStorageConfig',
    'LocalStorageConfig',
    'OSSStorageConfig',
    'S3StorageConfig',
    'SecureURLConfig',
    'StorageConfig',
    # 工具函数
    'validate_config',
    'resolve_env_var',
    # 常量
    'BACKEND_CONFIG_CLASSES',
]
