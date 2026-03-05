"""标签系统模块

提供通用的标签功能支持。

导出:
    - AbstractTag: 标签抽象模型
    - AbstractTagRelation: 标签关联抽象模型
    - TaggableMixin: 标签管理 Mixin

使用示例:
    from yweb.orm import BaseModel
    from yweb.orm.taggable import AbstractTag, AbstractTagRelation, TaggableMixin
    
    # 1. 定义标签模型（项目级别，一次性）
    class Tag(BaseModel, AbstractTag):
        __tablename__ = "tag"
    
    class TagRelation(BaseModel, AbstractTagRelation):
        __tablename__ = "tag_relation"
    
    # 2. 业务模型使用 TaggableMixin
    class Article(BaseModel, TaggableMixin):
        __tablename__ = "article"
        __tag_model__ = Tag
        __tag_relation_model__ = TagRelation
        
        title = mapped_column(String(200))
    
    # 3. 使用标签功能
    article = Article(title="Python 入门")
    article.save(commit=True)
    
    # 添加标签
    article.add_tag("Python")
    article.add_tags(["Web", "Tutorial"])
    
    # 查询标签
    print(article.get_tags())  # ["Python", "Web", "Tutorial"]
    print(article.has_tag("Python"))  # True
    
    # 移除标签
    article.remove_tag("Tutorial")
    
    # 设置标签（覆盖）
    article.set_tags(["Python", "FastAPI"])
    
    # 按标签查询记录
    articles = Article.find_by_tag("Python")
    articles = Article.find_by_any_tags(["Python", "Java"])
    articles = Article.find_by_all_tags(["Python", "Web"])
    
    # 标签操作
    Tag.get_popular(limit=10)  # 热门标签
    Tag.get_by_group("技术")   # 按分组获取
    Tag.search("Py")          # 搜索标签
"""

from .tag_model import AbstractTag, AbstractTagRelation
from .taggable_mixin import TaggableMixin

__all__ = [
    "AbstractTag",
    "AbstractTagRelation",
    "TaggableMixin",
]
