"""主键冲突重试机制测试

测试当主键生成器生成重复主键时，系统是否能正确检测冲突并重试。

测试场景：
1. 不带历史记录的模型 - 测试基本的重试机制
2. 带历史记录的模型 - 测试重试机制与 sqlalchemy-history 的兼容性

测试用例：
- 生成器前几次返回重复ID，最后返回唯一ID → 应该成功
- 生成器始终返回重复ID → 应该在 max_retries 次后失败
- 验证重试计数是否正确
- 验证错误信息是否清晰
"""

import pytest
from unittest.mock import patch, MagicMock
from sqlalchemy import String, Column, text
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_primary_key,
    PrimaryKeyConfig,
    IdType,
)
from yweb.orm.primary_key_generators import (
    PrimaryKeyGenerator,
    generate_short_uuid,
    generate_snowflake_id,
)


# ==================== 测试模型定义（不带历史记录） ====================

class CollisionTestModel(BaseModel):
    """用于测试主键冲突的模型（不带历史记录）"""
    __tablename__ = "test_pk_collision"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    
    content: Mapped[str] = mapped_column(String(200), nullable=True)


class SnowflakeCollisionModel(BaseModel):
    """用于测试雪花算法主键冲突的模型（不带历史记录）"""
    __tablename__ = "test_pk_snowflake_collision"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    
    content: Mapped[str] = mapped_column(String(200), nullable=True)


class CustomCollisionModel(BaseModel):
    """用于测试自定义主键冲突的模型（不带历史记录）"""
    __tablename__ = "test_pk_custom_collision"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.CUSTOM
    
    content: Mapped[str] = mapped_column(String(200), nullable=True)


# ==================== 测试模型定义（带历史记录） ====================

# 导入版本化相关组件
from yweb.orm import init_versioning, is_versioning_initialized, get_history_count

# 确保版本化已初始化
try:
    if not is_versioning_initialized():
        init_versioning()
except Exception:
    pass


class CollisionHistoryModel(BaseModel):
    """用于测试主键冲突的模型（带历史记录）"""
    __tablename__ = "test_pk_collision_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SHORT_UUID
    enable_history = True
    
    content: Mapped[str] = mapped_column(String(200), nullable=True)


class SnowflakeCollisionHistoryModel(BaseModel):
    """用于测试雪花算法主键冲突的模型（带历史记录）"""
    __tablename__ = "test_pk_snowflake_collision_history"
    __table_args__ = {'extend_existing': True}
    __pk_strategy__ = IdType.SNOWFLAKE
    enable_history = True
    
    content: Mapped[str] = mapped_column(String(200), nullable=True)


# 配置 mappers
try:
    configure_mappers()
except Exception:
    pass


# ==================== 通用 Fixture ====================

@pytest.fixture
def setup_db():
    """初始化数据库（不带历史记录）"""
    PrimaryKeyConfig.reset()
    configure_primary_key(
        strategy=IdType.SHORT_UUID,
        short_uuid_length=10,
        snowflake_worker_id=1,
        snowflake_datacenter_id=1,
        custom_generator=lambda: f"CUSTOM_{id(object()):010d}",
        max_retries=5
    )
    
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    CoreModel.query = session_scope.query_property()
    BaseModel.metadata.create_all(bind=engine)
    
    session = session_scope()
    
    yield session
    
    session_scope.remove()
    engine.dispose()
    PrimaryKeyConfig.reset()


@pytest.fixture
def setup_history_db():
    """初始化数据库（带历史记录）
    
    注意：带历史记录的测试需要使用整数类型的主键策略（snowflake/auto_increment），
    因为 sqlalchemy-history 的 transaction 表默认使用整数主键。
    """
    from sqlalchemy_history import versioning_manager
    
    PrimaryKeyConfig.reset()
    # 使用 snowflake 策略，避免与 transaction 表的整数主键冲突
    configure_primary_key(
        strategy=IdType.SNOWFLAKE,
        snowflake_worker_id=1,
        snowflake_datacenter_id=1,
        short_uuid_length=10,
        custom_generator=lambda: f"CUSTOM_{id(object()):010d}",
        max_retries=5
    )
    
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    CoreModel.query = session_scope.query_property()
    BaseModel.metadata.create_all(bind=engine)
    
    # 创建版本化相关的表
    if versioning_manager.transaction_cls is not None:
        versioning_manager.transaction_cls.__table__.create(bind=engine, checkfirst=True)
    
    for table_key, version_cls in versioning_manager.version_class_map.items():
        if version_cls is not None and hasattr(version_cls, '__table__'):
            version_cls.__table__.create(bind=engine, checkfirst=True)
    
    session = session_scope()
    
    yield session
    
    session_scope.remove()
    engine.dispose()
    PrimaryKeyConfig.reset()


