"""Optuna's Tree-structured Parzen Estimator (TPE): the model-based baseline.

Variant
    ``optuna.samplers.TPESampler`` driven through Optuna's own ask/tell API, one candidate per
    ``ask`` (sequential model-based optimization, so no parallel-batch approximation is
    involved). It works with any number of objectives: with M >= 2 Optuna uses its
    multi-objective TPE.
Search space
    Every decision variable becomes a ``FloatDistribution(lower, upper)`` over the problem's box.
    HPO problems expose the same unit cube to every algorithm (ADR 0006), so TPE searches the
    identical space as the evolutionary baselines and random search.
Constraints
    Each ``g_k`` is passed with ``Trial.set_constraint``; Optuna treats a trial as feasible when
    every value is ``<= 0``, which is the EvoOptLab convention.
Settings
    The arguments below are passed explicitly and recorded. Defaults equal Optuna 5.1's own.
    The remaining TPE settings (prior weight, magic clip, endpoints, gamma, weights) are
    deprecated as constructor arguments in Optuna 5.x and stay at the library defaults of the
    recorded ``implementation`` version.
Randomness
    The sampler seed is drawn once from the run's algorithm RNG, so runs are reproducible and
    independent of global random state.
"""

from __future__ import annotations

import copy
from typing import Any, ClassVar

import numpy as np
import optuna
from optuna.distributions import BaseDistribution, FloatDistribution
from optuna.trial import Trial

from evooptlab.core.algorithm import Algorithm
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import EvaluationResult
from evooptlab.core.problem import FloatArray, ProblemSpec


class OptunaTPE(Algorithm):
    name: ClassVar[str] = "optuna_tpe"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = None

    def __init__(
        self,
        n_startup_trials: int = 10,
        n_ei_candidates: int = 24,
        multivariate: bool = True,
    ) -> None:
        if n_startup_trials < 0:
            raise ValueError("n_startup_trials must be >= 0")
        if n_ei_candidates < 1:
            raise ValueError("n_ei_candidates must be >= 1")
        self.n_startup_trials = n_startup_trials
        self.n_ei_candidates = n_ei_candidates
        self.multivariate = multivariate
        self._study: optuna.Study | None = None
        self._spec: ProblemSpec | None = None
        self._distributions: dict[str, BaseDistribution] = {}
        self._pending: Trial | None = None
        self.sampler_seed: int | None = None

    def parameters(self) -> dict[str, Any]:
        return {
            "implementation": f"optuna=={optuna.__version__}",
            "variant": "TPESampler, sequential ask/tell (one candidate per ask)",
            "n_startup_trials": self.n_startup_trials,
            "n_ei_candidates": self.n_ei_candidates,
            "multivariate": self.multivariate,
            "group": False,
            "constant_liar": True,
            "search_space": "FloatDistribution(lower, upper) per variable",
            "constraints": "Trial.set_constraint, feasible iff every g <= 0",
        }

    def initialize(self, spec: ProblemSpec, rng: np.random.Generator) -> None:
        optuna.logging.set_verbosity(optuna.logging.WARNING)
        self.sampler_seed = int(rng.integers(0, 2**32))
        sampler = optuna.samplers.TPESampler(
            seed=self.sampler_seed,
            n_startup_trials=self.n_startup_trials,
            n_ei_candidates=self.n_ei_candidates,
            multivariate=self.multivariate,
            group=False,
            constant_liar=True,
        )
        self._spec = spec
        self._study = optuna.create_study(
            directions=["minimize"] * spec.n_objectives, sampler=sampler
        )
        self._distributions = {
            f"x_{i}": FloatDistribution(float(lo), float(hi))
            for i, (lo, hi) in enumerate(zip(spec.lower_bounds, spec.upper_bounds, strict=True))
        }
        self._pending = None

    def ask(self, max_candidates: int) -> FloatArray:
        if self._study is None:
            raise AlgorithmError(f"{self.name}: ask() before initialize()")
        if self._pending is not None:
            raise AlgorithmError(f"{self.name}: ask() called twice without tell()")
        if max_candidates < 1:
            raise AlgorithmError(f"{self.name}: max_candidates must be >= 1")
        trial = self._study.ask(self._distributions)
        self._pending = trial
        x = np.array([[trial.params[name] for name in self._distributions]], dtype=np.float64)
        return x

    def tell(self, result: EvaluationResult) -> None:
        if self._study is None or self._spec is None:
            raise AlgorithmError(f"{self.name}: tell() before initialize()")
        trial, self._pending = self._pending, None
        if trial is None:
            raise AlgorithmError(f"{self.name}: tell() without a pending ask()")
        if result.n != 1:
            raise AlgorithmError(f"{self.name}: tell() received {result.n} results, expected 1")
        if result.constraints is not None:
            for k, value in enumerate(result.constraints[0]):
                trial.set_constraint(f"g_{k}", float(value))
        values = [float(v) for v in result.objectives[0]]
        self._study.tell(trial, values if len(values) > 1 else values[0])

    def state_dict(self) -> dict[str, Any]:
        if self._study is None:
            raise AlgorithmError(f"{self.name}: state_dict() before initialize()")
        # One deepcopy keeps the pending trial bound to the copied study.
        return copy.deepcopy(
            {
                "study": self._study,
                "pending": self._pending,
                "spec": self._spec,
                "distributions": self._distributions,
                "sampler_seed": self.sampler_seed,
            }
        )

    def load_state_dict(self, state: dict[str, Any]) -> None:
        state = copy.deepcopy(state)
        self._study = state["study"]
        self._pending = state["pending"]
        self._spec = state["spec"]
        self._distributions = state["distributions"]
        self.sampler_seed = state["sampler_seed"]
