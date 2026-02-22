"""标签系统 TaggableMixin 测试

测试 TaggableMixin 的核心功能：
1. 基本标签操作（添加、移除、查询）
2. 标签元数据（分组、颜色等）
3. 按标签查询记录
4. 多模型共享标签
"""

import pytest
from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    Base,
    AbstractTag,
    AbstractTagRelation,
    TaggableMixin,
)


# ==================== 测试模型定义 ====================

class TagModel(BaseModel, AbstractTag):
    """标签模型"""
    __tablename__ = "test_tag"
    __table_args__ = {'extend_existing': True}


class TagRelationModel(BaseModel, AbstractTagRelation):
    """标签关联模型"""
    __tablename__ = "test_tag_relation"
    __table_args__ = {'extend_existing': True}


class TagArticle(BaseModel, TaggableMixin):
    """文章模型"""
    __tablename__ = "test_taggable_article"
    __table_args__ = {'extend_existing': True}
    __tag_model__ = TagModel
    __tag_relation_model__ = TagRelationModel
    
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text, nullable=True)


class TagProduct(BaseModel, TaggableMixin):
    """产品模型 - 演示多模型共享标签"""
    __tablename__ = "test_taggable_product"
    __table_args__ = {'extend_existing': True}
    __tag_model__ = TagModel
    __tag_relation_model__ = TagRelationModel
    
    name: Mapped[str] = mapped_column(String(200))
    price: Mapped[int] = mapped_column(Integer, default=0)


# ==================== 测试类 ====================

class TestBasicTagging:
    """基本标签操作测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_add_single_tag(self):
        """测试添加单个标签"""
        article = TagArticle(title="Test Article")
        article.save(commit=True)
        
        article.add_tag("Python")
        tags = article.get_tags()
        
        assert "Python" in tags
    
    def test_add_multiple_tags(self):
        """测试批量添加标签"""
        article = TagArticle(title="Multi Tag Article")
        article.save(commit=True)
        
        article.add_tags(["Python", "Web", "Tutorial"])
        tags = article.get_tags()
        
        assert len(tags) == 3
        assert "Python" in tags
        assert "Web" in tags
        assert "Tutorial" in tags
    
    def test_remove_tag(self):
        """测试移除标签"""
        article = TagArticle(title="Remove Tag Article")
        article.save(commit=True)
        
        article.add_tags(["A", "B", "C"])
        article.remove_tag("B")
        tags = article.get_tags()
        
        assert "B" not in tags
        assert "A" in tags
        assert "C" in tags
    
    def test_has_tag(self):
        """测试检查标签"""
        article = TagArticle(title="Check Tag Article")
        article.save(commit=True)
        
        article.add_tag("Python")
        
        assert article.has_tag("Python") == True
        assert article.has_tag("Java") == False
    
    def test_has_any_tags(self):
        """测试检查任一标签"""
        article = TagArticle(title="Any Tags Article")
        article.save(commit=True)
        
        article.add_tags(["Python", "Django"])
        
        assert article.has_any_tags(["Python", "Java"]) == True
        assert article.has_any_tags(["Java", "Rust"]) == False
    
    def test_has_all_tags(self):
        """测试检查全部标签"""
        article = TagArticle(title="All Tags Article")
        article.save(commit=True)
        
        article.add_tags(["Python", "Django", "Web"])
        
        assert article.has_all_tags(["Python", "Django"]) == True
        assert article.has_all_tags(["Python", "Java"]) == False
    
    def test_get_tag_count(self):
        """测试获取标签数量"""
        article = TagArticle(title="Count Tags Article")
        article.save(commit=True)
        
        article.add_tags(["A", "B", "C"])
        
        assert article.get_tag_count() == 3
    
    def test_set_tags_replaces_all(self):
        """测试设置标签（覆盖）"""
        article = TagArticle(title="Set Tags Article")
        article.save(commit=True)
        
        article.add_tags(["Old1", "Old2"])
        article.set_tags(["New1", "New2", "New3"])
        tags = article.get_tags()
        
        assert len(tags) == 3
        assert "Old1" not in tags
        assert "New1" in tags


class TestTagMetadata:
    """标签元数据测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_tag_with_group(self):
        """测试带分组的标签"""
        article = TagArticle(title="Grouped Tag Article")
        article.save(commit=True)
        
        article.add_tag("Python", group="Language", color="#3776AB")
        
        tag_objects = article.get_tag_objects()
        python_tag = next((t for t in tag_objects if t.name == "Python"), None)
        
        assert python_tag is not None
        assert python_tag.group == "Language"
        assert python_tag.color == "#3776AB"
    
    def test_get_tags_by_group(self):
        """测试按分组获取标签"""
        article = TagArticle(title="Group Filter Article")
        article.save(commit=True)
        
        article.add_tag("Python", group="Language")
        article.add_tag("Django", group="Framework")
        article.add_tag("JavaScript", group="Language")
        
        lang_tags = article.get_tags_by_group("Language")
        lang_names = [t.name for t in lang_tags]
        
        assert "Python" in lang_names
        assert "JavaScript" in lang_names
        assert "Django" not in lang_names


