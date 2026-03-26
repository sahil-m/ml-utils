import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from unittest.mock import patch

import pytest

from ml_utils.logger import (
    JsonFormatter,
    _get_active_handlers,
    get_logger,
    setup_logging,
    shutdown_logging,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _clean_logging():
    """Reset logging state before and after every test."""
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()
    yield
    shutdown_logging()
    root = logging.getLogger()
    for h in root.handlers[:]:
        root.removeHandler(h)
        h.close()


@pytest.fixture()
def log_file(tmp_path: Path) -> Path:
    """Provide a temporary log file path (auto-cleaned by tmp_path)."""
    return tmp_path / "test.log"


def _flush_and_read(log_file: Path) -> list[dict]:
    """Shutdown logging, wait briefly, return parsed JSON lines."""
    shutdown_logging()
    time.sleep(0.1)
    lines = log_file.read_text().strip().split("\n")
    return [json.loads(line) for line in lines if line]


# ===========================================================================
# setup_logging basics
# ===========================================================================
class TestSetupLogging:
    def test_returns_without_error(self):
        setup_logging()

    def test_level_filters_messages(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.WARNING)
        logging.getLogger("test.filter").debug("should be dropped")
        logging.getLogger("test.filter").warning("should appear")
        records = _flush_and_read(log_file)
        messages = [r["message"] for r in records]
        assert "should appear" in messages
        assert "should be dropped" not in messages

    def test_attaches_single_queue_handler_to_root(self):
        setup_logging()
        root = logging.getLogger()
        qh = [h for h in root.handlers if isinstance(h, logging.handlers.QueueHandler)]
        assert len(qh) == 1

    def test_default_level_is_debug(self):
        setup_logging()
        assert logging.getLogger().level == logging.DEBUG

    @pytest.mark.parametrize("level", [logging.WARNING, logging.ERROR, logging.INFO])
    def test_custom_level(self, level: int):
        setup_logging(level=level)
        assert logging.getLogger().level == level


# ===========================================================================
# get_logger
# ===========================================================================
class TestGetLogger:
    def test_returns_named_logger(self):
        setup_logging()
        logger = get_logger("myapp.module")
        assert logger.name == "myapp.module"
        assert isinstance(logger, logging.Logger)

    def test_without_name_uses_caller_module(self):
        setup_logging()
        logger = get_logger()
        assert logger.name is not None
        assert logger.name != "root"


# ===========================================================================
# Console handler
# ===========================================================================
class TestConsoleHandler:
    def test_enabled_by_default(self):
        setup_logging()
        handlers = _get_active_handlers()
        try:
            from rich.logging import RichHandler as _RichHandler

            _console_types = (logging.StreamHandler, _RichHandler)
        except ImportError:
            _console_types = (logging.StreamHandler,)
        console = [
            h
            for h in handlers
            if isinstance(h, _console_types) and not isinstance(h, logging.FileHandler)
        ]
        assert len(console) >= 1

    def test_can_be_disabled(self):
        setup_logging(enable_console=False)
        handlers = _get_active_handlers()
        console = [
            h
            for h in handlers
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler)
        ]
        assert len(console) == 0

    def test_uses_rich_handler_when_available(self):
        """RichHandler is used as the console handler when rich is installed."""
        try:
            from rich.logging import RichHandler
        except ImportError:
            pytest.skip("rich not installed")
        setup_logging()
        handlers = _get_active_handlers()
        assert any(isinstance(h, RichHandler) for h in handlers)

    def test_fallback_without_rich(self):
        """Console logging works even if rich is not installed."""
        with patch.dict("sys.modules", {"rich": None, "rich.logging": None}):
            import importlib
            import ml_utils.logger as logger_mod

            importlib.reload(logger_mod)
            logger_mod.setup_logging()
            log = logging.getLogger("test.no_rich")
            log.info("works without rich")  # should not raise
            logger_mod.shutdown_logging()


