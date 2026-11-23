"""Structured logging.

Two output formats are supported:

* ``json``: one JSON object per line (machine-readable; the default for run logs).
* ``text``: human-readable, for interactive use.

Structured context is attached with the standard ``extra`` mechanism, e.g.::

    log = get_logger(__name__)
    log.info("run started", extra={"run_id": run_id, "seed": 11})

Any key passed through ``extra`` appears as a top-level field in JSON output.
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import UTC, datetime
from typing import Any, Literal, TextIO

LogFormat = Literal["json", "text"]

ROOT_LOGGER_NAME = "evooptlab"

# Attributes present on every LogRecord; anything else came from ``extra``.
_RESERVED_RECORD_ATTRS: frozenset[str] = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", None, None)).keys() | {"message", "asctime"}
)


class JsonFormatter(logging.Formatter):
    """Format log records as single-line JSON objects with UTC timestamps."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.fromtimestamp(record.created, tz=UTC).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in vars(record).items():
            if key not in _RESERVED_RECORD_ATTRS and not key.startswith("_"):
                payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)


class TextFormatter(logging.Formatter):
    """Human-readable format that still shows structured ``extra`` fields."""

    def __init__(self) -> None:
        super().__init__(fmt="%(asctime)s %(levelname)-8s %(name)s: %(message)s")

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        extras = {
            k: v
            for k, v in vars(record).items()
            if k not in _RESERVED_RECORD_ATTRS and not k.startswith("_")
        }
        if extras:
            base += " " + " ".join(f"{k}={v!r}" for k, v in sorted(extras.items()))
        return base


def configure_logging(
    level: str | int = "INFO",
    fmt: LogFormat = "json",
    stream: TextIO | None = None,
) -> logging.Logger:
    """Configure the package root logger. Safe to call repeatedly (handlers are replaced).

    Only the ``evooptlab`` logger hierarchy is configured; the global root logger is untouched so
    that importing EvoOptLab as a library never hijacks an application's logging.
    """
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    handler = logging.StreamHandler(stream if stream is not None else sys.stderr)
    handler.setFormatter(JsonFormatter() if fmt == "json" else TextFormatter())
    logger.addHandler(handler)
    logger.setLevel(level.upper() if isinstance(level, str) else level)
    logger.propagate = False
    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a logger inside the ``evooptlab`` hierarchy."""
    if name == ROOT_LOGGER_NAME or name.startswith(ROOT_LOGGER_NAME + "."):
        return logging.getLogger(name)
    return logging.getLogger(f"{ROOT_LOGGER_NAME}.{name}")
