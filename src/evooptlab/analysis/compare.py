"""Compare algorithms from an aggregate directory under a declared analysis plan (ADR 0007).

Input is only what ``evooptlab aggregate`` wrote (``runs.csv``, ``manifest.json``), so every
number traces to stored run artifacts. Rules:

* **Pre-registration guard.** A final-stage aggregate is analysed only under a ``frozen`` plan,
  from a committed and clean source tree. Anything else is labelled ``preliminary`` throughout.
* **Failed runs are counted, never scored** (ADR 0005). Missing metric values are dropped
  pairwise and the number dropped is reported.
* **Paired tests** pair replicates by index. All algorithms of a problem share replicate seeds
  (common random numbers), and the pairing is checked against the recorded seeds.
* Cells with fewer than ``min_replicates`` complete values get descriptive statistics only; their
  tests are reported as "not run" with the reason, never silently skipped.
"""

from __future__ import annotations

import csv
import itertools
import json
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evooptlab.analysis.stats import (
    bootstrap_ci,
    friedman,
    holm,
    vargha_delaney_a12,
    wilcoxon_paired,
)
from evooptlab.config.schemas import AnalysisPlanConfig, PlanMetric


class AnalysisError(ValueError):
    """The aggregate cannot be analysed under this plan."""


@dataclass(frozen=True)
class AggregateInput:
    path: Path
    manifest: dict[str, Any]
    runs: list[dict[str, str]]

    @property
    def kind(self) -> str:
        return "hpo" if self.runs and "best_validation_error" in self.runs[0] else "benchmark"

    @property
    def stage(self) -> str:
        return str(self.manifest["stage"])

    @property
    def study(self) -> str:
        return str(self.manifest["study"])


def load_aggregate(path: Path) -> AggregateInput:
    try:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        text = (path / "runs.csv").read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        raise AnalysisError(f"{path}: not a readable aggregate directory ({exc})") from exc
    runs = list(csv.DictReader(text.splitlines()))
    if manifest.get("diagnostics", {}).get("status") == "FAIL":
        raise AnalysisError(f"{path}: diagnostics failed; the results cannot be analysed")
    return AggregateInput(path, manifest, runs)


@dataclass
class AnalysisResult:
    study: str
    stage: str
    kind: str
    preliminary: bool
    plan: dict[str, Any]
    source: dict[str, Any]
    descriptive: list[dict[str, Any]] = field(default_factory=list)
    pairwise: list[dict[str, Any]] = field(default_factory=list)
    across_problems: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "study": self.study,
            "stage": self.stage,
            "kind": self.kind,
            "preliminary": self.preliminary,
            "plan": self.plan,
            "source": self.source,
            "descriptive": self.descriptive,
            "pairwise": self.pairwise,
            "across_problems": self.across_problems,
            "notes": self.notes,
        }


def _check_preregistration(
    data: AggregateInput, plan: AnalysisPlanConfig, git_commit: str | None, git_dirty: bool | None
) -> bool:
    """Return ``preliminary``; raise if final results would be analysed under an open plan."""
    if data.stage == "final":
        if plan.status != "frozen":
            raise AnalysisError(
                "final-stage results need a frozen analysis plan (status: frozen), committed "
                "before the results are analysed (protocol section 9, P9)"
            )
        if git_commit is None or git_dirty is not False:
            raise AnalysisError("final-stage analysis needs a clean, committed source tree")
        return bool(data.manifest.get("preliminary", False))
    return True


def _value(row: dict[str, str], metric: str) -> float | None:
    raw = row.get(metric, "")
    if row.get("outcome") != "completed" or raw in ("", None):
        return None
    return float(raw)


def _cells(data: AggregateInput) -> dict[tuple[str, str], dict[int, dict[str, str]]]:
    cells: dict[tuple[str, str], dict[int, dict[str, str]]] = {}
    for row in data.runs:
        cells.setdefault((row["problem"], row["algorithm"]), {})[int(row["replicate"])] = row
    return cells


