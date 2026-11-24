"""pymoo-backed baselines with explicit, recorded hyperparameters.

Every default below equals the pymoo 0.6.2 constructor default
(``tests/algorithm_invariants/test_defaults_match_pymoo.py`` enforces this), so the values are
library defaults. They are not tuned. Tuning, if any, follows the protocol in ADR 0004.

Domains
-------
* Single-objective (M = 1): ``ga``, ``de``, ``pso``
* Multi-objective (M >= 2): ``nsga2``, ``gde3``, ``cmopso``
"""

from __future__ import annotations

from typing import Any, ClassVar

from pymoo.algorithms.moo.cmopso import CMOPSO as _CMOPSO
from pymoo.algorithms.moo.gde3 import GDE3 as _GDE3
from pymoo.algorithms.moo.nsga2 import NSGA2 as _NSGA2
from pymoo.algorithms.soo.nonconvex.de import DE as _DE
from pymoo.algorithms.soo.nonconvex.ga import GA as _GA
from pymoo.algorithms.soo.nonconvex.pso import PSO as _PSO
from pymoo.core.algorithm import Algorithm as PymooAlgorithm
from pymoo.operators.crossover.sbx import SBX
from pymoo.operators.mutation.pm import PM

from evooptlab.algorithms.pymoo_adapter import PymooAdapter

_SO: tuple[int, ...] = (1,)
_MO: tuple[int, ...] = tuple(range(2, 16))

_SBX_PM_DEFAULTS: dict[str, Any] = {
    "crossover": "SBX",
    "crossover_prob": 0.9,
    "crossover_eta": 15.0,
    "crossover_prob_var": 0.5,
    "mutation": "PM",
    "mutation_eta": 20.0,
    "mutation_prob": 0.9,
    "mutation_prob_var": None,  # None -> pymoo uses min(0.5, 1 / n_variables)
}


def _sbx_pm(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "crossover": SBX(
            prob=params["crossover_prob"],
            eta=params["crossover_eta"],
            prob_var=params["crossover_prob_var"],
        ),
        "mutation": PM(
            prob=params["mutation_prob"],
            eta=params["mutation_eta"],
            prob_var=params["mutation_prob_var"],
        ),
    }


class GA(PymooAdapter):
    """Generational GA: SBX + polynomial mutation, binary tournament, fitness survival (M = 1)."""

    name: ClassVar[str] = "ga"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _SO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return {"pop_size": 100, "eliminate_duplicates": True, **_SBX_PM_DEFAULTS}

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _GA(
            pop_size=params["pop_size"],
            eliminate_duplicates=params["eliminate_duplicates"],
            **_sbx_pm(params),
        )


class NSGA2(PymooAdapter):
    """NSGA-II: SBX + polynomial mutation, rank-and-crowding survival (M >= 2)."""

    name: ClassVar[str] = "nsga2"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _MO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return {"pop_size": 100, **_SBX_PM_DEFAULTS}

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _NSGA2(pop_size=params["pop_size"], **_sbx_pm(params))


class DE(PymooAdapter):
    """Differential Evolution DE/best/1/bin, pymoo defaults for CR and F (M = 1)."""

    name: ClassVar[str] = "de"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _SO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return {"pop_size": 100, "variant": "DE/best/1/bin"}

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _DE(pop_size=params["pop_size"], variant=params["variant"])


class GDE3(PymooAdapter):
    """GDE3 (Kukkonen & Lampinen, 2005): DE/rand/1/bin with dominance-based selection (M >= 2)."""

    name: ClassVar[str] = "gde3"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _MO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        # F = None: pymoo draws the scale factor at random from (0, 1) (dither).
        return {"pop_size": 100, "variant": "DE/rand/1/bin", "CR": 0.5, "F": None, "gamma": 1e-4}

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _GDE3(
            pop_size=params["pop_size"],
            variant=params["variant"],
            CR=params["CR"],
            F=params["F"],
            gamma=params["gamma"],
        )


class PSO(PymooAdapter):
    """Particle Swarm Optimization with pymoo's adaptive inertia and LHS initialization (M = 1)."""

    name: ClassVar[str] = "pso"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _SO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return {
            "pop_size": 25,
            "w": 0.9,
            "c1": 2.0,
            "c2": 2.0,
            "adaptive": True,
            "initial_velocity": "random",
            "max_velocity_rate": 0.2,
            "pertube_best": True,
        }

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _PSO(**params)


class CMOPSO(PymooAdapter):
    """CMOPSO: competitive-mechanism multi-objective PSO with to-bound repair (M >= 2)."""

    name: ClassVar[str] = "cmopso"
    supported_n_objectives: ClassVar[tuple[int, ...] | None] = _MO

    @classmethod
    def default_parameters(cls) -> dict[str, Any]:
        return {
            "pop_size": 100,
            "max_velocity_rate": 0.2,
            "elite_size": 10,
            "initial_velocity": "random",
            "mutation_rate": 0.5,
        }

    def _build(self, params: dict[str, Any]) -> PymooAlgorithm:
        return _CMOPSO(**params)
