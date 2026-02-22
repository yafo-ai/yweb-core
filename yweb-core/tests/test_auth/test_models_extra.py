"""models 模块补充测试"""

from types import SimpleNamespace

import pytest

from yweb.auth.models import AbstractLoginRecord, AbstractSimpleRole, AbstractUser, RoleMixin


class QueryChainObj:
    """查询链路桩"""

    def __init__(self, first_obj=None, all_rows=None):
        self._first_obj = first_obj
        self._all_rows = all_rows or []
        self._count = len(self._all_rows)
        self.filters = []

    def filter_by(self, **kwargs):
        self.filters.append(("filter_by", kwargs))
        return self

    def filter(self, *args):
        self.filters.append(("filter", args))
        return self

    def order_by(self, *_args):
        return self

    def limit(self, _v):
        return self

    def all(self):
        return self._all_rows

    def first(self):
        return self._first_obj

    def count(self):
        return self._count

    def paginate(self, page=1, page_size=10):
        return SimpleNamespace(
            rows=self._all_rows,
            total_records=len(self._all_rows),
            page=page,
            page_size=page_size,
            total_pages=1,
            has_prev=False,
            has_next=False,
        )

    def options(self, *_args):
        return self


class UserFake:
    """用于执行 AbstractUser classmethod 的桩类"""

    query = QueryChainObj()
    created_at = SimpleNamespace(desc=lambda: "desc")
    username = SimpleNamespace(ilike=lambda _p: True)
    name = SimpleNamespace(ilike=lambda _p: True)
    email = SimpleNamespace(ilike=lambda _p: True)
    phone = SimpleNamespace(ilike=lambda _p: True)
    is_active = True
    roles = []

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.add_called = False

    def add(self, _commit):
        self.add_called = True

    def save(self):
        self.saved = True


class RoleFake:
    """用于执行 AbstractSimpleRole classmethod 的桩类"""

    query = QueryChainObj(first_obj=SimpleNamespace(code="admin"), all_rows=[SimpleNamespace(code="admin")])

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.add_called = False

    def add(self, _commit):
        self.add_called = True


class LoginRecordFake:
    """用于执行 AbstractLoginRecord classmethod 的桩类"""

    query = QueryChainObj(all_rows=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
    created_at = SimpleNamespace(desc=lambda: "desc")
    user_id = 1


class RoleMixinUser(RoleMixin):
    """RoleMixin 用例类"""

    def __init__(self, roles=None):
        self.roles = roles or []


class TestModelsExtra:
    """models 补充分支"""

    def test_abstract_user_helpers(self, monkeypatch):
        import yweb.auth.password as pwd_mod
        import yweb.auth.validators as val_mod
        import yweb.validators as common_val

        # query helpers
        UserFake.query = QueryChainObj(first_obj=SimpleNamespace(id=1), all_rows=[SimpleNamespace(id=1)])
        assert AbstractUser.get_by_username.__func__(UserFake, "alice").id == 1
        assert AbstractUser.get_by_email.__func__(UserFake, "a@example.com").id == 1
        assert AbstractUser.get_by_phone.__func__(UserFake, "13800000000").id == 1

        # create_user path
        monkeypatch.setattr(val_mod.UsernameValidator, "validate_or_raise", lambda _u: None)
        monkeypatch.setattr(val_mod.PasswordValidator, "validate_or_raise", lambda _p: None)
        monkeypatch.setattr(common_val, "is_valid_email", lambda _e: True)
        monkeypatch.setattr(common_val, "is_valid_phone", lambda _p: True)
        monkeypatch.setattr(pwd_mod.PasswordHelper, "hash", lambda p: f"h:{p}")

        user = AbstractUser.create_user.__func__(
            UserFake,
            username="alice",
            password="Passw0rd!",
            email="alice@example.com",
            phone="13800000000",
            name="Alice",
        )
        assert user.username == "alice"
        assert user.password_hash == "h:Passw0rd!"
        assert user.add_called is True

        # invalid email / phone
        monkeypatch.setattr(common_val, "is_valid_email", lambda _e: False)
        with pytest.raises(ValueError):
            AbstractUser.create_user.__func__(UserFake, "u1", "p1", email="bad")

        monkeypatch.setattr(common_val, "is_valid_email", lambda _e: True)
        monkeypatch.setattr(common_val, "is_valid_phone", lambda _p: False)
        with pytest.raises(ValueError):
            AbstractUser.create_user.__func__(UserFake, "u2", "p2", phone="bad")

        # search helpers
        UserFake.query = QueryChainObj(all_rows=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
        UserFake._build_search_query = classmethod(AbstractUser._build_search_query.__func__)
        page = AbstractUser.search.__func__(UserFake, keyword="a", is_active=True, page=1, page_size=10)
        assert page.total_records == 2

        class UserNoRoles:
            query = QueryChainObj(all_rows=[SimpleNamespace(id=1), SimpleNamespace(id=2)])
            created_at = SimpleNamespace(desc=lambda: "desc")
            username = SimpleNamespace(ilike=lambda _p: True)
            name = SimpleNamespace(ilike=lambda _p: True)
            email = SimpleNamespace(ilike=lambda _p: True)
            phone = SimpleNamespace(ilike=lambda _p: True)
            is_active = True
            _build_search_query = classmethod(AbstractUser._build_search_query.__func__)

        page2 = AbstractUser.search_with_roles.__func__(UserNoRoles, role_code="admin", page=1, page_size=10)
        assert page2.total_records == 2

    def test_abstract_simple_role_and_login_record_helpers(self):
        role = AbstractSimpleRole.get_by_code.__func__(RoleFake, "admin")
        assert role.code == "admin"
        all_roles = AbstractSimpleRole.list_all.__func__(RoleFake)
        assert len(all_roles) == 1
        new_role = AbstractSimpleRole.create_role.__func__(RoleFake, "管理员", "admin", "desc")
        assert new_role.code == "admin"
        assert new_role.add_called is True

        # login record classmethods
        rec = SimpleNamespace(add=lambda _commit: None)
        created = AbstractLoginRecord.create_record.__func__(LoginRecordFake, rec)
        assert created is rec
        assert len(AbstractLoginRecord.get_recent_logins.__func__(LoginRecordFake, limit=5)) == 2
        assert len(AbstractLoginRecord.get_user_logins.__func__(LoginRecordFake, user_id=1, limit=5)) == 2
        assert AbstractLoginRecord.count_records.__func__(LoginRecordFake) == 2

    def test_role_mixin_methods(self):
        admin = SimpleNamespace(code="admin")
        user = SimpleNamespace(code="user")
        obj = RoleMixinUser(roles=[admin, user])
        assert obj.has_role("admin") is True
        assert obj.has_any_role("guest", "admin") is True
        assert obj.has_all_roles("admin", "user") is True
        assert obj.role_codes == {"admin", "user"}

        guest = SimpleNamespace(code="guest")
        obj.add_role(guest)
        assert obj.has_role("guest") is True
        obj.remove_role(guest)
        assert obj.has_role("guest") is False

    def test_role_mixin_handles_missing_roles_gracefully(self):
        """测试 roles 缺失时 RoleMixin 方法行为"""
        obj = RoleMixinUser(roles=None)
        obj.roles = None
        assert obj.has_role("admin") is False
        assert obj.has_any_role("admin", "user") is False
        assert obj.has_all_roles("admin") is False
        assert obj.role_codes == set()

        # roles 为 None 时 add/remove 不应抛异常
        obj.add_role(SimpleNamespace(code="admin"))
        obj.remove_role(SimpleNamespace(code="admin"))
