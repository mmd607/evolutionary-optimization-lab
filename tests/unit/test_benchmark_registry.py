"""Tests for the benchmark registry and suite-config validation."""

from __future__ import annotations

from pathlib import Path

import pytest

from evooptlab.benchmarks.registry import BENCHMARK_NAMES, build_suite, get_problem
from evooptlab.config import BenchmarksFile, load_config


def test_repository_suite_builds(configs_dir: Path) -> None:
    cfg = load_config(configs_dir / "benchmarks.yaml")
    assert isinstance(cfg, BenchmarksFile)
    problems = build_suite(cfg.benchmark_suite)
    dims = {p.name: (p.spec.n_variables, p.spec.n_objectives) for p in problems}
    assert dims == {
        "ZDT1": (30, 2),
        "ZDT2": (30, 2),
        "ZDT3": (30, 2),
        "DTLZ2": (12, 3),
        "DTLZ7": (22, 3),
    }


def test_dtlz_k_follows_variables() -> None:
    assert get_problem("DTLZ2", 7, 3).spec.metadata["k"] == 5


@pytest.mark.parametrize(
    ("name", "n_var", "n_obj", "match"),
    [
        ("ZDT1", 30, 3, "bi-objective"),
        ("DTLZ2", 2, 3, "n_variables must be >= n_objectives"),
        ("sphere", 3, 1, "unknown benchmark"),
        ("WFG1", 10, 2, "unknown benchmark"),
    ],
)
def test_mismatches_fail_early(name: str, n_var: int, n_obj: int, match: str) -> None:
    with pytest.raises(ValueError, match=match):
        get_problem(name, n_var, n_obj)


def test_names() -> None:
    assert BENCHMARK_NAMES == ("ZDT1", "ZDT2", "ZDT3", "DTLZ2", "DTLZ7")
