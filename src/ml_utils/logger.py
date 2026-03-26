"""
Async-capable logging setup with pluggable handlers.

Architecture:
    logger.info("msg")
        → QueueHandler (non-blocking, enqueues LogRecord)
            → QueueListener (background thread, dispatches to real handlers)
                ├─► Console handler (RichHandler if available, else clean StreamHandler)
                └─► RotatingFileHandler with JSON formatter (one JSON object per line)
"""

from __future__ import annotations

import atexit
import inspect
import json
import logging
import logging.handlers
import queue
import sys
from collections.abc import Sequence
from datetime import UTC, datetime
from pathlib import Path

# %% [markdown]
# # Module Level State
# %%
_listener: logging.handlers.QueueListener | None = None
_active_handlers: list[logging.Handler] = []

# Standard LogRecord attributes to exclude from "extra" fields
_LOG_RECORD_BUILTIN_ATTRS = {
    "args",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "message",
    "module",
    "msecs",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "thread",
    "threadName",
    "taskName",
}


# %% [markdown]
# # JSON Formatter
# %%
class JsonFormatter(logging.Formatter):
    """Formats each LogRecord as a single-line JSON object.

    Standard fields: timestamp, level, logger, module, function, line, message.
    Extra attributes added to the LogRecord are included automatically.
    Exception info is captured under the 'exception' key.
    """

    def __init__(self, *args, use_utc: bool = True, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.use_utc = use_utc

    def format(self, record: logging.LogRecord) -> str:
        message = record.getMessage()

        # Exception info — handle both direct and QueueListener-prepared records.
        # QueueListener.prepare() merges exc_info into the message text and
        # sets exc_info/exc_text to None. We detect this by looking for a
        # Traceback marker in the message and split it out.
        exception_text: str | None = None
        if record.exc_info and record.exc_info[0] is not None:
            exception_text = self.formatException(record.exc_info)
        elif record.exc_text:
            exception_text = record.exc_text
        else:
            # QueueListener already merged it — try to extract
            tb_marker = "\nTraceback (most recent call last):"
            if tb_marker in message:
                idx = message.index(tb_marker)
                exception_text = message[idx + 1 :]  # skip the leading \n
                message = message[:idx]

        tz = UTC if self.use_utc else None
        log_dict: dict = {
            "timestamp": datetime.fromtimestamp(record.created, tz=tz).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "message": message,
        }

        if exception_text:
            log_dict["exception"] = exception_text

        if record.stack_info:
            log_dict["stack_info"] = record.stack_info

        # Include any extra fields the caller attached
        for key, val in record.__dict__.items():
            if key not in _LOG_RECORD_BUILTIN_ATTRS and key not in log_dict:
                try:
                    json.dumps(val)  # check serializable
                    log_dict[key] = val
                except (TypeError, ValueError):
                    log_dict[key] = str(val)

        return json.dumps(log_dict, default=str)


# %% [markdown]
# # Console handler factory
# %%
def _make_console_handler(level: int = logging.DEBUG) -> logging.Handler:
    """Create a console handler. Uses RichHandler if available, else StreamHandler."""
    try:
        from rich.logging import RichHandler

        handler = RichHandler(
            level=level,
            show_time=True,
            show_level=True,
            show_path=True,
            rich_tracebacks=True,
            tracebacks_show_locals=False,
            markup=False,
        )
        handler.setFormatter(logging.Formatter("%(message)s"))
    except ImportError:
        handler = logging.StreamHandler(sys.stderr)
        handler.setLevel(level)
        fmt = "%(asctime)s │ %(levelname)-8s │ %(name)s:%(funcName)s:%(lineno)d │ %(message)s"
        handler.setFormatter(logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S"))
    return handler


# %% [markdown]
# # File Handle Factory
# %%
def _make_file_handler(
    log_file: str | Path,
    level: int = logging.DEBUG,
    max_bytes: int = 10_000_000,  # 10 MB
    backup_count: int = 5,
    use_utc: bool = True,
) -> logging.handlers.RotatingFileHandler:
    """Create a RotatingFileHandler with JSON formatting."""
    log_file = Path(log_file)
    log_file.parent.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.RotatingFileHandler(
        filename=str(log_file),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(JsonFormatter(use_utc=use_utc))
    return handler


# %% [markdown]
# # Public API
# %%
def setup_logging(
    *,
    level: int = logging.DEBUG,
    enable_console: bool = True,
    log_file: str | Path | None = None,
    max_bytes: int = 10_000_000,
    backup_count: int = 5,
    use_utc: bool = True,
    extra_handlers: Sequence[logging.Handler] | None = None,
) -> None:
    """Configure async logging with a QueueHandler/QueueListener pair.

    Args:
        level: Root logger level.
        enable_console: Attach a console handler (Rich or fallback).
        log_file: Path to JSON log file. None = no file logging.
        max_bytes: Max bytes per log file before rotation.
        backup_count: Number of rotated backup files to keep.
        use_utc: Timestamps in JSON log are UTC when True, local time when False.
        extra_handlers: Additional handlers to include in the listener.
    """
    global _listener, _active_handlers

    # Shut down any existing listener first (idempotent re-setup)
    shutdown_logging()

    downstream_handlers: list[logging.Handler] = []

    if enable_console:
        downstream_handlers.append(_make_console_handler(level))

    if log_file is not None:
        downstream_handlers.append(
            _make_file_handler(log_file, level, max_bytes, backup_count, use_utc)
        )

    if extra_handlers:
        downstream_handlers.extend(extra_handlers)

    _active_handlers = downstream_handlers

    # Wire up: root logger → QueueHandler → QueueListener → real handlers
    log_queue: queue.Queue[logging.LogRecord] = queue.Queue(-1)

    root = logging.getLogger()
    root.setLevel(level)
    # Clear any existing handlers on root
    for h in root.handlers[:]:
        root.removeHandler(h)

    queue_handler = logging.handlers.QueueHandler(log_queue)
    root.addHandler(queue_handler)

    _listener = logging.handlers.QueueListener(
        log_queue,
        *downstream_handlers,
        respect_handler_level=True,
    )
    _listener.start()
    atexit.unregister(shutdown_logging)
    atexit.register(shutdown_logging)


def shutdown_logging() -> None:
    """Stop the QueueListener and flush all handlers. Idempotent."""
    global _listener, _active_handlers
    if _listener is not None:
        _listener.stop()
        _listener = None
    for h in _active_handlers:
        try:
            h.flush()
            h.close()
        except Exception:
            pass
    _active_handlers = []


def get_logger(name: str | None = None) -> logging.Logger:
    """Get a named logger. If name is None, uses the caller's module name."""
    if name is None:
        frame = inspect.stack()[1]
        name = frame[0].f_globals.get("__name__", __name__)
    return logging.getLogger(name)


def _get_active_handlers() -> list[logging.Handler]:
    """Return the list of downstream handlers (for testing/introspection)."""
    return list(_active_handlers)


# %% [markdown]
# # Show usage
# %%
if __name__ == "__main__":
    setup_logging(log_file="app.log", level=logging.DEBUG, use_utc=False)
    logger = get_logger(__name__)
    logger.info("Hello from ml_utils.logger!")
    logger.debug(
        "This is a debug message with extra context",
        extra={"user_id": 123, "operation": "test_logging"},
    )
    try:
        1 / 0  # noqa: B018 — intentional demo of exception logging
    except ZeroDivisionError:
        logger.exception("An error occurred")
    shutdown_logging()
