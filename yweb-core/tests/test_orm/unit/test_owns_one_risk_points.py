"""OwnsOne 风险点专项测试

针对设计评审中识别的 6 个风险点逐一验证：
1. comparator_factory 查询代理（替代 OwnedColumnProxy）
2. __init_subclass__ 字段收集（替代元类）
3. __init__ 构造阶段不误触 changed()
4. OwnsOne(nullable=True) 强制展开列 nullable
5. to_dict_with_relations 与 OwnsOne 的协同
6. __owned_composites__ 继承隔离
"""
from __future__ import annotations

import pytest
from sqlalchemy import String, Integer, ForeignKey, inspect as sa_inspect
from sqlalchemy.orm import (
    sessionmaker, scoped_session, Mapped, mapped_column,
    relationship, CompositeProperty,
)
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel, fields
from yweb.orm.owned_types import OwnedType, owned_field, OwnedField


# ==================== 值对象定义 ====================

class StrictVO(OwnedType):
    """字段级 nullable=False 的值对象，用于测试 nullable 覆盖"""
    name = owned_field(String(100), nullable=False, comment="名称")
    code = owned_field(String(50), nullable=False, comment="编码")


class ParentVO(OwnedType):
    """父值对象，用于测试继承"""
    x = owned_field(String(50), comment="X 坐标")
    y = owned_field(String(50), comment="Y 坐标")


class ChildVO(ParentVO):
    """继承父值对象并扩展字段"""
    z = owned_field(String(50), comment="Z 坐标")


class SimpleVO(OwnedType):
    """简单值对象，用于继承隔离测试"""
    value = owned_field(String(100), comment="值")


# ==================== 测试模型 ====================

class _OwnedMixin:
    """Abstract Mixin 携带 OwnsOne，用于继承隔离测试"""
    info = fields.OwnsOne(SimpleVO, prefix="info")


class RiskMixinModelA(_OwnedMixin, BaseModel):
    """Mixin 模型 A（仅继承 Mixin 的 OwnsOne）"""
    __tablename__ = "test_risk_mixin_a"
    __table_args__ = {'extend_existing': True}


class RiskMixinModelB(_OwnedMixin, BaseModel):
    """Mixin 模型 B（继承 Mixin + 自有 OwnsOne）"""
    __tablename__ = "test_risk_mixin_b"
    __table_args__ = {'extend_existing': True}

    detail = fields.OwnsOne(StrictVO, prefix="detail", nullable=True)


class NullableOverrideModel(BaseModel):
    """OwnsOne(nullable=True) + owned_field(nullable=False) 的组合"""
    __tablename__ = "test_risk_nullable_override"
    __table_args__ = {'extend_existing': True}

    label: Mapped[str] = mapped_column(String(50), comment="标签")
    strict = fields.OwnsOne(StrictVO, prefix="strict", nullable=True)


class NotNullableModel(BaseModel):
    """OwnsOne(nullable=False) 保留字段级 nullable"""
    __tablename__ = "test_risk_not_nullable"
    __table_args__ = {'extend_existing': True}

    label: Mapped[str] = mapped_column(String(50), comment="标签")
    strict = fields.OwnsOne(StrictVO, prefix="strict", nullable=False)


class InheritedVOModel(BaseModel):
    """使用继承值对象的模型"""
    __tablename__ = "test_risk_inherited_vo"
    __table_args__ = {'extend_existing': True}

    point = fields.OwnsOne(ChildVO, prefix="pt")


class RelParentModel(BaseModel):
    """带关系 + OwnsOne 的模型，用于测试 to_dict_with_relations"""
    __tablename__ = "test_risk_rel_parent"
    __table_args__ = {'extend_existing': True}

    title: Mapped[str] = mapped_column(String(100), comment="标题")
    address = fields.OwnsOne(SimpleVO, prefix="addr")
    items = relationship("RelChildModel", back_populates="parent")