def _describe(values: list[float], plan: AnalysisPlanConfig) -> dict[str, Any]:
    if not values:
        return dict.fromkeys(("median", "q1", "q3", "mean", "std", "ci_low", "ci_high"))
    q1, q3 = (
        statistics.quantiles(values, n=4, method="inclusive")[::2]
        if len(values) > 1
        else (values[0], values[0])
    )
    ci = plan.confidence_interval
    interval = bootstrap_ci(
        values,
        statistic=ci.statistic,
        level=ci.level,
        n_resamples=ci.n_resamples,
        seed=ci.seed,
    )
    return {
        "median": statistics.median(values),
        "q1": q1,
        "q3": q3,
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values) if len(values) > 1 else None,
        "ci_low": None if interval is None else interval.low,
        "ci_high": None if interval is None else interval.high,
    }


def analyse(
    data: AggregateInput,
    plan: AnalysisPlanConfig,
    *,
    plan_sha256: str,
    git_commit: str | None = None,
    git_dirty: bool | None = None,
) -> AnalysisResult:
    """Descriptive statistics, per-problem paired tests and the across-problem comparison."""
    preliminary = _check_preregistration(data, plan, git_commit, git_dirty)
    metrics = plan.hpo_metrics if data.kind == "hpo" else plan.benchmark_metrics
    missing_columns = [m.name for m in metrics if data.runs and m.name not in data.runs[0]]
    if missing_columns:
        raise AnalysisError(f"runs.csv has no column(s) {missing_columns} required by the plan")
    cells = _cells(data)
    problems = list(dict.fromkeys(p for p, _ in cells))
    algorithms = list(dict.fromkeys(a for _, a in cells))
    result = AnalysisResult(
        study=data.study,
        stage=data.stage,
        kind=data.kind,
        preliminary=preliminary,
        plan={"name": plan.name, "status": plan.status, "sha256": plan_sha256},
        source={
            "aggregate": str(data.path),
            "manifest_created_at_utc": data.manifest.get("created_at_utc"),
            "run_ids": data.manifest.get("run_ids", []),
            "analysis_git_commit": git_commit,
            "analysis_git_dirty": git_dirty,
        },
    )
    _check_pairing(cells, problems, algorithms, result)
    for metric in metrics:
        _per_problem(metric, cells, problems, algorithms, plan, result)
        _across(metric, cells, problems, algorithms, plan, result)
    return result


def _check_pairing(
    cells: dict[tuple[str, str], dict[int, dict[str, str]]],
    problems: list[str],
    algorithms: list[str],
    result: AnalysisResult,
) -> None:
    for problem in problems:
        seeds: dict[int, set[str]] = {}
        for algorithm in algorithms:
            for replicate, row in cells.get((problem, algorithm), {}).items():
                seeds.setdefault(replicate, set()).add(row["seed"])
        if any(len(s) > 1 for s in seeds.values()):
            raise AnalysisError(f"{problem}: replicates do not share seeds; pairing is invalid")


def _per_problem(
    metric: PlanMetric,
    cells: dict[tuple[str, str], dict[int, dict[str, str]]],
    problems: list[str],
    algorithms: list[str],
    plan: AnalysisPlanConfig,
    result: AnalysisResult,
) -> None:
    family_start = len(result.pairwise)
    for problem in problems:
        start = len(result.pairwise)
        for algorithm in algorithms:
            rows = cells.get((problem, algorithm), {})
            values = [v for r in rows.values() if (v := _value(r, metric.name)) is not None]
            result.descriptive.append(
                {
                    "problem": problem,
                    "algorithm": algorithm,
                    "metric": metric.name,
                    "direction": metric.direction,
                    "primary": metric.primary,
                    "n_runs": len(rows),
                    "n_failed": sum(r.get("outcome") != "completed" for r in rows.values()),
                    "n": len(values),
                    **_describe(values, plan),
                }
            )
        for a, b in itertools.combinations(algorithms, 2):
            ra, rb = cells.get((problem, a), {}), cells.get((problem, b), {})
            shared = sorted(set(ra) | set(rb))
            pairs = [
                (va, vb)
                for i in shared
                if (va := _value(ra[i], metric.name) if i in ra else None) is not None
                and (vb := _value(rb[i], metric.name) if i in rb else None) is not None
            ]
            row: dict[str, Any] = {
                "problem": problem,
                "metric": metric.name,
                "direction": metric.direction,
                "algorithm_a": a,
                "algorithm_b": b,
                "n_pairs": len(pairs),
                "n_dropped": len(shared) - len(pairs),
                "a12": None,
                "statistic": None,
                "p_value": None,
                "p_holm": None,
                "note": None,
            }
            if len(pairs) < plan.min_replicates:
                row["note"] = f"not run: {len(pairs)} complete pairs < min_replicates"
                if pairs:
                    xs, ys = zip(*pairs, strict=True)
                    row["a12"] = vargha_delaney_a12(xs, ys, metric.direction)
            else:
                xs, ys = zip(*pairs, strict=True)
                test = wilcoxon_paired(
                    xs,
                    ys,
                    zero_method=plan.per_problem.zero_method,
                    alternative=plan.per_problem.alternative,
                )
                row.update(
                    {
                        "a12": vargha_delaney_a12(xs, ys, metric.direction),
                        "statistic": test.statistic,
                        "p_value": test.p_value,
                        "note": test.note,
                    }
                )
            result.pairwise.append(row)
        if plan.per_problem.correction_family == "problem_metric":
            _apply_holm(result.pairwise[start:])
    if plan.per_problem.correction_family == "metric":
        _apply_holm(result.pairwise[family_start:])