# ==================== PrimaryKeyGenerator 单元测试 ====================

class TestPrimaryKeyGeneratorRetry:
    """PrimaryKeyGenerator 重试机制单元测试"""
    
    def test_generate_with_no_collision(self, setup_db):
        """测试：无冲突时直接返回"""
        generator = PrimaryKeyGenerator(max_retries=5)
        
        # 使用一个肯定不冲突的生成器
        unique_ids = iter([f"unique_{i}" for i in range(10)])
        
        result = generator.generate_with_retry(
            model_class=CollisionTestModel,
            generator_func=lambda: next(unique_ids)
        )
        
        assert result == "unique_0"
    
    def test_retry_on_collision_then_success(self, setup_db):
        """测试：冲突后重试，最终成功"""
        session = setup_db
        
        # 先创建一条记录，使其 ID 存在
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 创建一个生成器：前2次返回冲突ID，第3次返回唯一ID
        call_count = [0]
        def mock_generator():
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id  # 返回已存在的ID（冲突）
            return f"unique_{call_count[0]}"  # 返回新的唯一ID
        
        generator = PrimaryKeyGenerator(max_retries=5)
        result = generator.generate_with_retry(
            model_class=CollisionTestModel,
            generator_func=mock_generator
        )
        
        # 应该在第3次成功
        assert call_count[0] == 3
        assert result == "unique_3"
    
    def test_fail_after_max_retries(self, setup_db):
        """测试：超过最大重试次数后失败"""
        session = setup_db
        
        # 先创建一条记录
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 创建一个始终返回冲突ID的生成器
        def always_collision_generator():
            return existing_id
        
        generator = PrimaryKeyGenerator(max_retries=3)
        
        # 应该抛出 RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_with_retry(
                model_class=CollisionTestModel,
                generator_func=always_collision_generator,
                max_retries=3
            )
        
        # 验证错误信息
        assert "3次尝试后仍然冲突" in str(exc_info.value)
        assert "CollisionTestModel" in str(exc_info.value)
    
    def test_retry_count_matches_max_retries(self, setup_db):
        """测试：重试次数与 max_retries 配置一致"""
        session = setup_db
        
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        call_count = [0]
        def counting_generator():
            call_count[0] += 1
            return existing_id  # 始终返回冲突ID
        
        max_retries = 7
        generator = PrimaryKeyGenerator(max_retries=max_retries)
        
        with pytest.raises(RuntimeError):
            generator.generate_with_retry(
                model_class=CollisionTestModel,
                generator_func=counting_generator,
                max_retries=max_retries
            )
        
        # 验证调用次数等于 max_retries
        assert call_count[0] == max_retries


# ==================== 不带历史记录的模型冲突测试 ====================

