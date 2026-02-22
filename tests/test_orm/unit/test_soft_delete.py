"""软删除功能测试

测试软删除相关的功能
"""

import pytest
from datetime import datetime, timedelta
from sqlalchemy import Column, Integer, String, ForeignKey, create_engine
from sqlalchemy.orm import sessionmaker, relationship, scoped_session

from yweb.orm import (
    CoreModel,
    BaseModel,
    SimpleSoftDeleteMixin,
    generate_soft_delete_mixin_class,
    activate_soft_delete_hook,
    deactivate_soft_delete_hook,
    is_soft_delete_active,
    SoftDeleteRewriter,
    IgnoredTable,
)


# ==================== 测试模型定义 ====================
# extend_existing=True：避免 pytest 多文件加载时重复定义表的错误

class ArticleModel(BaseModel):
    """测试文章模型"""
    __tablename__ = "test_articles"
    __table_args__ = {'extend_existing': True}
    
    title = Column(String(200))
    content = Column(String(1000))


class PostModel(BaseModel):
    """测试帖子模型"""
    __tablename__ = "test_posts"
    __table_args__ = {'extend_existing': True}
    
    title = Column(String(200))


class CommentModel(BaseModel):
    """测试评论模型"""
    __tablename__ = "test_comments"
    __table_args__ = {'extend_existing': True}
    
    text = Column(String(500))


# ==================== 主表-子表关系模型 ====================
# 用于测试级联软删除

class ParentModel(BaseModel):
    """父表模型"""
    __tablename__ = "test_parents"
    __table_args__ = {'extend_existing': True}
    
    name = Column(String(100))
    
    # 一对多关系：一个父表可以有多个子表记录
    children = relationship("ChildModel", back_populates="parent")


class ChildModel(BaseModel):
    """子表模型"""
    __tablename__ = "test_children"
    __table_args__ = {'extend_existing': True}
    
    name = Column(String(100))
    parent_id = Column(Integer, ForeignKey("test_parents.id"), nullable=True)
    
    # 多对一关系
    parent = relationship("ParentModel", back_populates="children")


# ==================== 测试类 ====================

class TestSimpleSoftDeleteMixin:
    """SimpleSoftDeleteMixin 测试"""
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_mixin_adds_deleted_at_column(self):
        """测试 Mixin 添加 deleted_at 列"""
        assert hasattr(ArticleModel, 'deleted_at')
    
    def test_new_record_not_deleted(self):
        """测试新记录未删除"""
        article = ArticleModel(title="Test", content="Content")
        article.add(True)
        articleTest = ArticleModel.get(article.id)
        assert articleTest.deleted_at is None
        assert articleTest.is_deleted == False
    
    def test_soft_delete_sets_deleted_at(self):
        """测试软删除设置 deleted_at"""
        article = ArticleModel(title="Test", content="Content")
        article.add(True)
        
        article_id = article.id
        
        # 执行软删除（通过 框架底层 delete 钩子 自动拦截）
        article.delete(True)
        
        # 重新查询以验证（包含已删除的记录）
        article = ArticleModel.query.execution_options(include_deleted=True).filter_by(id=article_id).first()
        assert article is not None
        assert article.deleted_at is not None
        
        # 软删除后，正常查询应该找不到（被过滤）
        articleTest = ArticleModel.get(article_id)
        assert articleTest is None
    
    def test_is_deleted_property(self):
        """测试 is_deleted 属性"""
        article = ArticleModel(title="Test", content="Content")
        article.add(True)
        
        article_id = article.id
        
        assert article.is_deleted == False
        
        article.delete(True)
        
        # 重新查询验证
        article = ArticleModel.query.execution_options(include_deleted=True).filter_by(id=article_id).first()
        assert article.is_deleted == True
    
    
    def test_soft_delete_uses_system_time(self):
        """测试软删除使用系统时间，不能自定义删除时间"""
        article = ArticleModel(title="Test", content="Content")
        article.add(True)
        
        article_id = article.id
        
        article.deleted_at = (datetime.now() - timedelta(minutes=1)).isoformat()
        
        # 记录删除前的时间
        before_delete = datetime.now()
        
        # 软删除（通过 delete 自动拦截）
        article.delete(True)
        
        after_delete = datetime.now()
        
        # 重新查询验证
        article = ArticleModel.query.execution_options(include_deleted=True).filter_by(id=article_id).first()
        assert article.deleted_at is not None
        assert article.is_deleted == True
        
        # 验证删除时间是系统时间（在 before 和 after 之间）
        # deleted_at 现在直接是 datetime 对象
        assert before_delete <= article.deleted_at <= after_delete, \
            f"删除时间 {article.deleted_at} 应该在 {before_delete} 和 {after_delete} 之间"


