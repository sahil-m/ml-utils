"""ml-utils — ML utilities for configuration, logging, and decorators."""

from importlib.metadata import version

from ml_utils.base_config import BaseConfigWithYaml
from ml_utils.decorators import log_it, time_it
from ml_utils.logger import get_logger, setup_logging, shutdown_logging
from ml_utils.stage import Stage, get_stage, init

__version__: str = version("ml-utils")

__all__ = [
    "__version__",
    "BaseConfigWithYaml",
    "Stage",
    "get_logger",
    "get_stage",
    "init",
    "log_it",
    "setup_logging",
    "shutdown_logging",
    "time_it",
]
