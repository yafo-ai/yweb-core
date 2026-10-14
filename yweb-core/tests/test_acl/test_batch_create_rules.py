"""AclService.batch_create_rules upsert 行为测试。"""

from __future__ import annotations

import pytest
from sqlalchemy.orm import sessionmaker, scoped_session

from yweb.orm import CoreModel, BaseModel
from yweb.acl.factory import create_acl_models


@pytest.fixture(scope="module")
def acl():
    return create_acl_models(table_prefix="test_batch_rule_")


@pytest.fixture(scope="module")
def AclRule(acl):
    return acl.AclRule


class TestBatchCreateRulesUpsert:
    """同主体+效果+资源：等级不同则更新，完全相同则跳过。"""

    @pytest.fixture(autouse=True)
    def setup_db(self, memory_engine, AclRule):
        BaseModel.metadata.create_all(bind=memory_engine)
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=memory_engine)
        session_scope = scoped_session(SessionLocal)
        CoreModel.query = session_scope.query_property()
        yield
        session_scope.remove()

    def test_create_then_upgrade_permission_level(self, acl, AclRule):
        """先 READ 再建 WRITE → updated，等级变为 WRITE。"""
        service = acl.get_service()
        resources = [{"resource_type": "FOLDER", "resource_id": "f1"}]

        first = service.batch_create_rules(
            resources=resources,
            subject_id="user:1",
            permission_level=10,
            effect="ALLOW",
            inherit=True,
        )
        assert len(first["created"]) == 1
        assert first["updated"] == []
        assert first["skipped"] == []
        assert first["created"][0].permission_level == 10

        second = service.batch_create_rules(
            resources=resources,
            subject_id="user:1",
            permission_level=30,
            effect="ALLOW",
            inherit=True,
        )
        assert second["created"] == []
        assert second["skipped"] == []
        assert len(second["updated"]) == 1
        assert second["updated"][0].permission_level == 30

        rules = AclRule.query.filter_by(
            subject_id="user:1",
            resource_type="FOLDER",
            resource_id="f1",
        ).all()
        assert len(rules) == 1
        assert rules[0].permission_level == 30

    def test_skip_when_identical(self, acl):
        """同等级同继承再提交 → skipped。"""
        service = acl.get_service()
        resources = [{"resource_type": "FOLDER", "resource_id": "f2"}]
        service.batch_create_rules(
            resources=resources,
            subject_id="user:2",
            permission_level=30,
        )
        again = service.batch_create_rules(
            resources=resources,
            subject_id="user:2",
            permission_level=30,
            inherit=True,
        )
        assert again["created"] == []
        assert again["updated"] == []
        assert again["skipped"] == [
            {
                "resource_type": "FOLDER",
                "resource_id": "f2",
                "reason": "duplicate",
            }
        ]

    def test_update_when_inherit_differs(self, acl):
        """等级相同但 inherit 不同 → updated。"""
        service = acl.get_service()
        resources = [{"resource_type": "FOLDER", "resource_id": "f3"}]
        service.batch_create_rules(
            resources=resources,
            subject_id="user:3",
            permission_level=20,
            inherit=True,
        )
        result = service.batch_create_rules(
            resources=resources,
            subject_id="user:3",
            permission_level=20,
            inherit=False,
        )
        assert len(result["updated"]) == 1
        assert result["updated"][0].inherit is False
        assert result["skipped"] == []
