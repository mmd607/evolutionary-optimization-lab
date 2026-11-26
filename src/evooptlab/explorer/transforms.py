"""Transformations behind the dashboard pages, all computed from stored artifacts.

* **Comparability.** Runs are overlaid or tabulated together only when they share an
  objective-evaluation budget. A mixed selection gets an explicit warning, and convergence
  curves refuse it (:class:`IncomparableRunsError`). Mixed stages are warned about too.
* **No made-up values.** A missing value stays ``None``. Only completed runs are scored (the
  ADR 0005 rule), and failed or interrupted runs are counted.
* **HPO test results** are only the stored ``evooptlab test-eval`` records. They are never
  computed here, and a record whose config hash differs from the run's is flagged.
* Quality indicators of a single run are computed with the same functions and default policy
  as ``evooptlab aggregate`` (ADR 0003; the policy is still proposal P8).
"""

from __future__ import annotations

import json
import statistics
from collections import Counter
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from evooptlab.analysis.curves import best_so_far_curve, checkpoints, igd_plus_curve
from evooptlab.config.schemas import SearchParameterConfig
from evooptlab.evaluation.dominance import non_dominated_mask
from evooptlab.evaluation.quality import compute_quality
from evooptlab.experiments.records import history_objectives
from evooptlab.explorer.catalog import AggregateEntry, Catalog, RunEntry

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

#: The only per-problem test ``evooptlab report`` implements (``PairwiseTestConfig.test``).
PAIRWISE_TEST = "paired Wilcoxon signed-rank, Holm-adjusted; effect size Vargha-Delaney A12"
ACROSS_TEST = {"friedman": "Friedman on per-problem medians; post-hoc Wilcoxon, Holm-adjusted"}


class IncomparableRunsError(ValueError):
    """The selected runs cannot be compared (different budgets or problems)."""


# ---------------------------------------------------------------------------------------------
# Comparability
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Comparability:
    budgets: dict[int, int]
    stages: dict[str, int]
    n_not_completed: int
    warnings: tuple[str, ...]

    @property
    def comparable_budgets(self) -> bool:
        return len(self.budgets) <= 1


def comparability(runs: Sequence[RunEntry]) -> Comparability:
    """Budget, stage and outcome mix of a selection, with the warnings to show."""
    budgets = Counter(r.budget for r in runs)
    stages: Counter[str] = Counter(r.stage for r in runs)
    not_completed = sum(r.outcome != "completed" for r in runs)
    warnings = []
    if len(budgets) > 1:
        listed = ", ".join(f"{b} ({n} runs)" for b, n in sorted(budgets.items()))
        warnings.append(
            f"Different evaluation budgets are selected: {listed}. Results under different "
            "budgets are not comparable; select one budget."
        )
    if len(stages) > 1:
        warnings.append(
            "Runs from different stages are mixed ("
            + ", ".join(sorted(stages))
            + "). Pilot and development runs are preliminary."
        )
    if not_completed:
        warnings.append(
            f"{not_completed} run(s) did not complete. They are counted but not scored "
            "(a failed run used a different number of evaluations)."
        )
    return Comparability(dict(budgets), dict(stages), not_completed, tuple(warnings))


# ---------------------------------------------------------------------------------------------
# Objective space of one run
# ---------------------------------------------------------------------------------------------
def reference_front(run: RunEntry) -> FloatArray | None:
    """The benchmark's reference front, rebuilt from the stored config; ``None`` for HPO."""
    if run.kind != "benchmark":
        return None
    from evooptlab.benchmarks.registry import get_problem

    p = (run.record.config or {}).get("problem") or {}
    try:
        problem = get_problem(p["name"], int(p["n_variables"]), int(p["n_objectives"]))
    except (KeyError, ValueError, TypeError):
        return None
    front = getattr(problem, "pareto_front", None)
    return None if front is None else np.asarray(front(), dtype=np.float64)


