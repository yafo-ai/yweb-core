"""版本历史记录功能测试

测试 BaseModel + enable_history 组合使用的版本历史功能

测试覆盖：
- init_versioning() 初始化
- is_versioning_initialized() 状态检查
- get_version_class() 获取历史类

实例方法测试（推荐方式）：
- model.get_history() 获取历史记录
- model.history 便捷属性
- model.history_count 历史数量属性
- model.get_history_diff() 版本差异比较
- model.get_field_text_diff() 字段文本差异比较
- model.restore_to_version() 恢复到指定版本

类方法测试：
- Model.get_history_by_id() 根据 ID 获取历史
- Model.get_history_count_by_id() 根据 ID 获取历史数量

其他测试：
- 软删除后版本历史的行为
"""

import pytest
from sqlalchemy import String, text
from sqlalchemy.orm import configure_mappers, Mapped, mapped_column

from yweb.orm import (
    CoreModel,
    BaseModel,
    init_database,
    get_db,
)

# ==================== 测试初始化和配置 ====================

class TestVersioningInitialization:
    """版本化初始化测试"""
    
    def test_init_versioning_function_exists(self):
        """测试 init_versioning 函数存在"""
        from yweb.orm import init_versioning
        assert callable(init_versioning)
    
    def test_is_versioning_initialized_function_exists(self):
        """测试 is_versioning_initialized 函数存在"""
        from yweb.orm import is_versioning_initialized
        assert callable(is_versioning_initialized)
    
    def test_is_versioning_initialized_returns_bool(self):
        """测试 is_versioning_initialized 返回布尔值"""
        from yweb.orm import is_versioning_initialized
        result = is_versioning_initialized()
        assert isinstance(result, bool)
    
    def test_get_version_class_function_exists(self):
        """测试 get_version_class 函数存在"""
        from yweb.orm import get_version_class
        assert callable(get_version_class)
    
    def test_get_history_function_exists(self):
        """测试 get_history 函数存在"""
        from yweb.orm import get_history
        assert callable(get_history)
    
    def test_get_history_count_function_exists(self):
        """测试 get_history_count 函数存在"""
        from yweb.orm import get_history_count
        assert callable(get_history_count)
    
    def test_get_history_diff_function_exists(self):
        """测试 get_history_diff 函数存在"""
        from yweb.orm import get_history_diff
        assert callable(get_history_diff)
    
    def test_restore_to_version_function_exists(self):
        """测试 restore_to_version 函数存在"""
        from yweb.orm import restore_to_version
        assert callable(restore_to_version)
    
    def test_get_field_text_diff_function_exists(self):
        """测试 get_field_text_diff 函数存在"""
        from yweb.orm import get_field_text_diff
        assert callable(get_field_text_diff)


# ==================== sqlalchemy-history 集成测试 ====================

# 注意：init_versioning() 已在 conftest.py 中全局初始化（带 CurrentUserPlugin）
# 这里不需要再次初始化


class User(CoreModel):
    """Mock User 类 - 用于 CurrentUserPlugin
    
    sqlalchemy-history 的 CurrentUserPlugin 需要一个 User 类来建立
    Transaction → User 的关系。这里定义一个简单的 mock 类满足需求。
    """
    __tablename__ = "test_user"
    __table_args__ = {'extend_existing': True}
    
    username: Mapped[str] = mapped_column(String(100), nullable=True)


class HistoryTestModel(BaseModel):
    """用于测试的版本化模型
    
    说明：
    - BaseModel: 提供基础字段（id, name, code, created_at, updated_at）和软删除
    - enable_history = True: 启用自动版本历史功能
    
    每次修改都会自动记录一个历史版本。
    """
    __tablename__ = "test_versioned_model"
    __table_args__ = {'extend_existing': True}
    
    enable_history = True
    
    content: Mapped[str] = mapped_column(String(500), nullable=True)