class TestCollisionWithoutHistory:
    """不带历史记录的模型主键冲突测试"""
    
    def test_short_uuid_collision_retry(self, setup_db):
        """测试：short_uuid 策略冲突重试"""
        session = setup_db
        
        # 创建一条记录
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 模拟冲突：前2次返回已存在的ID
        call_count = [0]
        original_generate = generate_short_uuid
        
        def mock_short_uuid(length=10):
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id
            return original_generate(length)
        
        with patch('yweb.orm.primary_key_generators.generate_short_uuid', mock_short_uuid):
            # 重新配置以使用 mock
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SHORT_UUID,
                short_uuid_length=10,
                max_retries=5
            )
            
            # 创建新记录
            new_model = CollisionTestModel(name="New", content="new content")
            new_model.add(True)
            
            # 应该成功创建
            assert new_model.id is not None
            assert new_model.id != existing_id
    
    def test_snowflake_collision_retry(self, setup_db):
        """测试：snowflake 策略冲突重试"""
        session = setup_db
        
        # 先配置为 snowflake 策略
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.SNOWFLAKE,
            snowflake_worker_id=1,
            snowflake_datacenter_id=1,
            max_retries=5
        )
        
        # 创建一条记录
        existing = SnowflakeCollisionModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 模拟冲突
        call_count = [0]
        original_generate = generate_snowflake_id
        
        def mock_snowflake(worker_id=1, datacenter_id=1):
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id
            return original_generate(worker_id, datacenter_id)
        
        with patch('yweb.orm.primary_key_generators.generate_snowflake_id', mock_snowflake):
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SNOWFLAKE,
                snowflake_worker_id=1,
                snowflake_datacenter_id=1,
                max_retries=5
            )
            
            new_model = SnowflakeCollisionModel(name="New", content="new content")
            new_model.add(True)
            
            assert new_model.id is not None
            assert new_model.id != existing_id
    
    def test_custom_generator_collision_retry(self, setup_db):
        """测试：custom 策略冲突重试"""
        session = setup_db
        
        # 定义自定义生成器
        collision_id = "COLLISION_ID_12345"
        call_count = [0]
        
        def custom_generator():
            call_count[0] += 1
            if call_count[0] <= 2:
                return collision_id
            return f"UNIQUE_ID_{call_count[0]}"
        
        # 配置自定义策略
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.CUSTOM,
            custom_generator=custom_generator,
            max_retries=5
        )
        
        # 先创建一条记录占用冲突ID
        existing = CustomCollisionModel(name="Existing", content="content")
        existing.id = collision_id
        existing.add(True)
        
        # 重置计数器
        call_count[0] = 0
        
        # 创建新记录（应该在重试后成功）
        new_model = CustomCollisionModel(name="New", content="new content")
        new_model.add(True)
        
        assert new_model.id is not None
        assert new_model.id != collision_id
    
    def test_collision_fail_exceeds_max_retries(self, setup_db):
        """测试：冲突次数超过 max_retries 时失败"""
        session = setup_db
        
        # 创建一条记录（使用 short_uuid 策略）
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 模拟始终返回冲突ID的生成器
        def always_collision(length=10):
            return existing_id
        
        # 使用 patch 来模拟冲突
        with patch('yweb.orm.primary_key_generators.generate_short_uuid', always_collision):
            # 配置较小的 max_retries
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SHORT_UUID,
                short_uuid_length=10,
                max_retries=2
            )
            
            # 创建新记录应该失败
            with pytest.raises(RuntimeError) as exc_info:
                new_model = CollisionTestModel(name="New", content="new content")
                new_model.add(True)
            
            assert "2次尝试后仍然冲突" in str(exc_info.value)


# ==================== 带历史记录的模型冲突测试 ====================

