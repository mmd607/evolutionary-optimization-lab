"""Tests for Pareto dominance utilities."""

from __future__ import annotations

import numpy as np
import pytest

from evooptlab.evaluation.dominance import dominates, non_dominated, non_dominated_mask


def _brute_force(f: np.ndarray) -> np.ndarray:
    n = f.shape[0]
    return np.array([not any(dominates(f[j], f[i]) for j in range(n) if j != i) for i in range(n)])


def test_dominates_definition() -> None:
    assert dominates([1, 1], [2, 2])
    assert dominates([1, 2], [1, 3])
    assert not dominates([1, 1], [1, 1])
    assert not dominates([1, 3], [2, 2])
    with pytest.raises(ValueError):
        dominates([1, 2], [1, 2, 3])


def test_mask_simple_case() -> None:
    f = np.array([[1, 4], [2, 2], [4, 1], [3, 3], [2, 2]])
    assert non_dominated_mask(f).tolist() == [True, True, True, False, True]


@pytest.mark.parametrize("m", [2, 3, 4])
def test_mask_matches_brute_force(m: int) -> None:
    rng = np.random.default_rng(m)
    f = rng.integers(0, 6, size=(60, m)).astype(float)  # many ties and duplicates
    np.testing.assert_array_equal(non_dominated_mask(f), _brute_force(f))


def test_single_objective_keeps_minima_only() -> None:
    assert non_dominated([[3.0], [1.0], [2.0], [1.0]]).ravel().tolist() == [1.0, 1.0]


@pytest.mark.parametrize("bad", [[1.0, 2.0], [[np.nan, 1.0]], np.empty((3, 0))])
def test_invalid_input(bad: object) -> None:
    with pytest.raises(ValueError):
        non_dominated_mask(bad)  # type: ignore[arg-type]
