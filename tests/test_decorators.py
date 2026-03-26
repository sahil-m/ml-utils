"""Tests for ml_utils.decorators — _repr_result, time_it, log_it, and no-op behavior."""

from __future__ import annotations

import importlib
import logging
import os
import time
from unittest.mock import patch

import pytest

from ml_utils.decorators import _repr_result, log_it, time_it
from ml_utils.logger import setup_logging, shutdown_logging


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
# _repr_result
# ===========================================================================
class TestReprResult:
    def test_none(self):
        assert _repr_result(None) == "None"

    def test_bool(self):
        assert _repr_result(True) == "True"

    def test_int(self):
        assert _repr_result(42) == "42"

    def test_float(self):
        assert _repr_result(3.14) == "3.14"

    def test_string(self):
        assert _repr_result("hello") == "'hello'"

    def test_list_with_types(self):
        assert _repr_result([1, 2, 3]) == "list[int](3 items)"

    def test_tuple_with_mixed_types(self):
        result = _repr_result((1, "a"))
        assert result.startswith("tuple[")
        assert "2 items" in result
        assert "int" in result
        assert "str" in result

    def test_set_with_types(self):
        result = _repr_result({1.0, 2.0})
        assert result == "set[float](2 items)"

    def test_dict_with_types(self):
        assert _repr_result({"a": 1, "b": 2}) == "dict[str, int](2 items)"

    def test_empty_collection(self):
        assert _repr_result([]) == "list[empty](0 items)"

    def test_empty_dict(self):
        assert _repr_result({}) == "dict[empty, empty](0 items)"

    def test_custom_object(self):
        class MyClass:
            pass

        assert _repr_result(MyClass()) == "MyClass(...)"


# ===========================================================================
# time_it
# ===========================================================================
class TestTimeIt:
    def test_logs_duration_at_debug(self, caplog):

        @time_it
        def fast():
            return 42

        with caplog.at_level(logging.DEBUG):
            result = fast()

        assert result == 42
        duration_records = [r for r in caplog.records if "finished in" in r.message]
        assert len(duration_records) >= 1
        assert duration_records[0].levelno == logging.DEBUG

    def test_preserves_function_metadata(self):
        @time_it
        def my_func():
            """My docstring."""

        assert my_func.__name__ == "my_func"
        assert my_func.__doc__ == "My docstring."

    def test_records_timing_on_exception(self, caplog):

        @time_it
        def failing():
            raise ValueError("boom")

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(ValueError, match="boom"):
                failing()

        duration_records = [r for r in caplog.records if "finished in" in r.message]
        assert len(duration_records) >= 1

    def test_funcname_is_original(self, caplog):

        @time_it
        def original_name():
            pass

        with caplog.at_level(logging.DEBUG):
            original_name()

        duration_records = [r for r in caplog.records if "finished in" in r.message]
        assert len(duration_records) >= 1
        assert duration_records[0].funcName == "original_name"


# ===========================================================================
# log_it
# ===========================================================================
class TestLogIt:
    def test_bare_usage_logs_entry_exit(self, caplog):

        @log_it
        def greet():
            return "hi"

        with caplog.at_level(logging.DEBUG):
            result = greet()

        assert result == "hi"
        messages = [r.message for r in caplog.records]
        assert any("→" in m and "greet" in m for m in messages)
        assert any("←" in m and "greet" in m for m in messages)

    def test_log_args_true_includes_args(self, caplog):

        @log_it(log_args=True)
        def add(x, y):
            return x + y

        with caplog.at_level(logging.DEBUG):
            add(3, 4)

        entry_records = [r for r in caplog.records if "→" in r.message]
        assert len(entry_records) >= 1
        assert "3" in entry_records[0].message
        assert "4" in entry_records[0].message

    def test_log_result_true_includes_result(self, caplog):

        @log_it(log_result=True)
        def compute():
            return 42

        with caplog.at_level(logging.DEBUG):
            compute()

        exit_records = [r for r in caplog.records if "←" in r.message]
        assert len(exit_records) >= 1
        assert "42" in exit_records[0].message

    def test_custom_level(self, caplog):

        @log_it(level=logging.INFO)
        def work():
            pass

        with caplog.at_level(logging.DEBUG):
            work()

        log_it_records = [r for r in caplog.records if "work" in r.message]
        assert all(r.levelno == logging.INFO for r in log_it_records)

    def test_exception_logged_and_reraised(self, caplog):

        @log_it
        def failing():
            raise RuntimeError("fail")

        with caplog.at_level(logging.DEBUG):
            with pytest.raises(RuntimeError, match="fail"):
                failing()

        error_records = [r for r in caplog.records if "✗" in r.message]
        assert len(error_records) >= 1
        assert "RuntimeError" in error_records[0].message

    def test_bare_and_parameterized_equivalent(self, caplog):

        @log_it
        def fn_bare():
            return 1

        @log_it()
        def fn_param():
            return 2

        with caplog.at_level(logging.DEBUG):
            fn_bare()
            fn_param()

        bare_records = [r for r in caplog.records if "fn_bare" in r.message]
        param_records = [r for r in caplog.records if "fn_param" in r.message]
        # Both produce entry + exit messages
        assert len(bare_records) == 2
        assert len(param_records) == 2


# ===========================================================================
# Decorator no-op when STAGE=prod
# ===========================================================================
class TestDecoratorNoOp:
    def test_decorators_active_by_default(self):
        """Without STAGE env var, decorators are active."""
        import ml_utils.decorators as mod

        with patch.dict(os.environ, {}, clear=True):
            importlib.reload(mod)
            assert mod._DECORATORS_ACTIVE is True

    def test_decorators_active_when_stage_debug(self):
        """STAGE=debug means decorators are active."""
        import ml_utils.decorators as mod

        with patch.dict(os.environ, {"STAGE": "debug"}):
            importlib.reload(mod)
            assert mod._DECORATORS_ACTIVE is True

    def test_decorators_inactive_when_stage_prod(self):
        """STAGE=prod means decorators are inactive."""
        import ml_utils.decorators as mod

        with patch.dict(os.environ, {"STAGE": "prod"}):
            importlib.reload(mod)
            assert mod._DECORATORS_ACTIVE is False

    def test_time_it_noop_when_inactive(self):
        """time_it returns the unwrapped function when STAGE=prod."""
        import ml_utils.decorators as mod

        with patch.dict(os.environ, {"STAGE": "prod"}):
            importlib.reload(mod)

            def my_func():
                return 99

            decorated = mod.time_it(my_func)
            assert decorated is my_func
            assert decorated() == 99

    def test_log_it_noop_when_inactive(self):
        """log_it returns the unwrapped function when STAGE=prod."""
        import ml_utils.decorators as mod

        with patch.dict(os.environ, {"STAGE": "prod"}):
            importlib.reload(mod)

            def my_func():
                return 77

            decorated = mod.log_it(my_func)
            assert decorated is my_func
            assert decorated() == 77
