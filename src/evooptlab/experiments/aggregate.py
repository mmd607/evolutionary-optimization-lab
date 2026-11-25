"""Aggregate a study's stored runs into per-run and per-cell tables.

* Quality indicators are recomputed from each run's full ``history.csv`` under the declared
  quality policy (ADR 0003), so no number depends on in-memory state.
* Only **completed** canonical runs are scored. A failed run (for example a timeout) used a
  different number of evaluations, so scoring it would break the equal-budget control. It is
  counted in ``n_failed`` instead and never dropped.
* Summaries are descriptive only (median, quartiles, mean, standard deviation). Statistical
  tests belong to Phase 06 and are pre-registered (P9).
* Outputs are written to a new directory and never overwrite anything. Non-final stages are
  labelled ``preliminary`` in the manifest, so pilot numbers cannot be mistaken for final ones.
* HPO studies (ADR 0006) have no reference front. Their rows report the validation-selected
  trial and its stored held-out test evaluation instead of front-based indicators.
"""

from __future__ import annotations

import csv
import io
import json
import math
import secrets
import statistics
from collections.abc import Iterable
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evooptlab.evaluation.quality import QualityPolicy, compute_quality
from evooptlab.experiments.diagnostics import DiagnosticsReport, StudyCollection
from evooptlab.experiments.hpo_evaluation import SELECTION_RULE
from evooptlab.experiments.matrix import StudyError, matrix_summary
from evooptlab.experiments.records import history_objectives
from evooptlab.utils.environment import capture_environment

QUALITY_KEYS: tuple[str, ...] = (
    "feasibility_rate",
    "n_nondominated",
    "hypervolume",
    "hypervolume_ratio",
    "igd",
    "igd_plus",
    "gd",
    "gd_plus",
    "spacing",
)
TIMING_KEYS: tuple[str, ...] = (
    "n_evaluations",
    "n_failed_evaluations",
    "wall_clock_seconds",
    "evaluation_seconds",
    "overhead_seconds",
)
#: Columns summarized per (problem, algorithm) cell.
SUMMARY_METRICS: tuple[str, ...] = (
    "hypervolume_ratio",
    "igd_plus",
    "igd",
    "gd_plus",
    "wall_clock_seconds",
)
RUN_COLUMNS: tuple[str, ...] = (
    "problem",
    "algorithm",
    "replicate",
    "seed",
    "run_id",
    "outcome",
    *TIMING_KEYS,
    *QUALITY_KEYS,
    "missing_reason",
)
HPO_KEYS: tuple[str, ...] = (
    "n_trials",
    "n_failed_trials",
    "selected_evaluation_id",
    "best_validation_error",
    "target_metric",
    "test_score",
    "test_error",
    "hyperparameters",
)
HPO_SUMMARY_METRICS: tuple[str, ...] = (
    "best_validation_error",
    "test_error",
    "n_failed_trials",
    "wall_clock_seconds",
)
HPO_RUN_COLUMNS: tuple[str, ...] = (
    "problem",
    "algorithm",
    "replicate",
    "seed",
    "run_id",
    "outcome",
    *TIMING_KEYS,
    *HPO_KEYS,
    "missing_reason",
)


def run_rows(
    collection: StudyCollection, policy: QualityPolicy | None = None
) -> list[dict[str, Any]]:
    """One row per planned cell that has a canonical run, in plan order."""
    policy = policy or QualityPolicy()
    rows: list[dict[str, Any]] = []
    for cell in collection.cells:
        record = collection.canonical.get(cell.key)
        if record is None:
            continue
        metrics = record.metrics or {}
        row: dict[str, Any] = {
            "problem": cell.problem.name,
            "algorithm": cell.algorithm.name,
            "replicate": cell.replicate,
            "seed": cell.seed,
            "run_id": record.run_id,
            "outcome": record.metadata.outcome,
            **{key: metrics.get(key) for key in TIMING_KEYS},
            **dict.fromkeys(QUALITY_KEYS),
            "missing_reason": None,
        }
        if collection.study.is_hpo:
            row = {k: v for k, v in row.items() if k not in QUALITY_KEYS}
            row.update(_hpo_fields(collection, record))
        elif record.metadata.outcome == "completed":
            problem = cell.build_problem()
            f, feasible = history_objectives(record.read_history(), problem.spec.n_objectives)
            front = problem.pareto_front()  # type: ignore[attr-defined]
            quality = compute_quality(f, feasible, front, policy)
            row.update({key: quality[key] for key in QUALITY_KEYS})
            row["missing_reason"] = quality["missing_reason"]
        else:
            row["missing_reason"] = (
                f"run {record.metadata.outcome}: {record.metadata.failure_reason}"
            )
        rows.append(row)
    return rows


