# SortableMixin 排序管理指南

## 概述

`SortableMixin` 提供通用的排序操作能力，支持：

- **简单列表排序**：全局排序，所有记录共用一个排序序列
- **分组排序**：按指定字段分组，组内独立排序
- **树形结构排序**：配合 `TreeMixin` 使用，实现同级节点排序

## 快速开始

### 安装和导入

```python
from yweb.orm import BaseModel, SortFieldMixin, SortableMixin
```

### 基本使用

```python
class Banner(BaseModel, SortFieldMixin, SortableMixin):
    """轮播图 - 简单排序"""
    __tablename__ = "banner"
    
    title = mapped_column(String(100))
    image_url = mapped_column(String(500))

# 使用排序方法
banner = Banner.get(1)
banner.move_up()          # 上移一位
banner.move_down()        # 下移一位
banner.move_to_top()      # 置顶
banner.move_to_bottom()   # 置底
banner.move_to(3)         # 移动到第3位

db.session.commit()  # 记得提交
```

## 组件说明

### SortFieldMixin

提供标准的 `sort_order` 字段定义：

```python
class SortFieldMixin:
    sort_order: Mapped[int] = mapped_column(
        Integer,
        default=0,
        nullable=False,
        index=True,
        comment="排序序号"
    )
```

**使用场景**：
- 需要排序字段但不需要树形字段时使用
- `TreeFieldsMixin` 已继承此 Mixin，无需重复添加

### SortableMixin

提供排序操作方法，**不包含**字段定义。

**配置属性**：

| 属性 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `__sort_field__` | str | `"sort_order"` | 排序字段名 |
| `__sort_group_by__` | str/list/None | `None` | 分组字段 |

## 使用场景

### 场景 1：简单列表排序

所有记录共用一个排序序列。

```python
class Banner(BaseModel, SortFieldMixin, SortableMixin):
    """轮播图"""
    __tablename__ = "banner"
    
    title = mapped_column(String(100))

# 创建时初始化排序号
banner = Banner(title="新轮播图")
banner.init_sort_order()  # 放到最后
db.session.add(banner)
db.session.commit()

# 或者放到最前
banner.init_sort_order(position="first")
```

### 场景 2：单字段分组排序

按某个字段分组，组内独立排序。

```python
class Product(BaseModel, SortFieldMixin, SortableMixin):
    """产品 - 按分类排序"""
    __tablename__ = "product"
    __sort_group_by__ = "category_id"  # 分组字段
    
    category_id = mapped_column(Integer)
    name = mapped_column(String(100))

# 分类1内上移
product = Product.get(1)  # category_id=1
product.move_up()  # 只在分类1内移动

# 获取分类1的排序列表
products = Product.get_sorted({"category_id": 1})
```

### 场景 3：多字段分组排序

按多个字段组合分组。

```python
class MenuItem(BaseModel, SortFieldMixin, SortableMixin):
    """菜单项 - 按(菜单ID, 父ID)分组"""
    __tablename__ = "menu_item"
    __sort_group_by__ = ["menu_id", "parent_id"]
    
    menu_id = mapped_column(Integer)
    parent_id = mapped_column(Integer, nullable=True)
    title = mapped_column(String(100))
```

### 场景 4：与 TreeMixin 结合

树形结构中实现同级节点排序。

```python
from yweb.orm.tree import TreeFieldsMixin, TreeMixin

class Category(BaseModel, TreeFieldsMixin, TreeMixin, SortableMixin):
    """分类 - 树形 + 排序"""
    __tablename__ = "category"
    __sort_group_by__ = "parent_id"  # 按父节点分组
    
    parent_id = mapped_column(Integer, ForeignKey("category.id"), nullable=True)
    name = mapped_column(String(100))

# TreeFieldsMixin 已包含 sort_order 字段，无需 SortFieldMixin
# 同级菜单内排序
menu = Category.get(1)
menu.move_up()    # 在同级中上移
menu.move_down()  # 在同级中下移
```

## API 参考

### 实例方法

