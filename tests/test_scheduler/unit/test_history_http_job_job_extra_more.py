"""history/http_job/job 模块补充测试。"""

from __future__ import annotations

import sys
from datetime import date, datetime
from types import SimpleNamespace

import pytest

from yweb.scheduler.context import JobContext
from yweb.scheduler.history import HistoryManager
from yweb.scheduler.http_job import HttpJob, HttpJobError, HttpResponse, HttpRetryError
from yweb.scheduler.job import Job
from yweb.scheduler.triggers import cron


class _ExprField:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return (self.name, "==", other)

    def __lt__(self, other):
        return (self.name, "<", other)

    def __le__(self, other):
        return (self.name, "<=", other)

    def __ge__(self, other):
        return (self.name, ">=", other)

    def desc(self):
        return f"{self.name}_desc"


class _QueryLike:
    def __init__(self, rows=None, first_item=None, count_value=0):
        self.rows = list(rows or [])
        self.first_item = first_item
        self.count_value = count_value
        self.filters = []
        self.offset_value = None
        self.limit_value = None
        self.order_value = None

    def filter(self, *args):
        self.filters.extend(args)
        return self

    def order_by(self, arg):
        self.order_value = arg
        return self

    def offset(self, v):
        self.offset_value = v
        return self

    def limit(self, v):
        self.limit_value = v
        return self

    def all(self):
        return list(self.rows)

    def first(self):
        if self.first_item is not None:
            return self.first_item
        return self.rows[0] if self.rows else None

    def count(self):
        return self.count_value


class _HistoryModelStub:
    run_id = _ExprField("run_id")
    job_code = _ExprField("job_code")
    status = _ExprField("status")
    start_time = _ExprField("start_time")
    query = _QueryLike()


class _StatsRecord:
    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.saved = False
        self.deleted = False

    def save(self, commit=False):
        _ = commit
        self.saved = True

    def delete(self):
        self.deleted = True


class _StatsModelStub:
    job_code = _ExprField("job_code")
    stat_date = _ExprField("stat_date")
    stat_hour = _ExprField("stat_hour")
    query = _QueryLike()

    def __new__(cls, **kwargs):
        return _StatsRecord(**kwargs)


class _HttpRespStub:
    def __init__(self, status=200, body="{}", headers=None):
        self.status = status
        self._body = body
        self.headers = headers or {"x": "1"}

    async def text(self):
        return self._body


class _ResponseContext:
    def __init__(self, resp):
        self.resp = resp

    async def __aenter__(self):
        return self.resp

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False


class _SessionContext:
    def __init__(self, response=None, error=None, sink=None):
        self.response = response
        self.error = error
        self.sink = sink

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        _ = (exc_type, exc, tb)
        return False

    def request(self, **kwargs):
        if self.sink is not None:
            self.sink["kwargs"] = kwargs
        if self.error:
            raise self.error("request error")
        return _ResponseContext(self.response)


class HttpJobWithBody(HttpJob):
    code = "HTTP_TEST_JOB"
    trigger = cron("0 8 * * *")
    url = "https://example.com/api"
    method = "POST"
    headers = {"Authorization": "Bearer x"}

    def __init__(self, body=None):
        self._body = body
        super().__init__()

    def get_body(self, context):
        _ = context
        return self._body


class JobPlainImpl(Job):
    code = "JOB_PLAIN_IMPL"
    trigger = cron("0 8 * * *")

    async def execute(self, context):
        _ = context
        return "ok"


class TestHistoryExtraMore:
    """HistoryManager 额外分支补测。"""

    def test_model_properties_raise_when_not_configured(self):
        manager = HistoryManager(enabled=True)
        with pytest.raises(RuntimeError):
            _ = manager.job_model
        with pytest.raises(RuntimeError):
            _ = manager.history_model
        with pytest.raises(RuntimeError):
            _ = manager.stats_model

    def test_get_executions_count_stats_and_cleanup_branches(self):
        history_query = _QueryLike(rows=[SimpleNamespace(run_id="r1")], count_value=7)
        stats_query = _QueryLike(rows=[SimpleNamespace(job_code="x")])
        _HistoryModelStub.query = history_query
        _StatsModelStub.query = stats_query

        manager = HistoryManager(
            enabled=True,
            retention_days=3,
            job_model=SimpleNamespace,
            history_model=_HistoryModelStub,
            stats_model=_StatsModelStub,
        )

        rows = manager.get_executions(
            job_code="J1",
            status="failed",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
            limit=5,
            offset=2,
        )
        assert len(rows) == 1
        assert history_query.offset_value == 2
        assert history_query.limit_value == 5
        assert history_query.order_value == "start_time_desc"

        total = manager.count_executions(
            job_code="J1",
            status="failed",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        assert total == 7

        stat_rows = manager.get_stats(
            job_code="J1",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 1, 31),
        )
        assert len(stat_rows) == 1
        assert stats_query.order_value == "stat_date_desc"

        assert manager.cleanup_old_history(days=-1) == 0
        assert manager.cleanup_old_stats(days=-1) == 0

    def test_cleanup_old_stats_and_update_paths(self):
        old_stats = [_StatsRecord(), _StatsRecord()]
        _StatsModelStub.query = _QueryLike(rows=old_stats)
        manager = HistoryManager(
            enabled=True,
            retention_days=3,
            job_model=SimpleNamespace,
            history_model=_HistoryModelStub,
            stats_model=_StatsModelStub,
        )
        assert manager.cleanup_old_stats(days=2) == 2
        assert all(s.deleted for s in old_stats)

        created_stats = []

        class StatsModelCreateStub(_StatsModelStub):
            query = _QueryLike(first_item=None)

            def __new__(cls, **kwargs):
                obj = _StatsRecord(**kwargs)
                created_stats.append(obj)
                return obj

        manager = HistoryManager(
            enabled=True,
            retention_days=3,
            job_model=SimpleNamespace,
            history_model=_HistoryModelStub,
            stats_model=StatsModelCreateStub,
        )
        manager._update_stats_record("id1", "code1", date.today(), None, "timeout", 120)
        assert created_stats[0].timeout_runs == 1
        assert created_stats[0].avg_duration == 120
        assert created_stats[0].saved is True

        def _boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        manager._update_stats_record = _boom
        manager._update_job_stats("id1", "code1", "success", 1)


