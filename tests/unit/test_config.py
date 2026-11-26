"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evooptlab.config import (
    BenchmarksFile,
    ConfigError,
    ExperimentsFile,
    HPOTasksFile,
    config_hash,
    load_config,
    unresolved_fields,
)


def _write(tmp_path: Path, text: str, name: str = "cfg.yaml") -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


BENCHMARK_YAML = """
benchmark_suite:
  name: tiny
  problems:
    - {name: ZDT1, objectives: 2, variables: 30}
  evaluation_budget: 100
  seeds: [1, 2, 3]
  pilot: true
"""


class TestRepositoryConfigs:
    """The committed configs must always validate."""

    def test_benchmarks_yaml_validates(self, configs_dir: Path) -> None:
        cfg = load_config(configs_dir / "benchmarks.yaml")
        assert isinstance(cfg, BenchmarksFile)
        names = [p.name for p in cfg.benchmark_suite.problems]
        assert names == ["ZDT1", "ZDT2", "ZDT3", "DTLZ2", "DTLZ7"]
        assert cfg.benchmark_suite.pilot is True

    def test_experiments_yaml_validates(self, configs_dir: Path) -> None:
        cfg = load_config(configs_dir / "experiments.yaml")
        assert isinstance(cfg, ExperimentsFile)
        assert cfg.experiment.budget.unit == "objective_evaluations"

    def test_hpo_yaml_validates(self, configs_dir: Path) -> None:
        cfg = load_config(configs_dir / "hpo_tasks.yaml")
        assert isinstance(cfg, HPOTasksFile)
        assert {t.name for t in cfg.hpo.tasks} >= {"breast_cancer_smoke", "california_housing"}

    def test_hpo_yaml_reports_open_decisions(self, configs_dir: Path) -> None:
        cfg = load_config(configs_dir / "hpo_tasks.yaml")
        unresolved = dict(unresolved_fields(cfg))
        assert unresolved["hpo.tasks[1].target_metric"] == "define_before_run"
        assert unresolved["hpo.tasks[1].task_type"] == "classification_or_regression"
        assert unresolved["hpo.split.strategy"] == "task_specific"

    def test_hpo_yaml_is_rejected_in_strict_mode(self, configs_dir: Path) -> None:
        with pytest.raises(ConfigError, match="unresolved decisions"):
            load_config(configs_dir / "hpo_tasks.yaml", strict=True)


class TestValidation:
    def test_minimal_benchmark_config(self, tmp_path: Path) -> None:
        cfg = load_config(_write(tmp_path, BENCHMARK_YAML))
        assert isinstance(cfg, BenchmarksFile)
        assert unresolved_fields(cfg) == []
        assert load_config(_write(tmp_path, BENCHMARK_YAML), strict=True) == cfg

    def test_unknown_key_is_rejected(self, tmp_path: Path) -> None:
        text = BENCHMARK_YAML + "  evaluation_budgett: 5\n"
        with pytest.raises(ConfigError, match="evaluation_budgett"):
            load_config(_write(tmp_path, text))

    def test_duplicate_seeds_are_rejected(self, tmp_path: Path) -> None:
        text = BENCHMARK_YAML.replace("[1, 2, 3]", "[1, 1, 3]")
        with pytest.raises(ConfigError, match="seeds must be unique"):
            load_config(_write(tmp_path, text))

    def test_duplicate_problems_are_rejected(self, tmp_path: Path) -> None:
        text = BENCHMARK_YAML.replace(
            "    - {name: ZDT1, objectives: 2, variables: 30}",
            "    - {name: ZDT1, objectives: 2, variables: 30}\n"
            "    - {name: ZDT1, objectives: 2, variables: 30}",
        )
        with pytest.raises(ConfigError, match="problem names must be unique"):
            load_config(_write(tmp_path, text))

    @pytest.mark.parametrize("budget", ["0", "-10"])
    def test_non_positive_budget_is_rejected(self, tmp_path: Path, budget: str) -> None:
        text = BENCHMARK_YAML.replace("evaluation_budget: 100", f"evaluation_budget: {budget}")
        with pytest.raises(ConfigError, match="evaluation_budget"):
            load_config(_write(tmp_path, text))

    def test_wrong_budget_unit_is_rejected(self, configs_dir: Path, tmp_path: Path) -> None:
        text = (configs_dir / "experiments.yaml").read_text(encoding="utf-8")
        text = text.replace("unit: objective_evaluations", "unit: seconds")
        with pytest.raises(ConfigError, match="unit"):
            load_config(_write(tmp_path, text))

    @pytest.mark.parametrize("fraction", ["0.0", "1.0", "1.5"])
    def test_test_fraction_must_be_open_interval(
        self, configs_dir: Path, tmp_path: Path, fraction: str
    ) -> None:
        text = (configs_dir / "hpo_tasks.yaml").read_text(encoding="utf-8")
        text = text.replace("test_fraction: 0.2", f"test_fraction: {fraction}")
        with pytest.raises(ConfigError, match="test_fraction"):
            load_config(_write(tmp_path, text))


