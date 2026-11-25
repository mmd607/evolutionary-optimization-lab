"""Pilot diagnostics: integrity, fairness and timing checks over a study's stored runs.

Every check is computed from the artifacts on disk, not from the in-memory run, so it also
catches artifacts that were edited, truncated, or produced by different code. Check statuses:

* ``FAIL``: the stored results cannot be trusted or compared (budget, history or config
  mismatch, unpaired seeds, and in the final stage also missing cells or a mixed or dirty source
  tree). Aggregation refuses to run.
* ``WARN``: the results are usable but need attention before scaling up (failed runs, missing
  pilot cells, duplicates, environment drift).
* ``PASS``: nothing found.
"""

from __future__ import annotations

import statistics
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from evooptlab.config.schemas import StudyConfig
from evooptlab.core.experiment import canonical_hash
from evooptlab.experiments.matrix import CellKey, RunCell, build_matrix, cell_config_hash
from evooptlab.experiments.records import RunRecord, read_test_evaluations, scan_stage
from evooptlab.experiments.study import index_by_hash
from evooptlab.storage.layout import ArtifactLayout

Status = Literal["PASS", "WARN", "FAIL"]
_RANK: dict[Status, int] = {"PASS": 0, "WARN": 1, "FAIL": 2}
#: Packages whose versions must not differ between compared runs.
TRACKED_PACKAGES: tuple[str, ...] = (
    "numpy",
    "scipy",
    "pymoo",
    "pydantic",
    "scikit-learn",
    "optuna",
)


@dataclass(frozen=True)
class Check:
    name: str
    status: Status
    summary: str
    details: tuple[str, ...] = ()


@dataclass
class StudyCollection:
    """A study's planned cells matched against the runs stored for its stage."""

    study: StudyConfig
    cells: list[RunCell]
    canonical: dict[CellKey, RunRecord] = field(default_factory=dict)
    duplicates: list[tuple[CellKey, str]] = field(default_factory=list)
    interrupted: list[tuple[CellKey, str]] = field(default_factory=list)
    unplanned: list[str] = field(default_factory=list)
    anomalies: list[tuple[str, str]] = field(default_factory=list)
    #: HPO studies only: stored held-out test evaluations by run ID.
    test_evaluations: dict[str, dict[str, Any]] = field(default_factory=dict)

    @property
    def missing(self) -> list[CellKey]:
        return [c.key for c in self.cells if c.key not in self.canonical]


def collect_study(
    study: StudyConfig, layout: ArtifactLayout, data_dir: Path | None = None
) -> StudyCollection:
    """Match stored runs to planned cells by config hash (the same rule resume uses)."""
    cells = build_matrix(study, data_dir)
    scan = scan_stage(layout, study.stage)
    index = index_by_hash(scan.records)
    collection = StudyCollection(study=study, cells=cells, anomalies=scan.anomalies)
    planned: set[str] = set()
    for cell in cells:
        cell_hash = cell_config_hash(study, cell)
        planned.add(cell_hash)
        for record in index.get(cell_hash, []):
            if record.interrupted:
                collection.interrupted.append((cell.key, record.run_id))
            elif cell.key in collection.canonical:
                collection.duplicates.append((cell.key, record.run_id))
            else:  # earliest settled run is canonical; later ones are reported, not used
                collection.canonical[cell.key] = record
    collection.unplanned = [
        r.run_id
        for r in scan.records
        if r.study == study.name and r.metadata.config_hash not in planned
    ]
    if study.is_hpo:
        collection.test_evaluations = read_test_evaluations(layout, study.stage)
    return collection


# ---------------------------------------------------------------------------- checks
def _check_coverage(c: StudyCollection) -> Check:
    missing = c.missing
    if not missing:
        return Check("coverage", "PASS", f"all {len(c.cells)} planned runs are stored")
    status: Status = "FAIL" if c.study.stage == "final" else "WARN"
    return Check(
        "coverage",
        status,
        f"{len(missing)} of {len(c.cells)} planned runs are missing",
        tuple(f"{p} / {a} / replicate {r}" for p, a, r in missing),
    )


def _check_failed_runs(c: StudyCollection) -> Check:
    failed = [r for r in c.canonical.values() if r.metadata.outcome == "failed"]
    if not failed:
        return Check("failed_runs", "PASS", "no failed runs")
    return Check(
        "failed_runs",
        "WARN",
        f"{len(failed)} runs failed (kept as results, excluded from quality)",
        tuple(f"{r.run_id}: {r.metadata.failure_reason}" for r in failed),
    )


def _check_budget(c: StudyCollection) -> Check:
    budget = c.study.budget.max_evaluations
    bad = []
    for record in c.canonical.values():
        if record.metadata.outcome != "completed":
            continue
        used = (record.metrics or {}).get("n_evaluations")
        if record.metadata.objective_evaluation_budget != budget or used != budget:
            bad.append(f"{record.run_id}: used {used} of {budget}")
    if bad:
        return Check(
            "budget_exact", "FAIL", f"{len(bad)} completed runs did not use the budget", tuple(bad)
        )
    return Check("budget_exact", "PASS", f"every completed run used exactly {budget} evaluations")


