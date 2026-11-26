"""Statistical building blocks against scipy and hand-computed reference values."""

from __future__ import annotations

import numpy as np
import pytest
from scipy import stats as sps

from evooptlab.analysis.stats import (
    bootstrap_ci,
    friedman,
    holm,
    mean_ranks,
    vargha_delaney_a12,
    wilcoxon_paired,
)


class TestA12:
    def test_hand_computed(self) -> None:
        # x better (smaller) than y in 3 of 4 pairs, one tie: (3 + 0.5) / 4
        assert vargha_delaney_a12([1, 2], [2, 3], "minimize") == pytest.approx(3.5 / 4)
        assert vargha_delaney_a12([1, 2], [2, 3], "maximize") == pytest.approx(0.5 / 4)
        assert vargha_delaney_a12([5, 5], [5, 5], "minimize") == 0.5

    def test_equals_mann_whitney_u_over_nm(self) -> None:
        rng = np.random.default_rng(1)
        x, y = np.round(rng.normal(size=12), 1), np.round(rng.normal(0.3, size=9), 1)
        u = sps.mannwhitneyu(x, y).statistic  # counts x > y plus half ties
        assert vargha_delaney_a12(x, y, "maximize") == pytest.approx(u / (x.size * y.size))
        assert vargha_delaney_a12(x, y, "minimize") == pytest.approx(
            1 - vargha_delaney_a12(x, y, "maximize")
        )

    def test_rejects_empty_and_missing_values(self) -> None:
        with pytest.raises(ValueError, match="non-empty"):
            vargha_delaney_a12([], [1.0], "minimize")
        with pytest.raises(ValueError, match="finite"):
            vargha_delaney_a12([float("nan")], [1.0], "minimize")


class TestWilcoxon:
    def test_matches_scipy(self) -> None:
        rng = np.random.default_rng(2)
        x = rng.normal(size=15)
        y = x + rng.normal(0.4, 0.5, size=15)
        ours = wilcoxon_paired(x, y)
        ref = sps.wilcoxon(x, y)
        assert ours.statistic == pytest.approx(ref.statistic)
        assert ours.p_value == pytest.approx(ref.pvalue)
        assert ours.n_pairs == ours.n_nonzero == 15

    def test_degenerate_cases_are_explicit(self) -> None:
        assert wilcoxon_paired([], []).note == "no complete pairs"
        same = wilcoxon_paired([1.0, 2.0], [1.0, 2.0])
        assert same.p_value is None and same.note == "all paired differences are zero"
        with pytest.raises(ValueError, match="same length"):
            wilcoxon_paired([1.0], [1.0, 2.0])


class TestHolm:
    def test_hand_computed_step_down(self) -> None:
        # sorted p: 0.01 (x3 = 0.03), 0.02 (x2 = 0.04), 0.04 (x1 = 0.04)
        assert holm([0.04, 0.01, 0.02]) == pytest.approx([0.04, 0.03, 0.04])

    def test_monotone_capped_and_skips_missing(self) -> None:
        adjusted = holm([0.5, None, 0.4, 0.001])
        assert adjusted[1] is None
        # sorted: 0.001 x 3 = 0.003; 0.4 x 2 = 0.8; 0.5 x 1 = 0.5 -> raised to 0.8 (monotone)
        assert adjusted == pytest.approx([0.8, None, 0.8, 0.003])
        assert holm([0.6, 0.9]) == pytest.approx([1.0, 1.0])  # capped at 1
        with pytest.raises(ValueError):
            holm([1.5])


class TestFriedman:
    def test_matches_scipy_and_ranks_follow_direction(self) -> None:
        blocks = np.array([[1.0, 2.0, 3.0], [1.5, 2.5, 2.0], [0.5, 3.0, 2.8], [1.0, 1.0, 4.0]])
        result = friedman(blocks, "minimize")
        ref = sps.friedmanchisquare(*blocks.T)
        assert result.statistic == pytest.approx(ref.statistic)
        assert result.p_value == pytest.approx(ref.pvalue)
        # per-block ranks (1 = smallest): (1,2,3), (1,3,2), (1,3,2), (1.5,1.5,3)
        assert result.mean_ranks == pytest.approx([1.125, 2.375, 2.5])
        assert mean_ranks(blocks, "maximize") == pytest.approx([2.875, 1.625, 1.5])

    def test_not_run_cases(self) -> None:
        assert friedman(np.ones((3, 2)), "minimize").note == "Friedman needs at least 3 algorithms"
        assert friedman(np.ones((1, 3)), "minimize").note == "Friedman needs at least 2 blocks"
        assert friedman(np.ones((3, 3)), "minimize").note == "all algorithms tie in every block"
        with pytest.raises(ValueError):
            friedman(np.array([[1.0, np.nan, 2.0]]), "minimize")


class TestBootstrap:
    def test_reproducible_and_brackets_the_statistic(self) -> None:
        values = np.random.default_rng(3).normal(size=25)
        kw = {"statistic": "median", "level": 0.95, "n_resamples": 2000, "seed": 7}
        a = bootstrap_ci(values, **kw)  # type: ignore[arg-type]
        b = bootstrap_ci(values, **kw)  # type: ignore[arg-type]
        assert a == b and a is not None
        assert a.low <= float(np.median(values)) <= a.high
        mean = bootstrap_ci(values, statistic="mean", level=0.9, n_resamples=2000, seed=7)
        assert mean is not None and mean.low < values.mean() < mean.high

    def test_degenerate_inputs(self) -> None:
        assert bootstrap_ci([1.0], statistic="median", level=0.95, n_resamples=100, seed=0) is None
        flat = bootstrap_ci([2.0] * 5, statistic="median", level=0.95, n_resamples=100, seed=0)
        assert flat is not None and flat.low == flat.high == 2.0
