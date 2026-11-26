"""Invariants that every registered algorithm must satisfy (Phase 03 acceptance).

Each algorithm runs through the real ExperimentRunner on a smoke problem from its valid domain,
with a budget that is not a multiple of its batch size, so the final partial batch is exercised.
"""

from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from evooptlab.algorithms import ALGORITHMS, get_algorithm
from evooptlab.algorithms.pymoo_adapter import PymooAdapter
from evooptlab.benchmarks import ZDT1, ConstrainedSphere, Sphere, TwoSpheres
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.experiment import ExperimentRunner, RunResult, RunSpec
from evooptlab.core.problem import Problem
from evooptlab.core.seeding import make_rng
from evooptlab.storage import ArtifactLayout

pytestmark = pytest.mark.integration

BUDGET = 237  # deliberately not a multiple of any default population size
SO = ["random_search", "ga", "de", "pso", "optuna_tpe"]
MO = ["random_search", "nsga2", "gde3", "cmopso", "optuna_tpe"]
SMOKE: list[tuple[str, str]] = [(n, "so") for n in SO] + [(n, "mo") for n in MO]


def _problem(kind: str) -> Problem:
    """Smoke problem for a domain: 3-D Sphere (M = 1) or 4-D TwoSpheres (M = 2)."""
    return Sphere(3) if kind == "so" else TwoSpheres(4)


@pytest.fixture
def runner(tmp_path: Path) -> ExperimentRunner:
    return ExperimentRunner(ArtifactLayout(tmp_path))


def _run(
    runner: ExperimentRunner, name: str, problem: Problem, seed: int = 1, budget: int = BUDGET
) -> RunResult:
    return runner.run(problem, get_algorithm(name), RunSpec("pilot", seed=seed, budget=budget))


def _history(result: RunResult) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO((result.run_dir / "history.csv").read_text())))


def test_every_registered_algorithm_has_a_smoke_problem() -> None:
    assert {name for name, _ in SMOKE} == set(ALGORITHMS)


@pytest.mark.parametrize(("name", "kind"), SMOKE)
class TestRunInvariants:
    def test_completes_and_uses_budget_exactly(
        self, runner: ExperimentRunner, name: str, kind: str
    ) -> None:
        result = _run(runner, name, _problem(kind))
        assert result.outcome == "completed", result.metadata.failure_reason
        assert result.n_evaluations == BUDGET
        rows = _history(result)
        assert [int(r["evaluation_id"]) for r in rows] == list(range(BUDGET))
        metrics = json.loads((result.run_dir / "metrics.json").read_text())
        assert metrics["n_failed_evaluations"] == 0

    def test_candidates_stay_in_bounds(
        self, runner: ExperimentRunner, name: str, kind: str
    ) -> None:
        problem = _problem(kind)
        algorithm = get_algorithm(name)
        result = runner.run(problem, algorithm, RunSpec("pilot", seed=1, budget=BUDGET))
        rows = _history(result)
        x = np.array([[float(r[f"x_{i}"]) for i in range(problem.spec.n_variables)] for r in rows])
        assert np.all(x >= problem.spec.lower_bounds)
        assert np.all(x <= problem.spec.upper_bounds)
        if isinstance(algorithm, PymooAdapter):
            # ADR 0004: pymoo's own operators keep candidates in bounds; no clipping was needed.
            assert algorithm.n_repaired == 0

    def test_deterministic_and_independent_of_global_rng(
        self, runner: ExperimentRunner, name: str, kind: str
    ) -> None:
        np.random.seed(0)  # noqa: NPY002 - perturb legacy global state between runs
        a = _run(runner, name, _problem(kind), seed=7)
        np.random.seed(12345)  # noqa: NPY002
        b = _run(runner, name, _problem(kind), seed=7)
        c = _run(runner, name, _problem(kind), seed=8)
        history = "history.csv"
        assert (a.run_dir / history).read_bytes() == (b.run_dir / history).read_bytes()
        assert (a.run_dir / history).read_bytes() != (c.run_dir / history).read_bytes()

    def test_parameters_are_recorded(self, runner: ExperimentRunner, name: str, kind: str) -> None:
        import yaml

        result = _run(runner, name, _problem(kind), budget=20)
        config = yaml.safe_load((result.run_dir / "config.yaml").read_text())
        assert config["algorithm"]["name"] == name
        params = config["algorithm"]["parameters"]
        assert params == get_algorithm(name).parameters()
        if issubclass(ALGORITHMS[name], PymooAdapter):
            assert params["implementation"] == "pymoo==0.6.2"
            assert params["variant"]


