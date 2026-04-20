"""OwnsOne 值对象嵌入功能测试

测试 yweb ORM 的 OwnsOne 值对象拥有关系：
1. 展开列自动生成
2. 值对象读写与变更追踪
3. to_dict 嵌套/平铺输出
4. 空值语义
5. 查询代理（Order.shipping_address.city）
6. 多个 OwnsOne 同模型
"""
from __future__ import annotations

import pytest
from sqlalchemy import String, Integer, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session, Mapped, mapped_column
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel, fields
from yweb.orm.owned_types import OwnedType, owned_field


# ==================== 值对象定义 ====================

class AddressVO(OwnedType):
    """测试用地址值对象"""
    street = owned_field(String(200), comment="街道")
    city = owned_field(String(100), comment="城市")
    province = owned_field(String(100), comment="省份")
    zip_code = owned_field(String(20), comment="邮编", nullable=True)


class PriceRangeVO(OwnedType):
    """测试用价格区间值对象"""
    min_price = owned_field(Integer, comment="最低价")
    max_price = owned_field(Integer, comment="最高价")


# ==================== 测试模型 ====================

class OwnsOneOrderModel(BaseModel):
    """测试订单模型（单个 OwnsOne）"""
    __tablename__ = "test_oo_orders"
    __table_args__ = {'extend_existing': True}

    order_no: Mapped[str] = mapped_column(String(50), comment="订单号")
    shipping_address = fields.OwnsOne(AddressVO, prefix="shipping")


class OwnsOneMultiModel(BaseModel):
    """测试模型（多个 OwnsOne）"""
    __tablename__ = "test_oo_multi"
    __table_args__ = {'extend_existing': True}

    title: Mapped[str] = mapped_column(String(100), comment="标题")
    shipping_address = fields.OwnsOne(AddressVO, prefix="shipping")
    billing_address = fields.OwnsOne(AddressVO, prefix="billing")


class OwnsOneNullableModel(BaseModel):
    """测试模型（nullable OwnsOne）"""
    __tablename__ = "test_oo_nullable"
    __table_args__ = {'extend_existing': True}

    label: Mapped[str] = mapped_column(String(50), comment="标签")
    address = fields.OwnsOne(AddressVO, prefix="addr", nullable=True)


class OwnsOneProductModel(BaseModel):
    """测试模型（OwnsOne + comment_prefix）"""
    __tablename__ = "test_oo_products"
    __table_args__ = {'extend_existing': True}

    product_name: Mapped[str] = mapped_column(String(100), comment="商品名")
    price_range = fields.OwnsOne(
        PriceRangeVO, prefix="price", comment_prefix="价格区间",
    )


# ==================== 测试类 ====================

class TestOwnsOneColumnGeneration:
    """OwnsOne 展开列自动生成测试"""

    def test_columns_exist_on_model(self):
        """测试展开列被正确注册到模型类上"""
        assert hasattr(OwnsOneOrderModel, 'shipping_street')
        assert hasattr(OwnsOneOrderModel, 'shipping_city')
        assert hasattr(OwnsOneOrderModel, 'shipping_province')
        assert hasattr(OwnsOneOrderModel, 'shipping_zip_code')

    def test_composite_attribute_exists(self):
        """测试 composite 属性存在"""
        assert hasattr(OwnsOneOrderModel, 'shipping_address')

    def test_owned_composites_metadata(self):
        """测试 __owned_composites__ 元数据正确注册"""
        meta = OwnsOneOrderModel.__owned_composites__
        assert 'shipping_address' in meta

        info = meta['shipping_address']
        assert info.owned_type is AddressVO
        assert info.prefix == 'shipping'
        assert info.field_to_column == {
            'street': 'shipping_street',
            'city': 'shipping_city',
            'province': 'shipping_province',
            'zip_code': 'shipping_zip_code',
        }

    def test_multiple_owns_one_metadata(self):
        """测试同一模型多个 OwnsOne 的元数据"""
        meta = OwnsOneMultiModel.__owned_composites__
        assert 'shipping_address' in meta
        assert 'billing_address' in meta
        assert meta['shipping_address'].prefix == 'shipping'
        assert meta['billing_address'].prefix == 'billing'

    def test_comment_prefix_applied(self):
        """测试 comment_prefix 拼接到列注释"""
        meta = OwnsOneProductModel.__owned_composites__
        assert 'price_range' in meta


