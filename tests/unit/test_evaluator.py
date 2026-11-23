"""Tests for budgeted evaluation: counters, budget limits, validation, constraints."""

from __future__ import annotations

import contextlib
from typing import Any

import numpy as np
import pytest

from evooptlab.benchmarks import ConstrainedSphere, Sphere, TwoSpheres
from evooptlab.core.errors import BudgetExhaustedError, CandidateError, ObjectiveError
from evooptlab.core.evaluator import Evaluator
from evooptlab.core.problem import FloatArray, Problem, ProblemOutput, ProblemSpec


class _Faulty(Problem):
    """Problem whose output can be corrupted on demand."""

    def __init__(self, mode: str, n_constraints: int = 0) -> None:
        super().__init__(
            ProblemSpec(
                name="faulty",
                lower_bounds=np.zeros(2),
                upper_bounds=np.ones(2),
                n_objectives=2,
                n_constraints=n_constraints,
            )
        )
        self.mode = mode

    def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
        n = candidates.shape[0]
        f: Any = np.zeros((n, 2))
        g: Any = np.zeros((n, self.spec.n_constraints)) if self.spec.n_constraints else None
        if self.mode == "raise":
            raise RuntimeError("simulator crashed")
        if self.mode == "nan":
            f[0, 0] = np.nan
        if self.mode == "shape":
            f = np.zeros((n, 3))
        if self.mode == "extra_constraints":
            g = np.zeros((n, 1))
        if self.mode == "missing_constraints":
            g = None
        if self.mode == "constraint_shape":
            g = np.zeros((n, 5))
        if self.mode == "constraint_nan":
            g[0, 0] = np.inf
        if self.mode == "mutate":
            candidates[0, 0] = 0.5  # must fail: inputs are read-only
        return ProblemOutput(objectives=f, constraints=g)


class TestBudget:
    def test_counter_and_ids(self) -> None:
        ev = Evaluator(TwoSpheres(2), budget=10)
        r1 = ev.evaluate(np.full((3, 2), 0.5))
        r2 = ev.evaluate(np.full((4, 2), 0.5))
        assert ev.n_evaluations == 7
        assert ev.remaining == 3
        assert r1.evaluation_ids.tolist() == [0, 1, 2]
        assert r2.evaluation_ids.tolist() == [3, 4, 5, 6]
        assert r2.n == 4

    def test_exact_budget_then_exhausted(self) -> None:
        ev = Evaluator(Sphere(2), budget=5)
        ev.evaluate(np.zeros((5, 2)))
        assert ev.exhausted
        with pytest.raises(BudgetExhaustedError):
            ev.evaluate(np.zeros((1, 2)))
        assert ev.n_evaluations == 5

    def test_oversized_batch_is_rejected_without_spending(self) -> None:
        ev = Evaluator(Sphere(2), budget=5)
        ev.evaluate(np.zeros((3, 2)))
        with pytest.raises(BudgetExhaustedError, match="exceeds remaining budget 2"):
            ev.evaluate(np.zeros((3, 2)))
        assert ev.n_evaluations == 3

    def test_budget_never_exceeded_under_random_batches(self) -> None:
        rng = np.random.default_rng(0)
        ev = Evaluator(Sphere(2), budget=97)
        for _ in range(200):
            k = int(rng.integers(1, 15))
            with contextlib.suppress(BudgetExhaustedError):
                ev.evaluate(rng.uniform(-5, 5, size=(k, 2)))
            assert ev.n_evaluations <= ev.budget
        assert ev.n_evaluations <= 97

    @pytest.mark.parametrize("budget", [0, -1, 2.5, True])
    def test_invalid_budget(self, budget: Any) -> None:
        with pytest.raises(ValueError):
            Evaluator(Sphere(2), budget=budget)


class TestValidation:
    def test_invalid_candidates_do_not_consume_budget(self) -> None:
        ev = Evaluator(Sphere(2), budget=5)
        with pytest.raises(CandidateError):
            ev.evaluate(np.full((2, 2), 6.0))
        with pytest.raises(CandidateError):
            ev.evaluate(np.zeros((2, 3)))
        assert ev.n_evaluations == 0

    @pytest.mark.parametrize(
        ("mode", "n_constraints", "match"),
        [
            ("raise", 0, "evaluation raised"),
            ("nan", 0, "objectives contain NaN"),
            ("shape", 0, "objectives must have shape"),
            ("extra_constraints", 0, "declares none"),
            ("missing_constraints", 1, "returned none"),
            ("constraint_shape", 1, "constraints must have shape"),
            ("constraint_nan", 1, "constraints contain NaN"),
            ("mutate", 0, "evaluation raised"),
        ],
    )
    def test_faulty_output_counts_as_spent(self, mode: str, n_constraints: int, match: str) -> None:
        ev = Evaluator(_Faulty(mode, n_constraints), budget=10)
        with pytest.raises(ObjectiveError, match=match):
            ev.evaluate(np.full((2, 2), 0.5))
        assert ev.n_evaluations == 2
        assert ev.n_failed_evaluations == 2

    def test_caller_array_is_not_aliased(self) -> None:
        ev = Evaluator(Sphere(2), budget=5)
        x = np.zeros((1, 2))
        result = ev.evaluate(x)
        x[0, 0] = 3.0
        assert result.candidates[0, 0] == 0.0

    def test_result_arrays_are_read_only(self) -> None:
        result = Evaluator(ConstrainedSphere(2), budget=5).evaluate(np.full((2, 2), 0.5))
        for array in (result.candidates, result.objectives, result.constraint_violation):
            with pytest.raises(ValueError):
                array[0] = 1.0
        assert result.constraints is not None
        assert not result.feasible.flags.writeable


class TestConstraints:
    def test_violation_and_feasibility(self) -> None:
        ev = Evaluator(ConstrainedSphere(2), budget=10)
        r = ev.evaluate(np.array([[0.5, 0.5], [0.1, 0.1], [1.0, 1.0]]))
        np.testing.assert_allclose(r.constraint_violation, [0.0, 0.8, 0.0])
        assert r.feasible.tolist() == [True, False, True]

    def test_unconstrained_is_always_feasible(self) -> None:
        r = Evaluator(TwoSpheres(2), budget=3).evaluate(np.full((3, 2), 0.3))
        assert r.constraints is None
        assert r.feasible.all()
        assert np.all(r.constraint_violation == 0.0)


def test_timing_is_accumulated() -> None:
    ev = Evaluator(Sphere(2), budget=10)
    r = ev.evaluate(np.zeros((2, 2)))
    assert r.elapsed_seconds >= 0.0
    assert ev.evaluation_seconds >= r.elapsed_seconds
    assert ev.spec.name == "sphere"
