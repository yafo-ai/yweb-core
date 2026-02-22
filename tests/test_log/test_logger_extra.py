"""log.logger 补充测试"""

import logging
import os
import importlib
from types import SimpleNamespace

logger_mod = importlib.import_module("yweb.log.logger")


class DummyConfig:
    level = "WARNING"
    file_path = ""
    file_backup_count = 3
    file_encoding = "utf-8"
    file_when = "midnight"
    file_interval = 1
    parsed_file_max_bytes = 1024
    parsed_max_total_size = 2048
    max_retention_days = 7
    buffer_enabled = True
    buffer_capacity = 5
    buffer_flush_interval = 1.0
    buffer_flush_level = "ERROR"
    sql_log_enabled = True
    sql_log_file_path = ""
    sql_log_level = "INFO"
    sql_log_backup_count = 2
    parsed_sql_log_max_bytes = 1024
    parsed_sql_log_max_total_size = 4096
    sql_log_max_retention_days = 3
    sql_log_buffer_enabled = True
    sql_log_buffer_capacity = 10
    sql_log_buffer_flush_interval = 2.0


class TestLoggerExtra:
    def test_parse_level_and_extract_options(self):
        assert logger_mod._parse_log_level("warning") == logging.WARNING
        assert logger_mod._parse_log_level("unknown") == logging.ERROR

        cfg = DummyConfig()
        options = logger_mod._extract_file_handler_options(cfg)
        assert options["maxBytes"] == 1024
        assert options["bufferEnabled"] is True
        assert options["bufferCapacity"] == 5

        sql_options = logger_mod._extract_sql_file_handler_options(cfg)
        assert sql_options["bufferEnabled"] is True
        assert sql_options["flushLevel"] == logging.ERROR

    def test_create_formatter_without_microseconds(self):
        formatter = logger_mod.create_formatter(use_microseconds=False)
        assert isinstance(formatter, logging.Formatter)
        assert not isinstance(formatter, logger_mod.MicrosecondFormatter)

    def test_setup_logger_with_buffer_file_handler(self, tmp_path):
        log_file = tmp_path / "x.log"
        lg = logger_mod.setup_logger(
            name="test.buffer.logger",
            level="INFO",
            log_file=str(log_file),
            console=False,
            file_handler_options={
                "maxBytes": 1024,
                "backupCount": 1,
                "encoding": "utf-8",
                "when": "midnight",
                "interval": 1,
                "bufferEnabled": True,
                "bufferCapacity": 2,
                "flushInterval": 0.2,
                "flushLevel": logging.ERROR,
            },
        )
        lg.info("hello")
        for h in lg.handlers:
            h.flush()
            h.close()
        lg.handlers.clear()
        assert os.path.exists(log_file)

    def test_setup_root_logger_from_config_and_setup_sql(self, monkeypatch):
        called = {"sql": 0}

        def fake_setup_sql_internal(config):
            assert getattr(config, "sql_log_enabled", False) is True
            called["sql"] += 1
            return logging.getLogger("sqlalchemy.engine")

        monkeypatch.setattr(logger_mod, "_setup_sql_logger_internal", fake_setup_sql_internal)
        cfg = DummyConfig()
        root = logger_mod.setup_root_logger(config=cfg, console=False, setup_sql_logger=True)
        assert isinstance(root, logging.Logger)
        assert called["sql"] == 1
        for h in root.handlers:
            h.close()
        root.handlers.clear()

    def test_setup_root_logger_from_config_path(self, monkeypatch):
        cfg = SimpleNamespace(
            level="INFO",
            file_path="",
            file_backup_count=1,
            file_encoding="utf-8",
            file_when="midnight",
            file_interval=1,
            parsed_file_max_bytes=256,
            parsed_max_total_size=0,
            max_retention_days=0,
            enable_console=False,
            sql_log_enabled=False,
        )
        monkeypatch.setattr(logger_mod, "_load_logging_config_from_file", lambda p, b=None: cfg)
        root = logger_mod.setup_root_logger(config_path="fake.yaml", setup_sql_logger=True)
        assert isinstance(root, logging.Logger)
        for h in root.handlers:
            h.close()
        root.handlers.clear()

    def test_setup_sql_logger_config_disabled_and_enabled(self):
        disabled_cfg = SimpleNamespace(sql_log_enabled=False)
        assert logger_mod.setup_sql_logger(config=disabled_cfg) is None

        enabled_cfg = SimpleNamespace(
            sql_log_enabled=True,
            sql_log_level="DEBUG",
            sql_log_file_path=None,
            sql_log_backup_count=1,
            file_encoding="utf-8",
            file_when="midnight",
            file_interval=1,
            parsed_sql_log_max_bytes=128,
            sql_log_max_retention_days=0,
            parsed_sql_log_max_total_size=0,
            sql_log_buffer_enabled=False,
        )
        sql_logger = logger_mod.setup_sql_logger(config=enabled_cfg, console=False)
        assert isinstance(sql_logger, logging.Logger)
        for h in sql_logger.handlers:
            h.close()
        sql_logger.handlers.clear()