@dataclass(frozen=True)
class FrontData:
    evaluation_ids: npt.NDArray[np.int64]
    objectives: FloatArray
    feasible: BoolArray
    #: Non-dominated among the feasible evaluations (the approximation set, ADR 0003).
    nondominated: BoolArray
    reference_front: FloatArray | None
    quality: dict[str, Any] | None


def run_front(run: RunEntry, *, with_quality: bool = True) -> FrontData:
    """Evaluations of one run in objective space. ``with_quality=False`` skips the indicators
    (use the aggregate's stored values instead; they are computed by the same function)."""
    rows = run.record.read_history()
    f, feasible = history_objectives(rows, run.n_objectives)
    ids = np.array([int(r["evaluation_id"]) for r in rows], dtype=np.int64)
    nondominated = np.zeros(len(rows), dtype=np.bool_)
    if feasible.any():
        nondominated[np.flatnonzero(feasible)] = non_dominated_mask(f[feasible])
    front = reference_front(run)
    quality = None
    if with_quality and front is not None and run.outcome == "completed" and len(rows):
        quality = compute_quality(f, feasible, front)
    return FrontData(ids, f, feasible, nondominated, front, quality)


# ---------------------------------------------------------------------------------------------
# Convergence (anytime) curves across replicates
# ---------------------------------------------------------------------------------------------
@dataclass(frozen=True)
class CurveBand:
    algorithm: str
    evaluations: tuple[int, ...]
    median: tuple[float | None, ...]
    q1: tuple[float | None, ...]
    q3: tuple[float | None, ...]
    #: Runs with a value at each checkpoint (a run has none before its first feasible point).
    n: tuple[int, ...]
    run_ids: tuple[str, ...]


def _quartiles(values: list[float]) -> tuple[float | None, float | None, float | None]:
    if not values:
        return None, None, None
    if len(values) == 1:
        return values[0], values[0], values[0]
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return statistics.median(values), q1, q3


def run_curve(run: RunEntry, at: Sequence[int], front: FloatArray | None) -> list[float | None]:
    rows = run.record.read_history()
    f, feasible = history_objectives(rows, run.n_objectives)
    if run.kind == "hpo":
        return best_so_far_curve(f[:, 0], feasible, at)
    if front is None:
        raise IncomparableRunsError(f"{run.problem}: no reference front for IGD+")
    return igd_plus_curve(f, feasible, front, at)


def convergence_bands(runs: Sequence[RunEntry], n_checkpoints: int = 20) -> list[CurveBand]:
    """Median and interquartile band per algorithm over completed runs of one problem.

    Benchmarks use IGD+ (normalized, ADR 0003), HPO the best validation error so far.

    Raises:
        IncomparableRunsError: the completed runs span several problems, kinds or budgets.
    """
    completed = [r for r in runs if r.outcome == "completed"]
    if not completed:
        return []
    distinct: tuple[tuple[str, set[Any]], ...] = (
        ("problems", {r.problem for r in completed}),
        ("kinds", {r.kind for r in completed}),
        ("evaluation budgets", {r.budget for r in completed}),
    )
    for label, found in distinct:
        if len(found) > 1:
            raise IncomparableRunsError(
                f"curves can only be overlaid for one problem and one budget; the selection "
                f"has several {label}: {sorted(found, key=str)}"
            )
    budget = completed[0].budget
    at = checkpoints(budget, n_checkpoints)
    front = reference_front(completed[0])
    bands = []
    for algorithm in dict.fromkeys(r.algorithm for r in completed):
        group = [r for r in completed if r.algorithm == algorithm]
        curves = [run_curve(r, at, front) for r in group]
        medians, lows, highs, counts = [], [], [], []
        for i in range(len(at)):
            values = [v for c in curves if i < len(c) and (v := c[i]) is not None]
            median, q1, q3 = _quartiles(values)
            medians.append(median)
            lows.append(q1)
            highs.append(q3)
            counts.append(len(values))
        bands.append(
            CurveBand(
                algorithm,
                tuple(at),
                tuple(medians),
                tuple(lows),
                tuple(highs),
                tuple(counts),
                tuple(r.run_id for r in group),
            )
        )
    return bands


