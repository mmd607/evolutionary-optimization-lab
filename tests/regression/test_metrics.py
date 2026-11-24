"""Reference-value and edge-case tests for quality indicators.

References: hand-computed values, analytical limits for continuous fronts, and pymoo 0.6
indicators (skipped when pymoo is not installed).
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from evooptlab.benchmarks import DTLZ2, ZDT1
from evooptlab.evaluation import metrics


class TestHypervolume:
    def test_single_point_is_box(self) -> None:
        assert metrics.hypervolume([[1.0, 2.0, 3.0]], [2.0, 4.0, 7.0]) == 1.0 * 2.0 * 4.0

    def test_two_points_inclusion_exclusion(self) -> None:
        # boxes [1,3]x[2,3] and [2,3]x[1,3] overlap in [2,3]x[2,3]
        assert metrics.hypervolume([[1, 2], [2, 1]], [3, 3]) == pytest.approx(2 + 2 - 1)

    def test_one_dimensional(self) -> None:
        assert metrics.hypervolume([[3.0], [1.0]], [5.0]) == 4.0

    def test_dominated_and_duplicate_points_do_not_change_hv(self) -> None:
        base = metrics.hypervolume([[1, 2], [2, 1]], [3, 3])
        assert metrics.hypervolume(np.array([[1, 2], [2, 1], [2.5, 2.5], [1, 2]]), [3, 3]) == base

    def test_points_outside_reference_contribute_nothing(self) -> None:
        assert metrics.hypervolume([[4.0, 0.0], [3.0, 1.0]], [3.0, 3.0]) == 0.0
        assert metrics.hypervolume([[1.0, 1.0], [0.0, 5.0]], [3.0, 3.0]) == 4.0

    def test_zdt1_front_converges_to_two_thirds(self) -> None:
        hv = metrics.hypervolume(ZDT1().pareto_front(4000), [1.0, 1.0])
        assert hv == pytest.approx(2.0 / 3.0, abs=1e-3)
        assert hv < 2.0 / 3.0  # a finite sample under-approximates

    def test_dtlz2_front_converges_to_cube_minus_sphere_octant(self) -> None:
        hv = metrics.hypervolume(DTLZ2(3).pareto_front(40), [1.0, 1.0, 1.0])
        assert hv == pytest.approx(1.0 - math.pi / 6.0, abs=2e-2)
        assert hv < 1.0 - math.pi / 6.0

    @pytest.mark.parametrize("m", [3, 4])
    def test_matches_inclusion_exclusion_on_random_sets(self, m: int) -> None:
        rng = np.random.default_rng(m)
        pts = rng.uniform(0, 1, size=(6, m))
        ref = np.ones(m) * 1.2
        # brute-force inclusion-exclusion over all subsets
        total = 0.0
        for mask in range(1, 2**6):
            idx = [i for i in range(6) if mask >> i & 1]
            corner = pts[idx].max(axis=0)
            total += (-1) ** (len(idx) + 1) * float(np.prod(np.clip(ref - corner, 0, None)))
        assert metrics.hypervolume(pts, ref) == pytest.approx(total, rel=1e-12)

    def test_invalid_reference_point(self) -> None:
        with pytest.raises(ValueError):
            metrics.hypervolume([[1.0, 1.0]], [2.0])
        with pytest.raises(ValueError):
            metrics.hypervolume([[1.0, 1.0]], [np.inf, 2.0])


class TestDistanceIndicators:
    Z = np.array([[0.0, 1.0], [0.5, 0.5], [1.0, 0.0]])

    def test_zero_on_reference_front(self) -> None:
        for fn in (metrics.gd, metrics.igd, metrics.gd_plus, metrics.igd_plus):
            assert fn(self.Z, self.Z) == 0.0

    def test_hand_computed_values(self) -> None:
        a = np.array([[0.5, 1.0]])
        assert metrics.gd(a, self.Z) == pytest.approx(0.5)  # nearest: (0,1) or (0.5,0.5)
        assert metrics.igd(a, self.Z) == pytest.approx((0.5 + 0.5 + math.sqrt(1.25)) / 3)
        assert metrics.gd_plus(a, self.Z) == pytest.approx(0.5)
        # d+ = ||max(a - z, 0)||: (0.5,0), (0,0.5), (0,1)
        assert metrics.igd_plus(a, self.Z) == pytest.approx((0.5 + 0.5 + 1.0) / 3)

    def test_plus_variants_ignore_better_points(self) -> None:
        better = self.Z - 0.1  # dominates the reference front
        assert metrics.gd_plus(better, self.Z) == 0.0
        assert metrics.igd_plus(better, self.Z) == 0.0
        assert metrics.gd(better, self.Z) > 0.0

    def test_dimension_mismatch_and_empty(self) -> None:
        with pytest.raises(ValueError, match="dimensions differ"):
            metrics.igd(np.zeros((2, 3)), self.Z)
        with pytest.raises(ValueError, match="non-empty"):
            metrics.gd(np.zeros((0, 2)), self.Z)


class TestOtherIndicators:
    def test_spacing_zero_for_even_points(self) -> None:
        t = np.linspace(0, 1, 11)
        assert metrics.spacing(np.column_stack([t, 1 - t])) == pytest.approx(0.0, abs=1e-12)

    def test_spacing_positive_for_uneven_points(self) -> None:
        assert metrics.spacing(np.array([[0, 1], [0.1, 0.9], [1, 0]])) > 0.0

    def test_spacing_needs_two_points(self) -> None:
        with pytest.raises(ValueError):
            metrics.spacing([[0.0, 1.0]])

    def test_feasibility_rate(self) -> None:
        assert metrics.feasibility_rate(np.array([True, False, True, True])) == 0.75
        with pytest.raises(ValueError):
            metrics.feasibility_rate(np.array([], dtype=bool))
        with pytest.raises(ValueError):
            metrics.feasibility_rate(np.array([1, 0]))


# ---------------------------------------------------------------------------------------------
# Cross-check against pymoo indicators
# ---------------------------------------------------------------------------------------------
def _random_sets(m: int, seed: int) -> tuple[Any, Any]:
    rng = np.random.default_rng(seed)
    return rng.uniform(0, 1, size=(40, m)), rng.uniform(0, 1, size=(80, m))


@pytest.mark.parametrize("m", [2, 3, 4])
def test_hypervolume_matches_pymoo(m: int) -> None:
    hv_mod = pytest.importorskip("pymoo.indicators.hv")
    a, _ = _random_sets(m, m)
    ref = np.full(m, 1.1)
    assert metrics.hypervolume(a, ref) == pytest.approx(hv_mod.HV(ref_point=ref)(a), rel=1e-10)


@pytest.mark.parametrize("m", [2, 3])
@pytest.mark.parametrize(
    ("ours", "module", "cls"),
    [
        (metrics.gd, "pymoo.indicators.gd", "GD"),
        (metrics.gd_plus, "pymoo.indicators.gd_plus", "GDPlus"),
        (metrics.igd, "pymoo.indicators.igd", "IGD"),
        (metrics.igd_plus, "pymoo.indicators.igd_plus", "IGDPlus"),
    ],
)
def test_distance_indicators_match_pymoo(m: int, ours: Any, module: str, cls: str) -> None:
    mod = pytest.importorskip(module)
    a, z = _random_sets(m, 10 + m)
    assert ours(a, z) == pytest.approx(getattr(mod, cls)(z)(a), rel=1e-12)
