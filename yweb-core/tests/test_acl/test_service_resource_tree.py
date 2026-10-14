"""AclService.get_resource_tree 过滤测试

验证 resource_type 过滤参数实际生效：
- 传 resource_type 只返回该类型的资源
- 不传返回全部
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
        table_prefix="test_tree_",
    )


@pytest.fixture(scope="module")
def AclResource(acl):
    return acl.AclResource


class TestGetResourceTreeFilter:
    """get_resource_tree 的 resource_type 过滤"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine, AclResource):
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()

    def _seed_mixed_resources(self, AclResource):
        """创建混合类型的资源节点"""
        AclResource(
            resource_type="FOLDER", resource_id="f1",
            display_name="Folder 1", parent_id=None,
        ).save(commit=True)
        AclResource(
            resource_type="FOLDER", resource_id="f2",
            display_name="Folder 2", parent_id=None,
        ).save(commit=True)
        AclResource(
            resource_type="DOCUMENT", resource_id="d1",
            display_name="Doc 1", parent_id=None,
        ).save(commit=True)
        AclResource(
            resource_type="DOCUMENT", resource_id="d2",
            display_name="Doc 2", parent_id=None,
        ).save(commit=True)
        AclResource(
            resource_type="API_ROUTE", resource_id="a1",
            display_name="API 1", parent_id=None,
        ).save(commit=True)

    def test_filter_by_resource_type_returns_only_matching(self, acl, AclResource):
        """按 resource_type 过滤只返回匹配的节点"""
        self._seed_mixed_resources(AclResource)
        service = acl.get_service()

        tree = service.get_resource_tree(resource_type="FOLDER")

        all_ids = self._collect_resource_ids(tree)
        assert "f1" in all_ids
        assert "f2" in all_ids
        assert "d1" not in all_ids, "DOCUMENT 不应出现在 FOLDER 过滤结果中"
        assert "d2" not in all_ids
        assert "a1" not in all_ids, "API_ROUTE 不应出现在 FOLDER 过滤结果中"

    def test_filter_returns_empty_for_nonexistent_type(self, acl, AclResource):
        """过滤不存在的类型返回空列表"""
        self._seed_mixed_resources(AclResource)
        service = acl.get_service()

        tree = service.get_resource_tree(resource_type="NONEXISTENT")
        assert tree == []

    def test_no_filter_returns_all_types(self, acl, AclResource):
        """不传 resource_type 返回全部类型"""
        self._seed_mixed_resources(AclResource)
        service = acl.get_service()

        tree = service.get_resource_tree(resource_type=None)

        all_ids = self._collect_resource_ids(tree)
        assert len(all_ids) >= 3, f"应返回多种类型的资源，实际只有 {len(all_ids)} 个"

    def _collect_resource_ids(self, tree_nodes: list[dict]) -> set[str]:
        """递归收集树中所有 resource_id"""
        ids = set()
        for node in tree_nodes:
            rid = node.get("resource_id")
            if rid:
                ids.add(rid)
            children = node.get("children", [])
            ids.update(self._collect_resource_ids(children))
        return ids
