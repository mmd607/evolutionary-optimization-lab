"""Unit tests for RandomSearch and the pymoo adapter's edge paths (repair, empty batches)."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from evooptlab.algorithms import NSGA2, RandomSearch
from evooptlab.benchmarks import TwoSpheres
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import Evaluator
from evooptlab.core.seeding import make_rng


class TestRandomSearch:
    def test_samples_uniformly_inside_bounds(self) -> None:
        spec = TwoSpheres(3).spec
        alg = RandomSearch(batch_size=500)
        alg.initialize(spec, make_rng(0))
        x = alg.ask(10_000)
        assert x.shape == (500, 3)
        assert np.all((x >= 0) & (x <= 1))
        assert abs(float(x.mean()) - 0.5) < 0.05

    def test_contract_errors(self) -> None:
        alg = RandomSearch()
        for call in (lambda: alg.ask(1), alg.state_dict, lambda: alg.load_state_dict({})):
            with pytest.raises(AlgorithmError, match="before initialize"):
                call()
        problem = TwoSpheres(2)
        alg.initialize(problem.spec, make_rng(0))
        x = alg.ask(3)
        wrong = Evaluator(problem, 10).evaluate(x[:2])
        with pytest.raises(AlgorithmError, match="does not match"):
            alg.tell(wrong)

    def test_state_round_trip(self) -> None:
        spec = TwoSpheres(2).spec
        a = RandomSearch(4)
        a.initialize(spec, make_rng(1))
        snapshot = a.state_dict()
        expected = a.ask(4)
        b = RandomSearch(4)
        b.initialize(spec, make_rng(2))
        b.load_state_dict(snapshot)
        np.testing.assert_array_equal(b.ask(4), expected)


class _FakePop:
    """Minimal stand-in for a pymoo Population used to drive adapter edge paths."""

    def __init__(self, x: np.ndarray[Any, Any]) -> None:
        self.data = {"X": x}

    def __len__(self) -> int:
        return len(self.data["X"])

    def get(self, key: str) -> Any:
        return self.data[key]

    def set(self, key: str, value: Any) -> None:
        self.data[key] = value


def _adapter_returning(pop: Any) -> NSGA2:
    alg = NSGA2(pop_size=4)
    alg.initialize(TwoSpheres(2).spec, make_rng(0))
    assert alg._alg is not None
    alg._alg.ask = lambda: pop
    return alg


def test_out_of_bounds_candidates_are_clipped_and_counted() -> None:
    pop = _FakePop(np.array([[1.5, 0.5], [0.2, -0.1], [0.3, 0.3]]))
    alg = _adapter_returning(pop)
    x = alg.ask(10)
    np.testing.assert_array_equal(x, [[1.0, 0.5], [0.2, 0.0], [0.3, 0.3]])
    np.testing.assert_array_equal(pop.get("X"), x)  # pymoo's view is updated too
    assert alg.n_repaired == 2


@pytest.mark.parametrize("pop", [None, _FakePop(np.empty((0, 2)))])
def test_empty_pymoo_batch_is_an_error(pop: Any) -> None:
    with pytest.raises(AlgorithmError, match="no candidates"):
        _adapter_returning(pop).ask(10)


def test_tell_size_mismatch_is_an_error() -> None:
    problem = TwoSpheres(2)
    alg = NSGA2(pop_size=4)
    alg.initialize(problem.spec, make_rng(0))
    x = alg.ask(10)
    with pytest.raises(AlgorithmError, match="does not match"):
        alg.tell(Evaluator(problem, 10).evaluate(x[:2]))