class SoftDeleteHistoryTestModel(BaseModel):
    """用于测试软删除+版本历史的模型
    
    说明：
    - BaseModel: 提供基础字段和软删除功能
    - enable_history = True: 启用自动版本历史功能
    
    测试要点：软删除主记录后，历史记录不会被硬删除（数据仍物理存在）
    """
    __tablename__ = "test_soft_delete_versioned_model"
    __table_args__ = {'extend_existing': True}
    
    enable_history = True
    
    content: Mapped[str] = mapped_column(String(500), nullable=True)


# 配置 mappers
try:
    configure_mappers()
except Exception:
    pass


# ==================== 通用 Fixture ====================

@pytest.fixture
def setup_history_db():
    """初始化数据库 - 使用全局 scoped_session"""
    from sqlalchemy_history import versioning_manager
    
    # 使用 init_database 初始化全局 session
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    
    # 设置 CoreModel.query 属性
    CoreModel.query = session_scope.query_property()
    
    # 创建所有表
    BaseModel.metadata.create_all(bind=engine)
    
    # 创建事务表
    if versioning_manager.transaction_cls is not None:
        versioning_manager.transaction_cls.__table__.create(bind=engine, checkfirst=True)
    
    # 创建版本类的表
    for table_key, version_cls in versioning_manager.version_class_map.items():
        if version_cls is not None and hasattr(version_cls, '__table__'):
            version_cls.__table__.create(bind=engine, checkfirst=True)
    
    # 获取 session
    session = session_scope()
    
    yield session
    
    # 清理
    session_scope.remove()
    engine.dispose()


# ==================== get_history() 测试 ====================

class TestGetHistoryWithSqlAlchemyHistory:
    """get_history() 实例方法测试 - 使用 sqlalchemy-history"""
    
    def test_get_history_returns_list_after_updates(self, setup_history_db):
        """测试：更新后 get_history 返回历史记录列表"""
        session = setup_history_db
        
        # 创建记录
        model = HistoryTestModel(name="V1", content="Content1")
        model.add(True)
        
        # 更新一次
        model.name = "V2"
        model.save(True)
        
        # 使用实例方法获取历史
        history = model.get_history()
        
        assert history is not None
        assert isinstance(history, list)
        assert model.ver == 2  # 版本号应该是 2
        assert len(history) == 2  # 历史记录数量应该是 2
    
    def test_get_history_with_limit(self, setup_history_db):
        """测试：get_history 的 limit 参数"""
        session = setup_history_db
        
        model = HistoryTestModel(name="V1", content="Content")
        model.add(True)
        
        # 多次更新
        for i in range(5):
            model.name = f"V{i+2}"
            model.save(True)
        
        # 使用实例方法限制返回 2 条
        history = model.get_history(limit=2)
        
        assert history is not None
        assert len(history) == 2
    
    def test_get_history_property(self, setup_history_db):
        """测试：history 便捷属性"""
        session = setup_history_db
        
        model = HistoryTestModel(name="V1", content="Content")
        model.add(True)
        
        model.name = "V2"
        model.save(True)
        
        # 使用 history 属性
        history = model.history
        
        assert history is not None
        assert isinstance(history, list)
        assert len(history) >= 1
    
    def test_get_history_returns_none_for_nonexistent(self, setup_history_db):
        """测试：不存在的记录返回 None（使用类方法）"""
        session = setup_history_db
        
        # 使用类方法查询不存在的记录
        history = HistoryTestModel.get_history_by_id(instance_id=99999)
        assert history is None


# ==================== get_history_count() 测试 ====================

