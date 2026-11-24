"""Multi-objective quality indicators (all objectives minimized).

Every function documents its exact definition, because several indicators have variants in the
literature. The definitions below match pymoo 0.6 (cross-checked in ``tests/regression``), except
``spacing``, which pymoo does not provide.

==============  ==========================================================  ==============
Indicator       Definition (A = approximation set, Z = reference front)     Better
==============  ==========================================================  ==============
``hypervolume`` Lebesgue measure of the region dominated by A and bounded     higher
                by reference point r; points not strictly better than r in
                every objective contribute nothing. Exact computation.
``gd``          mean over a in A of min over z in Z of ||a - z||_2            lower
``gd_plus``     mean over a in A of min over z of ||max(a - z, 0)||_2         lower
``igd``         mean over z in Z of min over a in A of ||a - z||_2            lower
``igd_plus``    mean over z in Z of min over a of ||max(a - z, 0)||_2         lower
``spacing``     Schott's spacing: std (ddof=1) of L1 nearest-neighbour        lower (more
                distances within A                                            uniform)
``feasibility_rate``  fraction of feasible evaluations                         higher
==============  ==========================================================  ==============

``gd``/``igd`` use the arithmetic mean of distances (``p = 1``), which is the pymoo convention and
not the original root-mean-square form. GD and spacing alone do not measure convergence plus
diversity and must be reported alongside HV and IGD+ (``docs/metrics_and_statistics.md``).
Normalization and the reference-point policy are applied by ``evaluation.quality``, not here.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

from evooptlab.core.problem import FloatArray
from evooptlab.evaluation.dominance import as_objective_matrix, non_dominated

_CHUNK = 2048


def _check_same_dims(a: FloatArray, b: FloatArray) -> None:
    if a.shape[1] != b.shape[1]:
        raise ValueError(f"objective dimensions differ: {a.shape[1]} vs {b.shape[1]}")
    if a.shape[0] == 0 or b.shape[0] == 0:
        raise ValueError("point sets must be non-empty")


def _min_distances(source: FloatArray, target: FloatArray, *, plus: bool) -> FloatArray:
    """For each row of ``source``, the minimum (modified) distance to any row of ``target``.

    With ``plus=True`` the distance is ``||max(s - t, 0)||``, i.e. only the part by which ``s`` is
    worse than ``t`` counts (Ishibuchi et al.'s modified distance, used in GD+/IGD+). Here ``s`` is
    the approximation point and ``t`` the reference point; callers pass them in that orientation.
    """
    out = np.empty(source.shape[0])
    for start in range(0, source.shape[0], _CHUNK):
        diff = source[start : start + _CHUNK, None, :] - target[None, :, :]
        if plus:
            diff = np.maximum(diff, 0.0)
        out[start : start + _CHUNK] = np.sqrt(np.min(np.sum(diff**2, axis=2), axis=1))
    return out


def gd(approximation: npt.ArrayLike, reference_front: npt.ArrayLike) -> float:
    a = as_objective_matrix(approximation, "approximation")
    z = as_objective_matrix(reference_front, "reference_front")
    _check_same_dims(a, z)
    return float(np.mean(_min_distances(a, z, plus=False)))


def gd_plus(approximation: npt.ArrayLike, reference_front: npt.ArrayLike) -> float:
    a = as_objective_matrix(approximation, "approximation")
    z = as_objective_matrix(reference_front, "reference_front")
    _check_same_dims(a, z)
    return float(np.mean(_min_distances(a, z, plus=True)))


def igd(approximation: npt.ArrayLike, reference_front: npt.ArrayLike) -> float:
    a = as_objective_matrix(approximation, "approximation")
    z = as_objective_matrix(reference_front, "reference_front")
    _check_same_dims(a, z)
    return float(np.mean(_min_distances(z, a, plus=False)))


def igd_plus(approximation: npt.ArrayLike, reference_front: npt.ArrayLike) -> float:
    a = as_objective_matrix(approximation, "approximation")
    z = as_objective_matrix(reference_front, "reference_front")
    _check_same_dims(a, z)
    # d+(z, a) = ||max(a - z, 0)||: orientation (a minus z) is what makes IGD+ weakly Pareto
    # compliant, so the "source" of the minimum is z but the difference is a - z.
    out = np.empty(z.shape[0])
    for start in range(0, z.shape[0], _CHUNK):
        diff = np.maximum(a[None, :, :] - z[start : start + _CHUNK, None, :], 0.0)
        out[start : start + _CHUNK] = np.sqrt(np.min(np.sum(diff**2, axis=2), axis=1))
    return float(np.mean(out))


def spacing(approximation: npt.ArrayLike) -> float:
    """Schott's spacing. Requires at least two points; 0 means perfectly even L1 spacing."""
    a = as_objective_matrix(approximation, "approximation")
    if a.shape[0] < 2:
        raise ValueError("spacing needs at least two points")
    d = np.sum(np.abs(a[:, None, :] - a[None, :, :]), axis=2)
    np.fill_diagonal(d, np.inf)
    return float(np.std(d.min(axis=1), ddof=1))


def feasibility_rate(feasible: npt.ArrayLike) -> float:
    mask = np.asarray(feasible)
    if mask.dtype != np.bool_ or mask.ndim != 1:
        raise ValueError("feasible must be a 1-D boolean array")
    if mask.size == 0:
        raise ValueError("feasibility rate of an empty set is undefined")
    return float(mask.mean())


def hypervolume(points: npt.ArrayLike, reference_point: npt.ArrayLike) -> float:
    """Exact hypervolume of ``points`` with respect to ``reference_point``.

    Uses dimension sweep: an O(n log n) sweep in 2-D, recursive slicing along the last objective
    above that. This is fast enough for the front sizes in this project (hundreds of points,
    up to about 5 objectives).
    """
    f = as_objective_matrix(points)
    r = np.asarray(reference_point, dtype=np.float64)
    if r.shape != (f.shape[1],) or not np.all(np.isfinite(r)):
        raise ValueError(f"reference_point must be a finite vector of length {f.shape[1]}")
    f = f[np.all(f < r, axis=1)]
    if f.shape[0] == 0:
        return 0.0
    return float(_hv(np.unique(non_dominated(f), axis=0), r))


def _hv(f: FloatArray, r: FloatArray) -> float:
    m = f.shape[1]
    if m == 1:
        return float(r[0] - f[:, 0].min())
    if m == 2:
        return _hv2d(f, r)
    f = f[np.argsort(f[:, -1], kind="stable")]
    volume = 0.0
    for i in range(f.shape[0]):
        upper = f[i + 1, -1] if i + 1 < f.shape[0] else r[-1]
        depth = upper - f[i, -1]
        if depth > 0.0:
            # The 2-D staircase handles dominated points itself, so 3-D slices skip the
            # quadratic non-dominated filter (O(n^2 log n) overall instead of O(n^3)).
            prefix = f[: i + 1, :-1]
            volume += depth * (
                _hv2d(prefix, r[:-1]) if m == 3 else _hv(non_dominated(prefix), r[:-1])
            )
    return volume


def _hv2d(f: FloatArray, r: FloatArray) -> float:
    """Exact 2-D hypervolume of any point set inside the reference box (dominated points allowed).

    Sort by (f0, f1); a point adds area only where its f1 is below the running minimum of the
    points before it. Vectorized form of the classic staircase sweep.
    """
    f = f[np.lexsort((f[:, 1], f[:, 0]))]
    best = np.minimum.accumulate(f[:, 1])
    previous = np.concatenate(([r[1]], best[:-1]))
    gain = np.clip(previous - f[:, 1], 0.0, None)
    return float(np.sum((r[0] - f[:, 0]) * gain))
