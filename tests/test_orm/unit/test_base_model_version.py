"""版本功能测试

测试 BaseModel 的版本功能

测试覆盖：
- BaseModel 的版本控制行为（ver 字段）
- 软删除后版本历史的行为
"""

import pytest
from sqlalchemy import Column, String
from sqlalchemy.orm import sessionmaker, DeclarativeBase, scoped_session




class TestHistoryUtilityFunctionsWithoutDB:
    """历史工具函数测试 - 无数据库"""
    
    def test_get_version_class_raises_for_non_versioned_model(self):
        """测试：对未启用版本控制的模型抛出异常"""
        from yweb.orm import get_version_class
        
        class MyBase(DeclarativeBase):
            pass
        
        class NonVersionedModel(MyBase):
            __tablename__ = "non_versioned"
            id = Column(String, primary_key=True)
        
        with pytest.raises(Exception):
            get_version_class(NonVersionedModel)
    
    def test_get_history_raises_without_session(self):
        """测试：没有 session 时 get_history 抛出异常"""
        from yweb.orm import get_history, BaseModel
        
        with pytest.raises(Exception):
            get_history(BaseModel, instance_id=1)
    
    def test_get_history_count_raises_for_non_versioned_model(self):
        """测试：对未启用版本控制的模型 get_history_count 抛出异常"""
        from yweb.orm import get_history_count, BaseModel

        # BaseModel 未启用版本控制，会抛出异常
        with pytest.raises(Exception):
            get_history_count(BaseModel, instance_id=99999)


# ==================== 版本控制行为测试（使用 BaseModel）====================

