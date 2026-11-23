"""Tests for the (proposed) normalization and HV reference-point policy."""

from __future__ import annotations

import numpy as np
import pytest

from evooptlab.benchmarks import ZDT1
from evooptlab.evaluation.quality import (
    QualityPolicy,
    compute_quality,
    ideal_and_nadir,
    normalize,
)


class TestQualityPolicy:
    def test_normalization(self) -> None:
        ideal, nadir = ideal_and_nadir([[0, 10], [2, 0]])
        np.testing.assert_array_equal(normalize([[1, 5]], ideal, nadir), [[0.5, 0.5]])
        with pytest.raises(ValueError, match="degenerate"):
            ideal_and_nadir([[1, 1], [1, 2]])

    def test_front_itself_scores_ratio_one(self) -> None:
        z = ZDT1().pareto_front(200)
        q = compute_quality(z, np.ones(len(z), dtype=bool), z)
        assert q["hypervolume_ratio"] == pytest.approx(1.0)
        assert q["igd_plus"] == 0.0
        assert q["reference_point"] == [1.1, 1.1]
        assert q["policy"]["version"] == "proposed-v1"

    def test_infeasible_points_are_excluded(self) -> None:
        z = ZDT1().pareto_front(50)
        f = np.vstack([z, z - 0.5])  # the shifted copy would dominate the front
        feasible = np.r_[np.ones(50, dtype=bool), np.zeros(50, dtype=bool)]
        q = compute_quality(f, feasible, z)
        assert q["hypervolume_ratio"] == pytest.approx(1.0)
        assert q["feasibility_rate"] == 0.5

    def test_no_feasible_point_gives_none_not_zero(self) -> None:
        z = ZDT1().pareto_front(10)
        q = compute_quality(z, np.zeros(10, dtype=bool), z)
        assert q["hypervolume"] is None
        assert q["igd"] is None
        assert q["missing_reason"] == "no feasible point"

    def test_without_normalization(self) -> None:
        z = ZDT1().pareto_front(10)
        q = compute_quality(z, np.ones(10, dtype=bool), z, QualityPolicy(normalize=False))
        assert q["hypervolume_ratio"] == pytest.approx(1.0)

    def test_invalid_inputs(self) -> None:
        z = ZDT1().pareto_front(10)
        with pytest.raises(ValueError):
            QualityPolicy(reference_offset=0.0)
        with pytest.raises(ValueError, match="boolean vector"):
            compute_quality(z, np.ones(3, dtype=bool), z)
        with pytest.raises(ValueError, match="different dimensions"):
            compute_quality(z, np.ones(10, dtype=bool), np.zeros((4, 3)))
