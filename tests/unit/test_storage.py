"""Tests for artifact layout conventions and the run-metadata schema."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from evooptlab.storage import ArtifactLayout, RunMetadata, make_run_id, parse_run_id

T0 = datetime(2026, 11, 23, 12, 0, tzinfo=UTC)


def _metadata(**overrides: Any) -> RunMetadata:
    fields: dict[str, Any] = {
        "run_id": make_run_id("ZDT1", "nsga2", 10000, 11, when=T0, short_id="a1b2c3"),
        "git_commit": "0" * 40,
        "algorithm": "nsga2",
        "problem": "ZDT1",
        "seed": 11,
        "objective_evaluation_budget": 10000,
        "started_at_utc": T0,
        "hardware": {"cpu": "test-cpu"},
        "software": {"python": "3.12.0"},
        "config_path": "config.yaml",
        "status": "pilot",
    }
    fields.update(overrides)
    return RunMetadata.model_validate(fields)


class TestRunId:
    def test_format_matches_protocol(self) -> None:
        run_id = make_run_id("ZDT1", "nsga2", 10000, 11, when=T0, short_id="a1b2c3")
        assert run_id == "ZDT1__nsga2__10000evals__seed-11__20261123-a1b2c3"

    def test_round_trip(self) -> None:
        run_id = make_run_id("DTLZ7", "random_search", 500, 0, when=T0, short_id="deadbeef")
        parts = parse_run_id(run_id)
        assert parts.problem == "DTLZ7"
        assert parts.algorithm == "random_search"
        assert parts.budget == 500
        assert parts.seed == 0
        assert parts.date == date(2026, 11, 23)
        assert parts.short_id == "deadbeef"

    def test_random_short_ids_are_unique(self) -> None:
        ids = {make_run_id("ZDT1", "nsga2", 10, 1, when=T0) for _ in range(200)}
        assert len(ids) == 200

    def test_date_uses_utc(self) -> None:
        # 22:00 at UTC-5 on the 23rd is already the 24th in UTC.
        when = datetime(2026, 11, 23, 22, 0, tzinfo=timezone(timedelta(hours=-5)))
        assert "__20261124-" in make_run_id("p", "a", 1, 1, when=when, short_id="abcdef")

    @pytest.mark.parametrize(
        ("problem", "algorithm"),
        [("bad__name", "nsga2"), ("ZDT1", "a/b"), ("", "nsga2"), ("ZDT1", "../x")],
    )
    def test_rejects_unsafe_components(self, problem: str, algorithm: str) -> None:
        with pytest.raises(ValueError):
            make_run_id(problem, algorithm, 10, 1, when=T0, short_id="abcdef")

    @pytest.mark.parametrize(
        ("budget", "seed", "short_id"), [(0, 1, "abcdef"), (10, -1, "abcdef"), (10, 1, "XYZ")]
    )
    def test_rejects_invalid_numbers_and_ids(self, budget: int, seed: int, short_id: str) -> None:
        with pytest.raises(ValueError):
            make_run_id("ZDT1", "nsga2", budget, seed, when=T0, short_id=short_id)

    def test_parse_rejects_garbage(self) -> None:
        with pytest.raises(ValueError, match="not a valid run id"):
            parse_run_id("../../etc/passwd")


class TestRunMetadata:
    def test_valid_running_record(self) -> None:
        md = _metadata()
        assert md.outcome == "running"
        assert md.schema_version == "1"

    def test_finished_returns_new_object(self) -> None:
        md = _metadata()
        done = md.finished(T0 + timedelta(minutes=5), "completed")
        assert done.outcome == "completed"
        assert md.outcome == "running"

    def test_failed_requires_reason(self) -> None:
        with pytest.raises(ValidationError, match="failure_reason"):
            _metadata().finished(T0 + timedelta(minutes=1), "failed")
        failed = _metadata().finished(T0 + timedelta(minutes=1), "failed", "timeout")
        assert failed.failure_reason == "timeout"

    def test_finish_before_start_is_rejected(self) -> None:
        with pytest.raises(ValidationError, match="earlier"):
            _metadata().finished(T0 - timedelta(seconds=1), "completed")

    def test_running_cannot_have_finish_time(self) -> None:
        with pytest.raises(ValidationError, match="running run"):
            _metadata(finished_at_utc=T0)

    def test_reason_only_for_failures(self) -> None:
        with pytest.raises(ValidationError, match="only allowed"):
            _metadata(failure_reason="x")

    def test_naive_datetimes_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(started_at_utc=datetime(2026, 1, 1))

    def test_unknown_stage_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(status="pilot_or_final")

    def test_extra_fields_are_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(unexpected=1)

    def test_bad_commit_hash_is_rejected(self) -> None:
        with pytest.raises(ValidationError):
            _metadata(git_commit="not-a-sha")

    def test_committed_json_schema_is_current(self, repo_root: Path) -> None:
        schema_path = repo_root / "docs" / "schemas" / "run_metadata.schema.json"
        committed = json.loads(schema_path.read_text(encoding="utf-8"))
        assert committed == RunMetadata.model_json_schema(), (
            "regenerate with: evooptlab schema run-metadata > docs/schemas/run_metadata.schema.json"
        )


class TestArtifactLayout:
    def test_stage_separation(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        run_id = _metadata().run_id
        assert layout.run_dir("pilot", run_id).parent.name == "pilot"
        assert layout.run_dir("final", run_id).parent.name == "final"

    def test_create_write_read(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        md = _metadata()
        run_dir = layout.create_run_dir("pilot", md.run_id)
        assert (run_dir / "logs").is_dir()
        path = layout.write_metadata(md)
        assert path.name == "run_metadata.json"
        assert layout.read_metadata("pilot", md.run_id) == md

    def test_never_overwrites_run_dir(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        run_id = _metadata().run_id
        layout.create_run_dir("pilot", run_id)
        with pytest.raises(FileExistsError):
            layout.create_run_dir("pilot", run_id)

    def test_never_overwrites_metadata(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        md = _metadata()
        layout.create_run_dir("pilot", md.run_id)
        layout.write_metadata(md)
        with pytest.raises(FileExistsError):
            layout.write_metadata(md)

    def test_record_finish_once(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        md = _metadata()
        layout.create_run_dir("pilot", md.run_id)
        layout.write_metadata(md)
        done = md.finished(T0 + timedelta(minutes=2), "completed")
        layout.record_finish(done)
        assert layout.read_metadata("pilot", md.run_id) == done
        with pytest.raises(FileExistsError, match="already finished"):
            layout.record_finish(done)

    def test_record_finish_rejects_other_changes(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        md = _metadata()
        layout.create_run_dir("pilot", md.run_id)
        layout.write_metadata(md)
        tampered = _metadata(seed=99).finished(T0 + timedelta(minutes=2), "completed")
        with pytest.raises(ValueError, match="only finish fields"):
            layout.record_finish(tampered)
        with pytest.raises(ValueError, match="completed or failed"):
            layout.record_finish(md)

    def test_rejects_unknown_kind_and_stage(self, tmp_path: Path) -> None:
        layout = ArtifactLayout(tmp_path)
        run_id = _metadata().run_id
        with pytest.raises(ValueError, match="unknown run file kind"):
            layout.run_file("pilot", run_id, "weights")
        with pytest.raises(ValueError, match="unknown stage"):
            layout.stage_dir("staging")  # type: ignore[arg-type]

    def test_rejects_path_traversal(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            ArtifactLayout(tmp_path).run_dir("pilot", "../outside")