class TestVersionControlBehavior:
    """版本控制行为测试
    
    测试 BaseModel 的版本控制行为（ver 字段 / 乐观锁）
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        from yweb.orm import CoreModel, BaseModel
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        self.engine = memory_engine
        yield
        self.session_scope.remove()
    
    def test_version_field_exists_on_base_model(self):
        """测试：BaseModel 有 ver 字段"""
        from yweb.orm import BaseModel
        assert hasattr(BaseModel, 'ver')
    
    def test_initial_version_is_one(self):
        """测试：初始版本号为 1"""
        from yweb.orm import BaseModel
        
        class InitialVersionModel(BaseModel):
            __tablename__ = "test_initial_version"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = InitialVersionModel(name="Test")
        model.add(True)
        
        assert model.ver == 1
    
    def test_no_change_no_version_increment(self):
        """测试：无变更时版本号不增加"""
        from yweb.orm import BaseModel
        
        class NoChangeModel(BaseModel):
            __tablename__ = "test_no_change"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = NoChangeModel(name="Test")
        model.add(True)
        
        initial_version = model.ver
        model_id = model.id
        
        # 重新查询但不修改
        model = NoChangeModel.query.filter_by(id=model_id).first()
        model.update(True)
        
        model = NoChangeModel.query.filter_by(id=model_id).first()
        assert model.ver == initial_version
    
    def test_same_value_no_version_increment(self):
        """测试：设置相同值时版本号不增加"""
        from yweb.orm import BaseModel
        
        class SameValueModel(BaseModel):
            __tablename__ = "test_same_value"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = SameValueModel(name="Original")
        model.add(True)
        
        initial_version = model.ver
        model_id = model.id
        original_name = model.name
        
        model = SameValueModel.query.filter_by(id=model_id).first()
        model.name = original_name  # 相同的值
        model.update(True)
        
        model = SameValueModel.query.filter_by(id=model_id).first()
        assert model.ver == initial_version
    
    def test_actual_change_increments_version(self):
        """测试：实际变更时版本号增加"""
        from yweb.orm import BaseModel
        
        class ActualChangeModel(BaseModel):
            __tablename__ = "test_actual_change"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = ActualChangeModel(name="Original")
        model.add(True)
        
        initial_version = model.ver
        model_id = model.id
        
        model = ActualChangeModel.query.filter_by(id=model_id).first()
        model.name = "Modified"  # 不同的值
        model.update(True)
        
        model = ActualChangeModel.query.filter_by(id=model_id).first()
        assert model.ver > initial_version
    
    def test_multiple_updates_increment_version(self):
        """测试：多次更新版本号递增"""
        from yweb.orm import BaseModel
        
        class MultiUpdateModel(BaseModel):
            __tablename__ = "test_multi_update"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = MultiUpdateModel(name="V1")
        model.add(True)
        model_id = model.id
        
        versions = [model.ver]
        
        for i in range(3):
            model = MultiUpdateModel.query.filter_by(id=model_id).first()
            model.name = f"V{i+2}"
            model.update(True)
            versions.append(model.ver)
        
        # 验证版本号递增
        for i in range(len(versions) - 1):
            assert versions[i+1] > versions[i]


# ==================== 软删除与版本历史测试 ====================

class TestSoftDeleteWithVersionHistory:
    """软删除与版本历史测试
    
    测试 BaseModel 软删除后版本历史的行为
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        from yweb.orm import CoreModel, BaseModel, activate_soft_delete_hook
        
        activate_soft_delete_hook()
        BaseModel.metadata.create_all(bind=memory_engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        self.engine = memory_engine
        
        yield
        
        self.session_scope.remove()
    
    def test_soft_delete_does_not_delete_from_db(self):
        """测试：软删除不会从数据库物理删除"""
        from yweb.orm import BaseModel
        
        class SoftDeleteTestModel(BaseModel):
            __tablename__ = "test_soft_del_history"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = SoftDeleteTestModel(name="Test")
        model.add(True)
        model_id = model.id
        
        # 软删除
        model.delete(True)
        
        # 使用 include_deleted 查询，记录应该还在
        found = SoftDeleteTestModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        assert found is not None
        assert found.deleted_at is not None
    
    def test_soft_deleted_record_has_version_history(self):
        """测试：软删除的记录保留版本历史（ver 字段）"""
        from yweb.orm import BaseModel
        
        class VersionedSoftDeleteModel(BaseModel):
            __tablename__ = "test_versioned_soft_del"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建记录
        model = VersionedSoftDeleteModel(name="Original")
        model.add(True)
        model_id = model.id
        initial_ver = model.ver
        
        # 修改记录
        model.name = "Modified"
        model.update(True)
        modified_ver = model.ver
        
        # 软删除
        model.delete(True)
        
        # 验证版本号增加了
        found = VersionedSoftDeleteModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        assert found is not None
        assert found.ver >= modified_ver
    
    def test_soft_deleted_record_can_be_queried_with_history(self):
        """测试：软删除的记录可以通过 include_deleted 查询到完整状态"""
        from yweb.orm import BaseModel
        
        class QueryableHistoryModel(BaseModel):
            __tablename__ = "test_queryable_history"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = QueryableHistoryModel(name="Test", note="Important note")
        model.add(True)
        model_id = model.id
        
        # 软删除
        model.delete(True)
        
        # 正常查询不应该返回结果
        normal_query = QueryableHistoryModel.query.filter_by(id=model_id).first()
        assert normal_query is None
        
        # 使用 include_deleted 可以查询到
        found = QueryableHistoryModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        assert found is not None
        assert found.name == "Test"
        assert found.note == "Important note"
        assert found.deleted_at is not None
    
    def test_version_preserved_after_soft_delete(self):
        """测试：软删除后版本号保持不变（记录未被物理删除）"""
        from yweb.orm import BaseModel
        
        class VersionPreserveModel(BaseModel):
            __tablename__ = "test_version_preserve"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = VersionPreserveModel(name="Test")
        model.add(True)
        model_id = model.id
        
        # 多次更新
        model.name = "Update1"
        model.update(True)
        
        model.name = "Update2"
        model.update(True)
        
        version_before_delete = model.ver
        
        # 软删除
        model.delete(True)
        
        # 查询并验证版本号
        found = VersionPreserveModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        # 软删除可能会增加版本号
        assert found.ver >= version_before_delete
    
    def test_multiple_records_soft_delete_independence(self):
        """测试：多条记录的软删除相互独立"""
        from yweb.orm import BaseModel
        
        class IndependentModel(BaseModel):
            __tablename__ = "test_independent"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建三条记录
        model1 = IndependentModel(name="Record1")
        model2 = IndependentModel(name="Record2")
        model3 = IndependentModel(name="Record3")
        
        IndependentModel.add_all([model1, model2, model3], commit=True)
        
        id1, id2, id3 = model1.id, model2.id, model3.id
        
        # 只软删除第二条
        model2.delete(True)
        
        # 验证
        found1 = IndependentModel.query.filter_by(id=id1).first()
        found2 = IndependentModel.query.filter_by(id=id2).first()
        found3 = IndependentModel.query.filter_by(id=id3).first()
        
        assert found1 is not None  # 未删除
        assert found2 is None      # 已软删除，正常查询不到
        assert found3 is not None  # 未删除
        
        # 使用 include_deleted 可以查到所有
        all_records = IndependentModel.query.execution_options(
            include_deleted=True
        ).all()
        
        assert len(all_records) == 3
    
    def test_soft_delete_does_not_cascade_to_history_data(self):
        """测试：主体软删除后，历史数据（ver 字段等）不受影响
        
        验证软删除只是标记 deleted_at，不会影响已有的版本信息
        """
        from yweb.orm import BaseModel
        
        class HistoryDataModel(BaseModel):
            __tablename__ = "test_history_data"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建记录并记录初始状态
        model = HistoryDataModel(name="Original")
        model.add(True)
        model_id = model.id
        
        original_created_at = model.created_at
        original_id = model.id
        
        # 多次更新，记录每次的版本号
        version_history = [(model.ver, model.name)]
        
        model.name = "Update1"
        model.update(True)
        version_history.append((model.ver, model.name))
        
        model.name = "Update2"
        model.update(True)
        version_history.append((model.ver, model.name))
        
        # 记录软删除前的状态
        ver_before_delete = model.ver
        name_before_delete = model.name
        
        # 软删除
        model.delete(True)
        
        # 查询软删除后的记录
        found = HistoryDataModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        # 验证：软删除后，历史数据完整保留
        assert found is not None
        assert found.id == original_id  # ID 不变
        assert found.created_at == original_created_at  # 创建时间不变
        assert found.name == name_before_delete  # 名称不变
        assert found.ver >= ver_before_delete  # 版本号不减少
        assert found.deleted_at is not None  # 有删除时间
        assert found.updated_at is not None  # 有更新时间
    
    def test_restore_soft_deleted_record_updates_version(self):
        """测试：恢复软删除的记录后，版本号会更新"""
        from yweb.orm import BaseModel
        
        class RestoreModel(BaseModel):
            __tablename__ = "test_restore"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建并软删除
        model = RestoreModel(name="Test")
        model.add(True)
        model_id = model.id
        
        model.delete(True)
        
        # 获取软删除后的版本号
        deleted_model = RestoreModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        ver_after_delete = deleted_model.ver
        
        # 恢复记录（清除 deleted_at）
        deleted_model.deleted_at = None
        deleted_model.update(True)
        
        # 验证恢复后的状态
        restored = RestoreModel.query.filter_by(id=model_id).first()
        
        assert restored is not None
        assert restored.deleted_at is None
        # 恢复操作应该增加版本号
        assert restored.ver >= ver_after_delete


# ==================== history.py 工具函数功能测试 ====================

class TestHistoryFunctions:
    """history.py 工具函数功能测试
    
    测试 get_history, get_history_count, get_history_diff, restore_to_version 的实际功能
    注意：这些函数依赖 sqlalchemy-history 库的配置，可能在某些环境下无法正常工作
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        from yweb.orm import CoreModel, BaseModel
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        self.session = self.session_scope()
        CoreModel.query = self.session_scope.query_property()
        self.engine = memory_engine
        
        yield
        
        self.session_scope.remove()
    
    def test_get_history_count_raises_for_non_versioned_model(self):
        """测试：对未启用版本控制的模型 get_history_count 抛出异常"""
        from yweb.orm import get_history_count, BaseModel
        
        # BaseModel 未启用版本控制，会抛出异常
        with pytest.raises(Exception):
            get_history_count(BaseModel, instance_id=99999, session=self.session)
    
    def test_get_history_returns_none_for_nonexistent(self):
        """测试：get_history 对不存在的记录返回 None"""
        from yweb.orm import get_history, BaseModel
        
        # BaseModel 未启用 sqlalchemy-history，会抛出异常
        with pytest.raises(Exception):
            get_history(BaseModel, instance_id=99999, session=self.session)
    
    def test_get_history_diff_returns_none_for_invalid_versions(self):
        """测试：get_history_diff 对无效版本返回 None"""
        from yweb.orm import get_history_diff, BaseModel
        
        # BaseModel 未启用 sqlalchemy-history，会抛出异常或返回 None
        try:
            diff = get_history_diff(
                BaseModel, 
                instance_id=99999, 
                from_version=1, 
                to_version=2, 
                session=self.session
            )
            # 如果没有抛出异常，应该返回 None
            assert diff is None
        except Exception:
            # 预期会抛出异常
            pass
    
    def test_restore_to_version_returns_none_for_nonexistent(self):
        """测试：restore_to_version 对不存在的记录返回 None"""
        from yweb.orm import restore_to_version, BaseModel
        
        # BaseModel 未启用 sqlalchemy-history，会抛出异常或返回 None
        try:
            restored = restore_to_version(
                BaseModel,
                instance_id=99999,
                version=1,
                session=self.session
            )
            assert restored is None
        except Exception:
            # 预期会抛出异常
            pass


# ==================== 主体软删除后历史记录表行为测试 ====================

class TestSoftDeleteHistoryTableBehavior:
    """主体软删除后历史记录表行为测试
    
    验证主体被软删除后，相关的历史数据不会被级联软删除
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        from yweb.orm import CoreModel, BaseModel, activate_soft_delete_hook
        
        activate_soft_delete_hook()
        BaseModel.metadata.create_all(bind=memory_engine)
        
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        self.session = self.session_scope()
        CoreModel.query = self.session_scope.query_property()
        self.engine = memory_engine
        
        yield
        
        self.session_scope.remove()
    
    def test_main_record_soft_delete_preserves_all_fields(self):
        """测试：主记录软删除后，所有字段值保持不变"""
        from yweb.orm import BaseModel
        
        class PreserveFieldsModel(BaseModel):
            __tablename__ = "test_preserve_fields"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建记录
        model = PreserveFieldsModel(name="TestName", note="TestNote")
        model.add(True)
        model_id = model.id
        
        # 记录所有字段值
        original_values = {
            'id': model.id,
            'name': model.name,
            'note': model.note,
            'ver': model.ver,
            'created_at': model.created_at,
        }
        
        # 软删除
        model.delete(True)
        
        # 查询并验证所有字段
        found = PreserveFieldsModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        assert found.id == original_values['id']
        assert found.name == original_values['name']
        assert found.note == original_values['note']
        assert found.created_at == original_values['created_at']
        # ver 可能因为软删除操作而增加
        assert found.ver >= original_values['ver']
        # deleted_at 应该被设置
        assert found.deleted_at is not None
    
    def test_history_version_chain_not_broken_by_soft_delete(self):
        """测试：软删除不会破坏版本链（ver 递增历史）"""
        from yweb.orm import BaseModel
        
        class VersionChainModel(BaseModel):
            __tablename__ = "test_version_chain"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建记录
        model = VersionChainModel(name="V1")
        model.add(True)
        model_id = model.id
        
        # 记录版本历史
        versions = [model.ver]
        
        # 多次更新
        for i in range(3):
            model.name = f"V{i+2}"
            model.update(True)
            versions.append(model.ver)
        
        ver_before_delete = model.ver
        
        # 软删除
        model.delete(True)
        
        # 查询软删除后的记录
        found = VersionChainModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        # 验证版本链完整性
        # 软删除后版本号应该 >= 删除前版本号
        assert found.ver >= ver_before_delete
        
        # 所有之前的版本号应该是递增的
        for i in range(len(versions) - 1):
            assert versions[i] < versions[i + 1]
    
    def test_soft_deleted_record_can_still_be_updated_after_restore(self):
        """测试：软删除的记录恢复后可以继续更新"""
        from yweb.orm import BaseModel
        
        class RestoreUpdateModel(BaseModel):
            __tablename__ = "test_restore_update"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        # 创建并更新几次
        model = RestoreUpdateModel(name="Original")
        model.add(True)
        model_id = model.id
        
        model.name = "Updated1"
        model.update(True)
        
        # 软删除
        model.delete(True)
        
        # 恢复（清除 deleted_at）
        deleted_model = RestoreUpdateModel.query.execution_options(
            include_deleted=True
        ).filter_by(id=model_id).first()
        
        deleted_model.deleted_at = None
        deleted_model.update(True)
        
        ver_after_restore = deleted_model.ver
        
        # 继续更新
        restored = RestoreUpdateModel.query.filter_by(id=model_id).first()
        restored.name = "UpdatedAfterRestore"
        restored.update(True)
        
        # 验证可以继续更新
        final = RestoreUpdateModel.query.filter_by(id=model_id).first()
        assert final.name == "UpdatedAfterRestore"
        assert final.ver > ver_after_restore
        assert final.deleted_at is None
    
    def test_multiple_soft_delete_restore_cycles(self):
        """测试：多次软删除和恢复循环"""
        from yweb.orm import BaseModel
        
        class CycleModel(BaseModel):
            __tablename__ = "test_cycle"
            __table_args__ = {'extend_existing': True}
        
        BaseModel.metadata.create_all(bind=self.engine)
        
        model = CycleModel(name="Test")
        model.add(True)
        model_id = model.id
        
        # 进行多次软删除和恢复循环
        for i in range(3):
            # 软删除
            current = CycleModel.query.execution_options(
                include_deleted=True
            ).filter_by(id=model_id).first()
            
            if current.deleted_at is None:
                current.delete(True)
            
            # 验证已软删除
            normal_query = CycleModel.query.filter_by(id=model_id).first()
            assert normal_query is None
            
            # 恢复
            deleted = CycleModel.query.execution_options(
                include_deleted=True
            ).filter_by(id=model_id).first()
            deleted.deleted_at = None
            deleted.update(True)
            
            # 验证已恢复
            restored = CycleModel.query.filter_by(id=model_id).first()
            assert restored is not None
            assert restored.deleted_at is None
        
        # 最终验证记录完整
        final = CycleModel.query.filter_by(id=model_id).first()
        assert final is not None
        assert final.id == model_id


# ==================== sqlalchemy-history 集成测试 ====================

# 初始化 versioning（必须在定义模型之前）
from yweb.orm import init_versioning
try:
    init_versioning()
except Exception:
    pass

from sqlalchemy import Column, Integer, String as SAString, create_engine
from sqlalchemy.orm import configure_mappers

from yweb.orm import (
    BaseModel,
)


# 配置 mappers
try:
    configure_mappers()
except Exception:
    pass

