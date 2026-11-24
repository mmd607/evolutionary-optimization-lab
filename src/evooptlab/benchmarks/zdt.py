"""ZDT bi-objective benchmark problems (ZDT1, ZDT2, ZDT3).

Source: E. Zitzler, K. Deb, L. Thiele, "Comparison of Multiobjective Evolutionary Algorithms:
Empirical Results", *Evolutionary Computation* 8(2), 2000. Bibliographic details must be verified
in the literature matrix before they are cited (``docs/literature/``).

All three problems: ``x in [0, 1]^n``, two objectives (minimized), no constraints.

* ``f1 = x_1``
* ``g = 1 + 9 / (n - 1) * sum_{i=2..n} x_i``
* ``f2 = g * h(f1, g)``, where
  * ZDT1: ``h = 1 - sqrt(f1 / g)`` (convex front)
  * ZDT2: ``h = 1 - (f1 / g)^2`` (concave front)
  * ZDT3: ``h = 1 - sqrt(f1 / g) - (f1 / g) sin(10 pi f1)`` (disconnected front)

The Pareto-optimal set is ``x_2..x_n = 0`` (``g = 1``). Reference fronts are computed from that
analytical set: for ZDT3, the curve is sampled densely and its non-dominated subset is kept, so no
hard-coded region boundaries are needed.
"""

from __future__ import annotations

import numpy as np

from evooptlab.core.problem import FloatArray, Problem, ProblemOutput, ProblemSpec
from evooptlab.evaluation.dominance import non_dominated_mask

_SOURCE = "Zitzler, Deb & Thiele (2000), Evolutionary Computation 8(2) [verify]"


class _ZDT(Problem):
    _name: str
    _front_shape: str

    def __init__(self, n_variables: int = 30) -> None:
        if n_variables < 2:
            raise ValueError("ZDT problems need n_variables >= 2")
        super().__init__(
            ProblemSpec(
                name=self._name,
                lower_bounds=np.zeros(n_variables),
                upper_bounds=np.ones(n_variables),
                n_objectives=2,
                metadata={
                    "family": "ZDT",
                    "source": _SOURCE,
                    "front_shape": self._front_shape,
                    "pareto_set": "x_1 in [0, 1], x_2..x_n = 0",
                    "reference_front": "analytical",
                    "synthetic": False,
                },
            )
        )

    def _h(self, f1: FloatArray, g: FloatArray) -> FloatArray:
        raise NotImplementedError

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        n = candidates.shape[1]
        f1 = candidates[:, 0]
        g = 1.0 + 9.0 / (n - 1) * np.sum(candidates[:, 1:], axis=1)
        f2 = g * self._h(f1, g)
        return ProblemOutput(objectives=np.column_stack([f1, f2]))

    def pareto_front(self, n_points: int = 1000) -> FloatArray:
        """Reference front with ``n_points`` evenly spaced ``f1`` values on the optimal set."""
        if n_points < 2:
            raise ValueError("n_points must be >= 2")
        f1 = np.linspace(0.0, 1.0, n_points)
        return np.column_stack([f1, self._h(f1, np.ones_like(f1))])


class ZDT1(_ZDT):
    _name = "ZDT1"
    _front_shape = "convex"

    def _h(self, f1: FloatArray, g: FloatArray) -> FloatArray:
        return 1.0 - np.sqrt(f1 / g)


class ZDT2(_ZDT):
    _name = "ZDT2"
    _front_shape = "concave"

    def _h(self, f1: FloatArray, g: FloatArray) -> FloatArray:
        return 1.0 - (f1 / g) ** 2


class ZDT3(_ZDT):
    _name = "ZDT3"
    _front_shape = "disconnected"

    def _h(self, f1: FloatArray, g: FloatArray) -> FloatArray:
        r = f1 / g
        return 1.0 - np.sqrt(r) - r * np.sin(10.0 * np.pi * f1)

    def pareto_front(self, n_points: int = 1000) -> FloatArray:
        """Non-dominated subset of the optimal-set curve sampled at ``n_points`` values of ``f1``.

        The returned front therefore has fewer than ``n_points`` points.
        """
        curve = super().pareto_front(n_points)
        return curve[non_dominated_mask(curve)]
