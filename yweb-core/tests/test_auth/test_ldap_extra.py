"""ldap 模块补充测试"""

from types import SimpleNamespace

import pytest

from yweb.auth import ldap as ldap_mod
from yweb.auth.base import AuthType


class LdapValueObj:
    """LDAP 属性值封装"""

    def __init__(self, value):
        self.value = value


class LdapListValueObj:
    """LDAP 列表属性值封装"""

    def __init__(self, values):
        self.values = values


class LdapEntryObj:
    """LDAP 条目对象"""

    def __init__(self, dn: str, attrs: dict):
        self.entry_dn = dn
        self.entry_attributes_as_dict = attrs
        for k, v in attrs.items():
            if isinstance(v, list):
                setattr(self, k, LdapListValueObj(v))
            else:
                setattr(self, k, LdapValueObj(v))


class LdapConnObj:
    """LDAP 连接桩"""

    def __init__(self, entries=None):
        self.entries = entries or []
        self.server = SimpleNamespace(info="ok")
        self.unbound = False

    def search(self, **_kwargs):
        return True

    def start_tls(self):
        return True

    def unbind(self):
        self.unbound = True
        return True


class LdapManagerFixture:
    """LDAPManager 构建器"""

    @staticmethod
    def build(monkeypatch, ldap_type=ldap_mod.LDAPType.STANDARD):
        monkeypatch.setattr(ldap_mod, "LDAP3_AVAILABLE", True)
        monkeypatch.setattr(ldap_mod, "SUBTREE", "SUBTREE", raising=False)
        monkeypatch.setattr(ldap_mod, "LDAPException", Exception, raising=False)
        monkeypatch.setattr(ldap_mod, "LDAPBindError", Exception, raising=False)
        manager = ldap_mod.LDAPManager(
            server="ldap://example.com:389",
            base_dn="dc=example,dc=com",
            ldap_type=ldap_type,
        )
        return manager


