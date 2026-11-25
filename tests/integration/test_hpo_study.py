"""HPO studies end to end: run -> test-eval -> diagnose -> aggregate, through the CLI and API."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from evooptlab.cli import main
from evooptlab.config.schemas import StudyConfig
from evooptlab.experiments import (
    collect_study,
    diagnose,
    evaluate_study_on_test,
    read_test_evaluations,
    run_study,
    write_aggregate,
)
from evooptlab.experiments.records import held_out_path
from evooptlab.storage import ArtifactLayout
from hpo_helpers import hpo_config

pytestmark = pytest.mark.integration


def hpo_study(**overrides: Any) -> StudyConfig:
    base: dict[str, Any] = {
        "name": "hpo-tiny",
        "stage": "pilot",
        "output_dir": "unused",
        "problems": [hpo_config().model_dump(mode="json")],
        "algorithms": [
            {"name": "random_search", "parameters": {"batch_size": 3}},
            {"name": "optuna_tpe", "parameters": {"n_startup_trials": 2}},
        ],
        "budget": {"unit": "objective_evaluations", "max_evaluations": 5},
        "seeds": {"policy": "explicit", "values": [1]},
    }
    base.update(overrides)
    return StudyConfig.model_validate(base)


def _status(collection: Any) -> dict[str, str]:
    return {c.name: c.status for c in diagnose(collection).checks}


@pytest.fixture
def layout(tmp_path: Path) -> ArtifactLayout:
    layout = ArtifactLayout(tmp_path / "artifacts")
    run_study(hpo_study(), layout, data_dir=tmp_path)
    return layout


def test_study_rejects_mixing_benchmarks_and_hpo() -> None:
    with pytest.raises(ValueError, match="either all benchmark problems or all HPO"):
        hpo_study(
            problems=[
                hpo_config().model_dump(mode="json"),
                {"name": "ZDT1", "objectives": 2, "variables": 4},
            ]
        )


def test_test_evaluation_is_written_once_and_never_recomputed(layout: ArtifactLayout) -> None:
    collection = collect_study(hpo_study(), layout)
    assert _status(collection)["test_evaluations"] == "WARN"  # pilot: not evaluated yet

    report = evaluate_study_on_test(collection, layout)
    assert len(report.evaluated) == 2 and not report.skipped
    stored = read_test_evaluations(layout, "pilot")
    run_id = report.evaluated[0]
    first = held_out_path(layout, "pilot", run_id).read_bytes()
    record = collection.canonical[("bc-tiny", "random_search", 0)]
    assert stored[record.run_id]["config_hash"] == record.metadata.config_hash
    assert 0.0 < stored[record.run_id]["test"]["test_score"] <= 1.0

    again = evaluate_study_on_test(collect_study(hpo_study(), layout), layout)
    assert sorted(again.skipped) == sorted(report.evaluated) and not again.evaluated
    assert held_out_path(layout, "pilot", run_id).read_bytes() == first

    status = _status(collect_study(hpo_study(), layout))
    assert status["test_evaluations"] == "PASS"
    assert status["failed_trials"] == "PASS"


def test_inconsistent_test_evaluations_fail_diagnostics(layout: ArtifactLayout) -> None:
    evaluate_study_on_test(collect_study(hpo_study(), layout), layout)
    collection = collect_study(hpo_study(), layout)
    run_id = next(iter(collection.test_evaluations))
    path = held_out_path(layout, "pilot", run_id)
    data = json.loads(path.read_text(encoding="utf-8"))
    data["selected_evaluation_id"] = 4 if data["selected_evaluation_id"] != 4 else 3
    path.write_text(json.dumps(data), encoding="utf-8")
    collection = collect_study(hpo_study(), layout)
    check = next(c for c in diagnose(collection).checks if c.name == "test_evaluations")
    assert check.status == "FAIL" and "validation-best" in check.details[0]

    path.write_text("{not json", encoding="utf-8")
    check = next(
        c
        for c in diagnose(collect_study(hpo_study(), layout)).checks
        if c.name == "test_evaluations"
    )
    assert check.status == "FAIL" and "unreadable" in check.details[0]


def test_missing_test_evaluations_fail_in_final_stage(layout: ArtifactLayout) -> None:
    collection = collect_study(hpo_study(), layout)
    collection.study = hpo_study(stage="final")
    check = next(c for c in diagnose(collection).checks if c.name == "test_evaluations")
    assert check.status == "FAIL"


def test_benchmark_studies_have_no_hpo_checks() -> None:
    from evooptlab.experiments import StudyCollection
    from study_helpers import make_study

    names = {c.name for c in diagnose(StudyCollection(make_study(), cells=[])).checks}
    assert not names & {"test_evaluations", "failed_trials"}


def test_aggregate_reports_selection_and_test_scores(
    layout: ArtifactLayout, tmp_path: Path
) -> None:
    collection = collect_study(hpo_study(), layout)
    out = write_aggregate(collection, diagnose(collection), tmp_path / "before")
    rows = list(csv.DictReader((out / "runs.csv").read_text(encoding="utf-8").splitlines()))
    assert {r["missing_reason"] for r in rows} == {"test evaluation not run"}
    assert all(r["best_validation_error"] for r in rows)
    assert "hypervolume" not in rows[0]

    evaluate_study_on_test(collection, layout)
    collection = collect_study(hpo_study(), layout)
    out = write_aggregate(collection, diagnose(collection), tmp_path / "after")
    rows = list(csv.DictReader((out / "runs.csv").read_text(encoding="utf-8").splitlines()))
    stored = read_test_evaluations(layout, "pilot")
    for row in rows:
        test = stored[row["run_id"]]["test"]
        assert float(row["test_score"]) == test["test_score"]
        assert json.loads(row["hyperparameters"]) == test["hyperparameters"]
        assert row["target_metric"] == "f1_macro" and row["missing_reason"] == ""
        assert int(row["n_trials"]) == 5
    summary = list(csv.DictReader((out / "summary.csv").read_text(encoding="utf-8").splitlines()))
    assert {s["test_error__n"] for s in summary} == {"1"}
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["quality_policy"] is None
    assert manifest["hpo_selection_rule"].startswith("lowest validation_error")


def test_failed_runs_are_not_test_evaluated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evooptlab.experiments import RunCell
    from study_helpers import Exploding, builder_replacing

    layout = ArtifactLayout(tmp_path / "a")
    target = ("bc-tiny", "random_search", 0)
    monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Exploding))
    run_study(hpo_study(), layout, data_dir=tmp_path)
    collection = collect_study(hpo_study(), layout)
    report = evaluate_study_on_test(collection, layout)
    assert len(report.evaluated) == 1
    out = write_aggregate(collection, diagnose(collection), tmp_path / "agg")
    rows = list(csv.DictReader((out / "runs.csv").read_text(encoding="utf-8").splitlines()))
    failed = next(r for r in rows if r["outcome"] == "failed")
    assert failed["missing_reason"].startswith("run failed") and failed["test_score"] == ""


def test_cli_command_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    study_file = tmp_path / "hpo.yaml"
    study = hpo_study(data_dir=str(tmp_path / "data")).model_dump(mode="json")
    study_file.write_text(yaml.safe_dump({"study": study}, sort_keys=False), encoding="utf-8")
    common = [str(study_file), "--root", str(tmp_path / "artifacts")]

    assert main(["run", *common]) == 0
    assert main(["test-eval", *common]) == 0
    assert "evaluated 2, already evaluated 0" in capsys.readouterr().out
    assert main(["test-eval", *common]) == 0
    assert "evaluated 0, already evaluated 2" in capsys.readouterr().out
    assert main(["diagnose", *common]) == 0
    assert "PASS  test_evaluations" in capsys.readouterr().out
    assert main(["aggregate", *common, "--output", str(tmp_path / "agg")]) == 0
    capsys.readouterr()

    benchmark = tmp_path / "bench.yaml"
    from study_helpers import make_study

    benchmark.write_text(
        yaml.safe_dump({"study": make_study().model_dump(mode="json")}), encoding="utf-8"
    )
    assert main(["test-eval", str(benchmark), "--root", str(tmp_path / "b")]) == 2
    assert "no HPO problems" in capsys.readouterr().err


def test_cli_data_commands(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["data", "fetch", "breast_cancer_smoke", "--data-dir", str(tmp_path)]) == 0
    assert "bundled with scikit-learn" in capsys.readouterr().out
    assert main(["data", "info", "--data-dir", str(tmp_path)]) == 0
    records = json.loads(capsys.readouterr().out)
    assert {r["task"] for r in records} >= {"bank_marketing", "california_housing"}
    bank = next(r for r in records if r["task"] == "bank_marketing")
    assert bank["cached"] is False and bank["source"]["sha256"].startswith("e0bf5f5d")
    assert main(["data", "info", "iris"]) == 2
    assert "unknown HPO task" in capsys.readouterr().err


def test_runs_without_a_successful_trial_are_reported_not_scored(tmp_path: Path) -> None:
    # max_leaf_nodes < 2 always raises in scikit-learn, so every trial fails.
    failing = hpo_config(search_space={"max_leaf_nodes": {"type": "int", "low": 0, "high": 1}})
    study = hpo_study(problems=[failing.model_dump(mode="json")])
    layout = ArtifactLayout(tmp_path / "a")
    run_study(study, layout, data_dir=tmp_path)
    collection = collect_study(study, layout)
    assert _status(collection)["failed_trials"] == "WARN"
    report = evaluate_study_on_test(collection, layout)
    assert len(report.no_successful_trial) == 2 and not report.evaluated
    collection = collect_study(study, layout)
    assert _status(collection)["test_evaluations"] == "PASS"
    out = write_aggregate(collection, diagnose(collection), tmp_path / "agg")
    rows = list(csv.DictReader((out / "runs.csv").read_text(encoding="utf-8").splitlines()))
    assert {r["missing_reason"] for r in rows} == {"no successful trial"}
    assert {r["n_failed_trials"] for r in rows} == {"5"}


def test_test_eval_reports_missing_data_as_a_study_error(
    layout: ArtifactLayout, tmp_path: Path
) -> None:
    from evooptlab.experiments import StudyError

    study = hpo_study(problems=[hpo_config(task="bank_marketing").model_dump(mode="json")])
    bank_layout = ArtifactLayout(tmp_path / "bank")
    collection = collect_study(study, bank_layout, tmp_path / "empty")
    # Both studies name their problem "bc-tiny", so the completed breast-cancer runs stand in
    # for bank cells whose data were never fetched.
    collection.canonical = dict(collect_study(hpo_study(), layout).canonical)
    with pytest.raises(StudyError, match="raw file missing"):
        evaluate_study_on_test(collection, bank_layout)
