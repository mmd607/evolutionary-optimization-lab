"""Index of one artifact root: runs, aggregates, analysis reports and test evaluations.

Layout (ADR 0005-0007)::

    <root>/{pilot,development,final}/<run_id>/      runs
    <root>/aggregates/<stage>/<name>/               evooptlab aggregate
    <root>/reports/<name>/analysis.json             evooptlab report (default location)
    <root>/test_evaluations/<stage>/<run_id>.json   evooptlab test-eval

Rules:

* Nothing is written, created or deleted. Unreadable entries are listed as anomalies.
* The stage of every entry is kept, so pilot or development numbers cannot be mistaken for
  final ones.
* An aggregate is **stale** when the runs on disk no longer match it: a run it lists is missing,
  or a run of its study started after it was written. A report inherits the staleness of its
  source aggregate, and is stale when that aggregate is not under this root.
"""

from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from evooptlab.experiments.records import RunRecord, read_test_evaluations, scan_stage
from evooptlab.storage.layout import ArtifactLayout
from evooptlab.storage.metadata import RunStage

STAGES: tuple[RunStage, ...] = ("pilot", "development", "final")
NO_STUDY = "(no study)"


@dataclass(frozen=True)
class RunEntry:
    """One stored run, flattened for tables. ``record`` keeps the full artifacts."""

    stage: RunStage
    run_id: str
    study: str
    kind: str
    problem: str
    algorithm: str
    seed: int
    budget: int
    outcome: str
    failure_reason: str | None
    started_at_utc: datetime
    finished_at_utc: datetime | None
    n_evaluations: int | None
    n_feasible: int | None
    wall_clock_seconds: float | None
    git_commit: str | None
    git_dirty: bool | None
    config_hash: str | None
    record: RunRecord = field(compare=False, repr=False)

    @property
    def path(self) -> Path:
        return self.record.run_dir

    @property
    def preliminary(self) -> bool:
        return self.stage != "final"

    @property
    def n_objectives(self) -> int:
        problem = (self.record.config or {}).get("problem") or {}
        return int(problem.get("n_objectives", 1))

    def row(self) -> dict[str, Any]:
        """Display row; ``None`` stays ``None`` (shown as empty, never as zero)."""
        return {
            "stage": self.stage,
            "study": self.study,
            "problem": self.problem,
            "algorithm": self.algorithm,
            "seed": self.seed,
            "budget": self.budget,
            "outcome": self.outcome,
            "n_evaluations": self.n_evaluations,
            "n_feasible": self.n_feasible,
            "wall_clock_seconds": self.wall_clock_seconds,
            "started_at_utc": self.started_at_utc.isoformat(),
            "git_commit": (self.git_commit or "")[:12] or None,
            "git_dirty": self.git_dirty,
            "run_id": self.run_id,
        }


@dataclass(frozen=True)
class AggregateEntry:
    path: Path
    study: str
    stage: str
    kind: str
    preliminary: bool
    created_at_utc: datetime | None
    diagnostics_status: str | None
    run_ids: tuple[str, ...]
    git_commit: str | None
    git_dirty: bool | None
    stale_reasons: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stale(self) -> bool:
        return bool(self.stale_reasons)


@dataclass(frozen=True)
class ReportEntry:
    path: Path
    study: str
    stage: str
    kind: str
    preliminary: bool
    plan_name: str | None
    plan_status: str | None
    aggregate_name: str | None
    stale_reasons: tuple[str, ...] = ()

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def stale(self) -> bool:
        return bool(self.stale_reasons)

    def analysis(self) -> dict[str, Any]:
        data = json.loads((self.path / "analysis.json").read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"{self.path / 'analysis.json'}: not a JSON object")
        return data