# ---------------------------------------------------------------------------------------------
# HPO
# ---------------------------------------------------------------------------------------------
def search_space(run: RunEntry) -> dict[str, SearchParameterConfig]:
    details = ((run.record.config or {}).get("problem") or {}).get("details") or {}
    return {
        name: SearchParameterConfig.model_validate(spec)
        for name, spec in (details.get("search_space") or {}).items()
    }


def trial_rows(run: RunEntry) -> list[dict[str, Any]]:
    """One row per HPO trial: validation error, best so far, the selected trial and the
    decoded hyperparameters (the unit-cube decoding is deterministic, ADR 0006)."""
    from evooptlab.hpo.problem import select_trial
    from evooptlab.hpo.search_space import SearchSpace

    rows = run.record.read_history()
    space = SearchSpace.from_config(search_space(run))
    chosen = select_trial(rows) if rows else None
    best = float("inf")
    out = []
    for r in rows:
        feasible = r["feasible"] == "True"
        error = float(r["f_0"])
        if feasible:
            best = min(best, error)
        u = [float(r[f"x_{j}"]) for j in range(space.n_dimensions)]
        out.append(
            {
                "evaluation_id": int(r["evaluation_id"]),
                "batch": int(r["batch"]),
                "validation_error": error if feasible else None,
                "feasible": feasible,
                "best_so_far": best if best < float("inf") else None,
                "selected": chosen is not None and r["evaluation_id"] == chosen["evaluation_id"],
                **(space.decode(u) if space.n_dimensions else {}),
            }
        )
    return out


def test_result(catalog: Catalog, run: RunEntry) -> dict[str, Any] | None:
    """The stored held-out evaluation of ``run``, with an integrity flag; ``None`` if absent."""
    stored = catalog.test_evaluation(run)
    if stored is None:
        return None
    if "unreadable" in stored:
        return {"status": "unreadable", "reason": stored["unreadable"]}
    test = stored.get("test") or {}
    matches = stored.get("config_hash") == run.config_hash
    return {
        "status": "ok" if matches else "config hash mismatch",
        "evaluated_at_utc": stored.get("evaluated_at_utc"),
        "evaluator_git_commit": stored.get("evaluator_git_commit"),
        "evaluator_git_dirty": stored.get("evaluator_git_dirty"),
        "selected_evaluation_id": stored.get("selected_evaluation_id"),
        "selected_validation_error": stored.get("selected_validation_error"),
        "selection_rule": stored.get("selection_rule"),
        "target_metric": test.get("target_metric"),
        "test_score": test.get("test_score"),
        "test_error": test.get("test_error"),
        "n_train": test.get("n_train"),
        "n_test": test.get("n_test"),
        "hyperparameters": test.get("hyperparameters"),
    }


def hpo_run_rows(catalog: Catalog, runs: Sequence[RunEntry]) -> list[dict[str, Any]]:
    """Per-run quality and cost of HPO runs. Cost is the run's wall-clock time; per-trial fit
    time is not recorded (ADR 0006)."""
    from evooptlab.hpo.problem import select_trial

    out = []
    for run in runs:
        row: dict[str, Any] = {
            "stage": run.stage,
            "problem": run.problem,
            "algorithm": run.algorithm,
            "seed": run.seed,
            "budget": run.budget,
            "outcome": run.outcome,
            "n_trials": None,
            "n_failed_trials": None,
            "best_validation_error": None,
            "wall_clock_seconds": run.wall_clock_seconds,
            "test_error": None,
            "test_status": "not run",
            "run_id": run.run_id,
        }
        if run.outcome == "completed":
            history = run.record.read_history()
            chosen = select_trial(history)
            row["n_trials"] = len(history)
            row["n_failed_trials"] = sum(h["feasible"] != "True" for h in history)
            row["best_validation_error"] = None if chosen is None else float(chosen["f_0"])
            test = test_result(catalog, run)
            if test is not None:
                row["test_status"] = test["status"]
                if test["status"] == "ok":
                    row["test_error"] = test["test_error"]
        out.append(row)
    return out


