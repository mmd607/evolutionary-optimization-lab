"""Budgeted, validated objective evaluation.

The :class:`Evaluator` is the only component that calls
:meth:`~evooptlab.core.problem.Problem.evaluate_batch`. It owns objective-evaluation accounting,
which is the primary fairness control of the experimental protocol.

Accounting rules
----------------
* One candidate evaluated is one objective evaluation, regardless of the number of objectives.
* A batch that would exceed the remaining budget is **rejected before any evaluation**
  (:class:`~evooptlab.core.errors.BudgetExhaustedError`). The budget can never be exceeded.
* A batch that raises inside the problem, or returns malformed or non-finite output, **still
  counts as spent**, because the evaluations were attempted and cost compute. It is recorded in
  ``n_failed_evaluations`` and surfaces as :class:`~evooptlab.core.errors.ObjectiveError`.
* Invalid candidates (wrong shape, non-finite, out of bounds) are rejected *before* evaluation
  and do not consume budget. They indicate an algorithm bug, not an objective cost.
"""

from __future__ import annotations

import time
from dataclasses import dataclass

import numpy as np
import numpy.typing as npt

from evooptlab.core.errors import BudgetExhaustedError, ObjectiveError
from evooptlab.core.problem import BoolArray, FloatArray, Problem, ProblemSpec


def _freeze(array: FloatArray) -> FloatArray:
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class EvaluationResult:
    """Validated outcome of evaluating one batch. All arrays are read-only."""

    candidates: FloatArray
    objectives: FloatArray
    constraints: FloatArray | None
    constraint_violation: FloatArray
    feasible: BoolArray
    first_evaluation: int
    elapsed_seconds: float

    @property
    def n(self) -> int:
        return int(self.candidates.shape[0])

    @property
    def evaluation_ids(self) -> npt.NDArray[np.int64]:
        """Zero-based global evaluation indices of this batch."""
        return np.arange(self.first_evaluation, self.first_evaluation + self.n, dtype=np.int64)


class Evaluator:
    """Evaluate candidate batches against a problem under a fixed evaluation budget."""

    def __init__(self, problem: Problem, budget: int) -> None:
        if isinstance(budget, bool) or not isinstance(budget, int) or budget <= 0:
            raise ValueError(f"budget must be a positive int, got {budget!r}")
        self._problem = problem
        self._budget = budget
        self._n_evaluations = 0
        self._n_failed = 0
        self._evaluation_seconds = 0.0

    @property
    def spec(self) -> ProblemSpec:
        return self._problem.spec

    @property
    def budget(self) -> int:
        return self._budget

    @property
    def n_evaluations(self) -> int:
        """Objective evaluations consumed so far, including failed ones."""
        return self._n_evaluations

    @property
    def n_failed_evaluations(self) -> int:
        return self._n_failed

    @property
    def remaining(self) -> int:
        return self._budget - self._n_evaluations

    @property
    def exhausted(self) -> bool:
        return self.remaining == 0

    @property
    def evaluation_seconds(self) -> float:
        """Cumulative wall-clock time spent inside the problem (excludes algorithm overhead)."""
        return self._evaluation_seconds

    def evaluate(self, candidates: npt.ArrayLike) -> EvaluationResult:
        """Validate, evaluate, and account for one batch of candidates."""
        spec = self.spec
        x = np.array(spec.validate_candidates(candidates), dtype=np.float64, copy=True)
        n = int(x.shape[0])
        if n > self.remaining:
            raise BudgetExhaustedError(
                f"batch of {n} exceeds remaining budget {self.remaining} "
                f"({self._n_evaluations}/{self._budget} used)"
            )
        x.setflags(write=False)
        first = self._n_evaluations

        start = time.perf_counter()
        try:
            output = self._problem.evaluate_batch(x)
        except Exception as exc:
            self._account(n, time.perf_counter() - start, failed=True)
            raise ObjectiveError(f"{spec.name}: evaluation raised {exc!r}") from exc
        elapsed = time.perf_counter() - start

        try:
            objectives, constraints = self._validate_output(
                spec, n, output.objectives, output.constraints
            )
        except ObjectiveError:
            self._account(n, elapsed, failed=True)
            raise
        self._account(n, elapsed, failed=False)

        if constraints is None:
            violation = np.zeros(n, dtype=np.float64)
        else:
            violation = np.maximum(constraints, 0.0).sum(axis=1)
        feasible = violation <= 0.0
        feasible.setflags(write=False)
        return EvaluationResult(
            candidates=x,
            objectives=_freeze(objectives),
            constraints=None if constraints is None else _freeze(constraints),
            constraint_violation=_freeze(violation),
            feasible=feasible,
            first_evaluation=first,
            elapsed_seconds=elapsed,
        )

    def _account(self, n: int, elapsed: float, *, failed: bool) -> None:
        self._n_evaluations += n
        self._evaluation_seconds += elapsed
        if failed:
            self._n_failed += n

    @staticmethod
    def _validate_output(
        spec: ProblemSpec,
        n: int,
        objectives: npt.ArrayLike,
        constraints: npt.ArrayLike | None,
    ) -> tuple[FloatArray, FloatArray | None]:
        f = np.array(objectives, dtype=np.float64, copy=True)
        if f.shape != (n, spec.n_objectives):
            raise ObjectiveError(
                f"{spec.name}: objectives must have shape ({n}, {spec.n_objectives}), got {f.shape}"
            )
        if not np.all(np.isfinite(f)):
            raise ObjectiveError(f"{spec.name}: objectives contain NaN or infinite values")

        if spec.n_constraints == 0:
            if constraints is not None:
                raise ObjectiveError(f"{spec.name}: returned constraints but declares none")
            return f, None
        if constraints is None:
            raise ObjectiveError(
                f"{spec.name}: declares {spec.n_constraints} constraints but returned none"
            )
        g = np.array(constraints, dtype=np.float64, copy=True)
        if g.shape != (n, spec.n_constraints):
            raise ObjectiveError(
                f"{spec.name}: constraints must have shape "
                f"({n}, {spec.n_constraints}), got {g.shape}"
            )
        if not np.all(np.isfinite(g)):
            raise ObjectiveError(f"{spec.name}: constraints contain NaN or infinite values")
        return f, g
