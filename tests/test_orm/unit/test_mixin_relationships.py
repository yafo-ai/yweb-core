"""Mixin 模式的关系字段测试

验证通过 Mixin 类定义的 fields.OneToOne / ManyToOne / ManyToMany
能被具体模型类正确处理（FK 列创建、relationship 建立、数据持久化）。

背景：
    process_relationship_fields 原来只扫描 vars(cls)（类自身 __dict__），
    导致 Mixin 中定义的关系字段不会被处理。修复后应能正常工作。
"""
from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker, scoped_session, Mapped, mapped_column, relationship
from sqlalchemy import String

from yweb.orm import CoreModel, BaseModel, fields


# ==================== 目标模型（被关联的一方） ====================

class MxTargetUserModel(BaseModel):
    """用于被 OneToOne / ManyToOne 关联的用户模型"""
    __tablename__ = "test_mx_users"
    __table_args__ = {"extend_existing": True}

    username: Mapped[str] = mapped_column(String(100))


class MxTargetTagModel(BaseModel):
    """用于被 ManyToMany 关联的标签模型"""
    __tablename__ = "test_mx_tags"
    __table_args__ = {"extend_existing": True}

    tag_name: Mapped[str] = mapped_column(String(100))


# ==================== Mixin 定义 ====================

class OneToOneMixin:
    """通过 Mixin 定义一对一关系"""
    user = fields.OneToOne(MxTargetUserModel, on_delete=fields.DO_NOTHING, nullable=True)


class ManyToOneMixin:
    """通过 Mixin 定义多对一关系"""
    author = fields.ManyToOne(MxTargetUserModel, on_delete=fields.DO_NOTHING, nullable=True)


class ManyToManyMixin:
    """通过 Mixin 定义多对多关系"""
    tags = fields.ManyToMany(MxTargetTagModel, on_delete=fields.UNLINK)


# ==================== 使用 Mixin 的具体模型 ====================

class MxEmployeeModel(OneToOneMixin, BaseModel):
    """员工模型 - 通过 Mixin 获得 OneToOne(user)"""
    __tablename__ = "test_mx_employees"
    __table_args__ = {"extend_existing": True}

    emp_name: Mapped[str] = mapped_column(String(100))


class MxArticleModel(ManyToOneMixin, BaseModel):
    """文章模型 - 通过 Mixin 获得 ManyToOne(author)"""
    __tablename__ = "test_mx_articles"
    __table_args__ = {"extend_existing": True}

    title: Mapped[str] = mapped_column(String(200))


class MxPostModel(ManyToManyMixin, BaseModel):
    """帖子模型 - 通过 Mixin 获得 ManyToMany(tags)"""
    __tablename__ = "test_mx_posts"
    __table_args__ = {"extend_existing": True}

    content: Mapped[str] = mapped_column(String(500))


# ==================== Fixture ====================

@pytest.fixture
def setup_db(memory_engine):
    """初始化数据库"""
    BaseModel.metadata.create_all(bind=memory_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(session_factory)
    CoreModel.query = session_scope.query_property()

    yield session_scope

    session_scope.remove()


# ==================== 测试 ====================

class TestMixinOneToOne:
    """Mixin OneToOne 关系测试"""

    def test_fk_column_created(self, setup_db):
        """Mixin 的 OneToOne 应自动创建 FK 列"""
        assert hasattr(MxEmployeeModel, "test_mx_user_id"), \
            "应生成 test_mx_user_id 列（基于目标表名 test_mx_users）"

    def test_relationship_created(self, setup_db):
        """Mixin 的 OneToOne 应自动创建 relationship"""
        user = MxTargetUserModel(username="alice")
        user.add(True)

        emp = MxEmployeeModel(emp_name="员工A")
        emp.user = user
        emp.add(True)

        # 重新查询验证持久化
        emp = MxEmployeeModel.get(emp.id)
        assert emp.user is not None
        assert emp.user.id == user.id

    def test_set_fk_directly(self, setup_db):
        """通过 FK 列直接赋值并持久化"""
        user = MxTargetUserModel(username="bob")
        user.add(True)

        emp = MxEmployeeModel(emp_name="员工B")
        emp.test_mx_user_id = user.id
        emp.add(True)

        emp = MxEmployeeModel.get(emp.id)
        assert emp.test_mx_user_id == user.id
        assert emp.user.username == "bob"


class TestMixinManyToOne:
    """Mixin ManyToOne 关系测试"""

    def test_fk_column_created(self, setup_db):
        """Mixin 的 ManyToOne 应自动创建 FK 列"""
        assert hasattr(MxArticleModel, "test_mx_user_id"), \
            "应生成 test_mx_user_id 列"

    def test_relationship_works(self, setup_db):
        """多篇文章关联同一个作者"""
        author = MxTargetUserModel(username="作者")
        author.add(True)

        a1 = MxArticleModel(title="文章1", test_mx_user_id=author.id)
        a2 = MxArticleModel(title="文章2", test_mx_user_id=author.id)
        MxArticleModel.add_all([a1, a2], commit=True)

        a1 = MxArticleModel.get(a1.id)
        assert a1.author is not None
        assert a1.author.id == author.id


class TestMixinManyToMany:
    """Mixin ManyToMany 关系测试"""

    def test_relationship_works(self, setup_db):
        """通过 Mixin 定义的 ManyToMany 能正常建立关联"""
        tag1 = MxTargetTagModel(tag_name="Python")
        tag2 = MxTargetTagModel(tag_name="ORM")
        MxTargetTagModel.add_all([tag1, tag2], commit=True)

        post = MxPostModel(content="测试帖子")
        post.tags.extend([tag1, tag2])
        post.add(True)

        # 重新查询验证
        post = MxPostModel.get(post.id)
        assert len(post.tags) == 2
        tag_names = {t.tag_name for t in post.tags}
        assert tag_names == {"Python", "ORM"}
