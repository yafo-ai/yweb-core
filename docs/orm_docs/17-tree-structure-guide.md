# 树形结构指南 (Tree Structure Guide)

本文档介绍 `yweb.orm.tree` 模块的使用方法，该模块提供通用的树形结构支持。

## 目录

- [概述](#概述)
- [快速开始](#快速开始)
- [模型定义](#模型定义)
- [TreeMixin 方法详解](#treemixin-方法详解)
- [工具函数](#工具函数)
- [最佳实践](#最佳实践)
- [迁移指南](#迁移指南)

## 概述

`yweb.orm.tree` 模块使用**物化路径（Materialized Path）**模式实现树形结构，主要特点：

- **高效查询**：祖先/子孙查询使用 LIKE 前缀匹配，性能优秀
- **多主键支持**：支持整数、UUID、字符串等多种主键类型
- **可配置**：路径分隔符、排序字段等可自定义
- **丰富的工具函数**：提供树形数据转换、过滤等工具

### 物化路径模式

每个节点存储从根到自身的完整路径：

```
/1/           # 根节点（id=1）
/1/2/         # 一级子节点（id=2）
/1/2/5/       # 二级子节点（id=5）
/1/3/         # 另一个一级子节点（id=3）
```

## 快速开始

### 安装导入

```python
from yweb.orm import BaseModel
from yweb.orm.tree import TreeMixin, TreeFieldsMixin
```

### 最简单的树形模型

```python
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

class Category(BaseModel, TreeFieldsMixin, TreeMixin):
    """分类模型"""
    __tablename__ = "category"
    
    # parent_id 需要自行定义（因为外键目标表名不同）
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("category.id"), nullable=True
    )
    
    # path, level, sort_order 由 TreeFieldsMixin 自动提供
    
    # 业务字段
    title: Mapped[str] = mapped_column(String(100))
```

### 基本使用

```python
# 创建根节点
root = Category(title="电子产品")
root.update_path_and_level()
root.save(commit=True)

# 创建子节点
child = Category(title="手机", parent_id=root.id)
child.update_path_and_level()
child.save(commit=True)

# 查询
children = root.get_children()      # 直接子节点
descendants = root.get_descendants() # 所有子孙
ancestors = child.get_ancestors()    # 所有祖先

# 移动节点
child.move_to(new_parent_id)

# 获取树形结构
tree = Category.get_tree_list()
```

## 模型定义

### 方式1：使用 TreeFieldsMixin（推荐）

`TreeFieldsMixin` 自动提供 `path`、`level`、`sort_order` 字段：

```python
class Menu(BaseModel, TreeFieldsMixin, TreeMixin):
    __tablename__ = "menu"
    
    # 只需定义 parent_id
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("menu.id"), nullable=True
    )
    
    # 业务字段
    title: Mapped[str] = mapped_column(String(100))
    icon: Mapped[str] = mapped_column(String(50), nullable=True)
```

### 方式2：自定义字段

需要完全控制字段定义时：

```python
class Department(BaseModel, TreeMixin):
    __tablename__ = "department"
    
    # 必需字段
    parent_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("department.id"), nullable=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    
    # 业务字段
    name: Mapped[str] = mapped_column(String(100))
```

### 字段要求

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | int/str | 主键（继承自 BaseModel） |
| `parent_id` | int/str | 父节点 ID，与 id 类型一致 |
| `path` | str | 路径字符串，如 `/1/2/3/` |
| `level` | int | 层级，根节点为 1 |
| `sort_order` | int | 排序序号（可选） |

### 可配置属性

```python
class Menu(BaseModel, TreeMixin):
    # 自定义路径分隔符（默认 "/"）
    PATH_SEPARATOR = "/"
    
    # 自定义排序字段名（默认 "sort_order"）
    __tree_sort_field__ = "display_order"
```

## TreeMixin 方法详解

### 路径与层级

```python
# 构建路径
node.build_path()           # 返回 "/1/2/3/"

# 计算层级
node.calculate_level()      # 返回层级数

# 更新路径和层级（创建/移动节点后调用）
node.update_path_and_level()
```

### 节点查询

```python
# 获取直接子节点
children = node.get_children()

# 获取所有子孙节点
descendants = node.get_descendants()

# 获取所有祖先节点
ancestors = node.get_ancestors()

# 获取父节点
parent = node.get_parent()

# 获取兄弟节点（不含自己）
siblings = node.get_siblings()

# 获取根节点
root = node.get_root()
```

### 状态判断

```python
node.is_root()              # 是否根节点
node.is_leaf()              # 是否叶子节点
node.is_ancestor_of(other)  # 是否为 other 的祖先
node.is_descendant_of(other) # 是否为 other 的子孙
```

### 统计方法

```python
node.get_descendant_count() # 子孙总数
node.get_children_count()   # 直接子节点数
node.get_depth()            # 子树深度
```

### 节点操作

```python
# 移动节点（自动更新子孙路径）
node.move_to(new_parent_id)
```

### 便捷方法

```python
# 获取完整路径名称
node.get_path_names(separator=" > ")  # "一级 > 二级 > 三级"

# 获取路径 ID 列表
node.get_path_ids()  # [1, 2, 3]
```

### 类方法

```python
# 获取所有根节点
roots = Menu.get_roots()

# 获取树形结构（嵌套格式）
tree = Menu.get_tree_list()

# 重建所有路径
count = Menu.rebuild_all_paths()
```

## 工具函数

### build_tree_list

将扁平列表转换为嵌套树结构：

```python
from yweb.orm.tree import build_tree_list

flat_data = [
    {"id": 1, "parent_id": None, "name": "根"},
    {"id": 2, "parent_id": 1, "name": "子1"},
    {"id": 3, "parent_id": 1, "name": "子2"},
]

tree = build_tree_list(flat_data)
# 结果:
# [
#     {"id": 1, "name": "根", "children": [
#         {"id": 2, "name": "子1", "children": []},
#         {"id": 3, "name": "子2", "children": []},
#     ]}
# ]
```

### flatten_tree

将嵌套树展平为列表：

```python
from yweb.orm.tree import flatten_tree

flat = flatten_tree(tree, level_field="depth")
# 结果: [{"id": 1, "name": "根", "depth": 1}, ...]
```

### find_node_in_tree

在树中查找节点：

```python
from yweb.orm.tree import find_node_in_tree

node = find_node_in_tree(tree, target_id=2)
```

### filter_tree

过滤树节点：

```python
from yweb.orm.tree import filter_tree

# 只保留 is_active=True 的节点
filtered = filter_tree(tree, lambda n: n.get("is_active"))
```

### 其他工具

```python
from yweb.orm.tree import (
    get_node_path,           # 获取从根到目标的路径
    calculate_tree_depth,    # 计算树深度
    validate_no_circular_reference,  # 验证无循环引用
)
```

## 最佳实践

### 1. 创建节点时更新路径

```python
def create_node(title, parent_id=None):
    node = Menu(title=title, parent_id=parent_id)
    node.update_path_and_level()  # 重要！
    node.save(commit=True)
    return node
```

### 2. 批量创建时按层级顺序

```python
# 先创建父节点，再创建子节点
root = create_node("根")
child1 = create_node("子1", root.id)
child2 = create_node("子2", root.id)
grandchild = create_node("孙", child1.id)
```

### 3. 移动节点使用 move_to

```python
# 正确方式：使用 move_to，自动更新子孙路径
node.move_to(new_parent_id)
node.save(commit=True)

# 错误方式：直接修改 parent_id 会导致子孙路径不一致
# node.parent_id = new_parent_id  # 不要这样做！
```

### 4. 数据修复

如果路径数据不一致，可以重建：

```python
from yweb.orm import transactional

@transactional
def fix_tree_paths():
    """修复树形结构路径（使用 @transactional 自动提交）"""
    count = Menu.rebuild_all_paths()
    print(f"更新了 {count} 个节点")
    return count

# 调用修复函数
fix_tree_paths()
```

### 5. 大数据量优化

对于大量数据，考虑分批处理：

```python
# 获取指定深度的节点
shallow_nodes = Menu.query.filter(Menu.level <= 3).all()

# 使用 path 前缀快速过滤
subtree = Menu.query.filter(Menu.path.like("/1/2/%")).all()
```

### 新增功能


- `TreeFieldsMixin` - 简化字段定义
- `get_path_names()` - 获取路径名称
- `get_tree_list()` - 获取嵌套树结构
- `rebuild_all_paths()` - 重建所有路径
- 完整的工具函数集

## 示例代码

完整示例请参考：`examples/orm/demo_tree_mixin.py`

```bash
python -m examples.orm.demo_tree_mixin
```
