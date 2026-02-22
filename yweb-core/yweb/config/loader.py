"""配置加载器模块

提供从 YAML 文件加载配置的功能。

使用示例:
    from yweb.config import ConfigLoader
    
    # 加载配置
    config = ConfigLoader.load("config/settings.yaml")
    
    # 重新加载
    config = ConfigLoader.reload("config/settings.yaml")
    
    # 使用 Pydantic Settings
    from yweb.config import load_yaml_config
    
    class MySettings(BaseSettings):
        database_url: str
        debug: bool = False
    
    settings = load_yaml_config("config/settings.yaml", MySettings)
"""

import os
from typing import Dict, Any, Optional, Type, TypeVar
from pathlib import Path

# 尝试导入 yaml
try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

# 尝试导入 pydantic
try:
    from pydantic import BaseModel
    from pydantic_settings import BaseSettings
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False
    BaseSettings = object


T = TypeVar("T")


class ConfigLoader:
    """配置加载器
    
    从 YAML 文件加载配置，支持单例模式和配置缓存。
    
    使用示例:
        # 加载配置文件
        config = ConfigLoader.load("config/settings.yaml")
        
        # 获取配置值
        db_url = config.get("database", {}).get("url")
        
        # 重新加载配置
        config = ConfigLoader.reload("config/settings.yaml")
        
        # 清除缓存
        ConfigLoader.clear_cache()
    """
    
    _cache: Dict[str, Dict[str, Any]] = {}
    
    @classmethod
    def load(
        cls,
        config_path: str,
        base_dir: Optional[str] = None,
        use_cache: bool = True
    ) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径（相对或绝对路径）
            base_dir: 基础目录，用于解析相对路径
            use_cache: 是否使用缓存
            
        Returns:
            配置字典
            
        Raises:
            ImportError: 未安装 PyYAML
            FileNotFoundError: 配置文件不存在
            yaml.YAMLError: YAML 解析错误
        """
        if not YAML_AVAILABLE:
            raise ImportError(
                "PyYAML 未安装。请运行: pip install pyyaml"
            )
        
        # 解析配置文件路径
        if os.path.isabs(config_path):
            abs_path = config_path
        elif base_dir:
            abs_path = os.path.join(base_dir, config_path)
        else:
            # 尝试从当前工作目录解析
            abs_path = os.path.abspath(config_path)
        
        # 检查缓存
        if use_cache and abs_path in cls._cache:
            return cls._cache[abs_path]
        
        # 检查文件是否存在
        if not os.path.exists(abs_path):
            raise FileNotFoundError(f"配置文件不存在: {abs_path}")
        
        # 加载配置
        with open(abs_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        
        # 缓存配置
        if use_cache:
            cls._cache[abs_path] = config
        
        return config
    
    @classmethod
    def reload(cls, config_path: str, base_dir: Optional[str] = None) -> Dict[str, Any]:
        """重新加载配置文件（忽略缓存）
        
        Args:
            config_path: 配置文件路径
            base_dir: 基础目录
            
        Returns:
            配置字典
        """
        # 解析路径并清除对应缓存
        if os.path.isabs(config_path):
            abs_path = config_path
        elif base_dir:
            abs_path = os.path.join(base_dir, config_path)
        else:
            abs_path = os.path.abspath(config_path)
        
        if abs_path in cls._cache:
            del cls._cache[abs_path]
        
        return cls.load(config_path, base_dir, use_cache=True)
    
    @classmethod
    def clear_cache(cls):
        """清除所有配置缓存"""
        cls._cache.clear()
    
    @classmethod
    def get_cached_paths(cls) -> list:
        """获取所有已缓存的配置文件路径"""
        return list(cls._cache.keys())


def load_yaml_config(
    config_path: str,
    settings_class: Type[T],
    base_dir: Optional[str] = None,
    **overrides
) -> T:
    """加载 YAML 配置并创建 Pydantic Settings 实例
    
    Args:
        config_path: 配置文件路径
        settings_class: Pydantic Settings 类
        base_dir: 基础目录
        **overrides: 覆盖配置的参数
        
    Returns:
        Settings 实例
    
    使用示例:
        class MySettings(BaseSettings):
            database_url: str
            debug: bool = False
        
        settings = load_yaml_config(
            "config/settings.yaml",
            MySettings,
            debug=True  # 覆盖配置
        )
    """
    if not PYDANTIC_AVAILABLE:
        raise ImportError(
            "pydantic 未安装。请运行: pip install pydantic pydantic-settings"
        )
    
    # 加载 YAML 配置
    config = ConfigLoader.load(config_path, base_dir)
    
    # 合并覆盖参数
    config.update(overrides)
    
    # 创建 Settings 实例
    return settings_class(**config)


def load_env_file(env_path: str = ".env") -> Dict[str, str]:
    """加载 .env 文件
    
    简单的 .env 文件解析器，不依赖 python-dotenv。
    
    Args:
        env_path: .env 文件路径
        
    Returns:
        环境变量字典
    """
    env_vars = {}
    
    if not os.path.exists(env_path):
        return env_vars
    
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            
            # 跳过空行和注释
            if not line or line.startswith("#"):
                continue
            
            # 解析键值对
            if "=" in line:
                key, value = line.split("=", 1)
                key = key.strip()
                value = value.strip()
                
                # 移除引号
                if value and value[0] in ('"', "'") and value[-1] == value[0]:
                    value = value[1:-1]
                
                env_vars[key] = value
    
    return env_vars


def set_env_from_file(env_path: str = ".env", override: bool = False):
    """从 .env 文件设置环境变量
    
    Args:
        env_path: .env 文件路径
        override: 是否覆盖已存在的环境变量
    """
    env_vars = load_env_file(env_path)
    
    for key, value in env_vars.items():
        if override or key not in os.environ:
            os.environ[key] = value


class ConfigManager:
    """配置管理器
    
    管理多个配置文件和环境。
    
    使用示例:
        manager = ConfigManager(base_dir="config")
        
        # 加载主配置
        manager.load("settings.yaml")
        
        # 加载环境特定配置
        manager.load("settings.dev.yaml", merge=True)
        
        # 获取配置值
        db_url = manager.get("database.url")
    """
    
    def __init__(self, base_dir: str = None):
        self.base_dir = base_dir or os.getcwd()
        self._config: Dict[str, Any] = {}
    
    def load(self, config_path: str, merge: bool = False) -> Dict[str, Any]:
        """加载配置文件
        
        Args:
            config_path: 配置文件路径
            merge: 是否合并到现有配置
            
        Returns:
            配置字典
        """
        config = ConfigLoader.load(config_path, self.base_dir)
        
        if merge:
            self._deep_merge(self._config, config)
        else:
            self._config = config
        
        return self._config
    
    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔的路径）
        
        Args:
            key: 配置键，支持 "database.url" 格式
            default: 默认值
            
        Returns:
            配置值
        """
        keys = key.split(".")
        value = self._config
        
        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default
        
        return value
    
    def set(self, key: str, value: Any):
        """设置配置值（支持点号分隔的路径）
        
        Args:
            key: 配置键
            value: 配置值
        """
        keys = key.split(".")
        config = self._config
        
        for k in keys[:-1]:
            if k not in config:
                config[k] = {}
            config = config[k]
        
        config[keys[-1]] = value
    
    def to_dict(self) -> Dict[str, Any]:
        """返回完整配置字典"""
        return self._config.copy()
    
    def _deep_merge(self, base: dict, update: dict):
        """深度合并字典"""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_merge(base[key], value)
            else:
                base[key] = value