class RelChildModel(BaseModel):
    """关系子模型"""
    __tablename__ = "test_risk_rel_child"
    __table_args__ = {'extend_existing': True}

    parent_id = mapped_column(
        Integer, ForeignKey("test_risk_rel_parent.id"), nullable=True, comment="父 ID",
    )
    desc: Mapped[str] = mapped_column(String(100), comment="描述")
    parent = relationship("RelParentModel", back_populates="items",
                          foreign_keys=[parent_id])


# ==================== 风险点 1: comparator_factory 查询代理 ====================

class TestComparatorFactory:
    """验证 comparator_factory 正确实现类访问 → 列引用代理"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_class_access_returns_column_element(self):
        """类访问返回可参与 SQL 表达式的列对象"""
        col = NullableOverrideModel.strict.name
        assert hasattr(col, '__clause_element__') or hasattr(col, 'key'), \
            "类访问应返回 SQLAlchemy 列属性"

    def test_class_access_produces_sql_filter(self):
        """类访问的结果可用于 filter 生成 SQL 表达式"""
        expr = NullableOverrideModel.strict.name == "test"
        assert expr is not None
        compiled = str(expr.compile(compile_kwargs={"literal_binds": True}))
        assert "strict_name" in compiled

    def test_instance_access_returns_value(self):
        """实例访问返回实际 Python 值，而非列对象"""
        obj = NullableOverrideModel(name="V", label="L")
        obj.strict = StrictVO(name="hello", code="C01")
        obj.add(True)

        found = NullableOverrideModel.get(obj.id)
        assert isinstance(found.strict.name, str)
        assert found.strict.name == "hello"

    def test_access_nonexistent_field_raises(self):
        """访问值对象中不存在的字段应抛 AttributeError"""
        with pytest.raises(AttributeError):
            _ = NullableOverrideModel.strict.nonexistent_field

    def test_query_like_operator(self):
        """嵌套代理支持 like 等 SQL 操作符"""
        obj = NullableOverrideModel(name="Like测试", label="L")
        obj.strict = StrictVO(name="hello_world", code="C02")
        obj.add(True)

        results = NullableOverrideModel.query.filter(
            NullableOverrideModel.strict.name.like("hello%")
        ).all()
        assert len(results) == 1

    def test_query_is_null(self):
        """嵌套代理支持 IS NULL 判断"""
        obj = NullableOverrideModel(name="Null测试", label="L")
        obj.add(True)

        results = NullableOverrideModel.query.filter(
            NullableOverrideModel.strict.name.is_(None)
        ).all()
        assert len(results) == 1


# ==================== 风险点 2: __init_subclass__ 字段收集 ====================

class TestInitSubclassFieldCollection:
    """验证 __init_subclass__ 正确收集字段，包括继承场景"""

    def test_no_metaclass_on_owned_type(self):
        """OwnedType 不使用自定义元类"""
        assert type(OwnedType) is type, \
            "OwnedType 应使用 type 作为元类，不应有自定义元类"

    def test_child_inherits_parent_fields(self):
        """子值对象继承父值对象的字段"""
        assert 'x' in ChildVO.__owned_fields__
        assert 'y' in ChildVO.__owned_fields__
        assert 'z' in ChildVO.__owned_fields__
        assert len(ChildVO.__owned_fields__) == 3

    def test_parent_fields_not_polluted(self):
        """子类扩展不影响父类"""
        assert 'z' not in ParentVO.__owned_fields__
        assert len(ParentVO.__owned_fields__) == 2

    def test_inherited_vo_model_has_all_columns(self):
        """使用继承值对象的模型包含所有展开列"""
        assert hasattr(InheritedVOModel, 'pt_x')
        assert hasattr(InheritedVOModel, 'pt_y')
        assert hasattr(InheritedVOModel, 'pt_z')

    def test_inherited_vo_composite_values_order(self):
        """继承值对象的 __composite_values__ 字段顺序正确"""
        vo = ChildVO(x="1", y="2", z="3")
        assert vo.__composite_values__() == ("1", "2", "3")

    def test_inherited_vo_persistence(self, memory_engine):
        """继承值对象的持久化读写正确"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        ss = scoped_session(SessionLocal)
        CoreModel.query = ss.query_property()
        try:
            obj = InheritedVOModel(name="继承VO")
            obj.point = ChildVO(x="10", y="20", z="30")
            obj.add(True)

            found = InheritedVOModel.get(obj.id)
            assert found.point.x == "10"
            assert found.point.y == "20"
            assert found.point.z == "30"
        finally:
            ss.remove()