def _check_history(c: StudyCollection) -> Check:
    bad = []
    for record in c.canonical.values():
        expected = (record.metrics or {}).get("n_evaluations")
        rows = record.read_history()
        ids = [int(row["evaluation_id"]) for row in rows]
        if expected is None or len(rows) != expected or ids != list(range(len(rows))):
            bad.append(f"{record.run_id}: {len(rows)} history rows, metrics say {expected}")
    if bad:
        return Check(
            "history_integrity", "FAIL", f"{len(bad)} histories are inconsistent", tuple(bad)
        )
    return Check("history_integrity", "PASS", "every history is complete and contiguous")


def _check_config(c: StudyCollection) -> Check:
    bad = [
        r.run_id
        for r in c.canonical.values()
        if r.config is None or canonical_hash(r.config) != r.metadata.config_hash
    ]
    if bad:
        return Check(
            "config_integrity",
            "FAIL",
            f"{len(bad)} config.yaml files do not match their hash",
            tuple(bad),
        )
    return Check("config_integrity", "PASS", "every stored config matches its recorded hash")


def _check_paired_seeds(c: StudyCollection) -> Check:
    seeds: dict[str, dict[str, set[int]]] = defaultdict(lambda: defaultdict(set))
    for (problem, algorithm, _), record in c.canonical.items():
        seeds[problem][algorithm].add(record.metadata.seed)
    bad = []
    for problem, by_alg in sorted(seeds.items()):
        if len({frozenset(s) for s in by_alg.values()}) > 1:
            bad.append(
                f"{problem}: " + ", ".join(f"{a}={sorted(s)}" for a, s in sorted(by_alg.items()))
            )
    if bad:
        return Check(
            "paired_seeds", "FAIL", "algorithms were run on different seed sets", tuple(bad)
        )
    return Check("paired_seeds", "PASS", "all algorithms of a problem share one seed set")


def _distinct(values: list[Any]) -> list[Any]:
    return sorted(set(values), key=str)


def _check_environment(c: StudyCollection) -> Check:
    records = list(c.canonical.values())
    if not records:
        return Check("environment", "PASS", "no runs to compare")
    issues = []
    final = c.study.stage == "final"
    commits = _distinct([r.metadata.git_commit for r in records])
    if len(commits) > 1:
        issues.append(f"{len(commits)} git commits: {', '.join(str(x)[:12] for x in commits)}")
    dirty = [r.run_id for r in records if r.metadata.git_dirty is not False]
    if dirty:
        issues.append(f"{len(dirty)} runs from a dirty or unknown source tree")
    fields: list[tuple[str, list[Any]]] = [
        ("python", [r.metadata.software.python for r in records]),
        ("cpu", [r.metadata.hardware.cpu for r in records]),
    ]
    fields += [
        (p, [r.metadata.software.packages.get(p) for r in records]) for p in TRACKED_PACKAGES
    ]
    for label, values in fields:
        distinct = _distinct(values)
        if len(distinct) > 1:
            issues.append(f"{label} differs: {', '.join(map(str, distinct))}")
    if not issues:
        return Check("environment", "PASS", "one commit, clean tree, identical software and CPU")
    hard = final and (len(commits) > 1 or bool(dirty))
    return Check(
        "environment", "FAIL" if hard else "WARN", "environment is not uniform", tuple(issues)
    )


def _check_extras(c: StudyCollection) -> Check:
    details = (
        [f"duplicate (ignored): {rid}" for _, rid in c.duplicates]
        + [f"interrupted (ignored): {rid}" for _, rid in c.interrupted]
        + [f"unplanned (ignored, config differs from plan): {rid}" for rid in c.unplanned]
        + [f"unreadable: {path}: {why}" for path, why in c.anomalies]
    )
    if details:
        return Check(
            "stray_runs", "WARN", f"{len(details)} stored items are not used", tuple(details)
        )
    return Check("stray_runs", "PASS", "no duplicate, interrupted, unplanned or unreadable runs")


def _check_failed_evaluations(c: StudyCollection) -> Check:
    bad = [
        f"{r.run_id}: {(r.metrics or {}).get('n_failed_evaluations')}"
        for r in c.canonical.values()
        if (r.metrics or {}).get("n_failed_evaluations", 0)
    ]
    if bad:
        return Check(
            "failed_evaluations", "WARN", f"{len(bad)} runs had failed evaluations", tuple(bad)
        )
    return Check("failed_evaluations", "PASS", "no objective evaluation failed")


