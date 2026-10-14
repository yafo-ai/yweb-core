"""setup_acl get_current_user_func 透传测试

验证 setup_acl 的 get_current_user_func 参数能正确透传到 dependencies 模块，
使权限检查端点的身份解析可用。
"""

import pytest

from yweb.acl.dependencies import (
    init_acl_dependency,
    resolve_identities_for_target,
    get_acl_service,
    get_identity_provider,
)
from yweb.acl.exceptions import AclException


class SimpleUser:
    """测试用户对象"""
    def __init__(self, id, name="user"):
        self.id = id
        self.name = name


class SimpleIdentityProvider:
    """测试用 IdentityProvider"""
    def get_identities(self, user) -> set[str]:
        return {"everyone", f"user:{user.id}"}


class TestSetupAclUserFunc:
    """setup_acl / init_acl_dependency 的 get_current_user_func 透传"""

    @pytest.fixture(autouse=True)
    def reset_globals(self):
        """每个测试前重置全局状态"""
        import yweb.acl.dependencies as deps
        old_service = deps._acl_service
        old_provider = deps._identity_provider
        old_func = deps._get_current_user_func
        yield
        deps._acl_service = old_service
        deps._identity_provider = old_provider
        deps._get_current_user_func = old_func

    def test_resolve_fails_without_user_func(self):
        """未配置 get_current_user_func 时调用 resolve_identities_for_target 应抛异常"""
        init_acl_dependency(
            acl_service="fake_service",
            identity_provider=SimpleIdentityProvider(),
            get_current_user_func=None,
        )

        with pytest.raises(AclException, match="get_current_user_func not configured"):
            resolve_identities_for_target()

    def test_resolve_works_with_user_func(self):
        """配置 get_current_user_func 后 resolve_identities_for_target 正常工作"""
        users = {
            None: SimpleUser(id=1, name="current"),
            1: SimpleUser(id=1, name="current"),
            2: SimpleUser(id=2, name="target"),
        }

        def get_user(uid=None):
            return users[uid]

        init_acl_dependency(
            acl_service="fake_service",
            identity_provider=SimpleIdentityProvider(),
            get_current_user_func=get_user,
        )

        identities = resolve_identities_for_target(target_user_id=None)
        assert "user:1" in identities
        assert "everyone" in identities

        identities_target = resolve_identities_for_target(target_user_id=2)
        assert "user:2" in identities_target
        assert "everyone" in identities_target

    def test_setup_acl_passes_user_func_through(self):
        """setup_acl 的 get_current_user_func 参数透传到 dependencies"""
        from yweb.acl.factory import create_acl_models
        import yweb.acl.dependencies as deps

        acl = create_acl_models(table_prefix="test_func_")

        def my_get_user(uid=None):
            return SimpleUser(id=uid or 99)

        acl.init_dependency(
            identity_provider=SimpleIdentityProvider(),
            get_current_user_func=my_get_user,
        )

        assert deps._get_current_user_func is my_get_user, (
            "init_dependency 应将 get_current_user_func 透传到 dependencies 模块"
        )

        identities = resolve_identities_for_target(target_user_id=42)
        assert "user:42" in identities

    def test_get_acl_service_raises_without_init(self):
        """未初始化时 get_acl_service 抛异常"""
        import yweb.acl.dependencies as deps
        deps._acl_service = None

        with pytest.raises(AclException, match="AclService not configured"):
            get_acl_service()

    def test_get_identity_provider_raises_without_init(self):
        """未初始化时 get_identity_provider 抛异常"""
        import yweb.acl.dependencies as deps
        deps._identity_provider = None

        with pytest.raises(AclException, match="IdentityProvider not configured"):
            get_identity_provider()
