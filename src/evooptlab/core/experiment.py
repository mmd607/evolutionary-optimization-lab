"""Experiment runner: execute one (problem, algorithm, seed, budget) run and persist artifacts.

For every run the runner:

1. derives the run ID and creates a fresh run directory (an existing run is never overwritten);
2. writes ``config.yaml`` (problem spec, algorithm parameters, seed, budget, stage, extra config)
   and ``run_metadata.json`` with ``outcome: running``;
3. seeds the algorithm from a named stream of the run seed, never from global random state;
4. runs ask -> evaluate -> tell until the evaluation budget is used or the timeout is reached;
5. writes ``history.csv`` (every evaluation, full float precision) and ``metrics.json``
   (accounting and timing; quality metrics arrive in Phase 02);
6. records the finish as ``completed`` or ``failed`` with a reason. Failed runs are kept.

Algorithms, problems, and the runner never read datasets or touch dashboards (architecture.md).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import logging
import time
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import yaml

from evooptlab.core.algorithm import Algorithm
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import EvaluationResult, Evaluator
from evooptlab.core.problem import Problem
from evooptlab.core.seeding import MAX_SEED, derive_seed, make_rng
from evooptlab.storage.layout import ArtifactLayout, make_run_id
from evooptlab.storage.metadata import HardwareInfo, RunMetadata, RunStage, SoftwareInfo
from evooptlab.utils.environment import EnvironmentInfo, capture_environment
from evooptlab.utils.logging import JsonFormatter, get_logger

log = get_logger(__name__)

#: Name of the seed stream used for the algorithm's RNG (see ``derive_seed``).
ALGORITHM_STREAM = "algorithm"


@dataclass(frozen=True)
class RunSpec:
    """What to run. The problem and algorithm objects are passed separately."""

    stage: RunStage
    seed: int
    budget: int
    timeout_seconds: float | None = None
    extra_config: Mapping[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.stage not in ("pilot", "development", "final"):
            raise ValueError(f"unknown stage {self.stage!r}")
        if isinstance(self.seed, bool) or not 0 <= self.seed <= MAX_SEED:
            raise ValueError("seed must be an int in [0, 2**63 - 1]")
        if isinstance(self.budget, bool) or self.budget <= 0:
            raise ValueError("budget must be a positive int")
        if self.timeout_seconds is not None and self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")


@dataclass(frozen=True)
class RunResult:
    run_id: str
    run_dir: Path
    metadata: RunMetadata
    n_evaluations: int

    @property
    def outcome(self) -> Literal["running", "completed", "failed"]:
        return self.metadata.outcome


def canonical_hash(document: Mapping[str, Any]) -> str:
    """SHA-256 of a config document as canonical JSON; stored as ``config_hash`` in metadata."""
    text = json.dumps(document, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _history_csv(results: list[EvaluationResult], n_var: int, n_obj: int, n_con: int) -> str:
    header = (
        ["evaluation_id", "batch"]
        + [f"x_{i}" for i in range(n_var)]
        + [f"f_{j}" for j in range(n_obj)]
        + [f"g_{k}" for k in range(n_con)]
        + ["constraint_violation", "feasible"]
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(header)
    for batch, r in enumerate(results):
        g = r.constraints if r.constraints is not None else np.empty((r.n, 0))
        for i in range(r.n):
            # repr() of a Python float round-trips exactly, so no precision is lost.
            writer.writerow(
                [int(r.first_evaluation + i), batch]
                + [repr(float(v)) for v in r.candidates[i]]
                + [repr(float(v)) for v in r.objectives[i]]
                + [repr(float(v)) for v in g[i]]
                + [repr(float(r.constraint_violation[i])), bool(r.feasible[i])]
            )
    return buffer.getvalue()


class ExperimentRunner:
    """Run single optimization runs and persist immutable artifacts."""

    def __init__(
        self,
        layout: ArtifactLayout,
        *,
        repo_root: Path | None = None,
        lock_file: Path | None = None,
    ) -> None:
        self.layout = layout
        self.repo_root = repo_root
        self.lock_file = lock_file

    def run(self, problem: Problem, algorithm: Algorithm, spec: RunSpec) -> RunResult:
        """Execute one run. Failures are recorded in the artifacts and returned, not raised."""
        if not algorithm.supports(problem.spec):
            raise AlgorithmError(
                f"{algorithm.name} does not support {problem.spec.n_objectives}-objective "
                f"problems (supported: {algorithm.supported_n_objectives})"
            )
        env = capture_environment(self.repo_root, self.lock_file)
        started = datetime.now(UTC)
        run_id = make_run_id(problem.name, algorithm.name, spec.budget, spec.seed, when=started)
        self.layout.create_run_dir(spec.stage, run_id)

        config = self.config_document(problem, algorithm, spec)
        self.layout.write_run_text(
            spec.stage, run_id, "config", yaml.safe_dump(config, sort_keys=True)
        )
        metadata = self._initial_metadata(run_id, problem, algorithm, spec, env, started, config)
        self.layout.write_metadata(metadata)

        handler = logging.FileHandler(
            self.layout.run_file(spec.stage, run_id, "log"), mode="x", encoding="utf-8"
        )
        handler.setFormatter(JsonFormatter())
        handler.setLevel(logging.INFO)
        # Capture INFO+ in the run log without changing what console handlers emit: console
        # handlers installed by configure_logging carry their own level.
        package_logger = logging.getLogger("evooptlab")
        previous_level = package_logger.level
        if package_logger.getEffectiveLevel() > logging.INFO:
            package_logger.setLevel(logging.INFO)
        package_logger.addHandler(handler)
        try:
            return self._execute(problem, algorithm, spec, run_id, metadata)
        finally:
            package_logger.removeHandler(handler)
            handler.close()
            package_logger.setLevel(previous_level)

    # ------------------------------------------------------------------ internals
    def _execute(
        self,
        problem: Problem,
        algorithm: Algorithm,
        spec: RunSpec,
        run_id: str,
        metadata: RunMetadata,
    ) -> RunResult:
        evaluator = Evaluator(problem, spec.budget)
        history: list[EvaluationResult] = []
        failure: str | None = None
        interrupted: BaseException | None = None
        wall_start = time.perf_counter()
        ctx = {"run_id": run_id, "seed": spec.seed, "budget": spec.budget}
        log.info("run started", extra=ctx)
        try:
            algorithm.initialize(problem.spec, make_rng(derive_seed(spec.seed, ALGORITHM_STREAM)))
            while not evaluator.exhausted:
                elapsed = time.perf_counter() - wall_start
                if spec.timeout_seconds is not None and elapsed >= spec.timeout_seconds:
                    failure = (
                        f"timeout after {elapsed:.3f}s with "
                        f"{evaluator.n_evaluations}/{spec.budget} evaluations"
                    )
                    break
                candidates = np.asarray(algorithm.ask(evaluator.remaining))
                n_asked = candidates.shape[0] if candidates.ndim >= 1 else 0
                if not 1 <= n_asked <= evaluator.remaining:
                    raise AlgorithmError(
                        f"{algorithm.name}.ask({evaluator.remaining}) returned {n_asked} "
                        "candidates; expected between 1 and max_candidates"
                    )
                result = evaluator.evaluate(candidates)
                history.append(result)
                algorithm.tell(result)
        except Exception as exc:
            failure = f"{type(exc).__name__}: {exc}"
            log.exception("run failed", extra=ctx)
        except BaseException as exc:  # KeyboardInterrupt / SystemExit: record, then re-raise
            failure = f"interrupted: {type(exc).__name__}"
            interrupted = exc
        wall = time.perf_counter() - wall_start

        p = problem.spec
        self.layout.write_run_text(
            spec.stage,
            run_id,
            "history",
            _history_csv(history, p.n_variables, p.n_objectives, p.n_constraints),
        )
        metrics = {
            "budget": spec.budget,
            "n_evaluations": evaluator.n_evaluations,
            "n_failed_evaluations": evaluator.n_failed_evaluations,
            "n_batches": len(history),
            "n_feasible": int(sum(int(r.feasible.sum()) for r in history)),
            "wall_clock_seconds": wall,
            "evaluation_seconds": evaluator.evaluation_seconds,
            "overhead_seconds": max(wall - evaluator.evaluation_seconds, 0.0),
        }
        self.layout.write_run_text(
            spec.stage, run_id, "metrics", json.dumps(metrics, indent=2, sort_keys=True) + "\n"
        )

        finished = metadata.finished(
            datetime.now(UTC),
            "failed" if failure else "completed",
            failure,
        )
        self.layout.record_finish(finished)
        log.info(
            "run finished",
            extra={**ctx, "outcome": finished.outcome, "n_evaluations": evaluator.n_evaluations},
        )
        if interrupted is not None:
            raise interrupted
        return RunResult(
            run_id=run_id,
            run_dir=self.layout.run_dir(spec.stage, run_id),
            metadata=finished,
            n_evaluations=evaluator.n_evaluations,
        )

    @staticmethod
    def config_document(problem: Problem, algorithm: Algorithm, spec: RunSpec) -> dict[str, Any]:
        """The ``config.yaml`` document of a run; its :func:`canonical_hash` identifies the run.

        Two runs with the same document are replicates of the same planned cell, which is what
        study resume uses to decide whether a cell has already been run.
        """
        p = problem.spec
        problem_document: dict[str, Any] = {
            "name": p.name,
            "n_variables": p.n_variables,
            "n_objectives": p.n_objectives,
            "n_constraints": p.n_constraints,
            "lower_bounds": p.lower_bounds.tolist(),
            "upper_bounds": p.upper_bounds.tolist(),
        }
        details = problem.describe()
        if details:
            problem_document["details"] = details
        return {
            "stage": spec.stage,
            "seed": spec.seed,
            "seed_streams": {ALGORITHM_STREAM: derive_seed(spec.seed, ALGORITHM_STREAM)},
            "budget": {"unit": "objective_evaluations", "max_evaluations": spec.budget},
            "timeout_seconds": spec.timeout_seconds,
            "problem": problem_document,
            "algorithm": {"name": algorithm.name, "parameters": algorithm.parameters()},
            "extra": dict(spec.extra_config),
        }

    @staticmethod
    def _initial_metadata(
        run_id: str,
        problem: Problem,
        algorithm: Algorithm,
        spec: RunSpec,
        env: EnvironmentInfo,
        started: datetime,
        config: Mapping[str, Any],
    ) -> RunMetadata:
        return RunMetadata(
            run_id=run_id,
            git_commit=env.git.commit,
            git_dirty=env.git.dirty,
            algorithm=algorithm.name,
            problem=problem.name,
            seed=spec.seed,
            objective_evaluation_budget=spec.budget,
            started_at_utc=started,
            hardware=HardwareInfo(cpu=env.processor),
            software=SoftwareInfo(
                python=env.python_version,
                packages_lock_hash=env.packages_lock_hash,
                packages=env.packages,
            ),
            config_path="config.yaml",
            config_hash=canonical_hash(config),
            status=spec.stage,
        )