@dataclass
class Catalog:
    root: Path
    loaded_at_utc: datetime
    runs: list[RunEntry] = field(default_factory=list)
    aggregates: list[AggregateEntry] = field(default_factory=list)
    reports: list[ReportEntry] = field(default_factory=list)
    test_evaluations: dict[str, dict[str, dict[str, Any]]] = field(default_factory=dict)
    #: ``(path, reason)`` of entries that could not be read.
    anomalies: list[tuple[str, str]] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not (self.runs or self.aggregates or self.reports)

    def stages(self) -> list[str]:
        present = {r.stage for r in self.runs} | {a.stage for a in self.aggregates}
        return [s for s in STAGES if s in present]

    def studies(self, stage: str | None = None) -> list[str]:
        return sorted({r.study for r in self.runs if stage is None or r.stage == stage})

    def select(
        self,
        *,
        stage: str | None = None,
        study: str | None = None,
        kind: str | None = None,
        problem: str | None = None,
        algorithm: str | None = None,
        completed_only: bool = False,
    ) -> list[RunEntry]:
        return [
            r
            for r in self.runs
            if (stage is None or r.stage == stage)
            and (study is None or r.study == study)
            and (kind is None or r.kind == kind)
            and (problem is None or r.problem == problem)
            and (algorithm is None or r.algorithm == algorithm)
            and (not completed_only or r.outcome == "completed")
        ]

    def run(self, stage: str, run_id: str) -> RunEntry | None:
        return next((r for r in self.runs if r.stage == stage and r.run_id == run_id), None)

    def test_evaluation(self, run: RunEntry) -> dict[str, Any] | None:
        return self.test_evaluations.get(run.stage, {}).get(run.run_id)

    def latest_run(self) -> RunEntry | None:
        return max(self.runs, key=lambda r: (r.started_at_utc, r.run_id), default=None)

    def overview(self) -> list[dict[str, Any]]:
        """Run counts per stage and study, by outcome."""
        counts: Counter[tuple[str, str, str]] = Counter(
            (r.stage, r.study, r.outcome) for r in self.runs
        )
        rows: dict[tuple[str, str], dict[str, Any]] = {}
        for (stage, study, outcome), n in sorted(counts.items(), key=_stage_order):
            row = rows.setdefault(
                (stage, study),
                {
                    "stage": stage,
                    "study": study,
                    "kind": None,
                    "runs": 0,
                    "completed": 0,
                    "failed": 0,
                    "running": 0,
                    "problems": 0,
                    "algorithms": 0,
                },
            )
            row["runs"] += n
            row[outcome] += n
        for (stage, study), row in rows.items():
            runs = self.select(stage=stage, study=study)
            row["kind"] = ", ".join(sorted({r.kind for r in runs}))
            row["problems"] = len({r.problem for r in runs})
            row["algorithms"] = len({r.algorithm for r in runs})
        return list(rows.values())

    def environments(self) -> list[dict[str, Any]]:
        """Distinct source trees and environments the runs were produced with."""
        counts: Counter[tuple[Any, ...]] = Counter()
        for r in self.runs:
            m = r.record.metadata
            packages = ", ".join(f"{k} {v}" for k, v in sorted(m.software.packages.items()))
            counts[
                (
                    r.stage,
                    (r.git_commit or "")[:12] or None,
                    r.git_dirty,
                    m.software.python,
                    m.hardware.cpu,
                    packages,
                )
            ] += 1
        keys = ("stage", "git_commit", "git_dirty", "python", "cpu", "packages")
        return [
            {**dict(zip(keys, key, strict=True)), "runs": n}
            for key, n in sorted(counts.items(), key=lambda kv: str(kv[0]))
        ]


_STAGE_RANK: dict[str, int] = {stage: i for i, stage in enumerate(STAGES)}


def _stage_order(item: tuple[tuple[str, str, str], int]) -> tuple[int, str, str]:
    (stage, study, outcome), _ = item
    return (_STAGE_RANK.get(stage, len(STAGES)), study, outcome)


def _entry(stage: RunStage, record: RunRecord) -> RunEntry:
    m = record.metadata
    metrics = record.metrics or {}
    details = ((record.config or {}).get("problem") or {}).get("details") or {}

    def number(key: str, cast: type[int] | type[float]) -> Any:
        value = metrics.get(key)
        return None if value is None else cast(value)

    return RunEntry(
        stage=stage,
        run_id=m.run_id,
        study=record.study or NO_STUDY,
        kind="hpo" if details.get("kind") == "hpo" else "benchmark",
        problem=m.problem,
        algorithm=m.algorithm,
        seed=m.seed,
        budget=m.objective_evaluation_budget,
        outcome=m.outcome,
        failure_reason=m.failure_reason,
        started_at_utc=m.started_at_utc,
        finished_at_utc=m.finished_at_utc,
        n_evaluations=number("n_evaluations", int),
        n_feasible=number("n_feasible", int),
        wall_clock_seconds=number("wall_clock_seconds", float),
        git_commit=m.git_commit,
        git_dirty=m.git_dirty,
        config_hash=m.config_hash,
        record=record,
    )


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        stamp = datetime.fromisoformat(value)
    except ValueError:
        return None
    return stamp if stamp.tzinfo else stamp.replace(tzinfo=UTC)


