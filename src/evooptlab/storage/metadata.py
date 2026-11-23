"""Schema for ``run_metadata.json``.

The schema follows ``templates/run_metadata.json`` with these documented additions (see
``docs/decisions/0001-foundation-and-protocol-decisions.md``):

* ``schema_version`` so stored artifacts can be migrated safely;
* ``outcome`` (running / completed / failed) and ``failure_reason`` so failed runs are recorded,
  not dropped;
* ``config_hash`` and ``git_dirty`` so a result can be traced to an exact config and source tree.

``status`` keeps its template meaning: the *stage* of the study the run belongs to.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Final, Literal, TypeAlias

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

METADATA_SCHEMA_VERSION: Final = "1"

RunStage: TypeAlias = Literal["pilot", "development", "final"]
RunOutcome: TypeAlias = Literal["running", "completed", "failed"]


class HardwareInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    cpu: str
    gpu: str | None = None
    ram_gb: Annotated[float, Field(gt=0)] | None = None


class SoftwareInfo(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    python: str
    packages_lock_hash: str | None = None
    packages: dict[str, str | None] = Field(default_factory=dict)


class RunMetadata(BaseModel):
    """Immutable description of a single optimization run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1"] = METADATA_SCHEMA_VERSION
    run_id: Annotated[str, Field(min_length=1)]
    project: Literal["EvoOptLab"] = "EvoOptLab"
    git_commit: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")] | None
    git_dirty: bool | None = None
    algorithm: Annotated[str, Field(min_length=1)]
    problem: Annotated[str, Field(min_length=1)]
    seed: Annotated[int, Field(ge=0)]
    objective_evaluation_budget: Annotated[int, Field(gt=0)]
    started_at_utc: AwareDatetime
    finished_at_utc: AwareDatetime | None = None
    hardware: HardwareInfo
    software: SoftwareInfo
    config_path: Annotated[str, Field(min_length=1)]
    config_hash: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")] | None = None
    status: RunStage
    outcome: RunOutcome = "running"
    failure_reason: str | None = None

    @model_validator(mode="after")
    def _check_consistency(self) -> RunMetadata:
        if self.finished_at_utc is not None and self.finished_at_utc < self.started_at_utc:
            raise ValueError("finished_at_utc must not be earlier than started_at_utc")
        if self.outcome == "running" and self.finished_at_utc is not None:
            raise ValueError("a running run cannot have finished_at_utc")
        if self.outcome != "running" and self.finished_at_utc is None:
            raise ValueError(f"outcome {self.outcome!r} requires finished_at_utc")
        if self.outcome == "failed" and not self.failure_reason:
            raise ValueError("failed runs must record failure_reason")
        if self.outcome != "failed" and self.failure_reason is not None:
            raise ValueError("failure_reason is only allowed for failed runs")
        return self

    def finished(
        self,
        at: datetime,
        outcome: Literal["completed", "failed"],
        failure_reason: str | None = None,
    ) -> RunMetadata:
        """Return a copy marked as finished. The original object is not modified."""
        return RunMetadata.model_validate(
            {
                **self.model_dump(),
                "finished_at_utc": at,
                "outcome": outcome,
                "failure_reason": failure_reason,
            }
        )