@pytest.mark.parametrize("name", ["ga", "de", "pso"])
def test_single_objective_algorithms_reject_multi_objective(
    runner: ExperimentRunner, name: str
) -> None:
    with pytest.raises(AlgorithmError, match="does not support 2-objective"):
        _run(runner, name, TwoSpheres(2))


@pytest.mark.parametrize("name", ["nsga2", "gde3", "cmopso"])
def test_multi_objective_algorithms_reject_single_objective(
    runner: ExperimentRunner, name: str
) -> None:
    with pytest.raises(AlgorithmError, match="does not support 1-objective"):
        _run(runner, name, Sphere(2))


@pytest.mark.parametrize("name", ["random_search", "ga", "de", "pso", "optuna_tpe"])
def test_constrained_problem_runs(runner: ExperimentRunner, name: str) -> None:
    result = _run(runner, name, ConstrainedSphere(3), budget=300)
    assert result.outcome == "completed", result.metadata.failure_reason
    assert any(r["feasible"] == "True" for r in _history(result))


@pytest.mark.parametrize("name", sorted(set(ALGORITHMS) - {"random_search"}))
def test_state_dict_resume_reproduces_next_batch(name: str) -> None:
    problem = _problem("so" if name in SO else "mo")
    from evooptlab.core.evaluator import Evaluator

    alg = get_algorithm(name)
    alg.initialize(problem.spec, make_rng(3))
    ev = Evaluator(problem, budget=10_000)
    for _ in range(2):
        alg.tell(ev.evaluate(alg.ask(ev.remaining)))
    snapshot = alg.state_dict()
    expected = alg.ask(ev.remaining)

    other = get_algorithm(name)
    other.initialize(problem.spec, make_rng(999))
    other.load_state_dict(snapshot)
    np.testing.assert_array_equal(other.ask(ev.remaining), expected)


def test_final_partial_batch_ends_the_adapter() -> None:
    problem = TwoSpheres(2)
    alg = get_algorithm("nsga2", pop_size=10)
    alg.initialize(problem.spec, make_rng(1))
    from evooptlab.core.evaluator import Evaluator

    ev = Evaluator(problem, budget=15)
    alg.tell(ev.evaluate(alg.ask(ev.remaining)))
    partial = alg.ask(ev.remaining)
    assert partial.shape == (5, 2)
    alg.tell(ev.evaluate(partial))
    with pytest.raises(AlgorithmError, match="final partial batch"):
        alg.ask(1)


def test_adapter_contract_errors() -> None:
    alg = get_algorithm("nsga2")
    with pytest.raises(AlgorithmError, match="before initialize"):
        alg.ask(10)
    with pytest.raises(AlgorithmError, match="before initialize"):
        alg.state_dict()
    alg.initialize(TwoSpheres(2).spec, make_rng(1))
    with pytest.raises(AlgorithmError, match="without a pending"):
        alg.tell(None)  # type: ignore[arg-type]
    alg.ask(100)
    with pytest.raises(AlgorithmError, match="twice"):
        alg.ask(100)


def test_unknown_names_and_hyperparameters_fail_early() -> None:
    with pytest.raises(ValueError, match="unknown algorithm"):
        get_algorithm("mopso_cd")
    with pytest.raises(ValueError, match="unknown hyperparameters"):
        get_algorithm("nsga2", popsize=10)
    with pytest.raises(ValueError, match="batch_size"):
        get_algorithm("random_search", batch_size=0)


def test_guard_blocks_internal_pymoo_evaluation() -> None:
    from pymoo.core.evaluator import Evaluator as PymooEvaluator
    from pymoo.core.population import Population

    from evooptlab.algorithms.pymoo_adapter import _GuardProblem

    guard = _GuardProblem(TwoSpheres(2).spec)
    with pytest.raises(AlgorithmError, match="outside the ask/tell loop"):
        PymooEvaluator().eval(guard, Population.new(X=np.full((2, 2), 0.5)))


def test_adapters_optimize_better_than_random_search(runner: ExperimentRunner) -> None:
    """Wiring sanity check (fixed seed, framework test only, NOT a reported result).

    If objectives were told to pymoo in the wrong order or orientation, NSGA-II would not beat
    uniform sampling on ZDT1 at an equal budget.
    """
    from evooptlab.evaluation.quality import compute_quality

    def hv_ratio(name: str) -> Any:
        result = _run(runner, name, ZDT1(), seed=3, budget=3000)
        rows = _history(result)
        f = np.array([[float(r["f_0"]), float(r["f_1"])] for r in rows])
        feasible = np.array([r["feasible"] == "True" for r in rows])
        return compute_quality(f, feasible, ZDT1().pareto_front())["hypervolume_ratio"]

    assert hv_ratio("nsga2") > hv_ratio("random_search") + 0.1
