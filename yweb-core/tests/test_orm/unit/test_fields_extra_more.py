"""fields 额外分支测试（新文件）"""

from types import SimpleNamespace

from sqlalchemy import BigInteger, Integer, String

import yweb.orm.fields as fields_mod
from yweb.orm.fields import (
    DO_NOTHING,
    DELETE,
    HasMany,
    HasOne,
    ManyToMany,
    OnDelete,
    _find_has_many_backref_name,
    _find_has_one_backref_name,
    _get_fk_column_type,
    _get_on_delete_enum,
)
from yweb.orm.primary_key_config import IdType


class ParentModel:
    __tablename__ = "parent_models"


class ChildModel:
    __tablename__ = "child_models"


class TestFieldsExtraMore:
    def test_many_to_many_related_name_and_on_delete_enum(self):
        cfg = ManyToMany(ParentModel, related_name="members")
        assert cfg.backref == "members"

        assert _get_on_delete_enum(OnDelete.DELETE) == OnDelete.DELETE
        assert _get_on_delete_enum("set_null") == OnDelete.SET_NULL
        assert _get_on_delete_enum("unknown-x") == OnDelete.DO_NOTHING
        assert _get_on_delete_enum(123) == OnDelete.DO_NOTHING

    def test_fk_column_type_by_pk_strategy(self, monkeypatch):
        monkeypatch.setattr("yweb.orm.primary_key_config.PrimaryKeyConfig.get_short_uuid_length", lambda: 12)
        monkeypatch.setattr("yweb.orm.primary_key_config.PrimaryKeyConfig.get_strategy", lambda: IdType.AUTO_INCREMENT)

        class M1:
            __pk_strategy__ = IdType.AUTO_INCREMENT

        class M2:
            __pk_strategy__ = IdType.UUID

        class M3:
            __pk_strategy__ = IdType.SHORT_UUID

        class M4:
            __pk_strategy__ = IdType.SNOWFLAKE

        class M5:
            __pk_strategy__ = IdType.CUSTOM

        assert _get_fk_column_type(M1) is Integer
        assert isinstance(_get_fk_column_type(M2), String)
        short = _get_fk_column_type(M3)
        assert isinstance(short, String) and short.length == 14
        assert _get_fk_column_type(M4) is BigInteger
        custom = _get_fk_column_type(M5)
        assert isinstance(custom, String) and custom.length == 64

        class M6:
            __pk_strategy__ = "other"

        assert _get_fk_column_type(M6) is Integer

    def test_find_backref_name_paths_and_exceptions(self, monkeypatch):
        class ParentA:
            items: HasMany[ChildModel]
            profile: HasOne[ChildModel]

        assert _find_has_many_backref_name(ParentA, ChildModel) == "items"
        assert _find_has_one_backref_name(ParentA, ChildModel) == "profile"

        # get_type_hints 抛错，走 __annotations__ 字符串分支
        monkeypatch.setattr(fields_mod, "get_type_hints", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("x")))

        class ParentB:
            __annotations__ = {
                "children": "HasMany[ChildModel]",
                "profile": "HasOne[ChildModel]",
                "_private": "HasMany[ChildModel]",
            }

        assert _find_has_many_backref_name(ParentB, ChildModel) == "children"
        assert _find_has_one_backref_name(ParentB, ChildModel) == "profile"

        class ParentC:
            __annotations__ = {"x": int}

        assert _find_has_many_backref_name(ParentC, ChildModel) is None
        assert _find_has_one_backref_name(ParentC, ChildModel) is None

    def test_process_many_to_many_custom_backref_branch(self, monkeypatch):
        # 仅覆盖 802-804 分支：custom backref
        source = SimpleNamespace(__tablename__="users")
        target = SimpleNamespace(__tablename__="roles")
        cfg = SimpleNamespace(
            target_model=target,
            on_delete=DELETE,
            backref="members",
            table_name="u_roles",
            kwargs={},
            related_name=None,
        )

        fake_base = SimpleNamespace(metadata=SimpleNamespace(tables={"u_roles": object()}))
        monkeypatch.setattr(fields_mod, "relationship", lambda *a, **k: ("REL", a, k))
        monkeypatch.setattr(fields_mod, "sa_backref", lambda name, info=None: ("BACKREF", name, info))

        fields_mod._process_many_to_many(source, "roles", cfg, fake_base)
        assert getattr(source, "roles")[0] == "REL"
        assert getattr(source, "roles")[2]["backref"][1] == "members"
        assert getattr(source, "roles")[2]["backref"][2]

        # 顺带覆盖便捷常量路径
        assert DO_NOTHING == OnDelete.DO_NOTHING
