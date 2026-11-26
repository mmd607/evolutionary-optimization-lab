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


# ---------------------------------------------------------------------------
# configs/studies/*.yaml
# ---------------------------------------------------------------------------
StudyStage: TypeAlias = Literal["pilot", "development", "final"]
ParameterValue: TypeAlias = bool | int | float | str | None


class ExplicitSeeds(_StrictModel):
    """Seed policy *explicit*: every replicate's run seed is listed (ADR 0001, P6)."""

    policy: Literal["explicit"]
    values: Annotated[list[NonNegativeInt], Field(min_length=1)]

    @field_validator("values")
    @classmethod
    def _seeds_unique(cls, values: list[int]) -> list[int]:
        if len(set(values)) != len(values):
            raise ValueError("seeds must be unique; duplicated seeds silently reduce n")
        return values


class DerivedSeeds(_StrictModel):
    """Seed policy *derived*: run seeds come from ``master_seed`` per problem (ADR 0001, P6)."""

    policy: Literal["derived"]
    master_seed: NonNegativeInt
    n_replicates: PositiveInt


SeedPolicy: TypeAlias = Annotated[ExplicitSeeds | DerivedSeeds, Field(discriminator="policy")]


class StudyAlgorithmConfig(_StrictModel):
    """A registered algorithm and its explicit hyperparameter overrides (empty = defaults)."""

    name: Identifier
    parameters: dict[str, ParameterValue] = Field(default_factory=dict)


ChoiceValue: TypeAlias = bool | int | float | str


class SearchParameterConfig(_StrictModel):
    """One hyperparameter of an HPO search space (ADR 0006).

    Every algorithm searches the same unit cube; ``float`` and ``int`` map a coordinate linearly
    or, with ``log: true``, log-uniformly onto ``[low, high]``; ``categorical`` splits it into
    equal-width bins, one per choice.
    """

    type: Literal["float", "int", "categorical"]
    low: float | None = None
    high: float | None = None
    log: bool = False
    choices: list[ChoiceValue] | None = None

    @model_validator(mode="after")
    def _consistent(self) -> SearchParameterConfig:
        if self.type == "categorical":
            if self.low is not None or self.high is not None or self.log:
                raise ValueError("categorical parameters take only 'choices'")
            if not self.choices or len(self.choices) < 2:
                raise ValueError("categorical parameters need at least two choices")
            if len({repr(c) for c in self.choices}) != len(self.choices):
                raise ValueError("categorical choices must be unique")
            return self
        if self.choices is not None:
            raise ValueError(f"{self.type} parameters take 'low'/'high', not 'choices'")
        if self.low is None or self.high is None or not self.low < self.high:
            raise ValueError(f"{self.type} parameters need low < high")
        if self.log and self.low <= 0:
            raise ValueError("log-scaled parameters need low > 0")
        if self.type == "int" and not (self.low.is_integer() and self.high.is_integer()):
            raise ValueError("int parameters need integral low and high")
        return self


class HPOSplitStudyConfig(_StrictModel):
    """Train/test split of an HPO problem. The test part is never visible to the optimizer.

    ``stratified``/``random`` draw the test rows with ``random_seed``; ``ordered`` keeps the
    file order and holds out the last ``test_fraction`` of rows (for time-ordered sources).
    """

    strategy: Literal["stratified", "random", "ordered"]
    test_fraction: Annotated[float, Field(gt=0.0, lt=1.0)]
    random_seed: NonNegativeInt


class CVConfig(_StrictModel):
    """Cross-validation on the training part only; one trial = one full CV = one evaluation."""

    strategy: Literal["stratified_kfold", "kfold"]
    n_splits: Annotated[int, Field(ge=2)]
    random_seed: NonNegativeInt


HPOObjective: TypeAlias = Literal["validation_error", "fit_seconds"]


class HPOProblemConfig(_StrictModel):
    """A hyperparameter-optimization problem built from a catalogued tabular task (ADR 0006)."""

    name: Identifier
    task: Identifier
    variant: Identifier | None = None
    task_type: Literal["classification", "regression"]
    target_metric: Literal["f1_macro", "neg_root_mean_squared_error"]
    objectives: Annotated[list[HPOObjective], Field(min_length=1)]
    model: Literal["hist_gradient_boosting"]
    model_seed: NonNegativeInt
    fixed_parameters: dict[str, ParameterValue] = Field(default_factory=dict)
    search_space: Annotated[dict[str, SearchParameterConfig], Field(min_length=1)]
    split: HPOSplitStudyConfig
    cv: CVConfig

    @model_validator(mode="after")
    def _consistent(self) -> HPOProblemConfig:
        if self.objectives[0] != "validation_error" or len(set(self.objectives)) != len(
            self.objectives
        ):
            raise ValueError("objectives must start with 'validation_error' and be unique")
        expected = (
            "f1_macro" if self.task_type == "classification" else "neg_root_mean_squared_error"
        )
        if self.target_metric != expected:
            raise ValueError(f"{self.task_type} tasks use target_metric {expected!r}")
        if self.task_type == "regression" and (
            self.split.strategy == "stratified" or self.cv.strategy == "stratified_kfold"
        ):
            raise ValueError("stratified split or CV needs a classification task")
        overlap = set(self.fixed_parameters) & set(self.search_space)
        if overlap:
            raise ValueError(f"parameters both fixed and searched: {sorted(overlap)}")
        return self


StudyProblemConfig: TypeAlias = BenchmarkProblemConfig | HPOProblemConfig


