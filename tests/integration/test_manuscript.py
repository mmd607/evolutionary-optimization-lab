"""The shipped manuscript draft passes the claims audit (Phase 06 gate)."""

from __future__ import annotations

from pathlib import Path

from evooptlab.reporting.claims import audit


def test_manuscript_draft_passes_the_claims_audit(repo_root: Path) -> None:
    paper = repo_root / "reports" / "paper"
    report = audit(
        paper / "manuscript.md",
        matrix=paper / "claim_evidence.csv",
        literature=repo_root / "docs" / "literature" / "literature_matrix.csv",
        repo_root=repo_root,
    )
    assert report.status == "PASS", [f.__dict__ for f in report.findings]
    assert report.manuscript_status == "draft"  # no final results exist yet
    assert report.n_citations == 0  # the literature matrix has no verified entry yet
