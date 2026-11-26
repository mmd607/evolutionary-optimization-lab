"""Statistical building blocks for comparing algorithms (ADR 0007).

Everything here is a thin, tested layer over ``scipy.stats`` or a closed-form definition:

* :func:`vargha_delaney_a12`: ``A = P(X better than Y) + 0.5 P(X = Y)`` over all cross pairs.
  Here "better" follows the metric's direction. ``A = 0.5`` means no stochastic difference.
  It equals ``U / (n m)`` of the Mann-Whitney U statistic (tested). Magnitude labels are
  deliberately not assigned: the thresholds in use come from the literature, and none is
  verified in ``docs/literature`` yet.
* :func:`wilcoxon_paired`: ``scipy.stats.wilcoxon`` on paired differences, made explicit about
  degenerate cases: no pairs, or all differences zero, gives "no test" with a reason.
* :func:`holm`: Holm's step-down adjusted p-values (monotone, capped at 1).
* :func:`friedman`: ``scipy.stats.friedmanchisquare`` over blocks, plus direction-aware mean
  ranks (rank 1 = best, ties averaged).
* :func:`bootstrap_ci`: percentile bootstrap of the median or mean with a fixed seed, so the
  interval is reproducible.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

import numpy as np
import numpy.typing as npt

Direction = Literal["minimize", "maximize"]
FloatArray = npt.NDArray[np.float64]


def _array(values: Sequence[float] | FloatArray) -> FloatArray:
    a = np.asarray(values, dtype=np.float64)
    if a.ndim != 1:
        raise ValueError("expected a 1-D sequence")
    if not np.all(np.isfinite(a)):
        raise ValueError("values must be finite; drop missing values explicitly first")
    return a


def vargha_delaney_a12(
    x: Sequence[float] | FloatArray, y: Sequence[float] | FloatArray, direction: Direction
) -> float:
    """Probability that a random ``x`` is better than a random ``y`` (ties count half)."""
    a, b = _array(x), _array(y)
    if a.size == 0 or b.size == 0:
        raise ValueError("both samples must be non-empty")
    diff = a[:, None] - b[None, :]
    better = (diff < 0) if direction == "minimize" else (diff > 0)
    ties = diff == 0
    return float((better.sum() + 0.5 * ties.sum()) / diff.size)


@dataclass(frozen=True)
class PairedTest:
    n_pairs: int
    n_nonzero: int
    statistic: float | None
    p_value: float | None
    note: str | None = None


def wilcoxon_paired(
    x: Sequence[float] | FloatArray,
    y: Sequence[float] | FloatArray,
    *,
    zero_method: Literal["wilcox", "pratt", "zsplit"] = "wilcox",
    alternative: Literal["two-sided"] = "two-sided",
) -> PairedTest:
    """Wilcoxon signed-rank test of paired samples ``x`` and ``y``."""
    from scipy.stats import wilcoxon

    a, b = _array(x), _array(y)
    if a.shape != b.shape:
        raise ValueError("paired samples must have the same length")
    d = a - b
    n_nonzero = int(np.count_nonzero(d))
    if a.size == 0:
        return PairedTest(0, 0, None, None, "no complete pairs")
    if n_nonzero == 0:
        return PairedTest(int(a.size), 0, None, None, "all paired differences are zero")
    result = wilcoxon(a, b, zero_method=zero_method, alternative=alternative)
    return PairedTest(
        n_pairs=int(a.size),
        n_nonzero=n_nonzero,
        statistic=float(result.statistic),
        p_value=float(result.pvalue),
    )


def holm(p_values: Sequence[float | None]) -> list[float | None]:
    """Holm-adjusted p-values; ``None`` entries (tests not run) stay ``None``."""
    present = [(i, p) for i, p in enumerate(p_values) if p is not None]
    for _, p in present:
        if not 0.0 <= p <= 1.0 or math.isnan(p):
            raise ValueError(f"invalid p-value {p}")
    m = len(present)
    adjusted: list[float | None] = [None] * len(p_values)
    running = 0.0
    for rank, (i, p) in enumerate(sorted(present, key=lambda item: item[1])):
        running = max(running, min(1.0, (m - rank) * p))
        adjusted[i] = running
    return adjusted


@dataclass(frozen=True)
class FriedmanResult:
    n_blocks: int
    k: int
    statistic: float | None
    p_value: float | None
    mean_ranks: list[float]
    note: str | None = None


def mean_ranks(blocks: npt.ArrayLike, direction: Direction) -> list[float]:
    """Average within-block rank of each column (1 = best; ties get the average rank)."""
    from scipy.stats import rankdata

    m = np.asarray(blocks, dtype=np.float64)
    oriented = m if direction == "minimize" else -m
    ranks = np.vstack([rankdata(row) for row in oriented])
    return [float(v) for v in ranks.mean(axis=0)]


def friedman(blocks: npt.ArrayLike, direction: Direction) -> FriedmanResult:
    """Friedman test over ``(n_blocks, k)`` values; rows are blocks, columns treatments."""
    from scipy.stats import friedmanchisquare

    m = np.asarray(blocks, dtype=np.float64)
    if m.ndim != 2 or not np.all(np.isfinite(m)):
        raise ValueError("blocks must be a finite 2-D array")
    n, k = m.shape
    ranks = mean_ranks(m, direction) if n else []
    if k < 3:
        return FriedmanResult(n, k, None, None, ranks, "Friedman needs at least 3 algorithms")
    if n < 2:
        return FriedmanResult(n, k, None, None, ranks, "Friedman needs at least 2 blocks")
    if np.all(m == m[:, :1]):
        return FriedmanResult(n, k, None, None, ranks, "all algorithms tie in every block")
    result = friedmanchisquare(*m.T)
    return FriedmanResult(n, k, float(result.statistic), float(result.pvalue), ranks)


@dataclass(frozen=True)
class Interval:
    low: float
    high: float
    level: float


def bootstrap_ci(
    values: Sequence[float] | FloatArray,
    *,
    statistic: Literal["median", "mean"],
    level: float,
    n_resamples: int,
    seed: int,
) -> Interval | None:
    """Percentile bootstrap interval of the median or mean; ``None`` for fewer than 2 values."""
    a = _array(values)
    if a.size < 2:
        return None
    rng = np.random.default_rng(seed)
    samples = a[rng.integers(0, a.size, size=(n_resamples, a.size))]
    stats = np.median(samples, axis=1) if statistic == "median" else samples.mean(axis=1)
    alpha = (1.0 - level) / 2.0
    low, high = np.quantile(stats, [alpha, 1.0 - alpha])
    return Interval(float(low), float(high), level)
