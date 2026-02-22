"""短UUID主键冲突重试机制测试

测试当短UUID生成器生成重复主键时，系统是否能正确检测冲突并重试。

注意：
- 这个测试文件使用 module-scoped fixture 来隔离状态
- 所有模型类都在 fixture 内动态创建，避免模块级别的状态污染
- 带历史记录的测试已移至 test_short_uuid_with_history.py
"""

import pytest
from unittest.mock import patch
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

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
)

from tests.helpers import (
    get_primary_key_strategy,
    get_short_uuid_length,
    get_max_retries,
    set_max_retries,
)


# ==================== Module-scoped Fixture ====================

# 保存原始配置，用于恢复
_original_strategy = None
_original_short_uuid_length = None
_original_max_retries = None


@pytest.fixture(scope="module", autouse=True)
def module_setup_teardown():
    """模块级别的 setup/teardown，确保测试前后状态正确"""
    global _original_strategy, _original_short_uuid_length, _original_max_retries
    
    _original_strategy = get_primary_key_strategy()
    _original_short_uuid_length = get_short_uuid_length()
    _original_max_retries = get_max_retries()
    
    # 设置为 short_uuid 策略
    PrimaryKeyConfig.reset()
    configure_primary_key(
        strategy=IdType.SHORT_UUID,
        short_uuid_length=10,
        max_retries=5
    )
    
    yield
    
    # 恢复原始配置
    configure_primary_key(
        strategy=_original_strategy,
        short_uuid_length=_original_short_uuid_length,
        max_retries=_original_max_retries
    )


# 动态创建的模型类存储
_CollisionModel = None
_CollisionModel8 = None


@pytest.fixture(scope="module")
def collision_model_class():
    """创建测试用的模型类（10位短UUID）"""
    global _CollisionModel
    if _CollisionModel is None:
        _CollisionModel = type(
            'ShortUUIDCollisionModel',
            (BaseModel,),
            {
                '__tablename__': 'test_short_uuid_collision',
                '__table_args__': {'extend_existing': True},
                '__pk_strategy__': IdType.SHORT_UUID,
                '__module__': __name__,
                'content': mapped_column(String(200), nullable=True),
            }
        )
    return _CollisionModel


@pytest.fixture(scope="module")
def collision_model_class_8():
    """创建测试用的模型类（8位短UUID）"""
    global _CollisionModel8
    if _CollisionModel8 is None:
        _CollisionModel8 = type(
            'ShortUUID8CollisionModel',
            (BaseModel,),
            {
                '__tablename__': 'test_short_uuid_8_collision',
                '__table_args__': {'extend_existing': True},
                '__pk_strategy__': IdType.SHORT_UUID,
                '__module__': __name__,
                'content': mapped_column(String(200), nullable=True),
            }
        )
    return _CollisionModel8


@pytest.fixture(scope="module")
def db_engine_and_session(collision_model_class, collision_model_class_8):
    """模块级别的数据库引擎和 session（10位短UUID）"""
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    CoreModel.query = session_scope.query_property()
    BaseModel.metadata.create_all(bind=engine)
    
    yield engine, session_scope
    
    session_scope.remove()
    engine.dispose()


@pytest.fixture
def session(db_engine_and_session):
    """每个测试的独立 session"""
    engine, session_scope = db_engine_and_session
    sess = session_scope()
    yield sess
    sess.rollback()


@pytest.fixture
def model_class(collision_model_class):
    """获取模型类"""
    return collision_model_class


@pytest.fixture
def model_class_8(collision_model_class_8):
    """获取8位模型类"""
    return collision_model_class_8


# ==================== PrimaryKeyGenerator 单元测试 ====================

