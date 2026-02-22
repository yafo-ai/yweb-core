"""主键策略优先级测试

测试主键策略的优先级规则：
    模型级别配置（__pk_strategy__） > 模型级别配置（id_type） > 全局配置 > 默认值

测试覆盖：
- 默认配置：未设置任何配置时使用 AUTO_INCREMENT
- 全局配置：configure_primary_key 设置后生效
- 模型级别 id_type：优先于全局配置
- 模型级别 __pk_strategy__：优先级最高
- __pk_strategy__ 和 id_type 同时设置时，__pk_strategy__ 优先
"""

import pytest
from sqlalchemy import String, Integer, BigInteger, inspect as sa_inspect
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    IdType,
    configure_primary_key,
    PrimaryKeyConfig,
)


# ==================== 辅助函数 ====================

def get_pk_column_type(model_class) -> str:
    """获取模型主键列的类型"""
    mapper = sa_inspect(model_class)
    pk_columns = mapper.primary_key
    if pk_columns:
        pk_col = pk_columns[0]
        return str(pk_col.type)
    return "未知"


def is_integer_type(col_type: str) -> bool:
    """判断是否为整数类型"""
    return "INTEGER" in col_type.upper()


def is_biginteger_type(col_type: str) -> bool:
    """判断是否为大整数类型"""
    return "BIGINT" in col_type.upper()


def is_string_type(col_type: str, length: int = None) -> bool:
    """判断是否为字符串类型"""
    if "VARCHAR" not in col_type.upper() and "STRING" not in col_type.upper():
        return False
    if length:
        return str(length) in col_type
    return True


# ==================== 测试类 ====================

class TestPkStrategyPriorityDefault:
    """测试默认配置（未设置任何全局配置）"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置配置"""
        PrimaryKeyConfig.reset()
        yield
        PrimaryKeyConfig.reset()
    
    def test_default_strategy_is_auto_increment(self):
        """测试：默认策略是 AUTO_INCREMENT"""
        assert PrimaryKeyConfig.get_strategy() == IdType.AUTO_INCREMENT
    
    def test_model_without_pk_strategy_uses_default(self):
        """测试：未设置 __pk_strategy__ 的模型使用默认配置"""
        
        class DefaultTestModel(BaseModel):
            __tablename__ = "test_default_pk"
            __table_args__ = {'extend_existing': True}
            # 不设置 __pk_strategy__ 或 id_type
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(DefaultTestModel)
        assert is_integer_type(col_type), f"期望整数类型，实际: {col_type}"


class TestPkStrategyPriorityGlobal:
    """测试全局配置"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置配置"""
        PrimaryKeyConfig.reset()
        yield
        PrimaryKeyConfig.reset()
    
    def test_global_snowflake_config(self):
        """测试：全局配置为 SNOWFLAKE 时生效"""
        configure_primary_key(strategy=IdType.SNOWFLAKE)
        
        class GlobalSnowflakeModel(BaseModel):
            __tablename__ = "test_global_snowflake"
            __table_args__ = {'extend_existing': True}
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(GlobalSnowflakeModel)
        assert is_biginteger_type(col_type), f"期望 BIGINT 类型，实际: {col_type}"
    
    def test_global_uuid_config(self):
        """测试：全局配置为 UUID 时生效"""
        configure_primary_key(strategy=IdType.UUID)
        
        class GlobalUuidModel(BaseModel):
            __tablename__ = "test_global_uuid"
            __table_args__ = {'extend_existing': True}
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(GlobalUuidModel)
        assert is_string_type(col_type, 36), f"期望 VARCHAR(36) 类型，实际: {col_type}"
    
    def test_global_short_uuid_config(self):
        """测试：全局配置为 SHORT_UUID 时生效"""
        configure_primary_key(strategy=IdType.SHORT_UUID, short_uuid_length=10)
        
        class GlobalShortUuidModel(BaseModel):
            __tablename__ = "test_global_short_uuid"
            __table_args__ = {'extend_existing': True}
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(GlobalShortUuidModel)
        # short_uuid_length=10, 列长度为 length+2=12
        assert is_string_type(col_type, 12), f"期望 VARCHAR(12) 类型，实际: {col_type}"


class TestPkStrategyPriorityModelIdType:
    """测试模型级别 id_type 配置"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置配置"""
        PrimaryKeyConfig.reset()
        # 设置全局配置为 SNOWFLAKE，用于测试模型级别覆盖
        configure_primary_key(strategy=IdType.SNOWFLAKE)
        yield
        PrimaryKeyConfig.reset()
    
    def test_model_id_type_overrides_global(self):
        """测试：模型 id_type 覆盖全局配置"""
        # 全局是 SNOWFLAKE，但模型指定 UUID
        
        class IdTypeOverrideModel(BaseModel):
            __tablename__ = "test_id_type_override"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.UUID  # 模型级别覆盖
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(IdTypeOverrideModel)
        assert is_string_type(col_type, 36), f"期望 VARCHAR(36) 类型，实际: {col_type}"
    
    def test_model_id_type_auto_increment_overrides_global(self):
        """测试：模型 id_type=AUTO_INCREMENT 覆盖全局 SNOWFLAKE"""
        
        class IdTypeAutoModel(BaseModel):
            __tablename__ = "test_id_type_auto"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.AUTO_INCREMENT
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(IdTypeAutoModel)
        assert is_integer_type(col_type), f"期望整数类型，实际: {col_type}"
    
    def test_model_id_type_short_uuid_overrides_global(self):
        """测试：模型 id_type=SHORT_UUID 覆盖全局 SNOWFLAKE"""
        
        class IdTypeShortUuidModel(BaseModel):
            __tablename__ = "test_id_type_short_uuid"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.SHORT_UUID
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(IdTypeShortUuidModel)
        assert is_string_type(col_type), f"期望字符串类型，实际: {col_type}"


