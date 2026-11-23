"""Test-only algorithms that exercise the ask/tell contract.

These are deliberately minimal and live under ``tests/``. They are not baselines; the real
algorithms are implemented in Phase 03.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

import numpy as np

from evooptlab.core.algorithm import Algorithm
from evooptlab.core.evaluator import EvaluationResult
from evooptlab.core.problem import FloatArray, ProblemSpec


class UniformSampler(Algorithm):
    """Samples uniformly in the box and keeps simple bookkeeping for assertions."""

    name: ClassVar[str] = "uniform_sampler"

    def __init__(self, batch_size: int = 7) -> None:
        self.batch_size = batch_size
        self._spec: ProblemSpec | None = None
        self._rng: np.random.Generator | None = None
        self.n_told = 0
        self.n_asks = 0
        self._pending: int | None = None

    def parameters(self) -> dict[str, Any]:
        return {"batch_size": self.batch_size}

    def initialize(self, spec: ProblemSpec, rng: np.random.Generator) -> None:
        self._spec, self._rng = spec, rng
        self.n_told = self.n_asks = 0
        self._pending = None

    def ask(self, max_candidates: int) -> FloatArray:
        assert self._spec is not None and self._rng is not None
        assert self._pending is None, "ask called twice without tell"
        n = min(self.batch_size, max_candidates)
        self._pending = n
        self.n_asks += 1
        return self._rng.uniform(
            self._spec.lower_bounds, self._spec.upper_bounds, (n, self._spec.n_variables)
        )

    def tell(self, result: EvaluationResult) -> None:
        assert self._pending == result.n, "tell does not match the preceding ask"
        self._pending = None
        self.n_told += result.n

    def state_dict(self) -> dict[str, Any]:
        assert self._rng is not None
        return {
            "rng": copy.deepcopy(self._rng.bit_generator.state),
            "n_told": self.n_told,
            "n_asks": self.n_asks,
        }

    def load_state_dict(self, state: dict[str, Any]) -> None:
        assert self._rng is not None
        self._rng.bit_generator.state = copy.deepcopy(state["rng"])
        self.n_told = int(state["n_told"])
        self.n_asks = int(state["n_asks"])


class Misbehaving(UniformSampler):
    """Violates the contract in a configurable way."""

    name: ClassVar[str] = "misbehaving"

    def __init__(self, mode: str) -> None:
        super().__init__(batch_size=5)
        self.mode = mode

    def ask(self, max_candidates: int) -> FloatArray:
        x = super().ask(max_candidates)
        assert self._spec is not None
        if self.mode == "empty":
            return x[:0]
        if self.mode == "too_many":
            return np.resize(x, (max_candidates + 1, x.shape[1]))
        if self.mode == "out_of_bounds":
            return x + (self._spec.upper_bounds - self._spec.lower_bounds) * 2
        if self.mode == "crash":
            raise RuntimeError("algorithm crashed")
        return x


class SingleObjectiveOnly(UniformSampler):
    name: ClassVar[str] = "single_objective_only"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = (1,)
