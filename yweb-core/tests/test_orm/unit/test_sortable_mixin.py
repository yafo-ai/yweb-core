"""排序管理 SortableMixin 测试

测试 SortableMixin 的核心功能：
1. 基本排序操作（move_up, move_down, move_to_top, move_to_bottom）
2. 分组排序
3. 与 TreeFieldsMixin 集成
"""

import pytest
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    Base,
    SortFieldMixin,
    SortableMixin,
)
from yweb.orm.tree import TreeFieldsMixin, TreeMixin


# ==================== 测试模型定义 ====================

class SortBanner(BaseModel, SortFieldMixin, SortableMixin):
    """轮播图 - 简单排序"""
    __tablename__ = "test_sortable_banner"
    __table_args__ = {'extend_existing': True}
    
    title: Mapped[str] = mapped_column(String(100))


class SortProduct(BaseModel, SortFieldMixin, SortableMixin):
    """产品 - 按分类分组排序"""
    __tablename__ = "test_sortable_product"
    __table_args__ = {'extend_existing': True}
    __sort_group_by__ = "category_id"
    
    category_id: Mapped[int] = mapped_column(Integer)
    name: Mapped[str] = mapped_column(String(100))


class SortTreeCategory(BaseModel, TreeFieldsMixin, TreeMixin, SortableMixin):
    """分类 - 树形结构 + 排序"""
    __tablename__ = "test_sortable_tree_category"
    __table_args__ = {'extend_existing': True}
    __sort_group_by__ = "parent_id"
    
    parent_id: Mapped[int] = mapped_column(
        Integer, 
        ForeignKey("test_sortable_tree_category.id"), 
        nullable=True, 
        default=None
    )
    name: Mapped[str] = mapped_column(String(100))


# ==================== 测试类 ====================

