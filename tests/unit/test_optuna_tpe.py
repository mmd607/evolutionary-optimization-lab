"""Optuna TPE adapter: contract errors, recorded settings, constraints and wiring."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import optuna
import pytest

from evooptlab.algorithms import OptunaTPE, get_algorithm
from evooptlab.benchmarks import ConstrainedSphere, Sphere, TwoSpheres
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.evaluator import Evaluator
from evooptlab.core.experiment import ExperimentRunner, RunSpec
from evooptlab.core.seeding import make_rng
from evooptlab.storage import ArtifactLayout


def test_asks_one_in_bounds_candidate_at_a_time() -> None:
    problem = Sphere(3)
    alg = OptunaTPE()
    alg.initialize(problem.spec, make_rng(1))
    ev = Evaluator(problem, budget=15)
    while not ev.exhausted:
        x = alg.ask(ev.remaining)
        assert x.shape == (1, 3)
        assert np.all((x >= problem.spec.lower_bounds) & (x <= problem.spec.upper_bounds))
        alg.tell(ev.evaluate(x))


def test_contract_errors() -> None:
    alg = OptunaTPE()
    with pytest.raises(AlgorithmError, match="before initialize"):
        alg.ask(1)
    with pytest.raises(AlgorithmError, match="before initialize"):
        alg.state_dict()
    with pytest.raises(AlgorithmError, match="before initialize"):
        alg.tell(None)  # type: ignore[arg-type]
    problem = Sphere(2)
    alg.initialize(problem.spec, make_rng(1))
    with pytest.raises(AlgorithmError, match="without a pending"):
        alg.tell(None)  # type: ignore[arg-type]
    with pytest.raises(AlgorithmError, match="max_candidates"):
        alg.ask(0)
    x = alg.ask(5)
    with pytest.raises(AlgorithmError, match="twice"):
        alg.ask(5)
    ev = Evaluator(problem, budget=5)
    with pytest.raises(AlgorithmError, match="expected 1"):
        alg.tell(ev.evaluate(np.vstack([x, x])))


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [({"n_startup_trials": -1}, "n_startup_trials"), ({"n_ei_candidates": 0}, "n_ei_candidates")],
)
def test_invalid_settings(kwargs: dict[str, Any], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        OptunaTPE(**kwargs)
    with pytest.raises(TypeError):
        get_algorithm("optuna_tpe", popsize=3)


def test_parameters_record_the_library_version() -> None:
    params = OptunaTPE().parameters()
    assert params["implementation"] == f"optuna=={optuna.__version__}"
    assert (params["n_startup_trials"], params["n_ei_candidates"]) == (10, 24)


def test_constraints_reach_optuna() -> None:
    problem = ConstrainedSphere(2)
    alg = OptunaTPE(n_startup_trials=3)
    alg.initialize(problem.spec, make_rng(2))
    ev = Evaluator(problem, budget=6)
    while not ev.exhausted:
        alg.tell(ev.evaluate(alg.ask(ev.remaining)))
    assert alg._study is not None
    trials = alg._study.trials
    assert all(len(t.constraints) == problem.spec.n_constraints for t in trials)


def test_multi_objective_study_has_one_direction_per_objective() -> None:
    alg = OptunaTPE()
    alg.initialize(TwoSpheres(2).spec, make_rng(1))
    assert alg._study is not None
    assert len(alg._study.directions) == 2


def test_beats_random_search_on_sphere_at_equal_budget(tmp_path: Path) -> None:
    """Wiring sanity check (fixed seeds, framework test only, NOT a reported result)."""
    runner = ExperimentRunner(ArtifactLayout(tmp_path))
    best = {}
    for name in ("optuna_tpe", "random_search"):
        result = runner.run(Sphere(3), get_algorithm(name), RunSpec("pilot", seed=5, budget=80))
        rows = (result.run_dir / "history.csv").read_text(encoding="utf-8").splitlines()[1:]
        best[name] = min(float(r.split(",")[5]) for r in rows)
    assert best["optuna_tpe"] < best["random_search"]
