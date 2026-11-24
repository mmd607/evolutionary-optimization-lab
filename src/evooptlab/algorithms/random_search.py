"""Uniform random search: the reference baseline.

Variant
    Independent uniform sampling in the box ``[lower_bounds, upper_bounds]``, in batches of
    ``batch_size``. There is no adaptation, so it is valid for any number of objectives and
    constraints. Constraints are recorded but never used to guide sampling.
Bounds handling
    Samples are drawn inside the box, so no repair is needed.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

import numpy as np

from evooptlab.core.algorithm import Algorithm
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import EvaluationResult
from evooptlab.core.problem import FloatArray, ProblemSpec


class RandomSearch(Algorithm):
    name: ClassVar[str] = "random_search"

    def __init__(self, batch_size: int = 100) -> None:
        if batch_size < 1:
            raise ValueError("batch_size must be >= 1")
        self.batch_size = batch_size
        self._spec: ProblemSpec | None = None
        self._rng: np.random.Generator | None = None
        self._pending = 0

    def parameters(self) -> dict[str, Any]:
        return {"batch_size": self.batch_size, "sampling": "uniform"}

    def initialize(self, spec: ProblemSpec, rng: np.random.Generator) -> None:
        self._spec, self._rng, self._pending = spec, rng, 0

    def ask(self, max_candidates: int) -> FloatArray:
        if self._spec is None or self._rng is None:
            raise AlgorithmError("random_search: ask() before initialize()")
        n = min(self.batch_size, max_candidates)
        self._pending = n
        return self._rng.uniform(
            self._spec.lower_bounds, self._spec.upper_bounds, size=(n, self._spec.n_variables)
        )

    def tell(self, result: EvaluationResult) -> None:
        if result.n != self._pending:
            raise AlgorithmError("random_search: tell() does not match the preceding ask()")
        self._pending = 0

    def state_dict(self) -> dict[str, Any]:
        if self._rng is None:
            raise AlgorithmError("random_search: state_dict() before initialize()")
        return {"rng": copy.deepcopy(self._rng.bit_generator.state), "pending": self._pending}

    def load_state_dict(self, state: dict[str, Any]) -> None:
        if self._rng is None:
            raise AlgorithmError("random_search: load_state_dict() before initialize()")
        self._rng.bit_generator.state = copy.deepcopy(state["rng"])
        self._pending = int(state["pending"])
