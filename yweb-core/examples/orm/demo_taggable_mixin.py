"""标签系统 TaggableMixin 使用示例

演示 TaggableMixin 的各种使用场景：
1. 基本标签操作（添加、移除、查询）
2. 标签分组和层级
3. 按标签查询记录
4. 多模型共享标签
"""

import sys
from pathlib import Path

# 添加 yweb-core 到 path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from yweb.orm import (
    BaseModel,
    Base,
    init_database,
    AbstractTag,
    AbstractTagRelation,
    TaggableMixin,
)


# ==================== 定义标签模型（项目级别，一次性）====================

class Tag(BaseModel, AbstractTag):
    """标签模型"""
    __tablename__ = "demo_tag"


class TagRelation(BaseModel, AbstractTagRelation):
    """标签关联模型"""
    __tablename__ = "demo_tag_relation"


# ==================== 定义业务模型 ====================

class Article(BaseModel, TaggableMixin):
    """文章模型"""
    __tablename__ = "demo_article"
    __tag_model__ = Tag
    __tag_relation_model__ = TagRelation
    
    title: Mapped[str] = mapped_column(String(200), comment="标题")
    content: Mapped[str] = mapped_column(Text, nullable=True, comment="内容")


class Product(BaseModel, TaggableMixin):
    """产品模型 - 演示多模型共享标签"""
    __tablename__ = "demo_product"
    __tag_model__ = Tag
    __tag_relation_model__ = TagRelation
    
    product_name: Mapped[str] = mapped_column(String(200), comment="产品名称")
    price: Mapped[int] = mapped_column(Integer, default=0, comment="价格（分）")


# ==================== 演示函数 ====================

def demo_basic_tagging():
    """演示基本标签操作"""
    print("\n" + "=" * 60)
    print("Demo 1: Basic Tagging Operations")
    print("=" * 60)
    
    # 创建文章
    article = Article(title="Python Web Development Guide")
    article.save(commit=True)
    print(f"\n[Created] Article: {article.title} (id={article.id})")
    
    # 添加单个标签
    print("\n[Add single tag]")
    article.add_tag("Python")
    print(f"  Tags: {article.get_tags()}")
    
    # 批量添加标签
    print("\n[Add multiple tags]")
    article.add_tags(["Web", "Tutorial", "Backend"])
    print(f"  Tags: {article.get_tags()}")
    
    # 检查标签
    print("\n[Check tags]")
    print(f"  has_tag('Python'): {article.has_tag('Python')}")
    print(f"  has_tag('Java'): {article.has_tag('Java')}")
    print(f"  has_any_tags(['Python', 'Java']): {article.has_any_tags(['Python', 'Java'])}")
    print(f"  has_all_tags(['Python', 'Web']): {article.has_all_tags(['Python', 'Web'])}")
    print(f"  get_tag_count(): {article.get_tag_count()}")
    
    # 移除标签
    print("\n[Remove tag]")
    article.remove_tag("Tutorial")
    print(f"  Tags after remove: {article.get_tags()}")
    
    # 设置标签（覆盖）
    print("\n[Set tags (replace all)]")
    article.set_tags(["Python", "FastAPI", "API"])
    print(f"  Tags after set: {article.get_tags()}")
    
    return article


def demo_tag_with_metadata():
    """演示带元数据的标签"""
    print("\n" + "=" * 60)
    print("Demo 2: Tags with Metadata (group, color, description)")
    print("=" * 60)
    
    article = Article(title="Django REST Framework Tutorial")
    article.save(commit=True)
    print(f"\n[Created] Article: {article.title}")
    
    # 添加带分组的标签
    print("\n[Add tags with groups]")
    article.add_tag("Django", group="框架", color="#092E20", description="Python Web 框架")
    article.add_tag("REST", group="架构", color="#FF5733")
    article.add_tag("Python", group="语言", color="#3776AB")
    article.add_tag("Beginner", group="难度", color="#28A745")
    
    # 获取标签对象
    print("\n[Tag objects with metadata]")
    for tag in article.get_tag_objects():
        print(f"  {tag.name}: group={tag.group}, color={tag.color}, use_count={tag.use_count}")
    
    # 按分组获取标签
    print("\n[Tags by group '框架']")
    framework_tags = article.get_tags_by_group("框架")
    for tag in framework_tags:
        print(f"  {tag.name}")
    
    return article


def demo_tag_hierarchy():
    """演示标签层级"""
    print("\n" + "=" * 60)
    print("Demo 3: Tag Hierarchy")
    print("=" * 60)
    
    # 创建层级标签
    print("\n[Create hierarchical tags]")
    
    # 根标签
    tech = Tag.get_or_create("技术", group="根分类")
    
    # 子标签
    lang = Tag.get_or_create("编程语言", group="技术")
    lang.parent_id = tech.id
    lang.save()
    
    framework = Tag.get_or_create("框架", group="技术")
    framework.parent_id = tech.id
    framework.save()
    
    # 孙子标签
    python = Tag.get_or_create("Python", group="编程语言")
    python.parent_id = lang.id
    python.save()
    
    django = Tag.get_or_create("Django-Tag", group="框架")
    django.parent_id = framework.id
    django.save()
    
    print("  Tag hierarchy created:")
    print("    技术")
    print("    ├── 编程语言")
    print("    │   └── Python")
    print("    └── 框架")
    print("        └── Django-Tag")
    
    # 查询层级
    print("\n[Query hierarchy]")
    print(f"  Python's parent: {python.get_parent().name if python.get_parent() else 'None'}")
    print(f"  Python's ancestors: {[t.name for t in python.get_ancestors()]}")
    print(f"  tech's children: {[t.name for t in tech.get_children()]}")


