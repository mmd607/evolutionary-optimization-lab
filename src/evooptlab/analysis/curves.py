"""Search-progress curves from stored histories (anytime performance; ADR 0007).

* **Benchmarks:** IGD+ (normalized space, ADR 0003 policy) of all feasible evaluations up to
  each checkpoint. IGD+ is computed incrementally. For each reference point ``z``, the running
  minimum of ``d+(a, z)`` over the evaluations seen so far is kept. This equals IGD+ of the
  non-dominated subset, because a dominating point never has a larger ``d+``. At the last
  checkpoint the value equals the ``igd_plus`` that aggregation reports (tested).
* **HPO:** best-so-far validation error among feasible trials.

Checkpoints before the first feasible evaluation have no value (``None``), never a made-up one.
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
import numpy.typing as npt

from evooptlab.evaluation.quality import ideal_and_nadir, normalize

FloatArray = npt.NDArray[np.float64]


def checkpoints(n_evaluations: int, n_points: int) -> list[int]:
    """Evenly spaced evaluation counts ``1..n_evaluations`` (always including the last)."""
    if n_evaluations < 1:
        return []
    raw = np.linspace(1, n_evaluations, num=min(n_points, n_evaluations))
    return sorted({round(float(v)) for v in raw} | {n_evaluations})


def igd_plus_curve(
    objectives: FloatArray,
    feasible: npt.NDArray[np.bool_],
    reference_front: FloatArray,
    at: Sequence[int],
    *,
    chunk: int = 512,
) -> list[float | None]:
    ideal, nadir = ideal_and_nadir(reference_front)
    z = normalize(reference_front, ideal, nadir)
    f = normalize(objectives, ideal, nadir)
    best = np.full(z.shape[0], np.inf)
    out: list[float | None] = []
    done = 0
    for target in at:
        while done < target:
            stop = min(target, done + chunk)
            block = f[done:stop][feasible[done:stop]]
            if block.size:
                plus = np.maximum(block[:, None, :] - z[None, :, :], 0.0)
                best = np.minimum(best, np.sqrt((plus**2).sum(axis=2)).min(axis=0))
            done = stop
        out.append(float(best.mean()) if np.all(np.isfinite(best)) else None)
    return out


def best_so_far_curve(
    values: FloatArray, feasible: npt.NDArray[np.bool_], at: Sequence[int]
) -> list[float | None]:
    masked = np.where(feasible, values, np.inf)
    running = np.minimum.accumulate(masked) if masked.size else masked
    return [float(running[t - 1]) if np.isfinite(running[t - 1]) else None for t in at]
