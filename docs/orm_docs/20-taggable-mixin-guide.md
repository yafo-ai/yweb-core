# TaggableMixin 标签系统指南

## 概述

`TaggableMixin` 提供通用的标签功能，支持：

- **多态关联**：任意模型可共享同一套标签系统
- **标签分组**：按类别组织标签（如"技术"、"难度"）
- **标签层级**：支持父子关系的层级标签
- **使用统计**：自动维护标签使用次数

## 快速开始

### 1. 定义标签模型（项目级别，一次性）

```python
from yweb.orm import BaseModel, AbstractTag, AbstractTagRelation

class Tag(BaseModel, AbstractTag):
    __tablename__ = "tag"

class TagRelation(BaseModel, AbstractTagRelation):
    __tablename__ = "tag_relation"
```

### 2. 业务模型使用 TaggableMixin

```python
from yweb.orm import BaseModel, TaggableMixin

class Article(BaseModel, TaggableMixin):
    __tablename__ = "article"
    __tag_model__ = Tag
    __tag_relation_model__ = TagRelation
    
    title = mapped_column(String(200))
```

### 3. 使用标签功能

```python
article = Article(title="Python 入门")
article.save(commit=True)

# 添加标签
article.add_tag("Python")
article.add_tags(["Web", "Tutorial"])

# 查询标签
article.get_tags()  # ["Python", "Web", "Tutorial"]
article.has_tag("Python")  # True

# 按标签查询
Article.find_by_tag("Python")
```

## 数据模型

### Tag 模型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | 标签名称（继承自 BaseModel） |
| `slug` | str | URL 友好标识（如 "machine-learning"） |
| `group` | str | 标签分组（如 "技术"、"颜色"） |
| `parent_id` | int | 父标签ID（支持层级） |
| `color` | str | 显示颜色（如 "#FF5733"） |
| `description` | str | 标签描述 |
| `use_count` | int | 使用次数（自动维护） |
| `is_system` | bool | 是否系统标签（不可删除） |

### TagRelation 模型字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `tag_id` | int | 标签ID |
| `target_type` | str | 目标模型类型（如 "Article"） |
| `target_id` | int | 目标记录ID |

## API 参考

### TaggableMixin 实例方法

#### 添加标签

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `add_tag(name, **kwargs)` | str | Tag | 添加单个标签 |
| `add_tags(names, **kwargs)` | List[str] | List[Tag] | 批量添加标签 |

```python
# 简单添加
article.add_tag("Python")

# 带元数据添加
article.add_tag("Django", group="框架", color="#092E20")

# 批量添加
article.add_tags(["Web", "API", "Backend"])
```

#### 移除标签

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `remove_tag(name)` | str | bool | 移除单个标签 |
| `remove_tags(names)` | List[str] | int | 批量移除标签 |
| `remove_all_tags()` | - | int | 移除所有标签 |

#### 查询标签

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `get_tags()` | - | List[str] | 获取标签名列表 |
| `get_tag_objects()` | - | List[Tag] | 获取标签对象列表 |
| `get_tags_by_group(group)` | str | List[Tag] | 按分组获取标签 |
| `get_tag_count()` | - | int | 获取标签数量 |

#### 检查标签

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `has_tag(name)` | str | bool | 是否有指定标签 |
| `has_any_tags(names)` | List[str] | bool | 是否有任一标签 |
| `has_all_tags(names)` | List[str] | bool | 是否有全部标签 |

#### 设置标签

| 方法 | 参数 | 说明 |
|------|------|------|
| `set_tags(names, **kwargs)` | List[str] | 设置标签（覆盖现有） |

```python
# 覆盖所有标签
article.set_tags(["Python", "FastAPI"])
```

### TaggableMixin 类方法

| 方法 | 参数 | 返回值 | 说明 |
|------|------|--------|------|
| `find_by_tag(name)` | str | List | 按单个标签查询 |
| `find_by_any_tags(names)` | List[str] | List | 有任一标签的记录（OR） |
| `find_by_all_tags(names)` | List[str] | List | 有全部标签的记录（AND） |
| `count_by_tag(name)` | str | int | 按标签统计数量 |
| `get_all_used_tags(limit)` | int | List[Tag] | 获取使用的所有标签 |