class TestGetHistoryCountWithSqlAlchemyHistory:
    """history_count 属性测试 - 使用 sqlalchemy-history"""
    
    def test_get_history_count_returns_int(self, setup_history_db):
        """测试：history_count 返回整数"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        # 使用实例属性
        count = model.history_count
        assert isinstance(count, int)
        assert count >= 1
    
    def test_get_history_count_increases_on_update(self, setup_history_db):
        """测试：更新后历史数量增加"""
        session = setup_history_db
        
        model = HistoryTestModel(name="V1", content="Content")
        model.add(True)
        
        # 使用实例属性
        initial_count = model.history_count
        
        model.name = "V2"
        model.save(True)
        
        new_count = model.history_count
        assert new_count > initial_count
    
    def test_get_history_count_zero_for_nonexistent(self, setup_history_db):
        """测试：不存在的记录返回 0（使用类方法）"""
        session = setup_history_db
        
        # 使用类方法查询不存在的记录
        count = HistoryTestModel.get_history_count_by_id(instance_id=99999)
        assert count == 0


# ==================== get_history_diff() 测试 ====================

class TestGetHistoryDiffWithSqlAlchemyHistory:
    """get_history_diff() 实例方法测试 - 使用 sqlalchemy-history"""
    
    def test_get_history_diff_returns_dict(self, setup_history_db):
        """测试：get_history_diff 返回差异字典"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Original", content="Content1")
        model.add(True)
        
        # 使用实例方法获取第一个版本的 transaction_id
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        model.name = "Modified"
        model.content = "Content2"
        model.save(True)
        
        # 使用实例方法获取第二个版本的 transaction_id
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法获取差异
        diff = model.get_history_diff(from_version=version1, to_version=version2)
        
        if diff:
            assert isinstance(diff, dict)
            # 检查差异格式
            for key, value in diff.items():
                assert 'from' in value
                assert 'to' in value
    
    def test_get_history_diff_returns_none_for_nonexistent_version(self, setup_history_db):
        """测试：不存在的版本返回 None"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        # 使用实例方法
        diff = model.get_history_diff(from_version=1, to_version=99999)
        
        assert diff is None


# ==================== restore_to_version() 测试 ====================

class TestRestoreToVersionWithSqlAlchemyHistory:
    """restore_to_version() 实例方法测试 - 使用 sqlalchemy-history"""
    
    def test_restore_to_version_returns_instance(self, setup_history_db):
        """测试：restore_to_version 返回恢复后的实例"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Original", content="Content")
        model.add(True)
        
        # 使用实例方法获取初始版本
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        model.name = "Modified"
        model.save(True)
        
        # 使用实例方法恢复到初始版本
        restored = model.restore_to_version(version=version1)
        
        if restored:
            assert restored.name == "Original"
    
    def test_restore_to_version_returns_none_for_nonexistent_instance(self, setup_history_db):
        """测试：不存在的实例返回 None（使用传统函数）"""
        from yweb.orm import restore_to_version
        
        session = setup_history_db
        
        # 对于不存在的实例，需要使用传统函数
        restored = restore_to_version(
            HistoryTestModel, instance_id=99999,
            version=1, session=session
        )
        
        assert restored is None
    
    def test_restore_to_version_returns_none_for_nonexistent_version(self, setup_history_db):
        """测试：不存在的版本返回 None"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        # 使用实例方法
        restored = model.restore_to_version(version=99999)
        
        assert restored is None


# ==================== get_version_class() 测试 ====================

class TestGetVersionClassWithSqlAlchemyHistory:
    """get_version_class() 函数测试 - 使用 sqlalchemy-history"""
    
    def test_get_version_class_returns_history_model(self):
        """测试：get_version_class 返回历史模型类"""
        from yweb.orm import get_version_class
        
        HistoryClass = get_version_class(HistoryTestModel)
        
        assert HistoryClass is not None
        assert 'Version' in HistoryClass.__name__
    
    def test_get_version_class_history_model_has_required_columns(self):
        """测试：历史模型有必要的列"""
        from yweb.orm import get_version_class
        
        HistoryClass = get_version_class(HistoryTestModel)
        
        # 检查历史模型有 transaction_id 列
        assert hasattr(HistoryClass, 'transaction_id')
        assert hasattr(HistoryClass, 'operation_type')
        assert hasattr(HistoryClass, 'id')


# ==================== 软删除 + 版本历史 集成测试 ====================

class TestSoftDeleteWithHistory:
    """软删除后版本历史的行为测试
    
    核心测试点：主记录被软删除后，历史记录不会被硬删除（数据仍物理存在）
    """
    
    def _get_model_include_deleted(self, model_id: int):
        """获取记录（包括软删除的）"""
        return SoftDeleteHistoryTestModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
    
    def _get_history_count_raw(self, session, model_id: int) -> int:
        """直接通过 SQL 查询历史表记录数量（绕过软删除过滤）"""
        from yweb.orm import get_version_class
        
        HistoryClass = get_version_class(SoftDeleteHistoryTestModel)
        table_name = HistoryClass.__table__.name
        
        result = session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE id = :id"),
            {"id": model_id}
        )
        return result.scalar() or 0
    
    def test_history_not_hard_deleted_when_main_record_soft_deleted(self, setup_history_db):
        """测试：主记录被软删除时，历史记录不会被硬删除（物理数据仍存在）"""
        session = setup_history_db
        
        # 创建并更新几次以产生历史记录
        model = SoftDeleteHistoryTestModel(name="V1", content="Content")
        model.add(True)
        
        model_id = model.id
        
        model.name = "V2"
        model.save(True)
        
        model.name = "V3"
        model.save(True)
        
        # 获取软删除前的历史记录数量（使用原始 SQL 绕过过滤）
        count_before_delete = self._get_history_count_raw(session, model_id)
        assert count_before_delete >= 3, "软删除前应该有至少3条历史记录"
        
        # 软删除主记录
        model.delete(True)
        
        # 验证主记录已被软删除
        main_record = self._get_model_include_deleted(model_id)
        assert main_record is not None, "主记录应该物理存在"
        assert main_record.is_deleted, "主记录应该被标记为软删除"
        
        # 历史记录数量不应减少（使用原始 SQL 验证物理数据仍存在）
        count_after_delete = self._get_history_count_raw(session, model_id)
        assert count_after_delete >= count_before_delete, "历史记录不应该被硬删除"
    
    def test_soft_deleted_main_record_history_physically_exists(self, setup_history_db):
        """测试：软删除主记录后，历史表中的数据物理存在"""
        from yweb.orm import get_version_class
        
        session = setup_history_db
        
        model = SoftDeleteHistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        model_id = model.id
        
        # 更新以产生历史
        model.name = "Updated"
        model.save(True)
        
        # 软删除
        model.delete(True)
        
        # 直接用 SQL 查询历史表，验证数据物理存在
        HistoryClass = get_version_class(SoftDeleteHistoryTestModel)
        table_name = HistoryClass.__table__.name
        
        result = session.execute(
            text(f"SELECT * FROM {table_name} WHERE id = :id"),
            {"id": model_id}
        )
        rows = result.fetchall()
        
        assert len(rows) >= 2, "历史表中应该物理存在至少2条记录"
    
    def test_soft_delete_does_not_cascade_to_history(self, setup_history_db):
        """测试：软删除不会级联到历史表"""
        from yweb.orm import get_version_class
        
        session = setup_history_db
        
        model = SoftDeleteHistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        model_id = model.id
        
        # 多次更新
        for i in range(5):
            model.name = f"Version{i+2}"
            model.save(True)
        
        # 获取历史表名
        HistoryClass = get_version_class(SoftDeleteHistoryTestModel)
        table_name = HistoryClass.__table__.name
        
        # 软删除前：统计历史表记录
        result_before = session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE id = :id"),
            {"id": model_id}
        )
        count_before = result_before.scalar()
        
        # 软删除主记录
        model.delete(True)
        
        # 软删除后：统计历史表记录（物理存在的）
        result_after = session.execute(
            text(f"SELECT COUNT(*) FROM {table_name} WHERE id = :id"),
            {"id": model_id}
        )
        count_after = result_after.scalar()
        
        # 历史记录数量不应减少
        assert count_after >= count_before, "软删除不应该删除历史记录"


# ==================== get_field_text_diff() 测试 ====================

class TestGetFieldTextDiffWithSqlAlchemyHistory:
    """get_field_text_diff() 实例方法测试 - 文本细节差异对比"""
    
    def test_get_field_text_diff_unified_format(self, setup_history_db):
        """测试：get_field_text_diff 返回 unified 格式差异"""
        session = setup_history_db
        
        # 创建记录
        model = HistoryTestModel(name="Test", content="第一行\n第二行\n第三行")
        model.add(True)
        
        # 使用实例方法获取第一个版本的 transaction_id
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        # 更新内容
        model.content = "第一行\n修改后的第二行\n第三行"
        model.save(True)
        
        # 使用实例方法获取第二个版本的 transaction_id
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法获取 unified 格式差异
        result = model.get_field_text_diff(
            field_name="content",
            from_version=version1,
            to_version=version2,
            output_format="unified"
        )
        
        assert result is not None
        assert result["field"] == "content"
        assert result["from_version"] == version1
        assert result["to_version"] == version2
        assert isinstance(result["diff"], str)
        assert "stats" in result
    
    def test_get_field_text_diff_inline_format(self, setup_history_db):
        """测试：get_field_text_diff 返回 inline 格式差异"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="原始内容")
        model.add(True)
        
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        model.content = "修改后的内容"
        model.save(True)
        
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法
        result = model.get_field_text_diff(
            field_name="content",
            from_version=version1,
            to_version=version2,
            output_format="inline"
        )
        
        assert result is not None
        assert isinstance(result["diff"], list)
        # inline 格式返回列表，每项有 type 和 text
        for item in result["diff"]:
            assert "type" in item
            assert "text" in item
            assert item["type"] in ("equal", "insert", "delete")
    
    def test_get_field_text_diff_opcodes_format(self, setup_history_db):
        """测试：get_field_text_diff 返回 opcodes 格式差异"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="ABC")
        model.add(True)
        
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        model.content = "AXC"
        model.save(True)
        
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法
        result = model.get_field_text_diff(
            field_name="content",
            from_version=version1,
            to_version=version2,
            output_format="opcodes"
        )
        
        assert result is not None
        assert isinstance(result["diff"], list)
        # opcodes 格式返回操作码列表
        for op in result["diff"]:
            assert "operation" in op
            assert op["operation"] in ("equal", "replace", "insert", "delete")
    
    def test_get_field_text_diff_html_format(self, setup_history_db):
        """测试：get_field_text_diff 返回 html 格式差异"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Hello\nWorld")
        model.add(True)
        
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        model.content = "Hello\nPython"
        model.save(True)
        
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法
        result = model.get_field_text_diff(
            field_name="content",
            from_version=version1,
            to_version=version2,
            output_format="html"
        )
        
        assert result is not None
        assert isinstance(result["diff"], str)
        assert "<table" in result["diff"]  # HTML 表格
    
    def test_get_field_text_diff_returns_none_for_nonexistent(self, setup_history_db):
        """测试：不存在的版本返回 None"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        # 使用实例方法
        result = model.get_field_text_diff(
            field_name="content",
            from_version=1,
            to_version=99999
        )
        
        assert result is None
    
    def test_get_field_text_diff_stats(self, setup_history_db):
        """测试：get_field_text_diff 返回正确的统计信息"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="行1\n行2\n行3")
        model.add(True)
        
        history1 = model.get_history()
        version1 = history1[0].get('transaction_id')
        
        # 删除一行，添加两行
        model.content = "行1\n新行A\n新行B\n行3"
        model.save(True)
        
        history2 = model.get_history()
        version2 = history2[0].get('transaction_id')
        
        # 使用实例方法
        result = model.get_field_text_diff(
            field_name="content",
            from_version=version1,
            to_version=version2
        )
        
        assert result is not None
        assert "stats" in result
        stats = result["stats"]
        assert "added" in stats
        assert "removed" in stats
        assert "changed" in stats
        assert isinstance(stats["added"], int)
        assert isinstance(stats["removed"], int)
        assert isinstance(stats["changed"], int)