# ==================== 风险点 3: __init__ 不误触 changed() ====================

class TestInitNoSpuriousChanged:
    """验证构造阶段使用 object.__setattr__ 不触发 changed()"""

    def test_create_vo_without_parent_no_error(self):
        """独立创建值对象（无 ORM 父对象）不报错"""
        addr = StrictVO(name="test", code="C01")
        assert addr.name == "test"
        assert addr.code == "C01"

    def test_create_many_vos_no_error(self):
        """批量创建值对象不触发异常"""
        vos = [StrictVO(name=f"n{i}", code=f"c{i}") for i in range(100)]
        assert len(vos) == 100
        assert all(v.name.startswith("n") for v in vos)

    def test_create_vo_with_defaults_no_error(self):
        """默认参数（全 None）创建不报错"""
        vo = StrictVO()
        assert vo.name is None
        assert vo.code is None

    def test_create_vo_positional_args_no_error(self):
        """位置参数创建（composite 加载路径）不报错"""
        vo = StrictVO("hello", "world")
        assert vo.name == "hello"
        assert vo.code == "world"

    def test_setattr_after_init_calls_changed(self, memory_engine):
        """__init__ 后修改字段应触发变更追踪并成功持久化"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        ss = scoped_session(SessionLocal)
        CoreModel.query = ss.query_property()
        try:
            obj = NullableOverrideModel(name="追踪", label="L")
            obj.strict = StrictVO(name="before", code="C01")
            obj.add(True)

            obj.strict.name = "after"
            obj.update(True)

            found = NullableOverrideModel.get(obj.id)
            assert found.strict.name == "after"
        finally:
            ss.remove()


# ==================== 风险点 4: nullable 覆盖 ====================

class TestNullableOverride:
    """验证 OwnsOne(nullable=True) 强制展开列为 nullable"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        self._engine = memory_engine
        yield session_scope
        session_scope.remove()

    def test_nullable_true_overrides_field_not_nullable(self):
        """OwnsOne(nullable=True) 应强制 owned_field(nullable=False) 的列为可空"""
        mapper = sa_inspect(NullableOverrideModel)
        strict_name_col = mapper.columns['strict_name']
        strict_code_col = mapper.columns['strict_code']

        assert strict_name_col.nullable is True, \
            "OwnsOne(nullable=True) 应覆盖字段级 nullable=False"
        assert strict_code_col.nullable is True, \
            "OwnsOne(nullable=True) 应覆盖字段级 nullable=False"

    def test_nullable_false_preserves_field_not_nullable(self):
        """OwnsOne(nullable=False) 应保留字段原始的 nullable=False"""
        mapper = sa_inspect(NotNullableModel)
        strict_name_col = mapper.columns['strict_name']
        strict_code_col = mapper.columns['strict_code']

        assert strict_name_col.nullable is False, \
            "OwnsOne(nullable=False) 应保留字段级 nullable=False"
        assert strict_code_col.nullable is False, \
            "OwnsOne(nullable=False) 应保留字段级 nullable=False"

    def test_nullable_true_can_store_all_null(self):
        """nullable OwnsOne 可以将所有列存为 NULL"""
        obj = NullableOverrideModel(name="全空", label="L")
        obj.add(True)

        found = NullableOverrideModel.get(obj.id)
        assert not found.strict

    def test_nullable_true_can_assign_then_clear(self):
        """nullable OwnsOne 赋值后再清 None 能正确持久化"""
        obj = NullableOverrideModel(name="先赋后清", label="L")
        obj.strict = StrictVO(name="tmp", code="tmp")
        obj.add(True)

        obj.strict = None
        obj.update(True)

        found = NullableOverrideModel.get(obj.id)
        assert not found.strict


# ==================== 风险点 5: to_dict_with_relations 适配 ====================