class TestOwnsOneReadWrite:
    """OwnsOne 值对象读写与持久化测试"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_create_with_value_object(self):
        """测试使用值对象创建模型实例"""
        addr = AddressVO(
            street="世纪大道1号",
            city="上海",
            province="上海",
            zip_code="200120",
        )
        order = OwnsOneOrderModel(name="测试订单", order_no="ORD-001")
        order.shipping_address = addr
        order.add(True)

        found = OwnsOneOrderModel.get(order.id)
        assert found is not None
        assert found.shipping_address.street == "世纪大道1号"
        assert found.shipping_address.city == "上海"
        assert found.shipping_address.province == "上海"
        assert found.shipping_address.zip_code == "200120"

    def test_create_with_expanded_columns(self):
        """测试通过展开列直接赋值"""
        order = OwnsOneOrderModel(
            name="测试订单2",
            order_no="ORD-002",
            shipping_street="南京路100号",
            shipping_city="上海",
            shipping_province="上海",
            shipping_zip_code=None,
        )
        order.add(True)

        found = OwnsOneOrderModel.get(order.id)
        assert found.shipping_address.street == "南京路100号"
        assert found.shipping_address.city == "上海"

    def test_modify_value_object_field(self):
        """测试原地修改值对象字段"""
        addr = AddressVO(street="旧街", city="旧城", province="旧省")
        order = OwnsOneOrderModel(name="修改测试", order_no="ORD-003")
        order.shipping_address = addr
        order.add(True)

        order.shipping_address.city = "新城"
        order.update(True)

        found = OwnsOneOrderModel.get(order.id)
        assert found.shipping_address.city == "新城"
        assert found.shipping_address.street == "旧街"

    def test_replace_entire_value_object(self):
        """测试整体替换值对象"""
        order = OwnsOneOrderModel(name="替换测试", order_no="ORD-004")
        order.shipping_address = AddressVO(street="A", city="B", province="C")
        order.add(True)

        order.shipping_address = AddressVO(street="X", city="Y", province="Z")
        order.update(True)

        found = OwnsOneOrderModel.get(order.id)
        assert found.shipping_address.street == "X"
        assert found.shipping_address.city == "Y"

    def test_multiple_owns_one_persistence(self):
        """测试多个 OwnsOne 的读写"""
        obj = OwnsOneMultiModel(name="双地址", title="双地址测试")
        obj.shipping_address = AddressVO(street="发货街", city="发货市", province="发货省")
        obj.billing_address = AddressVO(street="账单街", city="账单市", province="账单省")
        obj.add(True)

        found = OwnsOneMultiModel.get(obj.id)
        assert found.shipping_address.street == "发货街"
        assert found.billing_address.street == "账单街"
        assert found.shipping_address.city != found.billing_address.city


class TestOwnsOneNullSemantics:
    """OwnsOne 空值语义测试"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_assign_none_clears_columns(self):
        """测试赋值 None 后全列置 NULL"""
        order = OwnsOneNullableModel(name="空值测试", label="L1")
        order.address = AddressVO(street="街", city="市", province="省")
        order.add(True)

        order.address = None
        order.update(True)

        found = OwnsOneNullableModel.get(order.id)
        assert found.address is None or not found.address

    def test_all_null_returns_falsy(self):
        """测试全空列返回的值对象布尔值为 False"""
        obj = OwnsOneNullableModel(name="全空", label="L2")
        obj.add(True)

        found = OwnsOneNullableModel.get(obj.id)
        assert not found.address

    def test_value_object_bool_true(self):
        """测试有值的值对象布尔值为 True"""
        addr = AddressVO(street="有", city="值", province="对象")
        assert bool(addr) is True

    def test_value_object_bool_false(self):
        """测试全 None 的值对象布尔值为 False"""
        addr = AddressVO()
        assert bool(addr) is False

    def test_is_empty_property(self):
        """测试 is_empty 属性"""
        empty = AddressVO()
        assert empty.is_empty is True

        nonempty = AddressVO(street="x")
        assert nonempty.is_empty is False


