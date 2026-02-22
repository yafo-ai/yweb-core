"""db_session 额外分支测试（新文件）"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

import yweb.orm.db_session as dbs


class SessionStub:
    def __init__(self, commit_error=None, rollback_error=None):
        self.dirty = {1}
        self.new = set()
        self.deleted = set()
        self.commit_called = 0
        self.rollback_called = 0
        self.commit_error = commit_error
        self.rollback_error = rollback_error

    def commit(self):
        self.commit_called += 1
        if self.commit_error:
            raise self.commit_error

    def rollback(self):
        self.rollback_called += 1
        if self.rollback_error:
            raise self.rollback_error


class SessionScopeStub:
    def __init__(self, session=None, has_session=True):
        self._session = session or SessionStub()
        self.removed = 0
        self.registry = SimpleNamespace(has=lambda: has_session)

    def __call__(self):
        return self._session

    def remove(self):
        self.removed += 1

    def query_property(self):
        return None


class QueryStub:
    def __init__(self):
        self.session = SessionStub()


class TestDbSessionExtraMore:
    def test_manager_properties_and_singleton(self):
        m1 = dbs.DatabaseManager()
        m2 = dbs.DatabaseManager()
        assert m1 is m2

        m1._engine = None
        m1._session_scope = None
        with pytest.raises(RuntimeError):
            _ = m1.engine
        with pytest.raises(RuntimeError):
            _ = m1.session_scope
        assert m1.is_initialized is False

    def test_init_param_extraction_and_create_engine_failures(self, monkeypatch):
        m = dbs.DatabaseManager()
        m._engine = None
        m._session_scope = None

        with pytest.raises(ValueError):
            m.init(database_url=None)

        fake_logger = SimpleNamespace(info=lambda *a, **k: None, error=lambda *a, **k: None)
        cfg = SimpleNamespace(
            url="sqlite:///:memory:",
            echo=True,
            pool_size=1,
            max_overflow=1,
            pool_timeout=2,
            pool_recycle=3,
            pool_pre_ping=True,
        )
        log_cfg = SimpleNamespace(sql_log_enabled=True)

        # create_engine 失败分支（sqlite）
        monkeypatch.setattr(dbs, "create_engine", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
        with pytest.raises(RuntimeError):
            m.init(config=cfg, logging_config=log_cfg, logger=fake_logger)

        # 非 sqlite 分支失败
        cfg2 = SimpleNamespace(url="postgresql://u:p@h/db")
        with pytest.raises(RuntimeError):
            m.init(config=cfg2, logger=fake_logger)

    def test_get_session_cleanup_and_request_id_lock(self):
        m = dbs.DatabaseManager()
        m._session_scope = None
        with pytest.raises(RuntimeError):
            m.get_session()

        # 正常获取 session 会锁定 request_id
        m._request_id_var.set("")
        m._request_id_explicit.set(False)
        m._session_scope = SessionScopeStub()
        s = m.get_session()
        assert s is not None
        assert m._request_id_explicit.get() is True

        # cleanup: commit 失败 + rollback 失败分支
        bad_session = SessionStub(commit_error=RuntimeError("c"), rollback_error=RuntimeError("r"))
        m._session_scope = SessionScopeStub(session=bad_session, has_session=True)
        m.cleanup()
        assert m._session_scope.removed == 1
        assert bad_session.commit_called == 1
        assert bad_session.rollback_called == 1

        # cleanup: 无活跃 session 分支
        m._session_scope = SessionScopeStub(has_session=False)
        m.cleanup()

        # request_id 已锁定分支
        m._request_id_var.set("locked")
        m._request_id_explicit.set(True)
        assert m._set_request_id("new-id") == "locked"

    def test_public_wrappers_get_db_and_db_session_scope(self, monkeypatch):
        # get_engine wrapper
        dbs.db_manager._engine = "E"
        assert dbs.get_engine() == "E"

        # get_db wrapper
        original_scope = dbs.db_session_scope

        @contextmanager
        def fake_scope():
            yield "SESSION-X"

        monkeypatch.setattr(dbs, "db_session_scope", fake_scope)
        with dbs.get_db() as s:
            assert s == "SESSION-X"
        monkeypatch.setattr(dbs, "db_session_scope", original_scope)

        # db_session_scope 异常分支（rollback）
        calls = {"end": 0}
        sess = SessionStub()
        monkeypatch.setattr(dbs.db_manager, "_set_request_id", lambda rid=None: rid or "rid")
        monkeypatch.setattr(dbs.db_manager, "get_session", lambda: sess)
        monkeypatch.setattr(dbs, "on_request_end", lambda: calls.__setitem__("end", calls["end"] + 1))

        with pytest.raises(RuntimeError):
            with dbs.db_session_scope(request_id="r1", auto_commit=True):
                raise RuntimeError("x")
        assert sess.rollback_called == 1
        assert calls["end"] == 1

    def test_with_db_session_sync_and_async(self, monkeypatch):
        calls = {"end": 0, "rid": []}
        sess = SessionStub()

        monkeypatch.setattr(dbs.db_manager, "_set_request_id", lambda rid=None: calls["rid"].append(rid))
        monkeypatch.setattr(dbs.db_manager, "get_session", lambda: sess)
        monkeypatch.setattr(dbs, "on_request_end", lambda: calls.__setitem__("end", calls["end"] + 1))

        @dbs.with_db_session(request_id="sync-{rand}", auto_commit=True)
        def fn(session, x):
            assert session is sess
            return x + 1

        assert fn(1) == 2
        assert sess.commit_called == 1
        assert calls["end"] >= 1
        assert calls["rid"][-1].startswith("sync-")

        @dbs.with_db_session(request_id="async-{rand}", auto_commit=False)
        async def afn(session, x):
            assert session is sess
            return x + 2
        import asyncio

        result = asyncio.run(afn(3))
        assert result == 5
