"""The clean command path: plan -> run -> diagnose -> aggregate through the CLI."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from evooptlab.cli import main
from study_helpers import make_study

pytestmark = pytest.mark.integration


@pytest.fixture
def study_file(tmp_path: Path) -> Path:
    path = tmp_path / "tiny.yaml"
    study = make_study().model_dump(mode="json")
    path.write_text(yaml.safe_dump({"study": study}, sort_keys=False), encoding="utf-8")
    return path


def test_full_command_path(
    study_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "artifacts"
    common = [str(study_file), "--root", str(root)]

    assert main(["plan", str(study_file)]) == 0
    plan = capsys.readouterr().out
    assert '"n_runs": 8' in plan
    assert not root.exists()  # planning never writes

    assert main(["run", *common]) == 0
    assert "executed 8, skipped 0, failed 0" in capsys.readouterr().out
    assert main(["run", *common]) == 2
    assert "pass resume" in capsys.readouterr().err
    assert main(["run", *common, "--resume"]) == 0
    assert "executed 0, skipped 8" in capsys.readouterr().out

    assert main(["diagnose", *common, "--project-budget", "100", "--project-replicates", "2"]) == 0
    text = capsys.readouterr().out
    assert "[pilot PRELIMINARY]" in text
    assert "PASS  budget_exact" in text
    assert "projected sequential time at 100 evaluations x 2 replicates" in text

    assert main(["diagnose", *common, "--json"]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["preliminary"] is True
    assert report["projected_sequential_seconds"] is None

    out = tmp_path / "agg"
    assert main(["aggregate", *common, "--output", str(out)]) == 0
    assert {p.name for p in out.iterdir()} == {"runs.csv", "summary.csv", "manifest.json"}
    assert main(["aggregate", *common, "--output", str(out)]) == 2  # never overwrites
    capsys.readouterr()

    assert main(["aggregate", *common]) == 0  # default location under the artifact root
    assert len(list((root / "aggregates" / "pilot").iterdir())) == 1


def test_diagnose_exits_1_on_failure(
    study_file: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "artifacts"
    assert main(["run", str(study_file), "--root", str(root)]) == 0
    history = next((root / "pilot").iterdir()) / "history.csv"
    history.write_text("evaluation_id\n", encoding="utf-8")
    assert main(["diagnose", str(study_file), "--root", str(root)]) == 1
    assert "FAIL  history_integrity" in capsys.readouterr().out
    assert main(["diagnose", str(study_file), "--root", str(root), "--json"]) == 1


def test_run_exits_1_when_a_run_fails(
    study_file: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from evooptlab.experiments import RunCell
    from study_helpers import Exploding, builder_replacing

    target = ("ZDT1", "random_search", 0)
    monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Exploding))
    assert main(["run", str(study_file), "--root", str(tmp_path / "a")]) == 1


def test_study_commands_reject_other_configs_and_placeholders(
    configs_dir: Path, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["plan", str(configs_dir / "benchmarks.yaml")]) == 2
    assert "expected a study config" in capsys.readouterr().err
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "study:\n  name: tbd\n  stage: pilot\n  output_dir: x\n"
        "  problems: [{name: ZDT1, objectives: 2, variables: 4}]\n"
        "  algorithms: [{name: nsga2}]\n"
        "  budget: {unit: objective_evaluations, max_evaluations: 10}\n"
        "  seeds: {policy: explicit, values: [1]}\n",
        encoding="utf-8",
    )
    assert main(["plan", str(bad)]) == 2
    assert "unresolved decisions" in capsys.readouterr().err
    incompatible = tmp_path / "incompatible.yaml"
    incompatible.write_text(
        bad.read_text(encoding="utf-8").replace("tbd", "x").replace("nsga2", "pso")
    )
    assert main(["plan", str(incompatible)]) == 2
    assert "pso does not support ZDT1" in capsys.readouterr().err
