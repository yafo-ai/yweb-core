"""ID模型基类

提供主键（ID）相关的功能：
- 动态主键类型定义（支持自增、UUID、短UUID、雪花ID、自定义）
- 主键生成策略配置
- 主键生成方法

使用说明：
    IdModel 是 CoreModel 的父类，专门负责 ID 相关的功能。
    一般情况下，用户应该使用 CoreModel 或 BaseModel，而不是直接使用 IdModel。
    
    如果你只需要 ID 功能而不需要 CoreModel 的其他功能（如时间戳、CRUD 等），
    可以直接继承 IdModel。

主要提供给sqlalchemy_history 自定义 Transaction 表使用：
 # 创建自定义 Transaction 类
    class AuditLog(IdModel, TransactionBase):
        #自定义审计日志表 - 替代默认的 transaction 表 
        __tablename__ = "audit_log"  # Transaction 表自定义表名
        # id会自动根据 IdModel的设置生成
        # 可以添加自定义字段
        remote_addr = mapped_column(String(50), comment="客户端IP")
        request_id = mapped_column(String(64), comment="请求ID")
        operation_reason = mapped_column(String(500), comment="操作原因")
    
    # 创建自定义 manager
    custom_manager = VersioningManager(transaction_cls=AuditLog)   
    # 初始化版本化 建议使用 init_versioning() 而不是原生的 make_versioned()
    init_versioning(manager=custom_manager)
"""

from __future__ import annotations

from sqlalchemy import Column, Integer, BigInteger, String, event
from sqlalchemy.orm import declared_attr, declarative_base, Mapped, mapped_column
from typing import Optional, ClassVar, Union

try:
    from typing import dataclass_transform  # Python 3.11+
except ImportError:
    from typing_extensions import dataclass_transform  # Python 3.10 及以下

from .primary_key_config import PrimaryKeyConfig, IdType


# 声明基类
Base = declarative_base()


@dataclass_transform(kw_only_default=True, field_specifiers=(mapped_column,))
class IdModel(Base):
    """ID模型基类
    
    提供功能：
    - 动态主键字段（根据配置自动确定类型）
    - 主键生成策略支持
    - 支持模型级别覆盖主键策略
    
    主键策略优先级：
    1. 模型级别 __pk_strategy__ > 模型级别 id_type > 全局配置 > 默认值(AUTO_INCREMENT)
    
    使用示例:
        # 使用全局配置的主键策略
        class User(IdModel):
            __tablename__ = "user"
            username = Column(String(50))
        
        # 使用模型级别覆盖
        class Order(IdModel):
            __tablename__ = "order"
            id_type = IdType.UUID  # 或使用 __pk_strategy__ = IdType.UUID
    """
    __abstract__ = True
    
    # 主键类型（方便子类覆盖使用，优先级低于 __pk_strategy__）
    # 如果子类没有设置 id_type，则使用 __pk_strategy__
    # 如果子类没有设置 __pk_strategy__，则使用全局配置
    # 如果全局配置也没有设置，则使用默认值 AUTO_INCREMENT
    id_type: ClassVar[Optional[IdType]] = None
    
    # id 类型注解（用于 IDE 提示）
    # 实际类型可能是 int（自增、雪花）或 str（UUID、短UUID）
    # 使用 Union 覆盖所有情况
    id: Mapped[Union[int, str]]
    
    def __init_subclass__(cls, **kwargs):
        """子类初始化钩子
        
        处理 id_type 到 __pk_strategy__ 的转换
        """
        super().__init_subclass__(**kwargs)
        
        # 如果子类设置了 id_type，自动设置 __pk_strategy__
        if getattr(cls, 'id_type', None) is not None:
            # 如果子类没有设置 __pk_strategy__，则设置为 id_type，__pk_strategy__优先级更高
            if not hasattr(cls, '__pk_strategy__'):
                cls.__pk_strategy__ = cls.id_type
    
    def _generate_primary_key(self, strategy: str):
        """生成主键值
        
        Args:
            strategy: 主键策略
            
        Returns:
            生成的主键值
        """
        from .primary_key_config import PrimaryKeyConfig
        from .primary_key_generators import (
            create_primary_key_generator,
            PrimaryKeyGenerator
        )
        
        # 获取配置
        short_uuid_length = PrimaryKeyConfig.get_short_uuid_length()
        snowflake_worker_id = PrimaryKeyConfig.get_snowflake_worker_id()
        snowflake_datacenter_id = PrimaryKeyConfig.get_snowflake_datacenter_id()
        custom_generator = PrimaryKeyConfig.get_custom_generator()
        max_retries = PrimaryKeyConfig.get_max_retries()
        
        # 创建生成器函数
        generator_func = create_primary_key_generator(
            strategy=strategy,
            short_uuid_length=short_uuid_length,
            snowflake_worker_id=snowflake_worker_id,
            snowflake_datacenter_id=snowflake_datacenter_id,
            custom_generator=custom_generator
        )
        
        # 使用带冲突检测的生成器
        pk_generator = PrimaryKeyGenerator(max_retries=max_retries)
        return pk_generator.generate_with_retry(
            model_class=self.__class__,
            generator_func=generator_func,
            max_retries=max_retries
        )
    
    @declared_attr
    def id(cls):
        """
        动态主键字段 - 根据配置自动确定类型
        
        支持策略：
        - auto_increment: Integer 自增（默认）
        - snowflake: BigInteger (64位整数)
        - uuid: String(36)
        - short_uuid: String(可配置长度)
        - custom: 根据配置自动判断类型
        
        优先级：模型级别配置 > 全局配置 > 默认值
        """
        # 检查是否禁用自动主键（复合主键场景）
        if getattr(cls, '__use_auto_pk__', True) is False:
            # 返回一个占位符，让子类自己定义主键
            # 注意：这种情况下子类必须定义自己的主键
            return None
        
        # 检查模型级别的策略覆盖
        id_type = getattr(cls, '__pk_strategy__', None)
        if id_type is None:
            id_type = PrimaryKeyConfig.get_strategy()
        
        if id_type == IdType.AUTO_INCREMENT:
            # 自增ID
            return Column(Integer, primary_key=True, autoincrement=True, comment='主键ID')
        elif id_type == IdType.UUID:
            # UUID
            return Column(String(36), primary_key=True, comment='主键ID（UUID）')
        elif id_type == IdType.SHORT_UUID:
            # 短UUID
            length = PrimaryKeyConfig.get_short_uuid_length()
            return Column(String(length + 2), primary_key=True, comment='主键ID（短UUID）')
        elif id_type == IdType.SNOWFLAKE:
            # 雪花ID
            return Column(BigInteger, primary_key=True, comment='主键ID（雪花ID）')
        elif id_type == IdType.CUSTOM:
            # 自定义
            return Column(String(64), primary_key=True, comment='主键ID（自定义）')
        else:
            raise ValueError(f'不支持的主键类型：{id_type}')


