"""多对多关系持久化测试

专门测试 ManyToMany 关系在 soft_delete_hook + event_before_flush 并存环境下的
持久化行为，覆盖以下场景：

1. 已持久化对象之间的 M2M 关联（append 到已有对象）
2. 新对象创建时的 M2M 关联（一次保存）
3. M2M 关联的移除
4. M2M 关联操作后 updated_at / ver 的正确性
5. 双向关系操作（从任一方向添加）
6. 批量关联操作
7. 关联操作与真实列变更同时发生
8. setup_auth 动态 M2M（模拟 User-Role 场景）

背景（BUG 复现）：
  soft_delete_hook._before_flush 会对所有 dirty 对象设置 updated_at，
  如果对象仅因 back_populates 被标记为 dirty（无真实列变更），
  event_before_flush 会误判为"仅 updated_at 变更"→ expunge 该对象
  → ManyToMany INSERT 失败。

  修复方案：
  - soft_delete_hook 仅在 is_modified(include_collections=False) 为 True 时
    才设置 updated_at
  - event_before_flush 仅当 attrs_changed == {'updated_at'} 时才 expunge

注意：
- 类名不以 Test 开头（避免 pytest 对模型类的警告）
- 所有测试都在 activate_soft_delete_hook 激活状态下运行
"""
from __future__ import annotations

import warnings
from datetime import datetime
from time import sleep
from typing import Optional

import pytest
from sqlalchemy import Column, Integer, String, Table, ForeignKey, text
from sqlalchemy.orm import (
    sessionmaker,
    scoped_session,
    relationship,
    Mapped,
    mapped_column,
)

from yweb.orm import (
    CoreModel,
    BaseModel,
    activate_soft_delete_hook,
    fields,
)


# ==================== 场景1: 原生 relationship 定义的 M2M ====================

m2m_tag_article_table = Table(
    "test_m2m_tag_article",
    BaseModel.metadata,
    Column("tag_id", Integer, ForeignKey("test_m2m_tags.id"), primary_key=True),
    Column("article_id", Integer, ForeignKey("test_m2m_articles.id"), primary_key=True),
    extend_existing=True,
)


class M2MTagModel(BaseModel):
    """标签模型（raw relationship M2M）"""

    __tablename__ = "test_m2m_tags"
    __table_args__ = {"extend_existing": True}

    tag_name: Mapped[str] = mapped_column(String(50))

    articles = relationship(
        "M2MArticleModel",
        secondary=m2m_tag_article_table,
        back_populates="tags",
    )


class M2MArticleModel(BaseModel):
    """文章模型（raw relationship M2M）"""

    __tablename__ = "test_m2m_articles"
    __table_args__ = {"extend_existing": True}

    title: Mapped[str] = mapped_column(String(200))

    tags = relationship(
        "M2MTagModel",
        secondary=m2m_tag_article_table,
        back_populates="articles",
    )


# ==================== 场景2: fields.ManyToMany 定义的 M2M ====================


class M2MSkillModel(BaseModel):
    """技能模型（fields.ManyToMany 的目标方）"""

    __tablename__ = "test_m2m_skills"
    __table_args__ = {"extend_existing": True}

    skill_name: Mapped[str] = mapped_column(String(50))


class M2MEmployeeModel(BaseModel):
    """员工模型（使用 fields.ManyToMany）"""

    __tablename__ = "test_m2m_employees"
    __table_args__ = {"extend_existing": True}

    emp_name: Mapped[str] = mapped_column(String(100))

    # 使用框架的 fields.ManyToMany（与 setup_auth 动态创建的方式一致）
    skills = fields.ManyToMany(M2MSkillModel, on_delete=fields.UNLINK)


# ==================== 场景3: 模拟 setup_auth 的动态 M2M ====================


class M2MSimpleRoleModel(BaseModel):
    """简化角色模型（模拟 auth.AbstractSimpleRole）"""

    __tablename__ = "test_m2m_simple_roles"
    __table_args__ = {"extend_existing": True}

    role_code: Mapped[str] = mapped_column(String(50), unique=True)
    role_name: Mapped[str] = mapped_column(String(100))