# ===========================================================================
# File handler
# ===========================================================================
class TestFileHandler:
    def test_console_and_file_active_simultaneously(self, log_file: Path):
        setup_logging(log_file=log_file)
        handlers = _get_active_handlers()
        file_handlers = [h for h in handlers if isinstance(h, logging.FileHandler)]
        try:
            from rich.logging import RichHandler as _RichHandler

            _console_types = (logging.StreamHandler, _RichHandler)
        except ImportError:
            _console_types = (logging.StreamHandler,)
        console_handlers = [
            h
            for h in handlers
            if isinstance(h, _console_types) and not isinstance(h, logging.FileHandler)
        ]
        assert len(file_handlers) >= 1
        assert len(console_handlers) >= 1

    def test_disabled_by_default(self):
        setup_logging()
        file_handlers = [h for h in _get_active_handlers() if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) == 0

    def test_enabled_with_path(self, log_file: Path):
        setup_logging(log_file=log_file)
        file_handlers = [h for h in _get_active_handlers() if isinstance(h, logging.FileHandler)]
        assert len(file_handlers) >= 1

    def test_uses_rotating_file_handler(self, log_file: Path):
        setup_logging(log_file=log_file)
        rotating = [
            h for h in _get_active_handlers() if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert len(rotating) == 1

    def test_rotation_params(self, log_file: Path):
        setup_logging(log_file=log_file, max_bytes=5_000_000, backup_count=3)
        rotating = [
            h for h in _get_active_handlers() if isinstance(h, logging.handlers.RotatingFileHandler)
        ]
        assert rotating[0].maxBytes == 5_000_000
        assert rotating[0].backupCount == 3


# ===========================================================================
# JSON file output
# ===========================================================================
class TestJsonFileOutput:
    def test_valid_json_per_line(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logger = logging.getLogger("test.json")
        logger.info("hello json")
        logger.warning("warn json")

        records = _flush_and_read(log_file)
        assert len(records) >= 2
        for rec in records:
            assert "message" in rec
            assert "level" in rec
            assert "timestamp" in rec

    def test_contains_expected_fields(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logging.getLogger("test.fields").info("structured log test")

        records = _flush_and_read(log_file)
        expected = {"message", "level", "timestamp", "logger", "module", "function", "line"}
        assert expected.issubset(records[0].keys()), f"Missing: {expected - records[0].keys()}"

    def test_captures_exception_info(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logger = logging.getLogger("test.exc")
        try:
            1 / 0
        except ZeroDivisionError:
            logger.exception("division failed")

        records = _flush_and_read(log_file)
        assert "exception" in records[0]
        assert "ZeroDivisionError" in records[0]["exception"]

    def test_extra_fields_in_file(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logging.getLogger("test.extra").info("with context", extra={"request_id": "req-42"})

        records = _flush_and_read(log_file)
        assert records[0]["request_id"] == "req-42"


# ===========================================================================
# JsonFormatter unit tests (no queue involved)
# ===========================================================================
class TestJsonFormatter:
    @pytest.fixture()
    def formatter(self) -> JsonFormatter:
        return JsonFormatter()

    def _make_record(self, **kwargs) -> logging.LogRecord:
        defaults = dict(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=42,
            msg="hello",
            args=(),
            exc_info=None,
        )
        defaults.update(kwargs)
        return logging.LogRecord(**defaults)

    def test_produces_valid_json(self, formatter: JsonFormatter):
        record = self._make_record(msg="hello %s", args=("world",))
        parsed = json.loads(formatter.format(record))
        assert parsed["message"] == "hello world"
        assert parsed["level"] == "INFO"

    def test_includes_exception(self, formatter: JsonFormatter):
        try:
            raise ValueError("test error")
        except ValueError:
            exc_info = sys.exc_info()
        record = self._make_record(level=logging.ERROR, msg="err", exc_info=exc_info)
        parsed = json.loads(formatter.format(record))
        assert "exception" in parsed
        assert "ValueError" in parsed["exception"]

    def test_includes_extra_fields(self, formatter: JsonFormatter):
        record = self._make_record(msg="with extra")
        record.request_id = "abc-123"
        parsed = json.loads(formatter.format(record))
        assert parsed["request_id"] == "abc-123"

    def test_non_serializable_extra_becomes_string(self, formatter: JsonFormatter):
        record = self._make_record()
        record.custom_obj = object()
        parsed = json.loads(formatter.format(record))
        assert isinstance(parsed["custom_obj"], str)

    def test_use_utc_true_produces_utc_timestamp(self):
        formatter = JsonFormatter(use_utc=True)
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        assert parsed["timestamp"].endswith("+00:00")

    def test_use_utc_false_produces_local_timestamp(self):
        formatter = JsonFormatter(use_utc=False)
        record = self._make_record()
        parsed = json.loads(formatter.format(record))
        # Naive local ISO string has no timezone suffix
        assert "+" not in parsed["timestamp"] and "Z" not in parsed["timestamp"]

    def test_use_utc_via_setup_logging(self, log_file: Path):
        setup_logging(log_file=log_file, enable_console=False, use_utc=True)
        logging.getLogger("test.utc").info("utc check")
        records = _flush_and_read(log_file)
        assert records[0]["timestamp"].endswith("+00:00")


# ===========================================================================
# Async (QueueHandler / QueueListener)
# ===========================================================================
class TestAsyncLogging:
    def test_queue_handler_is_non_blocking(self):
        """100 log calls should complete well under 1 second."""
        setup_logging()
        logger = logging.getLogger("test.async")
        start = time.monotonic()
        for _ in range(100):
            logger.info("fast log")
        elapsed = time.monotonic() - start
        assert elapsed < 1.0

    def test_listener_delivers_records_to_file(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logging.getLogger("test.listener").info("listener test message")

        shutdown_logging()
        time.sleep(0.1)
        assert "listener test message" in log_file.read_text()


# ===========================================================================
# Shutdown
# ===========================================================================
class TestShutdown:
    def test_idempotent(self):
        setup_logging()
        shutdown_logging()
        shutdown_logging()  # should not raise

    def test_flushes_pending_records(self, log_file: Path):
        setup_logging(log_file=log_file, level=logging.DEBUG)
        logging.getLogger("test.flush").info("flush me")
        shutdown_logging()
        time.sleep(0.1)
        assert "flush me" in log_file.read_text()


# ===========================================================================
# Extensibility
# ===========================================================================
class TestExtensibility:
    def test_extra_handlers_are_added(self):
        extra = logging.StreamHandler()
        setup_logging(extra_handlers=[extra])
        assert extra in _get_active_handlers()

    def test_only_extra_handlers(self):
        extra = logging.StreamHandler()
        setup_logging(enable_console=False, extra_handlers=[extra])
        assert extra in _get_active_handlers()

    def test_multiple_extra_handlers(self):
        h1 = logging.StreamHandler()
        h2 = logging.StreamHandler()
        setup_logging(extra_handlers=[h1, h2])
        active = _get_active_handlers()
        assert h1 in active
        assert h2 in active
