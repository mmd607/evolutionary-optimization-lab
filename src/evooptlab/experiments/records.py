"""Read stored runs of one stage back from disk, without ever modifying them."""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import yaml
from pydantic import ValidationError

from evooptlab.core.problem import FloatArray
from evooptlab.storage.layout import RUN_FILES, ArtifactLayout, parse_run_id
from evooptlab.storage.metadata import RunMetadata, RunStage


@dataclass(frozen=True)
class RunRecord:
    """A stored run: its directory, metadata, and (if present) config and metrics."""

    run_dir: Path
    metadata: RunMetadata
    config: dict[str, Any] | None
    metrics: dict[str, Any] | None

    @property
    def run_id(self) -> str:
        return self.metadata.run_id

    @property
    def study(self) -> str | None:
        extra = (self.config or {}).get("extra") or {}
        value = extra.get("study")
        return value if isinstance(value, str) else None

    @property
    def interrupted(self) -> bool:
        """Still ``running`` (process killed) or recorded as interrupted by a signal."""
        m = self.metadata
        return m.outcome == "running" or (
            m.outcome == "failed" and (m.failure_reason or "").startswith("interrupted")
        )

    def history_path(self) -> Path:
        return self.run_dir / RUN_FILES["history"]

    def read_history(self) -> list[dict[str, str]]:
        path = self.history_path()
        if not path.exists():
            return []
        with path.open(encoding="utf-8", newline="") as handle:
            return list(csv.DictReader(handle))


@dataclass(frozen=True)
class ScanResult:
    records: list[RunRecord]
    #: ``(path, reason)`` for directories that are not readable runs; never deleted.
    anomalies: list[tuple[str, str]]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def _read_yaml(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def scan_stage(layout: ArtifactLayout, stage: RunStage) -> ScanResult:
    """Load every run of ``stage``, ordered by start time then run ID."""
    stage_dir = layout.stage_dir(stage)
    records: list[RunRecord] = []
    anomalies: list[tuple[str, str]] = []
    if not stage_dir.is_dir():
        return ScanResult(records, anomalies)
    for path in sorted(stage_dir.iterdir()):
        if not path.is_dir():
            anomalies.append((str(path), "not a run directory"))
            continue
        try:
            parse_run_id(path.name)
            metadata = RunMetadata.model_validate_json(
                (path / RUN_FILES["metadata"]).read_text(encoding="utf-8")
            )
            config = _read_yaml(path / RUN_FILES["config"])
            metrics = _read_json(path / RUN_FILES["metrics"])
        except (OSError, ValueError, ValidationError, yaml.YAMLError) as exc:
            anomalies.append((str(path), f"{type(exc).__name__}: {exc}".splitlines()[0]))
            continue
        if metadata.run_id != path.name:
            anomalies.append((str(path), f"metadata run_id {metadata.run_id!r} != directory"))
            continue
        records.append(RunRecord(path, metadata, config, metrics))
    records.sort(key=lambda r: (r.metadata.started_at_utc, r.run_id))
    return ScanResult(records, anomalies)


def history_objectives(
    rows: list[dict[str, str]], n_objectives: int
) -> tuple[FloatArray, np.ndarray[Any, np.dtype[np.bool_]]]:
    """Objective matrix and feasibility mask of a stored ``history.csv``."""
    f = np.array(
        [[float(r[f"f_{j}"]) for j in range(n_objectives)] for r in rows], dtype=np.float64
    ).reshape(len(rows), n_objectives)
    feasible = np.array([r["feasible"] == "True" for r in rows], dtype=np.bool_)
    return f, feasible


# ---------------------------------------------------------------------------------------------
# HPO test evaluations (written by ``evooptlab test-eval``; see experiments/hpo_evaluation.py)
# ---------------------------------------------------------------------------------------------
def held_out_dir(layout: ArtifactLayout, stage: RunStage) -> Path:
    return layout.root / "test_evaluations" / stage


def held_out_path(layout: ArtifactLayout, stage: RunStage, run_id: str) -> Path:
    return held_out_dir(layout, stage) / f"{run_id}.json"


def read_test_evaluations(layout: ArtifactLayout, stage: RunStage) -> dict[str, dict[str, Any]]:
    """Stored evaluations by run ID; unreadable files map to ``{"unreadable": reason}``."""
    out: dict[str, dict[str, Any]] = {}
    directory = held_out_dir(layout, stage)
    if not directory.is_dir():
        return out
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("not a JSON object")
            out[path.stem] = data
        except (OSError, ValueError) as exc:
            out[path.stem] = {"unreadable": f"{type(exc).__name__}: {exc}"}
    return out
