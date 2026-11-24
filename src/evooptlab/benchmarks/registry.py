"""Build benchmark problems by name and validate benchmark-suite configs against them."""

from __future__ import annotations

from collections.abc import Callable

from evooptlab.benchmarks.dtlz import DTLZ2, DTLZ7
from evooptlab.benchmarks.zdt import ZDT1, ZDT2, ZDT3
from evooptlab.config.schemas import BenchmarkProblemConfig, BenchmarkSuiteConfig
from evooptlab.core.problem import Problem

_ZDT: dict[str, Callable[[int], Problem]] = {"ZDT1": ZDT1, "ZDT2": ZDT2, "ZDT3": ZDT3}
_DTLZ: dict[str, Callable[[int, int], Problem]] = {
    "DTLZ2": lambda m, n: DTLZ2(m, n),
    "DTLZ7": lambda m, n: DTLZ7(m, n),
}

#: Names accepted by :func:`get_problem` (framework-test problems are deliberately excluded).
BENCHMARK_NAMES: tuple[str, ...] = (*_ZDT, *_DTLZ)


def get_problem(name: str, n_variables: int, n_objectives: int) -> Problem:
    """Instantiate a benchmark problem; dimensions are explicit so configs stay authoritative."""
    if name in _ZDT:
        if n_objectives != 2:
            raise ValueError(f"{name} is bi-objective; config says {n_objectives} objectives")
        return _ZDT[name](n_variables)
    if name in _DTLZ:
        return _DTLZ[name](n_objectives, n_variables)
    raise ValueError(f"unknown benchmark {name!r}; available: {', '.join(BENCHMARK_NAMES)}")


def build_problem(entry: BenchmarkProblemConfig) -> Problem:
    return get_problem(entry.name, entry.variables, entry.objectives)


def build_suite(suite: BenchmarkSuiteConfig) -> list[Problem]:
    """Instantiate every problem of a validated suite config, failing early on any mismatch."""
    return [build_problem(entry) for entry in suite.problems]
