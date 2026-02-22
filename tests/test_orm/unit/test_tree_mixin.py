"""树形结构 TreeMixin 测试

测试 TreeMixin 的核心功能：
1. 基本树形操作
2. 树形查询方法
3. 节点移动
4. 工具函数
"""

import pytest
from sqlalchemy import Integer, String, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker, scoped_session

from yweb.orm import CoreModel, BaseModel, Base
from yweb.orm.tree import (
    TreeMixin,
    TreeFieldsMixin,
    build_tree_list,
    flatten_tree,
    find_node_in_tree,
    calculate_tree_depth,
    filter_tree,
)


# ==================== 测试模型定义 ====================

class TreeMenu(BaseModel, TreeMixin):
    """菜单模型 - 自定义字段方式"""
    __tablename__ = "test_tree_menu"
    __table_args__ = {'extend_existing': True}
    
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_tree_menu.id"),
        nullable=True
    )
    path: Mapped[str] = mapped_column(String(500), nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=1)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    title: Mapped[str] = mapped_column(String(100))


class TreeCategory(BaseModel, TreeFieldsMixin, TreeMixin):
    """分类模型 - 使用 TreeFieldsMixin"""
    __tablename__ = "test_tree_category"
    __table_args__ = {'extend_existing': True}
    
    parent_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("test_tree_category.id"),
        nullable=True
    )
    name: Mapped[str] = mapped_column(String(100))


# ==================== 测试类 ====================