class TestToDictWithRelations:
    """验证 to_dict_with_relations 和 OwnsOne 协同工作"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_with_relations_includes_nested_owned(self):
        """to_dict_with_relations 输出中包含嵌套的值对象"""
        parent = RelParentModel(name="父", title="T1")
        parent.address = SimpleVO(value="地址值")
        parent.add(True)

        child = RelChildModel(name="子", desc="D1", parent_id=parent.id)
        child.add(True)

        data = parent.to_dict_with_relations(relations=["items"])
        assert 'address' in data
        assert data['address'] == {'value': '地址值'}
        assert 'items' in data
        assert len(data['items']) == 1

    def test_with_relations_null_owned(self):
        """关联 + 空值对象的输出"""
        parent = RelParentModel(name="空地址", title="T2")
        parent.add(True)

        data = parent.to_dict_with_relations(relations=["items"])
        assert data['address'] is None
        assert data['items'] == []

    def test_with_relations_exclude_owned(self):
        """exclude 排除 OwnsOne 属性名，关系仍保留"""
        parent = RelParentModel(name="排除", title="T3")
        parent.address = SimpleVO(value="V")
        parent.add(True)

        child = RelChildModel(name="子", desc="D", parent_id=parent.id)
        child.add(True)

        data = parent.to_dict_with_relations(
            relations=["items"], exclude={"address"}
        )
        assert 'address' not in data
        assert 'items' in data

    def test_with_relations_no_flat_columns_leak(self):
        """to_dict_with_relations 默认嵌套模式下不泄露展开列"""
        parent = RelParentModel(name="不泄露", title="T4")
        parent.address = SimpleVO(value="V")
        parent.add(True)

        data = parent.to_dict_with_relations(relations=["items"])
        assert 'addr_value' not in data
        assert 'address' in data


# ==================== 风险点 6: __owned_composites__ 继承隔离 ====================

class TestOwnedCompositesInheritanceIsolation:
    """验证通过 Mixin 继承时 __owned_composites__ 的隔离性"""

    def test_mixin_a_has_composites(self):
        """仅继承 Mixin 的模型注册了 OwnsOne"""
        composites = getattr(RiskMixinModelA, '__owned_composites__', {})
        assert 'info' in composites

    def test_mixin_b_extends_not_replaces(self):
        """带额外 OwnsOne 的模型同时包含 Mixin 和自己的 OwnsOne"""
        composites = RiskMixinModelB.__owned_composites__
        assert 'info' in composites, "应继承 Mixin 的 owned composite"
        assert 'detail' in composites, "应包含自己新增的 owned composite"

    def test_b_does_not_pollute_a(self):
        """B 新增的 OwnsOne 不应出现在 A 的元数据中"""
        a_keys = set(getattr(RiskMixinModelA, '__owned_composites__', {}).keys())
        assert 'detail' not in a_keys

    def test_a_and_b_are_distinct_dicts(self):
        """A 和 B 的 __owned_composites__ 应是不同的 dict 对象"""
        a_dict = RiskMixinModelA.__dict__.get('__owned_composites__')
        b_dict = RiskMixinModelB.__dict__.get('__owned_composites__')

        assert a_dict is not None
        assert b_dict is not None
        assert a_dict is not b_dict

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_mixin_model_b_persistence(self):
        """带额外 OwnsOne 的 Mixin 模型读写正确"""
        obj = RiskMixinModelB(name="Mixin-B")
        obj.info = SimpleVO(value="来自 Mixin")
        obj.detail = StrictVO(name="来自自身", code="C01")
        obj.add(True)

        found = RiskMixinModelB.get(obj.id)
        assert found.info.value == "来自 Mixin"
        assert found.detail.name == "来自自身"

    def test_mixin_model_a_to_dict_only_has_info(self):
        """A 的 to_dict 只嵌套 info，不出现 detail"""
        obj = RiskMixinModelA(name="Mixin-A")
        obj.info = SimpleVO(value="仅A")
        obj.add(True)

        data = obj.to_dict()
        assert 'info' in data
        assert 'detail' not in data
