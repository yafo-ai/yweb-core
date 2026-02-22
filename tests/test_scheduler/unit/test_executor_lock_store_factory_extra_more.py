"""调度器低覆盖模块补充测试。"""

from __future__ import annotations

import pickle
import threading
import time
from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from apscheduler.jobstores.base import ConflictingIdError, JobLookupError

import yweb.scheduler.stores.orm as orm_mod
from yweb.scheduler.executors.thread_executor import ThreadExecutor
from yweb.scheduler.factory import create_scheduler_models, setup_scheduler
from yweb.scheduler.locks.base import DistributedLock
from yweb.scheduler.locks.redis_lock import (
    MemoryLock,
    RedisDistributedLock,
    create_distributed_lock,
)
from yweb.scheduler.stores.base import BaseStore
from yweb.scheduler.stores.memory import MemoryStore
from yweb.scheduler.stores.orm import ORMJobStore


class _QueryChain:
    def __init__(self, rows=None, first_item=None):
        self._rows = list(rows or [])
        self._first_item = first_item

    def filter(self, *_args, **_kwargs):
        return self

    def order_by(self, *_args, **_kwargs):
        return self

    def all(self):
        return list(self._rows)

    def first(self):
        if self._first_item is not None:
            return self._first_item
        return self._rows[0] if self._rows else None


class _ExprField:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return (self.name, "==", other)

    def __le__(self, other):
        return (self.name, "<=", other)

    def __ne__(self, other):
        return (self.name, "!=", other)


class _JobModelStub:
    code = _ExprField("code")
    next_run_time = _ExprField("next_run_time")
    is_enabled = _ExprField("is_enabled")
    query = _QueryChain()
    created = []

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.kwargs = kwargs.get("kwargs", {})
        self.deleted = False
        self.saved = False

    def save(self):
        self.saved = True
        type(self).created.append(self)

    def delete(self):
        self.deleted = True


class _APJobStub:
    def __init__(self, job_id="yweb_demo", trigger=None):
        self.id = job_id
        self.name = "demo"
        self.trigger = trigger or SimpleNamespace(__class__=SimpleNamespace(__name__="Unknown"))
        self.func = lambda: None
        self.args = (1, 2)
        self.kwargs = {"a": 1}
        self.executor = "default"
        self.max_instances = 2
        self.misfire_grace_time = 5
        self.coalesce = True
        self.next_run_time = datetime.now()

    def __getstate__(self):
        return {"id": self.id, "x": 1}


class _RedisClientStub:
    def __init__(self):
        self.set_result = True
        self.eval_result = 1
        self.get_result = b""
        self.raise_on_set = False
        self.raise_on_eval = False
        self.raise_on_get = False
        self.closed = False

    async def set(self, *_args, **_kwargs):
        if self.raise_on_set:
            raise RuntimeError("set error")
        return self.set_result

    async def eval(self, *_args, **_kwargs):
        if self.raise_on_eval:
            raise RuntimeError("eval error")
        return self.eval_result

    async def get(self, *_args, **_kwargs):
        if self.raise_on_get:
            raise RuntimeError("get error")
        return self.get_result

    async def close(self):
        self.closed = True


class _StoreImpl(BaseStore):
    def add_job(self, job):
        return BaseStore.add_job(self, job)

    def update_job(self, job):
        return BaseStore.update_job(self, job)

    def remove_job(self, job_id):
        return BaseStore.remove_job(self, job_id)

    def lookup_job(self, job_id):
        return BaseStore.lookup_job(self, job_id)

    def get_all_jobs(self):
        return BaseStore.get_all_jobs(self)

    def get_due_jobs(self, now):
        return BaseStore.get_due_jobs(self, now)

    def get_next_run_time(self):
        return BaseStore.get_next_run_time(self)


class _LockImpl(DistributedLock):
    async def acquire(self, key: str, timeout: int) -> bool:
        return await DistributedLock.acquire(self, key, timeout)

    async def release(self, key: str) -> bool:
        return await DistributedLock.release(self, key)

    async def extend(self, key: str, timeout: int) -> bool:
        return await DistributedLock.extend(self, key, timeout)