def _read_object(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("not a JSON object")
    return data


def _scan_aggregates(root: Path, catalog: Catalog) -> None:
    base = root / "aggregates"
    if not base.is_dir():
        return
    for stage_dir in sorted(p for p in base.iterdir() if p.is_dir()):
        for path in sorted(p for p in stage_dir.iterdir() if p.is_dir()):
            try:
                manifest = _read_object(path / "manifest.json")
                header = (path / "runs.csv").read_text(encoding="utf-8").partition("\n")[0]
                entry = AggregateEntry(
                    path=path,
                    study=str(manifest["study"]),
                    stage=str(manifest["stage"]),
                    kind="hpo" if "best_validation_error" in header.split(",") else "benchmark",
                    preliminary=bool(manifest.get("preliminary", True)),
                    created_at_utc=_timestamp(manifest.get("created_at_utc")),
                    diagnostics_status=(manifest.get("diagnostics") or {}).get("status"),
                    run_ids=tuple(manifest.get("run_ids") or ()),
                    git_commit=manifest.get("aggregator_git_commit"),
                    git_dirty=manifest.get("aggregator_git_dirty"),
                )
            except (OSError, ValueError, KeyError) as exc:
                catalog.anomalies.append((str(path), f"aggregate: {type(exc).__name__}: {exc}"))
                continue
            catalog.aggregates.append(entry)


def _aggregate_staleness(entry: AggregateEntry, catalog: Catalog) -> tuple[str, ...]:
    reasons = []
    present = {r.run_id for r in catalog.runs if r.stage == entry.stage}
    missing = [rid for rid in entry.run_ids if rid not in present]
    if missing:
        reasons.append(f"{len(missing)} run(s) it lists are not under this root")
    if entry.created_at_utc is not None:
        newer = [
            r
            for r in catalog.select(stage=entry.stage, study=entry.study)
            if r.started_at_utc > entry.created_at_utc and r.run_id not in entry.run_ids
        ]
        if newer:
            reasons.append(f"{len(newer)} run(s) of the study started after it was written")
    else:
        reasons.append("no creation time recorded")
    return tuple(reasons)


def _scan_reports(root: Path, catalog: Catalog) -> None:
    base = root / "reports"
    if not base.is_dir():
        return
    aggregates = {a.name: a for a in catalog.aggregates}
    for path in sorted(p for p in base.iterdir() if (p / "analysis.json").is_file()):
        try:
            data = _read_object(path / "analysis.json")
            plan = data.get("plan") or {}
            source = data.get("source") or {}
            aggregate_name = Path(source["aggregate"]).name if source.get("aggregate") else None
            reasons: tuple[str, ...]
            source_aggregate = aggregates.get(aggregate_name or "")
            if source_aggregate is None:
                reasons = ("its source aggregate is not under this root",)
            else:
                reasons = tuple(f"source aggregate: {r}" for r in source_aggregate.stale_reasons)
            entry = ReportEntry(
                path=path,
                study=str(data["study"]),
                stage=str(data["stage"]),
                kind=str(data.get("kind", "benchmark")),
                preliminary=bool(data.get("preliminary", True)),
                plan_name=plan.get("name"),
                plan_status=plan.get("status"),
                aggregate_name=aggregate_name,
                stale_reasons=reasons,
            )
        except (OSError, ValueError, KeyError) as exc:
            catalog.anomalies.append((str(path), f"report: {type(exc).__name__}: {exc}"))
            continue
        catalog.reports.append(entry)


def scan_artifacts(root: Path) -> Catalog:
    """Index everything stored under ``root``. Never modifies the root."""
    catalog = Catalog(root=root, loaded_at_utc=datetime.now(UTC))
    if not root.is_dir():
        catalog.anomalies.append((str(root), "artifact root does not exist"))
        return catalog
    layout = ArtifactLayout(root)
    for stage in STAGES:
        scan = scan_stage(layout, stage)
        catalog.runs.extend(_entry(stage, record) for record in scan.records)
        catalog.anomalies.extend(scan.anomalies)
        evaluations = read_test_evaluations(layout, stage)
        if evaluations:
            catalog.test_evaluations[stage] = evaluations
    _scan_aggregates(root, catalog)
    catalog.aggregates = [
        replace(a, stale_reasons=_aggregate_staleness(a, catalog)) for a in catalog.aggregates
    ]
    _scan_reports(root, catalog)
    return catalog
