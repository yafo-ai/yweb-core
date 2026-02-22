"""log.handlers 补充测试"""

import logging
import weakref

import yweb.log.handlers as handlers_mod


class FakeRef:
    def __init__(self, obj):
        self._obj = obj

    def __call__(self):
        return self._obj


class FlushObj:
    def __init__(self, fail=False):
        self.flushed = 0
        self.fail = fail

    def flush(self):
        self.flushed += 1
        if self.fail:
            raise RuntimeError("flush fail")


class JoinableThread:
    def __init__(self):
        self.join_called = False

    def is_alive(self):
        return True

    def join(self, timeout=None):
        _ = timeout
        self.join_called = True


class BadStream:
    def __init__(self):
        self.closed = False

    def write(self, _msg):
        raise RuntimeError("write fail")

    def flush(self):
        return None

    def close(self):
        self.closed = True

    def tell(self):
        return 0

    def seek(self, *_args):
        return None


class TestHandlersExtraMore:
    def test_flush_all_buffered_handlers(self, monkeypatch):
        ok_obj = FlushObj()
        bad_obj = FlushObj(fail=True)
        monkeypatch.setattr(
            handlers_mod,
            "_buffered_handlers",
            [FakeRef(ok_obj), FakeRef(bad_obj), FakeRef(None)],
        )
        handlers_mod._flush_all_buffered_handlers()
        assert ok_obj.flushed == 1
        assert bad_obj.flushed == 1

    def test_emit_handle_error_and_flush_buffer_exception(self, tmp_path, monkeypatch):
        log_file = tmp_path / "buffered_{date}.log"
        handler = handlers_mod.BufferedRotatingFileHandler(
            filename=str(log_file),
            maxBytes=1024,
            backupCount=1,
            bufferCapacity=5,
            flushInterval=1.0,
            flushLevel=logging.CRITICAL,
        )

        called = {"error": 0}

        def bad_format(_record):
            raise ValueError("format broken")

        def mark_error(_record):
            called["error"] += 1

        monkeypatch.setattr(handler, "format", bad_format)
        monkeypatch.setattr(handler, "handleError", mark_error)
        handler.emit(logging.LogRecord("x", logging.INFO, "", 1, "m", (), None))
        assert called["error"] == 1

        # 覆盖 _flush_buffer_unsafe 的异常分支
        handler._buffer = ["x1", "x2"]
        handler.stream = BadStream()
        handler._flush_buffer_unsafe()
        handler.close()

    def test_close_with_alive_thread_branch(self, tmp_path):
        log_file = tmp_path / "close_{date}.log"
        handler = handlers_mod.BufferedRotatingFileHandler(
            filename=str(log_file),
            maxBytes=0,
            backupCount=0,
            bufferCapacity=2,
            flushInterval=1.0,
            flushLevel=logging.ERROR,
        )
        # 停掉真实线程，替换为可控桩，命中 join 分支
        handler._stop_event.set()
        if handler._flush_thread and handler._flush_thread.is_alive():
            handler._flush_thread.join(timeout=0.2)

        fake_thread = JoinableThread()
        handler._flush_thread = fake_thread
        handler.close()
        assert fake_thread.join_called is True
