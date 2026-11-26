"""Shared pytest fixtures."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest

from evooptlab.utils.logging import ROOT_LOGGER_NAME

REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture
def configs_dir() -> Path:
    return REPO_ROOT / "configs"


@pytest.fixture
def synthetic_mixed_task(monkeypatch: pytest.MonkeyPatch) -> str:
    """The synthetic mixed-type HPO task from ``hpo_helpers``, registered for one test."""
    from hpo_helpers import register_synthetic

    return register_synthetic(monkeypatch)


@pytest.fixture(autouse=True)
def _reset_package_logger() -> Iterator[None]:
    """Undo ``configure_logging`` so handlers never leak between tests."""
    yield
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
    logger.setLevel(logging.NOTSET)
    logger.propagate = True
