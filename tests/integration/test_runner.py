"""End-to-end tests for ExperimentRunner on synthetic problems."""

from __future__ import annotations

import csv
import io
import json
import logging
import time
from pathlib import Path
from typing import Any, ClassVar

import numpy as np
import pytest
import yaml

from evooptlab.benchmarks import ConstrainedSphere, Sphere, TwoSpheres
from evooptlab.core.errors import AlgorithmError
from evooptlab.core.experiment import ExperimentRunner, RunResult, RunSpec, _canonical_hash
from evooptlab.core.problem import FloatArray, ProblemOutput
from evooptlab.storage import ArtifactLayout, RunMetadata
from evooptlab.utils.logging import configure_logging
from helpers import Misbehaving, SingleObjectiveOnly, UniformSampler

pytestmark = pytest.mark.integration


@pytest.fixture
def runner(tmp_path: Path, repo_root: Path) -> ExperimentRunner:
    return ExperimentRunner(ArtifactLayout(tmp_path / "artifacts"), repo_root=repo_root)


def _rows(result: RunResult) -> list[dict[str, str]]:
    text = (result.run_dir / "history.csv").read_text(encoding="utf-8")
    return list(csv.DictReader(io.StringIO(text)))


class TestCompletedRun:
    def test_artifacts_and_metadata(self, runner: ExperimentRunner) -> None:
        result = runner.run(TwoSpheres(3), UniformSampler(7), RunSpec("pilot", seed=11, budget=50))
        assert result.outcome == "completed"
        assert result.run_dir.parent.name == "pilot"
        for name in ("run_metadata.json", "config.yaml", "metrics.json", "history.csv"):
            assert (result.run_dir / name).is_file(), name
        assert (result.run_dir / "logs" / "run.log.jsonl").is_file()

        stored = RunMetadata.model_validate_json(
            (result.run_dir / "run_metadata.json").read_text(encoding="utf-8")
        )
        assert stored == result.metadata
        assert stored.outcome == "completed"
        assert stored.finished_at_utc is not None
        assert stored.problem == "two_spheres"
        assert stored.algorithm == "uniform_sampler"
        assert stored.seed == 11
        assert stored.objective_evaluation_budget == 50
        assert stored.software.packages["numpy"] is not None
        assert stored.git_commit is None or len(stored.git_commit) == 40

    def test_config_is_hashed_and_complete(self, runner: ExperimentRunner) -> None:
        result = runner.run(
            Sphere(2),
            UniformSampler(5),
            RunSpec("development", seed=3, budget=10, extra_config={"note": "x"}),
        )
        config = yaml.safe_load((result.run_dir / "config.yaml").read_text(encoding="utf-8"))
        assert result.metadata.config_hash == _canonical_hash(config)
        assert config["algorithm"] == {"name": "uniform_sampler", "parameters": {"batch_size": 5}}
        assert config["problem"]["lower_bounds"] == [-5.0, -5.0]
        assert config["budget"] == {"unit": "objective_evaluations", "max_evaluations": 10}
        assert config["extra"] == {"note": "x"}
        assert set(config["seed_streams"]) == {"algorithm"}

    def test_budget_is_used_exactly(self, runner: ExperimentRunner) -> None:
        result = runner.run(Sphere(2), UniformSampler(7), RunSpec("pilot", seed=1, budget=50))
        rows = _rows(result)
        assert result.n_evaluations == 50
        assert [int(r["evaluation_id"]) for r in rows] == list(range(50))
        metrics = json.loads((result.run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["n_evaluations"] == 50
        assert metrics["n_batches"] == 8  # 7 * 7 + 1
        assert metrics["n_failed_evaluations"] == 0
        assert metrics["wall_clock_seconds"] >= metrics["evaluation_seconds"] >= 0

    def test_history_preserves_full_precision(self, runner: ExperimentRunner) -> None:
        result = runner.run(Sphere(2), UniformSampler(3), RunSpec("pilot", seed=4, budget=3))
        row = _rows(result)[0]
        x = np.array([float(row["x_0"]), float(row["x_1"])])
        assert float(row["f_0"]) == float(np.sum(x**2))

    def test_constraints_are_recorded(self, runner: ExperimentRunner) -> None:
        result = runner.run(
            ConstrainedSphere(2), UniformSampler(10), RunSpec("pilot", seed=2, budget=40)
        )
        rows = _rows(result)
        assert {"g_0", "constraint_violation", "feasible"} <= rows[0].keys()
        n_feasible = sum(r["feasible"] == "True" for r in rows)
        metrics = json.loads((result.run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["n_feasible"] == n_feasible

    def test_run_log_is_json_lines(self, runner: ExperimentRunner) -> None:
        result = runner.run(Sphere(2), UniformSampler(5), RunSpec("pilot", seed=1, budget=5))
        lines = (result.run_dir / "logs" / "run.log.jsonl").read_text(encoding="utf-8").splitlines()
        records = [json.loads(line) for line in lines]
        assert [r["message"] for r in records] == ["run started", "run finished"]
        assert all(r["run_id"] == result.run_id for r in records)

    def test_console_level_is_not_lowered(
        self, runner: ExperimentRunner, capsys: pytest.CaptureFixture[str]
    ) -> None:
        configure_logging("WARNING", "json")
        runner.run(Sphere(2), UniformSampler(5), RunSpec("pilot", seed=1, budget=5))
        assert capsys.readouterr().err == ""
        assert logging.getLogger("evooptlab").level == logging.WARNING


class TestDeterminism:
    def test_same_seed_same_history(self, runner: ExperimentRunner) -> None:
        a = runner.run(TwoSpheres(3), UniformSampler(6), RunSpec("pilot", seed=42, budget=30))
        b = runner.run(TwoSpheres(3), UniformSampler(6), RunSpec("pilot", seed=42, budget=30))
        assert a.run_id != b.run_id
        assert (a.run_dir / "history.csv").read_bytes() == (b.run_dir / "history.csv").read_bytes()
        assert a.metadata.config_hash == b.metadata.config_hash

    def test_different_seed_different_history(self, runner: ExperimentRunner) -> None:
        a = runner.run(TwoSpheres(3), UniformSampler(6), RunSpec("pilot", seed=42, budget=30))
        b = runner.run(TwoSpheres(3), UniformSampler(6), RunSpec("pilot", seed=43, budget=30))
        assert (a.run_dir / "history.csv").read_bytes() != (b.run_dir / "history.csv").read_bytes()


class TestFailures:
    @pytest.mark.parametrize(
        ("mode", "reason"),
        [
            ("empty", "returned 0 candidates"),
            ("too_many", "returned 4 candidates"),
            ("out_of_bounds", "CandidateError"),
            ("crash", "RuntimeError: algorithm crashed"),
        ],
    )
    def test_contract_violations_are_recorded(
        self, runner: ExperimentRunner, mode: str, reason: str
    ) -> None:
        result = runner.run(Sphere(2), Misbehaving(mode), RunSpec("pilot", seed=1, budget=3))
        assert result.outcome == "failed"
        assert result.metadata.failure_reason is not None
        assert reason in result.metadata.failure_reason
        assert (result.run_dir / "history.csv").is_file()
        assert result.n_evaluations == 0

    def test_objective_failure_is_recorded_and_counted(self, runner: ExperimentRunner) -> None:
        class Crashing(Sphere):
            calls = 0

            def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
                Crashing.calls += 1
                if Crashing.calls == 2:
                    raise RuntimeError("simulator down")
                return super().evaluate_batch(candidates)

        result = runner.run(Crashing(2), UniformSampler(4), RunSpec("pilot", seed=1, budget=20))
        assert result.outcome == "failed"
        assert "simulator down" in (result.metadata.failure_reason or "")
        metrics = json.loads((result.run_dir / "metrics.json").read_text(encoding="utf-8"))
        assert metrics["n_evaluations"] == 8
        assert metrics["n_failed_evaluations"] == 4
        assert len(_rows(result)) == 4  # only the successful batch is in the history

    def test_timeout_is_recorded(self, runner: ExperimentRunner) -> None:
        class Slow(Sphere):
            def evaluate_batch(self, candidates: FloatArray) -> ProblemOutput:
                time.sleep(0.05)
                return super().evaluate_batch(candidates)

        result = runner.run(
            Slow(2), UniformSampler(1), RunSpec("pilot", seed=1, budget=1000, timeout_seconds=0.1)
        )
        assert result.outcome == "failed"
        assert (result.metadata.failure_reason or "").startswith("timeout after")
        assert 0 < result.n_evaluations < 1000

    def test_interrupt_is_recorded_then_reraised(
        self, runner: ExperimentRunner, tmp_path: Path
    ) -> None:
        class Interrupting(UniformSampler):
            name: ClassVar[str] = "interrupting"

            def tell(self, result: Any) -> None:
                raise KeyboardInterrupt

        with pytest.raises(KeyboardInterrupt):
            runner.run(Sphere(2), Interrupting(2), RunSpec("pilot", seed=1, budget=10))
        (run_dir,) = (tmp_path / "artifacts" / "pilot").iterdir()
        stored = RunMetadata.model_validate_json((run_dir / "run_metadata.json").read_text())
        assert stored.outcome == "failed"
        assert stored.failure_reason == "interrupted: KeyboardInterrupt"

    def test_unsupported_algorithm_fails_before_any_artifact(
        self, runner: ExperimentRunner, tmp_path: Path
    ) -> None:
        with pytest.raises(AlgorithmError, match="does not support 2-objective"):
            runner.run(TwoSpheres(2), SingleObjectiveOnly(), RunSpec("pilot", seed=1, budget=5))
        assert not (tmp_path / "artifacts").exists()


class TestNoOverwrite:
    def test_colliding_run_id_never_overwrites(
        self, runner: ExperimentRunner, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("evooptlab.storage.layout.secrets.token_hex", lambda _n: "abcdef")
        first = runner.run(Sphere(2), UniformSampler(5), RunSpec("pilot", seed=1, budget=5))
        before = {p.name: p.read_bytes() for p in first.run_dir.iterdir() if p.is_file()}
        with pytest.raises(FileExistsError):
            runner.run(Sphere(2), UniformSampler(5), RunSpec("pilot", seed=1, budget=5))
        after = {p.name: p.read_bytes() for p in first.run_dir.iterdir() if p.is_file()}
        assert before == after


class TestRunSpecValidation:
    @pytest.mark.parametrize(
        "kw",
        [
            {"stage": "staging"},
            {"seed": -1},
            {"seed": 2**63},
            {"seed": True},
            {"budget": 0},
            {"budget": True},
            {"timeout_seconds": 0.0},
        ],
    )
    def test_invalid_specs_fail_early(self, kw: dict[str, Any]) -> None:
        args: dict[str, Any] = {"stage": "pilot", "seed": 1, "budget": 10}
        args.update(kw)
        with pytest.raises(ValueError):
            RunSpec(**args)
