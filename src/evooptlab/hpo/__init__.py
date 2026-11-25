"""Hyperparameter optimization on real tabular tasks (Phase 05, ADR 0006)."""

from __future__ import annotations

from evooptlab.hpo.datasets import CATALOG, Dataset, DatasetError, TaskDefinition, fetch, load
from evooptlab.hpo.problem import (
    HPOProblem,
    SplitIndices,
    cv_folds,
    evaluate_on_test,
    select_trial,
    split_indices,
)
from evooptlab.hpo.search_space import SearchSpace

__all__ = [
    "CATALOG",
    "Dataset",
    "DatasetError",
    "HPOProblem",
    "SearchSpace",
    "SplitIndices",
    "TaskDefinition",
    "cv_folds",
    "evaluate_on_test",
    "fetch",
    "load",
    "select_trial",
    "split_indices",
]
