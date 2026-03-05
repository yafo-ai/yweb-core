"""
主键策略全局配置管理

提供全局配置接口，用于设置和获取主键生成策略。
"""

from typing import Optional, Callable
from enum import Enum


class IdType(Enum):
    """主键类型枚举"""
    AUTO_INCREMENT = "auto_increment"  # 自增ID
    SNOWFLAKE = "snowflake"  # 雪花ID
    UUID = "uuid"  # UUID
    SHORT_UUID = "short_uuid"  # 短UUID
    CUSTOM = "custom"  # 自定义生成器

    def __str__(self) -> str:
        """返回字符串表示"""
        return self.value

    def __repr__(self) -> str:
        """返回对象表示"""
        return f"IdType.{self.name}"


class PrimaryKeyConfig:
    """主键策略全局配置类

    使用类变量存储全局配置，支持以下策略：
    - auto_increment: 整数自增（默认）
    - uuid: 完整UUID（36位）
    - short_uuid: 短UUID（8-32位可配置）
    - snowflake: 雪花算法（64位整数）
    - custom: 自定义生成器
    """
    # 默认主键类型
    id_type: IdType = IdType.AUTO_INCREMENT

    # 全局配置变量
    _strategy: IdType = IdType.AUTO_INCREMENT
    _short_uuid_length: int = 10
    _snowflake_worker_id: int = 1
    _snowflake_datacenter_id: int = 1
    _custom_generator: Optional[Callable] = None
    _max_retries: int = 5

    @classmethod
    def configure(
        cls,
        strategy: IdType = IdType.AUTO_INCREMENT,
        short_uuid_length: int = 10,
        snowflake_worker_id: int = 1,
        snowflake_datacenter_id: int = 1,
        custom_generator: Optional[Callable] = None,
        max_retries: int = 5
    ):
        """配置全局主键策略

        Args:
            strategy: 主键策略，可选值：
                - IdType.AUTO_INCREMENT: 整数自增（默认）
                - IdType.UUID: 完整UUID（36位）
                - IdType.SHORT_UUID: 短UUID（可配置长度）
                - IdType.SNOWFLAKE: 雪花算法
                - IdType.CUSTOM: 自定义生成器
            short_uuid_length: 短UUID长度（8-32位），默认10位
            snowflake_worker_id: 雪花算法工作节点ID（0-31）
            snowflake_datacenter_id: 雪花算法数据中心ID（0-31）
            custom_generator: 自定义主键生成器函数
            max_retries: ID冲突最大重试次数，默认5次

        Raises:
            ValueError: 参数验证失败

        Examples:
            >>> # 配置短UUID
            >>> configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=10)

            >>> # 配置雪花算法
            >>> configure_primary_key(
            ...     strategy=IdType.SNOWFLAKE,
            ...     snowflake_worker_id=1,
            ...     snowflake_datacenter_id=1
            ... )

            >>> # 配置自定义生成器
            >>> def my_generator():
            ...     return "custom_id"
            >>> configure_primary_key(strategy=IdType.CUSTOM, custom_generator=my_generator)
        """

        # 验证短UUID长度
        if strategy == IdType.SHORT_UUID:
            if not (8 <= short_uuid_length <= 32):
                raise ValueError(
                    f"短UUID长度必须在8-32之间，当前值: {short_uuid_length}"
                )

        # 验证雪花算法参数
        if strategy == IdType.SNOWFLAKE:
            if not (0 <= snowflake_worker_id <= 31):
                raise ValueError(
                    f"雪花算法工作节点ID必须在0-31之间，当前值: {snowflake_worker_id}"
                )
            if not (0 <= snowflake_datacenter_id <= 31):
                raise ValueError(
                    f"雪花算法数据中心ID必须在0-31之间，当前值: {snowflake_datacenter_id}"
                )

        # 验证自定义生成器
        if strategy == IdType.CUSTOM:
            if custom_generator is None:
                raise ValueError("使用custom策略时必须提供custom_generator参数")
            if not callable(custom_generator):
                raise ValueError("custom_generator必须是可调用对象")

        # 验证重试次数
        if max_retries < 1:
            raise ValueError(f"max_retries必须大于0，当前值: {max_retries}")

        # 设置配置
        cls._strategy = strategy
        cls._short_uuid_length = short_uuid_length
        cls._snowflake_worker_id = snowflake_worker_id
        cls._snowflake_datacenter_id = snowflake_datacenter_id
        cls._custom_generator = custom_generator
        cls._max_retries = max_retries

    @classmethod
    def get_strategy(cls) -> IdType:
        """获取当前主键策略"""
        return cls._strategy

    @classmethod
    def get_short_uuid_length(cls) -> int:
        """获取短UUID长度"""
        return cls._short_uuid_length

    @classmethod
    def get_snowflake_worker_id(cls) -> int:
        """获取雪花算法工作节点ID"""
        return cls._snowflake_worker_id

    @classmethod
    def get_snowflake_datacenter_id(cls) -> int:
        """获取雪花算法数据中心ID"""
        return cls._snowflake_datacenter_id

    @classmethod
    def get_custom_generator(cls) -> Optional[Callable]:
        """获取自定义生成器"""
        return cls._custom_generator

    @classmethod
    def get_max_retries(cls) -> int:
        """获取最大重试次数"""
        return cls._max_retries

    @classmethod
    def reset(cls):
        """重置为默认配置（主要用于测试）"""
        cls._strategy = IdType.AUTO_INCREMENT
        cls._short_uuid_length = 10
        cls._snowflake_worker_id = 1
        cls._snowflake_datacenter_id = 1
        cls._custom_generator = None
        cls._max_retries = 5


def configure_primary_key(
    strategy: IdType = IdType.AUTO_INCREMENT,
    short_uuid_length: int = 10,
    snowflake_worker_id: int = 1,
    snowflake_datacenter_id: int = 1,
    custom_generator: Optional[Callable] = None,
    max_retries: int = 5
):
    """配置全局主键策略（便捷函数）

    这是 PrimaryKeyConfig.configure() 的便捷封装。

    Args:
        strategy: 主键策略（IdType枚举）
        short_uuid_length: 短UUID长度
        snowflake_worker_id: 雪花算法工作节点ID
        snowflake_datacenter_id: 雪花算法数据中心ID
        custom_generator: 自定义生成器
        max_retries: 最大重试次数

    Examples:
        >>> from yweb.orm import configure_primary_key, IdType
        >>> configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=10)
    """
    PrimaryKeyConfig.configure(
        strategy=strategy,
        short_uuid_length=short_uuid_length,
        snowflake_worker_id=snowflake_worker_id,
        snowflake_datacenter_id=snowflake_datacenter_id,
        custom_generator=custom_generator,
        max_retries=max_retries
    )


def get_primary_key_config() -> PrimaryKeyConfig:
    """获取主键配置对象（便捷函数）

    Returns:
        PrimaryKeyConfig: 配置对象

    Examples:
        >>> config = get_primary_key_config()
        >>> print(config.get_strategy())
        IdType.AUTO_INCREMENT
    """
    return PrimaryKeyConfig
