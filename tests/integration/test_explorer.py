"""The dashboard's data layer against a real artifact root (no UI library involved)."""

from __future__ import annotations

import csv
import json
import shutil
import statistics
import subprocess
import sys
from pathlib import Path

import pytest

from evooptlab.experiments import run_study
from evooptlab.explorer import scan_artifacts
from evooptlab.explorer import transforms as tf
from evooptlab.explorer.catalog import Catalog, RunEntry
from evooptlab.hpo.problem import select_trial
from evooptlab.storage import ArtifactLayout
from explorer_helpers import bench_study, build_root, tree_digest

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, Path]]:
    base = tmp_path_factory.mktemp("explorer")
    root = base / "artifacts"
    return root, build_root(root, base / "data")


@pytest.fixture(scope="module")
def cat(built: tuple[Path, dict[str, Path]]) -> Catalog:
    return scan_artifacts(built[0])


def _runs_csv(path: Path) -> dict[str, dict[str, str]]:
    with (path / "runs.csv").open(encoding="utf-8", newline="") as handle:
        return {r["run_id"]: r for r in csv.DictReader(handle)}


def test_catalog_indexes_runs_aggregates_reports_and_test_evaluations(cat: Catalog) -> None:
    assert cat.stages() == ["pilot"] and not cat.is_empty and cat.anomalies == []
    assert len(cat.select(kind="benchmark")) == 12 and len(cat.select(kind="hpo")) == 4
    assert cat.studies() == ["hpo-tiny", "tiny"]
    assert {a.name: (a.kind, a.stale) for a in cat.aggregates} == {
        "hpo-tiny__agg": ("hpo", False),
        "tiny__agg": ("benchmark", False),
    }
    for a in cat.aggregates:  # the stored diagnostics status, passed through unchanged
        manifest = json.loads((a.path / "manifest.json").read_text(encoding="utf-8"))
        assert a.diagnostics_status == manifest["diagnostics"]["status"] != "FAIL"
    (report,) = cat.reports
    assert (report.aggregate_name, report.preliminary, report.stale) == ("tiny__agg", True, False)
    assert report.plan_status == "proposal"
    assert len(cat.test_evaluations["pilot"]) == 4
    rows = {r["study"]: r for r in cat.overview()}
    assert rows["tiny"] == {
        "stage": "pilot",
        "study": "tiny",
        "kind": "benchmark",
        "runs": 12,
        "completed": 12,
        "failed": 0,
        "running": 0,
        "problems": 2,
        "algorithms": 2,
    }
    assert sum(e["runs"] for e in cat.environments()) == 16
    latest = cat.latest_run()
    assert latest is not None and latest.study == "hpo-tiny"
    run = cat.select(kind="benchmark")[0]
    assert cat.run("pilot", run.run_id) is run and cat.run("final", run.run_id) is None
    assert run.row()["stage"] == "pilot" and run.preliminary and run.path.is_dir()


def test_missing_or_empty_root_is_reported_honestly(tmp_path: Path) -> None:
    missing = scan_artifacts(tmp_path / "nope")
    assert missing.is_empty and missing.anomalies[0][1] == "artifact root does not exist"
    empty = scan_artifacts(tmp_path)
    assert empty.is_empty and empty.anomalies == [] and empty.stages() == []
    assert empty.latest_run() is None and empty.overview() == []


def test_unreadable_entries_become_anomalies_and_reports_lose_their_source(
    built: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built[0], root)
    (root / "pilot" / "not-a-run").mkdir()
    (root / "aggregates" / "pilot" / "broken").mkdir()
    (root / "aggregates" / "pilot" / "broken" / "manifest.json").write_text("[]", encoding="utf-8")
    shutil.rmtree(root / "aggregates" / "pilot" / "tiny__agg")
    bad_report = root / "reports" / "bad"
    bad_report.mkdir()
    (bad_report / "analysis.json").write_text("{}", encoding="utf-8")
    cat = scan_artifacts(root)
    reasons = " | ".join(r for _, r in cat.anomalies)
    assert "not-a-run" in " ".join(p for p, _ in cat.anomalies)
    assert "aggregate: ValueError" in reasons and "report: KeyError" in reasons
    (report,) = cat.reports
    assert report.stale_reasons == ("its source aggregate is not under this root",)


