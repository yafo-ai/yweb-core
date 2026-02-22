"""主键策略与历史记录兼容性测试

测试不同主键策略是否都能正确支持 sqlalchemy-history 的历史记录功能。

测试覆盖的主键策略：
1. auto_increment - 整数自增（应用层生成，内部使用雪花算法）
2. short_uuid - 短UUID（10位字符串）
3. uuid - 完整UUID（36位字符串）
4. snowflake - 雪花算法（大整数）
5. custom - 自定义生成器

每种策略测试：
- 创建记录时历史记录是否正确生成
- 更新记录时历史记录是否增加
- 历史记录中 id 字段值是否正确

重要！正确的初始化顺序：
1. configure_primary_key()  - 配置主键策略
2. init_versioning()        - 初始化版本化（开始监听 mapper 事件）
3. 动态创建模型类           - 此时版本化系统会监听到
4. configure_mappers()      - 触发版本类创建
"""

import random

import pytest
from sqlalchemy import String, text
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    configure_primary_key,
    PrimaryKeyConfig,
    IdType,
    init_versioning,
    get_history,
    get_history_count,
    get_version_class,
)


# ==================== 全局变量 - 存储动态创建的模型类 ====================
_AutoIncrementHistoryModel = None
_ShortUUIDHistoryModel = None
_FullUUIDHistoryModel = None
_SnowflakeHistoryModel = None
_CustomPKHistoryModel = None


# ==================== 模块级别 Fixture ====================

