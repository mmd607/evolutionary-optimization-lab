"""DTLZ scalable benchmark problems (DTLZ2, DTLZ7).

Source: K. Deb, L. Thiele, M. Laumanns, E. Zitzler, "Scalable Multi-Objective Optimization Test
Problems", *Proc. IEEE CEC 2002*. Bibliographic details must be verified in the literature matrix
before they are cited.

Notation: ``M`` objectives, ``n = M + k - 1`` variables, ``x in [0, 1]^n``. ``x_M`` denotes the last
``k`` variables. No constraints.

DTLZ2 (``k = 10`` is customary)
    ``g = sum_{x_i in x_M} (x_i - 0.5)^2``
    ``f_1 = (1 + g) prod_{j=1..M-1} cos(x_j pi / 2)``
    ``f_m = (1 + g) [prod_{j=1..M-m} cos(x_j pi / 2)] sin(x_{M-m+1} pi / 2)``, ``m = 2..M``
    Pareto front: ``sum_m f_m^2 = 1``, ``f >= 0`` (``x_M = 0.5``).

DTLZ7 (``k = 20`` is customary)
    ``f_m = x_m`` for ``m = 1..M-1``
    ``g = 1 + 9 / k * sum_{x_i in x_M} x_i``
    ``h = M - sum_{m=1..M-1} [f_m / (1 + g)] (1 + sin(3 pi f_m))``
    ``f_M = (1 + g) h``
    Pareto front: disconnected, the non-dominated part of the ``g = 1`` surface (``x_M = 0``).
"""

from __future__ import annotations

import numpy as np

from evooptlab.benchmarks.reference_fronts import das_dennis
from evooptlab.core.problem import FloatArray, Problem, ProblemOutput, ProblemSpec
from evooptlab.evaluation.dominance import non_dominated_mask

_SOURCE = "Deb, Thiele, Laumanns & Zitzler (2002), Proc. IEEE CEC [verify]"


class _DTLZ(Problem):
    _name: str
    _default_k: int
    _front_shape: str
    _pareto_set: str

    def __init__(self, n_objectives: int = 3, n_variables: int | None = None) -> None:
        if n_objectives < 2:
            raise ValueError("DTLZ problems need n_objectives >= 2")
        n = n_objectives + self._default_k - 1 if n_variables is None else n_variables
        k = n - n_objectives + 1
        if k < 1:
            raise ValueError(f"n_variables must be >= n_objectives (got n={n}, M={n_objectives})")
        self.k = k
        super().__init__(
            ProblemSpec(
                name=self._name,
                lower_bounds=np.zeros(n),
                upper_bounds=np.ones(n),
                n_objectives=n_objectives,
                metadata={
                    "family": "DTLZ",
                    "source": _SOURCE,
                    "k": k,
                    "front_shape": self._front_shape,
                    "pareto_set": self._pareto_set,
                    "reference_front": "analytical",
                    "synthetic": False,
                },
            )
        )


class DTLZ2(_DTLZ):
    _name = "DTLZ2"
    _default_k = 10
    _front_shape = "concave (unit hypersphere, positive orthant)"
    _pareto_set = "x_M = 0.5"

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        m = self.spec.n_objectives
        x_pos, x_m = candidates[:, : m - 1], candidates[:, m - 1 :]
        g = np.sum((x_m - 0.5) ** 2, axis=1)
        angles = x_pos * (np.pi / 2.0)
        f = np.empty((candidates.shape[0], m))
        for i in range(m):  # i = 0 is f_1
            term = (1.0 + g) * np.prod(np.cos(angles[:, : m - 1 - i]), axis=1)
            if i > 0:
                term = term * np.sin(angles[:, m - 1 - i])
            f[:, i] = term
        return ProblemOutput(objectives=f)

    def pareto_front(self, n_partitions: int = 12) -> FloatArray:
        """Das-Dennis directions projected onto the unit sphere (``C(p + M - 1, M - 1)`` points)."""
        w = das_dennis(n_partitions, self.spec.n_objectives)
        norms: FloatArray = np.linalg.norm(w, axis=1, keepdims=True)
        return w / norms


class DTLZ7(_DTLZ):
    _name = "DTLZ7"
    _default_k = 20
    _front_shape = "disconnected"
    _pareto_set = "x_M = 0"

    @staticmethod
    def _last_objective(f_pos: FloatArray, g: FloatArray, m: int) -> FloatArray:
        h: FloatArray = m - np.sum(
            f_pos / (1.0 + g)[:, None] * (1.0 + np.sin(3.0 * np.pi * f_pos)), axis=1
        )
        return (1.0 + g) * h

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        m = self.spec.n_objectives
        f_pos, x_m = candidates[:, : m - 1], candidates[:, m - 1 :]
        g = 1.0 + 9.0 / self.k * np.sum(x_m, axis=1)
        return ProblemOutput(objectives=np.column_stack([f_pos, self._last_objective(f_pos, g, m)]))

    def pareto_front(self, n_per_axis: int = 60) -> FloatArray:
        """Non-dominated subset of the ``g = 1`` surface on a regular ``(M-1)``-D grid."""
        m = self.spec.n_objectives
        axis = np.linspace(0.0, 1.0, n_per_axis)
        grid = np.stack(np.meshgrid(*([axis] * (m - 1)), indexing="ij"), axis=-1).reshape(-1, m - 1)
        surface = np.column_stack([grid, self._last_objective(grid, np.ones(grid.shape[0]), m)])
        return surface[non_dominated_mask(surface)]
