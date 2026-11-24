"""Study config schema and matrix expansion (validation, pairing, order, hashing)."""

from __future__ import annotations

from pathlib import Path

import pytest
from pydantic import ValidationError

from evooptlab.config import StudyFile, load_config
from evooptlab.core.seeding import derive_run_seeds
from evooptlab.experiments import (
    StudyError,
    build_matrix,
    cell_config_hash,
    matrix_summary,
    replicate_seeds,
)
from study_helpers import make_study


class TestStudySchema:
    def test_repository_study_configs_load_strictly(self, configs_dir: Path) -> None:
        paths = sorted((configs_dir / "studies").glob("*.yaml"))
        assert {p.stem for p in paths} >= {"smoke", "pilot_core"}
        for path in paths:
            config = load_config(path, strict=True)
            assert isinstance(config, StudyFile)
            build_matrix(config.study)  # every repository study is runnable as written

    @pytest.mark.parametrize(
        ("override", "message"),
        [
            ({"seeds": {"policy": "explicit", "values": [1, 1]}}, "seeds must be unique"),
            ({"seeds": {"policy": "derived", "master_seed": 1}}, "n_replicates"),
            ({"seeds": {"policy": "random"}}, "does not match any of the expected tags"),
            ({"stage": "trial"}, "stage"),
            ({"algorithms": [{"name": "nsga2"}, {"name": "nsga2"}]}, "algorithm names must be"),
            (
                {"problems": [{"name": "ZDT1", "objectives": 2, "variables": 4}] * 2},
                "problem names must be unique",
            ),
            ({"timeout_seconds": 0}, "timeout_seconds"),
            ({"unknown": 1}, "Extra inputs are not permitted"),
        ],
    )
    def test_invalid_studies_are_rejected(self, override: dict[str, object], message: str) -> None:
        with pytest.raises(ValidationError, match=message):
            make_study(**override)


class TestMatrix:
    def test_order_interleaves_algorithms_within_each_replicate(self) -> None:
        cells = build_matrix(make_study())
        assert [c.key for c in cells] == [
            ("ZDT1", "random_search", 0),
            ("ZDT1", "nsga2", 0),
            ("ZDT1", "random_search", 1),
            ("ZDT1", "nsga2", 1),
            ("DTLZ2", "random_search", 0),
            ("DTLZ2", "nsga2", 0),
            ("DTLZ2", "random_search", 1),
            ("DTLZ2", "nsga2", 1),
        ]

    def test_explicit_seeds_are_paired_across_algorithms_and_problems(self) -> None:
        cells = build_matrix(make_study())
        assert {(c.replicate, c.seed) for c in cells} == {(0, 1), (1, 2)}

    def test_derived_seeds_are_paired_across_algorithms_but_differ_by_problem(self) -> None:
        study = make_study(seeds={"policy": "derived", "master_seed": 2026, "n_replicates": 3})
        cells = build_matrix(study)
        for problem in ("ZDT1", "DTLZ2"):
            expected = derive_run_seeds(2026, 3, problem)
            assert replicate_seeds(study, problem) == expected
            for algorithm in ("random_search", "nsga2"):
                got = [c.seed for c in cells if c.key[:2] == (problem, algorithm)]
                assert got == expected
        assert replicate_seeds(study, "ZDT1") != replicate_seeds(study, "DTLZ2")

    def test_every_error_is_reported_before_running(self) -> None:
        study = make_study(
            problems=[
                {"name": "ZDT1", "objectives": 2, "variables": 4},
                {"name": "ZDT9", "objectives": 2, "variables": 4},
            ],
            algorithms=[
                {"name": "ga"},
                {"name": "nsga2", "parameters": {"popsize": 3}},
                {"name": "differential_evolution_variant"},
            ],
        )
        with pytest.raises(StudyError) as info:
            build_matrix(study)
        text = str(info.value)
        assert "problem ZDT9: unknown benchmark" in text
        assert "algorithm nsga2: nsga2: unknown hyperparameters" in text
        assert "algorithm differential_evolution_variant: unknown algorithm" in text
        assert "ga does not support ZDT1" in text  # out-of-domain pairs are never skipped silently

    def test_cell_hash_is_stable_and_specific(self) -> None:
        study = make_study()
        cells = build_matrix(study)
        hashes = [cell_config_hash(study, c) for c in cells]
        assert hashes == [cell_config_hash(study, c) for c in build_matrix(make_study())]
        assert len(set(hashes)) == len(cells)
        other = make_study(name="other")
        assert cell_config_hash(other, build_matrix(other)[0]) != hashes[0]

    def test_summary_counts(self) -> None:
        study = make_study()
        summary = matrix_summary(study, build_matrix(study))
        assert summary["n_runs"] == 8
        assert summary["n_replicates_per_cell"] == 2
        assert summary["total_objective_evaluations"] == 8 * 30
