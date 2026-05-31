"""AclEngine inherit_parent 继承断开逻辑测试

验证 _collect_rules 在资源树遍历中正确处理 inherit_parent=False：
- 节点自身的规则不因 inherit_parent=False 被跳过
- inherit_parent=False 只阻止继续向上遍历
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.pool import StaticPool

from yweb.orm import CoreModel, BaseModel
from yweb.acl.factory import create_acl_models


@pytest.fixture(scope="module")
def acl():
    return create_acl_models(
        table_prefix="test_inherit_",
    )


@pytest.fixture(scope="module")
def AclRule(acl):
    return acl.AclRule


@pytest.fixture(scope="module")
def AclResource(acl):
    return acl.AclResource


class TestCollectRulesInheritParent:
    """_collect_rules 在 inherit_parent=False 场景下的行为"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine, AclRule, AclResource):
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()

    def test_grandparent_inherit_parent_false_own_rules_still_collected(
        self, acl, AclRule, AclResource
    ):
        """祖父节点 inherit_parent=False 时，祖父自身的规则仍然传播到孙子

        树结构: G(inherit_parent=False) → P(inherit_parent=True) → T(target)
        G 有 inherit=True 的 ALLOW 规则，T 应该能拿到这条规则。
        """
        engine = acl.get_engine()

        g = AclResource(
            resource_type="FOLDER", resource_id="g1",
            display_name="Grandparent", parent_id=None,
            inherit_parent=False,
        )
        g.save(commit=True)

        p = AclResource(
            resource_type="FOLDER", resource_id="p1",
            display_name="Parent", parent_id=g.id,
            inherit_parent=True,
        )
        p.save(commit=True)

        t = AclResource(
            resource_type="FOLDER", resource_id="t1",
            display_name="Target", parent_id=p.id,
            inherit_parent=True,
        )
        t.save(commit=True)

        AclRule(
            resource_type="FOLDER", resource_id="g1",
            subject_id="everyone", subject_type="everyone",
            permission_level=10, effect="ALLOW", inherit=True,
        ).save(commit=True)

        level = engine.get_effective_level({"everyone"}, "FOLDER", "t1")
        assert level == 10, (
            f"祖父节点 inherit_parent=False 不应阻止其自身规则传播到孙子，"
            f"期望 10，实际 {level}"
        )

    def test_grandparent_inherit_parent_false_blocks_great_grandparent(
        self, acl, AclRule, AclResource
    ):
        """祖父节点 inherit_parent=False 阻止从曾祖传播

        树结构: GG → G(inherit_parent=False) → P → T
        GG 有 ALLOW 规则，G 断开继承，T 不应拿到 GG 的规则。
        """
        engine = acl.get_engine()

        gg = AclResource(
            resource_type="DOC", resource_id="gg1",
            display_name="GreatGrand", parent_id=None,
            inherit_parent=True,
        )
        gg.save(commit=True)

        g = AclResource(
            resource_type="DOC", resource_id="g2",
            display_name="Grand", parent_id=gg.id,
            inherit_parent=False,
        )
        g.save(commit=True)

        p = AclResource(
            resource_type="DOC", resource_id="p2",
            display_name="Parent", parent_id=g.id,
            inherit_parent=True,
        )
        p.save(commit=True)

        t = AclResource(
            resource_type="DOC", resource_id="t2",
            display_name="Target", parent_id=p.id,
            inherit_parent=True,
        )
        t.save(commit=True)

        AclRule(
            resource_type="DOC", resource_id="gg1",
            subject_id="user:1", subject_type="user",
            permission_level=30, effect="ALLOW", inherit=True,
        ).save(commit=True)

        level = engine.get_effective_level({"user:1"}, "DOC", "t2")
        assert level == 0, (
            f"G.inherit_parent=False 应阻止曾祖 GG 的规则传播，"
            f"期望 0，实际 {level}"
        )

    def test_target_inherit_parent_false_ignores_parent_rules(
        self, acl, AclRule, AclResource
    ):
        """目标节点 inherit_parent=False 时，忽略所有父级规则

        树结构: P → T(inherit_parent=False)
        P 有 ALLOW 规则，T 不应继承。
        """
        engine = acl.get_engine()

        p = AclResource(
            resource_type="FILE", resource_id="p3",
            display_name="Parent", parent_id=None,
            inherit_parent=True,
        )
        p.save(commit=True)

        t = AclResource(
            resource_type="FILE", resource_id="t3",
            display_name="Target", parent_id=p.id,
            inherit_parent=False,
        )
        t.save(commit=True)

        AclRule(
            resource_type="FILE", resource_id="p3",
            subject_id="dept:tech", subject_type="dept",
            permission_level=20, effect="ALLOW", inherit=True,
        ).save(commit=True)

        level = engine.get_effective_level({"dept:tech"}, "FILE", "t3")
        assert level == 0, (
            f"目标节点 inherit_parent=False 应忽略父级规则，"
            f"期望 0，实际 {level}"
        )

    def test_target_inherit_parent_false_keeps_own_direct_rules(
        self, acl, AclRule, AclResource
    ):
        """目标节点 inherit_parent=False 时，仍保留自身的直接规则"""
        engine = acl.get_engine()

        p = AclResource(
            resource_type="API", resource_id="p4",
            display_name="Parent", parent_id=None,
            inherit_parent=True,
        )
        p.save(commit=True)

        t = AclResource(
            resource_type="API", resource_id="t4",
            display_name="Target", parent_id=p.id,
            inherit_parent=False,
        )
        t.save(commit=True)

        AclRule(
            resource_type="API", resource_id="t4",
            subject_id="user:5", subject_type="user",
            permission_level=50, effect="ALLOW", inherit=False,
        ).save(commit=True)

        level = engine.get_effective_level({"user:5"}, "API", "t4")
        assert level == 50, (
            f"目标节点 inherit_parent=False 不应影响自身直接规则，"
            f"期望 50，实际 {level}"
        )