#### 移动操作

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `move_up()` | bool | 上移一位 |
| `move_down()` | bool | 下移一位 |
| `move_to_top()` | bool | 置顶 |
| `move_to_bottom()` | bool | 置底 |
| `move_to(position)` | bool | 移动到指定位置（1-based） |
| `swap_with(other)` | None | 与另一对象交换位置 |

**返回值说明**：
- `True`：移动成功
- `False`：无法移动（已在边界或已在目标位置）

#### 查询方法

| 方法 | 返回值 | 说明 |
|------|--------|------|
| `get_sort_position()` | int | 获取当前位置（1-based） |
| `get_previous()` | Self/None | 获取前一个对象 |
| `get_next()` | Self/None | 获取后一个对象 |

#### 初始化方法

| 方法 | 参数 | 说明 |
|------|------|------|
| `init_sort_order(position)` | `"last"` 或 `"first"` | 初始化排序号 |

### 类方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_max_sort_order(group_filters)` | dict/None | int | 获取最大排序号 |
| `get_min_sort_order(group_filters)` | dict/None | int | 获取最小排序号 |
| `reorder(ids, group_filters)` | List[id], dict/None | int | 批量重排序 |
| `normalize_sort_order(group_filters)` | dict/None | int | 规范化排序号 |
| `get_sorted(group_filters, desc)` | dict/None, bool | List | 获取排序后的列表 |

## 典型应用

### 前端拖拽排序

```python
@app.post("/banners/reorder")
def reorder_banners(ids: List[int]):
    """前端拖拽后提交新顺序"""
    count = Banner.reorder(ids)
    db.session.commit()
    return {"updated": count}
```

### 删除后规范化

```python
@app.delete("/products/{id}")
def delete_product(id: int):
    """删除产品后规范化排序号"""
    product = Product.get(id)
    category_id = product.category_id
    
    product.delete()
    db.session.commit()
    
    # 消除间隙
    Product.normalize_sort_order({"category_id": category_id})
    db.session.commit()
```

### 移动到指定位置

```python
@app.put("/products/{id}/move")
def move_product(id: int, position: int):
    """将产品移动到指定位置"""
    product = Product.get(id)
    product.move_to(position)
    db.session.commit()
    return {"position": product.get_sort_position()}
```

## 自定义排序字段

如果排序字段不叫 `sort_order`：

```python
class Article(BaseModel, SortableMixin):
    __tablename__ = "article"
    __sort_field__ = "display_order"  # 自定义字段名
    
    display_order = mapped_column(Integer, default=0)
    title = mapped_column(String(200))
```

## 最佳实践

1. **继承顺序**：`BaseModel` → `SortFieldMixin` → `SortableMixin`

2. **树形结构**：使用 `TreeFieldsMixin` 时无需 `SortFieldMixin`
   ```python
   # 正确
   class Menu(BaseModel, TreeFieldsMixin, TreeMixin, SortableMixin):
       pass
   
   # 错误（重复定义 sort_order）
   class Menu(BaseModel, TreeFieldsMixin, SortFieldMixin, TreeMixin, SortableMixin):
       pass
   ```

3. **分组排序**：配置 `__sort_group_by__` 后，所有操作自动在组内进行

4. **批量操作**：使用 `reorder()` 比多次 `move_to()` 更高效

5. **间隙清理**：定期调用 `normalize_sort_order()` 保持排序号连续

## 与其他 Mixin 的关系

| Mixin | 包含 sort_order | 说明 |
|-------|-----------------|------|
| `SortFieldMixin` | ✅ | 排序字段定义 |
| `TreeFieldsMixin` | ✅（继承自 SortFieldMixin） | 树形字段 + 排序字段 |
| `SortableMixin` | ❌ | 排序操作方法 |

## 注意事项

1. **提交事务**：排序操作后需调用 `db.session.commit()`

2. **并发安全**：高并发场景建议使用数据库锁或乐观锁

3. **性能考虑**：
   - `move_to_top()` 和 `move_to_bottom()` 会更新多条记录
   - 大量数据时考虑使用间隔排序法（如排序号间隔1000）

4. **NULL 处理**：分组字段为 NULL 时，会正确匹配 `IS NULL`