### Tag 模型方法

| 方法 | 说明 |
|------|------|
| `Tag.get_or_create(name, **kwargs)` | 获取或创建标签 |
| `Tag.get_by_group(group)` | 获取指定分组的标签 |
| `Tag.get_popular(limit, group)` | 获取热门标签 |
| `Tag.get_groups()` | 获取所有分组 |
| `Tag.search(keyword)` | 搜索标签 |

## 使用场景

### 场景 1：基本标签

```python
class Article(BaseModel, TaggableMixin):
    __tablename__ = "article"
    __tag_model__ = Tag
    __tag_relation_model__ = TagRelation

article = Article(title="Python 入门")
article.save(commit=True)

article.add_tags(["Python", "Beginner", "Tutorial"])
print(article.get_tags())  # ["Python", "Beginner", "Tutorial"]
```

### 场景 2：标签分组

```python
# 添加带分组的标签
article.add_tag("Python", group="语言", color="#3776AB")
article.add_tag("Django", group="框架", color="#092E20")
article.add_tag("Beginner", group="难度", color="#28A745")

# 按分组获取
lang_tags = article.get_tags_by_group("语言")
```

### 场景 3：标签层级

```python
# 创建层级标签
tech = Tag.get_or_create("技术")
lang = Tag.get_or_create("编程语言")
lang.parent_id = tech.id
lang.save()

python = Tag.get_or_create("Python")
python.parent_id = lang.id
python.save()

# 查询层级
print(python.get_parent().name)  # "编程语言"
print(python.get_ancestors())     # [编程语言, 技术]
print(tech.get_children())        # [编程语言]
```

### 场景 4：按标签查询

```python
# 按单个标签查询
articles = Article.find_by_tag("Python")

# 按任一标签查询（OR）
articles = Article.find_by_any_tags(["Python", "Java"])

# 按全部标签查询（AND）
articles = Article.find_by_all_tags(["Python", "Web"])

# 统计
count = Article.count_by_tag("Python")
```

### 场景 5：多模型共享标签

```python
class Article(BaseModel, TaggableMixin):
    __tablename__ = "article"
    __tag_model__ = Tag
    __tag_relation_model__ = TagRelation

class Product(BaseModel, TaggableMixin):
    __tablename__ = "product"
    __tag_model__ = Tag  # 共享同一个标签模型
    __tag_relation_model__ = TagRelation

# 两个模型共享标签
article.add_tag("Python")
product.add_tag("Python")

# 标签使用次数自动累加
python_tag = Tag.query.filter_by(name="Python").first()
print(python_tag.use_count)  # 2
```

### 场景 6：热门标签

```python
# 获取热门标签（全局）
popular = Tag.get_popular(limit=10)

# 获取某分组的热门标签
popular_lang = Tag.get_popular(limit=5, group="语言")

# 获取某模型使用的标签
article_tags = Article.get_all_used_tags(limit=20)
```

## 最佳实践

1. **标签模型复用**：整个项目定义一套 Tag 和 TagRelation 模型

2. **使用分组**：合理使用 `group` 字段组织标签
   ```python
   article.add_tag("Python", group="技术")
   article.add_tag("Easy", group="难度")
   ```

3. **使用 slug**：前端显示时使用 `slug` 作为 URL 参数
   ```
   /articles?tag=machine-learning
   ```

4. **利用 use_count**：直接按使用次数排序，无需 JOIN
   ```python
   Tag.query.order_by(Tag.use_count.desc()).limit(10).all()
   ```

5. **系统标签**：重要标签设置 `is_system=True` 防止误删

## 配置选项

```python
class Article(BaseModel, TaggableMixin):
    __tablename__ = "article"
    
    # 必须配置
    __tag_model__ = Tag                # 标签模型类
    __tag_relation_model__ = TagRelation  # 关联模型类
```

## 注意事项

1. **先保存记录**：添加标签前必须先保存记录（需要 ID）
   ```python
   article = Article(title="Test")
   article.save(commit=True)  # 先保存
   article.add_tag("Python")  # 再添加标签
   ```

2. **use_count 自动维护**：添加/移除标签时自动更新

3. **标签去重**：同一标签不会重复关联同一记录

4. **删除记录时**：需要手动清理标签关联（或使用级联删除）
