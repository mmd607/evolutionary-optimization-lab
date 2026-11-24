"""Quality indicators of a run under one declared normalization and reference-point policy.

The **proposed** policy is recorded in ADR 0003 and still needs owner approval (P8):

1. The approximation set is the non-dominated subset of the run's **feasible** evaluations.
2. Objectives are normalized with the ideal and nadir points of the problem's **reference front**:
   ``(f - ideal) / (nadir - ideal)``. After this, the reference front spans ``[0, 1]`` per
   objective.
3. The HV reference point is ``(1 + offset) * ones`` in normalized space, with ``offset = 0.1``.
4. HV is also reported as a ratio to the HV of the reference front under the same policy.
5. If no feasible point exists, every quality indicator is ``None`` and a reason is given. It is
   never zero, because zero would be a fabricated measurement.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import numpy.typing as npt

from evooptlab.core.problem import FloatArray
from evooptlab.evaluation import metrics
from evooptlab.evaluation.dominance import as_objective_matrix, non_dominated

POLICY_VERSION = "proposed-v1"


@dataclass(frozen=True)
class QualityPolicy:
    """Normalization and HV reference-point policy (ADR 0003)."""

    normalize: bool = True
    reference_offset: float = 0.1
    version: str = POLICY_VERSION

    def __post_init__(self) -> None:
        if not self.reference_offset > 0.0:
            raise ValueError("reference_offset must be positive")


def ideal_and_nadir(reference_front: npt.ArrayLike) -> tuple[FloatArray, FloatArray]:
    z = as_objective_matrix(reference_front, "reference_front")
    ideal, nadir = z.min(axis=0), z.max(axis=0)
    if np.any(nadir <= ideal):
        raise ValueError("reference front is degenerate in at least one objective")
    return ideal, nadir


def normalize(points: npt.ArrayLike, ideal: FloatArray, nadir: FloatArray) -> FloatArray:
    f = as_objective_matrix(points)
    if f.shape[1] != ideal.shape[0]:
        raise ValueError("objective dimension does not match ideal/nadir")
    return (f - ideal) / (nadir - ideal)


def compute_quality(
    objectives: npt.ArrayLike,
    feasible: npt.ArrayLike,
    reference_front: npt.ArrayLike,
    policy: QualityPolicy | None = None,
) -> dict[str, Any]:
    """Quality indicators for one run's evaluations (all of them, not only the final batch)."""
    policy = policy or QualityPolicy()
    f = as_objective_matrix(objectives, "objectives")
    mask = np.asarray(feasible)
    if mask.shape != (f.shape[0],) or mask.dtype != np.bool_:
        raise ValueError("feasible must be a boolean vector with one entry per evaluation")
    z = as_objective_matrix(reference_front, "reference_front")
    if z.shape[1] != f.shape[1]:
        raise ValueError("reference front and objectives have different dimensions")

    result: dict[str, Any] = {
        "policy": asdict(policy),
        "n_evaluations": int(f.shape[0]),
        "feasibility_rate": metrics.feasibility_rate(mask),
        "n_reference_points": int(z.shape[0]),
    }
    indicator_keys = ("hypervolume", "hypervolume_ratio", "igd", "igd_plus", "gd", "gd_plus")
    if not mask.any():
        result.update(dict.fromkeys(indicator_keys))
        result.update({"spacing": None, "n_nondominated": 0, "missing_reason": "no feasible point"})
        return result

    approx = non_dominated(f[mask])
    if policy.normalize:
        ideal, nadir = ideal_and_nadir(z)
        approx_n, z_n = normalize(approx, ideal, nadir), normalize(z, ideal, nadir)
    else:
        approx_n, z_n = approx, z
    ref = np.full(f.shape[1], 1.0 + policy.reference_offset)
    if not policy.normalize:
        ref = z.max(axis=0) + policy.reference_offset * (z.max(axis=0) - z.min(axis=0))

    hv = metrics.hypervolume(approx_n, ref)
    hv_front = metrics.hypervolume(z_n, ref)
    result.update(
        {
            "n_nondominated": int(approx.shape[0]),
            "hypervolume": hv,
            "hypervolume_ratio": hv / hv_front if hv_front > 0 else None,
            "reference_point": ref.tolist(),
            "igd": metrics.igd(approx_n, z_n),
            "igd_plus": metrics.igd_plus(approx_n, z_n),
            "gd": metrics.gd(approx_n, z_n),
            "gd_plus": metrics.gd_plus(approx_n, z_n),
            "spacing": metrics.spacing(approx_n) if approx_n.shape[0] >= 2 else None,
            "missing_reason": None,
        }
    )
    return result