class M2MUserModel(BaseModel):
    """简化用户模型（模拟 auth.AbstractUser）"""

    __tablename__ = "test_m2m_users"
    __table_args__ = {"extend_existing": True}

    username: Mapped[str] = mapped_column(String(50), unique=True)


# 手动定义中间表（模拟 setup_auth 使用 fields.ManyToMany 的行为）
m2m_user_role_table = Table(
    "test_m2m_user_role",
    BaseModel.metadata,
    Column(
        "user_id",
        Integer,
        ForeignKey("test_m2m_users.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    Column(
        "role_id",
        Integer,
        ForeignKey("test_m2m_simple_roles.id", ondelete="CASCADE"),
        primary_key=True,
    ),
    extend_existing=True,
)

# 动态添加 relationship（模拟 setup.py 的 _add_roles_relationship）
M2MUserModel.roles = relationship(
    M2MSimpleRoleModel,
    secondary=m2m_user_role_table,
    backref="users",
    lazy="selectin",
)


# ==================== Fixture ====================


@pytest.fixture
def setup_db(memory_engine):
    """初始化数据库（激活 soft_delete_hook + event_before_flush）"""
    activate_soft_delete_hook()

    BaseModel.metadata.create_all(bind=memory_engine)
    session_factory = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
    session_scope = scoped_session(session_factory)
    CoreModel.query = session_scope.query_property()

    yield session_scope

    session_scope.remove()


# ==================== 测试类 ====================


class TestM2MPersistWithRawRelationship:
    """场景1: 使用原生 relationship 定义的 M2M 持久化测试"""

    def test_append_to_existing_objects(self, setup_db):
        """核心场景：两个已持久化对象之间建立 M2M 关联

        这是触发 BUG 的经典场景：
        1. tag 和 article 都已 save 到数据库
        2. article.tags.append(tag)
        3. soft_delete_hook 给 dirty 的 tag 设 updated_at
        4. event_before_flush 判断 tag 只有 updated_at 变更 → expunge
        5. M2M INSERT 失败
        """
        tag = M2MTagModel(tag_name="Python")
        tag.add(True)

        article = M2MArticleModel(title="Python入门")
        article.add(True)

        tag_id = tag.id
        article_id = article.id

        # 关键操作：对已持久化对象建立关联
        article.tags.append(tag)
        article.save(commit=True)

        # 验证：关联必须持久化
        session = setup_db()
        session.expire_all()

        article = M2MArticleModel.get(article_id)
        assert len(article.tags) == 1
        assert article.tags[0].id == tag_id

        tag = M2MTagModel.get(tag_id)
        assert len(tag.articles) == 1
        assert tag.articles[0].id == article_id

    def test_no_sa_warning_on_append(self, setup_db):
        """确保 append 操作不产生 SAWarning"""
        tag = M2MTagModel(tag_name="Java")
        tag.add(True)

        article = M2MArticleModel(title="Java实战")
        article.add(True)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            article.tags.append(tag)
            article.save(commit=True)

            # 检查没有 "not in session" 的 SAWarning
            sa_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning)
                and "not in session" in str(x.message)
            ]
            assert len(sa_warnings) == 0, (
                f"不应产生 'not in session' 警告，但收到: "
                f"{[str(x.message) for x in sa_warnings]}"
            )

    def test_append_from_reverse_side(self, setup_db):
        """从反向端（tag.articles.append）建立关联"""
        tag = M2MTagModel(tag_name="Go")
        tag.add(True)

        article = M2MArticleModel(title="Go并发编程")
        article.add(True)

        # 从 tag 侧添加
        tag.articles.append(article)
        tag.save(commit=True)

        # 验证
        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 1
        assert article.tags[0].tag_name == "Go"

    def test_append_new_object_to_existing(self, setup_db):
        """向已持久化对象 append 尚未保存的新对象"""
        article = M2MArticleModel(title="数据结构")
        article.add(True)

        # tag 还没保存
        new_tag = M2MTagModel(tag_name="算法")
        article.tags.append(new_tag)
        article.save(commit=True)

        # 验证新 tag 被级联保存并建立关联
        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 1
        assert article.tags[0].tag_name == "算法"
        assert article.tags[0].id is not None

    def test_create_both_new_with_m2m(self, setup_db):
        """两个新对象同时建立 M2M 关联后一次保存"""
        article = M2MArticleModel(title="机器学习")
        tag1 = M2MTagModel(tag_name="AI")
        tag2 = M2MTagModel(tag_name="ML")

        article.tags.extend([tag1, tag2])
        article.add(True)

        # 验证
        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 2
        tag_names = {t.tag_name for t in article.tags}
        assert tag_names == {"AI", "ML"}

    def test_remove_m2m_association(self, setup_db):
        """移除已有的 M2M 关联"""
        article = M2MArticleModel(title="设计模式")
        tag1 = M2MTagModel(tag_name="OOP")
        tag2 = M2MTagModel(tag_name="GoF")

        article.tags.extend([tag1, tag2])
        article.add(True)
        assert len(article.tags) == 2

        # 移除一个关联
        article.tags.remove(tag1)
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 1
        assert article.tags[0].tag_name == "GoF"

    def test_multiple_append_operations(self, setup_db):
        """多次追加操作"""
        article = M2MArticleModel(title="Web开发")
        article.add(True)

        tags = [M2MTagModel(tag_name=name) for name in ["HTML", "CSS", "JS"]]
        for tag in tags:
            tag.add(True)

        # 逐个追加已有对象
        for tag in tags:
            article.tags.append(tag)
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 3
        tag_names = {t.tag_name for t in article.tags}
        assert tag_names == {"HTML", "CSS", "JS"}

    def test_updated_at_not_bumped_on_back_populates_only(self, setup_db):
        """back_populates 方不应因关联操作而更新 updated_at

        当 article.tags.append(tag) 时：
        - article: 直接操作方，可以更新 updated_at（取决于是否有列变更）
        - tag: 仅因 back_populates 被标记为 dirty，不应更新 updated_at
        """
        tag = M2MTagModel(tag_name="Rust")
        tag.add(True)
        original_tag_updated_at = tag.updated_at
        original_tag_ver = tag.ver

        article = M2MArticleModel(title="Rust系统编程")
        article.add(True)

        # 等一小段时间确保时间差异
        sleep(0.05)

        # 建立关联（tag 是 back_populates 方）
        article.tags.append(tag)
        article.save(commit=True)

        setup_db().expire_all()
        tag = M2MTagModel.get(tag.id)

        # tag 的 updated_at 不应因 back_populates 而变化
        assert tag.updated_at == original_tag_updated_at, (
            f"tag.updated_at 不应变化: 原={original_tag_updated_at}, 现={tag.updated_at}"
        )
        # tag 的 ver 也不应递增
        assert tag.ver == original_tag_ver, (
            f"tag.ver 不应递增: 原={original_tag_ver}, 现={tag.ver}"
        )

    def test_real_column_change_with_m2m_append(self, setup_db):
        """同时修改列属性 + 建立 M2M 关联"""
        tag = M2MTagModel(tag_name="C++")
        tag.add(True)

        article = M2MArticleModel(title="旧标题")
        article.add(True)
        original_article_ver = article.ver

        # 同时修改列和添加关联
        article.title = "C++高级编程"
        article.tags.append(tag)
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)

        # 列变更应该生效
        assert article.title == "C++高级编程"
        # M2M 关联应该生效
        assert len(article.tags) == 1
        assert article.tags[0].tag_name == "C++"
        # updated_at 和 ver 应该递增（因为有真实列变更）
        assert article.ver > original_article_ver

    def test_append_then_remove_in_same_session(self, setup_db):
        """同一 session 中先 append 再 remove"""
        tag = M2MTagModel(tag_name="Temp")
        tag.add(True)

        article = M2MArticleModel(title="临时文章")
        article.add(True)

        # append 然后立即 remove
        article.tags.append(tag)
        article.tags.remove(tag)
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 0


