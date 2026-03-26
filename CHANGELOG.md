# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-03-26

### Added
- Async logging pipeline using `QueueHandler` / `QueueListener` for non-blocking log I/O
- `JsonFormatter` — structured JSON log lines with timestamp, level, logger, module, function, line, message, and arbitrary `extra` fields
- `_RealFuncFilter` — patches `record.funcName` at filter-time so decorated functions appear under their real name instead of `wrapper`
- `get_logger(name)` — returns a logger with the real-function-name filter pre-attached
- `setup_logging()` — configures the async pipeline with optional Rich console handler and rotating JSON file handler
- `shutdown_logging()` — stops the background listener; also registered via `atexit`
- `@time_it` decorator — logs execution duration at `DEBUG` with `duration_s` in JSON extras
- `@log_it` decorator — logs function entry (`→`) and exit (`←`) with configurable level, optional argument repr, and optional return-value repr
- `log_result` parameter on `@log_it` — compact return-value repr: primitives via `repr()`, collections as `type[inner](N items)`, custom objects as `ClassName(...)`
- `Stage` enum — `dev` (default), `pre_prod`, `prod`
- `STAGE_PRESETS` — per-stage logging config (level, console, UTC, decorators\_active)
- `get_stage()` — reads `STAGE` env var, returns `Stage` member; defaults to `Stage.DEV`
- `init()` — single-call setup: resolves stage from env var, applies preset, configures logging
- Decoration-time no-op: when `STAGE=prod`, `@time_it` and `@log_it` return the original function unwrapped — zero per-call overhead
- `BaseConfigWithYaml` — Pydantic `BaseSettings` subclass with YAML file support; priority: CLI > kwargs > env vars > YAML > `.env` > defaults
- `py.typed` marker — PEP 561 typed package

[Unreleased]: https://github.com/sahil-maheshwari/ml-utils/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/sahil-maheshwari/ml-utils/releases/tag/v0.1.0