def _hpo_fields(collection: StudyCollection, record: Any) -> dict[str, Any]:
    from evooptlab.hpo.problem import select_trial

    fields: dict[str, Any] = dict.fromkeys(HPO_KEYS)
    if record.metadata.outcome != "completed":
        fields["missing_reason"] = (
            f"run {record.metadata.outcome}: {record.metadata.failure_reason}"
        )
        return fields
    rows = record.read_history()
    chosen = select_trial(rows)
    fields["n_trials"] = len(rows)
    fields["n_failed_trials"] = sum(r["feasible"] != "True" for r in rows)
    if chosen is None:
        fields["missing_reason"] = "no successful trial"
        return fields
    fields["selected_evaluation_id"] = int(chosen["evaluation_id"])
    fields["best_validation_error"] = float(chosen["f_0"])
    stored = collection.test_evaluations.get(record.run_id)
    test = (stored or {}).get("test")
    if not test:
        fields["missing_reason"] = "test evaluation not run"
        return fields
    fields.update(
        {
            "target_metric": test["target_metric"],
            "test_score": test["test_score"],
            "test_error": test["test_error"],
            "hyperparameters": json.dumps(test["hyperparameters"], sort_keys=True),
        }
    )
    return fields


def _describe(values: list[float]) -> dict[str, float | None]:
    if not values:
        return {"median": None, "q1": None, "q3": None, "mean": None, "std": None}
    if len(values) == 1:
        v = values[0]
        return {"median": v, "q1": v, "q3": v, "mean": v, "std": None}
    q1, _, q3 = statistics.quantiles(values, n=4, method="inclusive")
    return {
        "median": statistics.median(values),
        "q1": q1,
        "q3": q3,
        "mean": statistics.fmean(values),
        "std": statistics.stdev(values),
    }


def summary_rows(collection: StudyCollection, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Per (problem, algorithm) counts and descriptive statistics of completed runs."""
    planned: dict[tuple[str, str], int] = {}
    for cell in collection.cells:
        key = (cell.problem.name, cell.algorithm.name)
        planned[key] = planned.get(key, 0) + 1
    out = []
    for (problem, algorithm), n_planned in planned.items():
        cell_rows = [r for r in rows if (r["problem"], r["algorithm"]) == (problem, algorithm)]
        completed = [r for r in cell_rows if r["outcome"] == "completed"]
        summary: dict[str, Any] = {
            "problem": problem,
            "algorithm": algorithm,
            "n_planned": n_planned,
            "n_completed": len(completed),
            "n_failed": len(cell_rows) - len(completed),
            "n_missing": n_planned - len(cell_rows),
        }
        metrics = HPO_SUMMARY_METRICS if collection.study.is_hpo else SUMMARY_METRICS
        for metric in metrics:
            values = [float(r[metric]) for r in completed if r[metric] is not None]
            summary[f"{metric}__n"] = len(values)
            for stat, value in _describe(values).items():
                summary[f"{metric}__{stat}"] = value
        out.append(summary)
    return out


def _cell(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return repr(value) if math.isfinite(value) else str(value)
    return str(value)


def to_csv(rows: Iterable[dict[str, Any]], columns: Iterable[str]) -> str:
    columns = list(columns)
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([_cell(row.get(c)) for c in columns])
    return buffer.getvalue()


def default_output_dir(root: Path, collection: StudyCollection) -> Path:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    study = collection.study
    return root / "aggregates" / study.stage / f"{study.name}__{stamp}-{secrets.token_hex(3)}"


def write_aggregate(
    collection: StudyCollection,
    report: DiagnosticsReport,
    output_dir: Path,
    *,
    policy: QualityPolicy | None = None,
    repo_root: Path | None = None,
) -> Path:
    """Write ``runs.csv``, ``summary.csv`` and ``manifest.json`` into a new ``output_dir``.

    Raises:
        StudyError: if diagnostics report any ``FAIL`` (results cannot be trusted).
        FileExistsError: if ``output_dir`` already exists.
    """
    if report.status == "FAIL":
        failing = ", ".join(c.name for c in report.checks if c.status == "FAIL")
        raise StudyError(f"refusing to aggregate: diagnostics failed ({failing})")
    policy = policy or QualityPolicy()
    rows = run_rows(collection, policy)
    summary = summary_rows(collection, rows)
    summary_columns = list(summary[0]) if summary else ["problem", "algorithm"]

    output_dir.parent.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(exist_ok=False)
    git = capture_environment(repo_root).git
    manifest = {
        "study": collection.study.name,
        "stage": collection.study.stage,
        "preliminary": collection.study.stage != "final",
        "created_at_utc": datetime.now(UTC).isoformat(),
        "aggregator_git_commit": git.commit,
        "aggregator_git_dirty": git.dirty,
        "quality_policy": None if collection.study.is_hpo else asdict(policy),
        "hpo_selection_rule": SELECTION_RULE if collection.study.is_hpo else None,
        "matrix": matrix_summary(collection.study, collection.cells),
        "diagnostics": report.to_dict(),
        "run_ids": [r["run_id"] for r in rows],
        "excluded": {
            "duplicates": [rid for _, rid in collection.duplicates],
            "interrupted": [rid for _, rid in collection.interrupted],
            "unplanned": collection.unplanned,
        },
    }
    files = {
        "runs.csv": to_csv(rows, HPO_RUN_COLUMNS if collection.study.is_hpo else RUN_COLUMNS),
        "summary.csv": to_csv(summary, summary_columns),
        "manifest.json": json.dumps(manifest, indent=2, sort_keys=True) + "\n",
    }
    for name, text in files.items():
        with (output_dir / name).open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
    return output_dir