class TestShortUUIDGeneratorRetry:
    """短UUID PrimaryKeyGenerator 重试机制单元测试"""
    
    def test_generate_with_no_collision(self, session, model_class):
        """测试：无冲突时直接返回"""
        generator = PrimaryKeyGenerator(max_retries=5)
        
        unique_ids = iter([f"uuid_{i:05d}" for i in range(10)])
        
        result = generator.generate_with_retry(
            model_class=model_class,
            generator_func=lambda: next(unique_ids)
        )
        
        assert result == "uuid_00000"
        assert isinstance(result, str)
    
    def test_retry_on_collision_then_success(self, session, model_class):
        """测试：短UUID冲突后重试，最终成功"""
        # 先创建一条记录
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        assert isinstance(existing_id, str)
        assert len(existing_id) == 10
        
        # 创建一个生成器：前2次返回冲突ID，第3次返回唯一ID
        call_count = [0]
        def mock_generator():
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id
            return f"new_{call_count[0]:05d}"
        
        generator = PrimaryKeyGenerator(max_retries=5)
        result = generator.generate_with_retry(
            model_class=model_class,
            generator_func=mock_generator
        )
        
        assert call_count[0] == 3
        assert result == "new_00003"
        assert result != existing_id
    
    def test_fail_after_max_retries(self, session, model_class):
        """测试：超过最大重试次数后失败"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        def always_collision_generator():
            return existing_id
        
        generator = PrimaryKeyGenerator(max_retries=3)
        
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_with_retry(
                model_class=model_class,
                generator_func=always_collision_generator,
                max_retries=3
            )
        
        assert "3次尝试后仍然冲突" in str(exc_info.value)
    
    def test_retry_count_matches_max_retries(self, session, model_class):
        """测试：重试次数与 max_retries 配置一致"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        call_count = [0]
        def counting_generator():
            call_count[0] += 1
            return existing_id
        
        max_retries = 7
        generator = PrimaryKeyGenerator(max_retries=max_retries)
        
        with pytest.raises(RuntimeError):
            generator.generate_with_retry(
                model_class=model_class,
                generator_func=counting_generator,
                max_retries=max_retries
            )
        
        assert call_count[0] == max_retries


# ==================== 不带历史记录的短UUID冲突测试 ====================