class StudyConfig(_StrictModel):
    """A full experiment matrix: problems x algorithms x seeds at one budget and stage."""

    name: Identifier
    stage: StudyStage
    output_dir: Annotated[str, Field(min_length=1)]
    problems: Annotated[list[StudyProblemConfig], Field(min_length=1)]
    algorithms: Annotated[list[StudyAlgorithmConfig], Field(min_length=1)]
    budget: BudgetConfig
    seeds: SeedPolicy
    timeout_seconds: PositiveInt | None = None
    #: Where HPO datasets are cached (``<data_dir>/raw/<task>/``). Machine-specific, so it is not
    #: part of any run's config hash; the dataset checksum is.
    data_dir: Annotated[str, Field(min_length=1)] = "data"

    @property
    def is_hpo(self) -> bool:
        return isinstance(self.problems[0], HPOProblemConfig)

    @field_validator("problems")
    @classmethod
    def _problem_names_unique(cls, problems: list[StudyProblemConfig]) -> list[StudyProblemConfig]:
        names = [p.name for p in problems]
        if len(set(names)) != len(names):
            raise ValueError("study problem names must be unique")
        if len({type(p) for p in problems}) > 1:
            raise ValueError("a study is either all benchmark problems or all HPO problems")
        return problems

    @field_validator("algorithms")
    @classmethod
    def _algorithm_names_unique(
        cls, algorithms: list[StudyAlgorithmConfig]
    ) -> list[StudyAlgorithmConfig]:
        names = [a.name for a in algorithms]
        if len(set(names)) != len(names):
            raise ValueError("study algorithm names must be unique")
        return algorithms


class StudyFile(_StrictModel):
    """Top-level structure of ``configs/studies/*.yaml``."""

    study: StudyConfig


# ---------------------------------------------------------------------------
# configs/analysis_plan.yaml (P9) and configs/reporting.yaml
# ---------------------------------------------------------------------------
class PlanMetric(_StrictModel):
    """A metric column of ``runs.csv`` and the direction in which it is better."""

    name: Identifier
    direction: Literal["minimize", "maximize"]
    primary: bool = False


class PairwiseTestConfig(_StrictModel):
    """Per-problem pairwise comparison across replicates.

    Replicates are paired because every algorithm of a problem runs on the same seeds (common
    random numbers, ADR 0005 D2), so a paired test is justified.
    """

    test: Literal["wilcoxon_signed_rank"]
    zero_method: Literal["wilcox", "pratt", "zsplit"]
    alternative: Literal["two-sided"]
    effect_size: Literal["vargha_delaney_a12"]
    correction: Literal["holm"]
    #: Holm family: every pairwise test of one metric on one problem, or of one metric overall.
    correction_family: Literal["problem_metric", "metric"]


class AcrossProblemsConfig(_StrictModel):
    """Omnibus comparison over problems, using one summary value per (problem, algorithm)."""

    test: Literal["friedman"]
    block_statistic: Literal["median", "mean"]
    posthoc: Literal["wilcoxon_signed_rank_holm"]
    min_problems: Annotated[int, Field(ge=2)]


class ConfidenceIntervalConfig(_StrictModel):
    method: Literal["bootstrap_percentile"]
    statistic: Literal["median", "mean"]
    level: Annotated[float, Field(gt=0.0, lt=1.0)]
    n_resamples: Annotated[int, Field(ge=100)]
    seed: NonNegativeInt


class AnalysisPlanConfig(_StrictModel):
    """The statistical analysis plan. It must be ``frozen`` before final results are analysed.

    ``status: proposal`` plans may analyse pilot and development aggregates only (labelled
    preliminary). Final-stage aggregates require ``status: frozen`` from a committed, clean tree,
    so the test plan cannot be chosen after looking at final results (protocol §9, P9).
    """

    name: Identifier
    status: Literal["proposal", "frozen"]
    alpha: Annotated[float, Field(gt=0.0, lt=1.0)]
    benchmark_metrics: Annotated[list[PlanMetric], Field(min_length=1)]
    hpo_metrics: Annotated[list[PlanMetric], Field(min_length=1)]
    per_problem: PairwiseTestConfig
    across_problems: AcrossProblemsConfig
    confidence_interval: ConfidenceIntervalConfig
    #: Fewer completed replicates than this in a cell makes that cell's tests "not run".
    min_replicates: Annotated[int, Field(ge=2)]
    missing_values: Literal["pairwise_complete"]

    @model_validator(mode="after")
    def _one_primary(self) -> AnalysisPlanConfig:
        for label, metrics in (("benchmark", self.benchmark_metrics), ("hpo", self.hpo_metrics)):
            names = [m.name for m in metrics]
            if len(set(names)) != len(names):
                raise ValueError(f"{label} metric names must be unique")
            if sum(m.primary for m in metrics) != 1:
                raise ValueError(f"exactly one {label} metric must be primary")
        return self


class AnalysisPlanFile(_StrictModel):
    analysis_plan: AnalysisPlanConfig


class ReportingConfig(_StrictModel):
    """How generated tables and figures look. Never changes any number."""

    figure_formats: Annotated[list[Literal["svg", "pdf", "png"]], Field(min_length=1)]
    palette: Literal["okabe_ito"]
    decimals: dict[Identifier, NonNegativeInt] = Field(default_factory=dict)
    default_decimals: NonNegativeInt = 4
    convergence_checkpoints: Annotated[int, Field(ge=2)]


class ReportingFile(_StrictModel):
    reporting: ReportingConfig


AnyConfig: TypeAlias = (
    BenchmarksFile | ExperimentsFile | HPOTasksFile | StudyFile | AnalysisPlanFile | ReportingFile
)


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
