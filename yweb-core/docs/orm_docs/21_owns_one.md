# 21. OwnsOne 值对象嵌入

## 概述

`OwnsOne` 用于将一个**值对象**（Value Object）的多个字段展开存储到父模型的同一张表中，无需创建独立的关联表。适用于"地址"、"价格区间"、"联系方式"等没有独立生命周期的嵌套数据。

### 与 OneToOne 的区别

| 对比项 | `OneToOne` | `OwnsOne` |
|--------|-----------|-----------|
| 数据表 | 两张表 | 一张表 |
| 子对象主键 | 有 | 无 |
| 生命周期 | 可相对独立 | 完全依附父对象 |
| 查询方式 | JOIN 关系 | 父表直接读取 |
| 适用场景 | 用户-档案、订单-扩展实体 | 地址、金额、时间范围、联系人 |

**判断建议**：子对象需要独立增删改查 → `OneToOne`；子对象只是父对象的一部分 → `OwnsOne`。

---

## 定义值对象

```python
from sqlalchemy import String, Integer
from yweb.orm import OwnedType, owned_field


class Address(OwnedType):
    """地址值对象"""
    street   = owned_field(String(200), nullable=False, comment="街道")
    city     = owned_field(String(100), nullable=False, comment="城市")
    province = owned_field(String(100), nullable=False, comment="省份")
    zip_code = owned_field(String(20),  nullable=True,  comment="邮编")


class PriceRange(OwnedType):
    """价格区间值对象"""
    min_price = owned_field(Integer, nullable=False, comment="最低价")
    max_price = owned_field(Integer, nullable=False, comment="最高价")
```

**要点**：

- 继承 `OwnedType`（基于 SQLAlchemy `MutableComposite`，支持原地修改追踪）
- 用 `owned_field()` 声明每个字段，参数与 `mapped_column` 类似
- 值对象不对应独立的数据库表

### owned_field 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `column_type` | SQLAlchemy Type | 必填 | 列类型，如 `String(200)`、`Integer` |
| `nullable` | bool | `True` | 该列是否允许为空 |
| `comment` | str | `None` | 数据库列注释 |
| `default` | Any | `None` | 默认值 |
| `**kwargs` | dict | — | 传递给 `mapped_column` 的其他参数 |

---

## 在模型中使用 OwnsOne

```python
from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column
from yweb.orm import BaseModel, OwnsOne


class Order(BaseModel):
    __tablename__ = "orders"

    order_no: Mapped[str] = mapped_column(String(50), comment="订单号")

    # 必填地址
    shipping_address = OwnsOne(Address, prefix="shipping")

    # 可选地址（整个值对象可以为空）
    billing_address  = OwnsOne(Address, prefix="billing", nullable=True)


class Product(BaseModel):
    __tablename__ = "products"

    title: Mapped[str] = mapped_column(String(100), comment="商品名")

    # comment_prefix 会拼到每个列注释前，如 "价格区间-最低价"
    price_range = OwnsOne(PriceRange, prefix="price", comment_prefix="价格区间")
```

### OwnsOne 参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `owned_type` | class | 必填 | OwnedType 子类 |
| `prefix` | str | 属性名 | 展开列名前缀，如 `shipping` → `shipping_street` |
| `nullable` | bool | `False` | 整个值对象是否允许为空 |
| `comment_prefix` | str | `None` | 列注释前缀，拼接为 `"前缀-原注释"` |

### 自动生成的数据库列

以 `Order` 为例：

| 列名 | 类型 | 注释 |
|------|------|------|
| `shipping_street` | String(200) | 街道 |
| `shipping_city` | String(100) | 城市 |
| `shipping_province` | String(100) | 省份 |
| `shipping_zip_code` | String(20) | 邮编 |
| `billing_street` | String(200) | 街道 |
| `billing_city` | String(100) | 城市 |
| ... | ... | ... |

### nullable 覆盖规则

`OwnsOne(nullable=True)` 时，所有展开列的 `nullable` 会被**强制覆盖为 `True`**，即使 `owned_field` 中声明了 `nullable=False`。这确保整个值对象可以存储为 NULL。

`OwnsOne(nullable=False)` 时，保留每个 `owned_field` 自身的 `nullable` 设置。

---

## CRUD 操作

### 创建

```python
# 方式1：通过值对象赋值
order = Order(name="测试订单", order_no="ORD-001")
order.shipping_address = Address(
    street="世纪大道1号",
    city="上海",
    province="上海",
    zip_code="200120",
)
order.add(commit=True)

# 方式2：通过展开列直接赋值
order = Order(
    name="测试订单2",
    order_no="ORD-002",
    shipping_street="南京路100号",
    shipping_city="上海",
    shipping_province="上海",
)
order.add(commit=True)
```

### 读取

```python
found = Order.get(order.id)
print(found.shipping_address.city)       # → "上海"
print(found.shipping_address.zip_code)   # → "200120"
```

### 原地修改（自动变更追踪）

```python
found.shipping_address.city = "北京"
found.update(commit=True)
# MutableComposite 自动追踪字段级修改，无需整体替换
```

### 整体替换

```python
found.shipping_address = Address(street="新街", city="深圳", province="广东")
found.update(commit=True)
```

### 清空（nullable 场景）

```python
found.billing_address = None
found.update(commit=True)
```

---

## 查询

`OwnsOne` 通过 `comparator_factory` 实现嵌套属性代理，支持透明的查询语法。

### 按嵌套字段查询（推荐）