# ==================== 自定义主键生成事件监听器 ====================

@event.listens_for(IdModel, 'before_insert', propagate=True)
def event_before_insert_generate_pk(mapper, connection, target):
    """在插入前生成主键
    
    所有非自增主键（UUID、SHORT_UUID、SNOWFLAKE、CUSTOM）都在此事件中生成。
    自增主键由数据库在 INSERT 时生成。
    
    生成时机：flush 过程中，INSERT 语句执行之前。
    
    注意：
    - 只有当主键为 None 时才生成（支持手动指定主键）
    - 使用 generate_with_retry 机制确保 ID 唯一
    - 访问 model.id 时会自动触发 flush（通过 __getattribute__ 拦截）
    """
    from .primary_key_config import PrimaryKeyConfig
    from .primary_key_generators import (
        create_primary_key_generator,
        PrimaryKeyGenerator
    )

    # 检查是否禁用自动主键
    if hasattr(target.__class__, '__use_auto_pk__') and not target.__class__.__use_auto_pk__:
        return

    # 检查是否有模型级别的策略覆盖
    strategy = getattr(target.__class__, '__pk_strategy__', None)
    if strategy is None:
        strategy = PrimaryKeyConfig.get_strategy()

    # 如果主键已经有值，不生成
    if target.id is not None:
        return

    # 获取配置
    short_uuid_length = PrimaryKeyConfig.get_short_uuid_length()
    snowflake_worker_id = PrimaryKeyConfig.get_snowflake_worker_id()
    snowflake_datacenter_id = PrimaryKeyConfig.get_snowflake_datacenter_id()
    custom_generator = PrimaryKeyConfig.get_custom_generator()
    max_retries = PrimaryKeyConfig.get_max_retries()

    # 创建生成器函数
    generator_func = create_primary_key_generator(
        strategy=strategy,
        short_uuid_length=short_uuid_length,
        snowflake_worker_id=snowflake_worker_id,
        snowflake_datacenter_id=snowflake_datacenter_id,
        custom_generator=custom_generator
    )

    # 使用带冲突检测的生成器
    pk_generator = PrimaryKeyGenerator(max_retries=max_retries)
    new_id = pk_generator.generate_with_retry(
        model_class=target.__class__,
        generator_func=generator_func,
        max_retries=max_retries
    )

    # 设置主键
    target.id = new_id
