"""middleware.request_logging 补充测试"""

import asyncio
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from yweb.middleware.request_logging import RequestLoggingMiddleware


class LoggerStub:
    def __init__(self):
        self.events = []

    def debug(self, msg):
        self.events.append(("debug", msg))

    def info(self, msg):
        self.events.append(("info", msg))

    def warning(self, msg):
        self.events.append(("warning", msg))

    def error(self, msg):
        self.events.append(("error", msg))


class TestRequestLoggingExtra:
    def test_config_path_parse_and_skip_prefix(self, monkeypatch):
        parse_called = {"count": 0}

        def fake_parse_file_size(raw):
            parse_called["count"] += 1
            assert raw == "2MB"
            return 2 * 1024 * 1024

        import yweb.utils as u

        monkeypatch.setattr(u, "parse_file_size", fake_parse_file_size)

        cfg = SimpleNamespace(
            request_log_max_body_size="2MB",
            request_log_skip_paths=["/health", "/api/internal"],
        )
        mw = RequestLoggingMiddleware(app=lambda s, r, w: None, config=cfg, enable_sensitive_filter=False)
        assert parse_called["count"] == 1
        assert mw.max_body_size == 2 * 1024 * 1024
        assert mw._should_skip("/api/internal/metrics") is True
        assert mw._should_skip("/openapi.json") is False

    def test_parse_body_variants(self):
        mw = RequestLoggingMiddleware(app=lambda s, r, w: None, max_body_size=7, enable_sensitive_filter=False)
        mw_large = RequestLoggingMiddleware(app=lambda s, r, w: None, max_body_size=2000, enable_sensitive_filter=False)

        assert mw._parse_body(b"", "application/json") is None

        truncated_json = mw._parse_body(b'{"x":1}   ', "application/json")
        assert isinstance(truncated_json, dict)
        assert truncated_json["_truncated"] is True

        long_text = mw_large._parse_body(b"x" * 1000, "text/plain")
        assert long_text.endswith("...")

        binary_preview = mw._parse_body(b"\xff\xfe\xfd", "application/octet-stream")
        assert isinstance(binary_preview, str)
        assert len(binary_preview) > 0

    @pytest.mark.asyncio
    async def test_get_user_info_timeout_error_and_sync(self):
        logger = LoggerStub()
        mw_no_getter = RequestLoggingMiddleware(
            app=lambda s, r, w: None, logger=logger, enable_sensitive_filter=False
        )
        assert await mw_no_getter._get_user_info_with_timeout({}) == "anonymous"

        async def slow_getter(_scope):
            await asyncio.sleep(0.2)
            return "u"

        mw_timeout = RequestLoggingMiddleware(
            app=lambda s, r, w: None,
            logger=logger,
            user_info_getter=slow_getter,
            user_info_timeout=0.01,
            enable_sensitive_filter=False,
        )
        assert await mw_timeout._get_user_info_with_timeout({}) == "anonymous[timeout]"

        def bad_sync_getter(_scope):
            raise RuntimeError("sync failed")

        mw_error = RequestLoggingMiddleware(
            app=lambda s, r, w: None,
            logger=logger,
            user_info_getter=bad_sync_getter,
            user_info_timeout=0.1,
            enable_sensitive_filter=False,
        )
        assert await mw_error._get_user_info_with_timeout({}) == "anonymous[error]"

    def test_apply_filters_and_write_levels(self):
        logger = LoggerStub()
        mw = RequestLoggingMiddleware(app=lambda s, r, w: None, logger=logger, enable_sensitive_filter=False)

        def f1(data):
            d = dict(data)
            d["user_info"] = "filtered"
            return d

        def f2(_data):
            raise ValueError("bad filter")

        filtered = mw._apply_log_filters({"user_info": "raw", "status_code": 200})
        assert filtered["user_info"] == "raw"

        mw.log_filters = [f1, f2]
        filtered2 = mw._apply_log_filters({"user_info": "raw", "status_code": 200})
        assert filtered2["user_info"] == "filtered"

        mw._write_log_sync({"status_code": 200, "request_body_preview": {"a": 1}})
        mw._write_log_sync({"status_code": 404, "request_body_preview": None})
        mw._write_log_sync({"status_code": 500, "request_body_preview": "x"})
        levels = [item[0] for item in logger.events]
        assert "info" in levels and "warning" in levels and "error" in levels

    def test_schedule_log_fallback_and_call_non_http(self):
        logger = LoggerStub()
        mw = RequestLoggingMiddleware(app=lambda s, r, w: None, logger=logger, enable_sensitive_filter=False)

        # 线程池为空时，回退到同步写入
        mw._executor = None
        mw._schedule_log({"status_code": 200, "request_body_preview": None})
        assert any(level == "info" for level, _ in logger.events)

    def test_call_exception_path_with_test_client(self, monkeypatch):
        import yweb.middleware.request_logging as m

        app = FastAPI()
        app.add_middleware(RequestLoggingMiddleware, enable_sensitive_filter=False)

        @app.get("/boom")
        def boom():
            raise RuntimeError("boom")

        # 覆盖 request_id 读取异常分支
        monkeypatch.setattr(m.db_manager, "_get_request_id", lambda: (_ for _ in ()).throw(RuntimeError("x")))
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/boom")
        assert resp.status_code == 500