@pytest.fixture(scope="module")
def pk_strategy_history_env():
    """模块级别的 fixture - 设置所有主键策略 + 历史记录环境
    
    使用 module scope 确保整个测试模块只初始化一次。
    
    重要：模型类必须在 init_versioning() 之后动态创建，
    这样版本化系统才能正确监听并为它们创建版本类。
    """
    global _AutoIncrementHistoryModel, _ShortUUIDHistoryModel
    global _FullUUIDHistoryModel, _SnowflakeHistoryModel, _CustomPKHistoryModel
    
    from sqlalchemy_history import versioning_manager
    
    # 1. 重置配置
    PrimaryKeyConfig.reset()
    
    # 2. 配置所有主键策略参数
    configure_primary_key(
        strategy=IdType.AUTO_INCREMENT,  # 默认策略
        short_uuid_length=10,
        snowflake_worker_id=1,
        snowflake_datacenter_id=1,
        custom_generator=lambda: f"CUSTOM_{random.randint(10**9, 10**10-1)}",
        max_retries=5
    )
    
    # 3. 初始化版本化（必须在模型定义之前！）
    init_versioning()
    
    # 4. 动态创建模型类（版本化系统会监听这些类的创建）
    # 使用 enable_history = True 代替 __versioned__ = {}
    _AutoIncrementHistoryModel = type(
        'AutoIncrementHistoryModel',
        (BaseModel,),
        {
            '__tablename__': 'test_pk_history_auto_increment',
            '__pk_strategy__': IdType.AUTO_INCREMENT,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    _ShortUUIDHistoryModel = type(
        'ShortUUIDHistoryModel',
        (BaseModel,),
        {
            '__tablename__': 'test_pk_history_short_uuid',
            '__pk_strategy__': IdType.SHORT_UUID,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    _FullUUIDHistoryModel = type(
        'FullUUIDHistoryModel',
        (BaseModel,),
        {
            '__tablename__': 'test_pk_history_full_uuid',
            '__pk_strategy__': IdType.UUID,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    _SnowflakeHistoryModel = type(
        'SnowflakeHistoryModel',
        (BaseModel,),
        {
            '__tablename__': 'test_pk_history_snowflake',
            '__pk_strategy__': IdType.SNOWFLAKE,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    _CustomPKHistoryModel = type(
        'CustomPKHistoryModel',
        (BaseModel,),
        {
            '__tablename__': 'test_pk_history_custom',
            '__pk_strategy__': IdType.CUSTOM,
            '__module__': __name__,
            'enable_history': True,
            'content': mapped_column(String(200), nullable=True),
        }
    )
    
    # 5. 配置 mappers（触发版本类创建）
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
        'versioning_manager': versioning_manager,
        'models': {
            'auto_increment': _AutoIncrementHistoryModel,
            'short_uuid': _ShortUUIDHistoryModel,
            'uuid': _FullUUIDHistoryModel,
            'snowflake': _SnowflakeHistoryModel,
            'custom': _CustomPKHistoryModel,
        }
    }
    
    # 清理
    session_scope.remove()
    engine.dispose()
    PrimaryKeyConfig.reset()
    
    _AutoIncrementHistoryModel = None
    _ShortUUIDHistoryModel = None
    _FullUUIDHistoryModel = None
    _SnowflakeHistoryModel = None
    _CustomPKHistoryModel = None


@pytest.fixture
def session(pk_strategy_history_env):
    """为每个测试创建新的 session"""
    session_scope = pk_strategy_history_env['session_scope']
    session = session_scope()
    yield session
    session.rollback()


@pytest.fixture
def models(pk_strategy_history_env):
    """获取所有模型类"""
    return pk_strategy_history_env['models']


# ==================== auto_increment 策略测试 ====================

class TestAutoIncrementWithHistory:
    """整数自增主键 + 历史记录测试
    
    验证：auto_increment 策略（内部使用雪花算法）能正确支持历史记录
    """
    
    def test_create_generates_history(self, session, models):
        """测试：创建记录时自动生成历史"""
        model_class = models['auto_increment']
        
        model = model_class(name="TestAuto", content="Content1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 验证 id 已生成
        assert model_id is not None
        assert isinstance(model_id, int), f"auto_increment id 应该是整数，实际是 {type(model_id)}"
        
        # 验证历史记录已创建
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 1, "创建后应该有至少1条历史记录"
    
    def test_update_increases_history(self, session, models):
        """测试：更新记录时历史数量增加"""
        model_class = models['auto_increment']
        
        model = model_class(name="V1", content="Original")
        session.add(model)
        session.commit()
        
        model_id = model.id
        initial_count = get_history_count(model_class, model_id, session=session)
        
        # 更新记录
        model.name = "V2"
        model.content = "Updated"
        session.commit()
        
        new_count = get_history_count(model_class, model_id, session=session)
        assert new_count > initial_count, "更新后历史记录数量应该增加"
    
    def test_history_contains_correct_id(self, session, models):
        """测试：历史记录中 id 字段值正确"""
        model_class = models['auto_increment']
        
        model = model_class(name="Test", content="Content")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 获取历史记录
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        assert len(history) >= 1
        
        # 验证历史记录中的 id 与原记录一致
        for record in history:
            assert record.get('id') == model_id, \
                f"历史记录中的 id 应该是 {model_id}，实际是 {record.get('id')}"


# ==================== short_uuid 策略测试 ====================

class TestShortUUIDWithHistory:
    """短UUID主键 + 历史记录测试"""
    
    def test_create_generates_history(self, session, models):
        """测试：创建记录时自动生成历史"""
        model_class = models['short_uuid']
        
        model = model_class(name="TestShortUUID", content="Content1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 验证 id 已生成
        assert model_id is not None
        assert isinstance(model_id, str), f"short_uuid id 应该是字符串，实际是 {type(model_id)}"
        assert len(model_id) == 10, f"short_uuid 长度应该是 10，实际是 {len(model_id)}"
        
        # 验证历史记录已创建
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 1, "创建后应该有至少1条历史记录"
    
    def test_update_increases_history(self, session, models):
        """测试：更新记录时历史数量增加"""
        model_class = models['short_uuid']
        
        model = model_class(name="V1", content="Original")
        session.add(model)
        session.commit()
        
        model_id = model.id
        initial_count = get_history_count(model_class, model_id, session=session)
        
        model.name = "V2"
        session.commit()
        
        new_count = get_history_count(model_class, model_id, session=session)
        assert new_count > initial_count, "更新后历史记录数量应该增加"
    
    def test_history_contains_correct_id(self, session, models):
        """测试：历史记录中 id 字段值正确"""
        model_class = models['short_uuid']
        
        model = model_class(name="Test", content="Content")
        session.add(model)
        session.commit()
        
        model_id = model.id
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        for record in history:
            assert record.get('id') == model_id, \
                f"历史记录中的 id 应该是 {model_id}，实际是 {record.get('id')}"


# ==================== uuid 策略测试 ====================

class TestFullUUIDWithHistory:
    """完整UUID主键 + 历史记录测试"""
    
    def test_create_generates_history(self, session, models):
        """测试：创建记录时自动生成历史"""
        model_class = models['uuid']
        
        model = model_class(name="TestFullUUID", content="Content1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 验证 id 已生成
        assert model_id is not None
        assert isinstance(model_id, str), f"uuid id 应该是字符串，实际是 {type(model_id)}"
        assert len(model_id) == 36, f"uuid 长度应该是 36，实际是 {len(model_id)}"
        assert "-" in model_id, "uuid 应该包含连字符"
        
        # 验证历史记录已创建
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 1, "创建后应该有至少1条历史记录"
    
    def test_update_increases_history(self, session, models):
        """测试：更新记录时历史数量增加"""
        model_class = models['uuid']
        
        model = model_class(name="V1", content="Original")
        session.add(model)
        session.commit()
        
        model_id = model.id
        initial_count = get_history_count(model_class, model_id, session=session)
        
        model.name = "V2"
        session.commit()
        
        new_count = get_history_count(model_class, model_id, session=session)
        assert new_count > initial_count, "更新后历史记录数量应该增加"
    
    def test_history_contains_correct_id(self, session, models):
        """测试：历史记录中 id 字段值正确"""
        model_class = models['uuid']
        
        model = model_class(name="Test", content="Content")
        session.add(model)
        session.commit()
        
        model_id = model.id
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        for record in history:
            assert record.get('id') == model_id, \
                f"历史记录中的 id 应该是 {model_id}，实际是 {record.get('id')}"


# ==================== snowflake 策略测试 ====================

class TestSnowflakeWithHistory:
    """雪花算法主键 + 历史记录测试"""
    
    def test_create_generates_history(self, session, models):
        """测试：创建记录时自动生成历史"""
        model_class = models['snowflake']
        
        model = model_class(name="TestSnowflake", content="Content1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 验证 id 已生成
        assert model_id is not None
        assert isinstance(model_id, int), f"snowflake id 应该是整数，实际是 {type(model_id)}"
        assert model_id > 1_000_000_000_000, f"snowflake id 应该是大整数，实际是 {model_id}"
        
        # 验证历史记录已创建
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 1, "创建后应该有至少1条历史记录"
    
    def test_update_increases_history(self, session, models):
        """测试：更新记录时历史数量增加"""
        model_class = models['snowflake']
        
        model = model_class(name="V1", content="Original")
        session.add(model)
        session.commit()
        
        model_id = model.id
        initial_count = get_history_count(model_class, model_id, session=session)
        
        model.name = "V2"
        session.commit()
        
        new_count = get_history_count(model_class, model_id, session=session)
        assert new_count > initial_count, "更新后历史记录数量应该增加"
    
    def test_history_contains_correct_id(self, session, models):
        """测试：历史记录中 id 字段值正确"""
        model_class = models['snowflake']
        
        model = model_class(name="Test", content="Content")
        session.add(model)
        session.commit()
        
        model_id = model.id
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        for record in history:
            assert record.get('id') == model_id, \
                f"历史记录中的 id 应该是 {model_id}，实际是 {record.get('id')}"


# ==================== custom 策略测试 ====================

class TestCustomPKWithHistory:
    """自定义主键 + 历史记录测试"""
    
    def test_create_generates_history(self, session, models):
        """测试：创建记录时自动生成历史"""
        model_class = models['custom']
        
        model = model_class(name="TestCustom", content="Content1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 验证 id 已生成
        assert model_id is not None
        assert isinstance(model_id, str), f"custom id 应该是字符串，实际是 {type(model_id)}"
        assert model_id.startswith("CUSTOM_"), f"custom id 应该以 CUSTOM_ 开头，实际是 {model_id}"
        
        # 验证历史记录已创建
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 1, "创建后应该有至少1条历史记录"
    
    def test_update_increases_history(self, session, models):
        """测试：更新记录时历史数量增加"""
        model_class = models['custom']
        
        model = model_class(name="V1", content="Original")
        session.add(model)
        session.commit()
        
        model_id = model.id
        initial_count = get_history_count(model_class, model_id, session=session)
        
        model.name = "V2"
        session.commit()
        
        new_count = get_history_count(model_class, model_id, session=session)
        assert new_count > initial_count, "更新后历史记录数量应该增加"
    
    def test_history_contains_correct_id(self, session, models):
        """测试：历史记录中 id 字段值正确"""
        model_class = models['custom']
        
        model = model_class(name="Test", content="Content")
        session.add(model)
        session.commit()
        
        model_id = model.id
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        for record in history:
            assert record.get('id') == model_id, \
                f"历史记录中的 id 应该是 {model_id}，实际是 {record.get('id')}"


# ==================== 综合对比测试 ====================

class TestAllStrategiesHistoryComparison:
    """所有策略的历史记录功能综合对比测试"""
    
    def test_all_strategies_create_history_successfully(self, session, models):
        """测试：所有策略都能成功创建历史记录"""
        for strategy_name, model_class in models.items():
            model = model_class(name=f"Test-{strategy_name}", content=f"{strategy_name} content")
            session.add(model)
            session.commit()
            
            model_id = model.id
            
            # 验证 id 已生成
            assert model_id is not None, f"{strategy_name} 的 id 不应该为 None"
            
            # 验证历史记录已创建
            count = get_history_count(model_class, model_id, session=session)
            assert count >= 1, f"{strategy_name} 创建后应该有至少1条历史记录"
    
    def test_all_strategies_update_increases_history(self, session, models):
        """测试：所有策略更新后历史记录都会增加"""
        for strategy_name, model_class in models.items():
            model = model_class(name=f"Test-{strategy_name}", content="v1")
            session.add(model)
            session.commit()
            
            model_id = model.id
            initial_count = get_history_count(model_class, model_id, session=session)
            
            # 更新
            model.content = "v2"
            session.commit()
            
            new_count = get_history_count(model_class, model_id, session=session)
            
            assert new_count > initial_count, \
                f"{strategy_name} 更新后历史记录数量应该增加"
    
    def test_all_strategies_history_id_integrity(self, session, models):
        """测试：所有策略的历史记录中 id 字段完整性"""
        for strategy_name, model_class in models.items():
            model = model_class(name=f"Test-{strategy_name}", content="content")
            session.add(model)
            session.commit()
            
            model_id = model.id
            
            # 获取历史记录
            history = get_history(model_class, model_id, session=session)
            
            assert history is not None, \
                f"策略 {strategy_name} 应该有历史记录"
            assert len(history) >= 1, \
                f"策略 {strategy_name} 应该有至少1条历史记录"
            
            # 验证所有历史记录的 id 都正确
            for i, record in enumerate(history):
                record_id = record.get('id')
                assert record_id == model_id, \
                    f"策略 {strategy_name} 第 {i+1} 条历史记录的 id 应该是 {model_id}，实际是 {record_id}"


# ==================== 历史表结构验证测试 ====================

class TestHistoryTableStructure:
    """历史表结构验证测试"""
    
    def test_version_class_exists_for_all_strategies(self, session, models):
        """测试：所有策略的模型都有对应的版本类"""
        for strategy_name, model_class in models.items():
            version_class = get_version_class(model_class)
            
            assert version_class is not None, \
                f"{strategy_name} 应该有对应的版本类"
            assert 'Version' in version_class.__name__, \
                f"{strategy_name} 的版本类名应该包含 'Version'"
    
    def test_version_class_has_required_columns(self, session, models):
        """测试：版本类有必要的列"""
        for strategy_name, model_class in models.items():
            version_class = get_version_class(model_class)
            
            # 检查必要的列
            assert hasattr(version_class, 'id'), \
                f"{strategy_name} 的版本类应该有 id 列"
            assert hasattr(version_class, 'transaction_id'), \
                f"{strategy_name} 的版本类应该有 transaction_id 列"
            assert hasattr(version_class, 'operation_type'), \
                f"{strategy_name} 的版本类应该有 operation_type 列"
    
    def test_history_table_physically_exists(self, session, models):
        """测试：历史表物理存在于数据库中"""
        for strategy_name, model_class in models.items():
            version_class = get_version_class(model_class)
            table_name = version_class.__table__.name
            
            # 查询 sqlite_master 验证表存在
            result = session.execute(
                text("SELECT name FROM sqlite_master WHERE type='table' AND name=:name"),
                {"name": table_name}
            )
            row = result.fetchone()
            
            assert row is not None, \
                f"{strategy_name} 的历史表 {table_name} 应该物理存在"


# ==================== 边界情况测试 ====================

class TestEdgeCases:
    """边界情况测试"""
    
    def test_multiple_updates_generate_multiple_history_records(self, session, models):
        """测试：多次更新生成多条历史记录"""
        model_class = models['snowflake']
        
        model = model_class(name="MultiUpdate", content="v1")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 执行多次更新
        for i in range(5):
            model.content = f"v{i+2}"
            session.commit()
        
        # 验证历史记录数量
        count = get_history_count(model_class, model_id, session=session)
        assert count >= 6, f"多次更新后应该有至少6条历史记录，实际有 {count} 条"
    
    def test_history_preserves_all_versions(self, session, models):
        """测试：历史记录保留所有版本"""
        model_class = models['short_uuid']
        
        model = model_class(name="VersionTest", content="initial")
        session.add(model)
        session.commit()
        
        model_id = model.id
        
        # 更新3次
        versions = ["v2", "v3", "v4"]
        for v in versions:
            model.content = v
            session.commit()
        
        # 获取所有历史记录
        history = get_history(model_class, model_id, session=session)
        
        assert history is not None
        assert len(history) >= 4, f"应该有至少4条历史记录，实际有 {len(history)} 条"
    
    def test_manual_id_with_history(self, session, models):
        """测试：手动指定 id 时历史记录正常工作"""
        model_class = models['uuid']
        
        # 手动指定一个 UUID
        import uuid
        manual_id = str(uuid.uuid4())
        
        model = model_class(name="ManualID", content="content")
        model.id = manual_id
        session.add(model)
        session.commit()
        
        # 验证 id 是我们指定的
        assert model.id == manual_id
        
        # 验证历史记录正确
        history = get_history(model_class, manual_id, session=session)
        assert history is not None
        assert len(history) >= 1
        assert history[0].get('id') == manual_id