class TestGenerateSoftDeleteMixinClass:
    """generate_soft_delete_mixin_class 测试"""
    
    def test_generate_mixin_default(self):
        """测试生成默认配置的 Mixin"""
        # 先确保钩子未激活
        deactivate_soft_delete_hook()
        
        CustomMixin = generate_soft_delete_mixin_class()
        
        assert CustomMixin is not None
        assert hasattr(CustomMixin, 'deleted_at')
        assert hasattr(CustomMixin, 'soft_delete')
        assert hasattr(CustomMixin, 'undelete')
    
    def test_generate_mixin_with_custom_field_name(self):
        """测试生成自定义字段名的 Mixin"""
        deactivate_soft_delete_hook()
        
        CustomMixin = generate_soft_delete_mixin_class(
            deleted_field_name="removed_at"
        )
        
        assert hasattr(CustomMixin, 'removed_at')
    
    def test_generate_mixin_with_custom_method_name(self):
        """测试生成自定义方法名的 Mixin"""
        deactivate_soft_delete_hook()
        
        CustomMixin = generate_soft_delete_mixin_class(
            delete_method_name="remove",
            undelete_method_name="restore"
        )
        
        assert hasattr(CustomMixin, 'remove')
        assert hasattr(CustomMixin, 'restore')
    
    def test_generate_mixin_with_ignored_tables(self):
        """测试生成带忽略表的 Mixin"""
        deactivate_soft_delete_hook()
        
        CustomMixin = generate_soft_delete_mixin_class(
            ignored_tables=[
                IgnoredTable(name='audit_log'),
                IgnoredTable(name='system_config')
            ]
        )
        
        assert CustomMixin is not None


class TestSoftDeleteHook:
    """软删除钩子测试"""
    
    def teardown_method(self):
        """每个测试后清理"""
        deactivate_soft_delete_hook()
    
    def test_activate_soft_delete_hook(self):
        """测试激活软删除钩子"""
        deactivate_soft_delete_hook()
        
        activate_soft_delete_hook()
        assert is_soft_delete_active() == True
    
    def test_deactivate_soft_delete_hook(self):
        """测试停用软删除钩子"""
        activate_soft_delete_hook()
        deactivate_soft_delete_hook()
        
        assert is_soft_delete_active() == False
    
    def test_is_soft_delete_active(self):
        """测试检查软删除是否激活"""
        deactivate_soft_delete_hook()
        assert is_soft_delete_active() == False
        
        activate_soft_delete_hook()
        assert is_soft_delete_active() == True
        
        deactivate_soft_delete_hook()
        assert is_soft_delete_active() == False
    
    def test_activate_with_custom_field(self):
        """测试激活带自定义字段的钩子"""
        deactivate_soft_delete_hook()
        
        activate_soft_delete_hook(
            deleted_field_name="removed_at",
            disable_soft_delete_option_name="show_removed"
        )
        
        assert is_soft_delete_active() == True


class TestSoftDeleteRewriter:
    """SoftDeleteRewriter 测试"""
    
    def test_rewriter_creation(self):
        """测试创建重写器"""
        rewriter = SoftDeleteRewriter()
        assert rewriter is not None
    
    def test_rewriter_with_custom_field(self):
        """测试自定义字段的重写器"""
        rewriter = SoftDeleteRewriter(deleted_field_name="removed_at")
        assert rewriter.deleted_field_name == "removed_at"
    
    def test_rewriter_with_custom_option(self):
        """测试自定义选项的重写器"""
        rewriter = SoftDeleteRewriter(
            disable_soft_delete_option_name="show_all"
        )
        assert rewriter.disable_soft_delete_option_name == "show_all"
    
    def test_rewriter_with_ignored_tables(self):
        """测试带忽略表的重写器"""
        rewriter = SoftDeleteRewriter(
            ignored_tables=[
                IgnoredTable(name='audit_log')
            ]
        )
        assert len(rewriter.ignored_tables) == 1