class TestThreadExecutorExtra:
    """ThreadExecutor 边界行为测试。"""

    def test_submit_execute_and_shutdown(self):
        executor = ThreadExecutor(max_workers=1, max_instances=1)
        future = executor.submit(lambda x: x + 1, 2, job_id="A")
        assert future.result(timeout=1) == 3
        assert executor.get_running_count("A") == 0

        assert executor.execute(lambda: "ok") == "ok"
        executor.shutdown(wait=True)
        assert executor._executor is None

    def test_max_instances_blocked(self):
        signal = threading.Event()
        executor = ThreadExecutor(max_workers=1, max_instances=1)

        def hold():
            signal.wait(0.5)
            return "done"

        first = executor.submit(hold, job_id="same")
        second = executor.submit(lambda: "x", job_id="same")
        assert second is None

        signal.set()
        assert first.result(timeout=2) == "done"
        executor.shutdown(wait=True)

    def test_execute_returns_none_when_submit_none(self, monkeypatch):
        executor = ThreadExecutor()
        monkeypatch.setattr(executor, "submit", lambda *_a, **_k: None)
        assert executor.execute(lambda: 1) is None


class TestBaseContractsExtra:
    """抽象基类默认分支覆盖。"""

    @pytest.mark.asyncio
    async def test_distributed_lock_abstract_methods(self):
        impl = _LockImpl()
        assert await impl.acquire("k", 1) is None
        assert await impl.release("k") is None
        assert await impl.extend("k", 1) is None

    def test_store_abstract_methods(self):
        impl = _StoreImpl()
        assert impl.add_job(SimpleNamespace()) is None
        assert impl.update_job(SimpleNamespace()) is None
        assert impl.remove_job("x") is None
        assert impl.lookup_job("x") is None
        assert impl.get_all_jobs() is None
        assert impl.get_due_jobs(datetime.now()) is None
        assert impl.get_next_run_time() is None


class TestMemoryStoreExtra:
    """MemoryStore 分支补测。"""

    def test_crud_due_and_next_run(self):
        store = MemoryStore()
        now = datetime.now()
        j1 = SimpleNamespace(id="j1", next_run_time=now + timedelta(seconds=2))
        j2 = SimpleNamespace(id="j2", next_run_time=now - timedelta(seconds=1))
        j3 = SimpleNamespace(id="j3", next_run_time=None)
        store.add_job(j1)
        store.add_job(j2)
        store.add_job(j3)

        due = store.get_due_jobs(now)
        assert [j.id for j in due] == ["j2"]
        assert store.get_next_run_time() == j2.next_run_time
        assert store.lookup_job("missing") is None

        j2_new = SimpleNamespace(id="j2", next_run_time=now + timedelta(seconds=10))
        store.update_job(j2_new)
        assert store.lookup_job("j2").next_run_time == j2_new.next_run_time

        with pytest.raises(KeyError):
            store.update_job(SimpleNamespace(id="nope", next_run_time=now))

        store.remove_job("j1")
        store.remove_job("missing")
        assert len(store.get_all_jobs()) == 2
        store.remove_all_jobs()
        assert store.get_all_jobs() == []
        assert store.get_next_run_time() is None


class TestRedisLockExtra:
    """RedisDistributedLock 分支补测。"""

    @pytest.mark.asyncio
    async def test_acquire_release_extend_is_held_and_close(self, monkeypatch):
        lock = RedisDistributedLock("redis://demo")
        client = _RedisClientStub()
        lock._redis = client
        monkeypatch.setattr(lock, "_get_lock_value", lambda: "LOCK-VALUE")

        assert await lock.acquire("task", timeout=10) is True
        assert lock._lock_values["task"] == "LOCK-VALUE"

        client.set_result = False
        assert await lock.acquire("task2", timeout=10) is False

        client.raise_on_set = True
        assert await lock.acquire("task3", timeout=10) is False
        client.raise_on_set = False

        assert await lock.release("not-held") is False
        lock._lock_values["task"] = "LOCK-VALUE"
        client.eval_result = 1
        assert await lock.release("task") is True
        assert "task" not in lock._lock_values

        lock._lock_values["task"] = "LOCK-VALUE"
        client.eval_result = 0
        assert await lock.release("task") is False

        client.raise_on_eval = True
        assert await lock.release("task") is False
        client.raise_on_eval = False

        assert await lock.extend("not-held", timeout=20) is False
        lock._lock_values["task"] = "LOCK-VALUE"
        client.eval_result = 1
        assert await lock.extend("task", timeout=20) is True
        client.eval_result = 0
        assert await lock.extend("task", timeout=20) is False
        client.raise_on_eval = True
        assert await lock.extend("task", timeout=20) is False
        client.raise_on_eval = False

        assert await lock.is_held("none") is False
        lock._lock_values["task"] = "LOCK-VALUE"
        client.get_result = b"LOCK-VALUE"
        assert await lock.is_held("task") is True
        client.get_result = b"OTHER"
        assert await lock.is_held("task") is False
        client.raise_on_get = True
        assert await lock.is_held("task") is False

        await lock.close()
        assert client.closed is True
        assert lock._redis is None

    @pytest.mark.asyncio
    async def test_lock_context_manager_release_called(self, monkeypatch):
        lock = RedisDistributedLock("redis://demo")
        called = {"release": 0}

        async def fake_acquire(_key, _timeout):
            return True

        async def fake_release(_key):
            called["release"] += 1
            return True

        monkeypatch.setattr(lock, "acquire", fake_acquire)
        monkeypatch.setattr(lock, "release", fake_release)

        async with lock.lock("ctx", timeout=1) as acquired:
            assert acquired is True
        assert called["release"] == 1

    @pytest.mark.asyncio
    async def test_memory_lock_expire_and_factory(self):
        lock = MemoryLock()
        assert await lock.acquire("k", timeout=0) is True
        time.sleep(0.01)
        assert await lock.acquire("k", timeout=1) is True
        assert isinstance(create_distributed_lock(), MemoryLock)
        assert isinstance(create_distributed_lock(redis_url="redis://x"), RedisDistributedLock)