class TestM2MPersistWithFieldsManyToMany:
    """场景2: 使用 fields.ManyToMany 定义的 M2M 持久化测试"""

    def test_append_skill_to_existing_employee(self, setup_db):
        """已持久化员工添加已持久化技能"""
        skill = M2MSkillModel(skill_name="Python")
        skill.add(True)

        emp = M2MEmployeeModel(emp_name="张三")
        emp.add(True)

        emp.skills.append(skill)
        emp.save(commit=True)

        setup_db().expire_all()
        emp = M2MEmployeeModel.get(emp.id)
        assert len(emp.skills) == 1
        assert emp.skills[0].skill_name == "Python"

    def test_no_sa_warning_with_fields_m2m(self, setup_db):
        """fields.ManyToMany 操作不应产生 SAWarning"""
        skill = M2MSkillModel(skill_name="Java")
        skill.add(True)

        emp = M2MEmployeeModel(emp_name="李四")
        emp.add(True)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            emp.skills.append(skill)
            emp.save(commit=True)

            sa_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning)
                and "not in session" in str(x.message)
            ]
            assert len(sa_warnings) == 0

    def test_multiple_skills_to_employee(self, setup_db):
        """员工添加多个技能"""
        skills = [M2MSkillModel(skill_name=n) for n in ["Go", "Rust", "C++"]]
        for s in skills:
            s.add(True)

        emp = M2MEmployeeModel(emp_name="王五")
        emp.add(True)

        emp.skills.extend(skills)
        emp.save(commit=True)

        setup_db().expire_all()
        emp = M2MEmployeeModel.get(emp.id)
        assert len(emp.skills) == 3

    def test_remove_skill_from_employee(self, setup_db):
        """移除员工的技能关联"""
        skill1 = M2MSkillModel(skill_name="SQL")
        skill2 = M2MSkillModel(skill_name="NoSQL")

        emp = M2MEmployeeModel(emp_name="赵六")
        emp.skills.extend([skill1, skill2])
        emp.add(True)

        assert len(emp.skills) == 2

        emp.skills.remove(skill1)
        emp.save(commit=True)

        setup_db().expire_all()
        emp = M2MEmployeeModel.get(emp.id)
        assert len(emp.skills) == 1
        assert emp.skills[0].skill_name == "NoSQL"


