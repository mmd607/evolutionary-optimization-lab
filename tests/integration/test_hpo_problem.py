"""HPO problem behaviour through the real runner: trials, failures, determinism, hashing."""

from __future__ import annotations

import csv
from pathlib import Path

import numpy as np
import pytest
import yaml

from evooptlab.algorithms import get_algorithm
from evooptlab.core.experiment import ExperimentRunner, RunSpec, canonical_hash
from evooptlab.hpo import HPOProblem, select_trial
from evooptlab.storage import ArtifactLayout
from hpo_helpers import SYNTHETIC, hpo_config, mixed_config, register_synthetic

pytestmark = pytest.mark.integration


def _rows(run_dir: Path) -> list[dict[str, str]]:
    return list(csv.DictReader((run_dir / "history.csv").read_text(encoding="utf-8").splitlines()))


def test_construction_needs_no_data_and_spec_is_the_unit_cube(tmp_path: Path) -> None:
    problem = HPOProblem(hpo_config(task="bank_marketing"), tmp_path / "nowhere")
    assert problem.spec.n_variables == 3
    assert np.all(problem.spec.lower_bounds == 0) and np.all(problem.spec.upper_bounds == 1)
    assert (problem.spec.n_objectives, problem.spec.n_constraints) == (1, 1)
    assert problem.audit is None  # nothing loaded yet


@pytest.mark.parametrize(
    ("overrides", "match"),
    [
        (
            {"task": "california_housing"},
            "supports \\['regression'\\]",
        ),
        ({"task": "wine_quality", "variant": None}, "variant must be one of"),
        ({"fixed_parameters": {"n_estimators": 10}}, "unknown hyperparameters"),
    ],
)
def test_invalid_problem_definitions(overrides: dict[str, object], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        HPOProblem(hpo_config(**overrides))


def test_runs_are_deterministic_and_describe_their_definition(tmp_path: Path) -> None:
    runner = ExperimentRunner(ArtifactLayout(tmp_path))
    histories, configs = [], []
    for _ in range(2):
        result = runner.run(
            HPOProblem(hpo_config(), tmp_path),
            get_algorithm("optuna_tpe", n_startup_trials=2),
            RunSpec("pilot", seed=4, budget=5),
        )
        assert result.outcome == "completed", result.metadata.failure_reason
        histories.append((result.run_dir / "history.csv").read_bytes())
        configs.append(yaml.safe_load((result.run_dir / "config.yaml").read_text("utf-8")))
    assert histories[0] == histories[1]
    details = configs[0]["problem"]["details"]
    assert details["dataset_sha256"].startswith("25e2eb7b")
    assert details["split"]["random_seed"] == 2026
    assert details["search_space"]["max_iter"]["high"] == 10.0
    changed = HPOProblem(hpo_config(model_seed=1)).describe()
    assert canonical_hash(changed) != canonical_hash(HPOProblem(hpo_config()).describe())


def test_failed_trials_are_recorded_as_infeasible_and_never_selected(tmp_path: Path) -> None:
    # max_leaf_nodes must be >= 2 in scikit-learn; the decoded value 1 makes some fits raise.
    space = {"max_leaf_nodes": {"type": "int", "low": 1, "high": 3}}
    problem = HPOProblem(hpo_config(search_space=space), tmp_path)
    out = problem.evaluate_batch(np.array([[0.0], [1.0]]))
    assert out.constraints is not None
    assert out.constraints[:, 0].tolist() == [1.0, 0.0]
    assert out.objectives[0, 0] == 1.0  # worst possible macro-F1 error
    assert out.objectives[1, 0] < 1.0

    result = ExperimentRunner(ArtifactLayout(tmp_path)).run(
        problem, get_algorithm("random_search", batch_size=4), RunSpec("pilot", seed=1, budget=8)
    )
    assert result.outcome == "completed"
    rows = _rows(result.run_dir)
    assert {r["feasible"] for r in rows} == {"True", "False"}
    chosen = select_trial(rows)
    assert chosen is not None and chosen["feasible"] == "True"


def test_select_trial_breaks_ties_by_earliest_and_handles_no_success() -> None:
    rows = [
        {"evaluation_id": "0", "f_0": "0.2", "feasible": "True"},
        {"evaluation_id": "1", "f_0": "0.1", "feasible": "False"},
        {"evaluation_id": "2", "f_0": "0.2", "feasible": "True"},
    ]
    assert select_trial(rows) == rows[0]
    assert select_trial([rows[1]]) is None


def test_regression_failed_trials_use_the_mean_predictor_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from dataclasses import replace

    register_synthetic(monkeypatch, replace(SYNTHETIC, task_types=("regression",)))
    config = mixed_config(
        task_type="regression",
        target_metric="neg_root_mean_squared_error",
        search_space={"max_leaf_nodes": {"type": "int", "low": 1, "high": 3}},
    )
    problem = HPOProblem(config, tmp_path)
    out = problem.evaluate_batch(np.array([[0.0]]))
    assert out.constraints is not None and out.constraints[0, 0] == 1.0
    assert out.objectives[0, 0] == pytest.approx(problem._worst_error)
    assert 0.0 < problem._worst_error < 1.0  # std of a 0/1 target


def test_two_objective_hpo_runs_with_multi_objective_algorithms(tmp_path: Path) -> None:
    config = hpo_config(objectives=["validation_error", "fit_seconds"])
    runner = ExperimentRunner(ArtifactLayout(tmp_path))
    for name, params in (("nsga2", {"pop_size": 4}), ("optuna_tpe", {"n_startup_trials": 2})):
        result = runner.run(
            HPOProblem(config, tmp_path),
            get_algorithm(name, **params),
            RunSpec("pilot", seed=2, budget=6),
        )
        assert result.outcome == "completed", result.metadata.failure_reason
        rows = _rows(result.run_dir)
        assert len(rows) == 6 and all(float(r["f_1"]) > 0 for r in rows)


def test_study_with_missing_data_stops_before_any_run(tmp_path: Path) -> None:
    from evooptlab.config.schemas import StudyConfig
    from evooptlab.experiments import StudyError, build_matrix, run_study

    study = StudyConfig.model_validate(
        {
            "name": "hpo-missing",
            "stage": "pilot",
            "output_dir": "x",
            "problems": [hpo_config(task="bank_marketing").model_dump(mode="json")],
            "algorithms": [{"name": "random_search"}],
            "budget": {"unit": "objective_evaluations", "max_evaluations": 2},
            "seeds": {"policy": "explicit", "values": [1]},
            "data_dir": str(tmp_path / "empty"),
        }
    )
    assert study.is_hpo
    assert [c.data_dir for c in build_matrix(study)] == [tmp_path / "empty"]
    layout = ArtifactLayout(tmp_path / "artifacts")
    with pytest.raises(StudyError, match="raw file missing"):
        run_study(study, layout)
    assert not layout.stage_dir("pilot").exists()  # nothing recorded as a (failed) result
