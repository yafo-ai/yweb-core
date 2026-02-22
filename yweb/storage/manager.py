# -*- coding: utf-8 -*-
"""
存储管理器

管理多个存储后端实例，提供统一的访问入口。
支持：
- 多后端注册与切换
- 配置文件初始化
- 默认后端设置
"""

import logging
from typing import Dict, Optional, Type, Any, List

from .base import StorageBackend
from .exceptions import StorageNotFoundError, StorageConfigError

logger = logging.getLogger(__name__)


class StorageManager:
    """存储管理器
    
    管理多个存储后端实例，提供统一的访问入口。
    使用类方法实现单例模式，全局共享配置。
    
    Example:
        # 方式1：手动注册
        StorageManager.register('local', LocalStorage('/data/uploads'))
        StorageManager.register('oss', OSSStorage(...), default=True)
        
        # 方式2：配置文件初始化
        StorageManager.configure({
            'backends': {
                'local': {'type': 'local', 'base_path': '/data/uploads'},
                'oss': {'type': 'oss', 'access_key_id': '...', ...},
            },
            'default': 'oss'
        })
        
        # 使用
        storage = StorageManager.get()  # 获取默认后端
        storage = StorageManager.get('local')  # 获取指定后端
        
        # 列出所有后端
        backends = StorageManager.list_backends()
        # -> {'local': 'LocalStorage', 'oss': 'OSSStorage'}
    
    Note:
        - 所有方法都是类方法，无需实例化
        - 配置是全局共享的，修改会影响所有使用者
        - 测试时可使用 reset() 方法重置配置
    """
    
    # 已注册的后端实例
    _backends: Dict[str, StorageBackend] = {}
    # 默认后端名称
    _default: Optional[str] = None
    # 已注册的后端类（用于配置文件初始化）
    _backend_classes: Dict[str, Type[StorageBackend]] = {}
    # 是否已初始化默认后端类
    _classes_initialized: bool = False
    
    # ==================== 注册与获取 ====================
    
    @classmethod
    def register(
        cls,
        name: str,
        backend: StorageBackend,
        default: bool = False,
    ) -> None:
        """注册存储后端
        
        Args:
            name: 后端名称，用于后续获取
            backend: 后端实例
            default: 是否设为默认后端
            
        Example:
            StorageManager.register('local', LocalStorage('/data'))
            StorageManager.register('temp', MemoryStorage(), default=True)
        """
        cls._backends[name] = backend
        
        # 设置默认后端
        if default or cls._default is None:
            cls._default = name
        
        logger.info(f"注册存储后端: {name} ({backend.__class__.__name__})")
    
    @classmethod
    def unregister(cls, name: str) -> bool:
        """注销存储后端
        
        Args:
            name: 后端名称
            
        Returns:
            bool: 是否注销成功（不存在返回 False）
        """
        if name not in cls._backends:
            return False
        
        del cls._backends[name]
        
        # 如果注销的是默认后端，选择新的默认后端
        if cls._default == name:
            cls._default = next(iter(cls._backends), None)
        
        logger.info(f"注销存储后端: {name}")
        return True
    
    @classmethod
    def get(cls, name: Optional[str] = None) -> StorageBackend:
        """获取存储后端
        
        Args:
            name: 后端名称，为空时返回默认后端
            
        Returns:
            StorageBackend: 存储后端实例
            
        Raises:
            StorageNotFoundError: 后端未注册
            
        Example:
            # 获取默认后端
            storage = StorageManager.get()
            
            # 获取指定后端
            storage = StorageManager.get('local')
        """
        target_name = name or cls._default
        
        if not target_name:
            raise StorageNotFoundError("default")
        
        if target_name not in cls._backends:
            raise StorageNotFoundError(target_name)
        
        return cls._backends[target_name]
    
    @classmethod
    def get_default_name(cls) -> Optional[str]:
        """获取默认后端名称
        
        Returns:
            Optional[str]: 默认后端名称，未设置返回 None
        """
        return cls._default
    
    @classmethod
    def set_default(cls, name: str) -> None:
        """设置默认后端
        
        Args:
            name: 后端名称
            
        Raises:
            StorageNotFoundError: 后端未注册
        """
        if name not in cls._backends:
            raise StorageNotFoundError(name)
        cls._default = name
        logger.info(f"设置默认存储后端: {name}")
    
    @classmethod
    def list_backends(cls) -> Dict[str, str]:
        """列出所有已注册的后端
        
        Returns:
            Dict[str, str]: 后端名称到类名的映射
            
        Example:
            backends = StorageManager.list_backends()
            # -> {'local': 'LocalStorage', 'oss': 'OSSStorage'}
        """
        return {
            name: backend.__class__.__name__
            for name, backend in cls._backends.items()
        }
    
    @classmethod
    def has_backend(cls, name: str) -> bool:
        """检查后端是否已注册
        
        Args:
            name: 后端名称
            
        Returns:
            bool: 是否已注册
        """
        return name in cls._backends
    
    # ==================== 配置初始化 ====================
    
    @classmethod
    def register_backend_class(
        cls,
        type_name: str,
        backend_class: Type[StorageBackend],
    ) -> None:
        """注册后端类（用于配置文件初始化）
        
        Args:
            type_name: 类型名称，用于配置中的 'type' 字段
            backend_class: 后端类
            
        Example:
            StorageManager.register_backend_class('custom', MyCustomStorage)
        """
        cls._backend_classes[type_name] = backend_class
        logger.debug(f"注册存储后端类: {type_name} -> {backend_class.__name__}")
    
    @classmethod
    def configure(cls, config: Dict[str, Any]) -> None:
        """从配置初始化所有后端
        
        Args:
            config: 配置字典
            
        配置格式:
            {
                'backends': {
                    'local': {
                        'type': 'local',
                        'base_path': '/data/uploads',
                        ...
                    },
                    'oss': {
                        'type': 'oss',
                        'access_key_id': '...',
                        ...
                    },
                },
                'default': 'oss'  # 可选，不指定则使用第一个
            }
            
        Raises:
            StorageConfigError: 配置错误
            
        Example:
            StorageManager.configure({
                'backends': {
                    'local': {'type': 'local', 'base_path': '/data'},
                    'temp': {'type': 'memory', 'max_size': 50*1024*1024},
                },
                'default': 'local'
            })
        """
        # 确保默认后端类已注册
        cls._register_default_backend_classes()
        
        # 复制配置，避免修改原对象
        config = dict(config)
        
        # 提取配置
        backends_config = config.get('backends', {})
        default_name = config.get('default')
        
        # 兼容旧格式（直接在顶层配置后端）
        if not backends_config:
            # 移除非后端配置项
            config.pop('default', None)
            backends_config = config
        
        if not backends_config:
            raise StorageConfigError("配置中未指定任何存储后端")
        
        # 初始化各后端
        for name, backend_config in backends_config.items():
            if not isinstance(backend_config, dict):
                continue
            
            backend_config = dict(backend_config)  # 复制
            type_name = backend_config.pop('type', None)
            
            if not type_name:
                raise StorageConfigError(f"后端 '{name}' 未指定 type")
            
            if type_name not in cls._backend_classes:
                raise StorageConfigError(
                    f"未知的存储后端类型: {type_name}，"
                    f"可用类型: {list(cls._backend_classes.keys())}"
                )
            
            try:
                backend_class = cls._backend_classes[type_name]
                backend = backend_class(**backend_config)
                
                # 是否设为默认
                is_default = (name == default_name) or (
                    default_name is None and not cls._backends
                )
                cls.register(name, backend, default=is_default)
                
            except TypeError as e:
                raise StorageConfigError(
                    f"初始化后端 '{name}' 失败: {e}"
                )
            except Exception as e:
                raise StorageConfigError(
                    f"初始化后端 '{name}' 时发生错误: {e}"
                )
        
        # 如果指定了默认后端，确保设置
        if default_name and default_name in cls._backends:
            cls._default = default_name
        
        logger.info(f"存储配置完成，共 {len(cls._backends)} 个后端，默认: {cls._default}")
    
    @classmethod
    def init_from_settings(cls, settings: 'StorageSettings') -> None:
        """从 StorageSettings 配置初始化存储管理器
        
        与 config 模块集成的推荐方式。
        
        Args:
            settings: StorageSettings 配置实例
            
        Example:
            from yweb.config import StorageSettings
            from yweb.storage import StorageManager
            
            # 方式1：从环境变量自动加载
            settings = StorageSettings()
            StorageManager.init_from_settings(settings)
            
            # 方式2：从 YAML 加载
            from yweb.config import ConfigLoader
            config = ConfigLoader.load("config/settings.yaml")
            settings = StorageSettings(**config.get('storage', {}))
            StorageManager.init_from_settings(settings)
            
            # 方式3：集成到应用启动（AppSettings 已内置 storage 配置）
            class MyAppSettings(AppSettings):
                pass
            
            app_settings = load_yaml_config("config/settings.yaml", MyAppSettings)
            StorageManager.init_from_settings(app_settings.storage)
        """
        from .backends.memory import MemoryStorage
        from .backends.local import LocalStorage
        
        # 本地存储
        if settings.local.enabled:
            try:
                local_storage = LocalStorage(
                    base_path=settings.local.base_path,
                    base_url=settings.local.base_url,
                    create_dirs=settings.local.create_dirs,
                )
                cls.register(
                    'local',
                    local_storage,
                    default=(settings.default == 'local'),
                )
            except Exception as e:
                logger.warning(f"初始化本地存储失败: {e}")
        
        # 内存存储
        if settings.memory.enabled:
            try:
                memory_storage = MemoryStorage(
                    max_size=settings.memory.parsed_max_size,
                    max_files=settings.memory.max_files,
                    auto_cleanup=settings.memory.auto_cleanup,
                )
                cls.register(
                    'memory',
                    memory_storage,
                    default=(settings.default == 'memory'),
                )
            except Exception as e:
                logger.warning(f"初始化内存存储失败: {e}")
        
        # OSS 存储
        if settings.oss.enabled:
            try:
                from .backends.oss import OSSStorage
                oss_storage = OSSStorage(
                    access_key_id=settings.oss.access_key_id,
                    access_key_secret=settings.oss.access_key_secret,
                    endpoint=settings.oss.endpoint,
                    bucket_name=settings.oss.bucket_name,
                    prefix=settings.oss.prefix,
                    internal_endpoint=settings.oss.internal_endpoint,
                )
                cls.register(
                    'oss',
                    oss_storage,
                    default=(settings.default == 'oss'),
                )
            except ImportError:
                logger.warning("OSS 存储需要安装 oss2: pip install oss2")
            except Exception as e:
                logger.warning(f"初始化 OSS 存储失败: {e}")
        
        # S3 存储
        if settings.s3.enabled:
            try:
                from .backends.s3 import S3Storage
                s3_storage = S3Storage(
                    access_key_id=settings.s3.access_key_id,
                    secret_access_key=settings.s3.secret_access_key,
                    bucket_name=settings.s3.bucket_name,
                    region=settings.s3.region,
                    endpoint_url=settings.s3.endpoint_url,
                    prefix=settings.s3.prefix,
                )
                cls.register(
                    's3',
                    s3_storage,
                    default=(settings.default == 's3'),
                )
            except ImportError:
                logger.warning("S3 存储需要安装 boto3: pip install boto3")
            except Exception as e:
                logger.warning(f"初始化 S3 存储失败: {e}")
        
        # 确保默认后端已设置
        if settings.default and cls.has_backend(settings.default):
            cls.set_default(settings.default)
        
        logger.info(
            f"从 StorageSettings 初始化完成，"
            f"共 {len(cls._backends)} 个后端，"
            f"默认: {cls._default}"
        )
    
    @classmethod
    def _register_default_backend_classes(cls) -> None:
        """注册默认后端类"""
        if cls._classes_initialized:
            return
        
        cls._classes_initialized = True
        
        # 始终可用的后端
        from .backends.memory import MemoryStorage
        from .backends.local import LocalStorage
        
        cls._backend_classes['memory'] = MemoryStorage
        cls._backend_classes['local'] = LocalStorage
        
        # 可选后端（需要额外依赖）
        # OSS
        try:
            from .backends.oss import OSSStorage
            cls._backend_classes['oss'] = OSSStorage
        except ImportError:
            pass
        
        # S3
        try:
            from .backends.s3 import S3Storage
            cls._backend_classes['s3'] = S3Storage
        except ImportError:
            pass
    
    # ==================== 工具方法 ====================
    
    @classmethod
    def reset(cls) -> None:
        """重置所有配置
        
        清除所有已注册的后端和默认设置。
        主要用于测试环境。
        """
        cls._backends.clear()
        cls._default = None
        logger.debug("存储管理器已重置")
    
    @classmethod
    def reset_all(cls) -> None:
        """完全重置，包括后端类注册
        
        主要用于测试环境的彻底重置。
        """
        cls._backends.clear()
        cls._default = None
        cls._backend_classes.clear()
        cls._classes_initialized = False
        logger.debug("存储管理器已完全重置")
    
    @classmethod
    def get_stats(cls) -> Dict[str, Any]:
        """获取所有后端的统计信息
        
        Returns:
            Dict[str, Any]: 各后端的统计信息
        """
        stats = {
            'default': cls._default,
            'backend_count': len(cls._backends),
            'backends': {},
        }
        
        for name, backend in cls._backends.items():
            backend_stats = {'type': backend.__class__.__name__}
            
            # 尝试获取后端特有的统计信息
            if hasattr(backend, 'get_stats'):
                try:
                    backend_stats.update(backend.get_stats())
                except Exception:
                    pass
            
            stats['backends'][name] = backend_stats
        
        return stats


__all__ = ["StorageManager"]
