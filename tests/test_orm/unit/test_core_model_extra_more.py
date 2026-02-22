"""core_model 额外分支测试（新文件）"""

from types import SimpleNamespace

import pytest

import yweb.orm.core_model as core_mod
from yweb.orm.core_model import CoreModel


class QueryChain:
    def __init__(self, count_value=0, first_obj=None, rows=None):
        count_query = SimpleNamespace(
            filter=lambda *a, **k: SimpleNamespace(
                filter=lambda *a2, **k2: SimpleNamespace(scalar=lambda: 0),
                scalar=lambda: 0,
            ),
            scalar=lambda: 0,
        )
        self._count = count_value
        self._first = first_obj
        self._rows = list(rows or [])
        self.session = SimpleNamespace(
            execute=lambda stmt: SimpleNamespace(rowcount=3),
            refresh=lambda obj, attrs=None: None,
            query=lambda *a, **k: count_query,
            commit=lambda: None,
        )

    def filter_by(self, **kwargs):
        _ = kwargs
        return self

    def filter(self, *args, **kwargs):
        _ = (args, kwargs)
        return self

    def count(self):
        return self._count

    def first(self):
        return self._first

    def all(self):
        return list(self._rows)

    def offset(self, n):
        _ = n
        return self

    def limit(self, n):
        _ = n
        return self


class ExprField:
    def __init__(self, name):
        self.name = name

    def in_(self, ids):
        return (self.name, "in", ids)

    def isnot(self, val):
        return (self.name, "isnot", val)

    def __lt__(self, other):
        return (self.name, "lt", other)

    def __eq__(self, other):
        return (self.name, "eq", other)


class DummyCls:
    __name__ = "DummyCls"
    __tablename__ = "dummy_cls"
    query = QueryChain()
    id = ExprField("id")
    deleted_at = ExprField("deleted_at")

    @classmethod
    def _cls_should_suppress_commit(cls):
        return False

    _CoreModel__cls_commit = classmethod(lambda cls, commit=False: None)

    @classmethod
    def bulk_update(cls, filters, values, commit=False):
        return CoreModel.bulk_update.__func__(cls, filters, values, commit=commit)

    @classmethod
    def bulk_update_by_ids(cls, ids, values, commit=False):
        return CoreModel.bulk_update_by_ids.__func__(cls, ids, values, commit=commit)

    @classmethod
    def cleanup_soft_deleted(cls, days=None, commit=False):
        return CoreModel.cleanup_soft_deleted.__func__(cls, days=days, commit=commit)