def _apply_holm(rows: list[dict[str, Any]]) -> None:
    for row, adjusted in zip(rows, holm([r["p_value"] for r in rows]), strict=True):
        row["p_holm"] = adjusted


def _block_value(values: list[float], statistic: str) -> float:
    return statistics.median(values) if statistic == "median" else statistics.fmean(values)


def _across(
    metric: PlanMetric,
    cells: dict[tuple[str, str], dict[int, dict[str, str]]],
    problems: list[str],
    algorithms: list[str],
    plan: AnalysisPlanConfig,
    result: AnalysisResult,
) -> None:
    cfg = plan.across_problems
    blocks: list[list[float]] = []
    used: list[str] = []
    skipped: list[str] = []
    for problem in problems:
        block: list[float] = []
        for algorithm in algorithms:
            values = [
                v
                for r in cells.get((problem, algorithm), {}).values()
                if (v := _value(r, metric.name)) is not None
            ]
            if len(values) < plan.min_replicates:
                break
            block.append(_block_value(values, cfg.block_statistic))
        else:
            blocks.append(block)
            used.append(problem)
            continue
        skipped.append(problem)
    entry: dict[str, Any] = {
        "metric": metric.name,
        "direction": metric.direction,
        "test": cfg.test,
        "block_statistic": cfg.block_statistic,
        "problems_used": used,
        "problems_skipped": skipped,
        "algorithms": algorithms,
        "mean_ranks": None,
        "statistic": None,
        "p_value": None,
        "posthoc": [],
        "note": None,
    }
    if len(used) < cfg.min_problems:
        entry["note"] = (
            f"not run: {len(used)} problems with >= {plan.min_replicates} complete replicates "
            f"per algorithm < min_problems {cfg.min_problems}"
        )
        result.across_problems.append(entry)
        return
    omnibus = friedman(blocks, metric.direction)
    entry.update(
        {
            "mean_ranks": dict(zip(algorithms, omnibus.mean_ranks, strict=True)),
            "statistic": omnibus.statistic,
            "p_value": omnibus.p_value,
            "note": omnibus.note,
        }
    )
    posthoc: list[dict[str, Any]] = []
    for i, j in itertools.combinations(range(len(algorithms)), 2):
        xs = [b[i] for b in blocks]
        ys = [b[j] for b in blocks]
        test = wilcoxon_paired(xs, ys, zero_method=plan.per_problem.zero_method)
        posthoc.append(
            {
                "algorithm_a": algorithms[i],
                "algorithm_b": algorithms[j],
                "n_blocks": len(blocks),
                "a12": vargha_delaney_a12(xs, ys, metric.direction),
                "statistic": test.statistic,
                "p_value": test.p_value,
                "note": test.note,
            }
        )
    for comparison, adjusted in zip(posthoc, holm([r["p_value"] for r in posthoc]), strict=True):
        comparison["p_holm"] = adjusted
    entry["posthoc"] = posthoc
    result.across_problems.append(entry)
