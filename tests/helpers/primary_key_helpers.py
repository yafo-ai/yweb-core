"""主键配置测试辅助工具

提供测试专用的主键配置辅助函数
"""

from yweb.orm import PrimaryKeyConfig, IdType


def get_primary_key_strategy(config: type[PrimaryKeyConfig] = PrimaryKeyConfig) -> IdType:
    """获取当前主键策略
    
    Args:
        config: PrimaryKeyConfig 类
        
    Returns:
        IdType: 当前策略
    """
    return config._strategy


def get_short_uuid_length(config: type[PrimaryKeyConfig] = PrimaryKeyConfig) -> int:
    """获取短UUID长度
    
    Args:
        config: PrimaryKeyConfig 类
        
    Returns:
        int: 短UUID长度
    """
    return config._short_uuid_length


def get_max_retries(config: type[PrimaryKeyConfig] = PrimaryKeyConfig) -> int:
    """获取最大重试次数
    
    Args:
        config: PrimaryKeyConfig 类
        
    Returns:
        int: 最大重试次数
    """
    return config._max_retries


def set_max_retries(config: type[PrimaryKeyConfig], max_retries: int) -> None:
    """设置最大重试次数
    
    Args:
        config: PrimaryKeyConfig 类
        max_retries: 最大重试次数
        
    警告：此函数仅用于测试环境，不应在生产代码中使用
    """
    if max_retries < 0:
        raise ValueError(f"max_retries必须大于等于0，当前值: {max_retries}")
    config._max_retries = max_retries