class TestM2MPersistDynamicRelationship:
    """场景3: 模拟 setup_auth 的动态 M2M (User-Role 场景)

    这是实际出 BUG 的场景：
    User 和 Role 的关系是在 setup_auth 时通过 fields.ManyToMany 动态创建的，
    通过 setattr + process_relationship_fields 注入到 User 模型上。
    """

    def test_assign_role_to_existing_user(self, setup_db):
        """核心 BUG 复现：给已有用户分配已有角色"""
        user = M2MUserModel(username="admin")
        user.add(True)

        role = M2MSimpleRoleModel(role_code="admin", role_name="管理员")
        role.add(True)

        user_id = user.id
        role_id = role.id

        # 分配角色
        user.roles.append(role)
        user.save(commit=True)

        # 验证持久化
        setup_db().expire_all()
        user = M2MUserModel.get(user_id)
        assert len(user.roles) == 1
        assert user.roles[0].role_code == "admin"

        role = M2MSimpleRoleModel.get(role_id)
        assert len(role.users) == 1
        assert role.users[0].username == "admin"

    def test_assign_role_no_sa_warning(self, setup_db):
        """角色分配不应产生 SAWarning"""
        user = M2MUserModel(username="test_user")
        user.add(True)

        role = M2MSimpleRoleModel(role_code="user", role_name="普通用户")
        role.add(True)

        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            user.roles.append(role)
            user.save(commit=True)

            sa_warnings = [
                x for x in w
                if issubclass(x.category, UserWarning)
                and "not in session" in str(x.message)
            ]
            assert len(sa_warnings) == 0, (
                f"角色分配不应产生 SAWarning: "
                f"{[str(x.message) for x in sa_warnings]}"
            )

    def test_assign_multiple_roles(self, setup_db):
        """给用户分配多个角色"""
        user = M2MUserModel(username="multi_role_user")
        user.add(True)

        roles = []
        for code, name in [("admin", "管理员"), ("user", "员工"), ("audit", "审计")]:
            r = M2MSimpleRoleModel(role_code=code, role_name=name)
            r.add(True)
            roles.append(r)

        for role in roles:
            user.roles.append(role)
        user.save(commit=True)

        setup_db().expire_all()
        user = M2MUserModel.get(user.id)
        assert len(user.roles) == 3
        role_codes = {r.role_code for r in user.roles}
        assert role_codes == {"admin", "user", "audit"}

    def test_remove_role_from_user(self, setup_db):
        """从用户移除角色"""
        user = M2MUserModel(username="role_remove_user")
        r1 = M2MSimpleRoleModel(role_code="r1", role_name="角色1")
        r2 = M2MSimpleRoleModel(role_code="r2", role_name="角色2")

        user.roles.extend([r1, r2])
        user.add(True)

        user_id = user.id
        assert len(user.roles) == 2

        user.roles.remove(r1)
        user.save(commit=True)

        setup_db().expire_all()
        user = M2MUserModel.get(user_id)
        assert len(user.roles) == 1
        assert user.roles[0].role_code == "r2"

    def test_role_not_updated_on_user_assignment(self, setup_db):
        """分配角色时，角色自身的 updated_at 和 ver 不应变化"""
        role = M2MSimpleRoleModel(role_code="stable", role_name="稳定角色")
        role.add(True)
        original_updated_at = role.updated_at
        original_ver = role.ver

        user = M2MUserModel(username="new_user")
        user.add(True)

        sleep(0.05)

        user.roles.append(role)
        user.save(commit=True)

        setup_db().expire_all()
        role = M2MSimpleRoleModel.get(role.id)
        assert role.updated_at == original_updated_at
        assert role.ver == original_ver

    def test_user_with_real_change_and_role_assignment(self, setup_db):
        """同时修改用户列属性 + 分配角色"""
        user = M2MUserModel(username="old_name")
        user.add(True)

        role = M2MSimpleRoleModel(role_code="editor", role_name="编辑")
        role.add(True)
        original_user_ver = user.ver

        # 同时修改列和添加关联
        user.username = "new_name"
        user.roles.append(role)
        user.save(commit=True)

        setup_db().expire_all()
        user = M2MUserModel.get(user.id)
        assert user.username == "new_name"
        assert len(user.roles) == 1
        assert user.ver > original_user_ver

    def test_sequential_role_assignments(self, setup_db):
        """分多次 commit 逐个分配角色"""
        user = M2MUserModel(username="seq_user")
        user.add(True)

        role1 = M2MSimpleRoleModel(role_code="seq_r1", role_name="序列角色1")
        role1.add(True)
        role2 = M2MSimpleRoleModel(role_code="seq_r2", role_name="序列角色2")
        role2.add(True)

        # 第一次分配
        user.roles.append(role1)
        user.save(commit=True)

        setup_db().expire(user, ["roles"])
        assert len(user.roles) == 1

        # 第二次分配
        user.roles.append(role2)
        user.save(commit=True)

        setup_db().expire_all()
        user = M2MUserModel.get(user.id)
        assert len(user.roles) == 2
        role_codes = {r.role_code for r in user.roles}
        assert role_codes == {"seq_r1", "seq_r2"}

    def test_verify_association_table_directly(self, setup_db):
        """直接查询中间表验证关联记录确实写入"""
        user = M2MUserModel(username="verify_user")
        user.add(True)

        role = M2MSimpleRoleModel(role_code="verify_role", role_name="验证角色")
        role.add(True)

        user.roles.append(role)
        user.save(commit=True)

        # 直接查询中间表
        session = setup_db()
        result = session.execute(
            text("SELECT user_id, role_id FROM test_m2m_user_role")
        ).fetchall()

        assert len(result) == 1
        assert result[0][0] == user.id
        assert result[0][1] == role.id