class TestLoaderErrors:
    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(tmp_path / "nope.yaml")

    def test_invalid_yaml(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="invalid YAML"):
            load_config(_write(tmp_path, "a: [unclosed"))

    def test_non_mapping_top_level(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="must be a mapping"):
            load_config(_write(tmp_path, "- 1\n- 2\n"))

    def test_unknown_root_key(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="unknown top-level key"):
            load_config(_write(tmp_path, "something_else: {}\n"))

    def test_multiple_root_keys(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigError, match="exactly one top-level key"):
            load_config(_write(tmp_path, "experiment: {}\nhpo: {}\n"))


class TestConfigHash:
    def test_hash_ignores_formatting_and_comments(self, tmp_path: Path) -> None:
        a = load_config(_write(tmp_path, BENCHMARK_YAML, "a.yaml"))
        reformatted = "# comment\n" + BENCHMARK_YAML.replace(
            "[1, 2, 3]", "\n    - 1\n    - 2\n    - 3"
        )
        b = load_config(_write(tmp_path, reformatted, "b.yaml"))
        assert config_hash(a) == config_hash(b)

    def test_hash_changes_with_content(self, tmp_path: Path) -> None:
        a = load_config(_write(tmp_path, BENCHMARK_YAML, "a.yaml"))
        b = load_config(_write(tmp_path, BENCHMARK_YAML.replace("100", "200"), "b.yaml"))
        assert config_hash(a) != config_hash(b)
        assert len(config_hash(a)) == 64


class TestAnalysisPlanAndReporting:
    def test_shipped_plan_is_a_proposal_and_reporting_loads(self, configs_dir: Path) -> None:
        from evooptlab.config import AnalysisPlanFile, ReportingFile

        plan = load_config(configs_dir / "analysis_plan.yaml", strict=True)
        assert isinstance(plan, AnalysisPlanFile)
        assert plan.analysis_plan.status == "proposal"  # P9 is an owner decision
        reporting = load_config(configs_dir / "reporting.yaml", strict=True)
        assert isinstance(reporting, ReportingFile)

    @pytest.mark.parametrize(
        ("change", "match"),
        [
            ({"hpo_metrics": [{"name": "a", "direction": "minimize"}]}, "exactly one hpo"),
            (
                {
                    "benchmark_metrics": [
                        {"name": "a", "direction": "minimize", "primary": True},
                        {"name": "a", "direction": "maximize"},
                    ]
                },
                "unique",
            ),
        ],
    )
    def test_plan_rules(self, configs_dir: Path, change: dict[str, object], match: str) -> None:
        from evooptlab.config import AnalysisPlanConfig, load_yaml

        data = load_yaml(configs_dir / "analysis_plan.yaml")["analysis_plan"]
        with pytest.raises(ValidationError, match=match):
            AnalysisPlanConfig.model_validate({**data, **change})
