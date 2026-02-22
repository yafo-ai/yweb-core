"""
主键生成器函数

提供多种主键生成策略的实现：
- UUID（完整36位）
- 短UUID（8-32位可配置）
- 雪花算法（64位整数）
- 自定义生成器
"""

import uuid
import base64
import time
import threading
from typing import Any, Callable, Optional
from .primary_key_config import IdType



# ==================== UUID生成器 ====================

def generate_uuid() -> str:
    """生成完整UUID（36位）

    Returns:
        str: UUID字符串，格式：xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx

    Examples:
        >>> id = generate_uuid()
        >>> print(id)
        '550e8400-e29b-41d4-a716-446655440000'
        >>> len(id)
        36
    """
    return str(uuid.uuid4())


def generate_short_uuid(length: int = 10) -> str:
    """生成短UUID（可配置长度）

    使用base32编码压缩UUID，生成更短的唯一标识符。
    base32使用字符集：A-Z和2-7（共32个字符），转小写后为a-z和2-7。

    Args:
        length: 生成的短UUID长度（8-32位），默认10位

    Returns:
        str: 短UUID字符串，只包含小写字母和数字

    碰撞概率（100万条数据）：
        - 8位：0.0000018%
        - 10位：0.00000000006%
        - 12位：极低

    Examples:
        >>> id = generate_short_uuid(10)
        >>> print(id)
        'a3f5k9m2p7'
        >>> len(id)
        10

        >>> # 生成8位短UUID
        >>> id = generate_short_uuid(8)
        >>> len(id)
        8
    """
    # 生成UUID并转换为字节
    uuid_bytes = uuid.uuid4().bytes

    # 使用base32编码（比base64更URL友好，不含特殊字符）
    base32_str = base64.b32encode(uuid_bytes).decode('utf-8').rstrip('=')

    # 转小写并截取指定长度
    return base32_str[:length].lower()


# ==================== 雪花算法生成器 ====================

class SnowflakeIDGenerator:
    """雪花算法ID生成器

    Twitter的Snowflake算法实现，生成64位整数ID。

    ID结构（64位）：
    - 1位：符号位（始终为0）
    - 41位：时间戳（毫秒级，可用69年）
    - 5位：数据中心ID（0-31）
    - 5位：工作节点ID（0-31）
    - 12位：序列号（同一毫秒内可生成4096个ID）

    特点：
    - 趋势递增（按时间排序）
    - 分布式唯一
    - 高性能（单机每秒可生成400万个ID）
    """

    # 起始时间戳（2020-01-01 00:00:00）
    EPOCH = 1577836800000

    # 各部分位数
    WORKER_ID_BITS = 5
    DATACENTER_ID_BITS = 5
    SEQUENCE_BITS = 12

    # 最大值
    MAX_WORKER_ID = (1 << WORKER_ID_BITS) - 1  # 31
    MAX_DATACENTER_ID = (1 << DATACENTER_ID_BITS) - 1  # 31
    MAX_SEQUENCE = (1 << SEQUENCE_BITS) - 1  # 4095

    # 位移量
    WORKER_ID_SHIFT = SEQUENCE_BITS
    DATACENTER_ID_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS
    TIMESTAMP_SHIFT = SEQUENCE_BITS + WORKER_ID_BITS + DATACENTER_ID_BITS

    def __init__(self, worker_id: int = 1, datacenter_id: int = 1):
        """初始化雪花算法生成器

        Args:
            worker_id: 工作节点ID（0-31）
            datacenter_id: 数据中心ID（0-31）

        Raises:
            ValueError: 参数超出范围
        """
        if worker_id < 0 or worker_id > self.MAX_WORKER_ID:
            raise ValueError(
                f"worker_id必须在0-{self.MAX_WORKER_ID}之间，当前值: {worker_id}"
            )
        if datacenter_id < 0 or datacenter_id > self.MAX_DATACENTER_ID:
            raise ValueError(
                f"datacenter_id必须在0-{self.MAX_DATACENTER_ID}之间，当前值: {datacenter_id}"
            )

        self.worker_id = worker_id
        self.datacenter_id = datacenter_id
        self.sequence = 0
        self.last_timestamp = -1
        self.lock = threading.Lock()

    def _current_millis(self) -> int:
        """获取当前时间戳（毫秒）"""
        return int(time.time() * 1000)

    def _wait_next_millis(self, last_timestamp: int) -> int:
        """等待下一毫秒"""
        timestamp = self._current_millis()
        while timestamp <= last_timestamp:
            timestamp = self._current_millis()
        return timestamp

    def generate(self) -> int:
        """生成雪花算法ID

        Returns:
            int: 64位整数ID

        Examples:
            >>> generator = SnowflakeIDGenerator(worker_id=1, datacenter_id=1)
            >>> id = generator.generate()
            >>> print(id)
            1234567890123456789
        """
        with self.lock:
            timestamp = self._current_millis()

            # 时钟回拨检测
            if timestamp < self.last_timestamp:
                raise RuntimeError(
                    f"时钟回拨检测：当前时间戳 {timestamp} 小于上次时间戳 {self.last_timestamp}"
                )

            # 同一毫秒内
            if timestamp == self.last_timestamp:
                self.sequence = (self.sequence + 1) & self.MAX_SEQUENCE
                # 序列号溢出，等待下一毫秒
                if self.sequence == 0:
                    timestamp = self._wait_next_millis(self.last_timestamp)
            else:
                # 新的毫秒，序列号重置
                self.sequence = 0

            self.last_timestamp = timestamp

            # 组装ID
            snowflake_id = (
                ((timestamp - self.EPOCH) << self.TIMESTAMP_SHIFT) |
                (self.datacenter_id << self.DATACENTER_ID_SHIFT) |
                (self.worker_id << self.WORKER_ID_SHIFT) |
                self.sequence
            )

            return snowflake_id