class TestFindByTags:
    """按标签查询测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_find_by_single_tag(self):
        """测试按单个标签查询"""
        # 创建文章
        for title, tags in [
            ("Python Basics", ["Python"]),
            ("Django Tutorial", ["Python", "Django"]),
            ("JavaScript Intro", ["JavaScript"]),
        ]:
            article = TagArticle(title=title)
            article.save(commit=True)
            article.add_tags(tags)
        
        results = TagArticle.find_by_tag("Python")
        titles = [a.title for a in results]
        
        assert "Python Basics" in titles
        assert "Django Tutorial" in titles
        assert "JavaScript Intro" not in titles
    
    def test_find_by_any_tags(self):
        """测试按任一标签查询（OR）"""
        for title, tags in [
            ("Article A", ["Python"]),
            ("Article B", ["JavaScript"]),
            ("Article C", ["Rust"]),
        ]:
            article = TagArticle(title=title)
            article.save(commit=True)
            article.add_tags(tags)
        
        results = TagArticle.find_by_any_tags(["Python", "JavaScript"])
        titles = [a.title for a in results]
        
        assert "Article A" in titles
        assert "Article B" in titles
        assert "Article C" not in titles
    
    def test_find_by_all_tags(self):
        """测试按全部标签查询（AND）"""
        for title, tags in [
            ("Full Stack", ["Python", "JavaScript"]),
            ("Backend Only", ["Python"]),
            ("Frontend Only", ["JavaScript"]),
        ]:
            article = TagArticle(title=title)
            article.save(commit=True)
            article.add_tags(tags)
        
        results = TagArticle.find_by_all_tags(["Python", "JavaScript"])
        titles = [a.title for a in results]
        
        assert "Full Stack" in titles
        assert "Backend Only" not in titles
        assert "Frontend Only" not in titles
    
    def test_count_by_tag(self):
        """测试按标签统计"""
        for i in range(3):
            article = TagArticle(title=f"Python Article {i}")
            article.save(commit=True)
            article.add_tag("Python")
        
        for i in range(2):
            article = TagArticle(title=f"Java Article {i}")
            article.save(commit=True)
            article.add_tag("Java")
        
        assert TagArticle.count_by_tag("Python") == 3
        assert TagArticle.count_by_tag("Java") == 2
        assert TagArticle.count_by_tag("Rust") == 0


class TestSharedTags:
    """多模型共享标签测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_shared_tag_use_count(self):
        """测试共享标签使用计数"""
        # 文章使用 Python 标签
        article = TagArticle(title="Python Article")
        article.save(commit=True)
        article.add_tag("Python")
        
        # 产品也使用 Python 标签
        product = TagProduct(name="Python Book", price=9900)
        product.save(commit=True)
        product.add_tag("Python")
        
        # 检查标签使用次数
        python_tag = TagModel.query.filter_by(name="Python").first()
        assert python_tag.use_count == 2
    
    def test_different_models_find_by_tag(self):
        """测试不同模型按标签查询"""
        article = TagArticle(title="Python Tutorial")
        article.save(commit=True)
        article.add_tag("Python")
        
        product = TagProduct(name="Python Course", price=19900)
        product.save(commit=True)
        product.add_tag("Python")
        
        # 各自查询
        articles = TagArticle.find_by_tag("Python")
        products = TagProduct.find_by_tag("Python")
        
        assert len(list(articles)) == 1
        assert len(list(products)) == 1


class TestTagManagement:
    """标签管理功能测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_get_or_create_tag(self):
        """测试获取或创建标签"""
        # 第一次创建
        tag1 = TagModel.get_or_create("NewTag", group="Test")
        # 第二次获取
        tag2 = TagModel.get_or_create("NewTag")
        
        assert tag1.id == tag2.id
    
    def test_search_tags(self):
        """测试搜索标签"""
        for name in ["Python", "PyTorch", "PySpark", "Java"]:
            TagModel.get_or_create(name)
        
        results = TagModel.search("Py", limit=10)
        names = [t.name for t in results]
        
        assert "Python" in names
        assert "PyTorch" in names
        assert "PySpark" in names
        assert "Java" not in names
    
    def test_get_popular_tags(self):
        """测试获取热门标签"""
        # 创建文章并添加标签（不同数量）
        for _ in range(5):
            article = TagArticle(title="Popular")
            article.save(commit=True)
            article.add_tag("Popular")
        
        for _ in range(2):
            article = TagArticle(title="Normal")
            article.save(commit=True)
            article.add_tag("Normal")
        
        popular = TagModel.get_popular(limit=2)
        names = [t.name for t in popular]
        
        # 热门标签应该排在前面
        assert names[0] == "Popular"