```python
# 按单个字段过滤
orders = Order.query.filter(
    Order.shipping_address.city == "上海"
).all()

# 组合多个字段
orders = Order.query.filter(
    Order.shipping_address.province == "广东",
    Order.shipping_address.city == "深圳",
).all()
```

### 支持的 SQL 操作符

```python
Order.query.filter(Order.shipping_address.city.like("上%")).all()
Order.query.filter(Order.shipping_address.zip_code.is_(None)).all()
Order.query.filter(Order.shipping_address.city.in_(["上海", "北京"])).all()
```

### 按展开列查询（等价写法）

```python
# 直接使用展开列名，两种写法等价
Order.query.filter(Order.shipping_city == "上海").all()
```

---

## 序列化

### to_dict() — 默认嵌套输出

```python
order.to_dict()
# {
#     "id": 1,
#     "order_no": "ORD-001",
#     "shipping_address": {
#         "street": "世纪大道1号",
#         "city": "上海",
#         "province": "上海",
#         "zip_code": "200120"
#     },
#     "billing_address": null,
#     ...
# }
```

默认嵌套模式下：
- 展开列（`shipping_street` 等）不会出现在顶层
- 值对象为空时输出 `null`

### to_dict(flatten_owned=True) — 平铺输出

```python
order.to_dict(flatten_owned=True)
# {
#     "id": 1,
#     "order_no": "ORD-001",
#     "shipping_street": "世纪大道1号",
#     "shipping_city": "上海",
#     ...
# }
```

平铺模式下：
- 展开列直接出现在顶层
- 不输出嵌套字典

### exclude 排除

```python
# 排除整个值对象
order.to_dict(exclude={"shipping_address"})

# 平铺模式下也可排除展开列
order.to_dict(flatten_owned=True, exclude={"shipping_zip_code"})
```

### to_dict_with_relations() 兼容

`to_dict_with_relations()` 内部调用 `to_dict()`，因此值对象自动以嵌套形式输出，不会泄露展开列：

```python
order.to_dict_with_relations(relations=["items"])
# shipping_address 以嵌套形式输出
# items 作为关联数据输出
```

---

## 值对象继承

值对象支持继承，子类自动包含父类的所有字段。

```python
class BaseLocation(OwnedType):
    longitude = owned_field(String(20), comment="经度")
    latitude  = owned_field(String(20), comment="纬度")


class DetailedLocation(BaseLocation):
    altitude = owned_field(String(20), comment="海拔")


class Warehouse(BaseModel):
    __tablename__ = "warehouses"

    title: Mapped[str] = mapped_column(String(100), comment="仓库名")
    location = OwnsOne(DetailedLocation, prefix="loc")
    # 自动展开列：loc_longitude, loc_latitude, loc_altitude
```

**要点**：子类继承不会影响父类的 `__owned_fields__`，两者独立隔离。

---

## 在 Mixin 中使用

`OwnsOne` 可以在 Mixin 类中定义，框架会通过 MRO 扫描自动识别并处理：

```python
class AddressMixin:
    """地址 Mixin"""
    address = OwnsOne(Address, prefix="addr")


class Store(AddressMixin, BaseModel):
    __tablename__ = "stores"
    title: Mapped[str] = mapped_column(String(100), comment="店铺名")
    # 自动拥有 addr_street, addr_city 等展开列


class Supplier(AddressMixin, BaseModel):
    __tablename__ = "suppliers"
    company: Mapped[str] = mapped_column(String(100), comment="公司名")
    # 各模型的 __owned_composites__ 独立隔离
```

---

## 值对象工具方法

### to_dict()

```python
addr = Address(street="A", city="B", province="C", zip_code="100000")
addr.to_dict()
# {"street": "A", "city": "B", "province": "C", "zip_code": "100000"}
```

### 空判断

```python
empty = Address()
bool(empty)       # → False
empty.is_empty    # → True

nonempty = Address(street="有值")
bool(nonempty)    # → True
nonempty.is_empty # → False
```

### 相等比较（按值）

```python
addr1 = Address(street="A", city="B", province="C")
addr2 = Address(street="A", city="B", province="C")
addr1 == addr2  # → True
```

### coerce 类型转换

支持 dict 和 None 赋值，由 SQLAlchemy 自动调用：

```python
# dict 赋值自动转为值对象
order.shipping_address = {"street": "X", "city": "Y", "province": "Z"}

# None 赋值清空
order.billing_address = None
```

---

## 速查表

| 操作 | 写法 |
|------|------|
| 定义值对象 | `class Foo(OwnedType): x = owned_field(...)` |
| 挂载到模型 | `foo = OwnsOne(Foo, prefix="foo")` |
| 可选值对象 | `OwnsOne(Foo, prefix="foo", nullable=True)` |
| 列注释前缀 | `OwnsOne(Foo, prefix="foo", comment_prefix="前缀")` |
| 实例读写 | `obj.foo.x` / `obj.foo.x = val` |
| 查询过滤 | `Model.foo.x == val` |
| 嵌套序列化 | `obj.to_dict()` （默认） |
| 平铺序列化 | `obj.to_dict(flatten_owned=True)` |
| 排除输出 | `obj.to_dict(exclude={"foo"})` |
| 空判断 | `if not obj.foo:` / `obj.foo.is_empty` |

---

## 下一步

- [03_关系定义](03_relationships.md) — 对比 OneToOne / ManyToOne 等实体关系
- [13_数据序列化](13_serialization.md) — 了解 to_dict / DTO 完整功能
