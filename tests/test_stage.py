"""Tests for ml_utils.stage — Stage enum, presets, get_stage(), and init()."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from unittest.mock import patch

import pytest

from ml_utils.logger import shutdown_logging


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


# ===========================================================================
# Stage enum
# ===========================================================================
class TestStageEnum:
    def test_values(self):
        from ml_utils.stage import Stage

        assert Stage.DEV.value == "dev"
        assert Stage.PRE_PROD.value == "pre_prod"
        assert Stage.PROD.value == "prod"

    def test_from_string(self):
        from ml_utils.stage import Stage

        assert Stage("dev") is Stage.DEV
        assert Stage("pre_prod") is Stage.PRE_PROD
        assert Stage("prod") is Stage.PROD


# ===========================================================================
# Stage presets
# ===========================================================================
class TestStagePresets:
    def test_dev_preset(self):
        from ml_utils.stage import STAGE_PRESETS, Stage

        p = STAGE_PRESETS[Stage.DEV]
        assert p["level"] == logging.DEBUG
        assert p["enable_console"] is True
        assert p["use_utc"] is False
        assert p["decorators_active"] is True

    def test_pre_prod_preset(self):
        from ml_utils.stage import STAGE_PRESETS, Stage

        p = STAGE_PRESETS[Stage.PRE_PROD]
        assert p["level"] == logging.INFO
        assert p["enable_console"] is True
        assert p["use_utc"] is True
        assert p["decorators_active"] is True

    def test_prod_preset(self):
        from ml_utils.stage import STAGE_PRESETS, Stage

        p = STAGE_PRESETS[Stage.PROD]
        assert p["level"] == logging.WARNING
        assert p["enable_console"] is False
        assert p["use_utc"] is True
        assert p["decorators_active"] is False


# ===========================================================================
# get_stage()
# ===========================================================================
class TestGetStage:
    def test_reads_env_var(self):
        from ml_utils.stage import Stage, get_stage

        with patch.dict(os.environ, {"STAGE": "prod"}):
            assert get_stage() is Stage.PROD

    def test_default_is_dev(self):
        from ml_utils.stage import Stage, get_stage

        with patch.dict(os.environ, {}, clear=True):
            assert get_stage() is Stage.DEV

    def test_unknown_value_raises(self):
        from ml_utils.stage import get_stage

        with patch.dict(os.environ, {"STAGE": "banana"}):
            with pytest.raises(ValueError):
                get_stage()


# ===========================================================================
# init()
# ===========================================================================
class TestInit:
    def test_init_reads_stage_env_var(self):
        from ml_utils.stage import init

        with patch.dict(os.environ, {"STAGE": "prod"}):
            init()

        assert logging.getLogger().level == logging.WARNING

    def test_init_default_is_dev(self):
        from ml_utils.stage import init

        with patch.dict(os.environ, {}, clear=True):
            init()

        assert logging.getLogger().level == logging.DEBUG

    def test_init_configures_logging(self):
        from ml_utils.stage import Stage, init

        init(stage=Stage.PRE_PROD)
        assert logging.getLogger().level == logging.INFO

    def test_init_accepts_log_file(self, tmp_path: Path):
        from ml_utils.stage import init

        log_file = tmp_path / "test.log"
        with patch.dict(os.environ, {}, clear=True):
            init(log_file=log_file)

        logger = logging.getLogger("test.init")
        logger.info("hello")
        shutdown_logging()
        assert log_file.exists()
        assert "hello" in log_file.read_text()

    def test_init_accepts_stage_override(self):
        from ml_utils.stage import Stage, init

        with patch.dict(os.environ, {"STAGE": "dev"}):
            init(stage=Stage.PROD)

        # Stage override wins over env var
        assert logging.getLogger().level == logging.WARNING
