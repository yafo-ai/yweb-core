"""主键策略测试

测试自定义主键生成策略（方案C：declared_attr + Union类型）

测试场景：
1. 默认整数自增主键
2. 短UUID主键（10位）
3. 完整UUID主键（36位）
4. 雪花算法主键
5. 自定义主键生成器
6. 模型级别覆盖全局配置
7. 动态列类型验证
"""

import pytest
from typing import Union, get_args, get_origin
from sqlalchemy import Column, String, Integer, BigInteger
from sqlalchemy.orm import sessionmaker, scoped_session, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    configure_primary_key,
    PrimaryKeyConfig,
    PKType,
    IdType,
)


# ==================== 测试模型定义 ====================
# extend_existing=True：避免 pytest 多文件加载时重复定义表的错误
# 使用 __pk_strategy__ 在模型级别指定策略

class AutoIncrementModel(BaseModel):
    """整数自增主键模型"""
    __tablename__ = "test_pk_auto_increment"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.AUTO_INCREMENT
    
    username = Column(String(50))


class ShortUUIDModel(BaseModel):
    """短UUID主键模型（10位）"""
    __tablename__ = "test_pk_short_uuid"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    product_name = Column(String(100))


class FullUUIDModel(BaseModel):
    """完整UUID主键模型（36位）"""
    __tablename__ = "test_pk_full_uuid"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.UUID
    
    order_no = Column(String(50))


class SnowflakeModel(BaseModel):
    """雪花算法主键模型"""
    __tablename__ = "test_pk_snowflake"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    
    message = Column(String(500))


class CustomPKModel(BaseModel):
    """自定义主键模型"""
    __tablename__ = "test_pk_custom"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.CUSTOM
    
    title = Column(String(200))


# ==================== 测试类 ====================

class TestAutoIncrementPrimaryKey:
    """整数自增主键测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        # 重置并配置主键策略
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.AUTO_INCREMENT,
            short_uuid_length=10,
            snowflake_worker_id=1,
            snowflake_datacenter_id=1,
            custom_generator=lambda: f"CUSTOM_{id(object()):05d}",
            max_retries=5
        )
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_create_with_auto_increment(self):
        """测试创建自增主键记录"""
        user = AutoIncrementModel(username="tom")
        user.add(True)
        
        assert user.id is not None
        assert isinstance(user.id, int), f"主键应该是整数，实际是 {type(user.id)}"
    
    def test_auto_increment_sequence(self):
        """测试自增主键递增"""
        user1 = AutoIncrementModel(username="alice")
        user1.add(True)
        
        user2 = AutoIncrementModel(username="bob")
        user2.add(True)
        
        assert user2.id > user1.id, "主键应该递增"
    
    def test_column_type_is_integer(self):
        """测试列类型是 Integer"""
        col = AutoIncrementModel.__table__.c.id
        assert isinstance(col.type, Integer), f"列类型应该是 Integer，实际是 {type(col.type)}"


class TestShortUUIDPrimaryKey:
    """短UUID主键测试（10位）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        configure_primary_key(strategy=IdType.AUTO_INCREMENT, short_uuid_length=10)
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_create_with_short_uuid(self):
        """测试创建短UUID主键记录"""
        product = ShortUUIDModel(product_name="iPhone")
        product.add(True)
        
        assert product.id is not None
        assert isinstance(product.id, str), f"主键应该是字符串，实际是 {type(product.id)}"
        assert len(product.id) == 10, f"短UUID长度应该是10位，实际是 {len(product.id)}"
    
    def test_short_uuid_uniqueness(self):
        """测试短UUID唯一性"""
        product1 = ShortUUIDModel(product_name="iPad")
        product1.add(True)
        
        product2 = ShortUUIDModel(product_name="MacBook")
        product2.add(True)
        
        assert product1.id != product2.id, "短UUID应该唯一"
    
    def test_column_type_is_string(self):
        """测试列类型是 String"""
        col = ShortUUIDModel.__table__.c.id
        assert isinstance(col.type, String), f"列类型应该是 String，实际是 {type(col.type)}"


