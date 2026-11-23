"""On-disk artifact conventions.

Layout::

    <root>/
      pilot/<run_id>/            # preliminary runs; never mixed with final results
      development/<run_id>/
      final/<run_id>/
        run_metadata.json
        config.yaml
        metrics.json
        history.csv
        logs/run.log.jsonl

Run IDs follow ``docs/experimental_protocol.md`` section 8::

    {problem}__{algorithm}__{budget}evals__seed-{seed}__{YYYYMMDD}-{shortid}

Run directories and metadata files are created exclusively: an existing run is never overwritten.
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from evooptlab.storage.metadata import RunMetadata, RunStage

RUN_FILES: Final[dict[str, str]] = {
    "metadata": "run_metadata.json",
    "config": "config.yaml",
    "metrics": "metrics.json",
    "history": "history.csv",
    "log": "logs/run.log.jsonl",
}

_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*(?:_[A-Za-z0-9.\-]+)*$")
_SHORT_ID = re.compile(r"^[0-9a-f]{6,12}$")
_RUN_ID = re.compile(
    r"^(?P<problem>.+?)__(?P<algorithm>.+?)__(?P<budget>\d+)evals"
    r"__seed-(?P<seed>\d+)__(?P<date>\d{8})-(?P<short_id>[0-9a-f]{6,12})$"
)
_STAGES: Final[tuple[RunStage, ...]] = ("pilot", "development", "final")


@dataclass(frozen=True)
class RunIdParts:
    problem: str
    algorithm: str
    budget: int
    seed: int
    date: date
    short_id: str


def _check_component(label: str, value: str) -> None:
    if not _COMPONENT.match(value) or "__" in value:
        raise ValueError(
            f"{label} {value!r} must be alphanumeric with single '_', '-', or '.' separators "
            "(double underscores are reserved as run-id delimiters)"
        )


def make_run_id(
    problem: str,
    algorithm: str,
    budget: int,
    seed: int,
    when: datetime | None = None,
    short_id: str | None = None,
) -> str:
    """Build a unique, human-readable run ID following the protocol naming scheme."""
    _check_component("problem", problem)
    _check_component("algorithm", algorithm)
    if budget <= 0:
        raise ValueError("budget must be positive")
    if seed < 0:
        raise ValueError("seed must be non-negative")
    stamp = (when or datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%d")
    sid = short_id if short_id is not None else secrets.token_hex(3)
    if not _SHORT_ID.match(sid):
        raise ValueError("short_id must be 6-12 lowercase hex characters")
    return f"{problem}__{algorithm}__{budget}evals__seed-{seed}__{stamp}-{sid}"


def parse_run_id(run_id: str) -> RunIdParts:
    """Inverse of :func:`make_run_id`."""
    match = _RUN_ID.match(run_id)
    if match is None:
        raise ValueError(f"not a valid run id: {run_id!r}")
    return RunIdParts(
        problem=match["problem"],
        algorithm=match["algorithm"],
        budget=int(match["budget"]),
        seed=int(match["seed"]),
        date=datetime.strptime(match["date"], "%Y%m%d").replace(tzinfo=UTC).date(),
        short_id=match["short_id"],
    )


@dataclass(frozen=True)
class ArtifactLayout:
    """Resolve and create artifact paths under a single root directory."""

    root: Path

    def stage_dir(self, stage: RunStage) -> Path:
        if stage not in _STAGES:
            raise ValueError(f"unknown stage {stage!r}; expected one of {_STAGES}")
        return self.root / stage

    def run_dir(self, stage: RunStage, run_id: str) -> Path:
        parse_run_id(run_id)  # validates; prevents path traversal via crafted ids
        return self.stage_dir(stage) / run_id

    def run_file(self, stage: RunStage, run_id: str, kind: str) -> Path:
        try:
            relative = RUN_FILES[kind]
        except KeyError as exc:
            expected = sorted(RUN_FILES)
            raise ValueError(f"unknown run file kind {kind!r}; expected {expected}") from exc
        return self.run_dir(stage, run_id) / relative

    def create_run_dir(self, stage: RunStage, run_id: str) -> Path:
        """Create a new, empty run directory. Fails if the run already exists."""
        path = self.run_dir(stage, run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.mkdir(exist_ok=False)
        (path / "logs").mkdir()
        return path

    def write_metadata(self, metadata: RunMetadata) -> Path:
        """Write ``run_metadata.json`` for a new run. Never overwrites an existing file."""
        path = self.run_file(metadata.status, metadata.run_id, "metadata")
        _write_new_json(path, metadata)
        return path

    def read_metadata(self, stage: RunStage, run_id: str) -> RunMetadata:
        path = self.run_file(stage, run_id, "metadata")
        return RunMetadata.model_validate_json(path.read_text(encoding="utf-8"))

    def record_finish(self, metadata: RunMetadata) -> Path:
        """Replace a *running* run's metadata with its finished version, atomically.

        This is the only permitted rewrite of ``run_metadata.json``: the stored record must
        still be ``running`` and identical in every field except the finish fields. Finished
        records are immutable.
        """
        if metadata.outcome == "running":
            raise ValueError("record_finish requires a completed or failed outcome")
        stored = self.read_metadata(metadata.status, metadata.run_id)
        if stored.outcome != "running":
            raise FileExistsError(f"run {metadata.run_id} is already finished; refusing to rewrite")
        finish_fields = {"finished_at_utc", "outcome", "failure_reason"}
        if stored.model_dump(exclude=finish_fields) != metadata.model_dump(exclude=finish_fields):
            raise ValueError("only finish fields may change when recording a run's finish")
        path = self.run_file(metadata.status, metadata.run_id, "metadata")
        tmp = path.with_name(path.name + ".tmp")
        _write_new_json(tmp, metadata)
        tmp.replace(path)
        return path


def _write_new_json(path: Path, model: RunMetadata) -> None:
    """Write ``model`` as JSON to ``path``, failing if the file already exists."""
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(model.model_dump_json(indent=2))
        handle.write("\n")
