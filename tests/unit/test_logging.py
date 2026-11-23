"""Tests for structured logging."""

from __future__ import annotations

import io
import json
import logging
from collections.abc import Iterator

import pytest

from evooptlab.utils.logging import ROOT_LOGGER_NAME, configure_logging, get_logger


@pytest.fixture(autouse=True)
def _reset_logger() -> Iterator[None]:
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True


def test_json_lines_include_extra_fields() -> None:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    get_logger("core").info("run started", extra={"run_id": "abc", "seed": 11})

    record = json.loads(stream.getvalue().strip())
    assert record["message"] == "run started"
    assert record["level"] == "INFO"
    assert record["logger"] == "evooptlab.core"
    assert record["run_id"] == "abc"
    assert record["seed"] == 11
    assert record["ts"].endswith("+00:00")


def test_level_filters_records() -> None:
    stream = io.StringIO()
    configure_logging("WARNING", "json", stream)
    log = get_logger("x")
    log.info("hidden")
    log.warning("shown")
    lines = stream.getvalue().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["message"] == "shown"


def test_exceptions_are_serialized() -> None:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        get_logger("x").exception("failed")
    record = json.loads(stream.getvalue())
    assert "RuntimeError: boom" in record["exc_info"]


def test_text_format_shows_extras() -> None:
    stream = io.StringIO()
    configure_logging("DEBUG", "text", stream)
    get_logger("x").debug("hello", extra={"seed": 3})
    line = stream.getvalue()
    assert "hello" in line
    assert "seed=3" in line


def test_reconfiguring_does_not_duplicate_handlers() -> None:
    stream = io.StringIO()
    configure_logging("INFO", "json", stream)
    configure_logging("INFO", "json", stream)
    get_logger("x").info("once")
    assert len(stream.getvalue().strip().splitlines()) == 1


def test_root_logger_is_untouched() -> None:
    before = list(logging.getLogger().handlers)
    configure_logging("INFO", "json", io.StringIO())
    assert logging.getLogger().handlers == before


def test_get_logger_namespacing() -> None:
    assert get_logger("evooptlab").name == "evooptlab"
    assert get_logger("evooptlab.core").name == "evooptlab.core"
    assert get_logger("thirdparty").name == "evooptlab.thirdparty"
