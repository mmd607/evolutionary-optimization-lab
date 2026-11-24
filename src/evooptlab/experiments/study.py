"""Run a whole study matrix, with resume that can never corrupt or overwrite artifacts.

Resume rules (ADR 0005)
-----------------------
A stored run belongs to a planned cell when its ``config_hash`` equals the cell's hash, which
covers problem, algorithm parameters, seed, budget, stage, timeout, study name and replicate.

* **completed** -> the cell is done and is skipped.
* **failed** (any reason except interruption) -> the cell is done and is skipped. A genuine failure
  is a result. Re-running until success would be cherry-picking.
* **interrupted** (still ``running`` after a crash, or ``failed`` with an ``interrupted:`` reason)
  -> the cell runs again under a *new* run ID. The interrupted run stays on disk, untouched.

Without ``resume``, a study refuses to start if any of its cells already has stored runs, so
running the same study twice cannot create silent duplicates.

Final-stage runs additionally require a known, clean git commit, so every final result traces to
committed code.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from evooptlab.config.schemas import StudyConfig
from evooptlab.core.experiment import ExperimentRunner
from evooptlab.experiments.matrix import (
    CellKey,
    RunCell,
    StudyError,
    build_matrix,
    cell_config_hash,
    run_spec,
)
from evooptlab.experiments.records import RunRecord, scan_stage
from evooptlab.storage.layout import ArtifactLayout
from evooptlab.utils.environment import capture_environment
from evooptlab.utils.logging import get_logger

log = get_logger(__name__)

Progress = Callable[[int, int, RunCell, str], None]


@dataclass
class StudyRunReport:
    executed: list[tuple[CellKey, str, str]] = field(default_factory=list)  # key, run_id, outcome
    skipped: list[tuple[CellKey, str]] = field(default_factory=list)  # key, existing run_id

    @property
    def n_failed(self) -> int:
        return sum(1 for _, _, outcome in self.executed if outcome != "completed")


def index_by_hash(records: list[RunRecord]) -> dict[str, list[RunRecord]]:
    index: dict[str, list[RunRecord]] = {}
    for record in records:
        if record.metadata.config_hash is not None:
            index.setdefault(record.metadata.config_hash, []).append(record)
    return index


def finished_record(records: list[RunRecord]) -> RunRecord | None:
    """The earliest stored run that settles a cell, or ``None`` if the cell must (re)run."""
    for record in records:  # already ordered by start time
        if not record.interrupted:
            return record
    return None


def _require_clean_commit(repo_root: Path | None) -> None:
    git = capture_environment(repo_root).git
    if git.commit is None:
        raise StudyError("final-stage studies require a git checkout with a known commit")
    if git.dirty is not False:
        raise StudyError(
            "final-stage studies require a clean working tree (dirty or unknown); "
            "commit or stash changes first"
        )


def run_study(
    study: StudyConfig,
    layout: ArtifactLayout,
    *,
    resume: bool = False,
    repo_root: Path | None = None,
    lock_file: Path | None = None,
    progress: Progress | None = None,
) -> StudyRunReport:
    """Run every planned cell of ``study`` that is not already settled."""
    cells = build_matrix(study)
    if study.stage == "final":
        _require_clean_commit(repo_root)
    index = index_by_hash(scan_stage(layout, study.stage).records)
    hashes = [cell_config_hash(study, cell) for cell in cells]

    existing = sum(1 for h in hashes if h in index)
    if existing and not resume:
        raise StudyError(
            f"study {study.name!r} already has stored runs for {existing} of {len(cells)} cells "
            f"under {layout.stage_dir(study.stage)}; pass resume to continue it"
        )

    runner = ExperimentRunner(layout, repo_root=repo_root, lock_file=lock_file)
    report = StudyRunReport()
    for position, (cell, cell_hash) in enumerate(zip(cells, hashes, strict=True), start=1):
        settled = finished_record(index.get(cell_hash, []))
        if settled is not None:
            report.skipped.append((cell.key, settled.run_id))
            if progress:
                progress(position, len(cells), cell, f"skipped ({settled.metadata.outcome})")
            continue
        result = runner.run(cell.build_problem(), cell.build_algorithm(), run_spec(study, cell))
        if result.metadata.config_hash != cell_hash:  # pragma: no cover - internal invariant
            raise StudyError(f"run {result.run_id} hash does not match its planned cell")
        report.executed.append((cell.key, result.run_id, result.outcome))
        if progress:
            progress(position, len(cells), cell, result.outcome)
    log.info(
        "study finished",
        extra={
            "study": study.name,
            "executed": len(report.executed),
            "skipped": len(report.skipped),
            "failed": report.n_failed,
        },
    )
    return report