class TestBasicTreeOperations:
    """基本树形操作测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_create_root_node(self):
        """测试创建根节点"""
        root = TreeMenu(title="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        assert root.level == 1
        assert root.parent_id is None
        assert root.is_root() == True
    
    def test_create_child_node(self):
        """测试创建子节点"""
        root = TreeMenu(title="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        child = TreeMenu(title="Child", parent_id=root.id, sort_order=1)
        child.save(commit=True)
        child.update_path_and_level()
        child.save(commit=True)
        
        assert child.level == 2
        assert child.parent_id == root.id
        assert child.is_root() == False
    
    def test_path_contains_ancestor_ids(self):
        """测试路径包含祖先ID"""
        root = TreeMenu(title="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        child = TreeMenu(title="Child", parent_id=root.id, sort_order=1)
        child.save(commit=True)
        child.update_path_and_level()
        child.save(commit=True)
        
        grandchild = TreeMenu(title="Grandchild", parent_id=child.id, sort_order=1)
        grandchild.save(commit=True)
        grandchild.update_path_and_level()
        grandchild.save(commit=True)
        
        # 路径应该包含所有祖先
        assert str(root.id) in grandchild.path
        assert str(child.id) in grandchild.path


class TestTreeQueryMethods:
    """树形查询方法测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def _create_tree(self):
        """创建测试树结构"""
        # 根节点
        root = TreeMenu(title="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        # 子节点
        child1 = TreeMenu(title="Child 1", parent_id=root.id, sort_order=1)
        child1.save(commit=True)
        child1.update_path_and_level()
        child1.save(commit=True)
        
        child2 = TreeMenu(title="Child 2", parent_id=root.id, sort_order=2)
        child2.save(commit=True)
        child2.update_path_and_level()
        child2.save(commit=True)
        
        # 孙节点
        grandchild = TreeMenu(title="Grandchild", parent_id=child1.id, sort_order=1)
        grandchild.save(commit=True)
        grandchild.update_path_and_level()
        grandchild.save(commit=True)
        
        return root, child1, child2, grandchild
    
    def test_get_children(self):
        """测试获取直接子节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        children = root.get_children()
        titles = [c.title for c in children]
        
        assert len(children) == 2
        assert "Child 1" in titles
        assert "Child 2" in titles
    
    def test_get_descendants(self):
        """测试获取所有子孙节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        descendants = root.get_descendants()
        titles = [d.title for d in descendants]
        
        assert len(descendants) == 3
        assert "Grandchild" in titles
    
    def test_get_ancestors(self):
        """测试获取祖先节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        ancestors = grandchild.get_ancestors()
        titles = [a.title for a in ancestors]
        
        assert "Root" in titles
        assert "Child 1" in titles
    
    def test_get_parent(self):
        """测试获取父节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        parent = grandchild.get_parent()
        
        assert parent.title == "Child 1"
    
    def test_get_siblings(self):
        """测试获取兄弟节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        siblings = child1.get_siblings()
        titles = [s.title for s in siblings]
        
        assert "Child 2" in titles
        assert "Child 1" not in titles  # 不包括自己
    
    def test_get_root(self):
        """测试获取根节点"""
        root, child1, child2, grandchild = self._create_tree()
        
        found_root = grandchild.get_root()
        
        assert found_root.title == "Root"
    
    def test_is_leaf(self):
        """测试叶子节点判断"""
        root, child1, child2, grandchild = self._create_tree()
        
        assert root.is_leaf() == False
        assert grandchild.is_leaf() == True
        assert child2.is_leaf() == True
    
    def test_is_ancestor_of(self):
        """测试祖先关系判断"""
        root, child1, child2, grandchild = self._create_tree()
        
        assert root.is_ancestor_of(grandchild) == True
        assert child1.is_ancestor_of(grandchild) == True
        assert child2.is_ancestor_of(grandchild) == False
    
    def test_is_descendant_of(self):
        """测试子孙关系判断"""
        root, child1, child2, grandchild = self._create_tree()
        
        assert grandchild.is_descendant_of(root) == True
        assert grandchild.is_descendant_of(child1) == True
        assert grandchild.is_descendant_of(child2) == False


class TestTreeClassMethods:
    """树形结构类方法测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_get_roots(self):
        """测试获取所有根节点"""
        # 创建多个根节点
        for title in ["Root A", "Root B"]:
            root = TreeMenu(title=title, sort_order=1)
            root.save(commit=True)
            root.update_path_and_level()
            root.save(commit=True)
        
        roots = TreeMenu.get_roots()
        titles = [r.title for r in roots]
        
        assert len(roots) == 2
        assert "Root A" in titles
        assert "Root B" in titles
    
    def test_get_tree_list(self):
        """测试获取树形结构列表"""
        root = TreeMenu(title="Root", sort_order=1)
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        child = TreeMenu(title="Child", parent_id=root.id, sort_order=1)
        child.save(commit=True)
        child.update_path_and_level()
        child.save(commit=True)
        
        tree = TreeMenu.get_tree_list()
        
        assert len(tree) >= 1
        # 树形结构应该有 children 字段
        assert "children" in tree[0]


class TestTreeUtilityFunctions:
    """树形工具函数测试"""
    
    def test_build_tree_list(self):
        """测试构建树形列表"""
        flat_data = [
            {"id": 1, "parent_id": None, "name": "Root"},
            {"id": 2, "parent_id": 1, "name": "Child"},
            {"id": 3, "parent_id": 2, "name": "Grandchild"},
        ]
        
        tree = build_tree_list(flat_data)
        
        assert len(tree) == 1
        assert tree[0]["name"] == "Root"
        assert len(tree[0]["children"]) == 1
        assert tree[0]["children"][0]["name"] == "Child"
    
    def test_flatten_tree(self):
        """测试展平树形结构"""
        tree = [
            {
                "id": 1,
                "name": "Root",
                "children": [
                    {"id": 2, "name": "Child", "children": []}
                ]
            }
        ]
        
        flat = flatten_tree(tree)
        
        assert len(flat) == 2
    
    def test_find_node_in_tree(self):
        """测试在树中查找节点"""
        tree = [
            {
                "id": 1,
                "name": "Root",
                "children": [
                    {"id": 2, "name": "Child", "children": []}
                ]
            }
        ]
        
        found = find_node_in_tree(tree, target_id=2)
        
        assert found is not None
        assert found["name"] == "Child"
    
    def test_calculate_tree_depth(self):
        """测试计算树深度"""
        tree = [
            {
                "id": 1,
                "children": [
                    {
                        "id": 2,
                        "children": [
                            {"id": 3, "children": []}
                        ]
                    }
                ]
            }
        ]
        
        depth = calculate_tree_depth(tree)
        
        assert depth == 3
    
    def test_filter_tree(self):
        """测试过滤树节点"""
        tree = [
            {
                "id": 1,
                "active": True,
                "children": [
                    {"id": 2, "active": False, "children": []},
                    {"id": 3, "active": True, "children": []}
                ]
            }
        ]
        
        filtered = filter_tree(tree, lambda n: n.get("active", False))
        
        # 只保留 active=True 的节点
        assert len(filtered) == 1
        assert len(filtered[0]["children"]) == 1
        assert filtered[0]["children"][0]["id"] == 3


class TestTreeFieldsMixin:
    """TreeFieldsMixin 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库"""
        Base.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_tree_fields_mixin_provides_fields(self):
        """测试 TreeFieldsMixin 提供必要字段"""
        assert hasattr(TreeCategory, 'path')
        assert hasattr(TreeCategory, 'level')
        assert hasattr(TreeCategory, 'sort_order')
    
    def test_category_tree_operations(self):
        """测试分类模型的树形操作"""
        root = TreeCategory(name="Electronics")
        root.save(commit=True)
        root.update_path_and_level()
        root.save(commit=True)
        
        child = TreeCategory(name="Phones", parent_id=root.id)
        child.save(commit=True)
        child.update_path_and_level()
        child.save(commit=True)
        
        assert root.level == 1
        assert child.level == 2
        assert child.get_parent().name == "Electronics"