class TestShortUUIDCollisionWithoutHistory:
    """不带历史记录的短UUID主键冲突测试"""
    
    def test_short_uuid_collision_retry_basic(self, session, model_class):
        """测试：短UUID策略基本冲突重试"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        assert isinstance(existing_id, str)
        assert len(existing_id) == 10
        
        call_count = [0]
        original_generate = generate_short_uuid
        
        def mock_short_uuid(length=10):
            call_count[0] += 1
            if call_count[0] <= 2:
                return existing_id
            return original_generate(length)
        
        with patch('yweb.orm.primary_key_generators.generate_short_uuid', mock_short_uuid):
            new_model = model_class(name="New", content="new content")
            session.add(new_model)
            session.commit()
            
            assert new_model.id is not None
            assert new_model.id != existing_id
            assert isinstance(new_model.id, str)
    
    def test_short_uuid_collision_fail_exceeds_max_retries(self, session, model_class):
        """测试：短UUID冲突次数超过 max_retries 时失败"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        def always_collision(length=10):
            return existing_id
        
        # 临时修改 max_retries
        old_max_retries = get_max_retries()
        set_max_retries(PrimaryKeyConfig, 2)
        
        try:
            with patch('yweb.orm.primary_key_generators.generate_short_uuid', always_collision):
                with pytest.raises(RuntimeError) as exc_info:
                    new_model = model_class(name="New", content="new content")
                    session.add(new_model)
                    session.commit()
                
                assert "2次尝试后仍然冲突" in str(exc_info.value)
        finally:
            set_max_retries(PrimaryKeyConfig, old_max_retries)
    
    def test_short_uuid_multiple_collisions_then_success(self, session, model_class):
        """测试：短UUID多次冲突后最终成功"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        call_count = [0]
        original_generate = generate_short_uuid
        
        def mock_short_uuid(length=10):
            call_count[0] += 1
            if call_count[0] <= 4:
                return existing_id
            return original_generate(length)
        
        with patch('yweb.orm.primary_key_generators.generate_short_uuid', mock_short_uuid):
            new_model = model_class(name="New", content="new content")
            session.add(new_model)
            session.commit()
            
            assert new_model.id is not None
            assert new_model.id != existing_id
            assert call_count[0] == 5


# ==================== 边界情况测试 ====================

class TestShortUUIDCollisionEdgeCases:
    """短UUID冲突重试边界情况测试"""
    
    def test_max_retries_zero(self, session, model_class):
        """测试：max_retries=0 时第一次冲突就失败"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        def always_collision():
            return existing_id
        
        generator = PrimaryKeyGenerator(max_retries=0)
        
        with pytest.raises(RuntimeError) as exc_info:
            generator.generate_with_retry(
                model_class=model_class,
                generator_func=always_collision,
                max_retries=0
            )
        
        assert "0次尝试" in str(exc_info.value)
    
    def test_max_retries_one(self, session, model_class):
        """测试：max_retries=1 时只有一次机会"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        call_count = [0]
        def collision_then_unique():
            call_count[0] += 1
            if call_count[0] == 1:
                return existing_id
            return f"unique{call_count[0]:04d}"
        
        generator = PrimaryKeyGenerator(max_retries=1)
        
        with pytest.raises(RuntimeError):
            generator.generate_with_retry(
                model_class=model_class,
                generator_func=collision_then_unique,
                max_retries=1
            )
    
    def test_first_attempt_success(self, session, model_class):
        """测试：第一次就成功（无冲突）"""
        call_count = [0]
        def unique_generator():
            call_count[0] += 1
            return f"unique{call_count[0]:04d}"
        
        generator = PrimaryKeyGenerator(max_retries=5)
        result = generator.generate_with_retry(
            model_class=model_class,
            generator_func=unique_generator
        )
        
        assert call_count[0] == 1
        assert result == "unique0001"
    
    def test_last_attempt_success(self, session, model_class):
        """测试：最后一次尝试成功"""
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        max_retries = 5
        call_count = [0]
        
        def collision_until_last():
            call_count[0] += 1
            if call_count[0] < max_retries:
                return existing_id
            return "unique_last"
        
        generator = PrimaryKeyGenerator(max_retries=max_retries)
        result = generator.generate_with_retry(
            model_class=model_class,
            generator_func=collision_until_last,
            max_retries=max_retries
        )
        
        assert call_count[0] == max_retries
        assert result == "unique_last"
    
    def test_short_uuid_length_variations(self, session):
        """测试：不同长度的短UUID"""
        for length in [8, 10, 12, 16]:
            uuid = generate_short_uuid(length)
            assert len(uuid) == length
            assert isinstance(uuid, str)
            assert uuid.isalnum()


# ==================== 并发场景测试 ====================

class TestShortUUIDConcurrentCollision:
    """短UUID并发场景下的冲突测试"""
    
    def test_multiple_records_same_session(self, session, model_class):
        """测试：同一 session 中创建多条记录"""
        models = []
        for i in range(10):
            model = model_class(name=f"Record_{i}", content=f"content_{i}")
            session.add(model)
            session.commit()
            models.append(model)
        
        ids = [m.id for m in models]
        assert len(ids) == len(set(ids)), "所有ID应该唯一"
        
        for model_id in ids:
            assert isinstance(model_id, str)
            assert len(model_id) == 10


# ==================== 配置验证测试 ====================

class TestShortUUIDRetryConfiguration:
    """短UUID重试配置测试"""
    
    def test_current_short_uuid_length(self):
        """测试：当前短UUID长度配置"""
        # 由于 module fixture 已设置为 10
        assert PrimaryKeyConfig.get_short_uuid_length() == 10
    
    def test_current_max_retries(self):
        """测试：当前 max_retries 配置"""
        # 由于 module fixture 已设置为 5
        assert PrimaryKeyConfig.get_max_retries() == 5
    
    def test_short_uuid_length_affects_id_generation(self, session, model_class):
        """测试：短UUID长度配置影响ID生成"""
        model1 = model_class(name="Model1", content="content1")
        session.add(model1)
        session.commit()
        assert len(model1.id) == 10
