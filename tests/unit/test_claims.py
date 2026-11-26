"""Claims audit: every rule has a passing and a failing case."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from evooptlab.cli import main
from evooptlab.reporting.claims import audit, render

LIT_HEADER = (
    "paper_id,authors,year,title,venue,doi_or_url,problem,algorithms,benchmarks,metrics,"
    "budget_protocol,main_findings,limitations,relevance,verified\n"
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "src.py").write_text("x = 1\n", encoding="utf-8")
    (tmp_path / "lit.csv").write_text(
        LIT_HEADER
        + "good2020,A,2020,T,V,doi,,,,,,,,RQ1,yes\nweak2021,B,2021,T,V,doi,,,,,,,,RQ1,no\n",
        encoding="utf-8",
    )
    (tmp_path / "values.json").write_text(
        json.dumps(
            {
                "s/ZDT1/nsga2/igd_plus/median": {"value": 0.0123456, "preliminary": True},
                "s/ZDT1/a-vs-b/igd_plus/p_holm": {"value": 0.004, "preliminary": True},
                "s/final/x": {"value": 2.5, "preliminary": False},
            }
        ),
        encoding="utf-8",
    )
    return tmp_path


def _write(repo: Path, body: str, rows: list[str], status: str = "draft") -> Path:
    (repo / "matrix.csv").write_text(
        "claim_id,section,claim,evidence_type,evidence_ref,status\n"
        + "".join(r + "\n" for r in rows),
        encoding="utf-8",
    )
    path = repo / "paper.md"
    path.write_text(f"---\nstatus: {status}\n---\n\n{body}\n", encoding="utf-8")
    return path


def _audit(repo: Path, path: Path) -> list[tuple[str, str]]:
    report = audit(
        path,
        matrix=repo / "matrix.csv",
        literature=repo / "lit.csv",
        values=[repo / "values.json"],
        repo_root=repo,
    )
    return [(f.severity, f.rule) for f in report.findings]


def test_clean_draft_passes(repo: Path) -> None:
    body = (
        "# 4. Methodology\n\nWe use a budget of 10 000 evaluations. <!-- claim: C1 -->\n"
        "Prior work exists [@good2020].\n\n"
        "# 6. Results\n\nDRAFT — RESULTS PENDING. Median IGD+ was "
        "{{value:s/ZDT1/nsga2/igd_plus/median:.3f}} "
        "(Table 2, RQ1). <!-- claim: C2 -->\n"
    )
    rows = [
        "C1,4,budget,code,src.py,supported",
        "C2,6,igd,value,s/ZDT1/nsga2/igd_plus/median,supported",
    ]
    assert _audit(repo, _write(repo, body, rows)) == []


@pytest.mark.parametrize(
    ("body", "rule"),
    [
        ("# Results\n\nIGD+ fell to 0.012.", "number"),
        ("# Abstract\n\nWe ran 20 seeds.", "number"),
        ("## 6. Results\n\n### 6.1 RQ1\n\nNSGA-II reached 0.9.", "number"),
        ("# Intro\n\nA novel framework.", "wording"),
        ("# Intro\n\nState-of-the-art results.", "wording"),
        ("# Results\n\nA was significantly better.", "wording"),
        ("# Intro\n\nSee [@missing1999].", "citation"),
        ("# Intro\n\nSee [@weak2021].", "citation"),
        ("# Intro\n\nUnbacked. <!-- claim: C9 -->", "claim"),
    ],
)
def test_failing_rules(repo: Path, body: str, rule: str) -> None:
    assert ("FAIL", rule) in _audit(repo, _write(repo, body, []))


def test_examples_in_inline_code_are_not_references(repo: Path) -> None:
    body = "# Intro\n\nWrite `{{value:KEY}}` and cite with `[@key]`."
    assert _audit(repo, _write(repo, body, [])) == []


def test_significance_with_corrected_p_value_is_allowed(repo: Path) -> None:
    body = (
        "# Results\n\nA differed significantly (Holm p = {{value:s/ZDT1/a-vs-b/igd_plus/p_holm}})."
    )
    assert _audit(repo, _write(repo, body, [])) == []


def test_numbers_in_code_comments_and_methods_are_not_results(repo: Path) -> None:
    body = (
        "# Methodology\n\nPopulation 100, offset 0.1.\n\n# Results\n\n```\nlog 123\n```\n"
        "<!-- note: 42 -->\nSee Section 3 and ADR 0005.\n"
    )
    assert _audit(repo, _write(repo, body, [])) == []


def test_evidence_rows_are_checked(repo: Path) -> None:
    body = "# Intro\n\nA. <!-- claim: C1 -->\nB. <!-- claim: C2 -->\nC. <!-- claim: C3 -->"
    rows = [
        "C1,1,a,code,nope.py,supported",
        "C2,1,b,literature,weak2021,supported",
        "C3,1,c,magic,x,supported",
        "C4,1,d,code,src.py,supported",
    ]
    findings = _audit(repo, _write(repo, body, rows))
    assert findings.count(("FAIL", "evidence")) == 3
    assert ("WARN", "claim") in findings  # C4 has evidence but is never cited


def test_pending_claims_need_the_marker_in_drafts_and_are_banned_in_final(repo: Path) -> None:
    rows = ["C1,6,result,value,s/x,pending"]
    draft = _write(repo, "# Results\n\nPending. <!-- claim: C1 -->", rows)
    assert ("FAIL", "pending") in _audit(repo, draft)
    final = _write(repo, "# Results\n\nRESULTS PENDING. <!-- claim: C1 -->", rows, status="final")
    findings = _audit(repo, final)
    assert ("FAIL", "pending") in findings and ("FAIL", "evidence") in findings


def test_values_in_final_must_exist_and_be_final(repo: Path) -> None:
    body = (
        "# Results\n\nA {{value:s/ZDT1/nsga2/igd_plus/median}} B {{value:s/final/x}} "
        "C {{value:s/nowhere}}"
    )
    findings = _audit(repo, _write(repo, body, [], status="final"))
    assert findings.count(("FAIL", "value")) == 2  # preliminary + unresolved
    assert ("WARN", "value") in _audit(repo, _write(repo, "# Results\n\n{{value:s/nowhere}}", []))
    assert ("FAIL", "front_matter") in _audit(repo, _write(repo, "x", [], status="maybe"))


def test_render_and_cli(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    store = json.loads((repo / "values.json").read_text(encoding="utf-8"))
    assert (
        render("v={{value:s/final/x:.2f}} m={{value:s/none}}", store) == "v=2.50 m={{value:s/none}}"
    )
    store["s/nil"] = {"value": None}
    assert render("{{value:s/nil}}", store) == "—"

    paper = _write(repo, "# Results\n\nIGD+ fell to 0.012.", [])
    args = ["--matrix", str(repo / "matrix.csv"), "--literature", str(repo / "lit.csv")]
    assert main(["audit-claims", str(paper), *args]) == 1
    assert "FAIL  line" in capsys.readouterr().out
    assert main(["audit-claims", str(paper), *args, "--json"]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "FAIL"
    assert main(["audit-claims", str(repo / "missing.md"), *args]) == 2
    capsys.readouterr()

    out = repo / "rendered.md"
    good = _write(repo, "# Results\n\n{{value:s/final/x}}", [])
    assert (
        main(
            ["render-paper", str(good), "--values", str(repo / "values.json"), "--output", str(out)]
        )
        == 0
    )
    assert "2.5" in out.read_text(encoding="utf-8")
    assert (
        main(
            ["render-paper", str(good), "--values", str(repo / "values.json"), "--output", str(out)]
        )
        == 2
    )
