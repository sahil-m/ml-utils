"""Stage-based configuration presets for logging and decorators.

Reads the ``STAGE`` environment variable to determine which preset to apply.
Valid values: ``dev`` (default), ``pre_prod``, ``prod``.

Usage::

    from ml_utils.stage import init

    init()                      # reads STAGE env var
    init(stage="prod")          # explicit override
    init(log_file="app.log")    # passes through to setup_logging
"""

from __future__ import annotations

import logging
import os
from enum import Enum
from pathlib import Path
from typing import Any

from ml_utils.logger import setup_logging


class Stage(Enum):
    """Deployment stages that control logging and decorator behavior."""

    DEV = "dev"
    PRE_PROD = "pre_prod"
    PROD = "prod"


STAGE_PRESETS: dict[Stage, dict[str, Any]] = {
    Stage.DEV: {
        "level": logging.DEBUG,
        "enable_console": True,
        "use_utc": False,
        "decorators_active": True,
    },
    Stage.PRE_PROD: {
        "level": logging.INFO,
        "enable_console": True,
        "use_utc": True,
        "decorators_active": True,
    },
    Stage.PROD: {
        "level": logging.WARNING,
        "enable_console": False,
        "use_utc": True,
        "decorators_active": False,
    },
}


def get_stage() -> Stage:
    """Read the ``STAGE`` env var and return the corresponding enum member.

    Returns ``Stage.DEV`` when the variable is unset or empty.
    Raises ``ValueError`` for unrecognised values.
    """
    raw = os.environ.get("STAGE", "dev").strip().lower()
    return Stage(raw)


def init(
    *,
    stage: Stage | str | None = None,
    log_file: str | Path | None = None,
    **logging_overrides: Any,
) -> None:
    """One-call setup: resolve stage, configure logging.

    Args:
        stage: Explicit stage override. When ``None``, reads ``STAGE`` env var.
               Accepts a :class:`Stage` member or its string value.
        log_file: Path forwarded to :func:`setup_logging`.
        **logging_overrides: Extra keyword arguments merged into the preset and
                             forwarded to :func:`setup_logging` (e.g.
                             ``max_bytes``, ``backup_count``, ``extra_handlers``).
    """
    if stage is None:
        resolved = get_stage()
    elif isinstance(stage, str):
        resolved = Stage(stage.strip().lower())
    else:
        resolved = stage

    preset = {**STAGE_PRESETS[resolved]}
    # decorators_active is informational in the preset; don't pass to setup_logging
    preset.pop("decorators_active", None)

    preset.update(logging_overrides)
    if log_file is not None:
        preset["log_file"] = log_file

    setup_logging(**preset)