class TestOrmStoreExtra:
    """ORMJobStore 分支补测。"""

    def test_job_model_property_and_lookup_paths(self, monkeypatch):
        store = ORMJobStore(job_model=None)
        with pytest.raises(RuntimeError):
            _ = store.job_model

        _JobModelStub.query = _QueryChain(rows=[SimpleNamespace(code="demo", kwargs={})])
        store = ORMJobStore(job_model=_JobModelStub)
        monkeypatch.setattr(store, "_reconstitute_job", lambda record: f"job:{record.code}")
        assert store.lookup_job("yweb_demo") == "job:demo"

        _JobModelStub.query = _QueryChain(rows=[])
        assert store.lookup_job("missing") is None

    def test_get_due_next_all_and_remove_all(self, monkeypatch):
        now = datetime.now()
        _JobModelStub.query = _QueryChain(
            rows=[
                SimpleNamespace(code="a", kwargs={}),
                SimpleNamespace(code="b", kwargs={}),
            ],
            first_item=SimpleNamespace(next_run_time=now + timedelta(seconds=3)),
        )
        store = ORMJobStore(job_model=_JobModelStub)
        monkeypatch.setattr(store, "_reconstitute_job", lambda record: f"job:{record.code}")

        due = store.get_due_jobs(now)
        assert due == ["job:a", "job:b"]
        assert store.get_next_run_time() == now + timedelta(seconds=3)
        assert store.get_all_jobs() == ["job:a", "job:b"]

        bad = SimpleNamespace(code="bad", kwargs={})
        _JobModelStub.query = _QueryChain(rows=[bad])

        def boom(_record):
            raise RuntimeError("broken")

        monkeypatch.setattr(store, "_reconstitute_job", boom)
        assert store.get_all_jobs() == []

        obj1 = _JobModelStub(code="x", kwargs={})
        obj2 = _JobModelStub(code="y", kwargs={})
        _JobModelStub.query = _QueryChain(rows=[obj1, obj2])
        store.remove_all_jobs()
        assert obj1.deleted is True and obj2.deleted is True

    def test_add_update_remove_and_exceptions(self):
        _JobModelStub.created = []
        _JobModelStub.query = _QueryChain(first_item=None)
        store = ORMJobStore(job_model=_JobModelStub)
        job = _APJobStub(job_id="yweb_code1")
        store.add_job(job)
        created = _JobModelStub.created[-1]
        assert created.code == "code1"
        assert "__job_state__" in created.kwargs

        _JobModelStub.query = _QueryChain(first_item=SimpleNamespace(code="exists", kwargs={}))
        with pytest.raises(ConflictingIdError):
            store.add_job(_APJobStub(job_id="yweb_exists"))

        record = _JobModelStub(code="code1", kwargs={})
        _JobModelStub.query = _QueryChain(first_item=record)
        store.update_job(job)
        assert "__job_state__" in record.kwargs
        assert record.saved is True

        _JobModelStub.query = _QueryChain(first_item=None)
        with pytest.raises(JobLookupError):
            store.update_job(job)

        target = _JobModelStub(code="code1", kwargs={})
        _JobModelStub.query = _QueryChain(first_item=target)
        store.remove_job("yweb_code1")
        assert target.deleted is True

        _JobModelStub.query = _QueryChain(first_item=None)
        with pytest.raises(JobLookupError):
            store.remove_job("yweb_missing")

    def test_reconstitute_and_trigger_helpers(self, monkeypatch):
        class APSchedulerJobStub:
            def __setstate__(self, state):
                self.state = state

        monkeypatch.setattr(orm_mod, "APSchedulerJob", APSchedulerJobStub)
        store = ORMJobStore(job_model=_JobModelStub)

        state_hex = pickle.dumps({"ok": 1}).hex()
        rec = SimpleNamespace(kwargs={"__job_state__": state_hex})
        job = store._reconstitute_job(rec)
        assert job.state == {"ok": 1}
        assert job._scheduler == store._scheduler

        bad = SimpleNamespace(kwargs={"__job_state__": "zz-not-hex"})
        assert store._reconstitute_job(bad) is None

        CronTrigger = type("CronTrigger", (), {})
        IntervalTrigger = type("IntervalTrigger", (), {})
        DateTrigger = type("DateTrigger", (), {})
        XTrigger = type("XTrigger", (), {})

        cron_trigger = CronTrigger()
        cron_trigger.fields = ["s", "m", "h", "w", "d", "mo", "y"]
        cron_trigger.timezone = "UTC"

        interval_trigger = IntervalTrigger()
        interval_trigger.interval = timedelta(days=8, seconds=3661)
        interval_trigger.timezone = "UTC"

        date_trigger = DateTrigger()
        date_trigger.run_date = datetime(2026, 1, 1)
        date_trigger.timezone = "UTC"

        unknown_trigger = XTrigger()

        assert store._get_trigger_type(cron_trigger) == "cron"
        assert store._get_trigger_type(interval_trigger) == "interval"
        assert store._get_trigger_type(date_trigger) == "once"
        assert store._get_trigger_type(unknown_trigger) == "unknown"

        cron_data = store._serialize_trigger(cron_trigger)
        interval_data = store._serialize_trigger(interval_trigger)
        date_data = store._serialize_trigger(date_trigger)
        unknown_data = store._serialize_trigger(unknown_trigger)
        assert cron_data["minute"] == "m"
        assert interval_data["days"] == 1
        assert date_data["run_date"].startswith("2026-01-01")
        assert unknown_data == {}