class TestHttpJobExtraMore:
    """HttpJob 执行路径补测。"""

    @pytest.mark.asyncio
    async def test_execute_success_with_json_and_data_body(self, monkeypatch):
        sink = {}
        fake_aiohttp = SimpleNamespace(
            ClientTimeout=lambda total: SimpleNamespace(total=total),
            ClientError=RuntimeError,
            ClientSession=lambda: _SessionContext(
                response=_HttpRespStub(status=200, body='{"ok":1}'),
                sink=sink,
            ),
        )
        monkeypatch.setitem(sys.modules, "aiohttp", fake_aiohttp)

        job = HttpJobWithBody(body={"a": 1})
        ctx = JobContext(job_id="j1", job_code="c1", job_name="n1", run_id="r1")
        result = await job.execute(ctx)
        assert isinstance(result, HttpResponse)
        assert result.status_code == 200
        assert sink["kwargs"]["json"] == {"a": 1}

        job2 = HttpJobWithBody(body="raw-body")
        await job2.execute(ctx)
        assert sink["kwargs"]["data"] == "raw-body"
        assert job2.get_method(ctx) == "POST"
        assert job2.get_headers(ctx)["Authorization"] == "Bearer x"

    @pytest.mark.asyncio
    async def test_execute_retry_non_retry_and_client_error(self, monkeypatch):
        ctx = JobContext(job_id="j2", job_code="c2", job_name="n2", run_id="r2")

        fake_retry = SimpleNamespace(
            ClientTimeout=lambda total: SimpleNamespace(total=total),
            ClientError=RuntimeError,
            ClientSession=lambda: _SessionContext(response=_HttpRespStub(status=503, body="busy")),
        )
        monkeypatch.setitem(sys.modules, "aiohttp", fake_retry)
        with pytest.raises(HttpRetryError) as e1:
            await HttpJobWithBody(body=None).execute(ctx)
        assert e1.value.response.status_code == 503

        fake_fail = SimpleNamespace(
            ClientTimeout=lambda total: SimpleNamespace(total=total),
            ClientError=RuntimeError,
            ClientSession=lambda: _SessionContext(response=_HttpRespStub(status=400, body="bad")),
        )
        monkeypatch.setitem(sys.modules, "aiohttp", fake_fail)
        with pytest.raises(HttpJobError) as e2:
            await HttpJobWithBody(body=None).execute(ctx)
        assert e2.value.response.status_code == 400

        class FakeClientErr(Exception):
            pass

        fake_error = SimpleNamespace(
            ClientTimeout=lambda total: SimpleNamespace(total=total),
            ClientError=FakeClientErr,
            ClientSession=lambda: _SessionContext(
                response=None,
                error=FakeClientErr,
            ),
        )
        monkeypatch.setitem(sys.modules, "aiohttp", fake_error)
        with pytest.raises(HttpRetryError):
            await HttpJobWithBody(body=None).execute(ctx)

    @pytest.mark.asyncio
    async def test_default_callbacks_and_error_classes(self):
        ctx = JobContext(job_id="j3", job_code="c3", job_name="n3", run_id="r3")
        job = HttpJobWithBody(body=None)

        assert HttpResponse(status_code=204, body=None).json() is None
        err = HttpJobError("x", response=HttpResponse(status_code=500))
        retry = HttpRetryError("y", response=HttpResponse(status_code=503))
        assert err.response.status_code == 500
        assert retry.response.status_code == 503

        await job.on_success(ctx, HttpResponse(status_code=200))
        await job.on_error(ctx, RuntimeError("boom"))


class TestJobExtraMore:
    """Job 基类遗漏分支补测。"""

    def test_job_meta_rejects_noncallable_execute(self):
        with pytest.raises(TypeError):
            type(
                "BadJobNoCallableExecute",
                (Job,),
                {
                    "code": "BAD",
                    "trigger": cron("0 8 * * *"),
                    "execute": None,
                },
            )

    @pytest.mark.asyncio
    async def test_base_execute_callbacks_and_empty_triggers(self):
        job = JobPlainImpl()
        ctx = JobContext(job_id="j4", job_code="c4", job_name="n4", run_id="r4")

        with pytest.raises(NotImplementedError):
            await Job.execute(job, ctx)

        await Job.on_success(job, ctx, "ok")
        await Job.on_error(job, ctx, RuntimeError("err"))
        await Job.on_retry(job, ctx, RuntimeError("retry"))

        job.trigger = None
        job.triggers = None
        assert job.get_triggers() == []
