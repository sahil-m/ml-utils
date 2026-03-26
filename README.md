# ml-utils

[![CI](https://github.com/sahil-m/ml-utils/actions/workflows/ci.yml/badge.svg)](https://github.com/sahil-m/ml-utils/actions/workflows/ci.yml)
[![Python 3.12+](https://img.shields.io/badge/python-3.12%2B-blue)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

ML utilities for configuration management, async logging, and function decorators.

## Installation

Install directly from GitHub (not yet on PyPI):

```bash
uv add "ml-utils @ git+https://github.com/sahil-m/ml-utils.git"
```

Or pin to a specific tag:

```bash
uv add "ml-utils @ git+https://github.com/sahil-m/ml-utils.git@v0.1.0"
```

## Quick Start

```python
from ml_utils import init, get_logger, time_it

init()  # reads STAGE env var, configures logging
logger = get_logger(__name__)

@time_it
def train_model(data):
    logger.info("Training started", extra={"samples": len(data)})
    # ... training logic ...
    return model

train_model(dataset)
```

## Stage System

The `STAGE` environment variable controls logging behaviour and decorator activation.

```bash
STAGE=dev uv run app.py    # development defaults
STAGE=pre_prod uv run app.py # staging environment
STAGE=prod uv run app.py     # production: quiet logging, decorators disabled
```

| Setting | `dev` (default) | `pre_prod` | `prod` |
|---|---|---|---|
| Log level | `DEBUG` | `INFO` | `WARNING` |
| Console output | On (Rich) | On (Rich) | Off |
| UTC timestamps | No (local) | Yes | Yes |
| Decorators active | Yes | Yes | **No** (zero overhead) |

### `init()` options

```python
from ml_utils import init, Stage

init()                                 # reads STAGE env var
init(stage=Stage.PROD)                 # explicit override, ignores env var
init(log_file="app.log")              # enable JSON file logging
init(log_file="app.log", max_bytes=5_000_000, backup_count=3)  # with rotation
```

`init()` is a convenience wrapper around `setup_logging()`. For full control,
call `setup_logging()` directly.

## Logging

Async logging pipeline: `logger.info("msg")` → `QueueHandler` (non-blocking) →
`QueueListener` (background thread) → console + file handlers.

### Direct setup (without stage presets)

```python
from ml_utils import setup_logging, get_logger, shutdown_logging
import logging

setup_logging(
    level=logging.INFO,
    enable_console=True,
    log_file="app.log",        # JSON lines, one object per line
    max_bytes=10_000_000,      # 10 MB per file
    backup_count=5,            # rotated backups
    use_utc=True,              # UTC timestamps in JSON
)

logger = get_logger(__name__)
logger.info("Hello", extra={"request_id": "abc-123"})

# At shutdown (also registered via atexit):
shutdown_logging()
```

### JSON log format

Each line in the log file is a JSON object:

```json
{"timestamp": "2026-03-26T12:00:00+00:00", "level": "INFO", "logger": "myapp.train", "module": "train", "function": "run", "line": 42, "message": "Hello", "request_id": "abc-123"}
```

### Log levels (lowest → highest)

| Level | Value | Use for |
|---|---|---|
| `DEBUG` | 10 | Detailed diagnostics, disabled in production |
| `INFO` | 20 | Normal operational events |
| `WARNING` | 30 | Unexpected but non-critical situations |
| `ERROR` | 40 | Failures that need attention |
| `CRITICAL` | 50 | Severe failures, application may not continue |

## Decorators

### `@time_it` — execution timing

```python
from ml_utils import time_it

@time_it
def train(data):
    # ... training logic ...
    return model
```

Logs at `DEBUG`: `train finished in 1.2345s` with `duration_s` in the JSON extra fields.

### `@log_it` — entry/exit logging

```python
from ml_utils import log_it
import logging

@log_it                                           # bare: logs at DEBUG
def process(data): ...

@log_it(level=logging.INFO, log_args=True)        # log arguments
def predict(x, y): ...

@log_it(log_result=True)                          # log return value
def summarise(data):
    return {"count": len(data), "total": sum(data)}
```

**Parameters:**

| Param | Default | Description |
|---|---|---|
| `level` | `DEBUG` | Log level for entry/exit messages |
| `log_args` | `False` | Include `repr()` of arguments in entry message |
| `log_result` | `False` | Include compact return value in exit message |

**`log_result` output format:** primitives use `repr()` (`42`, `'hello'`);
collections show type + inner types + length (`list[int](5 items)`,
`dict[str, float](3 items)`); custom objects show the class name (`DataFrame(...)`).

### Stacking decorators

```python
@time_it
@log_it
def pipeline(data):
    ...
```

### Production no-op

When `STAGE=prod`, both `@time_it` and `@log_it` return the original function
unwrapped — zero per-call overhead, no wrapper in the call stack.

## Configuration

`BaseConfigWithYaml` extends Pydantic's `BaseSettings` with YAML file support.

### Priority order (highest → lowest)

1. **CLI arguments**
2. **Instantiation arguments** (`MyConfig(field="value")`)
3. **Environment variables** (with configurable prefix)
4. **YAML config file**
5. **`.env` file**
6. **Default values**

### Usage

```python
from pydantic import Field
from pydantic_settings import SettingsConfigDict
from ml_utils import BaseConfigWithYaml
from pathlib import Path

class TrainConfig(BaseConfigWithYaml):
    learning_rate: float = Field(0.001, description="Learning rate")
    batch_size: int = Field(32, description="Batch size")
    epochs: int = Field(10, description="Number of epochs")

    model_config = SettingsConfigDict(
        env_prefix="TRAIN_",
        cli_parse_args=True,
    )

# Load from YAML
TrainConfig._yaml_file = Path("configs/train.yaml")
config = TrainConfig()
```

```yaml
# configs/train.yaml
learning_rate: 0.0003
batch_size: 64
epochs: 20
```

Override via CLI: `python train.py --batch_size 128`
Override via env: `TRAIN_BATCH_SIZE=128 python train.py`

## IDE Debugging

Set the `STAGE` env var in your VS Code debug configuration:

```json
// .vscode/launch.json
{
    "version": "0.2.0",
    "configurations": [
        {
            "name": "Python: Debug",
            "type": "debugpy",
            "request": "launch",
            "program": "${file}",
            "env": {
                "STAGE": "dev"
            }
        }
    ]
}
```
