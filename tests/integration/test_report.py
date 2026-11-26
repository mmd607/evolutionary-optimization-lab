"""Analysis and report generation from real (tiny) study artifacts."""

from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

import pytest

from evooptlab.analysis.compare import AnalysisError, analyse, load_aggregate
from evooptlab.analysis.curves import checkpoints
from evooptlab.config import load_config
from evooptlab.config.schemas import AnalysisPlanConfig, PlanMetric, ReportingConfig
from evooptlab.experiments import collect_study, diagnose, run_study, write_aggregate
from evooptlab.reporting.report import write_report
from evooptlab.reporting.tables import latex_escape
from evooptlab.storage import ArtifactLayout
from study_helpers import make_study

pytestmark = pytest.mark.integration


def plan(configs_dir: Path, **changes: Any) -> AnalysisPlanConfig:
    base = load_config(configs_dir / "analysis_plan.yaml").analysis_plan  # type: ignore[union-attr]
    updates: dict[str, Any] = {
        "min_replicates": 2,
        "across_problems": base.across_problems.model_copy(update={"min_problems": 2}),
    }
    updates.update(changes)
    return base.model_copy(update=updates)


def reporting(configs_dir: Path) -> ReportingConfig:
    config = load_config(configs_dir / "reporting.yaml").reporting  # type: ignore[union-attr]
    return config.model_copy(update={"figure_formats": ["svg"], "convergence_checkpoints": 4})