class TestM2MPersistEdgeCases:
    """边界场景测试"""

    def test_empty_append_no_error(self, setup_db):
        """空列表 extend 不报错"""
        article = M2MArticleModel(title="空标签文章")
        article.add(True)

        article.tags.extend([])
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        assert len(article.tags) == 0

    def test_duplicate_append_raises_integrity_error(self, setup_db):
        """重复 append 同一对象会因中间表主键约束而报错

        SQLAlchemy 的 InstrumentedList 允许重复 append（内存中），
        但 flush 到数据库时会因中间表的复合主键约束而抛出 IntegrityError。
        使用前应先检查是否已存在关联。
        """
        from sqlalchemy.exc import IntegrityError

        tag = M2MTagModel(tag_name="唯一标签")
        article = M2MArticleModel(title="重复测试")

        article.tags.append(tag)
        article.tags.append(tag)  # 重复

        with pytest.raises(IntegrityError):
            article.add(True)

        # 回滚后 session 恢复正常
        setup_db().rollback()

    def test_m2m_persist_across_fresh_query(self, setup_db):
        """完全重新查询后关联仍在"""
        tag = M2MTagModel(tag_name="持久标签")
        tag.add(True)

        article = M2MArticleModel(title="持久文章")
        article.add(True)

        article_id = article.id
        tag_id = tag.id

        article.tags.append(tag)
        article.save(commit=True)

        # 完全清理 session 后重新查询
        session = setup_db()
        session.expunge_all()
        session.close()

        fresh_article = M2MArticleModel.get(article_id)
        assert fresh_article is not None
        assert len(fresh_article.tags) == 1
        assert fresh_article.tags[0].id == tag_id

    def test_m2m_with_soft_deleted_target(self, setup_db):
        """软删除的目标对象不应出现在关联列表中"""
        tag = M2MTagModel(tag_name="将被删除")
        article = M2MArticleModel(title="有软删除标签")

        article.tags.append(tag)
        article.add(True)

        assert len(article.tags) == 1

        # 软删除 tag
        tag.delete(True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        # 软删除后，查询不到该标签
        assert len(article.tags) == 0

    def test_concurrent_m2m_modifications(self, setup_db):
        """同一 session 中多个对象同时修改 M2M"""
        tag_shared = M2MTagModel(tag_name="共享标签")
        tag_shared.add(True)

        article1 = M2MArticleModel(title="文章1")
        article1.add(True)
        article2 = M2MArticleModel(title="文章2")
        article2.add(True)

        # 两篇文章同时关联同一标签
        article1.tags.append(tag_shared)
        article2.tags.append(tag_shared)

        session = setup_db()
        session.commit()

        setup_db().expire_all()
        tag_shared = M2MTagModel.get(tag_shared.id)
        assert len(tag_shared.articles) == 2

    def test_save_only_m2m_no_unnecessary_update(self, setup_db):
        """仅添加 M2M 关联时，不应对主对象产生多余的 UPDATE

        如果主对象没有列变更，理想情况下不应有 UPDATE 语句。
        关联操作应只产生中间表的 INSERT。
        """
        article = M2MArticleModel(title="无变更文章")
        article.add(True)
        original_ver = article.ver

        tag = M2MTagModel(tag_name="关联标签")
        tag.add(True)
        original_tag_ver = tag.ver

        article.tags.append(tag)
        article.save(commit=True)

        setup_db().expire_all()
        article = M2MArticleModel.get(article.id)
        tag = M2MTagModel.get(tag.id)

        # 关联应该成功
        assert len(article.tags) == 1

        # tag 不应有 ver 变化（它没有任何列变更）
        assert tag.ver == original_tag_ver
