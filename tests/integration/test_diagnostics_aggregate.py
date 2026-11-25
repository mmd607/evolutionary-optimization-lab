"""Diagnostics detect tampered or unfair artifacts; aggregation scores runs from disk only."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from evooptlab.benchmarks import ZDT1
from evooptlab.config.schemas import StudyConfig
from evooptlab.core.experiment import ExperimentRunner
from evooptlab.evaluation.quality import compute_quality
from evooptlab.experiments import (
    RunCell,
    StudyCollection,
    StudyError,
    build_matrix,
    collect_study,
    diagnose,
    projected_seconds,
    run_spec,
    run_study,
    write_aggregate,
)
from evooptlab.experiments.aggregate import _describe, to_csv
from evooptlab.experiments.records import history_objectives
from evooptlab.storage import ArtifactLayout
from study_helpers import BUDGET, Exploding, builder_replacing, make_study

pytestmark = pytest.mark.integration


@pytest.fixture
def layout(tmp_path: Path) -> ArtifactLayout:
    layout = ArtifactLayout(tmp_path / "artifacts")
    run_study(make_study(), layout)
    return layout


def _read_csv(path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(path.read_text(encoding="utf-8").splitlines()))


def _status(collection: StudyCollection) -> dict[str, str]:
    return {c.name: c.status for c in diagnose(collection).checks}


def _first(layout: ArtifactLayout, study: StudyConfig | None = None) -> Path:
    collection = collect_study(study or make_study(), layout)
    return collection.canonical[("ZDT1", "nsga2", 0)].run_dir


class TestDiagnostics:
    def test_clean_pilot_passes_every_integrity_check(self, layout: ArtifactLayout) -> None:
        status = _status(collect_study(make_study(), layout))
        for name in (
            "coverage",
            "failed_runs",
            "budget_exact",
            "history_integrity",
            "config_integrity",
            "paired_seeds",
            "stray_runs",
            "failed_evaluations",
        ):
            assert status[name] == "PASS", name
        assert status["environment"] in {"PASS", "WARN"}  # dirty tree during development

    def test_truncated_history_fails(self, layout: ArtifactLayout) -> None:
        path = _first(layout) / "history.csv"
        lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
        path.write_text("".join(lines[:-1]), encoding="utf-8")
        assert _status(collect_study(make_study(), layout))["history_integrity"] == "FAIL"

    def test_edited_config_fails(self, layout: ArtifactLayout) -> None:
        path = _first(layout) / "config.yaml"
        path.write_text(path.read_text(encoding="utf-8").replace("pop_size: 8", "pop_size: 9"))
        report = diagnose(collect_study(make_study(), layout))
        assert {c.name: c.status for c in report.checks}["config_integrity"] == "FAIL"
        assert report.status == "FAIL"

    def test_budget_mismatch_fails(self, layout: ArtifactLayout) -> None:
        path = _first(layout) / "metrics.json"
        metrics = json.loads(path.read_text(encoding="utf-8"))
        metrics["n_evaluations"] = BUDGET - 1
        path.write_text(json.dumps(metrics), encoding="utf-8")
        assert _status(collect_study(make_study(), layout))["budget_exact"] == "FAIL"

    def test_unpaired_seeds_fail(self, layout: ArtifactLayout) -> None:
        path = _first(layout) / "run_metadata.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["seed"] = 999
        path.write_text(json.dumps(data), encoding="utf-8")
        assert _status(collect_study(make_study(), layout))["paired_seeds"] == "FAIL"

    def test_missing_cells_warn_in_pilot_and_fail_in_final(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        run_study(make_study(seeds={"policy": "explicit", "values": [1]}), layout)
        collection = collect_study(make_study(), layout)
        assert len(collection.missing) == 4
        assert _status(collection)["coverage"] == "WARN"
        final = StudyCollection(
            study=make_study(stage="final"), cells=collection.cells, canonical={}
        )
        assert _status(final)["coverage"] == "FAIL"

    def test_duplicates_unplanned_and_unreadable_items_are_reported(
        self, layout: ArtifactLayout
    ) -> None:
        study = make_study()
        cell = build_matrix(study)[0]
        runner = ExperimentRunner(layout)
        duplicate = runner.run(cell.build_problem(), cell.build_algorithm(), run_spec(study, cell))
        other = make_study(budget={"unit": "objective_evaluations", "max_evaluations": 20})
        other_cell = build_matrix(other)[0]
        unplanned = runner.run(
            other_cell.build_problem(), other_cell.build_algorithm(), run_spec(other, other_cell)
        )
        (layout.stage_dir("pilot") / "notes.txt").write_text("x", encoding="utf-8")
        (layout.stage_dir("pilot") / "not-a-run").mkdir()

        collection = collect_study(study, layout)
        assert collection.duplicates == [(cell.key, duplicate.run_id)]
        assert collection.unplanned == [unplanned.run_id]
        assert len(collection.anomalies) == 2
        assert collection.canonical[cell.key].run_id != duplicate.run_id  # earliest wins
        assert _status(collection)["stray_runs"] == "WARN"

    def test_failed_runs_warn(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        layout = ArtifactLayout(tmp_path)
        target = ("DTLZ2", "random_search", 1)
        monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Exploding))
        run_study(make_study(), layout)
        status = _status(collect_study(make_study(), layout))
        assert status["failed_runs"] == "WARN"
        assert status["budget_exact"] == "PASS"  # failed runs are not held to the budget

    def test_environment_drift_warns_in_pilot_and_fails_in_final(
        self, layout: ArtifactLayout
    ) -> None:
        collection = collect_study(make_study(), layout)
        key = next(iter(collection.canonical))
        record = collection.canonical[key]
        drifted = record.metadata.model_copy(
            update={
                "git_commit": "b" * 40,
                "git_dirty": False,
                "software": record.metadata.software.model_copy(
                    update={"packages": {**record.metadata.software.packages, "pymoo": "0.0"}}
                ),
            }
        )
        collection.canonical[key] = type(record)(
            record.run_dir, drifted, record.config, record.metrics
        )
        env = next(c for c in diagnose(collection).checks if c.name == "environment")
        assert env.status == "WARN"
        assert any("pymoo differs" in d for d in env.details)
        assert any("git commits" in d for d in env.details)
        collection.study = make_study(stage="final")
        env = next(c for c in diagnose(collection).checks if c.name == "environment")
        assert env.status == "FAIL"

    def test_timing_and_projection(self, layout: ArtifactLayout) -> None:
        timings = diagnose(collect_study(make_study(), layout)).timings
        assert {(t.problem, t.algorithm) for t in timings} == {
            (p, a) for p in ("ZDT1", "DTLZ2") for a in ("random_search", "nsga2")
        }
        assert all(t.n_runs == 2 and t.median_seconds_per_evaluation > 0 for t in timings)
        one = projected_seconds(timings, budget=100, n_replicates=1)
        assert projected_seconds(timings, budget=100, n_replicates=3) == pytest.approx(3 * one)


class TestAggregate:
    def test_writes_tables_from_disk_with_recomputed_quality(
        self, layout: ArtifactLayout, tmp_path: Path
    ) -> None:
        collection = collect_study(make_study(), layout)
        out = write_aggregate(collection, diagnose(collection), tmp_path / "agg")
        rows = list(_read_csv(out / "runs.csv"))
        assert len(rows) == 8
        row = next(
            r
            for r in rows
            if (r["problem"], r["algorithm"], r["replicate"]) == ("ZDT1", "nsga2", "0")
        )
        record = collection.canonical[("ZDT1", "nsga2", 0)]
        f, feasible = history_objectives(record.read_history(), 2)
        expected = compute_quality(f, feasible, ZDT1(4).pareto_front())
        assert float(row["igd_plus"]) == expected["igd_plus"]
        assert int(row["n_evaluations"]) == BUDGET

        summary = list(_read_csv(out / "summary.csv"))
        assert len(summary) == 4
        assert all(s["n_planned"] == "2" and s["n_completed"] == "2" for s in summary)
        manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
        assert manifest["preliminary"] is True
        assert manifest["quality_policy"]["version"] == "proposed-v1"
        assert len(manifest["run_ids"]) == 8

    def test_failed_runs_are_counted_but_not_scored(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        layout = ArtifactLayout(tmp_path / "a")
        target = ("ZDT1", "random_search", 0)
        monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Exploding))
        run_study(make_study(), layout)
        collection = collect_study(make_study(), layout)
        out = write_aggregate(collection, diagnose(collection), tmp_path / "agg")
        rows = list(_read_csv(out / "runs.csv"))
        failed = next(r for r in rows if r["outcome"] == "failed")
        assert failed["hypervolume"] == ""
        assert failed["missing_reason"].startswith("run failed: RuntimeError: boom")
        summary = list(_read_csv(out / "summary.csv"))
        cell = next(
            s for s in summary if (s["problem"], s["algorithm"]) == ("ZDT1", "random_search")
        )
        assert (cell["n_completed"], cell["n_failed"], cell["igd_plus__n"]) == ("1", "1", "1")

    def test_refuses_failed_diagnostics_and_existing_output(
        self, layout: ArtifactLayout, tmp_path: Path
    ) -> None:
        collection = collect_study(make_study(), layout)
        (tmp_path / "exists").mkdir()
        with pytest.raises(FileExistsError):
            write_aggregate(collection, diagnose(collection), tmp_path / "exists")
        path = _first(layout) / "metrics.json"
        path.write_text(
            path.read_text(encoding="utf-8").replace('"n_evaluations": 30', '"n_evaluations": 3')
        )
        collection = collect_study(make_study(), layout)
        with pytest.raises(StudyError, match="budget_exact"):
            write_aggregate(collection, diagnose(collection), tmp_path / "new")
        assert not (tmp_path / "new").exists()


def test_describe_and_csv_formatting() -> None:
    assert _describe([]) == {"median": None, "q1": None, "q3": None, "mean": None, "std": None}
    assert _describe([2.0])["std"] is None
    d = _describe([1.0, 2.0, 3.0, 4.0, 5.0])
    assert (d["median"], d["q1"], d["q3"], d["mean"]) == (3.0, 2.0, 4.0, 3.0)
    text = to_csv([{"a": None, "b": 0.1, "c": float("inf")}], ["a", "b", "c"])
    assert text == "a,b,c\n,0.1,inf\n"


def test_scan_reports_copied_or_incomplete_runs(layout: ArtifactLayout) -> None:
    import shutil

    source = _first(layout)
    copy = source.with_name(source.name[:-6] + "abcdef")  # valid run id, foreign metadata
    shutil.copytree(source, copy)
    (source / "history.csv").unlink()
    (source / "metrics.json").unlink()

    collection = collect_study(make_study(), layout)
    assert any("!= directory" in why for _, why in collection.anomalies)
    record = collection.canonical[("ZDT1", "nsga2", 0)]
    assert record.metrics is None
    assert record.read_history() == []
    status = _status(collection)
    assert status["history_integrity"] == "FAIL"
    assert status["stray_runs"] == "WARN"