@pytest.fixture(scope="module")
def aggregate(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("artifacts")
    layout = ArtifactLayout(root)
    study = make_study(seeds={"policy": "explicit", "values": [1, 2, 3]})
    run_study(study, layout)
    collection = collect_study(study, layout)
    return write_aggregate(collection, diagnose(collection), root / "aggregates" / "pilot" / "x")


def test_report_regenerates_every_asset(aggregate: Path, configs_dir: Path, tmp_path: Path) -> None:
    out = write_report(
        load_aggregate(aggregate),
        plan(configs_dir),
        reporting(configs_dir),
        tmp_path / "r",
        plan_sha256="0" * 64,
    )
    names = {p.relative_to(out).as_posix() for p in out.rglob("*") if p.is_file()}
    for metric in ("hypervolume_ratio", "igd_plus"):
        assert {f"tables/{metric}_descriptive.md", f"tables/{metric}_pairwise.tex"} <= names
        assert {f"figures/{metric}_distribution.svg", f"figures/{metric}_distribution.csv"} <= names
    assert {"analysis.json", "values.json", "figures/convergence.svg", "README.md"} <= names

    table = (out / "tables" / "igd_plus_descriptive.md").read_text(encoding="utf-8")
    assert "PRELIMINARY" in table and "↓" in table and "| 3/3 |" in table
    assert "PRELIMINARY" in (out / "README.md").read_text(encoding="utf-8")
    analysis = json.loads((out / "analysis.json").read_text(encoding="utf-8"))
    assert analysis["preliminary"] is True
    assert len(analysis["source"]["run_ids"]) == 12
    with pytest.raises(FileExistsError):
        write_report(
            load_aggregate(aggregate),
            plan(configs_dir),
            reporting(configs_dir),
            out,
            plan_sha256="0" * 64,
        )


def test_values_trace_to_runs_csv(aggregate: Path, configs_dir: Path, tmp_path: Path) -> None:
    out = write_report(
        load_aggregate(aggregate),
        plan(configs_dir),
        reporting(configs_dir),
        tmp_path / "r",
        plan_sha256="0" * 64,
    )
    store = json.loads((out / "values.json").read_text(encoding="utf-8"))
    rows = list(csv.DictReader((aggregate / "runs.csv").read_text(encoding="utf-8").splitlines()))
    zdt = sorted(
        float(r["igd_plus"]) for r in rows if (r["problem"], r["algorithm"]) == ("ZDT1", "nsga2")
    )
    entry = store["tiny/ZDT1/nsga2/igd_plus/median"]
    assert entry["value"] == zdt[1] and entry["preliminary"] is True
    assert store["tiny/matrix/n_runs"]["value"] == 12


def test_last_convergence_point_equals_aggregated_igd_plus(
    aggregate: Path, configs_dir: Path, tmp_path: Path
) -> None:
    out = write_report(
        load_aggregate(aggregate),
        plan(configs_dir),
        reporting(configs_dir),
        tmp_path / "r",
        plan_sha256="0" * 64,
    )
    curve = list(
        csv.DictReader((out / "figures" / "convergence.csv").read_text("utf-8").splitlines())
    )
    last = max(int(r["evaluations"]) for r in curve)
    point = next(
        r
        for r in curve
        if (r["problem"], r["algorithm"], int(r["evaluations"])) == ("ZDT1", "nsga2", last)
    )
    rows = list(csv.DictReader((aggregate / "runs.csv").read_text(encoding="utf-8").splitlines()))
    values = sorted(
        float(r["igd_plus"]) for r in rows if (r["problem"], r["algorithm"]) == ("ZDT1", "nsga2")
    )
    assert float(point["median"]) == pytest.approx(values[1], rel=1e-12)


def test_paired_tests_and_ranks(aggregate: Path, configs_dir: Path) -> None:
    result = analyse(load_aggregate(aggregate), plan(configs_dir), plan_sha256="x")
    tested = [r for r in result.pairwise if r["metric"] == "igd_plus"]
    assert len(tested) == 2 and all(r["n_pairs"] == 3 for r in tested)
    assert all(r["p_holm"] is None or r["p_holm"] >= r["p_value"] for r in tested)
    across = next(a for a in result.across_problems if a["metric"] == "igd_plus")
    assert across["note"] == "Friedman needs at least 3 algorithms"  # only 2 algorithms here
    assert set(across["mean_ranks"]) == {"random_search", "nsga2"}
    strict = analyse(
        load_aggregate(aggregate), plan(configs_dir, min_replicates=10), plan_sha256="x"
    )
    assert all(r["note"].startswith("not run: 3 complete pairs") for r in strict.pairwise)
    assert all(a["note"].startswith("not run: 0 problems") for a in strict.across_problems)


def _copy(aggregate: Path, tmp_path: Path, edit: Any) -> Path:
    import shutil

    target = tmp_path / "copy"
    shutil.copytree(aggregate, target)
    edit(target)
    return target


def test_final_results_need_a_frozen_plan_and_clean_tree(
    aggregate: Path, configs_dir: Path, tmp_path: Path
) -> None:
    def make_final(path: Path) -> None:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        manifest.update({"stage": "final", "preliminary": False})
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    data = load_aggregate(_copy(aggregate, tmp_path, make_final))
    with pytest.raises(AnalysisError, match="frozen analysis plan"):
        analyse(data, plan(configs_dir), plan_sha256="x", git_commit="a" * 40, git_dirty=False)
    frozen = plan(configs_dir, status="frozen")
    with pytest.raises(AnalysisError, match="clean, committed"):
        analyse(data, frozen, plan_sha256="x", git_commit="a" * 40, git_dirty=True)
    result = analyse(data, frozen, plan_sha256="x", git_commit="a" * 40, git_dirty=False)
    assert result.preliminary is False


def test_refuses_failed_diagnostics_broken_pairing_and_missing_columns(
    aggregate: Path, configs_dir: Path, tmp_path: Path
) -> None:
    def fail(path: Path) -> None:
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        manifest["diagnostics"]["status"] = "FAIL"
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(AnalysisError, match="diagnostics failed"):
        load_aggregate(_copy(aggregate, tmp_path / "a", fail))
    with pytest.raises(AnalysisError, match="not a readable aggregate"):
        load_aggregate(tmp_path / "nowhere")

    def unpair(path: Path) -> None:
        text = (path / "runs.csv").read_text(encoding="utf-8").splitlines()
        header, rows = text[0], text[1:]
        cols = header.split(",")
        cells = rows[1].split(",")
        cells[cols.index("seed")] = "424242"
        rows[1] = ",".join(cells)
        (path / "runs.csv").write_text("\n".join([header, *rows]) + "\n", encoding="utf-8")

    with pytest.raises(AnalysisError, match="do not share seeds"):
        analyse(
            load_aggregate(_copy(aggregate, tmp_path / "b", unpair)),
            plan(configs_dir),
            plan_sha256="x",
        )
    data = load_aggregate(aggregate)
    with pytest.raises(AnalysisError, match="no column"):
        spread = PlanMetric(name="spread", direction="maximize", primary=True)
        analyse(data, plan(configs_dir, benchmark_metrics=[spread]), plan_sha256="x")


def test_checkpoints_and_latex_escaping() -> None:
    assert checkpoints(0, 5) == []
    assert checkpoints(3, 10) == [1, 2, 3]
    assert checkpoints(100, 5)[-1] == 100 and len(checkpoints(100, 5)) == 5
    assert latex_escape("a_b & 5% ± ↓ —") == r"a\_b \& 5\% $\pm$ $\downarrow$ ---"


def test_hpo_report_uses_best_so_far_curves(configs_dir: Path, tmp_path: Path) -> None:
    from evooptlab.config.schemas import StudyConfig
    from evooptlab.experiments import evaluate_study_on_test
    from hpo_helpers import hpo_config

    study = StudyConfig.model_validate(
        {
            "name": "hpo-report",
            "stage": "pilot",
            "output_dir": "unused",
            "problems": [hpo_config().model_dump(mode="json")],
            "algorithms": [
                {"name": "random_search", "parameters": {"batch_size": 2}},
                {"name": "optuna_tpe", "parameters": {"n_startup_trials": 2}},
            ],
            "budget": {"unit": "objective_evaluations", "max_evaluations": 4},
            "seeds": {"policy": "explicit", "values": [1, 2]},
        }
    )
    layout = ArtifactLayout(tmp_path / "artifacts")
    run_study(study, layout, data_dir=tmp_path)
    evaluate_study_on_test(collect_study(study, layout), layout)
    collection = collect_study(study, layout)
    agg = write_aggregate(
        collection, diagnose(collection), layout.root / "aggregates" / "pilot" / "h"
    )
    out = write_report(
        load_aggregate(agg),
        plan(configs_dir),
        reporting(configs_dir),
        tmp_path / "r",
        plan_sha256="0" * 64,
    )
    assert (out / "tables" / "test_error_descriptive.md").exists()
    curve = list(
        csv.DictReader((out / "figures" / "convergence.csv").read_text("utf-8").splitlines())
    )
    medians = [float(r["median"]) for r in curve if r["algorithm"] == "random_search"]
    assert medians == sorted(medians, reverse=True)  # best-so-far never gets worse


def test_report_cli(
    aggregate: Path, configs_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    from evooptlab.cli import main

    plan_file = tmp_path / "plan.yaml"
    text = (configs_dir / "analysis_plan.yaml").read_text(encoding="utf-8")
    plan_file.write_text(text.replace("min_replicates: 10", "min_replicates: 2"), encoding="utf-8")
    common = ["--plan", str(plan_file), "--reporting", str(configs_dir / "reporting.yaml")]
    out = tmp_path / "rep"
    assert main(["report", str(aggregate), *common, "--output", str(out)]) == 0
    assert "PRELIMINARY" in capsys.readouterr().out
    assert (out / "values.json").exists()
    assert main(["report", str(aggregate), *common, "--output", str(out)]) == 2  # never overwrites
    wrong = ["--plan", str(configs_dir / "reporting.yaml"), "--reporting", str(plan_file)]
    assert main(["report", str(aggregate), *wrong]) == 2
    assert "analysis_plan file" in capsys.readouterr().err


def test_regenerated_reports_are_byte_identical(
    aggregate: Path, configs_dir: Path, tmp_path: Path
) -> None:
    """Every asset, SVG included, is a pure function of its inputs (reproduction guide §5)."""
    outputs = [
        write_report(
            load_aggregate(aggregate),
            plan(configs_dir),
            reporting(configs_dir).model_copy(update={"figure_formats": ["svg", "pdf"]}),
            tmp_path / name,
            plan_sha256="0" * 64,
        )
        for name in ("first", "second")
    ]
    files = [
        {p.relative_to(o).as_posix(): p.read_bytes() for p in o.rglob("*") if p.is_file()}
        for o in outputs
    ]
    assert files[0].keys() == files[1].keys()
    assert any(name.endswith(".svg") for name in files[0])
    assert [n for n in files[0] if files[0][n] != files[1][n]] == []
