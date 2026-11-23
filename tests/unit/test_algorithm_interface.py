"""Contract tests for the ask/tell Algorithm interface (using a test-only sampler)."""

from __future__ import annotations

import numpy as np
import pytest

from evooptlab.benchmarks import Sphere, TwoSpheres
from evooptlab.core.algorithm import Algorithm
from evooptlab.core.evaluator import Evaluator
from evooptlab.core.seeding import make_rng
from helpers import SingleObjectiveOnly, UniformSampler


def test_cannot_instantiate_abstract_base() -> None:
    with pytest.raises(TypeError):
        Algorithm()  # type: ignore[abstract]


def test_ask_respects_max_candidates() -> None:
    alg = UniformSampler(batch_size=10)
    alg.initialize(TwoSpheres(2).spec, make_rng(1))
    assert alg.ask(3).shape == (3, 2)


def test_ask_tell_loop_with_evaluator() -> None:
    problem = TwoSpheres(3)
    alg = UniformSampler(batch_size=4)
    alg.initialize(problem.spec, make_rng(1))
    ev = Evaluator(problem, budget=10)
    while not ev.exhausted:
        alg.tell(ev.evaluate(alg.ask(ev.remaining)))
    assert alg.n_told == 10
    assert alg.n_asks == 3  # 4 + 4 + 2


def test_state_dict_round_trip_resumes_identically() -> None:
    spec = Sphere(2).spec
    a = UniformSampler()
    a.initialize(spec, make_rng(5))
    a.ask(3)
    a._pending = None
    snapshot = a.state_dict()
    expected = a.ask(3)

    b = UniformSampler()
    b.initialize(spec, make_rng(999))
    b.load_state_dict(snapshot)
    np.testing.assert_array_equal(b.ask(3), expected)


def test_supports_objective_count() -> None:
    assert UniformSampler().supports(TwoSpheres(2).spec)
    assert SingleObjectiveOnly().supports(Sphere(2).spec)
    assert not SingleObjectiveOnly().supports(TwoSpheres(2).spec)


def test_parameters_are_recorded() -> None:
    assert UniformSampler(batch_size=3).parameters() == {"batch_size": 3}