class TestCollisionWithHistory:
    """带历史记录的模型主键冲突测试"""
    
    def test_snowflake_collision_retry_with_history_basic(self, setup_history_db):
        """测试：snowflake 策略冲突重试（带历史记录）- 基础测试"""
        session = setup_history_db
        
        # 创建一条记录
        existing = SnowflakeCollisionHistoryModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 验证历史记录已创建
        count = get_history_count(SnowflakeCollisionHistoryModel, existing_id, session=session)
        assert count >= 1, "创建记录后应该有历史记录"
        
        # 模拟冲突
        call_count = [0]
        original_generate = generate_snowflake_id
        
        def mock_snowflake(worker_id=1, datacenter_id=1):
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id
            return original_generate(worker_id, datacenter_id)
        
        with patch('yweb.orm.primary_key_generators.generate_snowflake_id', mock_snowflake):
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SNOWFLAKE,
                snowflake_worker_id=1,
                snowflake_datacenter_id=1,
                max_retries=5
            )
            
            new_model = SnowflakeCollisionHistoryModel(name="New", content="new content")
            new_model.add(True)
            
            # 应该成功创建
            assert new_model.id is not None
            assert new_model.id != existing_id
            
            # 新记录的历史也应该正确创建
            new_count = get_history_count(SnowflakeCollisionHistoryModel, new_model.id, session=session)
            assert new_count >= 1, "新记录也应该有历史记录"
    
    def test_snowflake_collision_retry_with_history_extended(self, setup_history_db):
        """测试：snowflake 策略冲突重试（带历史记录）- 扩展测试"""
        session = setup_history_db
        
        # 创建一条记录
        existing = SnowflakeCollisionHistoryModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 验证历史记录
        count = get_history_count(SnowflakeCollisionHistoryModel, existing_id, session=session)
        assert count >= 1
        
        # 模拟冲突：前3次返回已存在的ID
        call_count = [0]
        original_generate = generate_snowflake_id
        
        def mock_snowflake(worker_id=1, datacenter_id=1):
            call_count[0] += 1
            if call_count[0] <= 3:
                return existing_id
            return original_generate(worker_id, datacenter_id)
        
        with patch('yweb.orm.primary_key_generators.generate_snowflake_id', mock_snowflake):
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SNOWFLAKE,
                snowflake_worker_id=1,
                snowflake_datacenter_id=1,
                max_retries=5
            )
            
            new_model = SnowflakeCollisionHistoryModel(name="New", content="new content")
            new_model.add(True)
            
            assert new_model.id is not None
            assert new_model.id != existing_id
            
            # 验证新记录的历史
            new_count = get_history_count(SnowflakeCollisionHistoryModel, new_model.id, session=session)
            assert new_count >= 1
    
    def test_collision_fail_with_history(self, setup_history_db):
        """测试：冲突失败时不会创建不完整的历史记录"""
        session = setup_history_db
        
        # 创建一条记录
        existing = SnowflakeCollisionHistoryModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 记录创建前的历史数量
        initial_count = get_history_count(SnowflakeCollisionHistoryModel, existing_id, session=session)
        
        # 模拟始终返回冲突ID的生成器
        def always_collision(worker_id=1, datacenter_id=1):
            return existing_id
        
        with patch('yweb.orm.primary_key_generators.generate_snowflake_id', always_collision):
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SNOWFLAKE,
                snowflake_worker_id=1,
                snowflake_datacenter_id=1,
                max_retries=2
            )
            
            # 创建新记录应该失败
            with pytest.raises(RuntimeError) as exc_info:
                new_model = SnowflakeCollisionHistoryModel(name="New", content="new content")
                new_model.add(True)
            
            # 验证错误信息
            assert "2次尝试后仍然冲突" in str(exc_info.value)
        
        # 由于异常导致 session 处于 rollback 状态，需要先回滚
        session.rollback()
        
        # 历史记录数量不应该增加（因为创建失败了）
        final_count = get_history_count(SnowflakeCollisionHistoryModel, existing_id, session=session)
        assert final_count == initial_count, "创建失败时不应该产生新的历史记录"
    
    def test_history_correct_after_retry(self, setup_history_db):
        """测试：重试成功后历史记录ID正确"""
        session = setup_history_db
        
        from yweb.orm import get_history
        
        # 创建一条记录
        existing = SnowflakeCollisionHistoryModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        # 模拟冲突后成功
        call_count = [0]
        original_generate = generate_snowflake_id
        
        def mock_snowflake(worker_id=1, datacenter_id=1):
            call_count[0] += 1
            if call_count[0] <= 1:
                return existing_id
            return original_generate(worker_id, datacenter_id)
        
        with patch('yweb.orm.primary_key_generators.generate_snowflake_id', mock_snowflake):
            PrimaryKeyConfig.reset()
            configure_primary_key(
                strategy=IdType.SNOWFLAKE,
                snowflake_worker_id=1,
                snowflake_datacenter_id=1,
                max_retries=5
            )
            
            new_model = SnowflakeCollisionHistoryModel(name="New", content="new content")
            new_model.add(True)
            new_id = new_model.id
            
            # 获取新记录的历史
            history = get_history(SnowflakeCollisionHistoryModel, new_id, session=session)
            
            assert history is not None
            assert len(history) >= 1
            
            # 验证历史记录中的ID是正确的（不是冲突的ID）
            for record in history:
                assert record.get('id') == new_id
                assert record.get('id') != existing_id


# ==================== 边界情况测试 ====================

