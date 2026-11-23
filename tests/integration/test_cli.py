"""End-to-end tests for the command-line interface."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from evooptlab import __version__
from evooptlab.cli import main
from evooptlab.storage import RunMetadata

pytestmark = pytest.mark.integration


def test_version(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["version"]) == 0
    assert capsys.readouterr().out.strip() == __version__


def test_validate_repository_configs(configs_dir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = sorted(str(p) for p in configs_dir.glob("*.yaml"))
    assert main(["validate-config", *paths]) == 0
    out = capsys.readouterr().out
    assert out.count("OK ") == len(paths)
    assert "unresolved: hpo.tasks[1].target_metric = 'define_before_run'" in out


def test_validate_strict_fails_on_placeholders(
    configs_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["validate-config", "--strict", str(configs_dir / "hpo_tasks.yaml")]) == 1
    assert "unresolved decisions" in capsys.readouterr().err


def test_validate_reports_failures(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "bad.yaml"
    bad.write_text("experiment: {name: x}\n", encoding="utf-8")
    assert main(["validate-config", str(bad)]) == 1
    assert "FAIL" in capsys.readouterr().err


def test_env_outputs_json(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["env"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert {"python_version", "packages", "git"} <= data.keys()


def test_schema_matches_model(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["schema", "run-metadata"]) == 0
    assert json.loads(capsys.readouterr().out) == RunMetadata.model_json_schema()


def test_json_logging_goes_to_stderr(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["--log-level", "DEBUG", "--log-format", "json", "version"]) == 0
    err_line = capsys.readouterr().err.strip().splitlines()[-1]
    assert json.loads(err_line)["command"] == "version"


def test_module_entry_point() -> None:
    result = subprocess.run(
        [sys.executable, "-m", "evooptlab", "version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    assert result.stdout.strip() == __version__
