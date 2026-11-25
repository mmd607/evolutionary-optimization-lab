"""Small, offline HPO fixtures: the bundled breast-cancer task and a synthetic mixed-type task."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from evooptlab.config.schemas import HPOProblemConfig
from evooptlab.hpo import datasets
from evooptlab.hpo.datasets import Dataset, TaskDefinition

TINY_SPACE: dict[str, Any] = {
    "learning_rate": {"type": "float", "low": 0.05, "high": 0.3, "log": True},
    "max_iter": {"type": "int", "low": 3, "high": 10},
    "max_leaf_nodes": {"type": "int", "low": 4, "high": 8},
}


def hpo_config(**overrides: Any) -> HPOProblemConfig:
    base: dict[str, Any] = {
        "name": "bc-tiny",
        "task": "breast_cancer_smoke",
        "task_type": "classification",
        "target_metric": "f1_macro",
        "objectives": ["validation_error"],
        "model": "hist_gradient_boosting",
        "model_seed": 0,
        "search_space": TINY_SPACE,
        "split": {"strategy": "stratified", "test_fraction": 0.2, "random_seed": 2026},
        "cv": {"strategy": "stratified_kfold", "n_splits": 3, "random_seed": 2026},
    }
    base.update(overrides)
    return HPOProblemConfig.model_validate(base)


N_MIXED = 120
N_MIXED_TEST = 30  # ordered split with test_fraction 0.25 holds out the last 30 rows


def mixed_dataset() -> Dataset:
    """Numeric + categorical features; category 'test_only' occurs only in the test rows."""
    rng = np.random.default_rng(0)
    colour = rng.choice(["red", "green", "blue"], size=N_MIXED).astype(object)
    colour[-N_MIXED_TEST:] = "test_only"
    numeric = rng.normal(size=N_MIXED)
    X = np.empty((N_MIXED, 2), dtype=object)
    X[:, 0] = colour
    X[:, 1] = numeric
    y = (numeric + (colour == "red") > 0.3).astype(np.int64)
    return Dataset("synthetic_mixed", None, X, y, ("colour", "value"), (0,))


SYNTHETIC = TaskDefinition(
    name="synthetic_mixed",
    title="synthetic mixed-type test task (tests only)",
    homepage="-",
    license="-",
    citation="-",
    doi=None,
    task_types=("classification",),
    loader_version="synthetic_mixed/v1",
    parse=lambda raw, variant: mixed_dataset(),
)


def register_synthetic(monkeypatch: pytest.MonkeyPatch, task: TaskDefinition = SYNTHETIC) -> str:
    """Add a test-only task to the catalogue for the duration of one test."""
    monkeypatch.setitem(datasets.CATALOG, task.name, task)
    return task.name


def mixed_config(**overrides: Any) -> HPOProblemConfig:
    values: dict[str, Any] = {
        "name": "mixed-tiny",
        "task": "synthetic_mixed",
        "split": {"strategy": "ordered", "test_fraction": 0.25, "random_seed": 0},
        "cv": {"strategy": "kfold", "n_splits": 3, "random_seed": 1},
    }
    values.update(overrides)
    return hpo_config(**values)