class TestSimpleSorting:
    """简单排序测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_sort_field_mixin_adds_sort_order(self):
        """测试 SortFieldMixin 添加 sort_order 字段"""
        assert hasattr(SortBanner, 'sort_order')
    
    def test_move_up(self):
        """测试上移"""
        # 创建测试数据
        for i, title in enumerate(["Banner 1", "Banner 2", "Banner 3"], 1):
            b = SortBanner(title=title, sort_order=i)
            b.save(commit=True)
        
        # 上移 Banner 3
        banner3 = SortBanner.query.filter_by(title="Banner 3").first()
        banner3.move_up()
        self.session_scope().commit()
        
        # 验证
        sorted_banners = SortBanner.get_sorted()
        titles = [b.title for b in sorted_banners]
        assert titles == ["Banner 1", "Banner 3", "Banner 2"]
    
    def test_move_down(self):
        """测试下移"""
        for i, title in enumerate(["Banner A", "Banner B", "Banner C"], 1):
            b = SortBanner(title=title, sort_order=i)
            b.save(commit=True)
        
        banner_a = SortBanner.query.filter_by(title="Banner A").first()
        banner_a.move_down()
        self.session_scope().commit()
        
        sorted_banners = SortBanner.get_sorted()
        titles = [b.title for b in sorted_banners]
        assert titles == ["Banner B", "Banner A", "Banner C"]
    
    def test_move_to_top(self):
        """测试置顶"""
        for i, title in enumerate(["Item 1", "Item 2", "Item 3"], 1):
            b = SortBanner(title=title, sort_order=i)
            b.save(commit=True)
        
        item3 = SortBanner.query.filter_by(title="Item 3").first()
        item3.move_to_top()
        self.session_scope().commit()
        
        sorted_banners = SortBanner.get_sorted()
        assert sorted_banners[0].title == "Item 3"
    
    def test_move_to_bottom(self):
        """测试置底"""
        for i, title in enumerate(["X1", "X2", "X3"], 1):
            b = SortBanner(title=title, sort_order=i)
            b.save(commit=True)
        
        x1 = SortBanner.query.filter_by(title="X1").first()
        x1.move_to_bottom()
        self.session_scope().commit()
        
        sorted_banners = SortBanner.get_sorted()
        assert sorted_banners[-1].title == "X1"
    
    def test_swap_with(self):
        """测试交换位置"""
        for i, title in enumerate(["S1", "S2", "S3"], 1):
            b = SortBanner(title=title, sort_order=i)
            b.save(commit=True)
        
        s1 = SortBanner.query.filter_by(title="S1").first()
        s3 = SortBanner.query.filter_by(title="S3").first()
        s1.swap_with(s3)
        self.session_scope().commit()
        
        sorted_banners = SortBanner.get_sorted()
        titles = [b.title for b in sorted_banners]
        assert titles == ["S3", "S2", "S1"]
    
    def test_get_max_min_sort_order(self):
        """测试获取最大/最小排序号"""
        for i, title in enumerate(["M1", "M2", "M3"], 1):
            b = SortBanner(title=title, sort_order=i * 10)
            b.save(commit=True)
        
        assert SortBanner.get_max_sort_order() == 30
        assert SortBanner.get_min_sort_order() == 10


class TestGroupedSorting:
    """分组排序测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_grouped_sorting_isolation(self):
        """测试分组排序隔离"""
        # 分类 1 的产品
        for i, name in enumerate(["A1", "A2", "A3"], 1):
            p = SortProduct(category_id=1, name=name, sort_order=i)
            p.save(commit=True)
        
        # 分类 2 的产品
        for i, name in enumerate(["B1", "B2"], 1):
            p = SortProduct(category_id=2, name=name, sort_order=i)
            p.save(commit=True)
        
        # 在分类 1 中移动 A3 到顶部
        a3 = SortProduct.query.filter_by(name="A3").first()
        a3.move_to_top()
        self.session_scope().commit()
        
        # 验证分类 1 的顺序
        cat1_products = SortProduct.get_sorted({"category_id": 1})
        assert [p.name for p in cat1_products] == ["A3", "A1", "A2"]
        
        # 验证分类 2 不受影响
        cat2_products = SortProduct.get_sorted({"category_id": 2})
        assert [p.name for p in cat2_products] == ["B1", "B2"]
    
    def test_get_max_sort_order_by_group(self):
        """测试按分组获取最大排序号"""
        for i in range(1, 4):
            p = SortProduct(category_id=1, name=f"P{i}", sort_order=i)
            p.save(commit=True)
        
        for i in range(1, 3):
            p = SortProduct(category_id=2, name=f"Q{i}", sort_order=i * 10)
            p.save(commit=True)
        
        assert SortProduct.get_max_sort_order({"category_id": 1}) == 3
        assert SortProduct.get_max_sort_order({"category_id": 2}) == 20


class TestTreeWithSorting:
    """树形结构与排序集成测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_tree_fields_mixin_inherits_sort_field(self):
        """测试 TreeFieldsMixin 继承 SortFieldMixin"""
        assert hasattr(SortTreeCategory, 'sort_order')
        assert hasattr(SortTreeCategory, 'path')
        assert hasattr(SortTreeCategory, 'level')
    
    def test_tree_sibling_sorting(self):
        """测试同级节点排序"""
        # 创建根节点
        root = SortTreeCategory(name="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        # 创建子节点
        for i, name in enumerate(["Child A", "Child B", "Child C"], 1):
            child = SortTreeCategory(name=name, parent_id=root.id, sort_order=i)
            child.save(commit=True)
            child.update_path_and_level()
            child.save(commit=True)
        
        # 移动 Child C 到顶部
        child_c = SortTreeCategory.query.filter_by(name="Child C").first()
        child_c.move_to_top()
        self.session_scope().commit()
        
        # 验证同级顺序
        children = SortTreeCategory.get_sorted({"parent_id": root.id})
        names = [c.name for c in children]
        assert names == ["Child C", "Child A", "Child B"]
