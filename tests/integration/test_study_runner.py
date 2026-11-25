"""Running study matrices: immutability, resume rules, reproducibility, final-stage guard."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from evooptlab.experiments import RunCell, StudyError, collect_study, run_study
from evooptlab.experiments import study as study_module
from evooptlab.storage import ArtifactLayout
from study_helpers import BUDGET, Exploding, Interrupting, builder_replacing, make_study

pytestmark = pytest.mark.integration


@pytest.fixture
def layout(tmp_path: Path) -> ArtifactLayout:
    return ArtifactLayout(tmp_path / "artifacts")


def _snapshot(root: Path) -> dict[str, bytes]:
    return {
        str(p.relative_to(root)): p.read_bytes() for p in sorted(root.rglob("*")) if p.is_file()
    }


def test_runs_every_cell_once_with_exact_budget(layout: ArtifactLayout) -> None:
    study = make_study()
    report = run_study(study, layout)
    assert len(report.executed) == 8
    assert report.n_failed == 0
    assert not report.skipped
    collection = collect_study(study, layout)
    assert not collection.missing
    for record in collection.canonical.values():
        assert record.metrics is not None
        assert record.metrics["n_evaluations"] == BUDGET
        assert record.metadata.status == "pilot"
        assert record.study == "tiny"


def test_rerun_without_resume_is_refused_and_writes_nothing(layout: ArtifactLayout) -> None:
    study = make_study()
    run_study(study, layout)
    before = _snapshot(layout.root)
    with pytest.raises(StudyError, match="already has stored runs for 8 of 8 cells"):
        run_study(study, layout)
    assert _snapshot(layout.root) == before


def test_resume_skips_settled_cells_and_never_modifies_artifacts(layout: ArtifactLayout) -> None:
    study = make_study()
    run_study(study, layout)
    before = _snapshot(layout.root)
    report = run_study(study, layout, resume=True)
    assert not report.executed
    assert len(report.skipped) == 8
    assert _snapshot(layout.root) == before


def test_resume_completes_a_partially_run_study(layout: ArtifactLayout) -> None:
    run_study(make_study(seeds={"policy": "explicit", "values": [1]}), layout)
    # Adding a replicate keeps the existing cells' hashes, so only the new cells run.
    report = run_study(make_study(), layout, resume=True)
    assert len(report.skipped) == 4
    assert {key[2] for key, _, _ in report.executed} == {1}


def test_histories_are_reproducible_across_roots(tmp_path: Path) -> None:
    a, b = ArtifactLayout(tmp_path / "a"), ArtifactLayout(tmp_path / "b")
    run_study(make_study(), a)
    run_study(make_study(), b)
    ca, cb = collect_study(make_study(), a), collect_study(make_study(), b)
    for key, record in ca.canonical.items():
        assert record.history_path().read_bytes() == cb.canonical[key].history_path().read_bytes()
        assert record.metadata.config_hash == cb.canonical[key].metadata.config_hash


def test_genuine_failures_are_results_and_are_not_retried(
    layout: ArtifactLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ("ZDT1", "random_search", 0)
    monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Exploding))
    report = run_study(make_study(), layout)
    assert report.n_failed == 1
    monkeypatch.undo()

    report = run_study(make_study(), layout, resume=True)
    assert not report.executed  # re-running until success would be cherry-picking
    record = collect_study(make_study(), layout).canonical[target]
    assert record.metadata.outcome == "failed"
    assert "boom" in (record.metadata.failure_reason or "")


def test_interrupted_runs_are_rerun_under_a_new_id_and_kept(
    layout: ArtifactLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = ("ZDT1", "random_search", 1)
    monkeypatch.setattr(RunCell, "build_algorithm", builder_replacing(target, Interrupting))
    with pytest.raises(KeyboardInterrupt):
        run_study(make_study(), layout)
    monkeypatch.undo()

    first = collect_study(make_study(), layout)
    assert [k for k, _ in first.interrupted] == [target]
    interrupted_id = first.interrupted[0][1]

    report = run_study(make_study(), layout, resume=True)
    assert next(key for key, _, _ in report.executed) == target
    after = collect_study(make_study(), layout)
    assert after.canonical[target].metadata.outcome == "completed"
    assert after.canonical[target].run_id != interrupted_id
    assert (layout.stage_dir("pilot") / interrupted_id).is_dir()  # evidence is kept
    assert not after.missing


@pytest.mark.parametrize(
    ("git", "message"),
    [
        (SimpleNamespace(commit=None, dirty=None), "known commit"),
        (SimpleNamespace(commit="a" * 40, dirty=True), "clean working tree"),
        (SimpleNamespace(commit="a" * 40, dirty=None), "clean working tree"),
    ],
)
def test_final_stage_requires_a_clean_commit(
    layout: ArtifactLayout, monkeypatch: pytest.MonkeyPatch, git: SimpleNamespace, message: str
) -> None:
    monkeypatch.setattr(
        study_module, "capture_environment", lambda *_a, **_k: SimpleNamespace(git=git)
    )
    with pytest.raises(StudyError, match=message):
        run_study(make_study(stage="final"), layout)
    assert not layout.root.exists()


def test_final_stage_runs_with_a_clean_commit(
    layout: ArtifactLayout, monkeypatch: pytest.MonkeyPatch
) -> None:
    git = SimpleNamespace(commit="a" * 40, dirty=False)
    monkeypatch.setattr(
        study_module, "capture_environment", lambda *_a, **_k: SimpleNamespace(git=git)
    )
    study = make_study(stage="final", seeds={"policy": "explicit", "values": [1]})
    assert len(run_study(study, layout).executed) == 4
    assert layout.stage_dir("final").is_dir()
    assert not layout.stage_dir("pilot").exists()


def test_progress_callback_sees_every_cell(layout: ArtifactLayout) -> None:
    seen: list[tuple[int, int, str]] = []
    run_study(
        make_study(), layout, progress=lambda i, n, _cell, status: seen.append((i, n, status))
    )
    assert [(i, n) for i, n, _ in seen] == [(i, 8) for i in range(1, 9)]
    assert {s for _, _, s in seen} == {"completed"}