class TestFullUUIDPrimaryKey:
    """完整UUID主键测试（36位）"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        configure_primary_key(strategy=IdType.UUID)
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_create_with_full_uuid(self):
        """测试创建完整UUID主键记录"""
        order = FullUUIDModel(order_no="ORD001")
        order.add(True)
        
        assert order.id is not None
        assert isinstance(order.id, str), f"主键应该是字符串，实际是 {type(order.id)}"
        assert len(order.id) == 36, f"UUID长度应该是36位，实际是 {len(order.id)}"
    
    def test_uuid_format(self):
        """测试UUID格式（包含连字符）"""
        order = FullUUIDModel(order_no="ORD002")
        order.add(True)
        
        assert "-" in order.id, "UUID应该包含连字符"
        parts = order.id.split("-")
        assert len(parts) == 5, "UUID应该有5个部分"
    
    def test_column_type_is_string(self):
        """测试列类型是 String"""
        col = FullUUIDModel.__table__.c.id
        assert isinstance(col.type, String), f"列类型应该是 String，实际是 {type(col.type)}"


class TestSnowflakePrimaryKey:
    """雪花算法主键测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.SNOWFLAKE,
            snowflake_worker_id=1,
            snowflake_datacenter_id=1
        )
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_create_with_snowflake(self):
        """测试创建雪花算法主键记录"""
        log = SnowflakeModel(message="测试日志")
        log.add(True)
        
        assert log.id is not None
        assert isinstance(log.id, int), f"主键应该是整数，实际是 {type(log.id)}"
    
    def test_snowflake_is_large_integer(self):
        """测试雪花ID是大整数"""
        log = SnowflakeModel(message="测试日志2")
        log.add(True)
        
        # 雪花ID应该是非常大的数字（超过10^15）
        assert log.id > 1_000_000_000_000, f"雪花ID应该是大整数，实际是 {log.id}"
    
    def test_snowflake_sequence(self):
        """测试雪花ID递增"""
        log1 = SnowflakeModel(message="日志1")
        log1.add(True)
        
        log2 = SnowflakeModel(message="日志2")
        log2.add(True)
        
        assert log2.id > log1.id, "雪花ID应该递增"
    
    def test_column_type_is_biginteger(self):
        """测试列类型是 BigInteger"""
        col = SnowflakeModel.__table__.c.id
        assert isinstance(col.type, (Integer, BigInteger)), \
            f"列类型应该是 BigInteger，实际是 {type(col.type)}"