def _check_failed_trials(c: StudyCollection) -> Check:
    """HPO: trials whose fit raised are kept as infeasible results (ADR 0006)."""
    details = []
    for record in c.canonical.values():
        if record.metadata.outcome != "completed":
            continue
        rows = record.read_history()
        n_failed = sum(r["feasible"] != "True" for r in rows)
        if n_failed:
            details.append(f"{record.run_id}: {n_failed} of {len(rows)} trials failed")
    if details:
        return Check(
            "failed_trials",
            "WARN",
            f"{len(details)} runs contain failed trials (recorded as infeasible)",
            tuple(details),
        )
    return Check("failed_trials", "PASS", "every trial fitted and scored")


def _check_test_evaluations(c: StudyCollection) -> Check:
    """HPO: every completed run has exactly one consistent held-out test evaluation."""
    from evooptlab.hpo.problem import select_trial

    missing, broken = [], []
    for record in c.canonical.values():
        if record.metadata.outcome != "completed":
            continue
        stored = c.test_evaluations.get(record.run_id)
        if stored is None:
            missing.append(record.run_id)
            continue
        if "unreadable" in stored:
            broken.append(f"{record.run_id}: unreadable ({stored['unreadable']})")
            continue
        if stored.get("config_hash") != record.metadata.config_hash:
            broken.append(f"{record.run_id}: config hash differs from the run")
        chosen = select_trial(record.read_history())
        expected = None if chosen is None else int(chosen["evaluation_id"])
        if stored.get("selected_evaluation_id") != expected:
            broken.append(f"{record.run_id}: selected trial is not the validation-best trial")
    if broken:
        return Check(
            "test_evaluations",
            "FAIL",
            f"{len(broken)} test evaluations are inconsistent with their runs",
            tuple(broken),
        )
    if missing:
        status: Status = "FAIL" if c.study.stage == "final" else "WARN"
        return Check(
            "test_evaluations",
            status,
            f"{len(missing)} completed runs have no test evaluation (run `evooptlab test-eval`)",
            tuple(missing),
        )
    return Check("test_evaluations", "PASS", "every completed run has one consistent evaluation")


CHECKS = (
    _check_coverage,
    _check_failed_runs,
    _check_budget,
    _check_history,
    _check_config,
    _check_paired_seeds,
    _check_environment,
    _check_extras,
    _check_failed_evaluations,
)


# ---------------------------------------------------------------------------- timing
@dataclass(frozen=True)
class CellTiming:
    problem: str
    algorithm: str
    n_runs: int
    median_wall_seconds: float
    median_seconds_per_evaluation: float
    median_overhead_fraction: float


def timing_table(c: StudyCollection) -> list[CellTiming]:
    """Per (problem, algorithm) wall-clock statistics of completed runs."""
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for (problem, algorithm, _), record in c.canonical.items():
        m = record.metrics or {}
        if record.metadata.outcome == "completed" and m.get("n_evaluations"):
            groups[(problem, algorithm)].append(m)
    table = []
    for (problem, algorithm), metrics in sorted(groups.items()):
        walls = [float(m["wall_clock_seconds"]) for m in metrics]
        table.append(
            CellTiming(
                problem=problem,
                algorithm=algorithm,
                n_runs=len(metrics),
                median_wall_seconds=statistics.median(walls),
                median_seconds_per_evaluation=statistics.median(
                    float(m["wall_clock_seconds"]) / int(m["n_evaluations"]) for m in metrics
                ),
                median_overhead_fraction=statistics.median(
                    float(m["overhead_seconds"]) / w if w > 0 else 0.0
                    for m, w in zip(metrics, walls, strict=True)
                ),
            )
        )
    return table


def projected_seconds(timings: list[CellTiming], budget: int, n_replicates: int) -> float:
    """Sequential wall-clock estimate of re-running the timed cells at another scale.

    Linear in the budget, so it ignores per-generation cost growth; treat it as a rough guide.
    """
    return sum(t.median_seconds_per_evaluation * budget * n_replicates for t in timings)


# ---------------------------------------------------------------------------- report
@dataclass(frozen=True)
class DiagnosticsReport:
    study: str
    stage: str
    status: Status
    checks: list[Check]
    timings: list[CellTiming]

    def to_dict(self) -> dict[str, Any]:
        return {
            "study": self.study,
            "stage": self.stage,
            "preliminary": self.stage != "final",
            "status": self.status,
            "checks": [
                {
                    "name": c.name,
                    "status": c.status,
                    "summary": c.summary,
                    "details": list(c.details),
                }
                for c in self.checks
            ],
            "timings": [t.__dict__ for t in self.timings],
        }


HPO_CHECKS = (_check_failed_trials, _check_test_evaluations)


def diagnose(collection: StudyCollection) -> DiagnosticsReport:
    checks = [check(collection) for check in CHECKS]
    if collection.study.is_hpo:
        checks += [check(collection) for check in HPO_CHECKS]
    status = max((c.status for c in checks), key=_RANK.__getitem__)
    return DiagnosticsReport(
        study=collection.study.name,
        stage=collection.study.stage,
        status=status,
        checks=checks,
        timings=timing_table(collection),
    )