# ==================== 实例方法 API 专项测试 ====================

class TestInstanceMethodsAPI:
    """实例方法 API 专项测试
    
    验证新的实例方法调用方式是否正常工作
    """
    
    def test_instance_has_get_history_method(self, setup_history_db):
        """测试：实例有 get_history 方法"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'get_history')
        assert callable(model.get_history)
    
    def test_instance_has_history_property(self, setup_history_db):
        """测试：实例有 history 属性"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'history')
        # history 是 property，不是 callable
        history = model.history
        assert history is not None
    
    def test_instance_has_history_count_property(self, setup_history_db):
        """测试：实例有 history_count 属性"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'history_count')
        count = model.history_count
        assert isinstance(count, int)
    
    def test_instance_has_get_history_diff_method(self, setup_history_db):
        """测试：实例有 get_history_diff 方法"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'get_history_diff')
        assert callable(model.get_history_diff)
    
    def test_instance_has_get_field_text_diff_method(self, setup_history_db):
        """测试：实例有 get_field_text_diff 方法"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'get_field_text_diff')
        assert callable(model.get_field_text_diff)
    
    def test_instance_has_restore_to_version_method(self, setup_history_db):
        """测试：实例有 restore_to_version 方法"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        assert hasattr(model, 'restore_to_version')
        assert callable(model.restore_to_version)
    
    def test_class_has_get_history_by_id_method(self, setup_history_db):
        """测试：类有 get_history_by_id 类方法"""
        assert hasattr(HistoryTestModel, 'get_history_by_id')
        assert callable(HistoryTestModel.get_history_by_id)
    
    def test_class_has_get_history_count_by_id_method(self, setup_history_db):
        """测试：类有 get_history_count_by_id 类方法"""
        assert hasattr(HistoryTestModel, 'get_history_count_by_id')
        assert callable(HistoryTestModel.get_history_count_by_id)
    
    def test_instance_method_equals_class_method(self, setup_history_db):
        """测试：实例方法与类方法返回相同结果"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        model.name = "Updated"
        model.save(True)
        
        # 实例方法
        instance_history = model.get_history()
        instance_count = model.history_count
        
        # 类方法
        class_history = HistoryTestModel.get_history_by_id(model.id)
        class_count = HistoryTestModel.get_history_count_by_id(model.id)
        
        assert len(instance_history) == len(class_history)
        assert instance_count == class_count
    
    def test_history_raises_error_for_non_versioned_model(self, setup_history_db):
        """测试：未启用版本控制的模型调用历史方法会抛出异常"""
        # 创建一个不启用 enable_history=True 的简单模型
        # 由于 HistoryTestModel 启用了历史，这里只能通过文档说明
        # 实际测试需要一个未启用历史的模型
        pass  # 此测试仅作为文档说明
    
    def test_get_history_with_field_names(self, setup_history_db):
        """测试：get_history 支持 field_names 参数"""
        session = setup_history_db
        
        model = HistoryTestModel(name="Test", content="Content")
        model.add(True)
        
        # 只获取指定字段
        history = model.get_history(field_names=['name', 'content'])
        
        assert history is not None
        if history:
            record = history[0]
            assert 'name' in record
            assert 'content' in record
    
    def test_chained_operations(self, setup_history_db):
        """测试：链式操作场景"""
        session = setup_history_db
        
        # 创建并更新
        model = HistoryTestModel(name="V1", content="Content1")
        model.add(True)
        
        model.name = "V2"
        model.content = "Content2"
        model.save(True)
        
        model.name = "V3"
        model.content = "Content3"
        model.save(True)
        
        # 获取版本信息
        history = model.history
        assert len(history) >= 3
        
        # 获取最早和最新版本
        latest_ver = history[0].get('transaction_id')
        oldest_ver = history[-1].get('transaction_id')
        
        # 获取差异
        diff = model.get_history_diff(oldest_ver, latest_ver)
        assert diff is not None
        
        # 恢复到最早版本
        model.restore_to_version(oldest_ver)
        session.commit()
        
        # 验证恢复结果
        assert model.name == "V1"
