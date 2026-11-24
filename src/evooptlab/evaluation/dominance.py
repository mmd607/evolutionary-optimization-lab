"""Pareto dominance utilities (minimization).

``a`` dominates ``b`` iff ``a <= b`` in every objective and ``a < b`` in at least one.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from evooptlab.core.problem import BoolArray, FloatArray


def as_objective_matrix(points: npt.ArrayLike, label: str = "points") -> FloatArray:
    """Return ``points`` as a finite float64 ``(n, m)`` array with ``m >= 1``."""
    f = np.asarray(points, dtype=np.float64)
    if f.ndim != 2 or f.shape[1] < 1:
        raise ValueError(f"{label} must be a 2-D (n, m) array, got shape {f.shape}")
    if not np.all(np.isfinite(f)):
        raise ValueError(f"{label} must be finite")
    return f


def dominates(a: npt.ArrayLike, b: npt.ArrayLike) -> bool:
    """Whether objective vector ``a`` Pareto-dominates ``b``."""
    x, y = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    if x.shape != y.shape or x.ndim != 1:
        raise ValueError("a and b must be 1-D vectors of equal length")
    return bool(np.all(x <= y) and np.any(x < y))


def non_dominated_mask(points: npt.ArrayLike) -> BoolArray:
    """Boolean mask of the points not dominated by any other point.

    Duplicates do not dominate each other, so all copies of a non-dominated point are kept.
    Uses O(n^2 m) time and O(n m) memory.
    """
    f = as_objective_matrix(points)
    n = f.shape[0]
    mask = np.ones(n, dtype=bool)
    for i in range(n):
        if not mask[i]:
            continue
        # Points that i dominates are removed; if any remaining point dominates i, i is removed.
        le = np.all(f[i] <= f, axis=1)
        lt = np.any(f[i] < f, axis=1)
        mask &= ~(le & lt)
        ge = np.all(f <= f[i], axis=1)
        gt = np.any(f < f[i], axis=1)
        if np.any(ge & gt & mask):
            mask[i] = False
    return mask


def non_dominated(points: npt.ArrayLike) -> FloatArray:
    """The non-dominated subset of ``points`` (order preserved)."""
    f = as_objective_matrix(points)
    return f[non_dominated_mask(f)]