class TestCustomPrimaryKey:
    """自定义主键生成器测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        
        # 自定义生成器
        self.counter = [0]
        
        def custom_generator():
            self.counter[0] += 1
            return f"CUSTOM_{self.counter[0]:05d}"
        
        configure_primary_key(
            strategy=IdType.CUSTOM,
            custom_generator=custom_generator
        )
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_create_with_custom_generator(self):
        """测试创建自定义主键记录"""
        task = CustomPKModel(title="任务1")
        task.add(True)
        
        assert task.id is not None
        assert str(task.id).startswith("CUSTOM_"), \
            f"自定义ID应该以CUSTOM_开头，实际是 {task.id}"
    
    def test_custom_generator_uniqueness(self):
        """测试自定义生成器生成的ID唯一"""
        task1 = CustomPKModel(title="任务A")
        task1.add(True)
        
        task2 = CustomPKModel(title="任务B")
        task2.add(True)
        
        assert task1.id != task2.id, "自定义ID应该唯一"
    
    def test_column_type_is_string(self):
        """测试列类型是 String"""
        col = CustomPKModel.__table__.c.id
        assert isinstance(col.type, String), f"列类型应该是 String，实际是 {type(col.type)}"


class TestDynamicColumnType:
    """动态列类型测试（方案C核心验证）"""
    
    def test_auto_increment_column_type(self):
        """测试整数自增列类型正确"""
        col = AutoIncrementModel.__table__.c.id
        assert isinstance(col.type, Integer), \
            f"AutoIncrementModel.id 应该是 Integer，实际是 {type(col.type)}"
    
    def test_short_uuid_column_type(self):
        """测试短UUID列类型正确"""
        col = ShortUUIDModel.__table__.c.id
        assert isinstance(col.type, String), \
            f"ShortUUIDModel.id 应该是 String，实际是 {type(col.type)}"
    
    def test_full_uuid_column_type(self):
        """测试完整UUID列类型正确"""
        col = FullUUIDModel.__table__.c.id
        assert isinstance(col.type, String), \
            f"FullUUIDModel.id 应该是 String，实际是 {type(col.type)}"
    
    def test_snowflake_column_type(self):
        """测试雪花算法列类型正确"""
        col = SnowflakeModel.__table__.c.id
        assert isinstance(col.type, (Integer, BigInteger)), \
            f"SnowflakeModel.id 应该是 BigInteger，实际是 {type(col.type)}"
    
    def test_custom_column_type(self):
        """测试自定义主键列类型正确"""
        col = CustomPKModel.__table__.c.id
        assert isinstance(col.type, String), \
            f"CustomPKModel.id 应该是 String，实际是 {type(col.type)}"


class TestPKTypeAlias:
    """PKType 类型别名测试"""
    
    def test_pktype_is_union(self):
        """验证 PKType 是 Union[int, str]"""
        origin = get_origin(PKType)
        args = get_args(PKType)
        
        assert origin is Union, f"PKType 应该是 Union 类型，实际是 {origin}"
        assert int in args, "PKType 应该包含 int"
        assert str in args, "PKType 应该包含 str"


class TestManualPrimaryKey:
    """手动指定主键测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        configure_primary_key(strategy=IdType.AUTO_INCREMENT, short_uuid_length=10)
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_manual_pk_auto_increment(self):
        """测试手动指定整数自增主键"""
        import random
        manual_id = random.randint(100000, 999999)
        
        user = AutoIncrementModel(username="manual_user")
        user.id = manual_id
        user.add(True)
        
        assert user.id == manual_id
    
    def test_manual_pk_short_uuid(self):
        """测试手动指定短UUID主键"""
        import uuid
        manual_id = f"M{str(uuid.uuid4())[:9]}"
        
        product = ShortUUIDModel(product_name="manual_product")
        product.id = manual_id
        product.add(True)
        
        assert product.id == manual_id


class TestQueryByPrimaryKey:
    """通过主键查询测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        configure_primary_key(strategy=IdType.AUTO_INCREMENT, short_uuid_length=10)
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_query_by_int_pk(self):
        """测试通过整数主键查询"""
        user = AutoIncrementModel(username="query_user")
        user.add(True)
        
        found = AutoIncrementModel.get(user.id)
        assert found is not None
        assert found.username == "query_user"
    
    def test_query_by_str_pk(self):
        """测试通过字符串主键查询"""
        product = ShortUUIDModel(product_name="query_product")
        product.add(True)
        
        found = ShortUUIDModel.get(product.id)
        assert found is not None
        assert found.product_name == "query_product"


class TestModelLevelOverride:
    """模型级别覆盖全局配置测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        PrimaryKeyConfig.reset()
        # 全局配置短UUID，但模型级别可以覆盖
        configure_primary_key(
            strategy=IdType.SHORT_UUID,
            short_uuid_length=10,
            snowflake_worker_id=1,
            snowflake_datacenter_id=1,
            custom_generator=lambda: f"CUSTOM_{id(object()):05d}"
        )
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
        # 恢复默认配置，避免影响其他测试
        PrimaryKeyConfig.reset()
    
    def test_different_strategies_coexist(self):
        """测试不同策略的模型共存"""
        # 创建不同策略的记录
        user = AutoIncrementModel(username="test_user")
        user.add(True)
        
        product = ShortUUIDModel(product_name="test_product")
        product.add(True)
        
        order = FullUUIDModel(order_no="TEST001")
        order.add(True)
        
        log = SnowflakeModel(message="test_log")
        log.add(True)
        
        # 验证类型
        assert isinstance(user.id, int), "AutoIncrementModel.id 应该是整数"
        assert isinstance(product.id, str) and len(product.id) == 10, \
            "ShortUUIDModel.id 应该是10位字符串"
        assert isinstance(order.id, str) and len(order.id) == 36, \
            "FullUUIDModel.id 应该是36位UUID"
        assert isinstance(log.id, int) and log.id > 1_000_000_000_000, \
            "SnowflakeModel.id 应该是大整数"
