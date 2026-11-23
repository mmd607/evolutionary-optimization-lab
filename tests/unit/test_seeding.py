"""Tests for deterministic seed derivation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from evooptlab.core.seeding import MAX_SEED, derive_run_seeds, derive_seed, make_rng


def test_derivation_is_deterministic() -> None:
    assert derive_seed(2026, "ZDT1", "nsga2", 3) == derive_seed(2026, "ZDT1", "nsga2", 3)


def test_derivation_regression_value() -> None:
    # Frozen value: changing the derivation scheme would silently change every stored run.
    assert derive_seed(2026, "ZDT1", "nsga2", 0) == 6738698115592139056


def test_keys_change_the_seed() -> None:
    base = derive_seed(2026, "ZDT1", "nsga2")
    assert derive_seed(2027, "ZDT1", "nsga2") != base
    assert derive_seed(2026, "ZDT2", "nsga2") != base
    assert derive_seed(2026, "nsga2", "ZDT1") != base  # order matters


def test_int_and_str_keys_differ() -> None:
    assert derive_seed(1, 1) != derive_seed(1, "1")


def test_seed_range() -> None:
    seeds = [derive_seed(s, "k") for s in range(500)]
    assert all(0 <= s <= MAX_SEED for s in seeds)


def test_run_seeds_are_prefix_stable_and_distinct() -> None:
    five = derive_run_seeds(2026, 5, "ZDT1", "nsga2")
    twenty = derive_run_seeds(2026, 20, "ZDT1", "nsga2")
    assert twenty[:5] == five
    assert len(set(twenty)) == 20
    assert derive_run_seeds(2026, 0) == []


def test_run_seeds_reject_negative_count() -> None:
    with pytest.raises(ValueError):
        derive_run_seeds(2026, -1)


@pytest.mark.parametrize("bad", [-1, MAX_SEED + 1])
def test_out_of_range_master_seed(bad: int) -> None:
    with pytest.raises(ValueError):
        derive_seed(bad)


@pytest.mark.parametrize("bad", [1.5, "7", True, None])
def test_non_int_master_seed(bad: Any) -> None:
    with pytest.raises(TypeError):
        derive_seed(bad)


@pytest.mark.parametrize("bad", [1.5, None, False, (1,)])
def test_invalid_keys(bad: Any) -> None:
    with pytest.raises(TypeError):
        derive_seed(1, bad)


def test_make_rng_reproducible_and_independent() -> None:
    a = make_rng(11).random(5)
    b = make_rng(11).random(5)
    c = make_rng(12).random(5)
    np.testing.assert_array_equal(a, b)
    assert not np.array_equal(a, c)


def test_make_rng_does_not_touch_global_state() -> None:
    np.random.seed(0)  # noqa: NPY002 - deliberately checking the legacy global state
    expected = np.random.random()  # noqa: NPY002
    np.random.seed(0)  # noqa: NPY002
    make_rng(5).random(100)
    assert np.random.random() == expected  # noqa: NPY002
