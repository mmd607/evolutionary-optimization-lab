"""Adapter that runs pymoo 0.6.2 algorithms through EvoOptLab's budgeted ask/tell contract.

How it works
------------
* ``initialize`` builds a **fresh** pymoo algorithm from the explicitly declared hyperparameters.
  pymoo's mutable default operator objects are never shared between runs. The algorithm is set up
  on a *guard problem* with the same dimensions and bounds, whose ``_evaluate`` raises. If pymoo
  ever tried to evaluate an objective outside the ask/tell loop, and so outside the budget, the run
  fails loudly instead of silently consuming hidden evaluations.
* pymoo's own termination is disabled (``NoTermination``). The budget is the only stopping rule,
  and it is enforced by the runner.
* The pymoo seed is drawn from the injected run RNG, so runs are deterministic under a fixed run
  seed and independent of global random state.
* ``ask(max_candidates)`` returns pymoo's next batch. When the remaining budget is smaller than
  that batch (only possible on the **final** batch), the first ``max_candidates`` candidates are
  returned. Their evaluations count and are stored, but this partial generation is not told to
  pymoo, because the run ends with it. A later ``ask`` then raises.
* Bounds: candidates are clipped to the box before evaluation, and pymoo's population is updated
  to the clipped values so that both views agree. ``n_repaired`` counts clipped candidates (it is
  0 for every adapter in the Phase 03 invariant tests).
* Constraints are passed to pymoo as inequality constraints with the same ``g <= 0`` convention.
"""

from __future__ import annotations

import copy
from abc import abstractmethod
from typing import Any

import numpy as np
from pymoo.core.algorithm import Algorithm as PymooAlgorithm
from pymoo.core.evaluator import Evaluator as PymooEvaluator
from pymoo.core.population import Population
from pymoo.core.problem import Problem as PymooProblem
from pymoo.core.termination import NoTermination
from pymoo.problems.static import StaticProblem

from evooptlab.core.algorithm import Algorithm
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import EvaluationResult
from evooptlab.core.problem import FloatArray, ProblemSpec

PYMOO_VERSION = "0.6.2"


class _GuardProblem(PymooProblem):  # type: ignore[misc]
    """pymoo problem with the right shape whose evaluation is forbidden."""

    def __init__(self, spec: ProblemSpec) -> None:
        super().__init__(
            n_var=spec.n_variables,
            n_obj=spec.n_objectives,
            n_ieq_constr=spec.n_constraints,
            xl=np.array(spec.lower_bounds),
            xu=np.array(spec.upper_bounds),
        )

    def _evaluate(self, x: Any, out: Any, *args: Any, **kwargs: Any) -> None:
        raise AlgorithmError(
            "pymoo attempted an objective evaluation outside the ask/tell loop; this would bypass "
            "the evaluation budget"
        )


class PymooAdapter(Algorithm):
    """Base class: subclasses declare ``name``, hyperparameters and ``_build``."""

    def __init__(self, **hyperparameters: Any) -> None:
        unknown = set(hyperparameters) - set(self.default_parameters())
        if unknown:
            raise ValueError(f"{self.name}: unknown hyperparameters {sorted(unknown)}")
        self._params: dict[str, Any] = {**self.default_parameters(), **hyperparameters}
        self._spec: ProblemSpec | None = None
        self._alg: PymooAlgorithm | None = None
        self._pending: Population | None = None
        self._pending_n = 0
        self._finished = False
        self.n_repaired = 0
        self.pymoo_seed: int | None = None

    # ------------------------------------------------------------------ declaration
    @classmethod
    @abstractmethod
    def default_parameters(cls) -> dict[str, Any]:
        """Explicit hyperparameter defaults (JSON-serializable). Tested against pymoo 0.6.2."""

    @abstractmethod
    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        """Construct a fresh pymoo algorithm from ``params``."""

    @classmethod
    def variant(cls) -> str:
        """One-line description of the exact variant, recorded with every run."""
        return cls.__doc__.strip().splitlines()[0] if cls.__doc__ else cls.name

    def parameters(self) -> dict[str, Any]:
        return {
            **self._params,
            "implementation": f"pymoo=={PYMOO_VERSION}",
            "variant": self.variant(),
        }

    # ------------------------------------------------------------------ ask/tell
    def initialize(self, spec: ProblemSpec, rng: np.random.Generator) -> None:
        self._spec = spec
        self.pymoo_seed = int(rng.integers(0, 2**31 - 1))
        self._alg = self._build(dict(self._params))
        self._alg.setup(
            _GuardProblem(spec), termination=NoTermination(), seed=self.pymoo_seed, verbose=False
        )
        self._pending, self._pending_n, self._finished, self.n_repaired = None, 0, False, 0

    def ask(self, max_candidates: int) -> FloatArray:
        if self._alg is None or self._spec is None:
            raise AlgorithmError(f"{self.name}: ask() before initialize()")
        if self._finished:
            raise AlgorithmError(f"{self.name}: the final partial batch was already asked")
        if self._pending is not None:
            raise AlgorithmError(f"{self.name}: ask() called twice without tell()")
        pop = self._alg.ask()
        if pop is None or len(pop) == 0:
            raise AlgorithmError(f"{self.name}: pymoo returned no candidates")
        x = np.asarray(pop.get("X"), dtype=np.float64)
        clipped = np.clip(x, self._spec.lower_bounds, self._spec.upper_bounds)
        repaired = np.any(clipped != x, axis=1)
        if repaired.any():
            self.n_repaired += int(repaired.sum())
            pop.set("X", clipped)
        if clipped.shape[0] > max_candidates:
            self._finished = True
            clipped = clipped[:max_candidates]
        self._pending, self._pending_n = pop, clipped.shape[0]
        return clipped

    def tell(self, result: EvaluationResult) -> None:
        if self._alg is None or self._pending is None:
            raise AlgorithmError(f"{self.name}: tell() without a pending ask()")
        if result.n != self._pending_n:
            raise AlgorithmError(f"{self.name}: tell() does not match the preceding ask()")
        pop, self._pending = self._pending, None
        if self._finished:
            return  # final partial generation: evaluated and recorded, never told to pymoo
        problem = self._alg.problem
        kwargs: dict[str, Any] = {"F": np.array(result.objectives)}
        if result.constraints is not None:
            kwargs["G"] = np.array(result.constraints)
        PymooEvaluator().eval(StaticProblem(problem, **kwargs), pop)
        self._alg.tell(infills=pop)

    # ------------------------------------------------------------------ checkpointing
    def state_dict(self) -> dict[str, Any]:
        if self._alg is None:
            raise AlgorithmError(f"{self.name}: state_dict() before initialize()")
        return copy.deepcopy(
            {
                "algorithm": self._alg,
                "pending": self._pending,
                "pending_n": self._pending_n,
                "finished": self._finished,
                "n_repaired": self.n_repaired,
                "pymoo_seed": self.pymoo_seed,
            }
        )

    def load_state_dict(self, state: dict[str, Any]) -> None:
        state = copy.deepcopy(state)
        self._alg = state["algorithm"]
        self._pending = state["pending"]
        self._pending_n = int(state["pending_n"])
        self._finished = bool(state["finished"])
        self.n_repaired = int(state["n_repaired"])
        self.pymoo_seed = state["pymoo_seed"]
