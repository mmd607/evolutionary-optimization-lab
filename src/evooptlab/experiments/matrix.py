"""Expand a study config into its full, validated run matrix.

Design rules (ADR 0005):

* **Fail before running.** Unknown problems or algorithms, invalid hyperparameters, and
  algorithm/problem pairs outside an algorithm's valid domain are all reported together before a
  single evaluation is spent. Incompatible pairs are never skipped silently, because that would
  shrink the matrix without anyone noticing.
* **Paired seeds.** Replicate ``i`` of a problem uses the same run seed for every algorithm
  (common random numbers), so algorithms are compared on identical seed sets.
* **Interleaved order.** Cells run problem by problem, replicate by replicate, and every algorithm
  runs before the next replicate starts. Slow drift in machine load therefore spreads across
  algorithms instead of biasing whichever ran last.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from evooptlab.algorithms import get_algorithm
from evooptlab.benchmarks.registry import build_problem
from evooptlab.config.schemas import (
    BenchmarkProblemConfig,
    DerivedSeeds,
    StudyAlgorithmConfig,
    StudyConfig,
)
from evooptlab.core.algorithm import Algorithm
from evooptlab.core.experiment import ExperimentRunner, RunSpec, canonical_hash
from evooptlab.core.problem import Problem
from evooptlab.core.seeding import derive_run_seeds


class StudyError(ValueError):
    """Raised when a study cannot be planned, run, or aggregated safely."""


CellKey = tuple[str, str, int]  # (problem, algorithm, replicate)


@dataclass(frozen=True)
class RunCell:
    """One planned run: a (problem, algorithm, replicate) combination with its seed."""

    problem: BenchmarkProblemConfig
    algorithm: StudyAlgorithmConfig
    replicate: int
    seed: int

    @property
    def key(self) -> CellKey:
        return (self.problem.name, self.algorithm.name, self.replicate)

    def build_problem(self) -> Problem:
        return build_problem(self.problem)

    def build_algorithm(self) -> Algorithm:
        return get_algorithm(self.algorithm.name, **self.algorithm.parameters)


def replicate_seeds(study: StudyConfig, problem: str) -> list[int]:
    """Run seeds of one problem's replicates; identical for every algorithm."""
    if isinstance(study.seeds, DerivedSeeds):
        return derive_run_seeds(study.seeds.master_seed, study.seeds.n_replicates, problem)
    return list(study.seeds.values)


def run_spec(study: StudyConfig, cell: RunCell) -> RunSpec:
    """The runner spec of a cell. ``extra`` ties the stored run back to its study and cell."""
    return RunSpec(
        stage=study.stage,
        seed=cell.seed,
        budget=study.budget.max_evaluations,
        timeout_seconds=study.timeout_seconds,
        extra_config={"study": study.name, "replicate": cell.replicate},
    )


def cell_config_hash(study: StudyConfig, cell: RunCell) -> str:
    """The ``config_hash`` a stored run of this cell must carry."""
    document = ExperimentRunner.config_document(
        cell.build_problem(), cell.build_algorithm(), run_spec(study, cell)
    )
    return canonical_hash(document)


def build_matrix(study: StudyConfig) -> list[RunCell]:
    """Validate ``study`` and return its cells in execution order.

    Raises:
        StudyError: listing every problem, algorithm, or domain error found.
    """
    errors: list[str] = []
    problems: dict[str, Problem] = {}
    for entry in study.problems:
        try:
            problems[entry.name] = build_problem(entry)
        except ValueError as exc:
            errors.append(f"problem {entry.name}: {exc}")
    algorithms: dict[str, Algorithm] = {}
    for alg_entry in study.algorithms:
        try:
            algorithms[alg_entry.name] = get_algorithm(alg_entry.name, **alg_entry.parameters)
        except (TypeError, ValueError) as exc:
            errors.append(f"algorithm {alg_entry.name}: {exc}")
    for p_name, problem in problems.items():
        for a_name, algorithm in algorithms.items():
            if not algorithm.supports(problem.spec):
                errors.append(
                    f"{a_name} does not support {p_name} "
                    f"({problem.spec.n_objectives} objectives; "
                    f"supported: {algorithm.supported_n_objectives})"
                )
    if errors:
        raise StudyError("invalid study matrix:\n  " + "\n  ".join(errors))

    cells: list[RunCell] = []
    for p_entry in study.problems:
        for replicate, seed in enumerate(replicate_seeds(study, p_entry.name)):
            cells.extend(
                RunCell(problem=p_entry, algorithm=a, replicate=replicate, seed=seed)
                for a in study.algorithms
            )
    return cells


def matrix_summary(study: StudyConfig, cells: list[RunCell]) -> dict[str, Any]:
    """Counts used by ``evooptlab plan`` and recorded in aggregate manifests."""
    budget = study.budget.max_evaluations
    return {
        "study": study.name,
        "stage": study.stage,
        "n_problems": len(study.problems),
        "n_algorithms": len(study.algorithms),
        "n_replicates_per_cell": len(cells) // max(len(study.problems) * len(study.algorithms), 1),
        "n_runs": len(cells),
        "budget_per_run": budget,
        "total_objective_evaluations": budget * len(cells),
        "seed_policy": study.seeds.policy,
    }
