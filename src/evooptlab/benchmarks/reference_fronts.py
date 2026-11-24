"""Helpers for constructing reference Pareto fronts from analytical definitions."""

from __future__ import annotations

import itertools
import math

import numpy as np

from evooptlab.core.problem import FloatArray


def das_dennis(n_partitions: int, n_dims: int) -> FloatArray:
    """Uniform simplex-lattice points (Das & Dennis): all ``w >= 0`` with ``sum(w) = 1`` and
    ``w_i`` a multiple of ``1 / n_partitions``.

    Returns ``C(n_partitions + n_dims - 1, n_dims - 1)`` points of dimension ``n_dims``.
    """
    if n_partitions < 1 or n_dims < 1:
        raise ValueError("n_partitions and n_dims must be >= 1")
    points = []
    # Stars and bars: choose n_dims - 1 bar positions among n_partitions + n_dims - 1 slots.
    for bars in itertools.combinations(range(n_partitions + n_dims - 1), n_dims - 1):
        edges = (-1, *bars, n_partitions + n_dims - 1)
        points.append([edges[i + 1] - edges[i] - 1 for i in range(n_dims)])
    result = np.asarray(points, dtype=np.float64) / n_partitions
    expected = math.comb(n_partitions + n_dims - 1, n_dims - 1)
    assert result.shape == (expected, n_dims)
    return result