class TestFactoryExtra:
    """factory.py 低覆盖分支补测。"""

    def test_customizers_singletons_and_mount(self, monkeypatch):
        called = {"job": 0, "history": 0, "stats": 0, "router": 0}

        def job_customizer(cls):
            cls.extra_job = True
            called["job"] += 1

        def history_customizer(cls):
            cls.extra_history = True
            called["history"] += 1

        def stats_customizer(cls):
            cls.extra_stats = True
            called["stats"] += 1

        models = create_scheduler_models(
            table_prefix="x_",
            job_customizer=job_customizer,
            history_customizer=history_customizer,
            stats_customizer=stats_customizer,
        )
        assert called == {"job": 1, "history": 1, "stats": 1, "router": 0}
        assert models.SchedulerJob.extra_job is True

        manager1 = models.get_history_manager(enabled=False, retention_days=1)
        manager2 = models.get_history_manager(enabled=True, retention_days=99)
        assert manager1 is manager2

        store1 = models.get_orm_store(scheduler="S1")
        store2 = models.get_orm_store(scheduler="S2")
        assert store1 is store2

        fake_router = object()
        import yweb.scheduler.api as api_mod

        def fake_create_router(**kwargs):
            called["router"] += 1
            assert kwargs["history_model"] is models.SchedulerJobHistory
            return fake_router

        monkeypatch.setattr(api_mod, "create_scheduler_router", fake_create_router)
        app = SimpleNamespace(calls=[])
        app.include_router = lambda router, prefix="": app.calls.append((router, prefix))
        models.mount_routes(app=app, scheduler="SCH", prefix="/sched")
        assert called["router"] == 1
        assert app.calls == [(fake_router, "/sched")]

    def test_setup_scheduler(self, monkeypatch):
        fake_router = object()
        import yweb.scheduler.api as api_mod

        monkeypatch.setattr(api_mod, "create_scheduler_router", lambda **_k: fake_router)
        app = SimpleNamespace(calls=[])
        app.include_router = lambda router, prefix="": app.calls.append((router, prefix))

        models = setup_scheduler(app=app, api_prefix="/api/scheduler", scheduler_instance="SCH")
        assert hasattr(models.SchedulerJob, "__tablename__")
        assert app.calls == [(fake_router, "/api/scheduler")]
