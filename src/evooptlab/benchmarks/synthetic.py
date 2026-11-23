"""Small synthetic problems with analytically known optima.

These problems exist to **test the framework** (interfaces, budget accounting, constraint
handling, determinism). They are not part of the benchmark suite, and results on them must not
be reported as benchmark findings.

=====================  ====  ====  ====  ===============================================
Problem                vars  objs  cons  Known optimum
=====================  ====  ====  ====  ===============================================
``Sphere``             d     1     0     ``x* = center``, ``f* = 0``
``TwoSpheres``         d     2     0     Pareto set ``x = t*1, t in [0, 1]``;
                                         front ``f1 = d t^2, f2 = d (1 - t)^2``
``ConstrainedSphere``  d     1     1     ``g = 1 - sum(x) <= 0``; ``x*_i = 1/d``, ``f* = 1/d``
=====================  ====  ====  ====  ===============================================
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from evooptlab.core.problem import FloatArray, Problem, ProblemOutput, ProblemSpec


def _check_dim(n_variables: int) -> None:
    if n_variables < 1:
        raise ValueError("n_variables must be >= 1")


class Sphere(Problem):
    """Single-objective ``f(x) = ||x - center||^2`` on ``[-5, 5]^d``."""

    def __init__(self, n_variables: int = 3, center: npt.ArrayLike | None = None) -> None:
        _check_dim(n_variables)
        c = np.zeros(n_variables) if center is None else np.asarray(center, dtype=np.float64)
        if c.shape != (n_variables,):
            raise ValueError(f"center must have shape ({n_variables},)")
        if np.any(np.abs(c) > 5.0):
            raise ValueError("center must lie inside [-5, 5]^d")
        self._center = c
        super().__init__(
            ProblemSpec(
                name="sphere",
                lower_bounds=np.full(n_variables, -5.0),
                upper_bounds=np.full(n_variables, 5.0),
                n_objectives=1,
                metadata={"synthetic": True, "optimum_value": 0.0},
            )
        )

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        f = np.sum((candidates - self._center) ** 2, axis=1, keepdims=True)
        return ProblemOutput(objectives=f)


class TwoSpheres(Problem):
    """Bi-objective ``(||x||^2, ||x - 1||^2)`` on ``[0, 1]^d`` with a known convex front."""

    def __init__(self, n_variables: int = 2) -> None:
        _check_dim(n_variables)
        super().__init__(
            ProblemSpec(
                name="two_spheres",
                lower_bounds=np.zeros(n_variables),
                upper_bounds=np.ones(n_variables),
                n_objectives=2,
                metadata={"synthetic": True},
            )
        )

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        f1 = np.sum(candidates**2, axis=1)
        f2 = np.sum((candidates - 1.0) ** 2, axis=1)
        return ProblemOutput(objectives=np.column_stack([f1, f2]))

    def pareto_front(self, n_points: int) -> FloatArray:
        """Exact Pareto front sampled at ``n_points`` evenly spaced values of ``t``."""
        t = np.linspace(0.0, 1.0, n_points)
        d = self.spec.n_variables
        return np.column_stack([d * t**2, d * (1.0 - t) ** 2])


class ConstrainedSphere(Problem):
    """``min ||x||^2`` subject to ``sum(x) >= 1`` (``g = 1 - sum(x) <= 0``) on ``[0, 1]^d``."""

    def __init__(self, n_variables: int = 2) -> None:
        _check_dim(n_variables)
        super().__init__(
            ProblemSpec(
                name="constrained_sphere",
                lower_bounds=np.zeros(n_variables),
                upper_bounds=np.ones(n_variables),
                n_objectives=1,
                n_constraints=1,
                metadata={"synthetic": True, "optimum_value": 1.0 / n_variables},
            )
        )

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        f = np.sum(candidates**2, axis=1, keepdims=True)
        g = 1.0 - np.sum(candidates, axis=1, keepdims=True)
        return ProblemOutput(objectives=f, constraints=g)
