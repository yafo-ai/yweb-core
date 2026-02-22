"""组织管理模块 - TreeMixin 测试

测试树形结构 Mixin 的功能
"""

import pytest
from sqlalchemy import Column, Integer, String, create_engine
from sqlalchemy.orm import sessionmaker, scoped_session

from yweb.orm import CoreModel, BaseModel
from yweb.organization import (
    AbstractOrganization,
    AbstractDepartment,
    AbstractEmployee,
    TreeMixin,
)


# ==================== 测试用具体模型定义 ====================

class TreeTestOrganization(AbstractOrganization):
    """测试用组织模型"""
    __tablename__ = "test_tree_organization"
    __table_args__ = {'extend_existing': True}


class TreeTestEmployee(AbstractEmployee):
    """测试用员工模型（用于外键引用）"""
    __tablename__ = "test_tree_employee"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_tree_organization"
    __dept_tablename__ = "test_tree_department"


class TreeTestDepartment(AbstractDepartment):
    """测试用部门模型（带 TreeMixin）"""
    __tablename__ = "test_tree_department"
    __table_args__ = {'extend_existing': True}
    __org_tablename__ = "test_tree_organization"
    __employee_tablename__ = "test_tree_employee"


# ==================== 测试类 ====================

class TestTreeMixin:
    """TreeMixin 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    @pytest.fixture
    def org(self):
        """创建测试组织"""
        org = TreeTestOrganization(name="Test Org", code="TO001")
        org.save(commit=True)
        return org
    
    @pytest.fixture
    def dept_tree(self, org):
        """创建测试部门树
        
        结构:
        - 总公司 (id=1)
          - 技术部 (id=2)
            - 后端组 (id=4)
            - 前端组 (id=5)
          - 市场部 (id=3)
            - 销售一部 (id=6)
        """
        # 总公司
        root = TreeTestDepartment(name="总公司", org_id=org.id, sort_order=1)
        root.save(commit=True)  # 先保存获取 id
        root.update_path_and_level()
        root.save(commit=True)
        
        # 技术部
        tech = TreeTestDepartment(name="技术部", org_id=org.id, parent_id=root.id, sort_order=1)
        tech.save(commit=True)
        tech.update_path_and_level()
        tech.save(commit=True)
        
        # 市场部
        market = TreeTestDepartment(name="市场部", org_id=org.id, parent_id=root.id, sort_order=2)
        market.save(commit=True)
        market.update_path_and_level()
        market.save(commit=True)
        
        # 后端组
        backend = TreeTestDepartment(name="后端组", org_id=org.id, parent_id=tech.id, sort_order=1)
        backend.save(commit=True)
        backend.update_path_and_level()
        backend.save(commit=True)
        
        # 前端组
        frontend = TreeTestDepartment(name="前端组", org_id=org.id, parent_id=tech.id, sort_order=2)
        frontend.save(commit=True)
        frontend.update_path_and_level()
        frontend.save(commit=True)
        
        # 销售一部
        sales = TreeTestDepartment(name="销售一部", org_id=org.id, parent_id=market.id, sort_order=1)
        sales.save(commit=True)
        sales.update_path_and_level()
        sales.save(commit=True)
        
        return {
            "root": root,
            "tech": tech,
            "market": market,
            "backend": backend,
            "frontend": frontend,
            "sales": sales,
        }
    
    def test_path_and_level(self, dept_tree):
        """测试 path 和 level 计算"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        backend = dept_tree["backend"]
        
        # 根节点
        assert root.level == 1
        assert root.path == f"/{root.id}/"
        
        # 二级节点
        assert tech.level == 2
        assert tech.path == f"/{root.id}/{tech.id}/"
        
        # 三级节点
        assert backend.level == 3
        assert backend.path == f"/{root.id}/{tech.id}/{backend.id}/"
    
    def test_is_root(self, dept_tree):
        """测试判断根节点"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        
        assert root.is_root() == True
        assert tech.is_root() == False
    
    def test_is_leaf(self, dept_tree):
        """测试判断叶子节点"""
        root = dept_tree["root"]
        backend = dept_tree["backend"]
        
        assert root.is_leaf() == False  # 有子节点
        assert backend.is_leaf() == True  # 无子节点
    
    def test_get_children(self, dept_tree):
        """测试获取直接子节点"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        
        # 根节点的子节点
        root_children = root.get_children()
        assert len(root_children) == 2
        child_names = [c.name for c in root_children]
        assert "技术部" in child_names
        assert "市场部" in child_names
        
        # 技术部的子节点
        tech_children = tech.get_children()
        assert len(tech_children) == 2
        child_names = [c.name for c in tech_children]
        assert "后端组" in child_names
        assert "前端组" in child_names
    
    def test_get_descendants(self, dept_tree):
        """测试获取所有子孙节点"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        
        # 根节点的所有子孙
        root_descendants = root.get_descendants()
        assert len(root_descendants) == 5  # 技术部、市场部、后端组、前端组、销售一部
        
        # 技术部的所有子孙
        tech_descendants = tech.get_descendants()
        assert len(tech_descendants) == 2  # 后端组、前端组
    
    def test_get_ancestors(self, dept_tree):
        """测试获取所有祖先节点"""
        root = dept_tree["root"]
        backend = dept_tree["backend"]
        tech = dept_tree["tech"]
        
        # 后端组的祖先
        backend_ancestors = backend.get_ancestors()
        assert len(backend_ancestors) == 2  # 总公司、技术部
        ancestor_names = [a.name for a in backend_ancestors]
        assert "总公司" in ancestor_names
        assert "技术部" in ancestor_names
        
        # 根节点没有祖先
        root_ancestors = root.get_ancestors()
        assert len(root_ancestors) == 0
    
    def test_get_parent(self, dept_tree):
        """测试获取父节点"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        backend = dept_tree["backend"]
        
        assert root.get_parent() is None
        assert tech.get_parent().id == root.id
        assert backend.get_parent().id == tech.id
    
    def test_get_siblings(self, dept_tree):
        """测试获取兄弟节点"""
        tech = dept_tree["tech"]
        market = dept_tree["market"]
        backend = dept_tree["backend"]
        frontend = dept_tree["frontend"]
        
        # 技术部的兄弟
        tech_siblings = tech.get_siblings()
        assert len(tech_siblings) == 1
        assert tech_siblings[0].name == "市场部"
        
        # 后端组的兄弟
        backend_siblings = backend.get_siblings()
        assert len(backend_siblings) == 1
        assert backend_siblings[0].name == "前端组"
    
    def test_get_root(self, dept_tree):
        """测试获取根节点"""
        root = dept_tree["root"]
        backend = dept_tree["backend"]
        
        assert backend.get_root().id == root.id
        assert root.get_root().id == root.id
    
    def test_is_ancestor_of(self, dept_tree):
        """测试判断祖先关系"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        backend = dept_tree["backend"]
        market = dept_tree["market"]
        
        assert root.is_ancestor_of(backend) == True
        assert tech.is_ancestor_of(backend) == True
        assert market.is_ancestor_of(backend) == False
        assert backend.is_ancestor_of(root) == False
    
    def test_is_descendant_of(self, dept_tree):
        """测试判断子孙关系"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        backend = dept_tree["backend"]
        
        assert backend.is_descendant_of(root) == True
        assert backend.is_descendant_of(tech) == True
        assert root.is_descendant_of(backend) == False
    
    def test_get_descendant_count(self, dept_tree):
        """测试获取子孙数量"""
        root = dept_tree["root"]
        tech = dept_tree["tech"]
        backend = dept_tree["backend"]
        
        assert root.get_descendant_count() == 5
        assert tech.get_descendant_count() == 2
        assert backend.get_descendant_count() == 0
    
    def test_move_to(self, org, dept_tree):
        """测试移动节点"""
        tech = dept_tree["tech"]
        market = dept_tree["market"]
        backend = dept_tree["backend"]
        frontend = dept_tree["frontend"]
        
        # 将后端组移动到市场部下
        old_path = backend.path
        backend.move_to(market.id)
        backend.save(commit=True)
        
        # 重新查询验证
        backend = TreeTestDepartment.get(backend.id)
        
        assert backend.parent_id == market.id
        assert backend.path != old_path
        assert f"/{market.id}/" in backend.path
    
    def test_move_to_root(self, org, dept_tree):
        """测试移动到根级别"""
        tech = dept_tree["tech"]
        
        # 将技术部移动到根级别
        tech.move_to(None)
        tech.save(commit=True)
        
        # 重新查询验证
        tech = TreeTestDepartment.get(tech.id)
        
        assert tech.parent_id is None
        assert tech.level == 1
        assert tech.is_root() == True
    
    def test_move_to_prevents_circular_reference(self, dept_tree):
        """测试移动节点时防止循环引用"""
        root = dept_tree["root"]
        backend = dept_tree["backend"]
        
        # 尝试将根节点移动到后端组下（应该失败）
        with pytest.raises(ValueError, match="不能将节点移动到其子孙节点下"):
            root.move_to(backend.id)
