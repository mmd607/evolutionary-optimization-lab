"""Typed, validated schemas for the YAML files in ``configs/``.

Design notes
------------
* Every model forbids unknown keys so that typos fail loudly instead of being ignored.
* Some protocol decisions are intentionally still open (for example the Wine Quality target
  metric). Those are written in the YAML as explicit placeholder strings such as
  ``define_before_run``. They are *accepted* by validation so that pilot work can proceed, but
  :func:`unresolved_fields` reports them, and ``strict`` loading rejects them. This keeps open
  decisions visible instead of silently inventing values.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated, Literal, TypeAlias

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

#: Strings that mark a protocol decision as deliberately unresolved.
PLACEHOLDER_VALUES: frozenset[str] = frozenset(
    {"define_before_run", "classification_or_regression", "task_specific", "tbd", "TBD"}
)

PositiveInt = Annotated[int, Field(gt=0)]
NonNegativeInt = Annotated[int, Field(ge=0)]
Identifier = Annotated[str, Field(min_length=1, pattern=r"^[A-Za-z][A-Za-z0-9_\-]*$")]


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)


# ---------------------------------------------------------------------------
# configs/benchmarks.yaml
# ---------------------------------------------------------------------------
class BenchmarkProblemConfig(_StrictModel):
    """A single benchmark problem entry."""

    name: Identifier
    objectives: Annotated[int, Field(ge=1)]
    variables: PositiveInt


class BenchmarkSuiteConfig(_StrictModel):
    """A named benchmark suite with a shared evaluation budget and seed list."""

    name: Identifier
    problems: Annotated[list[BenchmarkProblemConfig], Field(min_length=1)]
    evaluation_budget: PositiveInt
    seeds: Annotated[list[NonNegativeInt], Field(min_length=1)]
    pilot: bool

    @field_validator("seeds")
    @classmethod
    def _seeds_unique(cls, seeds: list[int]) -> list[int]:
        if len(set(seeds)) != len(seeds):
            raise ValueError("seeds must be unique; duplicated seeds silently reduce n")
        return seeds

    @field_validator("problems")
    @classmethod
    def _problem_names_unique(
        cls, problems: list[BenchmarkProblemConfig]
    ) -> list[BenchmarkProblemConfig]:
        names = [p.name for p in problems]
        if len(set(names)) != len(names):
            raise ValueError("benchmark problem names must be unique")
        return problems


class BenchmarksFile(_StrictModel):
    """Top-level structure of ``configs/benchmarks.yaml``."""

    benchmark_suite: BenchmarkSuiteConfig


# ---------------------------------------------------------------------------
# configs/experiments.yaml
# ---------------------------------------------------------------------------
class BudgetConfig(_StrictModel):
    """Evaluation budget. Objective evaluations are the primary comparison control."""

    unit: Literal["objective_evaluations"]
    max_evaluations: PositiveInt


class ExecutionConfig(_StrictModel):
    n_jobs: PositiveInt
    timeout_seconds: PositiveInt


LogLevel: TypeAlias = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]


class LoggingConfig(_StrictModel):
    level: LogLevel = "INFO"
    save_history: bool = True
    save_population: bool = False


class ReproducibilityConfig(_StrictModel):
    record_git_commit: bool = True
    record_environment: bool = True


class ExperimentConfig(_StrictModel):
    """Experiment-level settings shared by all runs of one study."""

    name: Identifier
    output_dir: Annotated[str, Field(min_length=1)]
    master_seed: NonNegativeInt
    algorithms: Annotated[list[Identifier], Field(min_length=1)]
    budget: BudgetConfig
    execution: ExecutionConfig
    logging: LoggingConfig = LoggingConfig()
    reproducibility: ReproducibilityConfig = ReproducibilityConfig()

    @field_validator("algorithms")
    @classmethod
    def _algorithms_unique(cls, algorithms: list[str]) -> list[str]:
        if len(set(algorithms)) != len(algorithms):
            raise ValueError("algorithm names must be unique")
        return algorithms


class ExperimentsFile(_StrictModel):
    """Top-level structure of ``configs/experiments.yaml``."""

    experiment: ExperimentConfig


# ---------------------------------------------------------------------------
# configs/hpo_tasks.yaml
# ---------------------------------------------------------------------------
TaskType: TypeAlias = Literal["classification", "regression", "classification_or_regression"]
TaskRole: TypeAlias = Literal["pipeline_smoke_test_only", "compact_hpo_task"]


class HPOTaskConfig(_StrictModel):
    name: Identifier
    source: Annotated[str, Field(min_length=1)]
    task_type: TaskType
    role: TaskRole
    target_metric: Annotated[str, Field(min_length=1)]


class SplitConfig(_StrictModel):
    strategy: Annotated[str, Field(min_length=1)]
    test_fraction: Annotated[float, Field(gt=0.0, lt=1.0)]
    random_seed: NonNegativeInt


class SearchConfig(_StrictModel):
    max_trials: PositiveInt
    timeout_seconds: PositiveInt


class HPOConfig(_StrictModel):
    tasks: Annotated[list[HPOTaskConfig], Field(min_length=1)]
    split: SplitConfig
    search: SearchConfig

    @model_validator(mode="after")
    def _task_names_unique(self) -> HPOConfig:
        names = [t.name for t in self.tasks]
        if len(set(names)) != len(names):
            raise ValueError("HPO task names must be unique")
        return self


class HPOTasksFile(_StrictModel):
    """Top-level structure of ``configs/hpo_tasks.yaml``."""

    hpo: HPOConfig


AnyConfig: TypeAlias = BenchmarksFile | ExperimentsFile | HPOTasksFile


# ---------------------------------------------------------------------------
# Unresolved-decision reporting
# ---------------------------------------------------------------------------
def _walk(value: object, path: str) -> Iterator[tuple[str, str]]:
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _walk(getattr(value, name), f"{path}.{name}" if path else name)
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    elif isinstance(value, str) and value in PLACEHOLDER_VALUES:
        yield path, value


def unresolved_fields(config: BaseModel) -> list[tuple[str, str]]:
    """Return ``(dotted_path, placeholder)`` pairs for every unresolved decision in ``config``."""
    return list(_walk(config, ""))
