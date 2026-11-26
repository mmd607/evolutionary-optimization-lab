"""Smoke tests of the Streamlit dashboard on a real artifact root (Streamlit's AppTest)."""

from __future__ import annotations

import shutil
from pathlib import Path

import numpy as np
import pytest

pytest.importorskip("streamlit")
pytest.importorskip("plotly")

from streamlit.testing.v1 import AppTest

from evodash import charts, common
from evooptlab.experiments import run_study
from evooptlab.explorer import scan_artifacts
from evooptlab.explorer import transforms as tf
from evooptlab.storage import ArtifactLayout
from explorer_helpers import bench_study, build_root, tree_digest

pytestmark = pytest.mark.integration

APP = Path(__file__).resolve().parents[2] / "dashboard" / "app.py"
PAGES = {
    "overview": "EvoOptLab — experiment overview",
    "benchmarks": "Benchmark Explorer",
    "convergence": "Convergence Analysis",
    "hpo": "HPO Explorer",
    "statistics": "Statistical Comparison",
    "runs": "Run Details",
}


@pytest.fixture(scope="module")
def root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    base = tmp_path_factory.mktemp("dashboard")
    build_root(base / "artifacts", base / "data")
    return base / "artifacts"


def app(root: Path) -> AppTest:
    at = AppTest.from_file(str(APP), default_timeout=120)
    at.session_state["root"] = str(root)
    return at.run()


def page(at: AppTest, name: str) -> AppTest:
    at.switch_page(f"views/page_{name}.py").run()
    assert not at.exception, [e.value for e in at.exception]
    assert [t.value for t in at.title] == [PAGES[name]]
    return at


def texts(elements: object) -> str:
    return " | ".join(str(e.value) for e in elements)  # type: ignore[attr-defined]


def test_every_page_renders_real_artifacts_and_writes_nothing(root: Path) -> None:
    before = tree_digest(root)
    at = app(root)
    assert not at.exception
    assert "No final-stage runs" in texts(at.warning)
    for name in PAGES:
        page(at, name)
        if name != "overview":
            assert "PRELIMINARY: pilot stage" in texts(at.warning)
    assert tree_digest(root) == before


def test_benchmark_explorer_shows_front_quality_and_stored_indicators(root: Path) -> None:
    at = page(app(root), "benchmarks")
    assert "non-dominated" in texts(at.caption) and "tiny__agg" in texts(at.caption)
    quality, compare = at.dataframe[0].value, at.dataframe[1].value
    assert list(quality.columns)[:2] == ["hypervolume_ratio", "igd_plus"]
    # every algorithm of the selected problem and budget, one row per stored run
    assert len(compare) == 6 and set(compare["algorithm"]) == {"random_search", "nsga2"}


def test_benchmark_quality_is_computed_live_only_without_an_aggregate(
    root: Path, tmp_path: Path
) -> None:
    at = page(app(root), "benchmarks")
    assert "stored in aggregate `tiny__agg`" in texts(at.markdown)
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    shutil.rmtree(copy / "aggregates")
    at = page(app(copy), "benchmarks")
    assert "computed now" in texts(at.markdown)
    assert "No aggregate for this study yet" in texts(at.info)


def test_convergence_curves_are_computed_only_on_request(root: Path) -> None:
    at = page(app(root), "convergence")
    at.selectbox(key="conv_study").set_value("tiny").run()
    assert "computed only on request" in texts(at.caption) and not at.dataframe
    next(b for b in at.button if b.label == "Compute curves").click().run()
    assert not at.exception
    (summary,) = at.dataframe
    assert set(summary.value["runs"]) == {3} and set(summary.value["evaluations"]) == {30}


def test_hpo_explorer_shows_stored_test_result_as_preliminary(root: Path) -> None:
    at = app(root)
    at.switch_page("views/page_hpo.py").run()
    assert "PRELIMINARY test result" in texts(at.warning)
    assert "Selected by lowest validation error" in texts(at.markdown)
    assert at.json and len(at.dataframe) == 2


def test_statistics_page_reads_the_report_and_flags_the_open_plan(root: Path) -> None:
    at = page(app(root), "statistics")
    assert "not frozen" in texts(at.warning)
    assert "Wilcoxon" in texts(at.caption)
    assert len(at.dataframe) == 3


def test_run_details_lists_files_with_downloads(root: Path) -> None:
    at = page(app(root), "runs")
    assert len(at.tabs) == 6 and at.json
    labels = {getattr(b, "label", None) for b in at.get("download_button")}
    assert "Download history.csv" in labels


def test_empty_root_shows_honest_empty_states(tmp_path: Path) -> None:
    at = app(tmp_path / "missing")
    assert "No results available" in texts(at.info)
    for name in PAGES:
        page(at, name)
        assert "No results available" in texts(at.info)


def test_mixed_budgets_and_new_runs_are_flagged(root: Path, tmp_path: Path) -> None:
    copy = tmp_path / "copy"
    shutil.copytree(root, copy)
    run_study(
        bench_study(budget={"unit": "objective_evaluations", "max_evaluations": 20}),
        ArtifactLayout(copy),
    )
    at = page(app(copy), "convergence")
    at.selectbox(key="conv_study").set_value("tiny").run()
    assert "different budgets" in texts(at.warning)
    at = page(at, "statistics")
    assert "Stale report" in texts(at.warning)


def test_default_root_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(common.ROOT_ENV, raising=False)
    assert common.default_root([]) == "artifacts"
    monkeypatch.setenv(common.ROOT_ENV, "from-env")
    assert common.default_root(["--other", "x"]) == "from-env"
    assert common.default_root(["--root", "from-arg"]) == "from-arg"


def test_figures_label_preliminary_data_and_keep_every_series(root: Path) -> None:
    cat = scan_artifacts(root)
    bench = cat.select(kind="benchmark", problem="ZDT1")
    front = tf.run_front(bench[0])
    fig = charts.front_figure(front, charts.title("ZDT1", preliminary=True))
    names = {t.name for t in fig.data}
    assert "reference front" in names and "non-dominated (approximation set)" in names
    assert fig.layout.title.text == "ZDT1 — PRELIMINARY"
    three = charts.front_figure(tf.run_front(cat.select(problem="DTLZ2")[0]), "DTLZ2")
    assert {t.type for t in three.data} == {"scatter3d"}

    bands = tf.convergence_bands(bench, n_checkpoints=4)
    curves = charts.curve_figure(bands, "IGD+", "c", log_y=True)
    assert len(curves.data) == 2 * len(bands) and curves.layout.yaxis.type == "log"

    values = {"a": [1.0, 2.0], "b": [3.0]}
    boxes = charts.distribution_figure(values, "igd_plus", "minimize", "d")
    assert [len(t.y) for t in boxes.data] == [
        2,
        1,
    ] and "lower is better" in boxes.layout.yaxis.title.text

    hpo = cat.select(kind="hpo")
    rows = tf.trial_rows(hpo[0])
    failed = [{**rows[0], "feasible": False, "validation_error": None, "selected": False}]
    trials = charts.trials_figure(rows + failed, "t")
    assert {t.name for t in trials.data} >= {"trial", "best so far", "failed trial"}
    cost = charts.quality_cost_figure(tf.hpo_run_rows(cat, hpo), "test_error", "q")
    assert sum(len(t.x) for t in cost.data) == len(hpo)
    assert charts.style(9) == charts.style(1) and np.isclose(len(charts.SYMBOLS), 8)