def test_new_runs_make_an_aggregate_and_its_report_stale(
    built: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built[0], root)
    other_budget = bench_study(budget={"unit": "objective_evaluations", "max_evaluations": 20})
    run_study(other_budget, ArtifactLayout(root))
    cat = scan_artifacts(root)
    aggregate = next(a for a in cat.aggregates if a.name == "tiny__agg")
    assert aggregate.stale_reasons == ("12 run(s) of the study started after it was written",)
    assert cat.reports[0].stale_reasons == (f"source aggregate: {aggregate.stale_reasons[0]}",)

    zdt = cat.select(study="tiny", problem="ZDT1")
    check = tf.comparability(zdt)
    assert check.budgets == {30: 6, 20: 6} and not check.comparable_budgets
    assert "not comparable" in check.warnings[0]
    with pytest.raises(tf.IncomparableRunsError, match="evaluation budgets"):
        tf.convergence_bands(zdt)
    with pytest.raises(tf.IncomparableRunsError, match="problems"):
        tf.convergence_bands(cat.select(study="tiny"))

    shutil.rmtree(cat.select(study="tiny")[0].path)
    rescanned = next(a for a in scan_artifacts(root).aggregates if a.name == "tiny__agg")
    assert "1 run(s) it lists are not under this root" in rescanned.stale_reasons


def test_comparability_warns_on_stages_and_unscored_runs(cat: Catalog) -> None:
    runs = cat.select(kind="benchmark", problem="ZDT1")
    assert tf.comparability(runs).warnings == ()
    failed = RunEntry(**{**runs[0].__dict__, "stage": "development", "outcome": "failed"})
    warnings = tf.comparability([*runs, failed]).warnings
    assert any("different stages" in w for w in warnings)
    assert any("1 run(s) did not complete" in w for w in warnings)
    assert tf.convergence_bands([failed]) == []


def test_live_quality_and_curves_equal_the_stored_aggregate(
    cat: Catalog, built: tuple[Path, dict[str, Path]]
) -> None:
    stored = _runs_csv(built[1]["bench_aggregate"])
    for problem in ("ZDT1", "DTLZ2"):
        runs = cat.select(kind="benchmark", problem=problem)
        for run in runs:
            front = tf.run_front(run)
            assert front.quality is not None and front.reference_front is not None
            row = stored[run.run_id]
            for key in ("igd_plus", "hypervolume_ratio", "feasibility_rate"):
                assert front.quality[key] == pytest.approx(float(row[key]), rel=1e-12)
            assert front.nondominated.sum() == int(row["n_nondominated"])
            assert tf.run_front(run, with_quality=False).quality is None
            assert not (front.nondominated & ~front.feasible).any()
        for band in tf.convergence_bands(runs, n_checkpoints=5):
            final = [float(stored[rid]["igd_plus"]) for rid in band.run_ids]
            assert band.evaluations[-1] == 30 and band.n[-1] == len(final) == 3
            assert band.median[-1] == pytest.approx(statistics.median(final), rel=1e-12)
            q1, _, q3 = statistics.quantiles(final, n=4, method="inclusive")
            assert (band.q1[-1], band.q3[-1]) == pytest.approx((q1, q3), rel=1e-12)


def test_hpo_trials_selection_and_test_results_match_stored_artifacts(
    cat: Catalog, built: tuple[Path, dict[str, Path]]
) -> None:
    stored = _runs_csv(built[1]["hpo_aggregate"])
    runs = cat.select(kind="hpo")
    for run in runs:
        rows = tf.trial_rows(run)
        chosen = select_trial(run.record.read_history())
        assert chosen is not None
        (selected,) = [r for r in rows if r["selected"]]
        assert selected["evaluation_id"] == int(chosen["evaluation_id"])
        best = [r["best_so_far"] for r in rows if r["best_so_far"] is not None]
        assert best == sorted(best, reverse=True) and best[-1] == float(chosen["f_0"])
        test = tf.test_result(cat, run)
        assert test is not None and test["status"] == "ok"
        decoded = {k: selected[k] for k in test["hyperparameters"]}
        assert decoded == pytest.approx(test["hyperparameters"])
        assert test["test_error"] == pytest.approx(float(stored[run.run_id]["test_error"]))
    summary = {r["run_id"]: r for r in tf.hpo_run_rows(cat, runs)}
    for run_id, row in summary.items():
        assert row["best_validation_error"] == pytest.approx(
            float(stored[run_id]["best_validation_error"])
        )
        assert row["n_trials"] == 6 and row["test_status"] == "ok"
    bands = tf.convergence_bands(runs, n_checkpoints=3)
    for band in bands:
        final = [float(stored[rid]["best_validation_error"]) for rid in band.run_ids]
        assert band.median[-1] == pytest.approx(statistics.median(final))
    assert tf.reference_front(runs[0]) is None and tf.run_front(runs[0]).quality is None