class TestCoreModelExtraMore:
    def test_get_update_refresh_and_history_guards(self):
        # get: count>1 / 0 / 1
        DummyCls.query = QueryChain(count_value=2, first_obj=None)
        with pytest.raises(ValueError):
            CoreModel.get.__func__(DummyCls, 1)
        DummyCls.query = QueryChain(count_value=0, first_obj=None)
        assert CoreModel.get.__func__(DummyCls, 1) is None
        one = SimpleNamespace(id=1)
        DummyCls.query = QueryChain(count_value=1, first_obj=one)
        assert CoreModel.get.__func__(DummyCls, 1) is one
        assert CoreModel.get_list_by_conditions.__func__(DummyCls, {"x": 1}) == []

        # update_all kwargs 分支 + 空列表分支
        o1 = SimpleNamespace(name="a")
        o2 = SimpleNamespace(name="b")
        assert CoreModel.update_all.__func__(DummyCls, [], commit=False) == []
        rows = CoreModel.update_all.__func__(DummyCls, [o1, o2], name="n", commit=False)
        assert rows[0].name == "n"

        # refresh / refresh_all 分支
        s = DummyCls.query.session
        obj = SimpleNamespace(session=s)
        CoreModel.refresh(obj, attribute_names=["name"])
        CoreModel.refresh(obj, attribute_names=None)
        assert CoreModel.refresh_all.__func__(DummyCls, [], attribute_names=None) == []
        CoreModel.refresh_all.__func__(DummyCls, [SimpleNamespace()], attribute_names=["x"])

        # history guard 分支
        inst = SimpleNamespace(__class__=SimpleNamespace(__name__="X", enable_history=False))
        with pytest.raises(AttributeError):
            CoreModel._check_history_enabled(inst)
        with pytest.raises(AttributeError):
            CoreModel.get_history_by_id.__func__(SimpleNamespace(__name__="Y", enable_history=False), 1)
        with pytest.raises(AttributeError):
            CoreModel.get_history_count_by_id.__func__(SimpleNamespace(__name__="Y", enable_history=False), 1)

    def test_to_dict_relations_detach_and_paginate_typeerror(self, monkeypatch):
        class Attr:
            def __init__(self, key):
                self.key = key

        # to_dict_with_relations 分支
        class RelObj:
            def __init__(self):
                self.id = 1
                self.name = "n"
                self.rel_list = [SimpleNamespace(to_dict=lambda exclude=None: {"a": 1}), 2]
                self.rel_obj = SimpleNamespace(to_dict=lambda exclude=None: {"b": 2})
                self.rel_other = "x"

            def to_dict(self, exclude=None):
                return CoreModel.to_dict(self, exclude=exclude)

        obj = RelObj()
        monkeypatch.setattr(core_mod, "inspect", lambda x, **k: SimpleNamespace(mapper=SimpleNamespace(column_attrs=[Attr("id"), Attr("name")])))
        data = CoreModel.to_dict_with_relations(obj, relations=["rel_list", "rel_obj", "rel_other", "none_rel"])
        assert data["rel_list"][0]["a"] == 1
        assert data["rel_obj"]["b"] == 2
        assert data["none_rel"] is None

        # detach / detach_with_relations 分支
        expunged = {"n": 0}
        monkeypatch.setattr("sqlalchemy.orm.make_transient_to_detached", lambda x: None)
        monkeypatch.setattr("sqlalchemy.orm.session.object_session", lambda x: SimpleNamespace(expunge=lambda y: expunged.__setitem__("n", expunged["n"] + 1)))
        monkeypatch.setattr(core_mod, "inspect", lambda x, **k: SimpleNamespace(mapper=SimpleNamespace(column_attrs=[Attr("id"), Attr("name")])))
        det_obj = SimpleNamespace(id=1, name="a")
        CoreModel.detach(det_obj)
        assert expunged["n"] == 1

        rel_item = SimpleNamespace(detach=lambda: None)
        det_obj2 = SimpleNamespace(detach=lambda: None, items=[rel_item], profile=SimpleNamespace(detach=lambda: None))
        CoreModel.detach_with_relations(det_obj2, relations=["items", "profile"])

        with pytest.raises(TypeError):
            CoreModel.paginate.__func__(DummyCls, object())

    def test_bulk_ops_cleanup_and_event_handlers(self, monkeypatch):
        # bulk 系列
        monkeypatch.setattr(core_mod, "update", lambda cls: SimpleNamespace(where=lambda *a, **k: SimpleNamespace(where=lambda *a2, **k2: SimpleNamespace(values=lambda **v: "stmt"), values=lambda **v: "stmt"), values=lambda **v: "stmt"))
        monkeypatch.setattr(
            core_mod,
            "delete",
            lambda cls: SimpleNamespace(where=lambda *a, **k: SimpleNamespace(where=lambda *a2, **k2: "stmt")),
        )

        assert CoreModel.bulk_update.__func__(DummyCls, {"id": 1}, {"name": "x"}, commit=False) == 3
        assert CoreModel.bulk_update_by_ids.__func__(DummyCls, [], {"name": "x"}, commit=False) == 0
        assert CoreModel.bulk_update_by_ids.__func__(DummyCls, [1], {"name": "x"}, commit=False) == 3
        assert CoreModel.bulk_delete.__func__(DummyCls, {"id": 1}, commit=False) == 3
        assert CoreModel.bulk_delete_by_ids.__func__(DummyCls, [], commit=False) == 0
        assert CoreModel.bulk_delete_by_ids.__func__(DummyCls, [1], commit=False) == 3
        assert CoreModel.bulk_soft_delete.__func__(DummyCls, {"id": 1}, commit=False) == 3
        assert CoreModel.bulk_soft_delete_by_ids.__func__(DummyCls, [1], commit=False) == 3
        assert CoreModel.cleanup_soft_deleted.__func__(DummyCls, days=1, commit=False) == 3
        assert isinstance(CoreModel.cleanup_all_soft_deleted.__func__(DummyCls, days=1, commit=False), dict)
        assert CoreModel.get_soft_deleted_count.__func__(DummyCls, days=1) == 0

        # commit 抑制分支
        class NoCommit:
            query = QueryChain()
            _cls_should_suppress_commit = classmethod(lambda cls: True)

        CoreModel._CoreModel__cls_commit.__func__(NoCommit, commit=True)

        # event_before_delete 分支
        target = SimpleNamespace(__class__=SimpleNamespace(__name__="T"))
        monkeypatch.setattr(core_mod, "inspect", lambda c, **k: SimpleNamespace(relationships={"r": SimpleNamespace(cascade=SimpleNamespace(delete_orphan=False))}))
        core_mod.event_before_delete(None, None, target)
        assert target.deleted_at is not None

        monkeypatch.setattr(core_mod, "inspect", lambda c, **k: SimpleNamespace(relationships={"r": SimpleNamespace(cascade=SimpleNamespace(delete_orphan=True))}))
        with pytest.raises(Exception):
            core_mod.event_before_delete(None, None, target)