class TestLdapManagerExtra:
    """LDAPManager 补充测试"""

    def test_init_active_directory_overrides_defaults(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch, ldap_type=ldap_mod.LDAPType.ACTIVE_DIRECTORY)
        assert manager.config.user_search_filter == "(sAMAccountName={username})"
        assert manager.config.attributes_mapping["username"] == "sAMAccountName"

    def test_find_user_dn_by_template(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        manager.config.user_dn_template = "uid={username},ou=users,dc=example,dc=com"
        assert manager._find_user_dn("alice") == "uid=alice,ou=users,dc=example,dc=com"

    def test_find_user_dn_from_search(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        conn = LdapConnObj(entries=[LdapEntryObj("uid=alice,ou=users,dc=example,dc=com", {})])
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: conn)
        assert manager._find_user_dn("alice") == "uid=alice,ou=users,dc=example,dc=com"

    def test_get_user_maps_attrs_and_groups(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        entry = LdapEntryObj(
            "uid=alice,ou=users,dc=example,dc=com",
            {
                "uid": "alice",
                "mail": "alice@example.com",
                "displayName": "Alice",
                "memberOf": [
                    "CN=Developers,OU=Groups,DC=example,DC=com",
                    "CN=Admins,OU=Groups,DC=example,DC=com",
                ],
            },
        )
        conn = LdapConnObj(entries=[entry])
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: conn)
        user = manager.get_user("alice")
        assert user is not None
        assert user.username == "alice"
        assert user.email == "alice@example.com"
        assert sorted(user.groups) == ["Admins", "Developers"]

    def test_search_users_and_test_connection(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        entry = LdapEntryObj("uid=bob,ou=users,dc=example,dc=com", {"uid": "bob", "mail": "bob@example.com"})
        conn = LdapConnObj(entries=[entry])
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: conn)

        users = manager.search_users("(uid=*)", limit=10)
        assert len(users) == 1
        assert users[0]["dn"].startswith("uid=bob")

        ok, msg = manager.test_connection()
        assert ok is True
        assert "Connected to" in msg

    def test_get_user_returns_none_on_ldap_exception(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(Exception("ldap down")))
        assert manager.get_user("alice") is None

    def test_parse_groups_skips_non_cn_parts(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        groups = manager._parse_groups(["OU=Users,DC=example,DC=com", "CN=Dev,OU=G,DC=example,DC=com"])
        assert groups == ["Dev"]

    def test_authenticate_user_not_found(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        monkeypatch.setattr(manager, "_find_user_dn", lambda _username: None)
        ok, msg = manager.authenticate("nouser", "pwd")
        assert ok is False
        assert msg == "User not found"

    def test_authenticate_invalid_credentials(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        monkeypatch.setattr(manager, "_find_user_dn", lambda _username: "uid=alice,dc=example,dc=com")

        class BindErr(Exception):
            pass

        monkeypatch.setattr(ldap_mod, "LDAPBindError", BindErr, raising=False)
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: (_ for _ in ()).throw(BindErr("bad")))
        ok, msg = manager.authenticate("alice", "wrong")
        assert ok is False
        assert msg == "Invalid credentials"

    def test_authenticate_success(self, monkeypatch):
        manager = LdapManagerFixture.build(monkeypatch)
        monkeypatch.setattr(manager, "_find_user_dn", lambda _username: "uid=alice,dc=example,dc=com")
        monkeypatch.setattr(manager, "_create_connection", lambda *args, **kwargs: LdapConnObj())
        monkeypatch.setattr(manager, "get_user", lambda _username: ldap_mod.LDAPUser(dn="uid=alice", username="alice", groups=["dev"]))
        ok, user = manager.authenticate("alice", "pwd")
        assert ok is True
        assert user.username == "alice"


class TestLdapAuthProviderExtra:
    """LDAPAuthProvider 补充测试"""

    def test_provider_authenticate_success_and_mapping(self):
        ldap_user = ldap_mod.LDAPUser(
            dn="uid=alice,dc=example,dc=com",
            username="alice",
            email="alice@example.com",
            display_name="Alice",
            first_name="Ali",
            last_name="Ce",
            department="IT",
            title="SE",
            groups=["Developers", "NoMapGroup"],
        )
        ldap_manager = SimpleNamespace(authenticate=lambda _u, _p: (True, ldap_user))
        provider = ldap_mod.LDAPAuthProvider(
            ldap_manager=ldap_manager,
            role_mapping={"Developers": ["dev_role"]},
            user_sync_callback=lambda _user: SimpleNamespace(id=1001),
        )
        result = provider.authenticate({"username": "alice", "password": "pwd"})
        assert result.success is True
        assert result.identity.auth_type == AuthType.LDAP
        assert result.identity.user_id == 1001
        assert "dev_role" in result.identity.roles
        assert "NoMapGroup" in result.identity.roles

    def test_provider_fail_branches_and_token_validation(self):
        ldap_manager = SimpleNamespace(authenticate=lambda _u, _p: (False, "ldap down"))
        provider = ldap_mod.LDAPAuthProvider(ldap_manager=ldap_manager)

        bad_format = provider.authenticate("not-dict")
        assert bad_format.success is False
        assert bad_format.error_code == "INVALID_CREDENTIALS"

        missing = provider.authenticate({"username": "u"})
        assert missing.success is False
        assert missing.error_code == "MISSING_CREDENTIALS"

        failed = provider.authenticate({"username": "u", "password": "p"})
        assert failed.success is False
        assert failed.error_code == "LDAP_AUTH_FAILED"

        token_result = provider.validate_token("abc")
        assert token_result.success is False
        assert token_result.error_code == "NOT_SUPPORTED"

    def test_parse_groups_and_config_helpers(self):
        groups = ldap_mod.LDAPManager._parse_groups(
            SimpleNamespace(),
            [
                "CN=Ops,OU=Groups,DC=example,DC=com",
                "CN=Admin,OU=Groups,DC=example,DC=com",
            ],
        )
        assert groups == ["Ops", "Admin"]

        openldap_cfg = ldap_mod.create_openldap_config(
            server="ldap://example.com",
            base_dn="dc=example,dc=com",
            use_tls=True,
        )
        assert openldap_cfg.ldap_type == ldap_mod.LDAPType.STANDARD
        assert openldap_cfg.use_tls is True

        ad_cfg = ldap_mod.create_active_directory_config(
            server="ldaps://ad.example.com",
            base_dn="dc=example,dc=com",
            use_ssl=True,
        )
        assert ad_cfg.ldap_type == ldap_mod.LDAPType.ACTIVE_DIRECTORY
        assert ad_cfg.attributes_mapping["username"] == "sAMAccountName"

    def test_role_mapping_deduplicates_roles(self):
        ldap_user = ldap_mod.LDAPUser(
            dn="uid=alice,dc=example,dc=com",
            username="alice",
            groups=["Dev", "Dev"],
        )
        ldap_manager = SimpleNamespace(authenticate=lambda _u, _p: (True, ldap_user))
        provider = ldap_mod.LDAPAuthProvider(
            ldap_manager=ldap_manager,
            role_mapping={"Dev": ["reader", "reader"]},
        )
        result = provider.authenticate({"username": "alice", "password": "pwd"})
        assert result.success is True
        assert sorted(result.identity.roles) == ["reader"]