# ---------------------------------------------------------------------------------------------
# Aggregates and analysis reports
# ---------------------------------------------------------------------------------------------
def read_csv_rows(path: Path) -> list[dict[str, str]]:
    import csv

    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def aggregate_tables(entry: AggregateEntry) -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    """``(runs.csv, summary.csv)`` rows of an aggregate, as written."""
    return read_csv_rows(entry.path / "runs.csv"), read_csv_rows(entry.path / "summary.csv")


def metric_values(
    rows: Sequence[dict[str, str]], metric: str
) -> tuple[dict[str, dict[str, list[float]]], int]:
    """Completed values of ``metric`` by problem and algorithm, and how many are missing."""
    values: dict[str, dict[str, list[float]]] = {}
    missing = 0
    for row in rows:
        raw = row.get(metric, "")
        if row.get("outcome") != "completed" or raw in ("", None):
            missing += 1
            continue
        values.setdefault(row["problem"], {}).setdefault(row["algorithm"], []).append(float(raw))
    return values, missing


def pairwise_rows(analysis: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    keys = ("problem", "algorithm_a", "algorithm_b", "n_pairs", "n_dropped", "a12")
    return [
        {
            **{k: r.get(k) for k in keys},
            "statistic": r.get("statistic"),
            "p_value": r.get("p_value"),
            "p_holm": r.get("p_holm"),
            "note": r.get("note"),
        }
        for r in analysis.get("pairwise", [])
        if r.get("metric") == metric
    ]


def across_rows(analysis: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    out = []
    for r in analysis.get("across_problems", []):
        if r.get("metric") != metric:
            continue
        out.append(
            {
                "test": ACROSS_TEST.get(str(r.get("test")), r.get("test")),
                "problems_used": len(r.get("problems_used") or []),
                "problems_skipped": len(r.get("problems_skipped") or []),
                "statistic": r.get("statistic"),
                "p_value": r.get("p_value"),
                "mean_ranks": json.dumps(r.get("mean_ranks")) if r.get("mean_ranks") else None,
                "note": r.get("note"),
            }
        )
    return out


def descriptive_rows(analysis: dict[str, Any], metric: str) -> list[dict[str, Any]]:
    keys = ("problem", "algorithm", "n", "n_runs", "n_failed", "median", "q1", "q3")
    return [
        {**{k: r.get(k) for k in keys}, "ci_low": r.get("ci_low"), "ci_high": r.get("ci_high")}
        for r in analysis.get("descriptive", [])
        if r.get("metric") == metric
    ]


def analysis_metrics(analysis: dict[str, Any]) -> list[tuple[str, str]]:
    """``(metric, direction)`` in the order the analysis lists them."""
    seen: dict[str, str] = {}
    for r in analysis.get("descriptive", []):
        seen.setdefault(str(r["metric"]), str(r.get("direction", "")))
    return list(seen.items())


# ---------------------------------------------------------------------------------------------
# Run details
# ---------------------------------------------------------------------------------------------
def run_files(run: RunEntry) -> list[dict[str, Any]]:
    """Every file of the run directory with its size (paths to download or open)."""
    base = run.path
    return [
        {"file": p.relative_to(base).as_posix(), "bytes": p.stat().st_size, "path": str(p)}
        for p in sorted(base.rglob("*"))
        if p.is_file()
    ]


def run_log(run: RunEntry, limit: int = 200) -> list[dict[str, Any]]:
    """The last ``limit`` structured log records; unparsable lines are kept as text."""
    path = run.path / "logs" / "run.log.jsonl"
    if not path.is_file():
        return []
    out: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            record = json.loads(line)
        except ValueError:
            record = None
        out.append(record if isinstance(record, dict) else {"message": line})
    return out