class TestCollisionEdgeCases:
    """冲突重试边界情况测试"""
    
    def test_max_retries_zero(self, setup_db):
        """测试：max_retries=0 时第一次冲突就失败"""
        session = setup_db
        
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        def always_collision():
            return existing_id
        
        generator = PrimaryKeyGenerator(max_retries=0)
        
        # max_retries=0 时，range(0) 不会执行任何循环
        # 所以会直接抛出 RuntimeError
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_with_retry(
                model_class=CollisionTestModel,
                generator_func=always_collision,
                max_retries=0
            )
        
        assert "0次尝试" in str(exc_info.value)
    
    def test_max_retries_one(self, setup_db):
        """测试：max_retries=1 时只有一次机会"""
        session = setup_db
        
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        call_count = [0]
        def collision_then_unique():
            call_count[0] += 1
            if call_count[0] == 1:
                return existing_id
            return f"unique_{call_count[0]}"
        
        generator = PrimaryKeyGenerator(max_retries=1)
        
        # 只有1次机会，第1次冲突就失败
        with pytest.raises(RuntimeError):
            generator.generate_with_retry(
                model_class=CollisionTestModel,
                generator_func=collision_then_unique,
                max_retries=1
            )
    
    def test_first_attempt_success(self, setup_db):
        """测试：第一次就成功（无冲突）"""
        session = setup_db
        
        call_count = [0]
        def unique_generator():
            call_count[0] += 1
            return f"unique_{call_count[0]}"
        
        generator = PrimaryKeyGenerator(max_retries=5)
        result = generator.generate_with_retry(
            model_class=CollisionTestModel,
            generator_func=unique_generator
        )
        
        # 应该只调用一次
        assert call_count[0] == 1
        assert result == "unique_1"
    
    def test_last_attempt_success(self, setup_db):
        """测试：最后一次尝试成功"""
        session = setup_db
        
        existing = CollisionTestModel(name="Existing", content="content")
        existing.add(True)
        existing_id = existing.id
        
        max_retries = 5
        call_count = [0]
        
        def collision_until_last():
            call_count[0] += 1
            if call_count[0] < max_retries:
                return existing_id
            return f"unique_last"
        
        generator = PrimaryKeyGenerator(max_retries=max_retries)
        result = generator.generate_with_retry(
            model_class=CollisionTestModel,
            generator_func=collision_until_last,
            max_retries=max_retries
        )
        
        # 应该在最后一次成功
        assert call_count[0] == max_retries
        assert result == "unique_last"


# ==================== 并发场景测试 ====================

class TestConcurrentCollision:
    """并发场景下的冲突测试"""
    
    def test_multiple_records_same_session(self, setup_db):
        """测试：同一 session 中创建多条记录"""
        session = setup_db
        
        # 快速创建多条记录
        models = []
        for i in range(10):
            model = CollisionTestModel(name=f"Record_{i}", content=f"content_{i}")
            model.add(True)
            models.append(model)
        
        # 验证所有ID都是唯一的
        ids = [m.id for m in models]
        assert len(ids) == len(set(ids)), "所有ID应该唯一"
    
    def test_multiple_records_with_history(self, setup_history_db):
        """测试：同一 session 中创建多条带历史记录的记录"""
        session = setup_history_db
        
        models = []
        for i in range(10):
            model = SnowflakeCollisionHistoryModel(name=f"Record_{i}", content=f"content_{i}")
            model.add(True)
            models.append(model)
        
        # 验证所有ID唯一
        ids = [m.id for m in models]
        assert len(ids) == len(set(ids)), "所有ID应该唯一"
        
        # 验证每条记录都有历史
        for model in models:
            count = get_history_count(SnowflakeCollisionHistoryModel, model.id, session=session)
            assert count >= 1, f"记录 {model.name} 应该有历史记录"


# ==================== 配置验证测试 ====================

class TestRetryConfiguration:
    """重试配置测试"""
    
    def test_default_max_retries(self):
        """测试：默认 max_retries 值"""
        PrimaryKeyConfig.reset()
        
        # 默认值应该是 5
        assert PrimaryKeyConfig.get_max_retries() == 5
    
    def test_custom_max_retries(self):
        """测试：自定义 max_retries 值"""
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.SHORT_UUID,
            max_retries=10
        )
        
        assert PrimaryKeyConfig.get_max_retries() == 10
        
        PrimaryKeyConfig.reset()
    
    def test_max_retries_persists_across_models(self, setup_db):
        """测试：max_retries 配置在不同模型间一致"""
        session = setup_db
        
        PrimaryKeyConfig.reset()
        configure_primary_key(
            strategy=IdType.SHORT_UUID,
            short_uuid_length=10,
            max_retries=7
        )
        
        # 验证配置值
        assert PrimaryKeyConfig.get_max_retries() == 7
        
        # 创建不同模型的记录，都应该使用相同的 max_retries
        model1 = CollisionTestModel(name="Model1", content="content1")
        model1.add(True)
        
        model2 = SnowflakeCollisionModel(name="Model2", content="content2")
        model2.add(True)
        
        # 两个模型都应该成功创建
        assert model1.id is not None
        assert model2.id is not None