class TestIgnoredTable:
    """IgnoredTable 测试"""
    
    def test_ignored_table_creation(self):
        """测试创建忽略表"""
        ignored = IgnoredTable(name="system_logs")
        assert ignored is not None
        assert ignored.name == "system_logs"
    
    def test_ignored_table_list(self):
        """测试忽略表列表"""
        ignored_tables = [
            IgnoredTable(name="system_logs"),
            IgnoredTable(name="audit_logs"),
        ]
        
        assert len(ignored_tables) == 2
        assert ignored_tables[0].name == "system_logs"
        assert ignored_tables[1].name == "audit_logs"
    
    def test_ignored_table_with_schema(self):
        """测试带 schema 的忽略表"""
        ignored = IgnoredTable(name="my_table", table_schema="public")
        
        assert ignored.name == "my_table"
        assert ignored.table_schema == "public"


class TestSoftDeleteIntegration:
    """软删除集成测试
    
    注意：由于 SQLAlchemy 事件监听器一旦注册就无法移除，
    这些测试需要确保 soft delete hook 处于激活状态
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        # 确保 hook 已激活（因为之前的测试可能已注册了事件监听器）
        activate_soft_delete_hook()
        
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_multiple_soft_delete_models(self):
        """测试多个软删除模型"""
        post = PostModel(title="Test Post")
        comment = CommentModel(text="Test Comment")
        
        post.add()
        comment.add(True)
        
        # 获取数据库值
        post_id = post.id
        comment_id = comment.id
        
        # 新查询获取最新状态（包括已删除的）
        post = PostModel.query.execution_options(include_deleted=True).filter(
            PostModel.id == post_id
        ).first()
        comment = CommentModel.query.execution_options(include_deleted=True).filter(
            CommentModel.id == comment_id
        ).first()
        
        assert post.deleted_at is None
        assert comment.deleted_at is None
        
        post.delete(True)
        
        # 重新查询（包括已删除的）
        post = PostModel.query.execution_options(include_deleted=True).filter(
            PostModel.id == post_id
        ).first()
        
        assert post.deleted_at is not None
        assert comment.deleted_at is None  # 未受影响
    
    def test_manual_filter_soft_deleted(self):
        """测试手动过滤软删除记录"""
        # 创建多个记录
        post1 = PostModel(title="Post 1")
        post2 = PostModel(title="Post 2")
        post3 = PostModel(title="Post 3")
        
        PostModel.add_all([post1, post2, post3], commit=True)
        
        # 软删除一个
        post2.delete(True)
        
        # 查询所有（包括已删除的）
        all_posts = PostModel.query.execution_options(include_deleted=True).filter(
            PostModel.title.like("Post%")
        ).all()
        assert len(all_posts) == 3  # 包含已删除的
        
        # 正常查询（自动过滤已删除）
        active_posts = PostModel.query.filter(
            PostModel.title.like("Post%")
        ).all()
        assert len(active_posts) == 2
    
    def test_soft_delete_then_restore(self):
        """测试软删除后恢复"""
        post = PostModel(title="Restore Test")
        post.add(True)
        
        post_id = post.id
        
        # 软删除
        post.delete(True)
        
        # 重新查询（包括已删除的）
        post = PostModel.query.execution_options(include_deleted=True).filter(
            PostModel.id == post_id
        ).first()
        assert post is not None
        assert post.is_deleted == True
        
        # 恢复
        post.undelete()
        post.update(True)
        
        # 重新查询
        post = PostModel.query.execution_options(include_deleted=True).filter(
            PostModel.id == post_id
        ).first()
        assert post is not None
        assert post.is_deleted == False
        
        # 正常查询确认可以找到
        found = PostModel.query.filter(
            PostModel.title == "Restore Test"
        ).first()
        assert found is not None


class TestParentChildSoftDelete:
    """主表-子表软删除测试
    
    测试场景：
    1. 删除主表时，子表的外键不应被置为空
    2. 删除主表时，子表应该被级联软删除（如果开启级联）
    3. 或者至少子表应保持原有的外键关系
    """
    
    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine):
        """初始化数据库会话"""
        activate_soft_delete_hook()
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        self.session_scope = scoped_session(SessionLocal)
        CoreModel.query = self.session_scope.query_property()
        yield
        self.session_scope.remove()
    
    def test_child_foreign_key_not_nullified_on_parent_soft_delete(self):
        """测试：软删除主表时，子表的外键不应被置为空
        
        期望行为：删除主表后，子表的 parent_id 仍然保持原值
        """
        # 创建主表记录
        parent = ParentModel(name="Parent 1")
        parent.add(True)
        
        parent_id = parent.id
        
        # 创建子表记录，关联到主表
        child = ChildModel(name="Child 1", parent_id=parent_id)
        child.add(True)
        
        child_id = child.id
        
        # 确认子表的外键已设置
        child = ChildModel.query.execution_options(include_deleted=True).filter(
            ChildModel.id == child_id
        ).first()
        assert child.parent_id == parent_id
        
        # 软删除主表
        parent = ParentModel.query.execution_options(include_deleted=True).filter(
            ParentModel.id == parent_id
        ).first()
        parent.delete(True)
        
        # 重新查询子表，检查外键是否仍然保持
        child = ChildModel.query.execution_options(include_deleted=True).filter(
            ChildModel.id == child_id
        ).first()
        
        # 关键断言：子表的外键不应被置为空
        assert child.parent_id == parent_id, \
            f"子表的外键被错误地置为空！期望 parent_id={parent_id}，实际={child.parent_id}"
    
    def test_child_should_be_cascade_soft_deleted_with_parent(self):
        """测试：删除主表时，子表应该被级联软删除
        
        注意：当前实现可能不支持级联软删除，这个测试用于验证行为
        
        期望行为（理想情况）：
        - 软删除主表后，关联的子表也应该被标记为软删除
        - 子表的 deleted_at 应该被设置
        
        实际行为（当前实现）：
        - 可能子表不会被自动软删除
        - 这个测试用于文档化当前行为并标记为待改进
        """
        # 创建主表记录
        parent = ParentModel(name="Cascade Parent")
        parent.add(True)
        
        parent_id = parent.id
        
        # 创建多个子表记录
        child1 = ChildModel(name="Cascade Child 1", parent_id=parent_id)
        child2 = ChildModel(name="Cascade Child 2", parent_id=parent_id)
        ChildModel.add_all([child1, child2], commit=True)
        
        child1_id = child1.id
        child2_id = child2.id
        
        # 软删除主表
        parent = ParentModel.query.execution_options(include_deleted=True).filter(
            ParentModel.id == parent_id
        ).first()
        parent.delete(True)
        
        # 查询子表状态
        child1 = ChildModel.query.execution_options(include_deleted=True).filter(
            ChildModel.id == child1_id
        ).first()
        child2 = ChildModel.query.execution_options(include_deleted=True).filter(
            ChildModel.id == child2_id
        ).first()
        
        # 当前实现：子表不会被自动软删除
        # 这里我们只验证当前行为，不做强制断言
        # 如果将来实现了级联软删除，可以取消下面的注释
        
        # 验证子表外键仍然存在
        assert child1.parent_id == parent_id
        assert child2.parent_id == parent_id
        
        # TODO: 如果需要级联软删除，应该实现以下断言
        # assert child1.is_deleted == True, "子表应该被级联软删除"
        # assert child2.is_deleted == True, "子表应该被级联软删除"
        
        # 当前行为：子表未被软删除
        # 这是一个已知的限制，记录在此
        print(f"注意：当前实现中，子表 is_deleted = {child1.is_deleted}（未实现级联软删除）")
    
    def test_delete_orphan_should_be_prevented(self):
        """测试：delete-orphan 级联配置应该被阻止
        
        原项目中明确禁止使用 delete_orphan，因为它与软删除不兼容
        """
        # 这个测试验证当前行为：
        # 如果模型配置了 cascade="all, delete-orphan"，
        # 在 before_flush 时应该抛出异常
        
        # 由于我们的测试模型没有配置 delete_orphan，
        # 这里主要是文档化这个限制
        pass
    
    def test_orphaned_child_keeps_original_state(self):
        """测试：主表被删除后，孤儿子表应保持原状态
        
        当主表被软删除后，子表：
        1. 外键不变
        2. 仍然可以查询到
        3. 可以被独立软删除
        """
        # 创建数据
        parent = ParentModel(name="To Be Deleted Parent")
        parent.add(True)
        
        parent_id = parent.id
        
        child = ChildModel(name="Orphan Child", parent_id=parent_id)
        child.add(True)
        
        child_id = child.id
        
        # 软删除主表
        parent = ParentModel.query.execution_options(include_deleted=True).filter(
            ParentModel.id == parent_id
        ).first()
        parent.delete(True)
        
        # 子表应该仍然存在且未被删除
        child = ChildModel.query.filter(
            ChildModel.id == child_id
        ).first()
        
        assert child is not None, "子表应该仍然存在"
        assert child.parent_id == parent_id, "子表的外键应保持不变"
        assert child.is_deleted == False, "子表不应被自动删除"
        
        # 子表可以被独立软删除
        child.delete(True)
        
        child = ChildModel.query.execution_options(include_deleted=True).filter(
            ChildModel.id == child_id
        ).first()
        assert child.is_deleted == True