class TestPkStrategyPriorityModelPkStrategy:
    """测试模型级别 __pk_strategy__ 配置（最高优先级）"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置配置"""
        PrimaryKeyConfig.reset()
        # 设置全局配置为 AUTO_INCREMENT
        configure_primary_key(strategy=IdType.AUTO_INCREMENT)
        yield
        PrimaryKeyConfig.reset()
    
    def test_pk_strategy_overrides_global(self):
        """测试：__pk_strategy__ 覆盖全局配置"""
        
        class PkStrategyOverrideModel(BaseModel):
            __tablename__ = "test_pk_strategy_override"
            __table_args__ = {'extend_existing': True}
            __pk_strategy__ = IdType.UUID
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(PkStrategyOverrideModel)
        assert is_string_type(col_type, 36), f"期望 VARCHAR(36) 类型，实际: {col_type}"
    
    def test_pk_strategy_snowflake_overrides_global(self):
        """测试：__pk_strategy__=SNOWFLAKE 覆盖全局 AUTO_INCREMENT"""
        
        class PkStrategySnowflakeModel(BaseModel):
            __tablename__ = "test_pk_strategy_snowflake"
            __table_args__ = {'extend_existing': True}
            __pk_strategy__ = IdType.SNOWFLAKE
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(PkStrategySnowflakeModel)
        assert is_biginteger_type(col_type), f"期望 BIGINT 类型，实际: {col_type}"


class TestPkStrategyPriorityPkStrategyOverridesIdType:
    """测试 __pk_strategy__ 优先于 id_type"""
    
    @pytest.fixture(autouse=True)
    def setup(self):
        """每个测试前重置配置"""
        PrimaryKeyConfig.reset()
        yield
        PrimaryKeyConfig.reset()
    
    def test_pk_strategy_overrides_id_type(self):
        """测试：同时设置 __pk_strategy__ 和 id_type 时，__pk_strategy__ 优先"""
        
        class BothSetModel(BaseModel):
            __tablename__ = "test_both_set"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.AUTO_INCREMENT  # 低优先级
            __pk_strategy__ = IdType.UUID     # 高优先级
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(BothSetModel)
        # __pk_strategy__ = UUID 应该生效
        assert is_string_type(col_type, 36), f"期望 VARCHAR(36) 类型，实际: {col_type}"
    
    def test_pk_strategy_snowflake_overrides_id_type_uuid(self):
        """测试：__pk_strategy__=SNOWFLAKE 覆盖 id_type=UUID"""
        
        class BothSetModel2(BaseModel):
            __tablename__ = "test_both_set_2"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.UUID              # 低优先级
            __pk_strategy__ = IdType.SNOWFLAKE  # 高优先级
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        col_type = get_pk_column_type(BothSetModel2)
        # __pk_strategy__ = SNOWFLAKE 应该生效
        assert is_biginteger_type(col_type), f"期望 BIGINT 类型，实际: {col_type}"


class TestPkStrategyPriorityWithDatabase:
    """带数据库的完整优先级测试"""
    
    @pytest.fixture
    def setup_db(self):
        """初始化数据库"""
        PrimaryKeyConfig.reset()
        
        engine, session_scope = init_database("sqlite:///:memory:", echo=False)
        CoreModel.query = session_scope.query_property()
        BaseModel.metadata.create_all(bind=engine)
        
        session = session_scope()
        
        yield session
        
        session_scope.remove()
        engine.dispose()
        PrimaryKeyConfig.reset()
    
    def test_priority_with_actual_data(self, setup_db):
        """测试：使用实际数据验证优先级"""
        session = setup_db
        
        # 设置全局配置为 SNOWFLAKE
        configure_primary_key(strategy=IdType.SNOWFLAKE)
        
        # 定义使用默认（跟随全局）的模型
        class FollowGlobalModel(BaseModel):
            __tablename__ = "test_follow_global"
            __table_args__ = {'extend_existing': True}
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        # 定义覆盖全局的模型
        class OverrideGlobalModel(BaseModel):
            __tablename__ = "test_override_global"
            __table_args__ = {'extend_existing': True}
            id_type = IdType.UUID
            content: Mapped[str] = mapped_column(String(200), nullable=True)
        
        # 创建表
        FollowGlobalModel.__table__.create(bind=session.bind, checkfirst=True)
        OverrideGlobalModel.__table__.create(bind=session.bind, checkfirst=True)
        
        # 创建记录
        obj1 = FollowGlobalModel(name="跟随全局", code="FOLLOW001", content="测试")
        obj1.add(True)
        
        obj2 = OverrideGlobalModel(name="覆盖全局", code="OVERRIDE001", content="测试")
        obj2.add(True)
        
        # 验证
        # obj1 应该是雪花ID（整数且很大）
        assert isinstance(obj1.id, int), f"期望整数，实际: {type(obj1.id)}"
        assert obj1.id > 2**31, f"期望雪花ID（大整数），实际: {obj1.id}"
        
        # obj2 应该是 UUID（36位字符串）
        assert isinstance(obj2.id, str), f"期望字符串，实际: {type(obj2.id)}"
        assert len(obj2.id) == 36, f"期望36位UUID，实际长度: {len(obj2.id)}"
        assert obj2.id.count('-') == 4, f"期望UUID格式（4个连字符），实际: {obj2.id}"