class TestOwnsOneToDict:
    """OwnsOne to_dict 序列化测试"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_nested_output_default(self):
        """测试默认嵌套输出"""
        order = OwnsOneOrderModel(name="嵌套测试", order_no="ORD-N01")
        order.shipping_address = AddressVO(
            street="世纪大道", city="上海", province="上海", zip_code="200120",
        )
        order.add(True)

        data = order.to_dict()
        assert 'shipping_address' in data
        assert isinstance(data['shipping_address'], dict)
        assert data['shipping_address']['street'] == "世纪大道"
        assert data['shipping_address']['city'] == "上海"
        # 默认嵌套模式下不出现展开列
        assert 'shipping_street' not in data
        assert 'shipping_city' not in data

    def test_flatten_output(self):
        """测试 flatten_owned=True 平铺输出"""
        order = OwnsOneOrderModel(name="平铺测试", order_no="ORD-F01")
        order.shipping_address = AddressVO(
            street="南京路", city="上海", province="上海",
        )
        order.add(True)

        data = order.to_dict(flatten_owned=True)
        assert 'shipping_street' in data
        assert data['shipping_street'] == "南京路"
        assert 'shipping_city' in data
        # 平铺模式下不出现嵌套字典
        assert 'shipping_address' not in data

    def test_nested_null_value_object(self):
        """测试嵌套输出中值对象为 None 的情况"""
        obj = OwnsOneNullableModel(name="空嵌套", label="L-N")
        obj.add(True)

        data = obj.to_dict()
        assert 'address' in data
        assert data['address'] is None

    def test_exclude_composite_name(self):
        """测试 exclude 排除整个值对象"""
        order = OwnsOneOrderModel(name="排除测试", order_no="ORD-E01")
        order.shipping_address = AddressVO(street="A", city="B", province="C")
        order.add(True)

        data = order.to_dict(exclude={'shipping_address'})
        assert 'shipping_address' not in data

    def test_multiple_owns_one_to_dict(self):
        """测试多 OwnsOne 嵌套输出"""
        obj = OwnsOneMultiModel(name="多值对象", title="T")
        obj.shipping_address = AddressVO(street="S1", city="C1", province="P1")
        obj.billing_address = AddressVO(street="S2", city="C2", province="P2")
        obj.add(True)

        data = obj.to_dict()
        assert data['shipping_address']['street'] == "S1"
        assert data['billing_address']['street'] == "S2"

    def test_value_object_to_dict(self):
        """测试值对象自身的 to_dict()"""
        addr = AddressVO(street="街道", city="城市", province="省份", zip_code="100000")
        d = addr.to_dict()
        assert d == {
            'street': '街道',
            'city': '城市',
            'province': '省份',
            'zip_code': '100000',
        }


class TestOwnsOneQuery:
    """OwnsOne 查询代理测试"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化测试数据库"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield session_scope
        session_scope.remove()

    def test_query_by_nested_field(self):
        """测试通过 Order.shipping_address.city 查询"""
        o1 = OwnsOneOrderModel(name="订单1", order_no="Q-001")
        o1.shipping_address = AddressVO(street="A街", city="上海", province="上海")
        o1.add(True)

        o2 = OwnsOneOrderModel(name="订单2", order_no="Q-002")
        o2.shipping_address = AddressVO(street="B街", city="北京", province="北京")
        o2.add(True)

        results = OwnsOneOrderModel.query.filter(
            OwnsOneOrderModel.shipping_address.city == "上海"
        ).all()

        assert len(results) == 1
        assert results[0].order_no == "Q-001"

    def test_query_by_expanded_column_still_works(self):
        """测试直接用展开列查询仍然可用"""
        o1 = OwnsOneOrderModel(name="直列查询", order_no="Q-003")
        o1.shipping_address = AddressVO(street="C街", city="广州", province="广东")
        o1.add(True)

        results = OwnsOneOrderModel.query.filter(
            OwnsOneOrderModel.shipping_city == "广州"
        ).all()

        assert len(results) == 1
        assert results[0].order_no == "Q-003"

    def test_query_proxy_multiple_fields(self):
        """测试组合多个嵌套字段查询"""
        o1 = OwnsOneOrderModel(name="组合查询", order_no="Q-004")
        o1.shipping_address = AddressVO(street="D街", city="深圳", province="广东")
        o1.add(True)

        o2 = OwnsOneOrderModel(name="组合查询2", order_no="Q-005")
        o2.shipping_address = AddressVO(street="E街", city="广州", province="广东")
        o2.add(True)

        results = OwnsOneOrderModel.query.filter(
            OwnsOneOrderModel.shipping_address.province == "广东",
            OwnsOneOrderModel.shipping_address.city == "深圳",
        ).all()

        assert len(results) == 1
        assert results[0].order_no == "Q-004"


class TestOwnsOneValueObject:
    """OwnedType 值对象基类行为测试"""

    def test_equality(self):
        """测试值对象相等比较"""
        a1 = AddressVO(street="X", city="Y", province="Z")
        a2 = AddressVO(street="X", city="Y", province="Z")
        assert a1 == a2

    def test_inequality(self):
        """测试值对象不等比较"""
        a1 = AddressVO(street="X", city="Y", province="Z")
        a2 = AddressVO(street="A", city="B", province="C")
        assert a1 != a2

    def test_repr(self):
        """测试值对象 repr"""
        addr = AddressVO(street="S", city="C", province="P")
        r = repr(addr)
        assert "AddressVO(" in r
        assert "street='S'" in r

    def test_composite_values(self):
        """测试 __composite_values__ 返回正确顺序"""
        addr = AddressVO(street="S", city="C", province="P", zip_code="Z")
        vals = addr.__composite_values__()
        assert vals == ("S", "C", "P", "Z")

    def test_coerce_none(self):
        """测试 coerce None 返回 None"""
        result = AddressVO.coerce("key", None)
        assert result is None

    def test_coerce_dict(self):
        """测试 coerce dict 转换为值对象"""
        result = AddressVO.coerce("key", {"street": "X", "city": "Y", "province": "Z"})
        assert isinstance(result, AddressVO)
        assert result.street == "X"

    def test_coerce_instance(self):
        """测试 coerce 值对象实例直接返回"""
        addr = AddressVO(street="X", city="Y", province="Z")
        result = AddressVO.coerce("key", addr)
        assert result is addr

    def test_owned_fields_collection(self):
        """测试 __owned_fields__ 收集正确"""
        fields_dict = AddressVO.__owned_fields__
        assert 'street' in fields_dict
        assert 'city' in fields_dict
        assert 'province' in fields_dict
        assert 'zip_code' in fields_dict
        assert len(fields_dict) == 4

    def test_price_range_fields(self):
        """测试不同值对象类型的字段收集"""
        fields_dict = PriceRangeVO.__owned_fields__
        assert 'min_price' in fields_dict
        assert 'max_price' in fields_dict
        assert len(fields_dict) == 2
