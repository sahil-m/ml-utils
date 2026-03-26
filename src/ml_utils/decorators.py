from __future__ import annotations

import functools
import logging
import os
import time
from collections.abc import Callable
from typing import Any, TypeVar

from ml_utils.logger import get_logger

_DECORATORS_ACTIVE: bool = os.environ.get("STAGE", "dev").strip().lower() != "prod"

F = TypeVar("F", bound=Callable[..., Any])


class _RealFuncFilter(logging.Filter):
    """Patch funcName on records that carry a _real_func_name sentinel in extra.

    Python's makeRecord blocks overwriting built-in fields via extra={}, so we
    use a filter (runs before the record enters the queue) to swap the value in.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        real = record.__dict__.pop("_real_func_name", None)
        if real is not None:
            record.funcName = real
        return True


_REAL_FUNC_FILTER = _RealFuncFilter()
# logging.Filterer.addFilter() deduplicates by object identity, so attaching
# the same singleton repeatedly is always a no-op.

_PRIMITIVES = (type(None), bool, int, float, str)
_COLLECTIONS = (list, tuple, set, frozenset)


def _repr_result(val: Any) -> str:
    """Compact, safe representation of a return value for log output.

    - Primitives            → repr(val)                        e.g. 42, 'hi'
    - list/tuple/set/frozenset → type + inner types + length   e.g. list[int](5 items)
    - dict                  → type + key/val types + length    e.g. dict[str, float](3 items)
    - anything else         → just the class name              e.g. DataFrame(...)
    """
    if isinstance(val, _PRIMITIVES):
        return repr(val)
    if isinstance(val, _COLLECTIONS):
        inner = ", ".join(sorted({type(v).__name__ for v in val})) or "empty"
        return f"{type(val).__name__}[{inner}]({len(val)} items)"
    if isinstance(val, dict):
        key_types = ", ".join(sorted({type(k).__name__ for k in val})) or "empty"
        val_types = ", ".join(sorted({type(v).__name__ for v in val.values()})) or "empty"
        return f"dict[{key_types}, {val_types}]({len(val)} items)"
    return f"{type(val).__name__}(...)"


def is_decorators_active() -> bool:
    """Return whether decorators are currently active."""
    return _DECORATORS_ACTIVE


def time_it[F: Callable[..., Any]](func: F) -> F:
    """Log the execution time of the decorated function.

    Uses the decorated function's own module logger so the log line
    shows the correct logger name, not 'ml_utils.decorators'.
    Returns the function unwrapped when ``STAGE=prod`` (zero overhead).
    """
    if not _DECORATORS_ACTIVE:
        return func

    log = get_logger(func.__module__)
    log.addFilter(_REAL_FUNC_FILTER)

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        start = time.perf_counter()
        try:
            return func(*args, **kwargs)
        finally:
            elapsed = time.perf_counter() - start
            log.debug(
                "%s finished in %.4fs",
                func.__qualname__,
                elapsed,
                extra={"duration_s": round(elapsed, 6), "_real_func_name": func.__name__},
            )

    return wrapper  # type: ignore[return-value]


def log_it[F: Callable[..., Any]](
    func: F | None = None,
    *,
    level: int = logging.DEBUG,
    log_args: bool = False,
    log_result: bool = False,
) -> Any:
    """Log entry and exit of the decorated function.

    Can be used bare or with options:

        @log_it
        def fn(): ...

        @log_it(level=logging.INFO, log_args=True, log_result=True)
        def fn(x, y): ...

    Args:
        level:      Severity level for entry/exit messages.
        log_args:   When True, include positional and keyword arguments in the
                    entry log line. Disable for functions that receive secrets
                    or large objects.
        log_result: When True, include a compact representation of the return
                    value. Primitives (None/bool/int/float/str) are shown via
                    repr(); collections show their element type(s) and length;
                    all other types are reduced to just the class name.
    """

    def decorator(f: F) -> F:
        if not _DECORATORS_ACTIVE:
            return f

        log = get_logger(f.__module__)
        log.addFilter(_REAL_FUNC_FILTER)

        _extra = {"_real_func_name": f.__name__}

        @functools.wraps(f)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            if log_args:
                arg_str = ", ".join(
                    [repr(a) for a in args] + [f"{k}={v!r}" for k, v in kwargs.items()]
                )
                log.log(level, "→ %s(%s)", f.__qualname__, arg_str, extra=_extra)
            else:
                log.log(level, "→ %s called", f.__qualname__, extra=_extra)

            try:
                result = f(*args, **kwargs)
                if log_result:
                    log.log(level, "← %s returned %s", f.__qualname__, _repr_result(result), extra=_extra)
                else:
                    log.log(level, "← %s returned", f.__qualname__, extra=_extra)
                return result
            except Exception as exc:
                log.exception("✗ %s raised %s", f.__qualname__, type(exc).__name__, extra=_extra)
                raise

        return wrapper  # type: ignore[return-value]

    # Support both @log_it and @log_it(level=...) usage
    if func is not None:
        return decorator(func)
    return decorator


if __name__ == "__main__":
    from time import sleep

    # from ml_utils.logger import setup_logging, shutdown_logging
    # setup_logging(log_file="decorators.log", level=logging.DEBUG, use_utc=False)
    # or
    from ml_utils.stage import init
    init(log_file="decorators.log")
    from ml_utils.logger import shutdown_logging

    @time_it
    def slow_function():
        sleep(0.5)

    @log_it(level=logging.INFO, log_args=True)
    def add(x: int, y: int) -> int:
        return x + y

    @log_it(level=logging.INFO, log_args=True, log_result=True)
    def subtract(x: int, y: int) -> int:
        return x - y

    @log_it(log_result=True)
    def summarise(data: list[int]) -> dict:
        return {"count": len(data), "total": sum(data)}

    @time_it
    @log_it
    def process(data: list) -> int:
        sleep(0.1)
        return len(data)

    slow_function()
    add(3, 4)
    subtract(10, 5)
    summarise([10, 20, 30])
    process([1, 2, 3])

    shutdown_logging()
