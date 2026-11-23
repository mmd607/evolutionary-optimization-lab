"""Ask/tell optimization algorithm interface.

Lifecycle::

    algorithm = SomeAlgorithm(**parameters)       # configuration goes in through the constructor
    algorithm.initialize(spec, rng)               # once per run
    while budget remains:
        x = algorithm.ask(max_candidates)         # 1 <= len(x) <= max_candidates
        result = evaluator.evaluate(x)            # the runner evaluates; the algorithm never does
        algorithm.tell(result)

Contract
--------
* ``initialize`` receives only the immutable :class:`~evooptlab.core.problem.ProblemSpec`, never
  the problem itself, so an algorithm cannot evaluate objectives outside the budget.
* ``ask(max_candidates)`` returns between 1 and ``max_candidates`` in-bounds candidates.
  ``max_candidates`` is the remaining evaluation budget. An algorithm with a fixed population
  must handle a final partial batch itself (the runner never truncates silently).
* ``tell`` receives the evaluated batch, in the same order as the preceding ``ask``.
* All randomness must come from the ``rng`` passed to ``initialize``.
* ``state_dict`` / ``load_state_dict`` capture the full internal state, including RNG state, so
  a run can be checkpointed and resumed deterministically.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, ClassVar

import numpy as np

from evooptlab.core.evaluator import EvaluationResult
from evooptlab.core.problem import FloatArray, ProblemSpec


class Algorithm(ABC):
    """Base class for ask/tell optimizers."""

    #: Short identifier used in run IDs and result tables, e.g. ``"nsga2"``.
    name: ClassVar[str]

    #: Objective counts the algorithm is valid for; ``None`` means any count.
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = None

    def supports(self, spec: ProblemSpec) -> bool:
        """Whether the algorithm is valid for ``spec`` (no out-of-setting comparisons)."""
        allowed = self.supported_n_objectives
        return allowed is None or spec.n_objectives in allowed

    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """Algorithm hyperparameters, recorded in every run's config (JSON-serializable)."""

    @abstractmethod
    def initialize(self, spec: ProblemSpec, rng: np.random.Generator) -> None:
        """Prepare a fresh run on ``spec``. Must reset any state from previous runs."""

    @abstractmethod
    def ask(self, max_candidates: int) -> FloatArray:
        """Propose between 1 and ``max_candidates`` candidates as an ``(n, n_variables)`` array."""

    @abstractmethod
    def tell(self, result: EvaluationResult) -> None:
        """Receive the evaluation of the most recently asked batch."""

    @abstractmethod
    def state_dict(self) -> dict[str, Any]:
        """Return a snapshot of the complete internal state (including RNG state)."""

    @abstractmethod
    def load_state_dict(self, state: dict[str, Any]) -> None:
        """Restore a snapshot produced by :meth:`state_dict`."""
