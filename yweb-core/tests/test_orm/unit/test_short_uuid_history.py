"""短 UUID + 历史记录功能测试

这个测试文件专门测试短 UUID（字符串类型）主键与历史记录功能的兼容性。

核心验证点：
1. Transaction 表使用字符串类型主键（与业务模型一致）
2. 历史记录表正确继承字符串类型主键
3. 历史记录中的 transaction_id 是字符串类型
4. 冲突重试机制与历史记录正常工作

正确的初始化顺序（重要！）：
1. configure_primary_key()      - 配置主键策略为 short_uuid
2. init_versioning()            - 初始化版本化（Transaction 表会使用短 UUID）
3. 定义模型类（设置 enable_history = True）
4. configure_mappers()          - 配置 mappers
"""

import pytest
from unittest.mock import patch
from sqlalchemy import String
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_primary_key,
    PrimaryKeyConfig,
    IdType,
    init_versioning,
    get_history_count,
    get_history,
)
from yweb.orm.primary_key_generators import generate_short_uuid


# 模型类会在 fixture 中动态创建
_HistoryModel = None


@pytest.fixture(scope="module")
def short_uuid_history_env():
    """模块级别的 fixture - 设置短 UUID + 历史记录环境
    
    使用 module scope 确保整个测试模块只初始化一次，
    避免测试之间的状态污染。
    """
    global _HistoryModel
    from sqlalchemy_history import versioning_manager
    
    # 1. 重置配置
    PrimaryKeyConfig.reset()
    
    # 2. 配置主键策略为 short_uuid（必须在 init_versioning 之前）
    configure_primary_key(
        strategy=IdType.SHORT_UUID,
        short_uuid_length=10,
        max_retries=5
    )
    
    # 3. 初始化版本化
    init_versioning()
    
    # 4. 动态创建模型类（使用 enable_history = True）
    # 使用唯一名称避免与其他测试模块的 versioning_manager 冲突
    _HistoryModel = type(
        'ShortUUIDWithHistoryTestModel',
        (BaseModel,),
        {
            '__tablename__': 'short_uuid_with_history_test_model',
            '__pk_strategy__': IdType.SHORT_UUID,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    # 5. 配置 mappers
    configure_mappers()
    
    # 6. 创建数据库和表
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    CoreModel.query = session_scope.query_property()
    BaseModel.metadata.create_all(bind=engine)
    
    # 创建版本化相关的表
    if versioning_manager.transaction_cls and hasattr(versioning_manager.transaction_cls, '__table__'):
        versioning_manager.transaction_cls.__table__.create(bind=engine, checkfirst=True)
    
    for table_key, version_cls in versioning_manager.version_class_map.items():
        if version_cls and hasattr(version_cls, '__table__'):
            version_cls.__table__.create(bind=engine, checkfirst=True)
    
    yield {
        'engine': engine,
        'session_scope': session_scope,
        'model_class': _HistoryModel,
        'versioning_manager': versioning_manager,
    }
    
    # 清理
    session_scope.remove()
    engine.dispose()
    PrimaryKeyConfig.reset()
    _HistoryModel = None


@pytest.fixture
def session(short_uuid_history_env):
    """为每个测试创建新的 session"""
    session_scope = short_uuid_history_env['session_scope']
    session = session_scope()
    yield session
    session.rollback()


@pytest.fixture
def model_class(short_uuid_history_env):
    """获取模型类"""
    return short_uuid_history_env['model_class']


@pytest.fixture
def versioning_manager(short_uuid_history_env):
    """获取版本管理器"""
    return short_uuid_history_env['versioning_manager']


class TestShortUUIDWithHistory:
    """短 UUID + 历史记录功能测试"""
    
    def test_model_id_is_string(self, session, model_class):
        """测试：模型 ID 是字符串类型"""
        model = model_class(name="Test", content="test content")
        session.add(model)
        session.commit()
        
        assert model.id is not None
        assert isinstance(model.id, str), f"ID 应该是字符串，实际是 {type(model.id)}"
        assert len(model.id) == 10, f"短 UUID 应该是 10 位，实际是 {len(model.id)}"
    
    def test_history_created(self, session, model_class):
        """测试：创建记录后有历史记录"""
        model = model_class(name="Test", content="test content")
        session.add(model)
        session.commit()
        
        count = get_history_count(model_class, model.id, session=session)
        assert count >= 1, "创建记录后应该有历史记录"
    
    def test_history_id_is_string(self, session, model_class):
        """测试：历史记录中的 ID 是字符串类型"""
        model = model_class(name="Test", content="test content")
        session.add(model)
        session.commit()
        
        history = get_history(model_class, model.id, session=session)
        assert history is not None
        assert len(history) >= 1
        
        for record in history:
            assert isinstance(record.get('id'), str), "历史记录中的 ID 应该是字符串"
    
    def test_transaction_table_exists(self, versioning_manager):
        """测试：Transaction 表存在且有主键列"""
        transaction_cls = versioning_manager.transaction_cls
        assert transaction_cls is not None
        assert hasattr(transaction_cls, '__table__')
        
        # Transaction 表应该有 id 列
        assert 'id' in transaction_cls.__table__.c
        id_column = transaction_cls.__table__.c.id
        assert id_column.primary_key, "Transaction 表的 id 列应该是主键"
    
    def test_collision_retry_with_history(self, session, model_class):
        """测试：冲突重试与历史记录正常工作"""
        # 创建一条记录
        existing = model_class(name="Existing", content="content")
        session.add(existing)
        session.commit()
        existing_id = existing.id
        
        # 验证是字符串类型
        assert isinstance(existing_id, str)
        
        # 模拟冲突
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
            
            # 新记录也应该有历史
            new_count = get_history_count(model_class, new_model.id, session=session)
            assert new_count >= 1, "新记录应该有历史记录"
    
    def test_multiple_records(self, session, model_class):
        """测试：创建多条记录，ID 唯一且都是字符串"""
        models = []
        for i in range(5):
            model = model_class(name=f"Record_{i}", content=f"content_{i}")
            session.add(model)
            session.commit()
            models.append(model)
        
        # 验证 ID 唯一
        ids = [m.id for m in models]
        assert len(ids) == len(set(ids)), "所有 ID 应该唯一"
        
        # 验证都是字符串
        for model_id in ids:
            assert isinstance(model_id, str)
            assert len(model_id) == 10
        
        # 验证都有历史
        for model in models:
            count = get_history_count(model_class, model.id, session=session)
            assert count >= 1, f"记录 {model.name} 应该有历史记录"
    
    def test_update_creates_history(self, session, model_class):
        """测试：更新记录会创建新的历史记录"""
        model = model_class(name="Test", content="original")
        session.add(model)
        session.commit()
        
        initial_count = get_history_count(model_class, model.id, session=session)
        
        # 更新记录
        model.content = "updated"
        session.commit()
        
        final_count = get_history_count(model_class, model.id, session=session)
        assert final_count > initial_count, "更新后历史记录数应该增加"
