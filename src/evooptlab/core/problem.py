"""Optimization problem interface.

Conventions (apply to every problem in EvoOptLab)
-------------------------------------------------
* Decision vectors are real-valued and box-bounded: ``lower_bounds <= x <= upper_bounds``.
* **All objectives are minimized.** A quantity to maximize, such as macro-F1, is exposed as its
  negation or as ``1 - score``. The problem documents which one it uses.
* **Inequality constraints use ``g(x) <= 0`` for feasibility** (the pymoo convention). The
  constraint violation of a candidate is ``sum(max(0, g_j(x)))``.
* Evaluation is **batched**: a problem receives an ``(n, n_variables)`` array and returns
  ``(n, n_objectives)`` objectives and ``(n, n_constraints)`` constraints.

Algorithms never receive a :class:`Problem`. They receive its immutable :class:`ProblemSpec`
(dimensions and bounds only), so every objective evaluation has to go through the budgeted
:class:`~evooptlab.core.evaluator.Evaluator`.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import numpy.typing as npt

from evooptlab.core.errors import CandidateError, ProblemDefinitionError

FloatArray = npt.NDArray[np.float64]
BoolArray = npt.NDArray[np.bool_]

_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.\-]*(?:_[A-Za-z0-9.\-]+)*$")


def _readonly(values: npt.ArrayLike, label: str) -> FloatArray:
    array = np.array(values, dtype=np.float64, copy=True)
    if array.ndim != 1 or array.size == 0:
        raise ProblemDefinitionError(f"{label} must be a non-empty 1-D array")
    if not np.all(np.isfinite(array)):
        raise ProblemDefinitionError(f"{label} must be finite")
    array.setflags(write=False)
    return array


@dataclass(frozen=True)
class ProblemSpec:
    """Immutable description of a problem's search space and output dimensions."""

    name: str
    lower_bounds: FloatArray
    upper_bounds: FloatArray
    n_objectives: int
    n_constraints: int = 0
    metadata: dict[str, Any] = field(default_factory=dict, compare=False)

    def __post_init__(self) -> None:
        if not _NAME.match(self.name) or "__" in self.name:
            raise ProblemDefinitionError(
                f"problem name {self.name!r} must be alphanumeric with single '_', '-' or '.'"
            )
        lower = _readonly(self.lower_bounds, "lower_bounds")
        upper = _readonly(self.upper_bounds, "upper_bounds")
        if lower.shape != upper.shape:
            raise ProblemDefinitionError("lower_bounds and upper_bounds must have the same shape")
        if np.any(lower >= upper):
            raise ProblemDefinitionError("every lower bound must be strictly below its upper bound")
        if self.n_objectives < 1:
            raise ProblemDefinitionError("n_objectives must be >= 1")
        if self.n_constraints < 0:
            raise ProblemDefinitionError("n_constraints must be >= 0")
        object.__setattr__(self, "lower_bounds", lower)
        object.__setattr__(self, "upper_bounds", upper)

    @property
    def n_variables(self) -> int:
        return int(self.lower_bounds.shape[0])

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, ProblemSpec):
            return NotImplemented
        return (
            self.name == other.name
            and self.n_objectives == other.n_objectives
            and self.n_constraints == other.n_constraints
            and np.array_equal(self.lower_bounds, other.lower_bounds)
            and np.array_equal(self.upper_bounds, other.upper_bounds)
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.name,
                self.n_objectives,
                self.n_constraints,
                self.lower_bounds.tobytes(),
                self.upper_bounds.tobytes(),
            )
        )

    def validate_candidates(self, candidates: npt.ArrayLike) -> FloatArray:
        """Return ``candidates`` as a float64 ``(n, n_variables)`` array, or raise.

        Raises:
            CandidateError: wrong shape, non-finite values, or values outside the bounds.
        """
        x = np.asarray(candidates, dtype=np.float64)
        if x.ndim != 2 or x.shape[1] != self.n_variables:
            raise CandidateError(
                f"{self.name}: candidates must have shape (n, {self.n_variables}), got {x.shape}"
            )
        if x.shape[0] == 0:
            raise CandidateError(f"{self.name}: candidate batch is empty")
        if not np.all(np.isfinite(x)):
            raise CandidateError(f"{self.name}: candidates contain NaN or infinite values")
        outside = (x < self.lower_bounds) | (x > self.upper_bounds)
        if np.any(outside):
            rows = np.unique(np.nonzero(outside)[0])
            raise CandidateError(
                f"{self.name}: {rows.size} candidate(s) outside bounds (rows {rows[:5].tolist()}"
                f"{'...' if rows.size > 5 else ''}); algorithms must repair candidates before "
                "asking for evaluation"
            )
        return x


@dataclass(frozen=True)
class ProblemOutput:
    """Raw output of :meth:`Problem.evaluate_batch`."""

    objectives: FloatArray
    constraints: FloatArray | None = None


class Problem(ABC):
    """Base class for black-box optimization problems."""

    def __init__(self, spec: ProblemSpec) -> None:
        self._spec = spec

    @property
    def spec(self) -> ProblemSpec:
        return self._spec

    @property
    def name(self) -> str:
        return self._spec.name

    def describe(self) -> dict[str, Any]:
        """Definition details beyond the spec that change the objective function.

        Returned values are JSON-serializable and become ``problem.details`` in a run's
        ``config.yaml``, so they are part of the run's config hash. Data-backed problems (HPO
        tasks) list their dataset checksum, split, CV, model and search space here. Analytic
        benchmarks are fully defined by name and dimensions and return ``{}``; the key is then
        omitted, which keeps their config hashes unchanged.
        """
        return {}

    @abstractmethod
    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        """Evaluate a validated ``(n, n_variables)`` batch.

        Only :class:`~evooptlab.core.evaluator.Evaluator` should call this method. The
        evaluator validates shapes, bounds, and finiteness and counts the budget. Implementations
        must not modify ``candidates``.
        """