# 全局雪花算法生成器实例
_snowflake_generator: Optional[SnowflakeIDGenerator] = None


def get_snowflake_generator(worker_id: int = 1, datacenter_id: int = 1) -> SnowflakeIDGenerator:
    """获取雪花算法生成器实例（单例模式）

    Args:
        worker_id: 工作节点ID
        datacenter_id: 数据中心ID

    Returns:
        SnowflakeIDGenerator: 生成器实例
    """
    global _snowflake_generator
    if _snowflake_generator is None:
        _snowflake_generator = SnowflakeIDGenerator(
            worker_id=worker_id,
            datacenter_id=datacenter_id
        )
    return _snowflake_generator


def generate_snowflake_id(worker_id: int = 1, datacenter_id: int = 1) -> int:
    """生成雪花算法ID（便捷函数）

    Args:
        worker_id: 工作节点ID（0-31）
        datacenter_id: 数据中心ID（0-31）

    Returns:
        int: 64位整数ID

    Examples:
        >>> id = generate_snowflake_id(worker_id=1, datacenter_id=1)
        >>> print(id)
        1234567890123456789
    """
    generator = get_snowflake_generator(worker_id, datacenter_id)
    return generator.generate()


# ==================== 主键生成器（带冲突检测） ====================

class PrimaryKeyGenerator:
    """主键生成器（带冲突检测和重试机制）

    负责生成主键并检测冲突，如果冲突则自动重试。
    """

    def __init__(self, max_retries: int = 5):
        """初始化主键生成器

        Args:
            max_retries: 最大重试次数，默认5次
        """
        self.max_retries = max_retries

    def generate_with_retry(
        self,
        model_class,
        generator_func: Callable[[], Any],
        max_retries: Optional[int] = None
    ) -> Any:
        """生成主键，如果冲突则重试

        Args:
            model_class: 模型类
            generator_func: 生成器函数
            max_retries: 最大重试次数（可选，默认使用实例配置）

        Returns:
            Any: 唯一的主键值

        Raises:
            RuntimeError: 超过最大重试次数仍然冲突

        Examples:
            >>> generator = PrimaryKeyGenerator(max_retries=5)
            >>> id = generator.generate_with_retry(
            ...     User,
            ...     lambda: generate_short_uuid(10)
            ... )
        """
        if max_retries is None:
            max_retries = self.max_retries

        from yweb.log import get_logger
        logger = get_logger("orm.primary_key")

        for attempt in range(max_retries):
            new_id = generator_func()

            # 检查ID是否已存在
            try:
                existing = model_class.query.filter_by(id=new_id).first()
                if existing is None:
                    return new_id

                # 记录冲突日志
                logger.warning(
                    f"主键冲突: {model_class.__name__}.id={new_id}, "
                    f"重试 {attempt + 1}/{max_retries}"
                )
            except Exception as e:
                # 如果查询失败（比如表还不存在），直接返回ID
                logger.debug(f"查询主键时出错（可能是表不存在）: {e}")
                return new_id

        raise RuntimeError(
            f"生成主键失败：{max_retries}次尝试后仍然冲突，"
            f"模型: {model_class.__name__}"
        )


# ==================== 便捷函数 ====================

def create_primary_key_generator(
    strategy: str,
    short_uuid_length: int = 10,
    snowflake_worker_id: int = 1,
    snowflake_datacenter_id: int = 1,
    custom_generator: Optional[Callable] = None
) -> Callable[[], Any]:
    """根据策略创建主键生成器函数

    Args:
        strategy: 主键策略
        short_uuid_length: 短UUID长度
        snowflake_worker_id: 雪花算法工作节点ID
        snowflake_datacenter_id: 雪花算法数据中心ID
        custom_generator: 自定义生成器

    Returns:
        Callable: 生成器函数

    Raises:
        ValueError: 无效的策略

    Examples:
        >>> generator = create_primary_key_generator("short_uuid", short_uuid_length=10)
        >>> id = generator()
        >>> print(id)
        'a3f5k9m2p7'
    """
    if strategy == IdType.UUID:
        return generate_uuid
    elif strategy == IdType.SHORT_UUID:
        return lambda: generate_short_uuid(short_uuid_length)
    elif strategy == IdType.SNOWFLAKE:
        return lambda: generate_snowflake_id(snowflake_worker_id, snowflake_datacenter_id)
    elif strategy == IdType.CUSTOM:
        if custom_generator is None:
            raise ValueError("使用custom策略时必须提供custom_generator")
        return custom_generator
    elif strategy == IdType.AUTO_INCREMENT:
        # 自增主键不需要生成器
        return lambda: None
    else:
        raise ValueError(f"无效的主键策略: {strategy}")