def test_test_results_are_flagged_when_absent_mismatched_or_unreadable(
    built: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built[0], root)
    first, second, third, _ = scan_artifacts(root).select(kind="hpo")
    held_out = root / "test_evaluations" / "pilot"
    record = json.loads((held_out / f"{first.run_id}.json").read_text(encoding="utf-8"))
    record["config_hash"] = "f" * 64
    (held_out / f"{first.run_id}.json").write_text(json.dumps(record), encoding="utf-8")
    (held_out / f"{second.run_id}.json").write_text("not json", encoding="utf-8")
    (held_out / f"{third.run_id}.json").unlink()
    cat = scan_artifacts(root)
    statuses = {
        r["run_id"]: (r["test_status"], r["test_error"])
        for r in tf.hpo_run_rows(cat, cat.select(kind="hpo"))
    }
    assert statuses[first.run_id] == ("config hash mismatch", None)
    assert statuses[second.run_id] == ("unreadable", None)
    assert statuses[third.run_id] == ("not run", None)


def test_report_and_aggregate_tables_pass_through_unchanged(cat: Catalog) -> None:
    (report,) = cat.reports
    analysis = report.analysis()
    assert tf.analysis_metrics(analysis) == [
        ("hypervolume_ratio", "maximize"),
        ("igd_plus", "minimize"),
    ]
    pairwise = tf.pairwise_rows(analysis, "igd_plus")
    source = [r for r in analysis["pairwise"] if r["metric"] == "igd_plus"]
    assert len(pairwise) == len(source) == 2
    assert [r["p_holm"] for r in pairwise] == [r["p_holm"] for r in source]
    assert [r["a12"] for r in pairwise] == [r["a12"] for r in source]
    descriptive = tf.descriptive_rows(analysis, "igd_plus")
    assert {r["n"] for r in descriptive} == {3}
    (across,) = tf.across_rows(analysis, "igd_plus")
    assert across["problems_used"] == 2 and across["test"].startswith("Friedman")

    aggregate = next(a for a in cat.aggregates if a.name == "tiny__agg")
    runs, summary = tf.aggregate_tables(aggregate)
    assert len(runs) == 12 and len(summary) == 4
    values, missing = tf.metric_values(runs, "igd_plus")
    assert missing == 0 and {len(v) for d in values.values() for v in d.values()} == {3}
    _, missing = tf.metric_values([{**runs[0], "outcome": "failed"}], "igd_plus")
    assert missing == 1


def test_run_files_and_log(cat: Catalog) -> None:
    run = cat.select(kind="benchmark")[0]
    files = {f["file"] for f in tf.run_files(run)}
    assert {"run_metadata.json", "config.yaml", "metrics.json", "history.csv"} <= files
    log = tf.run_log(run)
    assert log[0]["message"] == "run started" and log[-1]["message"] == "run finished"


def test_run_log_keeps_unparsable_lines_and_tolerates_absence(
    built: tuple[Path, dict[str, Path]], tmp_path: Path
) -> None:
    root = tmp_path / "copy"
    shutil.copytree(built[0], root)
    first, second = scan_artifacts(root).select(kind="benchmark")[:2]
    (first.path / "logs" / "run.log.jsonl").write_text("plain text\n[1]\n", encoding="utf-8")
    (second.path / "logs" / "run.log.jsonl").unlink()
    cat = scan_artifacts(root)
    assert tf.run_log(cat.run("pilot", first.run_id)) == [  # type: ignore[arg-type]
        {"message": "plain text"},
        {"message": "[1]"},
    ]
    assert tf.run_log(cat.run("pilot", second.run_id)) == []  # type: ignore[arg-type]


def test_explorer_never_writes(built: tuple[Path, dict[str, Path]]) -> None:
    root = built[0]
    before = tree_digest(root)
    cat = scan_artifacts(root)
    for run in cat.runs:
        tf.run_files(run)
        tf.run_log(run)
        if run.kind == "hpo":
            tf.trial_rows(run)
            tf.test_result(cat, run)
        else:
            tf.run_front(run)
    for problem in {r.problem for r in cat.runs}:
        tf.convergence_bands(cat.select(problem=problem))
    for aggregate in cat.aggregates:
        tf.aggregate_tables(aggregate)
    cat.reports[0].analysis()
    assert tree_digest(root) == before


def test_explorer_imports_no_ui_library() -> None:
    code = (
        "import sys, evooptlab.explorer, evooptlab.explorer.transforms; "
        "print(sorted(m for m in ('streamlit', 'plotly') if m in sys.modules))"
    )
    out = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, check=True
    ).stdout
    assert out.strip() == "[]"
