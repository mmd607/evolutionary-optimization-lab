"""Reference checks for ZDT and DTLZ problems.

Two independent references:

1. **Analytical**: points on the known Pareto-optimal set must land exactly on the analytical front.
2. **pymoo** (pinned, ``test`` dependency group): objectives for random inputs must match
   pymoo's implementation, and our reference fronts must match pymoo's ``pareto_front()``.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pytest

from evooptlab.benchmarks import DTLZ2, DTLZ7, ZDT1, ZDT2, ZDT3
from evooptlab.benchmarks.reference_fronts import das_dennis
from evooptlab.core.problem import Problem
from evooptlab.evaluation.dominance import non_dominated_mask
from evooptlab.evaluation.metrics import _min_distances

ATOL = 1e-12


def _on_optimal_set(problem: Problem, n: int, rng: np.random.Generator) -> np.ndarray[Any, Any]:
    spec = problem.spec
    x = rng.uniform(0, 1, size=(n, spec.n_variables))
    if spec.metadata["family"] == "ZDT":
        x[:, 1:] = 0.0
    elif problem.name == "DTLZ2":
        x[:, spec.n_objectives - 1 :] = 0.5
    else:  # DTLZ7
        x[:, spec.n_objectives - 1 :] = 0.0
    return x


class TestAnalytical:
    def test_zdt1_front(self) -> None:
        p = ZDT1()
        f = p.evaluate_batch(_on_optimal_set(p, 200, np.random.default_rng(0))).objectives
        np.testing.assert_allclose(f[:, 1], 1.0 - np.sqrt(f[:, 0]), atol=ATOL)

    def test_zdt2_front(self) -> None:
        p = ZDT2()
        f = p.evaluate_batch(_on_optimal_set(p, 200, np.random.default_rng(0))).objectives
        np.testing.assert_allclose(f[:, 1], 1.0 - f[:, 0] ** 2, atol=ATOL)

    def test_zdt3_optimal_set_curve(self) -> None:
        p = ZDT3()
        f = p.evaluate_batch(_on_optimal_set(p, 200, np.random.default_rng(0))).objectives
        f1 = f[:, 0]
        np.testing.assert_allclose(
            f[:, 1], 1.0 - np.sqrt(f1) - f1 * np.sin(10 * np.pi * f1), atol=ATOL
        )

    def test_zdt3_front_is_disconnected_and_non_dominated(self) -> None:
        front = ZDT3().pareto_front(5000)
        assert non_dominated_mask(front).all()
        gaps = np.diff(np.sort(front[:, 0]))
        assert int(np.sum(gaps > 0.05)) == 4  # five disconnected segments

    @pytest.mark.parametrize("m", [2, 3, 5])
    def test_dtlz2_front_is_unit_sphere(self, m: int) -> None:
        p = DTLZ2(m)
        f = p.evaluate_batch(_on_optimal_set(p, 100, np.random.default_rng(m))).objectives
        np.testing.assert_allclose(np.sum(f**2, axis=1), 1.0, atol=1e-12)
        assert np.all(f >= -ATOL)
        np.testing.assert_allclose(np.linalg.norm(p.pareto_front(8), axis=1), 1.0, atol=ATOL)

    def test_dtlz2_off_front_is_scaled_by_one_plus_g(self) -> None:
        p = DTLZ2(3)
        x = np.full((1, p.spec.n_variables), 0.5)
        x[0, 2:] = 1.0  # g = 10 * 0.25 = 2.5
        f = p.evaluate_batch(x).objectives
        np.testing.assert_allclose(np.linalg.norm(f), 3.5, atol=ATOL)

    def test_dtlz7_surface_and_front(self) -> None:
        p = DTLZ7(3)
        f = p.evaluate_batch(_on_optimal_set(p, 100, np.random.default_rng(1))).objectives
        expected = 2.0 * (3 - np.sum(f[:, :2] / 2.0 * (1 + np.sin(3 * np.pi * f[:, :2])), axis=1))
        np.testing.assert_allclose(f[:, 2], expected, atol=ATOL)
        front = p.pareto_front(40)
        assert non_dominated_mask(front).all()

    def test_default_dimensions_match_configs(self) -> None:
        assert ZDT1().spec.n_variables == 30
        assert DTLZ2().spec.n_variables == 12
        assert DTLZ7().spec.n_variables == 22
        assert DTLZ7().k == 20

    @pytest.mark.parametrize(
        ("factory", "match"),
        [
            (lambda: ZDT1(1), "n_variables >= 2"),
            (lambda: DTLZ2(1), "n_objectives >= 2"),
            (lambda: DTLZ2(3, n_variables=2), "n_variables must be >= n_objectives"),
            (lambda: ZDT1().pareto_front(1), "n_points"),
        ],
    )
    def test_invalid_construction(self, factory: Any, match: str) -> None:
        with pytest.raises(ValueError, match=match):
            factory()

    def test_metadata_records_provenance(self) -> None:
        for p in (ZDT1(), ZDT2(), ZDT3(), DTLZ2(), DTLZ7()):
            md = p.spec.metadata
            assert md["synthetic"] is False
            assert md["reference_front"] == "analytical"
            assert "[verify]" in md["source"]


class TestDasDennis:
    @pytest.mark.parametrize(("p", "m"), [(1, 2), (4, 2), (12, 3), (6, 4)])
    def test_count_and_simplex(self, p: int, m: int) -> None:
        w = das_dennis(p, m)
        assert w.shape == (math.comb(p + m - 1, m - 1), m)
        np.testing.assert_allclose(w.sum(axis=1), 1.0, atol=ATOL)
        assert np.all(w >= 0)
        assert len({tuple(row) for row in np.round(w * p).astype(int)}) == w.shape[0]

    def test_invalid(self) -> None:
        with pytest.raises(ValueError):
            das_dennis(0, 3)


# ---------------------------------------------------------------------------------------------
# Cross-check against pymoo
# ---------------------------------------------------------------------------------------------
CASES = [
    (ZDT1, {}, "zdt1", {}),
    (ZDT2, {}, "zdt2", {}),
    (ZDT3, {}, "zdt3", {}),
    (DTLZ2, {"n_objectives": 3}, "dtlz2", {"n_obj": 3, "n_var": 12}),
    (DTLZ7, {"n_objectives": 3}, "dtlz7", {"n_obj": 3, "n_var": 22}),
]


@pytest.mark.parametrize(("cls", "kw", "pymoo_name", "pymoo_kw"), CASES)
def test_objectives_match_pymoo(cls: Any, kw: Any, pymoo_name: str, pymoo_kw: Any) -> None:
    pymoo_problems = pytest.importorskip("pymoo.problems")
    ours = cls(**kw)
    theirs = pymoo_problems.get_problem(pymoo_name, **pymoo_kw)
    assert theirs.n_var == ours.spec.n_variables
    assert theirs.n_obj == ours.spec.n_objectives
    np.testing.assert_array_equal(theirs.xl, ours.spec.lower_bounds)
    np.testing.assert_array_equal(theirs.xu, ours.spec.upper_bounds)
    x = np.random.default_rng(123).uniform(0, 1, size=(500, ours.spec.n_variables))
    np.testing.assert_allclose(
        ours.evaluate_batch(x).objectives, theirs.evaluate(x), rtol=1e-12, atol=1e-12
    )


@pytest.mark.parametrize("cls", [ZDT1, ZDT2, ZDT3])
def test_zdt_fronts_match_pymoo(cls: Any) -> None:
    pymoo_problems = pytest.importorskip("pymoo.problems")
    theirs = pymoo_problems.get_problem(cls.__name__.lower()).pareto_front()
    ours = cls().pareto_front(20000)
    # Every pymoo front point lies on our (dense) front ...
    assert _min_distances(theirs, ours, plus=False).max() < 1e-3
    # ... and our front covers the same f1 regions, with no extra or missing segment. pymoo's front
    # has ~100 points, so this is compared along f1, where pymoo's spacing is at most ~0.01. That
    # is well below the >= 0.1 gaps between ZDT3's segments.
    nearest = np.min(np.abs(ours[:, :1] - theirs[None, :, 0]), axis=1)
    assert nearest.max() < 6e-3


def test_dtlz2_front_matches_pymoo() -> None:
    pymoo_problems = pytest.importorskip("pymoo.problems")
    from pymoo.util.ref_dirs import get_reference_directions

    ref_dirs = get_reference_directions("das-dennis", 3, n_partitions=12)
    theirs = pymoo_problems.get_problem("dtlz2", n_obj=3).pareto_front(ref_dirs)
    ours = DTLZ2(3).pareto_front(12)
    key = np.lexsort(ours.T)
    np.testing.assert_allclose(ours[key], theirs[np.lexsort(theirs.T)], atol=1e-12)