def demo_find_by_tags():
    """演示按标签查询"""
    print("\n" + "=" * 60)
    print("Demo 4: Find Records by Tags")
    print("=" * 60)
    
    # 创建多篇文章
    articles_data = [
        ("Python Basics", ["Python", "Beginner"]),
        ("Advanced Python", ["Python", "Advanced"]),
        ("Django Tutorial", ["Python", "Django", "Web"]),
        ("FastAPI Guide", ["Python", "FastAPI", "Web", "API"]),
        ("JavaScript Intro", ["JavaScript", "Beginner", "Web"]),
    ]
    
    print("\n[Create articles with tags]")
    for title, tags in articles_data:
        article = Article(title=title)
        article.save(commit=True)
        article.add_tags(tags)
        print(f"  {title}: {tags}")
    
    # 按单个标签查询
    print("\n[Find by single tag 'Python']")
    results = Article.find_by_tag("Python")
    for a in results:
        print(f"  - {a.title}")
    
    # 按任一标签查询（OR）
    print("\n[Find by any tags ['Django', 'FastAPI']]")
    results = Article.find_by_any_tags(["Django", "FastAPI"])
    for a in results:
        print(f"  - {a.title}: {a.get_tags()}")
    
    # 按全部标签查询（AND）
    print("\n[Find by all tags ['Python', 'Web']]")
    results = Article.find_by_all_tags(["Python", "Web"])
    for a in results:
        print(f"  - {a.title}: {a.get_tags()}")
    
    # 统计
    print("\n[Count by tag]")
    print(f"  Articles with 'Python': {Article.count_by_tag('Python')}")
    print(f"  Articles with 'Web': {Article.count_by_tag('Web')}")
    print(f"  Articles with 'Java': {Article.count_by_tag('Java')}")


def demo_shared_tags():
    """演示多模型共享标签"""
    print("\n" + "=" * 60)
    print("Demo 5: Shared Tags Across Models")
    print("=" * 60)
    
    # 创建产品
    products_data = [
        ("Python Book", 9900, ["Python", "Book", "Learning"]),
        ("Django Course", 19900, ["Python", "Django", "Course"]),
        ("JavaScript Course", 14900, ["JavaScript", "Course"]),
    ]
    
    print("\n[Create products with tags]")
    for name, price, tags in products_data:
        product = Product(product_name=name, price=price)
        product.save(commit=True)
        product.add_tags(tags)
        print(f"  {name}: {tags}")
    
    # 查询标签使用情况
    print("\n[Tag usage across models]")
    python_tag = Tag.query.filter_by(name="Python").first()
    if python_tag:
        print(f"  'Python' tag use_count: {python_tag.use_count}")
        print(f"  Used in Articles: {Article.count_by_tag('Python')}")
        print(f"  Used in Products: {Product.count_by_tag('Python')}")
    
    # 按标签查询产品
    print("\n[Find products by tag 'Course']")
    results = Product.find_by_tag("Course")
    for p in results:
        print(f"  - {p.product_name}: RMB {p.price/100:.2f}")


def demo_tag_management():
    """演示标签管理功能"""
    print("\n" + "=" * 60)
    print("Demo 6: Tag Management")
    print("=" * 60)
    
    # 获取热门标签
    print("\n[Popular tags]")
    popular = Tag.get_popular(limit=5)
    for tag in popular:
        print(f"  {tag.name}: {tag.use_count} uses")
    
    # 获取所有分组
    print("\n[All tag groups]")
    groups = Tag.get_groups()
    print(f"  Groups: {groups}")
    
    # 搜索标签
    print("\n[Search tags 'Py']")
    results = Tag.search("Py", limit=5)
    for tag in results:
        print(f"  {tag.name}")
    
    # 按分组获取标签
    print("\n[Tags in group '语言']")
    lang_tags = Tag.get_by_group("语言")
    for tag in lang_tags:
        print(f"  {tag.name}")
    
    # 获取模型使用的所有标签
    print("\n[All tags used by Article]")
    article_tags = Article.get_all_used_tags(limit=10)
    for tag in article_tags:
        print(f"  {tag.name}: {tag.use_count}")


def main():
    """主函数"""
    print("=" * 60)
    print("TaggableMixin Demo")
    print("=" * 60)
    
    # 初始化数据库（内存数据库）
    # init_database 返回 engine 和 session_scope
    engine, session_scope = init_database("sqlite:///:memory:", echo=False)
    
    # 创建所有表
    Base.metadata.create_all(engine)
    
    try:
        # 运行演示
        demo_basic_tagging()
        demo_tag_with_metadata()
        demo_tag_hierarchy()
        demo_find_by_tags()
        demo_shared_tags()
        demo_tag_management()
        
        print("\n" + "=" * 60)
        print("All demos completed successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n[Error] {e}")
        import traceback
        traceback.print_exc()
        session_scope.rollback()
    finally:
        session_scope.remove()


if __name__ == "__main__":
    main()
